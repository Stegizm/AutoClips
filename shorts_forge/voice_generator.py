"""Seslendirme (TTS) üretici modül.

edge-tts kütüphanesi ile her sahnenin metnini ayrı bir MP3 dosyasına dönüştürür
ve sahne-ses senkronizasyonu için gerçek süreleri (saniye) ölçer.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import edge_tts
import config
from shorts_forge.utils import ensure_dir, log_info


@dataclass
class VoiceClip:
    """Üretilmiş tek bir seslendirme kliplerinin bilgisi.

    Attributes:
        scene_index: İlgili sahnenin indeksi.
        audio_path: Üretilen MP3 dosyasının yolu.
        duration: Sesin gerçek süresi (saniye).
    """

    scene_index: int
    audio_path: Path
    duration: float


def _get_mp3_duration(path: Path) -> float:
    """Bir MP3 dosyasının süresini mutagen ile saniye cinsinden okur.

    Args:
        path: MP3 dosyasının yolu.

    Returns:
        float: Süre (saniye). Okunamazsa 0.0 döner.
    """
    try:
        # mutagen hafif bir bağımlılıktır; MP3 header'ından süreyi hızlıca verir
        from mutagen.mp3 import MP3

        audio = MP3(str(path))
        return float(audio.info.length)
    except Exception:  # noqa: BLE001 - süre okunamazsa 0 döndür, pipeline devam etsin
        return 0.0


async def _synthesize(text: str, output_path: Path) -> None:
    """Verilen metni edge-tts ile MP3 dosyasına yazan async yardımcı.

    Args:
        text: Seslendirilecek metin.
        output_path: Çıktı MP3 dosyasının yolu.
    """
    communicate = edge_tts.Communicate(
        text=text, voice=config.TTS_VOICE, rate=config.TTS_RATE, pitch=config.TTS_PITCH
    )
    await communicate.save(str(output_path))


def generate_voices(narrations: list[str], temp_dir: Path) -> list[VoiceClip]:
    """Her sahne metni için ayrı bir MP3 ses dosyası üretir.

    Sahne-ses senkronizasyonu kritik olduğundan her sahne AYRI dosya olarak
    üretilir ve gerçek süresi ölçülür.

    Args:
        narrations: Sahnelerin seslendirme metinleri listesi.
        temp_dir: Geçici dosyaların tutulacağı dizin.

    Returns:
        list[VoiceClip]: Her sahne için üretilen ses klipleri.

    Raises:
        RuntimeError: TTS üretimi sırasında geri dönüşü olmayan hata olursa.
    """
    ensure_dir(temp_dir)
    clips: list[VoiceClip] = []

    log_info(f"Seslendirmeler üretiliyor ({len(narrations)} sahne, ses: {config.TTS_VOICE})...")

    for index, text in enumerate(narrations):
        clip_path: Path = temp_dir / f"voice_scene_{index:02d}.mp3"
        try:
            # edge-tts async API -> asyncio.run ile sinkron sarmala
            asyncio.run(_synthesize(text, clip_path))
        except Exception as exc:  # noqa: BLE001 - tek sahne hatası tümünü bozmasın
            raise RuntimeError(f"Sahne {index} seslendirilemedi: {exc}") from exc

        if not clip_path.exists() or clip_path.stat().st_size == 0:
            raise RuntimeError(f"Sahne {index} için boş ses dosyası oluştu.")

        duration: float = _get_mp3_duration(clip_path)
        clips.append(VoiceClip(scene_index=index, audio_path=clip_path, duration=duration))
        log_info(f"  • Sahne {index}: {duration:.2f} sn")

    total: float = sum(c.duration for c in clips)
    log_info(f"Tüm sesler hazır. Toplam süre: {total:.2f} sn")
    return clips
