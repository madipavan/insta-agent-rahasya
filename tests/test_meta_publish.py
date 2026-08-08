"""Tests for Meta publish rate-limit handling and partial success."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.scheduler.meta import MetaPostResult, MetaScheduler


def _scheduler() -> MetaScheduler:
    config = AppConfig()
    logger = PipelineLogger(config.path("logs_dir"))
    return MetaScheduler(config, logger)


def test_meta_post_result_summary_includes_carousel_failure():
    result = MetaPostResult(
        reel_container_id="111",
        reel_publish_id="222",
        carousel_container_id="333",
        carousel_publish_id=None,
        scheduled_reel_at="2026-08-08T19:30:00",
        scheduled_carousel_at="2026-08-08T19:35:00",
        carousel_error="rate_limit",
    )
    summary = result.summary()
    assert "reel_pub:222" in summary
    assert "carousel_failed:rate_limit" in summary
    assert result.reel_posted is True


def test_is_rate_limited_detects_meta_error_payload():
    meta = _scheduler()
    resp = MagicMock(spec=requests.Response)
    resp.status_code = 403
    resp.json.return_value = {
        "error": {
            "message": "Application request limit reached",
            "type": "OAuthException",
            "code": 4,
            "error_subcode": 2207051,
        }
    }
    assert meta._is_rate_limited(resp) is True


def test_is_rate_limited_ignores_other_errors():
    meta = _scheduler()
    resp = MagicMock(spec=requests.Response)
    resp.status_code = 400
    resp.json.return_value = {
        "error": {
            "message": "Invalid parameter",
            "code": 100,
        }
    }
    assert meta._is_rate_limited(resp) is False


def test_classify_publish_error_rate_limit():
    meta = _scheduler()
    assert meta._classify_publish_error(
        requests.HTTPError("403 Client Error: Forbidden ... request limit reached")
    ) == "rate_limit"


@patch("src.scheduler.meta.time.sleep")
@patch("src.scheduler.meta.requests.post")
def test_media_publish_with_retry_recovers_after_rate_limit(mock_post, mock_sleep):
    meta = _scheduler()
    rate_limited = MagicMock(spec=requests.Response)
    rate_limited.status_code = 403
    rate_limited.json.return_value = {
        "error": {
            "message": "Application request limit reached",
            "code": 4,
            "error_subcode": 2207051,
        }
    }

    ok = MagicMock(spec=requests.Response)
    ok.status_code = 200
    ok.json.return_value = {"id": "published_123"}

    mock_post.return_value = ok
    publish_id = meta._media_publish_with_retry(rate_limited, "container_1")
    assert publish_id == "published_123"
    mock_sleep.assert_called_once_with(30)
    mock_post.assert_called_once()


@patch("src.scheduler.meta.time.sleep")
@patch("src.scheduler.meta.requests.post")
def test_media_publish_with_retry_raises_after_exhausted_retries(mock_post, mock_sleep):
    meta = _scheduler()
    rate_limited = MagicMock(spec=requests.Response)
    rate_limited.status_code = 403
    rate_limited.json.return_value = {
        "error": {
            "message": "Application request limit reached",
            "code": 4,
            "error_subcode": 2207051,
        }
    }
    rate_limited.text = "rate limited"
    rate_limited.raise_for_status.side_effect = requests.HTTPError("403")
    mock_post.return_value = rate_limited

    with pytest.raises(requests.HTTPError):
        meta._media_publish_with_retry(rate_limited, "container_1")

    assert mock_sleep.call_count == meta.RATE_LIMIT_RETRY_ATTEMPTS - 1
