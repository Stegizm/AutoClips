<div align="center">

# 🎬 Shorts Forge

**Yerel-first, modüler bir otomatik YouTube Shorts / Instagram Reels üretim hattı (pipeline).**

Verdiğiniz bir *konu/kavram* prompt'undan yola çıkarak:
🧠 yerel LLM ile senaryo yazar → 🗣️ doğal Türkçe seslendirme üretir →
📥 Pexels'ten **dikey stok videolar** indirir → 💬 CapCut/Hormozi tarzı altyazılar ekler →
🎞️ MoviePy ile **9:16 (1080×1920)** video render eder.

*GPU/VRAM gerekmez. Bulut aboneliği gerekmez. API anahtarı olarak yalnızca ücretsiz bir Pexels anahtarı yeterlidir.*

`Python 3.10+` · `Ollama` · `edge-tts` · `Pexels API` · `MoviePy` · `Typer` + `Rich`

</div>

---

## 📑 İçindekiler

1. [Proje Açıklaması](#-proje-açıklaması)
2. [Nasıl Çalışır? (Pipeline)](#-nasıl-çalışır-pipeline)
3. [Özellikler](#-özellikler)
4. [Proje Yapısı](#-proje-yapısı)
5. [Gereksinimler](#-gereksinimler)
6. [Kurulum Adımları](#-kurulum-adımları)
7. [Ollama Model Kurulumu](#-ollama-model-kurulumu)
8. [.env Dosyası Ayarı](#-env-dosyası-ayarı)
9. [Kullanım Örnekleri](#-kullanım-örnekleri)
10. [Yapılandırma (config.py)](#-yapılandırma-configpy)
11. [Modül Referansı](#-modül-referansı)
12. [Çıktı Nerede?](#-çıktı-nerede)
13. [Sorun Giderme](#-sorun-giderme)
14. [Bilinen Sınırlamalar](#-bilinen-sınırlamalar)
15. [Sıkça Sorulan Sorular](#-sıkça-sorulan-sorular)
16. [Katkıda Bulunma](#-katkıda-bulunma)
17. [Lisans](#-lisans)

---

## 🎯 Proje Açıklaması

Shorts Forge, tek bir komutla dikey format kısa videolar üreten **local-first** bir araçtır.
Temel tasarım kararları:

- **Stok video stratejisi:** Sıfırdan AI video üretimi (Stable Video Diffusion vb.) yüksek VRAM
  ve kalite sorunları nedeniyle **bilerek kullanılmaz.** Bunun yerine LLM'in senaryoda ürettiği
  İngilizce anahtar kelimelerle (**visual_prompt**) Pexels API'sinden `orientation=portrait`
  filtreli hazır dikey klipler indirilir. Sonuç: hızlı, deterministik, donanım dostu üretim.
- **Yerel LLM (Ollama):** Senaryo üretimi tamamen kendi makinenizde çalışır; metin veriniz
  hiçbir buluta gitmez (yalnızca Pexels araması ve edge-tts istekleri internet gerektirir).
- **Ücretsiz seslendirme:** Microsoft Edge'in sinirsel TTS motoru (`edge-tts`) ile
  `tr-TR-EmelNeural` / `tr-TR-AhmetNeural` sesleri — API anahtarı ve ücret yok.
- **Modüler mimari:** Her aşama bağımsız bir Python modülüdür; dilediğiniz modülü
  (ör. Whisper altyazı ya da Pixabay indirme) tek dosyayı değiştirerek güncelleyebilirsiniz.
- **Temiz kod:** PEP8 uyumlu, type hint'li, docstring'li, pathlib tabanlı, hatalara karşı
  dayanıklı; tüm sabitler `config.py` içinde merkezileştirilmiştir.

## 🔄 Nasıl Çalışır? (Pipeline)

```
┌────────────┐   ┌───────────────┐   ┌───────────────┐   ┌────────────────┐   ┌──────────────┐
│  --topic   │──▶│ 1. SENARYO    │──▶│ 2. SESLENDİRME│──▶│ 3. STOK VİDEO  │──▶│ 4. ALTYAZI   │──▶ output/*.mp4
│  "konu"    │   │ Ollama (LLM)  │   │   edge-tts    │   │  Pexels API    │   │ zamanlayıcı  │
└────────────┘   └───────────────┘   └───────────────┘   └────────────────┘   └──────────────┘
                   title + scenes      scene_0.mp3...     clip_0.mp4...        kelime/cümle
                   (JSON çıktısı)      + gerçek süreler   (portrait only)      zaman damgaları
                                                                         │
                                                             ┌───────────▼────────────┐
                                                             │  5. MONTAJ (MoviePy)   │
                                                             │  kırp + birleştir +    │
                                                             │  yaz → 1080x1920       │
                                                             └────────────────────────┘
```

1. **Senaryo:** Konu + tarz, `prompts/system_prompt.txt` kurallarıyla Ollama'ya gönderilir;
   viral hook içeren, sahne sahne JSON döner.
2. **Ses:** Her sahnenin `narration` metni ayrı MP3'e çevrilir ve **gerçek süresi ölçülür**
   (sahne–ses senkronizasyonunun temeli budur).
3. **Video:** Her sahnenin `visual_prompt`'u Pexels'te dikey videolar arasında aranır;
   en uygun klip `temp/` klasörüne indirilir (rate limit için istekler arası bekleme vardır).
4. **Altyazı:** Bilinen ses süreleri üzerinden kelime kelime (karaoke/CapCut tarzı) veya
   cümle bazlı zaman damgaları üretilir.
5. **Montaj:** Klipler sahne sürelerine göre kırpılır, sesler ofsetlerle birleştirilir,
   sarı/konturlu altyazılar ekranın ortasına basılır, 9:16 render edilir ve `temp/` temizlenir.

## ✨ Özellikler

- ✅ Tamamen **yerel çalışır** (Ollama + MoviePy); minimum bulut bağımlılığı
- ✅ **VRAM gerekmez** — harici GPU'suz laptoplarda bile çalışır
- ✅ **Ücretsiz seslendirme**: edge-tts ile doğal Türkçe kadın/erkek sesleri
- ✅ **Viral senaryo formatı**: hook'lu ilk sahne, kısa cümleler, genç kitle dili
- ✅ **Portre zorlaması**: Pexels'ten yalnızca dikey (9:16) klipler
- ✅ **Kelime kelime altyazı** (Hormozi/CapCut tarzı) veya cümle bazlı altyazı
- ✅ Sahne süresi = ses süresi (senkron, gerçek MP3 süre ölçümüyle garanti)
- ✅ Renkli terminal arayüzü (Rich) + adım adım ilerleme çubuğu
- ✅ `.env` tabanlı yapılandırma; sihirli sayı yok, her şey `config.py`de
- ✅ Hata durumlarında temiz raporlama ve tutarlı exit code disiplini
- ✅ GitHub'a hazır: README, LICENSE (MIT), .gitignore, requirements.txt, .env.example

## 📁 Proje Yapısı

```
shorts-forge/
├── .env.example              # Örnek çevre değişkenleri (kopyalayıp doldurun)
├── .gitignore                # Python + .env + output/temp hariç
├── LICENSE                   # MIT lisansı
├── README.md                 # Bu dosya
├── requirements.txt          # Bağımlılıklar
├── config.py                 # Merkezi ayar dosyası (tüm sabitler burada)
├── main.py                   # CLI giriş noktası (Typer)
├── output/                   # Üretilen videolar (.gitignore'da)
├── temp/                     # Geçici dosyalar — montaj sonrası silinir (.gitignore'da)
└── shorts_forge/             # Ana paket
    ├── __init__.py
    ├── script_generator.py   # Ollama ile senaryo + sahne prompt'ları üretir
    ├── voice_generator.py    # edge-tts ile ses dosyası üretir (+ süre ölçümü)
    ├── media_fetcher.py      # Pexels API'den dikey videoları indirir
    ├── subtitle_generator.py # Zaman damgalı altyazı üretir (word/sentence)
    ├── video_composer.py     # MoviePy ile her şeyi birleştirir ve render eder
    ├── utils.py              # Loglama, slug, dosya yardımcıları
    └── prompts/
        └── system_prompt.txt # LLM'e gönderilen sistem prompt'u (kural seti)
```

## 📋 Gereksinimler

| Bileşen | Sürüm / Not |
|---|---|
| **Python** | 3.10 veya üzeri |
| **ffmpeg** | MoviePy'nin arka plan kodlayıcısı (sistem paketi) |
| **Ollama** | Yerel LLM sunucusu — [ollama.com/download](https://ollama.com/download) |
| **LLM modeli** | `llama3` (≈4.7 GB) veya daha hafif `mistral` / `qwen2.5:3b` |
| **Pexels API anahtarı** | Ücretsiz — [pexels.com/api](https://www.pexels.com/api/) (saatte 200 istek) |
| **İnternet** | Yalnızca Pexels indirmeleri + edge-tts istekleri için |
| **Disk** | Geçici klipler için ~500 MB boş alan önerilir |

Donanım: Harici GPU **gerekmez**. 8 GB RAM'li herhangi bir modern laptop yeterlidir.

## 🚀 Kurulum Adımları

> Proje köküne inin: `cd shorts-forge`. Aşağıdaki komutlar bu dizinde varsayılır.

### Linux (CachyOS / Arch tabanlı) 🐧

```bash
# 1) Sistem paketleri (ffmpeg + python CachyOS'ta genelde zaten gelir)
sudo pacman -S --needed ffmpeg python

# 2) Sanal ortam (proje içinde — hangi paket yöneticisini kullanırsanız kullanın,
#    bu proje sisteminizin Python paketlerini kirletmez)
python -m venv .venv
source .venv/bin/activate        # fish: source .venv/bin/activate.fish

# 3) Bağımlılıklar
pip install --upgrade pip
pip install -r requirements.txt

# 4) Ortam dosyası
cp .env.example .env
$EDITOR .env                      # PEXELS_API_KEY'i yapıştırın

# 5) Ollama (systemd kurulumu varsa)
sudo systemctl enable --now ollama.service
# veya manuel:  ollama serve &

# 6) Model
ollama pull llama3               # düşük RAM için: ollama pull qwen2.5:3b

# 7) İlk video 🎉
python main.py --topic "Python'da list comprehension" --style "eğitici"
```

<details>
<summary><b>Hyprland kullanıcılarına not</b></summary>

Uçtan uca işlem tarayıcı gerektirmez; ancak Pexels anahtarı almak için bir tarayıcı gerekir
(`xdg-open https://www.pexels.com/api/`). Uzun süren render'larda ekran kilidi/kapanma
ayarlarını (idle/DPMS) geçici olarak devre dışı bırakmanız iyi olur. Önizleme için
`mpv output/shorts_*.mp4` veya `ffplay` kullanabilirsiniz.
</details>

### Ubuntu / Debian

```bash
sudo apt update && sudo apt install -y ffmpeg python3-venv python3-pip
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3
python main.py --topic "Kuantum bilgisayar nedir?" --style "merak uyandıran"
```

### Windows 🪟

```powershell
winget install Gyan.FFmpeg                # veya: choco install ffmpeg
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env                    # notepad .env ile düzenleyin
# Ollama Windows installer: https://ollama.com/download
ollama pull llama3
python main.py --topic "İstanbul'da yapılacak 3 şey" --style "eğlenceli"
```

## 🧠 Ollama Model Kurulumu

Shorts Forge, OpenAI uyumlu uç noktası değil Ollama'nın kendi `/api/chat` ucunu kullanır
(`http://localhost:11434`).

```bash
# Sunucu ayakta mı? (JSON yanıt dönerse hazırdır)
curl http://localhost:11434/api/tags

# Önerilen modeller (JSON talimatına uyum önemli)
ollama pull llama3         # dengeli, ~4.7 GB
ollama pull mistral        # daha küçük, ~4.1 GB
ollama pull qwen2.5:3b     # düşük RAM için ideal, ~1.9 GB
```

Model seçimi `.env` içindeki `OLLAMA_MODEL` ile yapılır; sunucu adresi `OLLAMA_BASE_URL`
ile değiştirilebilir (LAN'daki başka bir makinedeki Ollama'yı da kullanabilirsiniz).

> 💡 **İpucu:** Model JSON dışına taşan açıklama üretirse endişelenmeyin — parser markdown
> kod bloğu işaretlerini temizler ve `OLLAMA_MAX_RETRIES` kadar yeniden dener.

## 🔐 .env Dosyası Ayarı

`.env.example` dosyasını `.env` olarak kopyalayın (`.env` asla git'e girmez):

```ini
PEXELS_API_KEY=buraya_anahtarinizi_yapistirin
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
TTS_VOICE=tr-TR-EmelNeural
OUTPUT_RESOLUTION=1080x1920
```

| Değişken | Açıklama | Varsayılan |
|---|---|---|
| `PEXELS_API_KEY` | Pexels API anahtarı (**zorunlu**) | — |
| `OLLAMA_BASE_URL` | Ollama sunucu adresi | `http://localhost:11434` |
| `OLLAMA_MODEL` | Kullanılacak model adı | `llama3` |
| `TTS_VOICE` | edge-tts sesi (`edge-tts --list-voices` ile listeleyin) | `tr-TR-EmelNeural` |
| `OUTPUT_RESOLUTION` | `WxH` biçiminde çıktı çözünürlüğü | `1080x1920` |

Türkçe alternatif erkek sesi: `TTS_VOICE=tr-TR-AhmetNeural`.

## 🕹️ Kullanım Örnekleri

```bash
# Temel kullanım (altyazı varsayılan: kelime kelime)
python main.py --topic "Python'da list comprehension" --style "eğitici"

# Cümle bazlı (daha sade) altyazılar
python main.py -t "Karadeliğin nasıl çalıştığı" -s "merak uyandıran" --subtitles sentence

# Erkek sesli, motivasyon içerikli (geçici ortam değişkeni ile)
TTS_VOICE=tr-TR-AhmetNeural python main.py -t "Sabah 5'te kalkmak" -s "motivasyon"

# Sürüm bilgisi / yardım
python main.py --version
python main.py --help
```

**Seçenekler**

| Bayrak | Kısa | Açıklama | Varsayılan |
|---|---|---|---|
| `--topic` | `-t` | Videonun konusu (zorunlu) | — |
| `--style` | `-s` | Anlatım tarzı: eğitici, komik, motivasyon, merak uyandıran… | `eğitici` |
| `--subtitles` | — | `word` (kelime kelime) veya `sentence` (cümle bazlı) | `word` |
| `--version` | — | Sürüm numarasını yazdırıp çıkar | — |

Tipik çalışma süresi: konuya, internet hızınıza ve modelinize bağlı olarak **~1–4 dakika**
(senaryo 10–60 sn, TTS birkaç sn, indirmeler ağa bağlı, render 30–120 sn).

## ⚙️ Yapılandırma (config.py)

Tüm davranışsal sabitler `config.py` içindedir — koda gömülü sihirli sayı yoktur. En sık
dokunulanlar:

| Sabit | Anlamı | Varsayılan |
|---|---|---|
| `MAX_SCENES` / `MIN_SCENES` | Sahne sayısı aralığı (~60 sn hedefi) | 6 / 3 |
| `VIDEO_FPS`, `BITRATE` | Render parametreleri | 30, `6000k` |
| `SUBTITLE_FONT_SIZE` | Altyazı punto (px) | 72 |
| `SUBTITLE_FONT_COLOR` | Altyazı rengi | `yellow` |
| `SUBTITLE_WORDS_PER_CHUNK` | Kelime bazlı modda ekrandaki kelime sayısı | 3 |
| `SUBTITLE_Y_POSITION_RATIO` | Dikey konum (0.5 = ekran ortası) | 0.5 |
| `TTS_RATE` | Konuşma hızı (Shorts için hafif hızlı) | `+8%` |
| `PEXELS_REQUEST_DELAY_SECONDS` | Rate-limit beklemesi | 1.0 |
| `SCENE_PADDING_SECONDS` | Sahneler arası nefes payı | 0.15 |

## 📦 Modül Referansı

| Modül | Görevi | Dışa açtığı başlıca API |
|---|---|---|
| `script_generator.py` | Ollama `/api/chat`'e sistem prompt'u + konuyu gönderir, JSON senaryoyu doğrular | `generate_script(topic, style) -> Script` |
| `voice_generator.py` | Her sahneyi edge-tts ile MP3'ler, mutagen ile gerçek süreyi ölçer | `generate_voices(narrations, temp_dir) -> list[VoiceClip]` |
| `media_fetcher.py` | Pexels video araması (`orientation=portrait`), en iyi klibi indirir, sleep'li rate-limit | `fetch_media(prompts, temp_dir)` |
| `subtitle_generator.py` | Ses sürelerine göre word/sentence zaman damgası üretir | `generate_subtitles(narrations, durations, mode)` |
| `video_composer.py` | Kırp → birleştir → altyazı → render (1080×1920); sonra `temp/` temizler | `compose_video(...) -> CompositionResult` |
| `utils.py` | Rich konsol, log yardımcıları, slug/dosya işlemleri | `log_info/warning/error/step`, `ensure_dir`, `make_slug` |

## 📂 Çıktı Nerede?

Başarılı üretimde dosya şu şablonla `output/` klasörüne yazılır:

```
output/shorts_20261019_214530_python-da-list-comprehension.mp4
```

Terminal sonunda panel içinde kesin yol, toplam süre ve çözünürlük basılır.
Geçici dosyalar (`temp/`) montaj biter bitmez otomatik olarak silinir.

## 🩺 Sorun Giderme

| Belirti | Olası neden & çözüm |
|---|---|
| `PEXELS_API_KEY tanımlı değil` hatası | `.env` dosyası yok veya doldurulmamış → `cp .env.example .env` edip anahtarı girin |
| `ConnectionError ... localhost:11434` | Ollama çalışmıyor → `ollama serve` veya `sudo systemctl start ollama` |
| LLM bozuk JSON döndürüyor / retry uyarıları | Daha talimat-uyumlu model deneyin: `ollama pull qwen2.5:3b` veya `mistral` |
| `ModuleNotFoundError: moviepy.editor` | MoviePy **2.x** kurulmuş olabilir. Bu proje 1.x API'siyle yazıldı: `pip install "moviepy==1.0.3"` |
| `FFmpeg not found` / render hatası | `sudo pacman -S ffmpeg` (veya ilgili paket yöneticisi) kurun, PATH'i kontrol edin |
| `module 'PIL.Image' has no attribute 'ANTIALIAS'` uyarısı | Pillow ≥ 10 + MoviePy 1.0.3 uyumsuzluğu — composer başındaki yama bunu otomatik giderir; güncel `Pillow` kurulu tutun |
| `ImageMagick ... No such file or directory` | Artık beklenmez: altyazılar ImageMagick yerine PIL ile çizilir. Görürseniz eski sürüm kullanıyorsunuz demektir (`git pull`) |
| Altyazılarda Türkçe karakterler kutu/bozuk | Font sorunu — composer DejaVu/Liberation TTF arar; `ttf-dejavu` paketini kurun |
| İndirmeler çok yavaş / timeout | Ağ hızınız düşük; `PEXELS_DOWNLOAD_TIMEOUT_SECONDS` artırılabilir ama asıl çözüm stabil bağlantı |
| HTTP 429 Too Many Requests (Pexels) | Saatlik 200 istek aşıldı → `PEXELS_REQUEST_DELAY_SECONDS` değerini artırın veya ~1 saat bekleyin |
| Ses/video senkronu kaymış | Sahne sesi üretilemediyse fallback devrededir; `temp/`deki MP3'lerin oluştuğunu kontrol edin |
| Ctrl+C ile iptal | Pipeline iptal edilir (exit code 130); `temp/` içeriğini elle silmek güvenlidir |

## ⚠️ Bilinen Sınırlamalar

- **VRAM gerektirmez** — AI video üretmediğimiz için ekran kartından bağımsız çalışır;
  düşük donanımda darboğaz yalnızca CPU render ve ağ hızıdır.
- **Pexels saatlik 200 istek limiti**, çok sahneli/çok denemeli işlerde beklemeye yol açar.
- Altyazı zamanlaması, bilinen MP3 süreleri üzerinden **yaklaşık kelime hızı** ile hesaplanır;
  mükemmel fonetik senkron isterseniz `subtitle_generator.py` modülünü Whisper ile
  genişletebilirsiniz (modüler tasarım buna uygundur).
- Stok klip, sahnenin anlamıyla %100 eşleşmeyebilir (LLM'in İngilizce anahtar kelime
  kalitesine bağlıdır). `prompts/system_prompt.txt` dosyasını kişiselleştirmek en hızlı
  iyileştirmedir.
- edge-tts, Microsoft uç noktalarına anonim istek atar; gelecekte erişim politikası
  değişebilir (tamamen offline alternatif: Piper).
- Üretilen videolar platformların telif/farklılık politikalarına takılabilir; Pexels
  materyalleri serbest olsa da yayına almadan önce içeriği gözden geçirin.

## ❓ Sıkça Sorulan Sorular

**Para gerekir mi?** Hayır. Ollama, edge-tts, Pexels API ve MoviePy ücretsizdir.

**İnternet şart mı?** Kısmen: Pexels indirmeleri ve edge-tts için gerekli; senaryo üretimi
tamamen çevrimdışı çalışır.

**Başka dil/aksan kullanabilir miyim?** Evet — `edge-tts --list-voices` ile tüm sesleri
görüp `TTS_VOICE` değerini değiştirin; sistem prompt'unu da o dile uyarlayın.

**Kendi görüntülerimi kullanabilir miyim?** `media_fetcher.py` modülünü yerel bir klasörden
klip seçecek şekilde ~20 satırda değiştirebilirsiniz (modüler tasarım bunun için var).

**Yatay (16:9) video üretilebilir mi?** Mimari uygun: `OUTPUT_RESOLUTION=1920x1080` ve
`config.py` içindeki `PEXELS_ORIENTATION="landscape"` değişikliğiyle başlayabilirsiniz.

**Kaç video üretebilirim?** Yazılımsal sınır yok; pratikte Pexels saatlik kota belirleyicidir.

## 🤝 Katkıda Bulunma

1. Fork'layın ve feature branch açın: `git checkout -b feature/pixabay-fetcher`
2. Değişikliği yapın (PEP8, type hint, Türkçe docstring — mevcut stile uyun)
3. Test edin: en azından `python main.py --help` ve gerçek bir üretim koşusu
4. Commit: `git commit -m "feat: Pixabay fallback fetcher eklendi"`
5. Pull Request açın

Fikir alanları: Whisper ile fonetik altyazı, Pixabay/coverr yedek kaynağı, arka plan müzik
katmanı, otomatik thumbnail, toplu konu dosyası (batch), Dockerfile.

## 📜 Lisans

Dağıtım [MIT](LICENSE) lisansı altında yapılır — ticari kullanım dahil serbesttir.
İndirilen materyaller **Pexels License** hükümlerine tabidir.

---

<sub>Made with ❤️ and far too many cat videos. İyi üretimler!</sub>
