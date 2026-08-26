import pytest

from app.services.tock_de_classe import (
    CampaignBrief,
    build_campaign,
    build_script,
)


def test_campaign_uses_vertical_twenty_second_format():
    campaign = build_campaign(
        CampaignBrief(
            product="faixa elástica",
            benefit="ajuda a organizar meu aquecimento",
            context="treino",
        )
    )

    assert campaign["aspect"] == "9:16"
    assert campaign["target_duration_seconds"] == 20
    assert len(campaign["scene_prompts"]) == 2
    assert all("exactly 10 seconds" in prompt for prompt in campaign["scene_prompts"])
    assert all("Brazilian Portuguese only" in prompt for prompt in campaign["scene_prompts"])
    assert all(len(prompt) <= 900 for prompt in campaign["scene_prompts"])


def test_script_includes_product_benefit_and_cta():
    script = build_script(
        CampaignBrief(
            product="corda",
            benefit="entra fácil na preparação antes do jogo",
            cta="Toca no carrinho e confere.",
        )
    )

    assert "corda" in script
    assert "entra fácil" in script
    assert script.endswith("Toca no carrinho e confere.")


@pytest.mark.parametrize("field", ["product", "benefit"])
def test_required_fields(field):
    values = {"product": "corda", "benefit": "facilita minha rotina"}
    values[field] = "   "

    with pytest.raises(ValueError):
        build_campaign(CampaignBrief(**values))
