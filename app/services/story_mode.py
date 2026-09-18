"""Local-first helpers for cinematic narrated story videos.

The story workflow intentionally keeps text planning and image generation behind
local HTTP services. Ollama handles adaptation/translation/prompt writing and a
Stable Diffusion WebUI compatible server (Forge/A1111) renders portrait images.
No paid provider is required.
"""

from __future__ import annotations

import base64
import io
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
from PIL import Image


DEFAULT_NEGATIVE_PROMPT = (
    "text, captions, watermark, logo, low quality, blurry, deformed, extra fingers, "
    "duplicate person, cropped face, bad anatomy"
)
DEFAULT_STYLE = (
    "cinematic dark fantasy, photorealistic, dramatic film lighting, detailed faces, "
    "moody atmosphere, vertical composition, consistent character design"
)


@dataclass(frozen=True)
class StoryScene:
    index: int
    source_text: str
    text_pt: str
    text_en: str
    visual_prompt: str
    estimated_seconds: int


class LocalServiceError(RuntimeError):
    """Raised when Ollama or Forge cannot complete a local request."""


def normalize_story(text: str) -> str:
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_oversized_paragraph(paragraph: str, max_chars: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?…])\s+", paragraph.strip())
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
        while len(current) > max_chars:
            split_at = current.rfind(" ", 0, max_chars + 1)
            if split_at < max_chars // 2:
                split_at = max_chars
            chunks.append(current[:split_at].strip())
            current = current[split_at:].strip()
    if current:
        chunks.append(current)
    return chunks


def split_story(text: str, max_chars: int = 430) -> list[str]:
    """Split prose into narration scenes without losing or reordering text."""

    if max_chars < 120:
        raise ValueError("max_chars must be at least 120")
    normalized = normalize_story(text)
    if not normalized:
        return []

    units: list[str] = []
    for paragraph in normalized.split("\n\n"):
        units.extend(_split_oversized_paragraph(paragraph, max_chars))

    scenes: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n\n{unit}".strip()
        if current and len(candidate) > max_chars:
            scenes.append(current)
            current = unit
        else:
            current = candidate
    if current:
        scenes.append(current)
    return scenes


def estimate_narration_seconds(text: str, words_per_minute: int = 145) -> int:
    words = len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))
    if not words:
        return 4
    return max(4, round(words / max(words_per_minute, 60) * 60))


def safe_slug(value: str, fallback: str = "story") -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return (slug or fallback)[:60]


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 300):
        self.base_url = base_url.rstrip("/")
        self.model = model.strip()
        self.timeout = timeout
        if not self.model:
            raise ValueError("Ollama model cannot be empty")

    def check(self) -> None:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LocalServiceError(
                f"Ollama is unavailable at {self.base_url}: {exc}"
            ) from exc

    def generate(self, prompt: str, temperature: float = 0.2) -> str:
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": temperature},
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = str(response.json().get("response") or "").strip()
        except (requests.RequestException, ValueError) as exc:
            raise LocalServiceError(f"Ollama generation failed: {exc}") from exc
        if not result:
            raise LocalServiceError("Ollama returned an empty response")
        return result

    def adapt_for_platform(self, text: str, language: str) -> str:
        language_name = "Brazilian Portuguese" if language == "pt" else "English"
        return self.generate(
            "Rewrite the passage below in "
            f"{language_name} for a narrated social-media story. Preserve every plot "
            "event, character name, suspense beat and dialogue meaning. Remove explicit "
            "sexual detail and replace strong profanity with platform-safe language. "
            "Do not summarize, add commentary, or include a title. Return only prose.\n\n"
            f"PASSAGE:\n{text}"
        )

    def translate(self, text: str, target_language: str) -> str:
        language_name = (
            "natural Brazilian Portuguese" if target_language == "pt" else "natural English"
        )
        return self.generate(
            f"Translate the passage into {language_name}. Preserve names, paragraph breaks, "
            "dialogue, tone and all story events. Do not summarize, explain, censor, or add "
            "a title. Return only the translated prose.\n\nPASSAGE:\n"
            f"{text}"
        )

    def visual_prompt(
        self,
        scene_text: str,
        character_bible: str,
        style: str = DEFAULT_STYLE,
    ) -> str:
        prompt = self.generate(
            "Create one concise English Stable Diffusion prompt for the most visual moment "
            "in this story scene. Describe only visible subjects, exact character traits, "
            "clothing, action, setting, camera shot and lighting. Keep recurring characters "
            "consistent with the character bible. No quotes, text, captions, logos, analysis, "
            "or sexual content. Return only the image prompt.\n\n"
            f"CHARACTER BIBLE:\n{character_bible or 'No character bible supplied.'}\n\n"
            f"SCENE:\n{scene_text}"
        )
        return f"{prompt}, {style}".strip(", ")


