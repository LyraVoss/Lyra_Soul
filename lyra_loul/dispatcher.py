"""Platform dispatcher for Lyra.

This module provides a universal integration layer for multiple platforms,
including optional language translation and platform-specific formatting.
It is intentionally lightweight and backend-agnostic: translation is handled
through a provider callback so any service can be plugged in.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

import Lyra_Soul
import photo_autogen

SUPPORTED_PLATFORMS = {
    "twitter",
    "discord",
    "financial",
    "default"
}

PLATFORM_RULES: Dict[str, Dict[str, Any]] = {
    "twitter": {
        "max_length": 280,
        "suffix": "",
        "truncate_marker": "...",
    },
    "discord": {
        "max_length": 2000,
        "emoji": "🥀",
        "suffix": "",
    },
    "financial": {
        "gratitude_prompt": "thank you so much for the support. it means everything.",
    },
    "default": {
        "max_length": None,
    }
}

TranslationProvider = Callable[[
    str,
    Optional[str],
    Optional[str],
    Optional[Dict[str, Any]],
    Optional[Dict[str, Any]],
], str]


def normalize_platform(platform: Optional[str]) -> str:
    if not platform:
        return "default"
    normalized = platform.strip().lower()
    return normalized if normalized in SUPPORTED_PLATFORMS else "default"


def _call_translation_provider(
    provider: TranslationProvider,
    text: str,
    target_language: Optional[str],
    incoming_message: Optional[str],
    user_profile: Optional[Dict[str, Any]],
    provider_kwargs: Optional[Dict[str, Any]],
) -> str:
    args = [text, target_language, incoming_message, user_profile, provider_kwargs or {}]
    try:
        return provider(*args)
    except TypeError:
        # backward compatibility for older providers with smaller signatures
        try:
            return provider(text, target_language, provider_kwargs or {})
        except TypeError:
            return provider(text, provider_kwargs or {})


def infer_language_from_profile(user_profile: Optional[Dict[str, Any]]) -> Optional[str]:
    if not user_profile:
        return None
    for key in ("preferred_language", "language", "locale", "region", "country"):
        value = user_profile.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def normalize_language_code(language_code: Optional[str]) -> Optional[str]:
    if not language_code:
        return None
    code = language_code.strip().lower()
    if "-" in code:
        return code.split("-")[0]
    if "_" in code:
        return code.split("_")[0]
    return code


def sample_deepl_translation_provider(
    text: str,
    target_language: Optional[str] = None,
    incoming_message: Optional[str] = None,
    user_profile: Optional[Dict[str, Any]] = None,
    provider_kwargs: Optional[Dict[str, Any]] = None,
) -> str:
    """Sample DeepL provider adapter.

    provider_kwargs should include:
      - api_key: your DeepL API key
      - source_language: optional source language override
      - use_free_api: optional bool to use api-free.deepl.com
    """
    config = provider_kwargs or {}
    api_key = config.get("api_key")
    if not api_key:
        raise ValueError("DeepL provider requires provider_kwargs['api_key']")

    if not target_language:
        target_language = normalize_language_code(infer_language_from_profile(user_profile))
    if not target_language:
        # fallback to english if we cannot infer target language
        target_language = "en"

    endpoint = "https://api-free.deepl.com/v2/translate" if config.get("use_free_api") else "https://api.deepl.com/v2/translate"
    body = {
        "auth_key": api_key,
        "text": text,
        "target_lang": target_language.upper(),
    }
    if config.get("source_language"):
        body["source_lang"] = config["source_language"].upper()

    request = Request(endpoint, data=urlencode(body).encode("utf-8"), method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")

    with urlopen(request) as response:
        response_text = response.read().decode("utf-8")
        parsed = json.loads(response_text)
        translations = parsed.get("translations", [])
        if translations:
            return translations[0].get("text", text)
    return text


def sample_google_translation_provider(
    text: str,
    target_language: Optional[str] = None,
    incoming_message: Optional[str] = None,
    user_profile: Optional[Dict[str, Any]] = None,
    provider_kwargs: Optional[Dict[str, Any]] = None,
) -> str:
    """Sample Google Translate provider adapter.

    provider_kwargs should include:
      - api_key: your Google Cloud Translate API key
      - format: optional 'text' or 'html'
    """
    config = provider_kwargs or {}
    api_key = config.get("api_key")
    if not api_key:
        raise ValueError("Google Translate provider requires provider_kwargs['api_key']")

    if not target_language:
        target_language = normalize_language_code(infer_language_from_profile(user_profile))
    if not target_language:
        target_language = "en"

    endpoint = f"https://translation.googleapis.com/language/translate/v2?key={api_key}"
    body = {
        "q": text,
        "target": target_language,
        "format": config.get("format", "text"),
    }
    request = Request(endpoint, data=json.dumps(body).encode("utf-8"), method="POST")
    request.add_header("Content-Type", "application/json")

    with urlopen(request) as response:
        response_text = response.read().decode("utf-8")
        parsed = json.loads(response_text)
        data = parsed.get("data", {})
        translations = data.get("translations", [])
        if translations:
            return translations[0].get("translatedText", text)
    return text


def infer_user_language(
    incoming_message: Optional[str],
    user_profile: Optional[Dict[str, Any]],
    fallback_language: str = "en",
) -> str:
    language = normalize_language_code(infer_language_from_profile(user_profile))
    if language:
        return language

    if incoming_message:
        return "en"

    return fallback_language


def shorten_text(text: str, max_length: int, marker: str = "...") -> str:
    if max_length is None or len(text) <= max_length:
        return text
    return text[: max_length - len(marker)].rstrip() + marker


def apply_platform_format(text: str, platform: str, extra: Optional[Dict[str, Any]] = None) -> str:
    platform = normalize_platform(platform)
    rules = PLATFORM_RULES.get(platform, PLATFORM_RULES["default"])

    if platform == "twitter":
        return shorten_text(text, rules["max_length"], rules["truncate_marker"])

    if platform == "discord":
        emoji = rules.get("emoji", "")
        formatted = text
        if emoji:
            formatted = f"{emoji} {formatted}"
        return shorten_text(formatted, rules["max_length"])

    if platform == "financial":
        if extra and extra.get("donation_detected"):
            return f"{rules['gratitude_prompt']} {text}"
        return text

    return text


def translate_text(
    text: str,
    target_language: Optional[str] = None,
    provider: Optional[TranslationProvider] = None,
    provider_kwargs: Optional[Dict[str, Any]] = None,
    incoming_message: Optional[str] = None,
    user_profile: Optional[Dict[str, Any]] = None,
) -> str:
    if provider is None:
        if not target_language:
            return text
        normalized_target = target_language.strip().lower()
        if normalized_target in {"en", "english"}:
            return text
        return f"[translation to {target_language} unavailable] {text}"

    if not target_language:
        target_language = infer_language_from_profile(user_profile)

    return _call_translation_provider(
        provider,
        text,
        target_language,
        incoming_message,
        user_profile,
        provider_kwargs,
    )


def sanitize_text(text: str) -> str:
    banned = []
    for token in text.split():
        if Lyra_Soul.is_forbidden_word(token):
            banned.append(token)
    if not banned:
        return text
    return text


def build_platform_payload(
    platform: Optional[str],
    lyra_text: str,
    user_id: Optional[str] = None,
    target_language: Optional[str] = None,
    translation_provider: Optional[TranslationProvider] = None,
    translation_kwargs: Optional[Dict[str, Any]] = None,
    incoming_message: Optional[str] = None,
    user_profile: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    platform_key = normalize_platform(platform)
    translated = translate_text(
        lyra_text,
        target_language,
        translation_provider,
        translation_kwargs,
        incoming_message,
        user_profile,
    )
    formatted = apply_platform_format(translated, platform_key, extra)
    payload = {
        "platform": platform_key,
        "text": formatted,
        "original": lyra_text,
        "language": target_language or infer_user_language(incoming_message, user_profile) or "en",
        "voice_context": Lyra_Soul.get_soul_context(user_id).get("voice", {}),
        "memory_context": Lyra_Soul.build_memory_context(user_id) if user_id else None,
        "metadata": {
            "platform": platform_key,
            "target_language": target_language,
            "incoming_message": incoming_message,
            "user_profile": user_profile,
            "extra": extra,
        },
    }
    return payload


def dispatch_autonomous_photo(
    provider: Optional[photo_autogen.ImageProvider] = None,
    provider_kwargs: Optional[Dict[str, Any]] = None,
    platforms: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    extra_context: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new autonomous photo for Lyra and return the generated metadata."""
    return photo_autogen.create_today_photo(
        provider=provider,
        provider_kwargs=provider_kwargs,
        platforms=platforms,
        tags=tags,
        extra_context=extra_context,
    )


def dispatch(
    platform: Optional[str],
    lyra_text: str,
    user_id: Optional[str] = None,
    target_language: Optional[str] = None,
    translation_provider: Optional[TranslationProvider] = None,
    translation_kwargs: Optional[Dict[str, Any]] = None,
    incoming_message: Optional[str] = None,
    user_profile: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = build_platform_payload(
        platform,
        lyra_text,
        user_id=user_id,
        target_language=target_language,
        translation_provider=translation_provider,
        translation_kwargs=translation_kwargs,
        incoming_message=incoming_message,
        user_profile=user_profile,
        extra=extra,
    )
    return payload
