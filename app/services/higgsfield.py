"""Higgsfield text-to-video material provider.

The public ``higgsfield-ai/higgsfield`` repository is a GPU training
orchestrator and is not the video-generation product.  This adapter uses the
official Higgsfield API client so MoneyPrinterTurbo can keep its existing
script, voice, subtitle, and editing pipeline while Higgsfield creates the
visual clips.
"""

from __future__ import annotations

import time
from typing import List

from loguru import logger
import requests

from app.config import config
from app.models.schema import MaterialInfo, VideoAspect


DEFAULT_MODEL = "bytedance/seedance-2.0/text-to-video"
API_BASE_URL = "https://api.higgsfield.ai"
DEFAULT_RESOLUTION = "720p"
DEFAULT_TIMEOUT_SECONDS = 90.0
DEFAULT_RUN_TIMEOUT_SECONDS = 900.0
POLL_INTERVAL_SECONDS = 2.0
DEFAULT_MIN_DURATION_SECONDS = 4
DEFAULT_MAX_DURATION_SECONDS = 15


class HiggsfieldUnconfirmedTaskError(RuntimeError):
    """A paid request may exist remotely, but its final state is unknown."""

    def __init__(self, message: str, request_id: str = ""):
        super().__init__(message)
        self.request_id = request_id


def _get_api_key() -> str:
    values = config.app.get("higgsfield_api_keys", [])
    if isinstance(values, str):
        values = [values]
    values = [str(value).strip() for value in values if str(value).strip()]
    if not values:
        raise ValueError("Higgsfield API credentials are not configured")
    # The official SDK accepts the combined ``key-id:key-secret`` value.
    return values[0]


def _duration_bounds() -> tuple[int, int]:
    def read(key: str, default: int) -> int:
        try:
            value = int(config.app.get(key, default))
        except (TypeError, ValueError):
            return default
        return value if value > 0 else default

    minimum = read("higgsfield_min_duration", DEFAULT_MIN_DURATION_SECONDS)
    maximum = read("higgsfield_max_duration", DEFAULT_MAX_DURATION_SECONDS)
    return minimum, max(minimum, maximum)


def generate_videos(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    """Generate one clip and return it in MoneyPrinterTurbo's material shape."""

    aspect = VideoAspect(video_aspect)
    width, height = aspect.to_resolution()
    min_duration, max_duration = _duration_bounds()
    requested_duration = max(int(minimum_duration), 1)
    duration = min(max(requested_duration, min_duration), max_duration)
    model = str(config.app.get("higgsfield_text_to_video_model", DEFAULT_MODEL)).strip()
    resolution = str(
        config.app.get("higgsfield_video_resolution", DEFAULT_RESOLUTION)
    ).strip()
    timeout = float(
        config.app.get("higgsfield_request_timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    )

    arguments = {
        "prompt": search_term,
        "resolution": resolution,
        "generate_audio": False,
        "duration": duration,
        "aspect_ratio": aspect.value,
    }
    request_id = ""
    api_key = _get_api_key()
    headers = {
        "Authorization": f"Key {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "moneyprinterturbo-higgsfield/1.0",
    }
    logger.info(
        "generating Higgsfield video: "
        f"model={model}, term={search_term!r}, duration={duration}s, "
        f"aspect={aspect.value}"
    )

    try:
        response = requests.post(
            f"{API_BASE_URL}/{model}",
            json=arguments,
            headers=headers,
            proxies=config.proxy,
            verify=bool(config.app.get("tls_verify", True)),
            timeout=(30, timeout),
        )
        response.raise_for_status()
        submission = response.json()
        request_id = str(submission.get("request_id") or "")
        status_url = str(submission.get("status_url") or "")
        if not request_id or not status_url:
            raise ValueError(
                "Higgsfield submission did not return request tracking data"
            )
        # Persist the only stable remote reference in logs immediately. If
        # polling later fails, the user can still recover the paid generation.
        logger.info(f"Higgsfield request created: id={request_id}")
        result = _wait_for_result(
            status_url=status_url,
            headers=headers,
            timeout=timeout,
        )
    except (requests.RequestException, OSError, TimeoutError, ValueError) as exc:
        raise HiggsfieldUnconfirmedTaskError(
            "Higgsfield request state could not be confirmed; do not resubmit "
            f"automatically: {type(exc).__name__}: {exc}",
            request_id=request_id,
        ) from exc

    if not isinstance(result, dict):
        raise HiggsfieldUnconfirmedTaskError(
            "Higgsfield returned an unreadable result",
            request_id=request_id,
        )

    status = str(result.get("status") or "").lower()
    if status and status != "completed":
        logger.error(
            f"Higgsfield generation did not complete: id={request_id}, status={status}"
        )
        return []

    video = result.get("video")
    video_url = video.get("url") if isinstance(video, dict) else ""
    if not isinstance(video_url, str) or not video_url.startswith(
        ("http://", "https://")
    ):
        logger.error(
            f"Higgsfield completed without a downloadable video: id={request_id}"
        )
        return []

    return [
        MaterialInfo(
            provider="higgsfield",
            url=video_url,
            duration=duration,
            source_info={
                "provider": "higgsfield",
                "search_term": search_term,
                "asset_id": request_id,
                "rendition": {
                    "id": model,
                    "width": width,
                    "height": height,
                },
            },
        )
    ]


def _wait_for_result(*, status_url: str, headers: dict, timeout: float) -> dict:
    """Poll one accepted request; never submit a replacement automatically."""
    run_timeout = float(
        config.app.get("higgsfield_run_timeout_seconds", DEFAULT_RUN_TIMEOUT_SECONDS)
    )
    deadline = time.monotonic() + run_timeout
    while True:
        response = requests.get(
            status_url,
            headers=headers,
            proxies=config.proxy,
            verify=bool(config.app.get("tls_verify", True)),
            timeout=(30, timeout),
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("Higgsfield returned an unreadable status response")
        status = str(result.get("status") or "").lower()
        if status in {"completed", "failed", "nsfw", "canceled"}:
            return result
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Higgsfield request is still {status or 'pending'} after "
                f"{run_timeout:.0f}s"
            )
        time.sleep(POLL_INTERVAL_SECONDS)
