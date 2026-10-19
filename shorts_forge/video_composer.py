"""Video montaj (kompozisyon) modülü.

MoviePy ile indirilen stok klipleri sahne sürelerine göre kırpar, sesleri
sırayla birleştirir, altyazıları ekler ve 9:16 dikey formatta output/'a yazar.
İşlem bitince temp/ klasörünü temizler.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)

import config
from shorts_forge.media_fetcher import MediaClip
from shorts_forge.script_generator import Scene
from shorts_forge.subtitle_generator import SubtitleCue
from shorts_forge.voice_generator import VoiceClip
from shorts_forge.utils import clean_dir, ensure_dir, log_info, log_warning, make_slug


@dataclass
class CompositionResult:
    """Montaj sonucunun özeti.

    Attributes:
        output_path: Üretilen videonun yolu.
        total_duration: Toplam video süresi (saniye).
    """

    output_path: Path
    total_duration: float


def _find_font() -> str:
    """Sistemde bulunan uygun bir TTF font dosyasının yolunu döner.

    MoviePy v1 ImageMagick yerine doğrudan PIL/TTF kullanır; Türkçe karakterler
    için DejaVu Sans tercih edilir. Bulunamazsa boş string döner (ImageMagick
    varsayılan fontunu kullanır).

    Returns:
        str: Font dosya yolu ya da bulunamazsa boş string.
    """
    candidates: list[Path] = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/liberation/LiberationSans-Bold.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return ""


def _build_scene_clip(
    media: MediaClip | None,
    duration: float,
) -> ColorClip | VideoFileClip:
    """Tek bir sahne için arka plan video klip üretir.

    Stok klip varsa ortadan kesip (crop) dikey çözünürlüğe ölçekler; yoksa
    düz siyah bir arka plan (fallback) kullanır.

    Args:
        media: İndirilmiş stok klip (None olabilir).
        duration: Sahnenin hedef süresi (saniye).

    Returns:
        ColorClip | VideoFileClip: Sahneye ait görsel klip.
    """
    if media is None or not media.video_path.exists():
        # Fallback: stok bulunamadıysa siyah arka plan
        return ColorClip(
            size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT),
            color=(0, 0, 0),
            duration=duration,
        )

    try:
        clip: VideoFileClip = VideoFileClip(str(media.video_path))
        # Sesli stok videonun kendi sesi istenmez (TTS kullanılacak)
        clip = clip.without_audio()

        # Kırpma: klip süresi yetmiyorsa baştan sar gibi davran (loop değil, kes)
        available: float = min(duration, clip.duration) if clip.duration else duration
        clip = clip.subclip(0, available)

        # Dikey format için: en-boy oranını 9:16'ya getir (ortadan crop)
        target_ratio: float = config.VIDEO_WIDTH / config.VIDEO_HEIGHT
        w, h = clip.size
        current_ratio: float = w / h
        if current_ratio > target_ratio:
            # Çok geniş -> yataydan kırp
            new_w: int = int(h * target_ratio)
            x_center: int = w // 2
            clip = clip.crop(x_center - new_w // 2, 0, width=new_w, height=h)
        elif current_ratio < target_ratio:
            # Çok uzun/dar -> dikeyden kırp
            new_h: int = int(w / target_ratio)
            y_center: int = h // 2
            clip = clip.crop(0, y_center - new_h // 2, width=w, height=new_h)

        # Hedef çözünürlüğe ölçekle
        clip = clip.resize((config.VIDEO_WIDTH, config.VIDEO_HEIGHT))

        # Stok klip sahne süresinden kısaysa, süreyi tamamla (donmuş kare yerine loop)
        if clip.duration < duration:
            remaining: float = duration - clip.duration
            repeats: int = int(remaining // max(clip.duration, 0.1)) + 1
            loops: list[VideoFileClip] = [clip] + [clip.copy() for _ in range(repeats)]
            clip = concatenate_videoclips(loops, method="chain")
            clip = clip.subclip(0, duration)

        return clip
    except Exception as exc:  # noqa: BLE001 - tek klip hatası tüm montajı bozmasın
        log_warning(f"Sahne klibi işlenemedi ({exc}), siyah arka plana düşülüyor.")
        return ColorClip(
            size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT),
            color=(0, 0, 0),
            duration=duration,
        )


def _make_text_clip(cue: SubtitleCue, font_path: str) -> TextClip:
    """Bir altyazı diliminden konturlu, ortalanmış TextClip üretir.

    Args:
        cue: Altyazı dilimi.
        font_path: Kullanılacak TTF font yolu (boşsa varsayılan).

    Returns:
        TextClip: Zamanlanmış, konumlandırılmış metin klibi.
    """
    kwargs: dict[str, object] = {
        "txt": cue.text,
        "fontsize": config.SUBTITLE_FONT_SIZE,
        "color": config.SUBTITLE_FONT_COLOR,
        "stroke_color": config.SUBTITLE_OUTLINE_COLOR,
        "stroke_width": config.SUBTITLE_STROKE_WIDTH,
        "method": "caption",
        "size": (int(config.VIDEO_WIDTH * 0.9), None),
    }
    if font_path:
        kwargs["font"] = font_path

    txt: TextClip = TextClip(**kwargs)  # type: ignore[arg-type]
    txt = txt.set_start(cue.start).set_duration(max(0.05, cue.end - cue.start))
    # Yatayda orta, dikeyde ekranın ortası (ratio ile)
    txt = txt.set_position(("center", int(config.VIDEO_HEIGHT * config.SUBTITLE_Y_POSITION_RATIO)))
    return txt


def compose_video(
    scenes: list[Scene],
    voices: list[VoiceClip],
    media: list[MediaClip | None],
    subtitles: list[SubtitleCue],
    topic: str,
    output_dir: Path,
    temp_dir: Path,
) -> CompositionResult:
    """Tüm parçaları birleştirip final Shorts videosunu üretir.

    Adımlar: sahne kliplerini kur -> sesleri birleştir -> altyazıları overlay yap
    -> 9:16 render -> output/'a kaydet -> temp/'i temizle.

    Args:
        scenes: Senaryo sahneleri.
        voices: Sahne başına üretilmiş ses klipleri.
        media: Sahne başına indirilmiş stok klipler (None olabilir).
        subtitles: Zaman damgalı altyazı dilimleri.
        topic: Çıktı dosya adında kullanılacak konu metni.
        output_dir: Final videonun yazılacağı dizin.
        temp_dir: Geçici dosyaların temizleneceği dizin.

    Returns:
        CompositionResult: Çıktı yolu ve toplam süre.

    Raises:
        RuntimeError: Montaj/render sırasında geri dönüşü olmayan hata olursa.
    """
    ensure_dir(output_dir)
    font_path: str = _find_font()

    # 1) Her sahnenin süresini gerçek ses süresine göre belirle
    durations: list[float] = []
    for index, scene in enumerate(scenes):
        voice_dur: float = voices[index].duration if index < len(voices) else 0.0
        # Ses süresi 0 ise LLM tahminini kullan; nefes payı ekle
        scene_dur: float = (voice_dur if voice_dur > 0 else scene.duration_estimate)
        durations.append(scene_dur + config.SCENE_PADDING_SECONDS)

    # 2) Sahne görsellerini kur
    log_info("Sahne görselleri hazırlanıyor...")
    scene_clips: list[VideoFileClip] = []
    for index, dur in enumerate(durations):
        media_item: MediaClip | None = media[index] if index < len(media) else None
        scene_clips.append(_build_scene_clip(media_item, dur))

    video_track: VideoFileClip = concatenate_videoclips(scene_clips, method="chain")

    # 3) Her sahnenin sesini kendi başlangıç ofsetine yerleştir ve birleştir
    log_info("Sesler birleştiriliyor...")
    placed_audio: list[AudioFileClip] = []
    offset: float = 0.0
    for index, dur in enumerate(durations):
        if index < len(voices):
            try:
                audio: AudioFileClip = AudioFileClip(str(voices[index].audio_path))
                # Ses sahne süresinden uzunsa kırp (padding kısmı sessiz kalsın)
                if audio.duration > dur:
                    audio = audio.subclip(0, dur)
                # Bu sesi sahnenin video içindeki başlangıcına konumlandır
                placed_audio.append(audio.set_start(offset))
            except Exception as exc:  # noqa: BLE001 - tek ses hatası montajı bozmasın
                log_warning(f"Sahne {index} sesi yüklenemedi: {exc}")
        offset += dur

    # Tüm sahne süreleri toplamı kadar bir arka plan oluşturup sesleri üzerine koy
    total_duration: float = sum(durations)
    combined_audio = CompositeAudioClip(placed_audio).set_duration(total_duration)

    video_with_audio: VideoFileClip = video_track.with_audio(combined_audio)

    # 4) Altyazıları overlay olarak ekle
    log_info("Altyazılar ekleniyor...")
    text_clips: list[TextClip] = [_make_text_clip(cue, font_path) for cue in subtitles]
    final: CompositeVideoClip = CompositeVideoClip(
        [video_with_audio] + text_clips,
        size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT),
    )

    # 5) Dosya adı ve render
    date_str: str = datetime.now().strftime(config.OUTPUT_DATE_FORMAT)
    slug: str = make_slug(topic) or "short"
    out_name: str = config.OUTPUT_FILENAME_TEMPLATE.format(date=date_str, slug=slug)
    out_path: Path = output_dir / out_name

    log_info(f"Video render ediliyor -> {out_path.name}")
    try:
        final.write_videofile(
            str(out_path),
            fps=config.VIDEO_FPS,
            codec=config.VIDEO_CODEC,
            audio_codec=config.AUDIO_CODEC,
            bitrate=config.BITRATE,
            preset="medium",
            threads=2,
        )
    finally:
        # Kaynak clip'leri kapat (dosya tutucuları bırak)
        for c in scene_clips:
            c.close()
        for a in placed_audio:
            a.close()
        video_track.close()
        final.close()

    result_duration: float = float(final.duration) if final.duration else total_duration

    # 6) Temp klasörünü temizle
    log_info("Geçici dosyalar temizleniyor...")
    clean_dir(temp_dir)

    return CompositionResult(output_path=out_path, total_duration=result_duration)
