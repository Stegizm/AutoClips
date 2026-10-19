"""Ortak yardımcı fonksiyonlar: loglama, dosya işlemleri, slug üretimi.

Bu modül diğer tüm modüller tarafından kullanılır; tek sorumluluğu
proje genelinde tekrar eden küçük işleri merkezi hale getirmektir.
"""

from __future__ import annotations

import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any

from rich.console import Console

# Rich konsol nesnesi: renkli terminal çıktısı için tek merkezden sağlanır
console: Console = Console()


def log_info(message: str) -> None:
    """Bilgi seviyesinde mesajı yeşil renkle terminale yazar.

    Args:
        message: Yazılacak mesaj metni.
    """
    console.print(f"[green]ℹ  {message}[/green]")


def log_warning(message: str) -> None:
    """Uyarı seviyesinde mesajı sarı renkle terminale yazar.

    Args:
        message: Yazılacak uyarı metni.
    """
    console.print(f"[yellow]⚠  {message}[/yellow]")


def log_error(message: str) -> None:
    """Hata seviyesinde mesajı kırmızı renkle terminale yazar.

    Args:
        message: Yazılacak hata metni.
    """
    console.print(f"[red]✖  {message}[/red]")


def log_step(message: str) -> None:
    """Pipeline adım başlığını vurgulu şekilde yazdırır.

    Args:
        message: Adım açıklaması (örn: 'Senaryo üretiliyor').
    """
    console.print(f"\n[bold cyan]==> {message}[/bold cyan]")


def ensure_dir(path: Path) -> Path:
    """Verilen yolun bir dizin olarak var olmasını sağlar.

    Args:
        path: Oluşturulacak dizin yolu.

    Returns:
        Path: Doğrulanmış/güvence altına alınmış dizin yolu.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def clean_dir(path: Path) -> None:
    """Bir dizinin içeriğini siler ve boş olarak yeniden oluşturur.

    .gitkeep gibi koruma dosyaları yeniden oluşturulmaz; sadece içerik temizlenir.

    Args:
        path: Temizlenecek dizin yolu.
    """
    if path.exists():
        shutil.rmtree(path)
    ensure_dir(path)


def make_slug(text: str, max_length: int = 40) -> str:
    """Metni dosya adına uygun, Türkçe karakterleri sadeleştirilmiş slug'a çevirir.

    Örnek: 'Python list comprehension' -> 'python-list-comprehension'

    Args:
        text: Dönüştürülecek ham metin.
        max_length: Slug'un azami uzunluğu.

    Returns:
        str: Dosya adı için güvenli slug.
    """
    # Türkçe ve diğer aksanlı karakterleri ASCII karşılıklarına indirge
    normalized: str = unicodedata.normalize("NFKD", text)
    ascii_text: str = normalized.encode("ascii", "ignore").decode("ascii")
    # Küçük harfe çevir ve dosyaya uygun olmayan karakterleri tire ile değiştir
    slug: str = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    # Uzunluk sınırını uygula ve sondaki tireleri temizle
    return slug[:max_length].rstrip("-")


def load_text_file(path: Path) -> str:
    """Bir metin dosyasının içeriğini UTF-8 olarak okur.

    Args:
        path: Okunacak dosyanın yolu.

    Returns:
        str: Dosya içeriği.

    Raises:
        FileNotFoundError: Dosya mevcut değilse.
    """
    if not path.exists():
        raise FileNotFoundError(f"Sistem prompt dosyası bulunamadı: {path}")
    return path.read_text(encoding="utf-8")


def coerce_number(value: Any, default: float) -> float:
    """LLM'den gelen değeri güvenle float'a çevirir; olmazsa varsayılanı döner.

    Args:
        value: Dönüştürülecek değer (int, float, str vb.).
        default: Dönüşüm başarısız olduğunda kullanılacak varsayılan sayı.

    Returns:
        float: Dönüştürülmüş sayı ya da varsayılan.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
