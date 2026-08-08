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
    caption_font: str = "assets/fonts/AnekDevanagari-ExtraBold.ttf"
    hindi_quote_font: str = "assets/fonts/NotoSerifDevanagari-Regular.ttf"
    caption_font_size: int = 52
    hook_font_size: int = 58
    caption_outline: int = 4
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
    chars_per_slide: int = 88
    max_slides: int = 10
    quote_font_size_max: int = 44
    quote_font_size_min: int = 30
    hindi_bold: bool = False
    text_stroke_width: int = 1
    max_lines_per_slide: int = 10
    text_area_ratio: float = 0.65


@dataclass
class VideoConfig:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    clip_count: int = 6
    photo_count: int = 2
    artistic_stock: bool = True
    stock_providers: list[str] = field(
        default_factory=lambda: ["local", "pixabay", "pexels"]
    )
    bgm_volume: float = 0.10
    voiceover_volume: float = 1.35
    instagram_max_sec: int = 90
    instagram_max_upload_mb: int = 12
    sfx_enabled: bool = True
    sfx_hook_volume: float = 0.35
    sfx_whoosh_volume: float = 0.22
    sfx_cliffhanger_volume: float = 0.30
    sfx_cliffhanger_before_end_sec: float = 8.0


@dataclass
class PathsConfig:
    data_dir: str = "data"
    db_path: str = "data/rahasya.db"
    output_dir: str = "output"
    logs_dir: str = "logs"
    stock_library: str = "assets/stock_library"
    sfx_library: str = "assets/sfx_library"
    sample_scripts: str = "data/sample_scripts"
    novels_seed: str = "data/novels_seed.json"
    novels_pdf_dir: str = "data/novels"


@dataclass
class AppConfig:
    brand: BrandConfig = field(default_factory=BrandConfig)
    llm_provider: str = "modal"
    llm_fallback_providers: list[str] = field(
        default_factory=lambda: ["gemini", "groq", "mistral"]
    )
    llm_model_modal: str = "Qwen/Qwen3.6-35B-A3B"
    llm_model_anthropic: str = "claude-sonnet-4-20250514"
    llm_model_openai: str = "gpt-4o"
    llm_model_grok: str = "grok-3-mini"
    llm_model_groq: str = "llama-3.3-70b-versatile"
    llm_model_gemini: str = "gemini-2.5-flash"
    llm_model_mistral: str = "mistral-small-latest"
    max_episodes: int = 12
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
    fish_audio_model: str = "s2.1-pro-free"
    fish_audio_voice_id: str = ""
    fish_audio_speed: float = 0.80
    fish_audio_temperature: float = 0.85
    fish_audio_latency: str = "normal"
    fish_audio_sentence_mode: bool = True
    fish_audio_sentence_pause_sec: float = 0.35
    fish_audio_fallback: bool = True
    sarvam_model: str = "bulbul:v3"
    sarvam_speaker: str = "priya"
    sarvam_language_code: str = "hi-IN"
    sarvam_pace: float = 0.78
    sarvam_temperature: float = 0.75
    sarvam_fallback: bool = True
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
    grok_api_key: str = ""
    groq_api_key: str = ""
    gemini_api_key: str = ""
    mistral_api_key: str = ""
    elevenlabs_api_key: str = ""
    fish_audio_api_key: str = ""
    sarvam_api_key: str = ""
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
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
    modal_endpoint_url: str = ""
    modal_api_key: str = ""

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
        llm_provider=raw.get("llm_provider", "modal"),
        llm_fallback_providers=raw.get(
            "llm_fallback_providers", ["gemini", "groq", "mistral"]
        ),
        llm_model_modal=raw.get("llm_model_modal", "Qwen/Qwen3.6-35B-A3B"),
        llm_model_anthropic=raw.get("llm_model_anthropic", "claude-sonnet-4-20250514"),
        llm_model_openai=raw.get("llm_model_openai", "gpt-4o"),
        llm_model_grok=raw.get("llm_model_grok", "grok-3-mini"),
        llm_model_groq=raw.get("llm_model_groq", "llama-3.3-70b-versatile"),
        llm_model_gemini=raw.get("llm_model_gemini", "gemini-2.5-flash"),
        llm_model_mistral=raw.get("llm_model_mistral", "mistral-small-latest"),
        max_episodes=int(raw.get("max_episodes", 12)),
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
        fish_audio_model=raw.get("fish_audio_model", "s2.1-pro-free"),
        fish_audio_voice_id=raw.get("fish_audio_voice_id", ""),
        fish_audio_speed=float(raw.get("fish_audio_speed", 0.80)),
        fish_audio_temperature=float(raw.get("fish_audio_temperature", 0.85)),
        fish_audio_latency=raw.get("fish_audio_latency", "normal"),
        fish_audio_sentence_mode=raw.get("fish_audio_sentence_mode", True),
        fish_audio_sentence_pause_sec=float(raw.get("fish_audio_sentence_pause_sec", 0.35)),
        fish_audio_fallback=raw.get("fish_audio_fallback", True),
        sarvam_model=raw.get("sarvam_model", "bulbul:v3"),
        sarvam_speaker=raw.get("sarvam_speaker", "priya"),
        sarvam_language_code=raw.get("sarvam_language_code", "hi-IN"),
        sarvam_pace=float(raw.get("sarvam_pace", 0.78)),
        sarvam_temperature=float(raw.get("sarvam_temperature", 0.75)),
        sarvam_fallback=raw.get("sarvam_fallback", True),
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
    config.grok_api_key = os.getenv("GROK_API_KEY", "") or os.getenv("XAI_API_KEY", "")
    config.groq_api_key = os.getenv("GROQ_API_KEY", "")
    config.gemini_api_key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    config.mistral_api_key = os.getenv("MISTRAL_API_KEY", "")
    config.elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY", "")
    config.fish_audio_api_key = os.getenv("FISH_AUDIO_API_KEY", "")
    config.sarvam_api_key = os.getenv("SARVAM_API_KEY", "")
    config.pexels_api_key = os.getenv("PEXELS_API_KEY", "")
    config.pixabay_api_key = os.getenv("PIXABAY_API_KEY", "")
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
    config.modal_endpoint_url = os.getenv("MODAL_ENDPOINT_URL", "").strip().rstrip("/")
    config.modal_api_key = os.getenv("MODAL_API_KEY", "").strip()

    return config
