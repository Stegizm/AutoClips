"""Shorts Forge CLI giriş noktası.

Typer ile komut satırı arayüzü sunar; tüm pipeline adımlarını sırayla çalıştırır
ve Rich ile ilerleme göstergesi basar. Ayrıca masaüstü GUI'sini başlatan bir
alt komut (`gui`) içerir.

Kullanım:
    python main.py generate --topic "Python'da list comprehension" --style "eğitici"
    python main.py gui
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
from shorts_forge.core import PIPELINE_STEPS, run_pipeline, validate_settings
from shorts_forge.utils import console, ensure_dir, log_error, log_info, log_step

# Typer uygulaması
app: typer.Typer = typer.Typer(
    help="Shorts Forge - Yerel tabanlı otomatik Shorts/Reels üretim hattı.",
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    """--version bayrağı sürümü yazdırıp çıkar."""
    if value:
        console.print(f"Shorts Forge v{__version__}")
        raise typer.Exit()


@app.callback()
def common(
    version: Optional[bool] = typer.Option(
        None, "--version", callback=_version_callback, is_eager=True,
        help="Sürüm bilgisini yazdır ve çık.",
    ),
) -> None:
    """Ortak CLI seçenekleri (sürüm)."""


@app.command()
def generate(
    topic: str = typer.Option(..., "--topic", "-t", help="Videonun konusu / kavramı."),
    style: str = typer.Option("eğitici", "--style", "-s", help="Anlatım tarzı."),
    subtitle_mode: str = typer.Option(
        "word",
        "--subtitles",
        help="Altyazı modu: 'word' (kelime kelime) veya 'sentence' (cümle bazlı).",
    ),
) -> None:
    """Komut satırı ana girdisi: konudan Shorts videosu üretir."""
    log_step(f"Shorts Forge başlatıldı — konu: '{topic}'")

    # Ön kontroller (ayarlar + altyazı modu)
    problems: list[str] = validate_settings()
    if problems:
        for problem in problems:
            log_error(problem)
        raise typer.Exit(code=1)

    if subtitle_mode not in ("word", "sentence"):
        log_error("Geçersiz altyazı modu. 'word' veya 'sentence' kullanın.")
        raise typer.Exit(code=1)

    # Gerekli dizinleri güvence altına al
    ensure_dir(config.OUTPUT_DIR)
    ensure_dir(config.TEMP_DIR)

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            total_steps: int = len(PIPELINE_STEPS)
            task = progress.add_task(PIPELINE_STEPS[0], total=total_steps)

            def on_step(name: str, index: int, total: int) -> None:
                """core geri çağırması: Rich ilerlemesini günceller."""
                progress.update(task, completed=index - 1, description=name)

            result = run_pipeline(
                topic=topic, style=style, subtitle_mode=subtitle_mode, on_step=on_step
            )
            progress.update(task, completed=total_steps, description="Tamamlandı")

        console.print(
            Panel.fit(
                f"[bold green]✔ Video üretildi![/bold green]\n"
                f"Dosya: [cyan]{result.output_path}[/cyan]\n"
                f"Süre: {result.total_duration:.1f} sn | "
                f"Boyut: {config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT}",
                title="Shorts Forge",
                border_style="green",
            )
        )
    except KeyboardInterrupt:
        log_error("Kullanıcı tarafından iptal edildi.")
        raise typer.Exit(code=130)
    except Exception as exc:  # noqa: BLE001 - CLI en dış yakalayıcı, temiz raporlama
        log_error(f"Pipeline başarısız oldu: {exc}")
        raise typer.Exit(code=1)


@app.command()
def gui() -> None:
    """Masaüstü grafik arayüzünü (CustomTkinter) başlatır."""
    try:
        from gui import launch_gui
    except ImportError as exc:  # customtkinter kurulu değilse anlaşılır hata ver
        log_error(f"GUI başlatılamadı (customtkinter eksik olabilir): {exc}")
        log_info("Kurulum için: pip install customtkinter")
        raise typer.Exit(code=1)
    launch_gui()


if __name__ == "__main__":
    app()
