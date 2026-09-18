"""Streamlit entrypoint for local cinematic story videos."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from uuid import uuid4

import streamlit as st


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.models.schema import MaterialInfo, VideoAspect, VideoConcatMode, VideoParams
from app.services import story_mode
from app.services import task as task_service
from app.utils import utils


st.set_page_config(
    page_title="MoneyPrinterTurbo - Modo Historia",
    page_icon="🎬",
    layout="wide",
)

st.title("🎬 Modo História Cinematográfica")
st.caption(
    "Crie versões completas em português e inglês com Ollama, Stable Diffusion local, "
    "Edge TTS, legendas e montagem vertical."
)

with st.sidebar:
    st.header("Serviços locais")
    ollama_url = st.text_input("Ollama", value="http://127.0.0.1:11434")
    ollama_model = st.text_input("Modelo", value="qwen2.5:3b")
    forge_url = st.text_input("Stable Diffusion Forge", value="http://127.0.0.1:7860")
    st.caption("Inicie o Forge com --api --lowvram para placas de até 4 GB.")

    if st.button("Testar conexões", use_container_width=True):
        checks = []
        try:
            story_mode.OllamaClient(ollama_url, ollama_model).check()
            checks.append("✅ Ollama conectado")
        except story_mode.LocalServiceError as exc:
            checks.append(f"❌ {exc}")
        try:
            story_mode.ForgeClient(forge_url).check()
            checks.append("✅ Stable Diffusion conectado")
        except story_mode.LocalServiceError as exc:
            checks.append(f"❌ {exc}")
        for check in checks:
            st.write(check)

left, right = st.columns([3, 2])
with left:
    title = st.text_input("Título", placeholder="Ex.: O último lobisomem")
    source_language_label = st.radio(
        "Idioma do texto original",
        options=["Inglês", "Português"],
        horizontal=True,
    )
    story = st.text_area(
        "História completa",
        height=430,
        placeholder="Cole aqui uma história que você escreveu ou tem permissão para usar...",
    )

with right:
    character_bible = st.text_area(
        "Ficha visual dos personagens",
        height=220,
        placeholder=(
            "Ash: homem adulto, cabelo curto grisalho, jaqueta tática preta...\n"
            "Viper: homem adulto muito alto, cabelo ruivo, olhos verdes..."
        ),
        help="Repita os mesmos detalhes físicos e roupas para aumentar a consistência.",
    )
    style = st.text_area(
        "Estilo visual",
        value=story_mode.DEFAULT_STYLE,
        height=110,
    )
    negative_prompt = st.text_area(
        "Evitar nas imagens",
        value=story_mode.DEFAULT_NEGATIVE_PROMPT,
        height=90,
    )

with st.expander("Configurações de geração", expanded=False):
    settings_col1, settings_col2, settings_col3 = st.columns(3)
    with settings_col1:
        scene_chars = st.slider("Tamanho de cada cena", 220, 650, 430, 10)
        steps = st.slider("Passos da imagem", 12, 30, 20)
    with settings_col2:
        pt_voice = st.selectbox(
            "Voz em português",
            ["pt-BR-AntonioNeural-Male", "pt-BR-FranciscaNeural-Female"],
        )
        en_voice = st.selectbox(
            "Voz em inglês",
            ["en-US-GuyNeural-Male", "en-US-JennyNeural-Female"],
        )
    with settings_col3:
        voice_rate = st.slider("Velocidade da voz", 0.80, 1.25, 1.00, 0.05)
        seed = st.number_input("Seed base", value=20260918, step=1)

adapt_for_platform = st.checkbox(
    "Adaptar para publicação (reduzir palavrões e conteúdo sexual explícito)", value=True
)
rights_confirmed = st.checkbox(
    "Confirmo que escrevi a história ou tenho autorização para reutilizá-la"
)


def _render_result(language: str, result: dict) -> None:
    label = "Português" if language == "pt" else "Inglês"
    videos = list(result.get("videos") or []) if isinstance(result, dict) else []
    if not videos:
        st.error(f"A versão em {label} não gerou um arquivo de vídeo.")
        return
    video_path = videos[0]
    st.subheader(f"Versão em {label}")
    st.video(video_path)
    with open(video_path, "rb") as video_file:
        st.download_button(
            f"Baixar vídeo em {label}",
            data=video_file.read(),
            file_name=Path(video_path).name,
            mime="video/mp4",
            key=f"download-{language}",
        )


if st.button("Gerar história em português e inglês", type="primary", use_container_width=True):
    if not title.strip():
        st.error("Informe um título.")
        st.stop()
    if not story_mode.normalize_story(story):
        st.error("Cole a história completa.")
        st.stop()
    if not rights_confirmed:
        st.error("Confirme que você tem autorização para reutilizar a história.")
        st.stop()

    ollama = story_mode.OllamaClient(ollama_url, ollama_model)
    forge = story_mode.ForgeClient(forge_url)
    try:
        ollama.check()
        forge.check()
    except story_mode.LocalServiceError as exc:
        st.error(str(exc))
        st.stop()

    source_language = "en" if source_language_label == "Inglês" else "pt"
    progress = st.progress(0, text="Preparando cenas...")
    try:
        scenes = story_mode.build_bilingual_plan(
            story,
            source_language=source_language,
            ollama=ollama,
            character_bible=character_bible,
            adapt_for_platform=adapt_for_platform,
            max_scene_chars=scene_chars,
            style=style,
        )
    except (story_mode.LocalServiceError, ValueError) as exc:
        progress.empty()
        st.error(f"Falha ao preparar a história: {exc}")
        st.stop()

    run_id = uuid4().hex
    material_root = Path(utils.storage_dir("local_videos", create=True))
    image_dir = material_root / f"story-{story_mode.safe_slug(title)}-{run_id[:8]}"
    image_paths: list[Path] = []
    for offset, scene in enumerate(scenes, start=1):
        progress.progress(
            int(offset / max(len(scenes), 1) * 65),
            text=f"Gerando imagem {offset} de {len(scenes)}...",
        )
        try:
            image_paths.append(
                forge.generate_image(
                    scene.visual_prompt,
                    image_dir / f"scene-{scene.index:03d}.png",
                    negative_prompt=negative_prompt,
                    steps=steps,
                    seed=int(seed) + scene.index,
                )
            )
        except story_mode.LocalServiceError as exc:
            progress.empty()
            st.error(f"Falha na imagem da cena {scene.index}: {exc}")
            st.stop()

    average_scene_seconds = max(
        4,
        math.ceil(sum(scene.estimated_seconds for scene in scenes) / len(scenes)),
    )
    materials = [
        MaterialInfo(provider="local", url=str(path), duration=average_scene_seconds)
        for path in image_paths
    ]
    generated: dict[str, dict] = {}
    voices = {"pt": pt_voice, "en": en_voice}

    for number, language in enumerate(("pt", "en"), start=1):
        progress.progress(
            65 + number * 15,
            text=(
                "Montando versão em português..."
                if language == "pt"
                else "Montando versão em inglês..."
            ),
        )
        params = VideoParams(
            video_subject=title,
            video_script=story_mode.narration_for_language(scenes, language),
            video_terms="",
            video_aspect=VideoAspect.portrait,
            video_concat_mode=VideoConcatMode.sequential,
            video_transition_mode=None,
            video_clip_duration=average_scene_seconds,
            video_count=1,
            video_source="local",
            video_materials=materials,
            video_language="pt-BR" if language == "pt" else "en-US",
            voice_name=voices[language],
            voice_rate=voice_rate,
            voice_volume=1.0,
            bgm_type="",
            bgm_volume=0.0,
            subtitle_enabled=True,
            subtitle_position="bottom",
            font_size=54,
            stroke_width=2.0,
        )
        result = task_service.start(
            task_id=str(uuid4()),
            params=params,
            stop_at="video",
            allow_server_file_input=True,
        )
        generated[language] = result or {}

    progress.progress(100, text="Vídeos concluídos.")
    progress.empty()
    st.success(
        f"História processada em {len(scenes)} cenas. As mesmas imagens foram usadas "
        "nas duas versões."
    )
    result_pt, result_en = st.columns(2)
    with result_pt:
        _render_result("pt", generated["pt"])
    with result_en:
        _render_result("en", generated["en"])
