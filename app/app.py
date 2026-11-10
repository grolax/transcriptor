"""Interfaz Streamlit.

Este archivo solo orquesta: carga el audio, llama a los servicios y al
motor de transcripción, y muestra el resultado. No contiene lógica de
transcripción ni de procesamiento de audio (eso vive en transcribers/ y
services/), para poder crecer sin que este archivo se vuelva inmanejable.

Flujo: subir → transcribir → mostrar → editar → descargar TXT.

La apariencia vive en dos lugares: el bloque [theme] de
.streamlit/config.toml (colores, radios, fuentes base) y
app/static/style.css (todo lo que el tema no cubre).
"""

from __future__ import annotations

import html
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from dotenv import load_dotenv

from app.services.audio import AudioProcessingError, normalize_to_wav
from app.transcribers.openai_transcriber import OpenAITranscriber
from app.utils.files import SUPPORTED_EXTENSIONS, save_upload, temp_workdir

load_dotenv()

STATIC_DIR = Path(__file__).resolve().parent / "static"


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


# --- Piezas de presentación -------------------------------------------------
# Funciones chicas que solo escriben HTML con las clases de style.css.


def _marca() -> None:
    """El nombre de la app escrito como una línea de su propia transcripción."""
    st.markdown(
        '<h1 class="marca"><span class="marca-tiempo">[00:00]</span> Transcriptor</h1>',
        unsafe_allow_html=True,
    )


def _nota(texto: str, tipo: str = "info") -> None:
    """Nota al margen con filete de color. tipo: "info", "aviso" o "error".

    El texto se escapa porque puede venir de un mensaje de error externo.
    """
    rol = "alert" if tipo == "error" else "note"
    st.markdown(
        f'<div class="nota nota-{tipo}" role="{rol}">{html.escape(texto)}</div>',
        unsafe_allow_html=True,
    )


def _duracion_legible(segundos: float) -> str:
    segundos = int(round(segundos))
    if segundos < 60:
        return f"{segundos} s"
    minutos, resto = divmod(segundos, 60)
    return f"{minutos} min {resto:02d} s"


st.set_page_config(
    page_title="Transcriptor",
    page_icon=str(STATIC_DIR / "favicon.png"),
    layout="centered",
)
st.markdown(
    f"<style>{(STATIC_DIR / 'style.css').read_text(encoding='utf-8')}</style>",
    unsafe_allow_html=True,
)

# --- Acceso con contraseña ---
# Solo se activa si se configuró APP_PASSWORD como secret (pensado para
# cuando la app se comparte con un link público). Si no está configurada
# -como en tu uso local-, no pide nada.
app_password = _get_secret("APP_PASSWORD")
if app_password:
    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False
    if not st.session_state.autenticado:
        _marca()
        clave_ingresada = st.text_input("Contraseña de acceso", type="password")
        if st.button("Entrar", type="primary"):
            if clave_ingresada == app_password:
                st.session_state.autenticado = True
                st.rerun()
            else:
                _nota("La contraseña no coincide. Vuelve a escribirla.", "error")
        st.stop()

if "transcript_text" not in st.session_state:
    st.session_state.transcript_text = ""
if "transcript_warnings" not in st.session_state:
    st.session_state.transcript_warnings = []
if "transcript_duracion" not in st.session_state:
    st.session_state.transcript_duracion = None

hay_resultado = bool(st.session_state.transcript_text)

_marca()

idioma_opciones = {
    "Detectar automáticamente": None,
    "Español": "es",
    "Inglés": "en",
}
idioma_label = st.selectbox("Idioma del audio", list(idioma_opciones.keys()))
idioma = idioma_opciones[idioma_label]

extensiones_legibles = ", ".join(sorted(ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS))
uploaded_file = st.file_uploader(
    "Archivo de audio o video",
    type=[ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS],
)
if uploaded_file is None:
    st.markdown(
        f'<p class="ayuda">Formatos: {extensiones_legibles}. Hasta 1 GB.</p>',
        unsafe_allow_html=True,
    )

# El azul marca siempre la acción siguiente: "Transcribir" mientras no hay
# resultado, "Descargar TXT" cuando lo hay.
transcribir = st.button(
    "Transcribir",
    type="secondary" if hay_resultado else "primary",
    disabled=uploaded_file is None,
)

