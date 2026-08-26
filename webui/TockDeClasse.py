import os
import sys
from pathlib import Path
from uuid import uuid4

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models import const  # noqa: E402
from app.models.schema import MaterialInfo, VideoParams  # noqa: E402
from app.services import state as sm  # noqa: E402
from app.services import webui_task  # noqa: E402
from app.services.tock_de_classe import CampaignBrief, build_campaign  # noqa: E402
from app.utils import utils  # noqa: E402


st.set_page_config(
    page_title="Tock de Classe — Afiliado",
    page_icon="⚽",
    layout="wide",
)

st.markdown(
    """
    <style>
    .stApp { background: #080808; color: #f4f4f4; }
    h1, h2, h3 { color: #d9ad43 !important; }
    [data-testid="stForm"] { border: 1px solid #6f5620; border-radius: 16px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("⚽ Tock de Classe — Afiliado")
st.caption("Roteiro, prompts de duas cenas e montagem vertical para TikTok Shop.")

with st.form("campaign_form"):
    left, right = st.columns(2)
    with left:
        product = st.text_input("Produto", placeholder="Ex.: pré-treino em pó")
        benefit = st.text_area(
            "Benefício principal",
            placeholder="Ex.: ajuda a entrar no clima e manter a disposição para o treino",
        )
        context = st.selectbox(
            "Momento da história",
            ["treino", "jogo", "aquecimento", "ida para o campo", "vestiário"],
        )
    with right:
        offer = st.text_input(
            "Oferta (opcional)",
            placeholder="Ex.: está na promoção da campanha do TikTok Shop",
        )
        cta = st.text_input(
            "Chamada final",
            value="Toca no carrinho e confere a promoção.",
        )
        st.info(
            "O texto evita promessas médicas e mantém o produto dentro da rotina do jogador."
        )
    create_campaign = st.form_submit_button(
        "Criar roteiro e prompts", type="primary", use_container_width=True
    )

if create_campaign:
    try:
        st.session_state["tock_campaign"] = build_campaign(
            CampaignBrief(
                product=product,
                benefit=benefit,
                context=context,
                offer=offer,
                cta=cta,
            )
        )
    except ValueError as exc:
        st.error(str(exc))

campaign = st.session_state.get("tock_campaign")
if campaign:
    st.subheader("1. Roteiro de narração")
    edited_script = st.text_area(
        "Fala em português brasileiro",
        value=campaign["script"],
        height=150,
        key="tock_edited_script",
    )

    st.subheader("2. Prompts para gerar os clipes")
    scene_one, scene_two = st.columns(2)
    with scene_one:
        st.text_area(
            "Cena 1 — 10 segundos",
            value=campaign["scene_prompts"][0],
            height=330,
        )
    with scene_two:
        st.text_area(
            "Cena 2 — 10 segundos",
            value=campaign["scene_prompts"][1],
            height=330,
        )

    st.subheader("3. Envie os dois clipes e monte o vídeo")
    uploaded_clips = st.file_uploader(
        "Clipes verticais gerados",
        type=["mp4", "mov", "avi", "mkv", "webm"],
        accept_multiple_files=True,
        help="Envie preferencialmente a cena 1 e depois a cena 2.",
    )

    if st.button(
        "Montar vídeo final", type="primary", use_container_width=True
    ):
        if len(uploaded_clips or []) < 2:
            st.error("Envie pelo menos os dois clipes de 10 segundos.")
        else:
            material_dir = Path(
                utils.storage_dir("local_videos/tock_de_classe", create=True)
            )
            materials = []
            for index, uploaded_clip in enumerate(uploaded_clips, start=1):
                suffix = Path(uploaded_clip.name).suffix.lower()
                output_path = material_dir / f"scene-{index}-{uuid4().hex}{suffix}"
                output_path.write_bytes(uploaded_clip.getbuffer())
                materials.append(
                    MaterialInfo(provider="local", url=str(output_path), duration=0)
                )

            task_id = f"tock-{uuid4().hex[:12]}"
            params = VideoParams(
                video_subject=campaign["brief"]["product"],
                video_script=edited_script.strip(),
                video_aspect="9:16",
                video_concat_mode="sequential",
                video_clip_duration=10,
                video_count=1,
                video_source="local",
                video_materials=materials,
                video_language="pt-BR",
                voice_name="pt-BR-AntonioNeural-Male",
                voice_rate=1.05,
                voice_volume=1.0,
                bgm_type="random",
                bgm_volume=0.15,
                subtitle_enabled=True,
                subtitle_position="bottom",
                font_size=70,
                text_fore_color="#FFFFFF",
                stroke_color="#000000",
                stroke_width=2.0,
                n_threads=2,
            )
            webui_task.submit_generation(task_id=task_id, params=params)
            st.session_state["tock_task_id"] = task_id
            st.success(f"Vídeo enviado para montagem. Tarefa: {task_id}")


@st.fragment(run_every="2s")
def render_task_status():
    task_id = st.session_state.get("tock_task_id")
    if not task_id:
        return
    task = sm.state.get_task(task_id) or {}
    progress = int(task.get("progress", 0) or 0)
    st.progress(progress, text=f"Montagem: {progress}%")

    if task.get("state") == const.TASK_STATE_FAILED:
        st.error(task.get("error") or "Não foi possível montar o vídeo.")
        return

    videos = task.get("videos") or []
    if task.get("state") == const.TASK_STATE_COMPLETE and videos:
        video_path = videos[0]
        if os.path.isfile(video_path):
            st.success("Vídeo finalizado!")
            st.video(video_path)
            with open(video_path, "rb") as video_file:
                st.download_button(
                    "Baixar vídeo final",
                    data=video_file.read(),
                    file_name=f"tock-de-classe-{task_id}.mp4",
                    mime="video/mp4",
                    use_container_width=True,
                )


render_task_status()
