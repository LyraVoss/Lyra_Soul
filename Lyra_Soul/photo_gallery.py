"""Photo metadata database for Lyra.

This module stores generated image metadata in a JSON-backed database, keeps
image style and safety guidelines consistent, and exposes helper functions for
querying and generating realistic prompts.
"""

from pathlib import Path
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

MEDIA_FILE = Path(__file__).with_name("media_gallery.json")

DEFAULT_SAFETY = "SFW — suggestive themes allowed but modest, never overtly adult or indecent."
IMAGE_STYLE_GUIDELINES = [
    "photo-realistic photography with natural lighting and tactile texture.",
    "consistent Lyra appearance: black base hair with burgundy panels, soft eyeliner, band tee or layered alternative style.",
    "no cartoonish filters, no surreal distortion, no obvious AI artifacts.",
    "keep facial proportions realistic and expressions subtle, not exaggerated.",
    "preserve a grounded environment: indoor shop corners, rainy window light, worn velvet, tea cups, guitar details.",
    "honor hair continuity: preserve current length and bangs unless a realistic haircut occurs, and allow only gradual growth if the hair is left uncut.",
    "preserve makeup, attire, and room layout continuity so the same person appears consistent across images.",
    "always enforce SFW image safety unless donor authorization explicitly allows a higher provocative style within their tier."
]

REQUIRED_IMAGE_FIELDS = {
    "filename",
    "description",
    "tags",
    "style",
    "mood",
    "prompt",
    "resolution",
    "model",
    "platforms",
    "safety",
    "created_at",
    "integrity",
}

BANNED_IMAGE_TERMS = {
    "nude",
    "porn",
    "sex",
    "penetration",
    "hardcore",
    "fetish",
    "inappropriate",
    "voyeur",
    "bare breasts",
    "bare butt",
    "nipples",
    "genitals",
}


def _load_raw_gallery() -> Dict[str, Any]:
    if not MEDIA_FILE.exists():
        return {}
    try:
        return json.loads(MEDIA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_raw_gallery(data: Dict[str, Any]) -> None:
    MEDIA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def normalize_image_id(image_id: str) -> str:
    return Path(image_id).stem.lower()


def _normalize_language_code(language_code: Optional[str]) -> Optional[str]:
    if not language_code:
        return None
    cleaned = language_code.strip().lower()
    if "-" in cleaned:
        return cleaned.split("-")[0]
    if "_" in cleaned:
        return cleaned.split("_")[0]
    return cleaned


def _ensure_safe_text(value: str, allow_explicit: bool = False) -> None:
    lowered = value.lower()
    for term in BANNED_IMAGE_TERMS:
        if term == "explicit" and allow_explicit:
            continue
        if term == "sex" and allow_explicit:
            continue
        if term in lowered:
            raise ValueError(f"image metadata contains unsafe term: {term}")


def _hydrate_entry(key: str, value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        return {
            "filename": f"{normalize_image_id(key)}.jpg",
            "description": value,
            "tags": [],
            "style": "photo-realistic, moody, grounded",
            "mood": "neutral",
            "prompt": value,
            "resolution": "1024x1024",
            "model": "stable-diffusion-v2",
            "platforms": [],
            "safety": DEFAULT_SAFETY,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "integrity": "legacy",
        }
    if isinstance(value, dict):
        return value
    raise ValueError("invalid gallery entry")


def load_gallery() -> Dict[str, Dict[str, Any]]:
    raw = _load_raw_gallery()
    gallery: Dict[str, Dict[str, Any]] = {}
    for key, value in raw.items():
        gallery[normalize_image_id(key)] = _hydrate_entry(key, value)
    return gallery


def save_gallery(gallery: Dict[str, Dict[str, Any]]) -> None:
    _save_raw_gallery(gallery)


def validate_image_entry(entry: Dict[str, Any]) -> None:
    missing = REQUIRED_IMAGE_FIELDS - set(entry.keys())
    if missing:
        raise ValueError(f"image entry missing required fields: {', '.join(sorted(missing))}")
    donor_metadata = entry.get("donor_status") or entry.get("donor_metadata") or {}
    allow_explicit = bool(donor_metadata.get("is_donor") and donor_metadata.get("explicit_level"))
    _ensure_safe_text(entry["description"], allow_explicit=allow_explicit)
    _ensure_safe_text(entry["prompt"], allow_explicit=allow_explicit)
    if not isinstance(entry["tags"], list):
        raise ValueError("image entry tags must be a list")


def add_image_entry(
    image_id: str,
    filename: str,
    description: str,
    tags: Optional[List[str]] = None,
    style: Optional[str] = None,
    mood: Optional[str] = None,
    prompt: Optional[str] = None,
    resolution: str = "1024x1024",
    model: str = "stable-diffusion-v2",
    platforms: Optional[List[str]] = None,
    safety: str = DEFAULT_SAFETY,
    created_at: Optional[str] = None,
    integrity: str = "verified",
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    image_id = normalize_image_id(image_id)
    gallery = load_gallery()
    entry = {
        "image_id": image_id,
        "filename": filename,
        "description": description.strip(),
        "tags": tags or [],
        "style": style or "photo-realistic, moody, grounded",
        "mood": mood or "quiet",
        "prompt": prompt or description.strip(),
        "resolution": resolution,
        "model": model,
        "platforms": platforms or [],
        "safety": safety,
        "created_at": created_at or datetime.utcnow().isoformat() + "Z",
        "integrity": integrity,
    }
    if extra_metadata:
        entry.update(extra_metadata)
    validate_image_entry(entry)
    gallery[image_id] = entry
    save_gallery(gallery)
    return entry


def update_image_entry(image_id: str, **updates: Any) -> Dict[str, Any]:
    image_id = normalize_image_id(image_id)
    gallery = load_gallery()
    entry = gallery.get(image_id)
    if not entry:
        raise KeyError(f"image entry not found: {image_id}")
    entry.update(updates)
    validate_image_entry(entry)
    gallery[image_id] = entry
    save_gallery(gallery)
    return entry


def get_image_entry(image_id: str) -> Optional[Dict[str, Any]]:
    return load_gallery().get(normalize_image_id(image_id))


def list_gallery_ids() -> List[str]:
    return list(load_gallery().keys())


def find_images_by_tag(tag: str) -> List[Dict[str, Any]]:
    normalized_tag = tag.strip().lower()
    return [entry for entry in load_gallery().values() if normalized_tag in [t.lower() for t in entry.get("tags", [])]]


def find_images_by_platform(platform: str) -> List[Dict[str, Any]]:
    normalized_platform = platform.strip().lower()
    return [
        entry
        for entry in load_gallery().values()
        if normalized_platform in [p.lower() for p in entry.get("platforms", [])]
    ]


def build_generation_prompt(image_id: str) -> str:
    entry = get_image_entry(image_id)
    if not entry:
        raise KeyError(f"image entry not found: {image_id}")
    style = "; ".join(IMAGE_STYLE_GUIDELINES)
    return (
        f"{entry['prompt']}"
        f" | {style}"
        f" | maintain SFW consistency and photo realism across all platforms."
        f" | preserve Lyra’s visual continuity: alternative clothing, warm moody lighting, subtle emotion, realistic skin tones."
    )


def get_gallery_overview() -> Dict[str, Any]:
    gallery = load_gallery()
    return {
        "count": len(gallery),
        "ids": list(gallery.keys()),
        "style_guidelines": IMAGE_STYLE_GUIDELINES,
        "safety": DEFAULT_SAFETY,
    }
