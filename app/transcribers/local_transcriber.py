"""Motor de transcripción local (faster-whisper).

Placeholder de la Etapa 2: la interfaz ya queda definida para que el resto
de la app pueda elegir entre motores sin cambios, pero la implementación
con faster-whisper + pyannote.audio se agrega en la Etapa 3 (item 10),
junto con la descarga de modelos y el manejo del token de Hugging Face
para diarización.
"""

from __future__ import annotations

from app.models.transcript import Transcript
from app.transcribers.base import Transcriber


class LocalTranscriber(Transcriber):
    """Transcribe localmente con faster-whisper (aún no implementado)."""

    def __init__(self, model_size: str = "large-v3") -> None:
        self.model_size = model_size

    def transcribe(
        self,
        audio_path: str,
        *,
        language: str | None = None,
        prompt: str | None = None,
    ) -> Transcript:
        raise NotImplementedError(
            "El motor local (faster-whisper) se implementa en la Etapa 3. "
            "Por ahora, usa el motor de OpenAI."
        )
