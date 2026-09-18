import base64
from io import BytesIO
from unittest.mock import Mock

from PIL import Image

from app.services import story_mode


def test_split_story_preserves_content_order():
    text = "First sentence. Second sentence.\n\nThird paragraph is here."

    scenes = story_mode.split_story(text, max_chars=120)

    assert scenes
    assert "First sentence" in scenes[0]
    assert "Third paragraph" in scenes[-1]


def test_safe_slug_removes_accents_and_symbols():
    assert story_mode.safe_slug("Lobisomem: A Caçada!") == "lobisomem-a-cacada"


def test_narration_for_language_uses_aligned_scenes():
    scenes = [
        story_mode.StoryScene(1, "one", "um", "one", "prompt 1", 4),
        story_mode.StoryScene(2, "two", "dois", "two", "prompt 2", 4),
    ]

    assert story_mode.narration_for_language(scenes, "pt") == "um\n\ndois"
    assert story_mode.narration_for_language(scenes, "en") == "one\n\ntwo"


def test_forge_client_saves_decoded_image(tmp_path, monkeypatch):
    buffer = BytesIO()
    Image.new("RGB", (32, 48), "navy").save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"images": [encoded]}
    monkeypatch.setattr(story_mode.requests, "post", Mock(return_value=response))

    output = story_mode.ForgeClient("http://localhost:7860").generate_image(
        "cinematic wolf", tmp_path / "scene.png"
    )

    assert output.exists()
    with Image.open(output) as image:
        assert image.size == (32, 48)


def test_build_bilingual_plan_keeps_one_visual_per_scene():
    ollama = Mock()
    ollama.adapt_for_platform.side_effect = lambda text, language: text
    ollama.translate.side_effect = lambda text, language: f"pt:{text}"
    ollama.visual_prompt.side_effect = lambda text, bible, style: f"image:{text}"

    first = "A wolf entered the abandoned store while broken glass moved underfoot."
    second = "The hunter followed quietly and searched every dark aisle behind the counter."
    scenes = story_mode.build_bilingual_plan(
        f"{first}\n\n{second}",
        source_language="en",
        ollama=ollama,
        character_bible="The wolf has silver hair.",
        max_scene_chars=120,
    )

    assert len(scenes) == 2
    assert scenes[0].text_en == first
    assert scenes[0].text_pt == f"pt:{first}"
    assert scenes[1].visual_prompt.startswith("image:")
