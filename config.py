"""Merkezi ayar dosyası.

Tüm sabitler, ortam değişkenleri ve yol tanımları burada toplanır.
Diğer modüller sihirli sayı (magic number) yerine bu dosyadaki sabitleri kullanır.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# .env dosyasını (varsa) proje kökünden yükle; ayrı çağrı aşağıda yapılır

# ---------------------------------------------------------------------------
# Proje yolları (pathlib ile -> Windows/Linux uyumlu)
# ---------------------------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).resolve().parent

# PyInstaller ile paketlenmiş (frozen) çalıştırmada uygulama dosyaları geçici
# bir klasörde olur; bu yüzden kullanıcı verisi için evin altında bir klasör kullanılır.
if getattr(sys, "frozen", False):
    DATA_ROOT: Path = Path.home() / ".shorts-forge"
else:
    DATA_ROOT = PROJECT_ROOT

OUTPUT_DIR: Path = DATA_ROOT / "output"
TEMP_DIR: Path = DATA_ROOT / "temp"
ENV_FILE: Path = DATA_ROOT / ".env"
PROMPTS_DIR: Path = PROJECT_ROOT / "shorts_forge" / "prompts"
SYSTEM_PROMPT_FILE: Path = PROMPTS_DIR / "system_prompt.txt"

# ---------------------------------------------------------------------------
# Ortam değişkenleri (.env üzerinden)
# ---------------------------------------------------------------------------
# 1) Geliştirme: proje kökündeki .env  2) Paketlenmiş: ~/.shorts-forge/.env
load_dotenv(PROJECT_ROOT / ".env")
if ENV_FILE != PROJECT_ROOT / ".env":
    load_dotenv(ENV_FILE, override=False)

# Okunan ortam değişkenleri (modül seviyesinde sabitler)
PEXELS_API_KEY: str = os.getenv("PEXELS_API_KEY", "")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
TTS_VOICE: str = os.getenv("TTS_VOICE", "tr-TR-EmelNeural")

# ---------------------------------------------------------------------------
# Çözünürlük ayarı (OUTPUT_RESOLUTION="1080x1920" biçiminde okunur)
# ---------------------------------------------------------------------------
_resolution_raw: str = os.getenv("OUTPUT_RESOLUTION", "1080x1920")
try:
    _w_str, _h_str = _resolution_raw.lower().split("x", 1)
    VIDEO_WIDTH: int = int(_w_str)
    VIDEO_HEIGHT: int = int(_h_str)
except ValueError:
    # Hatalı format verilirse dikey standart çözünürlüğe düş
    VIDEO_WIDTH = 1080
    VIDEO_HEIGHT = 1920

# ---------------------------------------------------------------------------
# Ollama sabitleri
# ---------------------------------------------------------------------------
OLLAMA_CHAT_ENDPOINT: str = "/api/chat"
OLLAMA_TIMEOUT_SECONDS: int = 300          # Yerel LLM üretim süresi uzun olabilir
OLLAMA_TEMPERATURE: float = 0.8            # Yaratıcılık seviyesi
OLLAMA_MAX_RETRIES: int = 2                # JSON bozuksa yeniden sorma sayısı

# ---------------------------------------------------------------------------
# Pexels API sabitleri
# ---------------------------------------------------------------------------
PEXELS_SEARCH_URL: str = "https://api.pexels.com/videos/search"
PEXELS_PER_PAGE: int = 15                  # Arama başına dönen sonuç sayısı
PEXELS_ORIENTATION: str = "portrait"       # Sadece dikey videolar
PEXELS_REQUEST_DELAY_SECONDS: float = 1.0  # Rate limit (saatlik 200 istek) için bekleme
PEXELS_DOWNLOAD_TIMEOUT_SECONDS: int = 120
PEXELS_MIN_DURATION_SECONDS: int = 4       # Çok kısa klipleri ele
PEXELS_MAX_DURATION_SECONDS: int = 60      # İndirme boyutunu sınırla

# ---------------------------------------------------------------------------
# edge-tts sabitleri
# ---------------------------------------------------------------------------
TTS_RATE: str = "+8%"                      # Konuşma hızı (Shorts için hafif hızlı)
TTS_PITCH: str = "+0Hz"                    # Perde değişikliği yok

# ---------------------------------------------------------------------------
# Video montaj (MoviePy) sabitleri
# ---------------------------------------------------------------------------
VIDEO_FPS: int = 30                        # Çıkış kare hızı
VIDEO_CODEC: str = "libx264"               # Video kodlayıcı
AUDIO_CODEC: str = "aac"                   # Ses kodlayıcı
BITRATE: str = "6000k"                     # Shorts/Reels için önerilen bitrate
SCENE_PADDING_SECONDS: float = 0.15        # Sahneler arası küçük nefes payı

# ---------------------------------------------------------------------------
# Altyazı sabitleri
# ---------------------------------------------------------------------------
SUBTITLE_FONT_SIZE: int = 72               # Piksel cinsinden yazı tipi boyutu
SUBTITLE_FONT_COLOR: str = "yellow"        # CapCut/Hormozi tarzı sarı vurgu
SUBTITLE_OUTLINE_COLOR: str = "black"      # Okunurluk için siyah kontur
SUBTITLE_STROKE_WIDTH: int = 4             # Kontur kalınlığı
SUBTITLE_WORDS_PER_CHUNK: int = 3          # Kelime bazlı altyazıda chunk büyüklüğü
SUBTITLE_Y_POSITION_RATIO: float = 0.5     # Dikey konum (ekranın ortası)

# ---------------------------------------------------------------------------
# Senaryo (script) sabitleri
# ---------------------------------------------------------------------------
MAX_SCENES: int = 6                        # Azami sahne sayısı (Shorts ~60 sn)
MIN_SCENES: int = 3                        # Asgari sahne sayısı

# ---------------------------------------------------------------------------
# Dosya adı şablonları
# ---------------------------------------------------------------------------
OUTPUT_FILENAME_TEMPLATE: str = "shorts_{date}_{slug}.mp4"
OUTPUT_DATE_FORMAT: str = "%Y%m%d_%H%M%S"
