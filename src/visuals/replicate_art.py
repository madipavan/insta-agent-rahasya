"""Replicate text-to-image client for fictional novel-scene art."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import requests

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger

FICTION_MARKERS = (
    "fictional illustrated scene",
    "stylized cinematic illustration",
    "thriller book-art",
    "not a real photograph",
)

PHOTO_REALISM_BANNED = (
    "photograph",
    "real life",
    "documentary",
    "stock photo",
)


def build_fiction_prompt(
    keywords: list[str],
    *,
    novel_title: str | None = None,
    style_tag: str = "",
    negative_avoid: str = "",
) -> str:
    """Build a T2I prompt locked to fictional illustrated novel scenes."""
    clean = [
        k.strip()
        for k in keywords
        if isinstance(k, str) and k.strip() and k.lower() not in ("esmodule", "module")
    ]
    # Drop search-style tags that push photoreal stock
    skip = {"cinematic", "artistic", "moody", "noir", "photo", "photograph"}
    # Keep scene/beat/variant salts so multi-still reels stay unique
    salts = [
        k
        for k in clean
        if k.lower().startswith(("scene", "beat", "variant", "shot"))
    ]
    subjects = [k for k in clean if k.lower() not in skip and k not in salts][:6]
    subjects = subjects + salts
    if not subjects:
        subjects = ["mysterious thriller scene", "shadowed corridor", "sealed letter"]

    scene = ", ".join(subjects)
    parts: list[str] = []
    if novel_title and novel_title.strip():
        title = novel_title.strip()
        parts.append(
            f'fictional illustrated scene from the classic novel "{title}", '
            "fictional characters, not a real photograph"
        )
    else:
        parts.append(
            "fictional illustrated scene, fictional characters, not a real photograph"
        )

    parts.append(scene)
    style = (style_tag or "").strip() or (
        "stylized cinematic illustration, teal-blue noir grade, "
        "dramatic shadows, fictional thriller book-art"
    )
    parts.append(style)
    parts.append("painterly stylized thriller book-art, no text, no watermark, no logo")

    avoid = (negative_avoid or "").strip() or (
        "photorealistic, real photo, stock photo, documentary, real person, "
        "celebrity, watermark, text, logo, blurry, low quality"
    )
    parts.append(f"avoid: {avoid}")
    return ", ".join(parts)


def aspect_ratio_for_size(width: int, height: int, default: str = "9:16") -> str:
    if width <= 0 or height <= 0:
        return default
    ratio = height / width
    if ratio >= 1.6:
        return "9:16"
    if ratio >= 1.2:
        return "3:4"
    if ratio >= 0.9:
        return "1:1"
    if ratio >= 0.7:
        return "4:3"
    return "16:9"


class ReplicateArtClient:
    """Generate fictional stills via Replicate (default: flux-schnell)."""

    def __init__(self, config: AppConfig, logger: PipelineLogger, cache_dir: Path) -> None:
        self.config = config
        self.logger = logger
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        art = getattr(config, "replicate_art", None)
        self.enabled = bool(getattr(art, "enabled", False))
        self.model = str(getattr(art, "model", "black-forest-labs/flux-schnell"))
        self.default_aspect = str(getattr(art, "aspect_ratio", "9:16"))
        self.style_tag = str(
            getattr(art, "style_tag", "") or getattr(config, "stock_style_tag", "")
        )
        self.negative_avoid = str(getattr(art, "negative_avoid", ""))
        self.api_token = (getattr(config, "replicate_api_token", "") or "").strip()

    @property
    def available(self) -> bool:
        return self.enabled and bool(self.api_token)

    def generate_photo(
        self,
        keywords: list[str],
        *,
        width: int | None = None,
        height: int | None = None,
        novel_title: str | None = None,
        aspect_ratio: str | None = None,
    ) -> Path | None:
        if not self.available:
            return None

        prompt = build_fiction_prompt(
            keywords,
            novel_title=novel_title,
            style_tag=self.style_tag,
            negative_avoid=self.negative_avoid,
        )
        if width and height:
            ar = aspect_ratio or aspect_ratio_for_size(width, height, self.default_aspect)
        else:
            ar = aspect_ratio or self.default_aspect

        cache_key = hashlib.sha1(f"{self.model}|{ar}|{prompt}".encode("utf-8")).hexdigest()[:20]
        out = self.cache_dir / f"replicate_{cache_key}.png"
        if out.exists() and out.stat().st_size > 0:
            return out

        import time

        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                data = self._run_model(prompt, ar)
                if not data:
                    return None
                out.write_bytes(data)
                self.logger.info(f"Replicate art saved ({self.model}, {ar})")
                return out
            except Exception as exc:  # noqa: BLE001 — soft-fail / retry throttle
                last_exc = exc
                msg = str(exc).lower()
                throttled = "429" in msg or "throttl" in msg or "rate limit" in msg
                if throttled and attempt < 4:
                    wait = 12 + attempt * 3
                    self.logger.warn(
                        "replicate",
                        f"rate limited — waiting {wait}s (attempt {attempt + 1}/5)",
                    )
                    time.sleep(wait)
                    continue
                self.logger.warn("replicate", f"generation failed: {exc}")
                return None
        if last_exc:
            self.logger.warn("replicate", f"generation failed: {last_exc}")
        return None

    def _run_model(self, prompt: str, aspect_ratio: str) -> bytes | None:
        try:
            import replicate
        except ImportError as exc:
            raise RuntimeError("replicate package not installed") from exc

        # Client picks up REPLICATE_API_TOKEN from env; also set explicitly for CI.
        client = replicate.Client(api_token=self.api_token)
        payload: dict[str, Any] = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "num_outputs": 1,
            "output_format": "png",
            "output_quality": 90,
        }
        # go_fast is flux-schnell specific; other FLUX models reject unknown fields
        if "schnell" in self.model.lower():
            payload["go_fast"] = True
        output = client.run(self.model, input=payload)
        return self._extract_image_bytes(output)

    def _extract_image_bytes(self, output: Any) -> bytes | None:
        item = output
        if isinstance(output, (list, tuple)):
            if not output:
                return None
            item = output[0]

        if item is None:
            return None

        # FileOutput / file-like
        read = getattr(item, "read", None)
        if callable(read):
            data = read()
            if isinstance(data, bytes) and data:
                return data

        url = item if isinstance(item, str) else getattr(item, "url", None) or str(item)
        if not url or not str(url).startswith("http"):
            return None
        resp = requests.get(str(url), timeout=120)
        resp.raise_for_status()
        return resp.content


def prompt_looks_fictional(prompt: str) -> bool:
    lower = prompt.lower()
    if any(b in lower for b in PHOTO_REALISM_BANNED if b != "photograph"):
        # "not a real photograph" is allowed; ban unnegated photo wording only loosely
        pass
    has_fiction = any(m in lower for m in FICTION_MARKERS)
    has_avoid = "avoid:" in lower and "photorealistic" in lower
    # Must not ask for a plain photograph as the main intent
    photo_request = bool(re.search(r"\b(photograph|real life|documentary)\b", lower))
    negated = "not a real photograph" in lower
    return has_fiction and has_avoid and (not photo_request or negated)
