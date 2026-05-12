"""Magezi — Sunbird AI API integration for Ugandan language speech.

Provides multilingual speech services via Sunbird AI:
- Translation (English ↔ Luganda / Runyankole / Swahili)
- Speech-to-Text (STT) with Ugandan language models
- Text-to-Speech (TTS) with native speaker voices

API docs: https://docs.sunbird.ai
"""

from __future__ import annotations

import io
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("magezi.sunbird")

# ── Config ────────────────────────────────────────────────────────────────

SUNBIRD_API_URL = os.getenv("SUNBIRD_API_URL", "https://api.sunbird.ai")
SUNBIRD_API_TOKEN = os.getenv("SUNBIRD_API_TOKEN", "")
SUNBIRD_TIMEOUT = int(os.getenv("SUNBIRD_TIMEOUT", "30"))

# Magezi locale → Sunbird language code
LOCALE_TO_SUNBIRD: dict[str, str] = {
    "en": "eng",
    "lg": "lug",
    "sw": "swa",
    "nyn": "nyn",
}

# Sunbird TTS speaker IDs (native voices)
TTS_SPEAKERS: dict[str, int] = {
    "lg": 248,    # Luganda female
    "nyn": 243,   # Runyankole female
    "sw": 246,    # Swahili male
    "en": 246,    # fallback
}

TRANSLATION_LANGUAGES = {"eng", "lug", "nyn", "swa"}

# ── Client ────────────────────────────────────────────────────────────────

_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _client
    if _client is None:
        if not SUNBIRD_API_TOKEN:
            raise RuntimeError("SUNBIRD_API_TOKEN not set")
        _client = httpx.Client(
            base_url=SUNBIRD_API_URL,
            headers={"Authorization": f"Bearer {SUNBIRD_API_TOKEN}"},
            timeout=SUNBIRD_TIMEOUT,
        )
    return _client


def is_available() -> bool:
    """Check if Sunbird API is configured."""
    return bool(SUNBIRD_API_TOKEN)


# ── Translation ───────────────────────────────────────────────────────────

def translate(text: str, source_lang: str, target_lang: str) -> str | None:
    """Translate text between English and Luganda."""
    if source_lang not in TRANSLATION_LANGUAGES or target_lang not in TRANSLATION_LANGUAGES:
        return None
    try:
        client = _get_client()
        resp = client.post("/tasks/translate", json={
            "source_language": source_lang,
            "target_language": target_lang,
            "text": text,
        })
        resp.raise_for_status()
        data = resp.json()
        result = data.get("output", {}).get("translated_text") or data.get("translated_text")
        if result:
            logger.info("Translated %s→%s: '%s' → '%s'", source_lang, target_lang,
                        text[:50], result[:50])
        return result
    except Exception as e:
        logger.warning("Sunbird translate failed: %s", e)
        return None


def translate_to_english(text: str, locale: str) -> str | None:
    if locale == "en":
        return None
    src = LOCALE_TO_SUNBIRD.get(locale)
    if not src or src not in TRANSLATION_LANGUAGES:
        return None
    return translate(text, src, "eng")


def translate_from_english(text: str, locale: str) -> str | None:
    if locale == "en":
        return None
    tgt = LOCALE_TO_SUNBIRD.get(locale)
    if not tgt or tgt not in TRANSLATION_LANGUAGES:
        return None
    return translate(text, "eng", tgt)


# ── Speech-to-Text ────────────────────────────────────────────────────────

def speech_to_text(
    audio_bytes: bytes,
    language: str = "eng",
    filename: str = "audio.wav",
) -> dict[str, Any] | None:
    """Transcribe audio via Sunbird API."""
    if not is_available():
        return None
    try:
        client = _get_client()
        files = {"audio": (filename, io.BytesIO(audio_bytes))}
        data: dict[str, Any] = {}
        if language:
            data["language"] = language
        resp = client.post("/tasks/modal/stt", files=files, data=data)
        resp.raise_for_status()
        result = resp.json()
        transcription = (
            result.get("output", {}).get("audio_transcription")
            or result.get("audio_transcription", "")
        )
        logger.info("Sunbird STT (%s): '%s'", language, transcription[:80])
        return {"text": transcription, "language": result.get("language", language)}
    except Exception as e:
        logger.warning("Sunbird STT failed: %s", e)
        return None


# ── Text-to-Speech ────────────────────────────────────────────────────────

def text_to_speech(
    text: str,
    locale: str = "en",
) -> dict[str, Any] | None:
    """Convert text to speech via Sunbird native voices."""
    speaker_id = TTS_SPEAKERS.get(locale)
    if not is_available() or not speaker_id:
        return None
    try:
        client = _get_client()
        resp = client.post("/tasks/modal/tts", json={
            "text": text[:10000],
            "speaker_id": speaker_id,
            "response_mode": "url",
        })
        resp.raise_for_status()
        data = resp.json()
        audio_url = data.get("output", {}).get("audio_url") or data.get("audio_url")
        logger.info("Sunbird TTS (%s): url=%s", locale, (audio_url or "")[:60])
        return {
            "audio_url": audio_url,
            "file_name": data.get("file_name"),
            "expires_at": data.get("expires_at"),
        }
    except Exception as e:
        logger.warning("Sunbird TTS failed: %s", e)
        return None
