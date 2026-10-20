"""Shorts Forge masaüstü GUI uygulaması (CustomTkinter).

Windows ve Linux'ta çalışır. Pipeline, arka plan iş parçacığında (thread)
çalıştırılır; GUI hiç kilitlenmez. İlerleme, log akışı, önizleme ve ayarlar
sekmesi içerir.

Kullanım:
    python gui.py
    python main.py gui ...
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any, Optional

import customtkinter as ctk

import config
from shorts_forge import script_generator
from shorts_forge.core import PIPELINE_STEPS, run_pipeline, validate_settings
from shorts_forge.script_generator import generate_script
from shorts_forge.subtitle_generator import generate_subtitles
from shorts_forge.voice_generator import generate_voices
from shorts_forge.utils import ensure_dir

# Uygulama sabitleri
APP_TITLE: str = "Shorts Forge"
GUI_WIDTH: int = 980
GUI_HEIGHT: int = 720
SUBTITLE_MODES: dict[str, str] = {
    "Kelime kelime (Hormozi)": "word",
    "Cümle bazlı": "sentence",
}
STYLE_PRESETS: tuple[str, ...] = ("eğitici", "komik", "motivasyon", "haber", "merak uyandıran")


class _EnvFile:
    """Basit .env okuyucu/yazıcı (GUI ayarları için).

    Yalnızca ``KEY=DEĞER`` satırlarını işler; yorum satırlarını korur.
    """

    def __init__(self, path: Path) -> None:
        """Verilen .env dosyası yoluyla başlatır."""
        self.path: Path = path
        self.data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        """.env dosyasındaki KEY=DEĞER çiftlerini sözlüğe yükler."""
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            stripped: str = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            self.data[key.strip()] = value.strip()

    def get(self, key: str, default: str = "") -> str:
        """Bir anahtarın değerini döndürür (yoksa varsayılan)."""
        return self.data.get(key, default)

    def set(self, key: str, value: str) -> None:
        """Bir anahtarı günceller veya ekler."""
        self.data[key] = value

    def save(self) -> None:
        """Tüm veriyi .env dosyasına yazar."""
        lines: list[str] = [f"{k}={v}" for k, v in self.data.items()]
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class ShortsForgeApp(ctk.CTk):
    """Ana pencere: Üretim sekmesi + Ayarlar sekmesi."""

    def __init__(self) -> None:
        """Pencereyi, widget'ları ve iş parçacığı kuyruğunu kurar."""
        super().__init__()
        self.title(f"{APP_TITLE} — Otomatik Shorts/Reels Üretici")
        self.geometry(f"{GUI_WIDTH}x{GUI_HEIGHT}")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # GUI <-> worker thread arasındaki mesajlaşma kuyruğu
        self.msg_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self.cancel_event: threading.Event = threading.Event()
        self.last_output: Optional[Path] = None

        # Ayar dosyası: geliştirme modunda proje kökü/.env, paketlenmiş
        # (PyInstaller) çalıştırmada ~/.shorts-forge/.env kullanılır.
        self.env: _EnvFile = _EnvFile(config.ENV_FILE)

        self._build_ui()
        self.after(100, self._poll_queue)  # Kuyruk tüketicisi

    # ------------------------------------------------------------------ UI ---
    def _build_ui(self) -> None:
        """Tüm arayüz bileşenlerini oluşturur."""
        self.tabview: ctk.CTkTabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 4))
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.tab_generate: ctk.CTkFrame = self.tabview.add("🎬 Üretim")
        self.tab_settings: ctk.CTkFrame = self.tabview.add("⚙️ Ayarlar")
        self._build_generate_tab()
        self._build_settings_tab()
        self._build_statusbar()

    def _build_generate_tab(self) -> None:
        """Üretim sekmesini kurar (girdi formu + ilerleme + log + önizleme)."""
        tab: ctk.CTkFrame = self.tab_generate
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(1, weight=1)

        # --- Sol: girdi formu ------------------------------------------------
        left: ctk.CTkFrame = ctk.CTkFrame(tab, width=340)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 8), pady=0)
        left.grid_propagate(False)

        ctk.CTkLabel(left, text="Video Konusu", font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", padx=12, pady=(12, 2)
        )
        topic_entry = ctk.CTkTextbox(left, height=70, wrap="word")
        topic_entry.pack(fill="x", padx=12)
        self.topic_entry = topic_entry

        ctk.CTkLabel(left, text="Anlatım Tarzı", font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", padx=12, pady=(12, 2)
        )
        self.style_combo = ctk.CTkComboBox(left, values=list(STYLE_PRESETS))
        self.style_combo.set("eğitici")
        self.style_combo.pack(fill="x", padx=12)

        ctk.CTkLabel(left, text="Altyazı Modu", font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", padx=12, pady=(12, 2)
        )
        subtitle_menu = ctk.CTkOptionMenu(
            left, values=list(SUBTITLE_MODES.keys()), dynamic_resizing=False
        )
        subtitle_menu.pack(fill="x", padx=12)
        self.subtitle_menu = subtitle_menu

        # Ön izleme butonu (yalnız senaryo + ses, indirme/montaj yok)
        preview_btn = ctk.CTkButton(
            left, text="🔍 Senaryoyu Ön İzle", fg_color="#3a3a55",
            command=self._on_preview_click,
        )
        preview_btn.pack(fill="x", padx=12, pady=(16, 4))
        self.preview_btn = preview_btn

        # Ana üretim butonu
        generate_btn = ctk.CTkButton(
            left, text="🚀 Video Üret", height=44,
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self._on_generate_click,
        )
        generate_btn.pack(fill="x", padx=12, pady=(4, 4))
        self.generate_btn = generate_btn

        # İptal butonu
        cancel_btn = ctk.CTkButton(
            left, text="✖ İptal", fg_color="#7a2e2e", state="disabled",
            command=self._on_cancel_click,
        )
        cancel_btn.pack(fill="x", padx=12, pady=(0, 8))
        self.cancel_btn = cancel_btn

        # --- Sağ: ilerleme + log + önizleme ---------------------------------
        right: ctk.CTkFrame = ctk.CTkFrame(tab, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")

        progress_label = ctk.CTkLabel(
            right, text="Hazır. Bir konu girip 'Video Üret' butonuna basın.",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        progress_label.pack(anchor="w", padx=4, pady=(0, 4))
        self.progress_label = progress_label

        progress_bar = ctk.CTkProgressBar(right)
        progress_bar.set(0.0)
        progress_bar.pack(fill="x", padx=4, pady=(0, 8))
        self.progress_bar = progress_bar

        # Adım işaretleri
        self.step_labels: list[ctk.CTkLabel] = []
        steps_frame: ctk.CTkFrame = ctk.CTkFrame(right, fg_color="transparent")
        steps_frame.pack(fill="x", padx=4, pady=(0, 6))
        for step_name in PIPELINE_STEPS:
            lbl: ctk.CTkLabel = ctk.CTkLabel(steps_frame, text=f"○ {step_name}", anchor="w")
            lbl.pack(fill="x")
            self.step_labels.append(lbl)

        # Log akışı
        ctk.CTkLabel(right, text="İşlem Günlüğü", font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=4, pady=(6, 2)
        )
        log_box = ctk.CTkTextbox(right, wrap="word")
        log_box.pack(fill="both", expand=True, padx=4, pady=(0, 6))
        log_box.configure(state="disabled")
        self.log_box = log_box

        # Alt eylem butonları
        actions: ctk.CTkFrame = ctk.CTkFrame(right, fg_color="transparent")
        actions.pack(fill="x", padx=4, pady=(0, 4))
        open_output_btn = ctk.CTkButton(
            actions, text="📂 Çıktı Klasörü", width=150, fg_color="#2b2b3d",
            command=self._open_output_folder,
        )
        open_output_btn.pack(side="left", padx=(0, 6))
        self.open_output_btn = open_output_btn
        play_btn = ctk.CTkButton(
            actions, text="▶ Videoyu Aç", width=130, fg_color="#2b2b3d",
            state="disabled", command=self._play_last_video,
        )
        play_btn.pack(side="left")
        self.play_btn = play_btn

    def _build_settings_tab(self) -> None:
        """Ayarlar sekmesini kurar (.env alanları + çıktı klasörü)."""
        tab: ctk.CTkFrame = self.tab_settings
        outer: ctk.CTkFrame = ctk.CTkFrame(tab)
        outer.pack(fill="both", expand=True, padx=8, pady=8)

        # Alan tanımı: (etiket, env_anahtari, varsayilan)
        fields: tuple[tuple[str, str, str], ...] = (
            ("Pexels API Key", "PEXELS_API_KEY", ""),
            ("Ollama Adresi", "OLLAMA_BASE_URL", "http://localhost:11434"),
            ("Ollama Modeli", "OLLAMA_MODEL", "llama3"),
            ("TTS Sesi", "TTS_VOICE", "tr-TR-EmelNeural"),
            ("Çözünürlük (GxY)", "OUTPUT_RESOLUTION", "1080x1920"),
        )
        self.setting_entries: dict[str, ctk.CTkEntry] = {}
        row: int = 0
        for label_text, key, default in fields:
            stored: str = self.env.get(key) or os.getenv(key, default)
            ctk.CTkLabel(outer, text=label_text, font=ctk.CTkFont(size=14, weight="bold")).grid(
                row=row, column=0, sticky="w", padx=14, pady=(12, 2)
            )
            entry = ctk.CTkEntry(outer, width=420)
            entry.insert(0, stored)
            entry.grid(row=row, column=1, sticky="we", padx=(6, 14))
            self.setting_entries[key] = entry
            row += 1
        outer.grid_columnconfigure(1, weight=1)

        # API anahtarını maskele/göster
        key_entry: ctk.CTkEntry = self.setting_entries["PEXELS_API_KEY"]
        show_btn = ctk.CTkButton(
            outer, text="Göster", width=70,
            command=lambda: self._toggle_secret(key_entry, show_btn),
        )
        show_btn.grid(row=0, column=2, padx=(0, 14))
        key_entry.configure(show="•")

        # Çıktı klasörü seçimi
        ctk.CTkLabel(outer, text="Çıktı Klasörü", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=row, column=0, sticky="w", padx=14, pady=(12, 2)
        )
        folder_frame: ctk.CTkFrame = ctk.CTkFrame(outer, fg_color="transparent")
        folder_frame.grid(row=row, column=1, columnspan=2, sticky="we", padx=(6, 14))
        output_entry = ctk.CTkEntry(folder_frame)
        output_entry.insert(0, str(config.OUTPUT_DIR))
        output_entry.pack(side="left", fill="x", expand=True)
        self.output_entry = output_entry
        ctk.CTkButton(
            folder_frame, text="Seç...", width=80, command=self._choose_output_dir
        ).pack(side="left", padx=(6, 0))
        row += 1

        # Butonlar
        btn_frame: ctk.CTkFrame = ctk.CTkFrame(outer, fg_color="transparent")
        btn_frame.grid(row=row, column=0, columnspan=3, pady=18)
        ctk.CTkButton(btn_frame, text="💾 Kaydet", width=130, command=self._save_settings).pack(
            side="left", padx=6
        )
        ctk.CTkButton(
            btn_frame, text="🔗 Ollama Bağlantısını Test Et", width=230,
            fg_color="#2b2b3d", command=self._test_ollama,
        ).pack(side="left", padx=6)

    def _build_statusbar(self) -> None:
        """Pencere altındaki durum çubuğunu kurar."""
        statusbar = ctk.CTkLabel(
            self, text="Hazır", anchor="w", font=ctk.CTkFont(size=12),
            text_color="gray70",
        )
        statusbar.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        self.statusbar = statusbar

    # ------------------------------------------------------------ helpers ---
    @staticmethod
    def _is_frozen() -> bool:
        """PyInstaller ile paketlenmiş çalıştırma olup olmadığını döndürür."""
        return getattr(sys, "frozen", False)

    def _toggle_secret(self, entry: ctk.CTkEntry, button: ctk.CTkButton) -> None:
        """API anahtarı girişinin maskesini açar/kapatır."""
        if entry.cget("show"):
            entry.configure(show="")
            button.configure(text="Gizle")
        else:
            entry.configure(show="•")
            button.configure(text="Göster")

    def _log(self, message: str) -> None:
        """Log kutusuna satır ekler (thread güvenli: kuyruk üzerinden)."""
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _set_status(self, text: str) -> None:
        """Durum çubuğu metnini günceller."""
        self.statusbar.configure(text=text)

    def _choose_output_dir(self) -> None:
        """Çıktı klasörü için sistem dizin seçim penceresini açar."""
        chosen: Optional[str] = filedialog.askdirectory(title="Çıktı Klasörü Seç")
        if chosen:
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, chosen)

    def _save_settings(self) -> None:
        """Ayarlar sekmesindeki değerleri .env'e yazar ve config'i günceller."""
        for key, entry in self.setting_entries.items():
            self.env.set(key, entry.get().strip())
        self.env.set("OUTPUT_DIR_OVERRIDE", self.output_entry.get().strip())
        try:
            self.env.save()
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f".env kaydedilemedi: {exc}")
            return

        # Çalışan config ve utils modüllerini hemen güncelle (modüller
        # değerleri kopyaladığı için her ikisine de yazmak gerekir).
        pexels_key: str = self.env.get("PEXELS_API_KEY")
        ollama_url: str = self.env.get("OLLAMA_BASE_URL", config.OLLAMA_BASE_URL)
        ollama_model: str = self.env.get("OLLAMA_MODEL", config.OLLAMA_MODEL)
        tts_voice: str = self.env.get("TTS_VOICE", config.TTS_VOICE)
        for module in (config,):  # modüller config.* niteliklerini anlık okur
            module.PEXELS_API_KEY = pexels_key
            module.OLLAMA_BASE_URL = ollama_url
            module.OLLAMA_MODEL = ollama_model
            module.TTS_VOICE = tts_voice
        # kenar etkisi: os.environ'i da güncelle (os.getenv ile okuyan yerler için)
        os.environ["PEXELS_API_KEY"] = pexels_key
        os.environ["OLLAMA_BASE_URL"] = ollama_url
        os.environ["OLLAMA_MODEL"] = ollama_model
        os.environ["TTS_VOICE"] = tts_voice
        self._apply_resolution(self.env.get("OUTPUT_RESOLUTION", "1080x1920"))
        self._log("✔ Ayarlar .env dosyasına kaydedildi.")
        self._set_status("Ayarlar kaydedildi.")

    def _apply_resolution(self, raw: str) -> None:
        """'1080x1920' biçimli çözünürlük metnini config'e uygular."""
        try:
            w_str, h_str = raw.lower().split("x", 1)
            config.VIDEO_WIDTH, config.VIDEO_HEIGHT = int(w_str), int(h_str)
        except ValueError:
            self._log("⚠ Geçersiz çözünürlük; 1080x1920 kullanılacak.")

    def _output_dir(self) -> Path:
        """Seçili/ayarlı çıktı klasörünü döndürür."""
        override: str = self.env.get("OUTPUT_DIR_OVERRIDE", "")
        return Path(override) if override else config.OUTPUT_DIR

    def _open_path(self, path: Path) -> None:
        """Dosya/klasörü işletim sisteminin varsayılan uygulamasıyla açar."""
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _open_output_folder(self) -> None:
        """Çıktı klasörünü dosya yöneticisinde açar."""
        out: Path = self._output_dir()
        ensure_dir(out)
        try:
            self._open_path(out)
        except OSError as exc:
            messagebox.showwarning(APP_TITLE, f"Klasör açılamadı: {exc}")

    def _test_ollama(self) -> None:
        """Ayarlar sekmesindeki Ollama adresine /api/tags ile istek atar."""
        import requests  # yerel import: GUI açılışını hafif tutmak için

        url: str = self.setting_entries["OLLAMA_BASE_URL"].get().strip().rstrip("/") + "/api/tags"
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            models: list[str] = [m.get("name", "?") for m in resp.json().get("models", [])]
            names: str = ", ".join(models) if models else "(kurulu model yok!)"
            self._log(f"✔ Ollama erişilebilir. Modeller: {names}")
            messagebox.showinfo(APP_TITLE, f"Ollama bağlantısı başarılı.\nModeller: {names}")
        except Exception as exc:  # noqa: BLE001 - kullanıcıya gösterilecek son durak
            self._log(f"✖ Ollama testi başarısız: {exc}")
            messagebox.showerror(
                APP_TITLE,
                f"Ollama'ya ulaşılamadı ({url}).\n\n'ollama serve' çalışıyor mu kontrol edin.",
            )

    def _play_last_video(self) -> None:
        """Son üretilen videoyu varsayılan oynatıcıda açar."""
        if self.last_output and self.last_output.exists():
            try:
                self._open_path(self.last_output)
            except OSError as exc:
                messagebox.showwarning(APP_TITLE, f"Video açılamadı: {exc}")

    # ------------------------------------------------------------- actions ---
    def _on_generate_click(self) -> None:
        """"Video Üret" butonu: doğrular ve pipeline'ı thread'de başlatır."""
        if self.worker and self.worker.is_alive():
            return
        topic: str = self.topic_entry.get("1.0", "end").strip()
        if not topic:
            messagebox.showwarning(APP_TITLE, "Lütfen bir video konusu girin.")
            return

        # Ayarlardaki değerleri üretmeden önce config'e işle
        self._save_settings()

        problems: list[str] = validate_settings()
        if problems:
            messagebox.showerror(APP_TITLE, "Eksik ayarlar:\n\n" + "\n".join(problems))
            self.tabview.set("⚙️ Ayarlar")
            return

        style: str = self.style_combo.get().strip() or "eğitici"
        mode: str = SUBTITLE_MODES[self.subtitle_menu.get()]
        self._reset_progress()
        self._set_buttons(running=True)
        self._log(f"=== Üretim başladı | konu: {topic!r} | tarz: {style} | altyazı: {mode} ===")

        self.cancel_event.clear()
        self.worker = threading.Thread(
            target=self._worker_generate, args=(topic, style, mode), daemon=True
        )
        self.worker.start()

    def _on_preview_click(self) -> None:
        """"Senaryoyu Ön İzle": yalnızca LLM senaryosu + TTS sürelerini gösterir."""
        if self.worker and self.worker.is_alive():
            return
        topic: str = self.topic_entry.get("1.0", "end").strip()
        if not topic:
            messagebox.showwarning(APP_TITLE, "Lütfen önce bir konu girin.")
            return
        self._save_settings()
        style: str = self.style_combo.get().strip() or "eğitici"
        self._set_buttons(running=True)
        self._reset_progress()
        self._log("=== Ön izleme: senaryo + seslendirme test ediliyor ===")
        self.worker = threading.Thread(
            target=self._worker_preview, args=(topic, style), daemon=True
        )
        self.worker.start()

    def _on_cancel_click(self) -> None:
        """"İptal" butonu: worker'a durma sinyali gönderir."""
        self.cancel_event.set()
        self._log("⏹ İptal isteği gönderildi; mevcut adım bitince durulacak...")
        self.cancel_btn.configure(state="disabled")

    # -------------------------------------------------------------- workers --
    def _worker_generate(self, topic: str, style: str, mode: str) -> None:
        """Arka plan iş parçacığı: tam pipeline'ı çalıştırır (GUI thread'i değil!)."""
        try:
            if self.cancel_event.is_set():
                self.msg_queue.put(("cancelled", None))
                return

            def on_step(name: str, index: int, total: int) -> None:
                """core.run_pipeline adım geri çağırması -> kuyruğa yazır."""
                if self.cancel_event.is_set():
                    raise KeyboardInterrupt("Kullanıcı iptali")
                self.msg_queue.put(("step", (name, index, total)))

            result = run_pipeline(
                topic=topic, style=style, subtitle_mode=mode, on_step=on_step,
                output_dir=self._output_dir(),
            )
            self.msg_queue.put(("done", result))
        except KeyboardInterrupt:
            self.msg_queue.put(("cancelled", None))
        except Exception as exc:  # noqa: BLE001 - worker son durağı
            self.msg_queue.put(("error", exc))

    def _worker_preview(self, topic: str, style: str) -> None:
        """Arka plan iş parçacığı: senaryo + ses ön izlemesi üretir."""
        try:
            self.msg_queue.put(("log", "[1/2] Ollama'dan senaryo isteniyor..."))
            script = generate_script(topic=topic, style=style)
            self.msg_queue.put(("log", f"Başlık: {script.title}"))
            narrations: list[str] = []
            for i, scene in enumerate(script.scenes, 1):
                self.msg_queue.put(
                    ("log", f"  Sahne {i}: \"{scene.narration}\" (görsel: {scene.visual_prompt})")
                )
                narrations.append(scene.narration)

            self.msg_queue.put(("log", "[2/2] Seslendirmeler üretiliyor (edge-tts)..."))
            temp_dir: Path = config.TEMP_DIR
            ensure_dir(temp_dir)
            voices = generate_voices(narrations, temp_dir)
            total: float = sum(v.duration for v in voices)
            for i, voice in enumerate(voices, 1):
                self.msg_queue.put(("log", f"  Ses {i}: {voice.duration:.1f} sn"))
            cues = generate_subtitles(narrations, [v.duration for v in voices], "word")[:3]
            for cue in cues:
                self.msg_queue.put(
                    ("log", f"  Altyazı örneği [{cue.start:.1f}-{cue.end:.1f}]: {cue.text}")
                )
            self.msg_queue.put(
                ("log", f"✔ Ön izleme bitti. Tahmini toplam süre: {total:.1f} sn. "
                        "Video üretmek için butona basın.")
            )
        except Exception as exc:  # noqa: BLE001
            self.msg_queue.put(("error", exc))
        finally:
            self.msg_queue.put(("idle", None))

    # --------------------------------------------------------------- queue ---
    def _reset_progress(self) -> None:
        """İlerleme çubuğunu ve adım işaretlerini sıfırlar."""
        self.progress_bar.set(0.0)
        for i, lbl in enumerate(self.step_labels):
            lbl.configure(text=f"○ {PIPELINE_STEPS[i]}")
        self.progress_label.configure(text="Başlatılıyor...")

    def _mark_step(self, name: str, index: int, total: int) -> None:
        """Belirtilen adımı GUI'de işaretler; önceki adımları ✔ yapar."""
        self.progress_bar.set((index - 1) / total)
        self.progress_label.configure(text=f"[{index}/{total}] {name}...")
        for i, lbl in enumerate(self.step_labels):
            plain: str = PIPELINE_STEPS[i]
            if i < index - 1:
                lbl.configure(text=f"✔ {plain}")
            elif i == index - 1:
                lbl.configure(text=f"◉ {plain}")
        self._set_status(f"Çalışıyor: {name}")

    def _set_buttons(self, running: bool) -> None:
        """Butonların etkinliğini çalışma durumuna göre ayarlar."""
        self.generate_btn.configure(state="disabled" if running else "normal")
        self.preview_btn.configure(state="disabled" if running else "normal")
        self.cancel_btn.configure(state="normal" if running else "disabled")

    def _poll_queue(self) -> None:
        """GUI thread'inde kuyruğu tüketir; periyodik olarak kendini yeniden zamanlar."""
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "step":
                    self._mark_step(*payload)
                elif kind == "log":
                    self._log(str(payload))
                elif kind == "done":
                    self.progress_bar.set(1.0)
                    for lbl in self.step_labels:
                        i: int = self.step_labels.index(lbl)
                        lbl.configure(text=f"✔ {PIPELINE_STEPS[i]}")
                    self.progress_label.configure(text="Tamamlandı ✔")
                    self.last_output = payload.output_path
                    self.play_btn.configure(state="normal")
                    self._log(
                        f"✔ Video üretildi: {payload.output_path} "
                        f"({payload.total_duration:.1f} sn)"
                    )
                    self._set_status("Hazır.")
                    self._set_buttons(running=False)
                    messagebox.showinfo(
                        APP_TITLE,
                        f"Video hazır!\n\n{payload.output_path}\n"
                        f"Süre: {payload.total_duration:.1f} sn",
                    )
                elif kind == "error":
                    self._log(f"✖ HATA: {payload}")
                    self._set_status("Hata oluştu.")
                    self._set_buttons(running=False)
                    self.progress_label.configure(text="Hata ✖")
                    messagebox.showerror(APP_TITLE, f"Üretim başarısız oldu:\n\n{payload}")
                elif kind == "cancelled":
                    self._log("⏹ Üretim iptal edildi.")
                    self._set_status("İptal edildi.")
                    self._set_buttons(running=False)
                    self.progress_label.configure(text="İptal edildi")
                elif kind == "idle":
                    self._set_buttons(running=False)
                    self._set_status("Hazır.")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)


def launch_gui() -> None:
    """GUI uygulamasını başlatır (CLI `gui` komutu ve gui.py için ortak giriş)."""
    app: ShortsForgeApp = ShortsForgeApp()
    app.mainloop()


if __name__ == "__main__":
    launch_gui()
