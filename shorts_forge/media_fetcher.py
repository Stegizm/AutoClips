"""Stok video çekme/indirme modülü.

Pexels API'sinden her sahnenin İngilizce anahtar kelimesiyle DİKEY (portrait)
stok videolar arar ve en uygun olanı temp/ klasörüne indirir.
Rate limit (saatlik 200 istek) için istekler arasında bekleme uygular.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

import config
from shorts_forge.utils import ensure_dir, log_info, log_warning


@dataclass
class MediaClip:
    """İndirilen tek bir stok video kliplerinin bilgisi.

    Attributes:
        scene_index: İlgili sahne indeksi.
        video_path: İndirilen video dosyasının yolu.
        duration: İndirilen orijinal videonun süresi (saniye).
    """

    scene_index: int
    video_path: Path
    duration: float


def _search_videos(query: str) -> list[dict[str, Any]]:
    """Pexels video arama API'sine tek istek atar ve sonuç listesini döner.

    Args:
        query: İngilizce arama anahtar kelimesi.

    Returns:
        list[dict]: Video sonuç sözlükleri (hata/boşluk durumunda boş liste).

    Raises:
        RuntimeError: API anahtarı eksikse veya HTTP 401/403 dönerse.
    """
    if not config.PEXELS_API_KEY:
        raise RuntimeError(
            "PEXELS_API_KEY tanımlı değil. .env dosyanızı kontrol edin."
        )

    headers: dict[str, str] = {"Authorization": config.PEXELS_API_KEY}
    params: dict[str, Any] = {
        "query": query,
        "orientation": config.PEXELS_ORIENTATION,  # ÖNEMLİ: sadece dikey videolar
        "per_page": config.PEXELS_PER_PAGE,
    }

    try:
        response: requests.Response = requests.get(
            config.PEXELS_SEARCH_URL,
            headers=headers,
            params=params,
            timeout=config.PEXELS_DOWNLOAD_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        log_warning(f"Pexels arama isteği başarısız ({query}): {exc}")
        return []

    if response.status_code in (401, 403):
        raise RuntimeError("Pexels API anahtarı geçersiz veya yetkisiz (401/403).")
    if response.status_code == 429:
        log_warning("Pexels rate limit doldu (429), biraz bekleyip boş dönülüyor.")
        return []

    if not response.ok:
        log_warning(f"Pexels arama hatası ({query}): HTTP {response.status_code}")
        return []

    data: dict[str, Any] = response.json()
    return data.get("videos", [])


def _pick_best_video(videos: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Sonuçlar arasından süre aralığına uyan ilk (en alakalı) videoyu seçer.

    Pexels sonuçları alaka sırasına göre gelir; biz makul süre aralığındaki
    ilk dikey videoyu tercih ederiz.

    Args:
        videos: Ham video sonuç listesi.

    Returns:
        dict | None: Seçilen video ya da uygun bulunamadıysa None.
    """
    for video in videos:
        duration: float = float(video.get("duration", 0))
        if config.PEXELS_MIN_DURATION_SECONDS <= duration <= config.PEXELS_MAX_DURATION_SECONDS:
            return video
    # Aralığa uyan yoksa ilk sonucu kullan (fallback)
    return videos[0] if videos else None


def _get_download_url(video: dict[str, Any]) -> str | None:
    """Video kaydından en yüksek çözünürlüklü mp4 linkini bulur.

    Mümkünse dikey formata en yakın (yüksekliği fazla) olanı tercih eder.

    Args:
        video: Seçilmiş video sözlüğü.

    Returns:
        str | None: İndirme URL'si ya da bulunamazsa None.
    """
    renditions: list[dict[str, Any]] = video.get("video_files", [])
    mp4s: list[dict[str, Any]] = [
        r for r in renditions if r.get("file_type", "").startswith("video/mp4")
    ]
    if not mp4s:
        # Bazı kayıtlarda file_type olmayabilir; link alanına göre filtrele
        mp4s = [r for r in renditions if str(r.get("link", "")).lower().endswith(".mp4")]
    if not mp4s:
        return None

    # Yüksekliğe göre sırala; çok devasa (>4K) olanları boyut için ele
    mp4s.sort(key=lambda r: int(r.get("height", 0)), reverse=True)
    suitable: list[dict[str, Any]] = [
        r for r in mp4s if int(r.get("height", 0)) <= config.VIDEO_HEIGHT * 2
    ]
    chosen: dict[str, Any] = suitable[0] if suitable else mp4s[-1]
    return chosen.get("link")


def _download_file(url: str, dest_path: Path) -> bool:
    """Bir URL'deki dosyayı akış (stream) halinde diske yazar.

    Args:
        url: İndirme adresi.
        dest_path: Hedef dosya yolu.

    Returns:
        bool: Başarılı indirmede True, hatada False.
    """
    try:
        with requests.get(url, stream=True, timeout=config.PEXELS_DOWNLOAD_TIMEOUT_SECONDS) as resp:
            resp.raise_for_status()
            with open(dest_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
        return dest_path.exists() and dest_path.stat().st_size > 0
    except requests.RequestException as exc:
        log_warning(f"İndirme başarısız ({url[:60]}...): {exc}")
        return False


def fetch_media(visual_prompts: list[str], temp_dir: Path) -> list[MediaClip | None]:
    """Her sahnenin görsel anahtar kelimesi için dikey stok video indirir.

    Rate limit'i aşmamak için her arama arasında kısa bir bekleme uygular.
    Bir sahne için video bulunamazsa o index'e None döner (montaj fallback kullanır).

    Args:
        visual_prompts: Sahnelerin İngilizce görsel arama kelimeleri listesi.
        temp_dir: Geçici indirme dizini.

    Returns:
        list[MediaClip | None]: Sahne sırasına göre indirilen klipler (None olabilir).

    Raises:
        RuntimeError: Pexels API anahtarı eksik/geçersizse.
    """
    ensure_dir(temp_dir)
    results: list[MediaClip | None] = []

    log_info(f"Dikey stok videolar aranıyor ({len(visual_prompts)} sahne, Pexels)...")

    for index, prompt in enumerate(visual_prompts):
        videos: list[dict[str, Any]] = _search_videos(prompt)
        clip: MediaClip | None = None

        if videos:
            best: dict[str, Any] | None = _pick_best_video(videos)
            url: str | None = _get_download_url(best) if best else None
            if url:
                dest: Path = temp_dir / f"clip_scene_{index:02d}.mp4"
                if _download_file(url, dest):
                    duration: float = float(best.get("duration", 0)) if best else 0.0
                    clip = MediaClip(scene_index=index, video_path=dest, duration=duration)
                    log_info(f"  • Sahne {index}: '{prompt}' indirildi ({duration:.1f} sn)")
                else:
                    log_warning(f"  • Sahne {index}: indirme başarısız, fallback kullanılacak.")
            else:
                log_warning(f"  • Sahne {index}: indirilebilir mp4 bulunamadı.")
        else:
            log_warning(f"  • Sahne {index}: '{prompt}' için dikey video bulunamadı.")

        results.append(clip)

        # Rate limit (saatlik 200 istek) için istekler arasında bekle
        time.sleep(config.PEXELS_REQUEST_DELAY_SECONDS)

    downloaded: int = sum(1 for c in results if c is not None)
    log_info(f"Stok video indirme tamamlandı: {downloaded}/{len(visual_prompts)} sahne.")
    return results
