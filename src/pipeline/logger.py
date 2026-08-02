"""Structured pipeline logging."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path


class PipelineLogger:
    def __init__(self, logs_dir: Path) -> None:
        logs_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        log_file = logs_dir / f"pipeline_{date_str}.log"

        self.logger = logging.getLogger("rahasya")
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        console_handler = logging.StreamHandler(sys.stdout)
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def start(self, step: str, detail: str = "") -> None:
        msg = f"START | {step}"
        if detail:
            msg += f" | {detail}"
        self.logger.info(msg)

    def ok(self, step: str, detail: str = "") -> None:
        msg = f"OK | {step}"
        if detail:
            msg += f" | {detail}"
        self.logger.info(msg)

    def fail(self, step: str, detail: str = "") -> None:
        msg = f"FAIL | {step}"
        if detail:
            msg += f" | {detail}"
        self.logger.error(msg)

    def warn(self, step: str, detail: str = "") -> None:
        msg = f"WARN | {step}"
        if detail:
            msg += f" | {detail}"
        self.logger.warning(msg)

    def info(self, message: str) -> None:
        self.logger.info(message)
