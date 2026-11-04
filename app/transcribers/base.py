"""Interfaz común para motores de transcripción.

Cualquier motor nuevo (OpenAI, faster-whisper, WhisperX, lo que sea)
implementa esta clase. La app y el resto de los servicios solo conocen
esta interfaz, nunca los detalles de un motor en particular — así se
pueden intercambiar sin tocar el resto del código.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.models.transcript import Transcript


class Transcriber(ABC):
    """Contrato que debe cumplir todo motor de transcripción."""

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        *,
        language: str | None = None,
        prompt: str | None = None,
        workdir: Path | None = None,
    ) -> Transcript:
        """Transcribe un archivo de audio ya normalizado (WAV mono).

        Args:
            audio_path: ruta local al archivo de audio a transcribir. Puede
                ser un audio largo: cada motor decide cómo (o si) lo parte
                en trozos para respetar sus propios límites.
            language: código de idioma ISO-639-1 (ej. "es"). Si es None,
                el motor debe detectar el idioma automáticamente.
            prompt: contexto opcional (nombres propios, siglas, glosario)
                para mejorar el reconocimiento. No debe usarse para
                inventar contenido, solo para guiar el reconocimiento. No
                todos los motores lo soportan (ver la documentación de
                cada implementación).
            workdir: directorio para archivos intermedios (ej. trozos de
                audio partido). Si es None, el motor debe crear y limpiar
                uno propio.

        Returns:
            Un Transcript con el resultado.
        """
        raise NotImplementedError
