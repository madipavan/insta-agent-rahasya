"""Telegram notification and approval bot."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import requests

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger


class TelegramNotifier:
    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        self.base_url = (
            f"https://api.telegram.org/bot{config.telegram_bot_token}"
            if config.telegram_bot_token
            else ""
        )

    def send_review_notification(
        self,
        bundle_id: str,
        caption: str,
        script_preview: str,
        bundle_dir: Path,
    ) -> None:
        if not self._configured():
            self.logger.warn("telegram", "not configured — skipping notification")
            return

        text = (
            f"📚 *Rahasya.exe — Review Required*\n\n"
            f"Bundle: `{bundle_id}`\n\n"
            f"*Script preview:*\n{script_preview[:500]}\n\n"
            f"*Caption:*\n{caption[:300]}\n\n"
            f"Approve: `python main.py approve {bundle_id}`\n"
            f"Reject: `python main.py reject {bundle_id}`"
        )
        self._send_message(text)

        reel = bundle_dir / "reel.mp4"
        if reel.exists() and reel.stat().st_size < 45 * 1024 * 1024:
            self._send_video(reel)

        static_slides = sorted(bundle_dir.glob("static_post_*.png"))
        if not static_slides:
            legacy = bundle_dir / "static_post.png"
            if legacy.exists():
                static_slides = [legacy]
        for slide in static_slides[:10]:
            self._send_photo(slide)
        if len(static_slides) > 10:
            self._send_message(f"…and {len(static_slides) - 10} more slides in bundle folder")

    def send_info(self, message: str) -> None:
        if self._configured():
            self._send_message(message)

    def send_error(self, message: str) -> None:
        if self._configured():
            self._send_message(f"❌ *Pipeline Error*\n{message}")

    def _configured(self) -> bool:
        return bool(self.config.telegram_bot_token and self.config.telegram_chat_id)

    def _send_message(self, text: str) -> None:
        try:
            requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": self.config.telegram_chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            self.logger.warn("telegram", f"send failed: {exc}")

    def _send_video(self, path: Path) -> None:
        try:
            with open(path, "rb") as f:
                requests.post(
                    f"{self.base_url}/sendVideo",
                    data={"chat_id": self.config.telegram_chat_id},
                    files={"video": f},
                    timeout=120,
                )
        except requests.RequestException as exc:
            self.logger.warn("telegram", f"video send failed: {exc}")

    def _send_photo(self, path: Path) -> None:
        try:
            with open(path, "rb") as f:
                requests.post(
                    f"{self.base_url}/sendPhoto",
                    data={"chat_id": self.config.telegram_chat_id},
                    files={"photo": f},
                    timeout=60,
                )
        except requests.RequestException as exc:
            self.logger.warn("telegram", f"photo send failed: {exc}")


class TelegramBot:
    """Long-polling bot for approve/reject commands."""

    def __init__(
        self,
        config: AppConfig,
        logger: PipelineLogger,
        on_approve: Callable[[str], None],
        on_reject: Callable[[str, str], None],
    ) -> None:
        self.config = config
        self.logger = logger
        self.on_approve = on_approve
        self.on_reject = on_reject
        self.base_url = f"https://api.telegram.org/bot{config.telegram_bot_token}"
        self.last_update_id: Optional[int] = None

    def poll(self) -> None:
        if not self.config.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set")

        self.logger.info("Telegram bot polling started")
        while True:
            try:
                params = {"timeout": 30}
                if self.last_update_id:
                    params["offset"] = self.last_update_id + 1
                resp = requests.get(f"{self.base_url}/getUpdates", params=params, timeout=35)
                resp.raise_for_status()
                for update in resp.json().get("result", []):
                    self.last_update_id = update["update_id"]
                    self._handle_update(update)
            except KeyboardInterrupt:
                break
            except requests.RequestException as exc:
                self.logger.warn("telegram_bot", f"poll error: {exc}")

    def _handle_update(self, update: dict) -> None:
        message = update.get("message", {})
        text = (message.get("text") or "").strip()
        if not text:
            return

        if text.startswith("/approve "):
            bundle_id = text.split(" ", 1)[1].strip()
            self.on_approve(bundle_id)
        elif text.startswith("/reject "):
            parts = text.split(" ", 2)
            bundle_id = parts[1].strip()
            reason = parts[2].strip() if len(parts) > 2 else ""
            self.on_reject(bundle_id, reason)
