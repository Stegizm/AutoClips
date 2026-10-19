"""Senaryo üretici modül.

Ollama yerel LLM'ine istek atarak kullanıcının verdiği konudan, sahne sahne
bir Shorts senaryosu (JSON) üretir. Çıktı veri sınıfı olarak normalize edilir.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import requests

import config
from shorts_forge.utils import coerce_number, load_text_file, log_info, log_warning


@dataclass
class Scene:
    """Tek bir video sahnesini temsil eder.

    Attributes:
        narration: Seslendirilecek Türkçe metin.
        visual_prompt: Pexels'te aranacak İngilizce anahtar kelime.
        duration_estimate: Sahnenin tahmini süresi (saniye).
    """

    narration: str
    visual_prompt: str
    duration_estimate: float = 5.0


@dataclass
class Script:
    """Tüm video senaryosunu temsil eder.

    Attributes:
        title: Video başlığı.
        scenes: Sahne listesi.
    """

    title: str
    scenes: list[Scene] = field(default_factory=list)


def _build_system_prompt() -> str:
    """Sistem promptu dosyasını okur ve sahne sayısı sabitleriyle doldurur.

    Returns:
        str: Kullanıma hazır sistem prompt metni.

    Raises:
        FileNotFoundError: Prompt dosyası yoksa.
    """
    template: str = load_text_file(config.SYSTEM_PROMPT_FILE)
    return template.format(min_scenes=config.MIN_SCENES, max_scenes=config.MAX_SCENES)


def _extract_json(raw_text: str) -> dict[str, Any]:
    """LLM çıktısından geçerli bir JSON nesnesi çıkarmaya çalışır.

    LLM bazen JSON'u ```json ... ``` bloğu içinde veya fazladan açıklama ile
    döndürür; bu fonksiyon bunları temizler.

    Args:
        raw_text: LLM'in ham yanıt metni.

    Returns:
        dict: Parse edilmiş JSON sözlüğü.

    Raises:
        ValueError: Hiçbir şekilde JSON çıkarılamıyorsa.
    """
    # 1) Doğrudan parse etmeyi dene
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    # 2) Markdown kod bloğu varsa içeriğini al
    fence_match: re.Match[str] | None = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL
    )
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # 3) Metindeki en dıştaki { ... } kümesini yakala
    brace_match: re.Match[str] | None = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError("LLM yanıtından geçerli JSON çıkarılamadı.")


def _parse_script(data: dict[str, Any]) -> Script:
    """Ham JSON sözlüğünü doğrulayıp Script veri sınıfına dönüştürür.

    Args:
        data: Parse edilmiş JSON sözlüğü.

    Returns:
        Script: Normalize edilmiş senaryo nesnesi.

    Raises:
        ValueError: Zorunlu alanlar eksik veya sahneler geçersizse.
    """
    title: str = str(data.get("title", "İsimsiz Short")).strip()
    raw_scenes: list[dict[str, Any]] = data.get("scenes", [])

    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise ValueError("Senaryoda hiç sahne bulunamadı.")

    scenes: list[Scene] = []
    for item in raw_scenes:
        narration: str = str(item.get("narration", "")).strip()
        visual_prompt: str = str(item.get("visual_prompt", "")).strip()
        if not narration or not visual_prompt:
            log_warning("Eksik alanlı sahne atlandı.")
            continue
        duration: float = coerce_number(item.get("duration_estimate"), 5.0)
        scenes.append(Scene(narration, visual_prompt, duration))

    if not scenes:
        raise ValueError("Hiç geçerli sahne parse edilemedi.")

    # Azami sahne sayısını aşarsa kes (Shorts süre sınırı için)
    if len(scenes) > config.MAX_SCENES:
        log_warning(
            f"Sahne sayısı ({len(scenes)}) sınırı aştı, ilk {config.MAX_SCENES} sahne kullanılıyor."
        )
        scenes = scenes[: config.MAX_SCENES]

    return Script(title=title, scenes=scenes)


def _query_ollama(system_prompt: str, topic: str, style: str) -> str:
    """Ollama chat endpoint'ine tek turluk bir istek atar ve yanıt metnini döner.

    Args:
        system_prompt: Sisteme verilecek rol/kural metni.
        topic: Kullanıcının konu girdisi.
        style: İstenen anlatım tarzı (örn: 'eğitici').

    Returns:
        str: Modelin ham yanıt metni.

    Raises:
        ConnectionError: Ollama sunucusuna ulaşılamıyorsa.
        requests.RequestException: Diğer HTTP hatalarında.
    """
    url: str = config.OLLAMA_BASE_URL.rstrip("/") + config.OLLAMA_CHAT_ENDPOINT
    user_message: str = (
        f"Konu: {topic}\nAnlatım tarzı: {style}\n"
        f"Yalnızca geçerli JSON döndür, başka hiçbir şey yazma."
    )
    payload: dict[str, Any] = {
        "model": config.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "options": {"temperature": config.OLLAMA_TEMPERATURE},
    }

    try:
        response: requests.Response = requests.post(
            url, json=payload, timeout=config.OLLAMA_TIMEOUT_SECONDS
        )
        response.raise_for_status()
    except requests.ConnectionError as exc:
        raise ConnectionError(
            f"Ollama sunucusuna ({config.OLLAMA_BASE_URL}) bağlanılamadı. "
            "Ollama'nın çalıştığından emin olun."
        ) from exc
    except requests.RequestException as exc:
        raise requests.RequestException(f"Ollama isteği başarısız: {exc}") from exc

    body: dict[str, Any] = response.json()
    content: str = body.get("message", {}).get("content", "")
    if not content:
        raise ValueError("Ollama boş yanıt döndürdü.")
    return content


def generate_script(topic: str, style: str = "eğitici") -> Script:
    """Verilen konu ve tarz için Ollama üzerinden senaryo üretir.

    JSON bozuk gelirse config.OLLAMA_MAX_RETRIES kadar yeniden dener.

    Args:
        topic: Videonun konusu / kavramı.
        style: Anlatım tarzı (eğitici, komik, motivasyon vb.).

    Returns:
        Script: Üretilmiş ve normalize edilmiş senaryo.

    Raises:
        ConnectionError: Ollama erişilemiyorsa.
        ValueError: Geçerli senaryo üretilemiyorsa.
    """
    log_info(f"Senaryo üretiliyor (konu: '{topic}', model: {config.OLLAMA_MODEL})...")
    system_prompt: str = _build_system_prompt()

    last_error: Exception | None = None
    for attempt in range(1, config.OLLAMA_MAX_RETRIES + 2):
        try:
            raw: str = _query_ollama(system_prompt, topic, style)
            data: dict[str, Any] = _extract_json(raw)
            script: Script = _parse_script(data)
            log_info(f"{len(script.scenes)} sahnelik senaryo hazır: '{script.title}'")
            return script
        except (ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            log_warning(f"Deneme {attempt} başarısız: {exc}. Yeniden deneniyor...")

    raise ValueError(f"Senaryo üretilemedi: {last_error}")
