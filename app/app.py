"""Interfaz Streamlit — MVP.

Este archivo solo orquesta: carga el audio, llama a los servicios y al
motor de transcripción, y muestra el resultado. No contiene lógica de
transcripción ni de procesamiento de audio (eso vive en transcribers/ y
services/), para poder crecer sin que este archivo se vuelva inmanejable.

Flujo del MVP: subir → transcribir → mostrar → editar → descargar TXT.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from dotenv import load_dotenv

from app.services.audio import AudioProcessingError, normalize_to_wav
from app.transcribers.openai_transcriber import OpenAITranscriber
from app.utils.files import SUPPORTED_EXTENSIONS, save_upload, temp_workdir

load_dotenv()


def _get_secret(name: str) -> str | None:
    """Busca una variable en los secrets de Streamlit (cuando la app está
    desplegada en Streamlit Community Cloud) y, si no está ahí, en el
    entorno / archivo .env (cuando corre en tu computador)."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name)


st.set_page_config(page_title="Transcriptor", page_icon="🎙️", layout="centered")

# --- Acceso con contraseña ---
# Solo se activa si se configuró APP_PASSWORD como secret (pensado para
# cuando la app se comparte con un link público). Si no está configurada
# -como en tu uso local-, no pide nada.
app_password = _get_secret("APP_PASSWORD")
if app_password:
    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False
    if not st.session_state.autenticado:
        st.title("🎙️ Transcriptor")
        clave_ingresada = st.text_input("Contraseña de acceso", type="password")
        if st.button("Entrar"):
            if clave_ingresada == app_password:
                st.session_state.autenticado = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
        st.stop()

if "transcript_text" not in st.session_state:
    st.session_state.transcript_text = ""
if "transcript_warnings" not in st.session_state:
    st.session_state.transcript_warnings = []

st.title("🎙️ Transcriptor")
st.caption(
    "Sube un archivo de audio o video, transcríbelo y descarga el resultado. "
    "El audio se envía a la API de OpenAI para procesarse y se elimina del "
    "servidor apenas termina la transcripción."
)

with st.expander("Contexto de la grabación (próximamente)"):
    st.caption(
        "El modelo que identifica hablantes (gpt-4o-transcribe-diarize) "
        "todavía no acepta contexto/glosario en la API de OpenAI. Este "
        "campo se activará en una próxima etapa."
    )
    contexto = st.text_area(
        "Nombres propios, siglas o conceptos frecuentes en el audio",
        placeholder="Ej: Entrevista sobre políticas educativas en Honduras. "
        "Conceptos frecuentes: UNESCO, CECC/SICA, SINAGER, COPECO.",
        disabled=True,
    )

idioma_opciones = {
    "Detectar automáticamente": None,
    "Español": "es",
    "Inglés": "en",
}
idioma_label = st.selectbox("Idioma", list(idioma_opciones.keys()))
idioma = idioma_opciones[idioma_label]

extensiones_legibles = ", ".join(sorted(SUPPORTED_EXTENSIONS))
uploaded_file = st.file_uploader(
    f"Arrastra un archivo o selecciónalo ({extensiones_legibles})",
    type=[ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS],
)

transcribir = st.button("Transcribir", type="primary", disabled=uploaded_file is None)

if transcribir and uploaded_file is not None:
    try:
        with st.spinner("Procesando audio..."):
            with temp_workdir() as workdir:
                original_path = save_upload(uploaded_file, workdir)
                audio_wav = normalize_to_wav(original_path, workdir)

                with st.spinner(
                    "Transcribiendo... si el audio es largo, esto puede tardar "
                    "varios minutos porque se procesa en partes."
                ):
                    transcriber = OpenAITranscriber(api_key=_get_secret("OPENAI_API_KEY"))
                    transcript = transcriber.transcribe(
                        str(audio_wav),
                        language=idioma,
                        workdir=workdir,
                    )

        st.session_state.transcript_text = transcript.formatted_text
        st.session_state.transcript_warnings = transcript.warnings

        if not st.session_state.transcript_text:
            st.warning("La transcripción resultó vacía. Verifica el archivo de audio.")
        else:
            st.success("Transcripción completada.")

    except (AudioProcessingError, ValueError) as e:
        st.error(str(e))
    except RuntimeError as e:
        st.error(str(e))
    except Exception as e:  # noqa: BLE001 — mostramos cualquier error inesperado al usuario
        st.error(f"Ocurrió un error inesperado: {e}")

if st.session_state.transcript_text:
    for warning in st.session_state.transcript_warnings:
        st.warning(warning)

    st.subheader("Transcripción")
    edited_text = st.text_area(
        "Puedes corregir el texto directamente aquí antes de descargarlo. "
        "El formato [inicio – fin] Hablante se mantiene como texto plano, "
        "así que puedes editarlo con cuidado si necesitas ajustar algo.",
        value=st.session_state.transcript_text,
        height=400,
        key="editor",
    )
    st.session_state.transcript_text = edited_text

    st.download_button(
        "Descargar TXT",
        data=edited_text,
        file_name="transcripcion.txt",
        mime="text/plain",
    )
    st.caption("Para copiar todo: haz clic dentro del cuadro de texto y usa Ctrl+A, Ctrl+C (Cmd+A, Cmd+C en Mac).")
