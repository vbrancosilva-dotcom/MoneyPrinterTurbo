"""Templates for Tock de Classe TikTok Shop affiliate campaigns."""

from dataclasses import asdict, dataclass


DEFAULT_CHARACTER = (
    "the same Brazilian male amateur football player in every shot, 24 to 28 "
    "years old, athletic build, medium-brown skin, short black curly hair, "
    "trimmed beard, wearing a clean blue football training kit"
)


@dataclass(frozen=True)
class CampaignBrief:
    product: str
    benefit: str
    context: str = "treino"
    offer: str = ""
    cta: str = "Toca no carrinho e confere a promoção."

    def normalized(self) -> "CampaignBrief":
        product = " ".join(self.product.split())
        benefit = " ".join(self.benefit.split())
        if not product:
            raise ValueError("Informe o nome do produto.")
        if not benefit:
            raise ValueError("Informe o principal benefício do produto.")
        return CampaignBrief(
            product=product,
            benefit=benefit,
            context=" ".join(self.context.split()) or "treino",
            offer=" ".join(self.offer.split()),
            cta=" ".join(self.cta.split())
            or "Toca no carrinho e confere a promoção.",
        )


def build_script(brief: CampaignBrief) -> str:
    """Build a concise PT-BR affiliate script without medical promises."""
    brief = brief.normalized()
    offer_text = brief.offer.rstrip(".")
    if offer_text:
        offer_text = offer_text[0].upper() + offer_text[1:]
    offer_sentence = f" {offer_text}." if offer_text else ""
    script = (
        f"Jogador, presta atenção nisso aqui. Antes do {brief.context}, eu coloco "
        f"{brief.product} na rotina porque {brief.benefit}. É simples, rápido e "
        f"já virou parte da minha preparação.{offer_sentence} {brief.cta}"
    )
    return script


def split_dialogue(script: str) -> tuple[str, str]:
    """Split the narration into two balanced dialogue blocks."""
    sentences = [part.strip() for part in script.split(". ") if part.strip()]
    sentences = [part if part.endswith(".") else f"{part}." for part in sentences]
    if len(sentences) < 2:
        midpoint = max(1, len(script) // 2)
        return script[:midpoint].strip(), script[midpoint:].strip()

    target = len(script) / 2
    best_index = min(
        range(1, len(sentences)),
        key=lambda index: abs(len(" ".join(sentences[:index])) - target),
    )
    return " ".join(sentences[:best_index]), " ".join(sentences[best_index:])


def build_scene_prompts(brief: CampaignBrief, script: str) -> tuple[str, str]:
    """Create two English generation prompts with spoken PT-BR dialogue."""
    brief = brief.normalized()
    dialogue_one, dialogue_two = split_dialogue(script)
    shared = (
        f"Vertical 9:16, exactly 10 seconds, realistic smartphone video. Show "
        f"{DEFAULT_CHARACTER}. Keep his face, hair, beard, kit and body identical in "
        f"both scenes. Natural Brazilian football setting, dynamic cuts and believable "
        f"product handling. No text, subtitles, added logos or health claims. Match the "
        f"supplied product reference. Dialogue must be Brazilian Portuguese only"
    )
    prompt_one = (
        f"{shared}. Scene 1: inside a locker room before {brief.context}, the player "
        f"looks into the camera, picks up and clearly presents {brief.product}. "
        f"Confident but natural delivery. Dialogue: \"{dialogue_one}\""
    )
    prompt_two = (
        f"{shared}. Scene 2: continue directly from scene 1. The same player naturally "
        f"uses or packs {brief.product}, then walks toward the pitch ready for "
        f"{brief.context}. Finish with the product visible near the camera. "
        f"Dialogue: \"{dialogue_two}\""
    )
    return prompt_one, prompt_two


def build_campaign(brief: CampaignBrief) -> dict:
    """Return the brief, narration and both 10-second prompts."""
    brief = brief.normalized()
    script = build_script(brief)
    prompts = build_scene_prompts(brief, script)
    return {
        "brief": asdict(brief),
        "script": script,
        "scene_prompts": list(prompts),
        "aspect": "9:16",
        "target_duration_seconds": 20,
    }
