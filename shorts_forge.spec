# -*- coding: utf-8 -*-
"""Shorts Forge — PyInstaller paketleme yapılandırması.

Bu dosya, `pyinstaller shorts_forge.spec` komutuyla kullanılır.
Windows ve Linux için ayrı ayrı (her platformda bir kez) çalıştırılabilir
üretir. macOS'ta da aynı spec çalışır.

Notlar:
- MoviePy/ffmpeg: ffmpeg.exe sistem PATH'inde olmalıdır (veya side-by-side
  olarak dist/'e kopyalanmalıdır). İstemci tarafı gereksinim README'de var.
- Ollama ve Pexels ağ servisleridir; pakete dahil edilmez.
- customtkinter'ın .json tema dosyaları collect_data_files ile toplanır.
"""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# customtkinter tema/asset dosyaları + alt modülleri
ctk_datas = collect_data_files("customtkinter")
ctk_hidden = collect_submodules("customtkinter")

# MoviePy ve dolaylı bağımlılıkları için gizli import'lar
hidden_imports = ctk_hidden + [
    "moviepy.editor",
    "moviepy.video.io.ffmpeg_writer",
    "edge_tts",
    "mutagen",
    "dotenv",
    "rich",
    "typer",
    "PIL",
]

a = Analysis(
    ["gui.py"],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=ctk_datas + [("shorts_forge/prompts", "shorts_forge/prompts")],
    hiddenimports=hidden_imports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "numpy.tests", "tkinter.test"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ShortsForge",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # GUI: konsol penceresi yok (Windows'ta cmd perdesi kapalı)
    icon=None,              # assets/icon.ico eklerseniz buraya yolu yazın
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ShortsForge",
)
