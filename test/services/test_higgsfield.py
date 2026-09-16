from unittest.mock import Mock, patch

import pytest

from app.config import config
from app.models.schema import VideoAspect
from app.services import higgsfield


@pytest.fixture(autouse=True)
def restore_config():
    original = dict(config.app)
    config.app["higgsfield_api_keys"] = ["key-id:key-secret"]
    yield
    config.app.clear()
    config.app.update(original)


def response(payload):
    result = Mock()
    result.json.return_value = payload
    result.raise_for_status.return_value = None
    return result


@patch("app.services.higgsfield.requests.get")
@patch("app.services.higgsfield.requests.post")
def test_generate_video_submits_polls_and_returns_material(post, get):
    post.return_value = response(
        {
            "status": "queued",
            "request_id": "request-123",
            "status_url": "https://api.higgsfield.ai/requests/request-123/status",
        }
    )
    get.return_value = response(
        {
            "status": "completed",
            "video": {"url": "https://cdn.example/video.mp4"},
        }
    )

    result = higgsfield.generate_videos(
        "a football player entering the stadium",
        minimum_duration=5,
        video_aspect=VideoAspect.portrait,
    )

    assert len(result) == 1
    assert result[0].provider == "higgsfield"
    assert result[0].source_info["asset_id"] == "request-123"
    assert post.call_args.args[0].endswith("/bytedance/seedance-2.0/text-to-video")
    assert post.call_args.kwargs["json"] == {
        "prompt": "a football player entering the stadium",
        "resolution": "720p",
        "generate_audio": False,
        "duration": 5,
        "aspect_ratio": "9:16",
    }


@patch("app.services.higgsfield.requests.get")
@patch("app.services.higgsfield.requests.post")
def test_generate_video_returns_empty_for_terminal_failure(post, get):
    post.return_value = response(
        {
            "request_id": "request-failed",
            "status_url": "https://api.higgsfield.ai/requests/request-failed/status",
        }
    )
    get.return_value = response({"status": "failed", "error": "model error"})

    result = higgsfield.generate_videos(
        "sunrise",
        minimum_duration=5,
    )

    assert result == []


@patch("app.services.higgsfield.requests.get")
@patch("app.services.higgsfield.requests.post")
def test_generate_video_preserves_request_id_when_polling_is_unconfirmed(post, get):
    post.return_value = response(
        {
            "request_id": "request-unknown",
            "status_url": "https://api.higgsfield.ai/requests/request-unknown/status",
        }
    )
    get.side_effect = higgsfield.requests.Timeout("timeout")

    with pytest.raises(higgsfield.HiggsfieldUnconfirmedTaskError) as caught:
        higgsfield.generate_videos(
            "sunrise",
            minimum_duration=5,
        )

    assert caught.value.request_id == "request-unknown"
