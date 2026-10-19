"""Altyazı üretici modül.

Her sahnenin seslendirme süresi ve metninden, MoviePy TextClip için gereken
zaman damgalı altyazı dilimlerini üretir. Kelime bazlı (CapCut/Hormozi tarzı)
veya cümle bazlı iki mod sunar. Whisper gerekmeden, bilinen TTS süreleri ile
hızlandırılmış (karaoke) zamanlama kullanır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import config


@dataclass
class SubtitleCue:
    """Tek bir altyazı dilimi (caption cue).

    Attributes:
        start: Başlangıç zamanı (saniye, video geneline göre mutlak).
        end: Bitiş zamanı (saniye).
        text: Ekranda gösterilecek kelime/kelime grubu.
    """

    start: float
    end: float
    text: str


def _tokenize(text: str) -> list[str]:
    """Metni kelimelere ayırır; noktalama kelimelere bitişik kalır.

    Args:
        text: Altyazı metni.

    Returns:
        list[str]: Kelime belirteçleri.
    """
    return [w for w in re.split(r"\s+", text.strip()) if w]


def build_scene_cues(
    narration: str,
    scene_start: float,
    scene_duration: float,
    words_per_chunk: int = config.SUBTITLE_WORDS_PER_CHUNK,
) -> list[SubtitleCue]:
    """Tek bir sahne için zaman damgalı altyazı dilimleri üretir.

    Ses süresi sahne süresine eşit kabul edilir; kelimeler bu süreye eşit
    dağıtılır (edge-tts WordBoundary verisi olmadığı için yaklaşık karaoke).

    Args:
        narration: Sahnenin seslendirme metni.
        scene_start: Sahnemin video içindeki başlangıç zamanı (saniye).
        scene_duration: Sahnenin toplam süresi (saniye).
        words_per_chunk: Her dilimde kaç kelime olsun (1 => kelime kelime).

    Returns:
        list[SubtitleCue]: Sahneye ait altyazı dilimleri.
    """
    tokens: list[str] = _tokenize(narration)
    if not tokens or scene_duration <= 0:
        return []

    # Chunk büyüklüğünü en az 1 yap
    chunk_size: int = max(1, words_per_chunk)
    chunks: list[list[str]] = [
        tokens[i : i + chunk_size] for i in range(0, len(tokens), chunk_size)
    ]

    per_chunk_time: float = scene_duration / len(chunks)
    cues: list[SubtitleCue] = []
    for idx, chunk in enumerate(chunks):
        start: float = scene_start + idx * per_chunk_time
        end: float = scene_start + (idx + 1) * per_chunk_time
        cues.append(SubtitleCue(start=start, end=end, text=" ".join(chunk)))
    return cues


def generate_subtitles(
    narrations: list[str],
    durations: list[float],
    mode: str = "word",
) -> list[SubtitleCue]:
    """Tüm video için zaman damgalı altyazı listesini üretir.

    Args:
        narrations: Sahnelerin seslendirme metinleri.
        durations: Sahnelerin gerçek ses süreleri (saniye), sırayla.
        mode: 'word' (kelime kelime) veya 'sentence' (cümle bazlı).

    Returns:
        list[SubtitleCue]: Video başına göre mutlak zamanlı tüm altyazılar.
    """
    all_cues: list[SubtitleCue] = []
    cursor: float = 0.0  # Video içindeki kayan zaman işareti

    words_per_chunk: int = 1 if mode == "word" else 999  # sentence => tek chunk
    for narration, duration in zip(narrations, durations):
        scene_cues: list[SubtitleCue] = build_scene_cues(
            narration=narration,
            scene_start=cursor,
            scene_duration=duration,
            words_per_chunk=words_per_chunk,
        )
        all_cues.extend(scene_cues)
        cursor += duration

    return all_cues