class ForgeClient:
    """Client for Forge/AUTOMATIC1111's local Stable Diffusion API."""

    def __init__(self, base_url: str, timeout: float = 600):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def check(self) -> None:
        try:
            response = requests.get(f"{self.base_url}/sdapi/v1/options", timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LocalServiceError(
                f"Stable Diffusion WebUI is unavailable at {self.base_url}: {exc}"
            ) from exc

    def generate_image(
        self,
        prompt: str,
        output_path: str | Path,
        *,
        negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
        width: int = 512,
        height: int = 768,
        steps: int = 20,
        cfg_scale: float = 6.5,
        seed: int = -1,
    ) -> Path:
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg_scale": cfg_scale,
            "sampler_name": "Euler a",
            "seed": seed,
            "batch_size": 1,
            "n_iter": 1,
        }
        try:
            response = requests.post(
                f"{self.base_url}/sdapi/v1/txt2img",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            images = response.json().get("images") or []
            if not images:
                raise ValueError("response did not contain an image")
            encoded = str(images[0]).split(",", 1)[-1]
            image_bytes = base64.b64decode(encoded, validate=True)
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except (requests.RequestException, ValueError, OSError) as exc:
            raise LocalServiceError(f"Stable Diffusion image generation failed: {exc}") from exc

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, format="PNG", optimize=True)
        return path


def build_bilingual_plan(
    story: str,
    *,
    source_language: str,
    ollama: OllamaClient,
    character_bible: str,
    adapt_for_platform: bool = True,
    max_scene_chars: int = 430,
    style: str = DEFAULT_STYLE,
) -> list[StoryScene]:
    """Create aligned PT/EN narration and one shared visual prompt per scene."""

    if source_language not in {"pt", "en"}:
        raise ValueError("source_language must be 'pt' or 'en'")
    source_scenes = split_story(story, max_chars=max_scene_chars)
    if not source_scenes:
        raise ValueError("story cannot be empty")

    result: list[StoryScene] = []
    for index, source_text in enumerate(source_scenes, start=1):
        prepared = (
            ollama.adapt_for_platform(source_text, source_language)
            if adapt_for_platform
            else source_text
        )
        if source_language == "en":
            text_en = prepared
            text_pt = ollama.translate(prepared, "pt")
        else:
            text_pt = prepared
            text_en = ollama.translate(prepared, "en")
        visual_prompt = ollama.visual_prompt(text_en, character_bible, style)
        result.append(
            StoryScene(
                index=index,
                source_text=source_text,
                text_pt=text_pt,
                text_en=text_en,
                visual_prompt=visual_prompt,
                estimated_seconds=max(
                    estimate_narration_seconds(text_pt),
                    estimate_narration_seconds(text_en),
                ),
            )
        )
    return result


def narration_for_language(scenes: Iterable[StoryScene], language: str) -> str:
    if language == "pt":
        return "\n\n".join(scene.text_pt for scene in scenes).strip()
    if language == "en":
        return "\n\n".join(scene.text_en for scene in scenes).strip()
    raise ValueError("language must be 'pt' or 'en'")
