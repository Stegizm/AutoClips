"""Shorts Forge çekirdek üretim hattı (pipeline).

Bu modül, arayüzden (CLI veya GUI) bağımsız olarak tüm üretim adımlarını
sırayla çalıştırır. Arayüz katmanları yalnızca bu modülü çağırır; böylece
iş mantığı tek yerde toplanır (Single Responsibility).

Kullanım:
    from shorts_forge.core import run_pipeline
    result = run_pipeline(topic="...", style="eğitici", subtitle_mode="word",
                          on_step=lambda name, idx, total: print(name))
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import config
from shorts_forge.media_fetcher import MediaClip, fetch_media
from shorts_forge.script_generator import Script, generate_script
from shorts_forge.subtitle_generator import SubtitleCue, generate_subtitles
from shorts_forge.utils import ensure_dir
from shorts_forge.video_composer import CompositionResult, compose_video
from shorts_forge.voice_generator import VoiceClip, generate_voices

# Adım geri çağırma tipi: (adım_adı, adım_indeksi, toplam_adim)
StepCallback = Callable[[str, int, int], None]

# Pipeline adım isimleri (GUI ilerleme etiketlerinde de kullanılır)
PIPELINE_STEPS: tuple[str, ...] = (
    "Senaryo üretiliyor (Ollama)",
    "Seslendirme üretiliyor (edge-tts)",
    "Stok videolar indiriliyor (Pexels)",
    "Altyazılar hazırlanıyor",
    "Video monte ediliyor (MoviePy)",
)


def validate_settings() -> list[str]:
    """Ortam ayarlarını ön kontrolünden geçirir.

    Eksik/bozuk yapılandırmaları üretimin başında yakalamak için kullanılır.

    Returns:
        Hata mesajlarının listesi; liste boşsa ayarlar geçerlidir.
    """
    errors: list[str] = []

    if not config.PEXELS_API_KEY or config.PEXELS_API_KEY == "your_pexels_api_key_here":
        errors.append("PEXELS_API_KEY tanımlı değil. Ayarlar > Ortam Değişkenleri > API Keys.")

    if not config.OLLAMA_BASE_URL.startswith(("http://", "https://")):
        errors.append(f"OLLAMA_BASE_URL geçersiz: '{config.OLLAMA_BASE_URL}'.")

    return errors


def run_pipeline(
    topic: str,
    style: str = "eğitici",
    subtitle_mode: str = "word",
    on_step: Optional[StepCallback] = None,
    output_dir: Optional[Path] = None,
    temp_dir: Optional[Path] = None,
) -> CompositionResult:
    """Tüm Shorts üretim hattını sırayla çalıştırır.

    Args:
        topic: Videonun konusu / kavramı.
        style: Anlatım tarzı (örn: 'eğitici', 'komik').
        subtitle_mode: Altyazı modu ('word' veya 'sentence').
        on_step: Her adımın başında çağrılan geri çağırma fonksiyonu
            (ilerleme çubuğu / log için). İsteğe bağlıdır.
        output_dir: Çıktı klasörü; verilmezse ``config.OUTPUT_DIR`` kullanılır.
        temp_dir: Geçici klasör; verilmezse ``config.TEMP_DIR`` kullanılır.

    Returns:
       compose_video çıktısını temsil eden ``CompositionResult`` nesnesi.

    Raises:
        ValueError: Geçersiz konu veya altyazı modu verilirse.
        Exception: Pipeline adımlarından biri başarısız olursa (olduğu gibi yansıtılır).
    """
    # --- Girdi doğrulama -------------------------------------------------
    clean_topic: str = topic.strip()
    if not clean_topic:
        raise ValueError("Konu (topic) boş olamaz.")
    if subtitle_mode not in ("word", "sentence"):
        raise ValueError(f"Geçersiz altyazı modu: '{subtitle_mode}'. 'word' veya 'sentence' olmalı.")

    out_dir: Path = output_dir or config.OUTPUT_DIR
    tmp_dir: Path = temp_dir or config.TEMP_DIR
    ensure_dir(out_dir)
    ensure_dir(tmp_dir)

    def _notify(index: int) -> None:
        """İlgili adım için geri çağırmayı güvenli biçimde tetikler."""
        if on_step is not None:
            on_step(PIPELINE_STEPS[index], index + 1, len(PIPELINE_STEPS))

    # --- 1. Senaryo ------------------------------------------------------
    _notify(0)
    script: Script = generate_script(topic=clean_topic, style=style)

    # --- 2. Seslendirme ----------------------------------------------------
    _notify(1)
    narrations: list[str] = [scene.narration for scene in script.scenes]
    voices: list[VoiceClip] = generate_voices(narrations, tmp_dir)

    # --- 3. Stok videolar --------------------------------------------------
    _notify(2)
    visual_prompts: list[str] = [scene.visual_prompt for scene in script.scenes]
    media: list[Optional[MediaClip]] = fetch_media(visual_prompts, tmp_dir)

    # --- 4. Altyazılar -----------------------------------------------------
    _notify(3)
    durations: list[float] = [voice.duration for voice in voices]
    subtitles: list[SubtitleCue] = generate_subtitles(
        narrations=narrations, durations=durations, mode=subtitle_mode
    )

    # --- 5. Montaj ---------------------------------------------------------
    _notify(4)
    result: CompositionResult = compose_video(
        scenes=script.scenes,
        voices=voices,
        media=media,
        subtitles=subtitles,
        topic=clean_topic,
        output_dir=out_dir,
        temp_dir=tmp_dir,
    )
    return result
