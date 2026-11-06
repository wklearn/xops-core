"""Parse and validate XOps PUBLIC_POSTS_V1 candidate documents."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SCHEMA = "PUBLIC_POSTS_V1"
MAX_BYTES = 2 * 1024 * 1024
ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


class ValidationError(ValueError):
    """Untrusted import document failed validation."""


def weighted_length(text: str) -> int:
    """Conservative platform length: ASCII=1, non-ASCII=2."""
    return sum(1 if ord(ch) < 128 else 2 for ch in text)


def load_document(path: str | Path) -> dict[str, Any]:
    data = Path(path).read_bytes()
    if len(data) > MAX_BYTES:
        raise ValidationError("File exceeds 2 MiB input limit")
    try:
        content = data.decode("utf-8-sig").strip()
    except UnicodeDecodeError as exc:
        raise ValidationError("File must be UTF-8") from exc
    if not content.startswith("{"):
        # Support email bodies with exactly one fenced JSON block.
        matches = re.findall(r"```(?:json)?\s*([\s\S]*?)```", content, re.IGNORECASE)
        if len(matches) != 1:
            raise ValidationError("Expected a JSON object or exactly one fenced JSON block")
        content = matches[0].strip()
    try:
        doc = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid JSON: {exc.msg}") from exc
    if not isinstance(doc, dict):
        raise ValidationError("Top-level document must be an object")
    return doc


def _required_text(value: Any, field: str, max_len: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be a nonempty string")
    value = value.strip()
    if len(value) > max_len:
        raise ValidationError(f"{field} exceeds {max_len} characters")
    return value


def _id(value: Any, field: str) -> str:
    text = _required_text(value, field, 120)
    if not ID_RE.fullmatch(text):
        raise ValidationError(f"{field} may only contain letters, digits, _ . : -")
    return text


def _https_url(value: Any) -> str:
    url = _required_text(value, "source_url", 2048)
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise ValidationError("source_url is malformed") from exc
    if parts.scheme.lower() != "https" or not parts.hostname or parts.username or parts.password:
        raise ValidationError("source_url must be a valid HTTPS URL without credentials")
    if any(ch.isspace() or ord(ch) < 32 for ch in url):
        raise ValidationError("source_url contains whitespace/control characters")
    return url


def validate_document(doc: dict[str, Any]) -> list[dict[str, Any]]:
    marker = doc.get("version", doc.get("schema", doc.get("format")))
    if marker != SCHEMA:
        raise ValidationError(f"version/schema/format must be {SCHEMA}")
    raw = doc.get("posts")
    if not isinstance(raw, list) or len(raw) > 100:
        raise ValidationError("posts must be a list containing at most 100 items")
    seen_events: set[tuple[str, str]] = set()
    seen_posts: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValidationError(f"posts[{i}] must be an object")
        try:
            event_id = _id(item.get("event_id"), "event_id")
            post_id = _id(item.get("post_id"), "post_id")
            account = _required_text(item.get("account"), "account", 30)
            lang = _required_text(item.get("lang"), "lang", 12)
            pillar = _required_text(item.get("pillar"), "pillar", 100)
            evidence_stage = _required_text(item.get("evidence_stage"), "evidence_stage", 100)
            priority = _required_text(str(item.get("priority", "normal")), "priority", 30)
            text = _required_text(item.get("text"), "text", 2000)
            alts = item.get("alt_texts")
            if not isinstance(alts, list) or len(alts) != 2:
                raise ValidationError("alt_texts must contain exactly two alternatives")
            alts = [_required_text(t, "alt_texts[]", 2000) for t in alts]
            for j, variant in enumerate([text, *alts]):
                if weighted_length(variant) > 260:
                    raise ValidationError(f"text variant {j} exceeds weighted 260 characters")
            source = item.get("source", {})
            if source is None:
                source = {}
            if not isinstance(source, dict):
                raise ValidationError("source must be an object if supplied")
            source_name = _required_text(item.get("source_name", source.get("name")), "source_name", 300)
            source_tier = _required_text(item.get("source_tier", source.get("tier")), "source_tier", 80)
            source_url = _https_url(item.get("source_url", source.get("url")))
            source_quote = _required_text(item.get("source_quote", source.get("quote")), "source_quote", 2000)
            key_numbers = item.get("key_numbers", [])
            if not isinstance(key_numbers, (list, dict)):
                raise ValidationError("key_numbers must be a list or object")
            if len(json.dumps(key_numbers, ensure_ascii=False)) > 4000:
                raise ValidationError("key_numbers is too large")
            identity = (account, event_id)
            if identity in seen_events:
                raise ValidationError("Only one post per event per account is allowed in a document")
            if post_id in seen_posts:
                raise ValidationError("post_id appears more than once in a document")
            seen_events.add(identity)
            seen_posts.add(post_id)
            record = {
                "event_id": event_id, "post_id": post_id, "account": account,
                "lang": lang, "pillar": pillar, "evidence_stage": evidence_stage,
                "priority": priority, "text": text, "alt_texts": alts,
                "source_name": source_name, "source_tier": source_tier,
                "source_url": source_url, "source_quote": source_quote,
                "key_numbers": key_numbers,
            }
            if "text_zh" in item or "alt_texts_zh" in item:
                translation = _required_text(item.get("text_zh"), "text_zh", 2000)
                translated_alts = item.get("alt_texts_zh")
                if not isinstance(translated_alts, list) or len(translated_alts) != 2:
                    raise ValidationError("alt_texts_zh must contain exactly two alternatives")
                translated_alts = [_required_text(t, "alt_texts_zh[]", 2000) for t in translated_alts]
                for j, variant in enumerate([translation, *translated_alts]):
                    if weighted_length(variant) > 260:
                        raise ValidationError(f"zh text variant {j} exceeds weighted 260 characters")
                record["text_zh"] = translation
                record["alt_texts_zh"] = translated_alts
            if "stage_now" in item:
                record["stage_now"] = _required_text(item["stage_now"], "stage_now", 200)
            if "evergreen" in item:
                if not isinstance(item["evergreen"], bool):
                    raise ValidationError("evergreen must be a boolean")
                record["evergreen"] = item["evergreen"]
            normalized.append(record)
        except ValidationError as exc:
            raise ValidationError(f"posts[{i}]: {exc}") from exc
    return normalized
