"""Manejo de archivos temporales.

Todo lo que se guarda en disco durante el procesamiento vive bajo un
directorio temporal por sesión, y se borra apenas termina el trabajo:
los audios pueden contener información confidencial y no deben quedar
en el servidor más tiempo del necesario.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# Formatos que la app acepta como entrada.
SUPPORTED_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".m4a",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".webm",
    ".ogg",
}


@contextmanager
def temp_workdir() -> Iterator[Path]:
    """Directorio temporal exclusivo para un procesamiento, que se autolimpia."""
    workdir = Path(tempfile.gettempdir()) / "transcriptor" / uuid.uuid4().hex
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        yield workdir
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def save_upload(uploaded_file, workdir: Path) -> Path:
    """Guarda un archivo subido desde Streamlit (UploadedFile) en `workdir`.

    Streamlit entrega el archivo en memoria; lo escribimos a disco porque
    ffmpeg y los SDKs de transcripción trabajan con rutas de archivo, no
    con objetos en memoria.
    """
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Formato '{suffix}' no soportado. Formatos aceptados: {supported}")

    destino = workdir / f"original{suffix}"
    with open(destino, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return destino