# Zona de estado: el único lugar de la página que cambia mientras se procesa.
estado = st.container()

if transcribir and uploaded_file is not None:
    inicio = time.monotonic()
    try:
        with estado:
            zona_paso = st.container()
            # El reloj es CSS puro (clase .reloj en style.css): sigue
            # corriendo en el navegador aunque Python esté ocupado
            # transcribiendo, así se ve que la app no se quedó pegada.
            aviso_espera = st.empty()
            aviso_espera.markdown(
                '<p class="ayuda">Tiempo transcurrido: '
                '<span class="reloj" aria-hidden="true"></span>. Los audios '
                "largos se procesan por partes y pueden tardar varios "
                "minutos. Mantén esta pestaña abierta.</p>",
                unsafe_allow_html=True,
            )
            with zona_paso, temp_workdir() as workdir:
                with st.spinner("Paso 1 de 2: preparando el audio"):
                    original_path = save_upload(uploaded_file, workdir)
                    audio_wav = normalize_to_wav(original_path, workdir)

                with st.spinner("Paso 2 de 2: transcribiendo"):
                    transcriber = OpenAITranscriber(api_key=_get_secret("OPENAI_API_KEY"))
                    transcript = transcriber.transcribe(
                        str(audio_wav),
                        language=idioma,
                        workdir=workdir,
                    )
            aviso_espera.empty()

        st.session_state.transcript_text = transcript.formatted_text
        st.session_state.transcript_warnings = transcript.warnings
        st.session_state.transcript_duracion = time.monotonic() - inicio
        # El editor guarda su contenido bajo la clave "editor"; hay que
        # reemplazarlo aquí para que una transcripción nueva no quede
        # tapada por el texto de la anterior.
        st.session_state.editor = transcript.formatted_text

        if st.session_state.transcript_text:
            # Vuelve a dibujar la página para que el acento pase de
            # "Transcribir" a "Descargar TXT".
            st.rerun()
        with estado:
            _nota(
                "La transcripción salió vacía. Revisa que el archivo tenga "
                "voz audible y vuelve a intentarlo.",
                "aviso",
            )

    except (AudioProcessingError, ValueError, RuntimeError) as e:
        aviso_espera.empty()
        with estado:
            _nota(f"{e} El archivo sigue cargado: puedes volver a intentarlo.", "error")
    except Exception as e:  # noqa: BLE001 — mostramos cualquier error inesperado al usuario
        aviso_espera.empty()
        with estado:
            _nota(
                f"Ocurrió un error inesperado: {e}. El archivo sigue cargado: "
                "puedes volver a intentarlo.",
                "error",
            )

if st.session_state.transcript_text:
    st.markdown('<hr class="corte">', unsafe_allow_html=True)
    st.markdown('<h2 class="seccion">Transcripción</h2>', unsafe_allow_html=True)

    if st.session_state.transcript_duracion is not None:
        st.markdown(
            '<p class="ayuda">Lista en '
            f"{_duracion_legible(st.session_state.transcript_duracion)}. "
            "Puedes corregir el texto aquí antes de descargarlo; conserva el "
            "formato [inicio – fin] Hablante.</p>",
            unsafe_allow_html=True,
        )

    for warning in st.session_state.transcript_warnings:
        _nota(warning, "aviso")

    # El editor toma su contenido de st.session_state.editor (su clave).
    # Se inicializa aquí por si Streamlit descartó ese estado mientras el
    # editor no estaba en pantalla.
    if "editor" not in st.session_state:
        st.session_state.editor = st.session_state.transcript_text
    edited_text = st.text_area(
        "Texto de la transcripción",
        height=520,
        key="editor",
        label_visibility="collapsed",
    )
    st.session_state.transcript_text = edited_text

    st.download_button(
        "Descargar TXT",
        data=edited_text,
        file_name="transcripcion.txt",
        mime="text/plain",
        type="primary",
    )
    st.markdown(
        '<p class="ayuda">Para copiar todo, haz clic dentro del texto y usa '
        "Cmd+A, Cmd+C (Ctrl+A, Ctrl+C en Windows).</p>",
        unsafe_allow_html=True,
    )

st.markdown(
    '<p class="pie">El audio se envía a la API de OpenAI para transcribirse y '
    "se borra de este equipo apenas termina el proceso.</p>",
    unsafe_allow_html=True,
)
