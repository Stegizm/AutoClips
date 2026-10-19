"""Shorts Forge CLI giriş noktası.

Typer ile komut satırı arayüzü sunar; tüm pipeline adımlarını sırayla çalıştırır
ve Rich ile ilerleme göstergesi basar.

Kullanım:
    python main.py --topic "Python'da list comprehension" --style "eğitici"
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

import config
from shorts_forge import __version__
from shorts_forge.media_fetcher import MediaClip, fetch_media
from shorts_forge.script_generator import Script, generate_script
from shorts_forge.subtitle_generator import SubtitleCue, generate_subtitles
from shorts_forge.utils import console, ensure_dir, log_error, log_step
from shorts_forge.video_composer import compose_video
from shorts_forge.voice_generator import VoiceClip, generate_voices

# Typer uygulaması
app: typer.Typer = typer.Typer(
    help="Shorts Forge - Yerel tabanlı otomatik Shorts/Reels üretim hattı.",
    add_completion=False,
)


def _run_pipeline(topic: str, style: str, subtitle_mode: str) -> None:
    """Tüm üretim hattını sırayla çalıştırır.

    Args:
        topic: Videonun konusu.
        style: Anlatım tarzı.
        subtitle_mode: Altyazı modu ('word' veya 'sentence').
    """
    # Gerekli dizinleri güvence altına al
    ensure_dir(config.OUTPUT_DIR)
    ensure_dir(config.TEMP_DIR)

    # Pipeline adımları için tek bir Rich ilerleme çubuğu
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        total_steps: int = 5

        task1 = progress.add_task("Senaryo üretiliyor (Ollama)...", total=total_steps)

        script: Script = generate_script(topic=topic, style=style)
        progress.update(task1, advance=1, description=f"Senaryo hazır: {script.title}")

        progress.advance(task1)  # Sesler üretiliyor
        narrations: list[str] = [scene.narration for scene in script.scenes]
        voices: list[VoiceClip] = generate_voices(narrations, config.TEMP_DIR)

        progress.advance(task1)  # Stok videolar indiriliyor
        visual_prompts: list[str] = [scene.visual_prompt for scene in script.scenes]
        media: list[Optional[MediaClip]] = fetch_media(visual_prompts, config.TEMP_DIR)

        progress.advance(task1)  # Altyazılar hazırlanıyor
        durations: list[float] = [v.duration for v in voices]
        subtitles: list[SubtitleCue] = generate_subtitles(
            narrations=narrations, durations=durations, mode=subtitle_mode
        )

        progress.advance(task1)  # Video monte ediliyor
        result = compose_video(
            scenes=script.scenes,
            voices=voices,
            media=media,
            subtitles=subtitles,
            topic=topic,
            output_dir=config.OUTPUT_DIR,
            temp_dir=config.TEMP_DIR,
        )

    console.print(
        Panel.fit(
            f"[bold green]✔ Video üretildi![/bold green]\n"
            f"Dosya: [cyan]{result.output_path}[/cyan]\n"
            f"Süre: {result.total_duration:.1f} sn | Boyut: {config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT}",
            title="Shorts Forge",
            border_style="green",
        )
    )


@app.command()
def main(
    topic: str = typer.Option(..., "--topic", "-t", help="Videonun konusu / kavramı."),
    style: str = typer.Option("eğitici", "--style", "-s", help="Anlatım tarzı."),
    subtitle_mode: str = typer.Option(
        "word",
        "--subtitles",
        help="Altyazı modu: 'word' (kelime kelime) veya 'sentence' (cümle bazlı).",
    ),
    version: bool = typer.Option(False, "--version", help="Sürüm bilgisini yazdır ve çık."),
) -> None:
    """Komut satırı ana girdisi: konudan Shorts videosu üretir."""
    if version:
        console.print(f"Shorts Forge v{__version__}")
        raise typer.Exit()

    log_step(f"Shorts Forge başlatıldı — konu: '{topic}'")

    # Ön kontroller
    if not config.PEXELS_API_KEY or config.PEXELS_API_KEY == "your_pexels_api_key_here":
        log_error("PEXELS_API_KEY tanımlı değil. .env dosyasını kopyalayıp doldurun.")
        raise typer.Exit(code=1)

    if subtitle_mode not in ("word", "sentence"):
        log_error("Geçersiz altyazı modu. 'word' veya 'sentence' kullanın.")
        raise typer.Exit(code=1)

    try:
        _run_pipeline(topic=topic, style=style, subtitle_mode=subtitle_mode)
    except KeyboardInterrupt:
        log_error("Kullanıcı tarafından iptal edildi.")
        raise typer.Exit(code=130)
    except Exception as exc:  # noqa: BLE001 - CLI en dış yakalayıcı, temiz raporlama
        log_error(f"Pipeline başarısız oldu: {exc}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
