"""Configuration loader for environment variables and config.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass
class BrandConfig:
    bg_color: str = "#0A0E1A"
    accent_color: str = "#C41E3A"
    text_color: str = "#F5F5F5"
    display_font: str = "assets/fonts/BebasNeue-Regular.ttf"
    body_font: str = "assets/fonts/Inter-Regular.ttf"
    quote_font: str = "C:/Windows/Fonts/georgiab.ttf"
    watermark_text: str = "Rahasya.exe"
    logo_path: str = "assets/brand/logo.png"
    intro_duration_sec: float = 1.0
    outro_duration_sec: float = 1.0


@dataclass
class DiscoveryConfig:
    min_queue_size: int = 3
    batch_size: int = 5


@dataclass
class StaticPostConfig:
    width: int = 1080
    height: int = 1350
    layout_rotation: str = "quote"
    chars_per_slide: int = 100
    max_slides: int = 10


@dataclass
class VideoConfig:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    clip_count: int = 6
    photo_count: int = 2
    artistic_stock: bool = True
    bgm_volume: float = 0.22


@dataclass
class PathsConfig:
    data_dir: str = "data"
    db_path: str = "data/rahasya.db"
    output_dir: str = "output"
    logs_dir: str = "logs"
    stock_library: str = "assets/stock_library"
    sample_scripts: str = "data/sample_scripts"
    novels_seed: str = "data/novels_seed.json"


@dataclass
class AppConfig:
    brand: BrandConfig = field(default_factory=BrandConfig)
    llm_provider: str = "groq"
    llm_fallback_providers: list[str] = field(default_factory=lambda: ["groq", "mistral", "gemini"])
    llm_model_anthropic: str = "claude-sonnet-4-20250514"
    llm_model_openai: str = "gpt-4o"
    llm_model_groq: str = "llama-3.3-70b-versatile"
    llm_model_gemini: str = "gemini-2.5-flash"
    llm_model_mistral: str = "mistral-small-latest"
    post_time: str = "19:30"
    timezone: str = "Asia/Kolkata"
    voice_provider: str = "elevenlabs"
    voice_id: str = ""
    voice_name: str = "Tarini"
    voice_language: str = "hindi"
    edge_tts_voice: str = "hi-IN-SwaraNeural"
    edge_tts_rate: str = "-8%"
    edge_tts_pitch: str = "-2Hz"
    elevenlabs_fallback: bool = True
    script_min_seconds: int = 75
    script_max_seconds: int = 80
    cta: str = "Follow for the next part 👀"
    hashtags: str = "#thrillerbooks #suspensenovel #bookstagram"
    review_required: bool = True
    auto_publish: bool = False
    min_publish_delay_hours: int = 20
    caption_template: str = ""
    post_provider: str = "meta"
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    static_post: StaticPostConfig = field(default_factory=StaticPostConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    groq_api_key: str = ""
    gemini_api_key: str = ""
    mistral_api_key: str = ""
    elevenlabs_api_key: str = ""
    pexels_api_key: str = ""
    metricool_api_key: str = ""
    metricool_user_id: str = ""
    meta_access_token: str = ""
    meta_ig_user_id: str = ""
    meta_page_id: str = ""
    meta_app_id: str = ""
    meta_app_secret: str = ""
    tmdb_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    def path(self, key: str) -> Path:
        value = getattr(self.paths, key)
        return ROOT_DIR / value

    def resolve_asset(self, relative: str) -> Path:
        return ROOT_DIR / relative


def _merge_dataclass(cls: type, data: dict[str, Any]) -> Any:
    instance = cls()
    for key, value in data.items():
        if hasattr(instance, key):
            setattr(instance, key, value)
    return instance


def load_config(config_path: Path | None = None) -> AppConfig:
    load_dotenv(ROOT_DIR / ".env")
    path = config_path or ROOT_DIR / "config.yaml"
    raw: dict[str, Any] = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    config = AppConfig(
        brand=_merge_dataclass(BrandConfig, raw.get("brand", {})),
        llm_provider=raw.get("llm_provider", "groq"),
        llm_fallback_providers=raw.get(
            "llm_fallback_providers", ["groq", "mistral", "gemini"]
        ),
        llm_model_anthropic=raw.get("llm_model_anthropic", "claude-sonnet-4-20250514"),
        llm_model_openai=raw.get("llm_model_openai", "gpt-4o"),
        llm_model_groq=raw.get("llm_model_groq", "llama-3.3-70b-versatile"),
        llm_model_gemini=raw.get("llm_model_gemini", "gemini-2.5-flash"),
        llm_model_mistral=raw.get("llm_model_mistral", "mistral-small-latest"),
        post_time=raw.get("post_time", "19:30"),
        timezone=raw.get("timezone", "Asia/Kolkata"),
        voice_provider=raw.get("voice_provider", "elevenlabs"),
        voice_id=raw.get("voice_id", ""),
        voice_name=raw.get("voice_name", "Tarini"),
        voice_language=raw.get("voice_language", "hindi"),
        edge_tts_voice=raw.get("edge_tts_voice", "hi-IN-SwaraNeural"),
        edge_tts_rate=raw.get("edge_tts_rate", "-8%"),
        edge_tts_pitch=raw.get("edge_tts_pitch", "-2Hz"),
        elevenlabs_fallback=raw.get("elevenlabs_fallback", True),
        script_min_seconds=raw.get("script_min_seconds", 75),
        script_max_seconds=raw.get("script_max_seconds", 80),
        cta=raw.get("cta", "Follow for the next part 👀"),
        hashtags=raw.get("hashtags", "#thrillerbooks"),
        review_required=raw.get("review_required", True),
        auto_publish=raw.get("auto_publish", False),
        min_publish_delay_hours=int(raw.get("min_publish_delay_hours", 20)),
        caption_template=raw.get("caption_template", ""),
        post_provider=raw.get("post_provider", "meta"),
        discovery=_merge_dataclass(DiscoveryConfig, raw.get("discovery", {})),
        static_post=_merge_dataclass(StaticPostConfig, raw.get("static_post", {})),
        video=_merge_dataclass(VideoConfig, raw.get("video", {})),
        paths=_merge_dataclass(PathsConfig, raw.get("paths", {})),
    )

    config.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
    config.openai_api_key = os.getenv("OPENAI_API_KEY", "")
    config.groq_api_key = os.getenv("GROQ_API_KEY", "")
    config.gemini_api_key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    config.mistral_api_key = os.getenv("MISTRAL_API_KEY", "")
    config.elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY", "")
    config.pexels_api_key = os.getenv("PEXELS_API_KEY", "")
    config.metricool_api_key = os.getenv("METRICOOL_API_KEY", "")
    config.metricool_user_id = os.getenv("METRICOOL_USER_ID", "")
    config.meta_access_token = os.getenv("META_ACCESS_TOKEN", "").strip()
    config.meta_ig_user_id = os.getenv("META_IG_USER_ID", "").strip()
    config.meta_page_id = os.getenv("META_PAGE_ID", "").strip()
    config.meta_app_id = os.getenv("META_APP_ID", "")
    config.meta_app_secret = os.getenv("META_APP_SECRET", "")
    config.tmdb_api_key = os.getenv("TMDB_API_KEY", "")
    config.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    config.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    return config
