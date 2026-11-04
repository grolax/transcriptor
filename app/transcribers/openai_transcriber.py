"""Motor de transcripción vía OpenAI API.

Usa `gpt-4o-transcribe-diarize`, que entrega en una sola respuesta texto +
timestamps + identificación de hablantes (ver
https://developers.openai.com/api/docs/models/gpt-4o-transcribe-diarize).

Este modelo NO soporta el parámetro `prompt` (contexto/glosario) — por eso
ese campo de la interfaz todavía no tiene efecto con este motor; se resolverá
en una etapa posterior (ver services/audio.py y el README para más detalle).

Para audios que exceden los límites de la API (25 MB por solicitud), este
motor los parte en trozos con `services.audio.split_into_chunks`, transcribe
cada uno por separado y reconstruye los timestamps globales sumando el
offset de cada trozo. Importante: cuando el audio se divide en más de un
trozo, cada trozo se diariza de forma independiente — la etiqueta
"Hablante A" de un trozo no está garantizado que sea la misma persona que
"Hablante A" de otro trozo. Esto se refleja en `Transcript.warnings`.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from openai import OpenAI

from app.models.transcript import Segment, Transcript
from app.services.audio import get_duration_seconds, split_into_chunks, to_flac
from app.transcribers.base import Transcriber

# Límite duro de la API de OpenAI para este endpoint, independiente del
# modelo. Se revisa por trozo (ya convertido a FLAC), no sobre el archivo
# original completo.
MAX_CHUNK_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

DEFAULT_MODEL = "gpt-4o-transcribe-diarize"


class OpenAITranscriber(Transcriber):
    """Transcribe usando la API de OpenAI (client.audio.transcriptions)."""

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None) -> None:
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "No se encontró OPENAI_API_KEY. Defínela en tu archivo .env "
                "(ver .env.example)."
            )
        self.model = model
        self._client = OpenAI(api_key=api_key)

    def transcribe(
        self,
        audio_path: str,
        *,
        language: str | None = None,
        prompt: str | None = None,
        workdir: Path | None = None,
    ) -> Transcript:
        audio_path = Path(audio_path)
        own_workdir = workdir is None
        workdir = workdir or Path(tempfile.mkdtemp(prefix="openai_transcriber_"))

        try:
            chunks = split_into_chunks(audio_path, workdir)
            segments: list[Segment] = []

            for chunk in chunks:
                flac_path = to_flac(chunk.path, workdir)
                self._check_chunk_size(flac_path)
                response = self._transcribe_chunk(flac_path, language=language)
                for raw_segment in response.segments:
                    segments.append(
                        Segment(
                            text=raw_segment.text,
                            start=chunk.start_offset + raw_segment.start,
                            end=chunk.start_offset + raw_segment.end,
                            speaker=f"Hablante {raw_segment.speaker}",
                        )
                    )

            warnings: list[str] = []
            if len(chunks) > 1:
                warnings.append(
                    f"Este audio se dividió en {len(chunks)} partes para poder "
                    "transcribirlo (supera el límite de tamaño por solicitud de "
                    "la API). Cada parte se diariza de forma independiente, así "
                    "que una misma etiqueta como 'Hablante A' puede corresponder "
                    "a personas distintas entre una parte y otra. Revisa la "
                    "asignación de hablantes con cuidado, especialmente cerca de "
                    "los cortes, antes de renombrarlos."
                )

            return Transcript(
                language=language,
                duration=get_duration_seconds(audio_path),
                segments=segments,
                warnings=warnings,
            )
        finally:
            if own_workdir:
                shutil.rmtree(workdir, ignore_errors=True)

    def _check_chunk_size(self, flac_path: Path) -> None:
        size = flac_path.stat().st_size
        if size > MAX_CHUNK_SIZE_BYTES:
            raise ValueError(
                f"Uno de los trozos del audio pesa {size / (1024 * 1024):.1f} MB "
                "incluso después de comprimirlo, y supera el límite de 25 MB de "
                "la API. Esto es inusual (suele pasar solo con audio muy denso "
                "o con mucho ruido de fondo) — contáctame para ajustar el "
                "tamaño de los trozos."
            )

    def _transcribe_chunk(self, flac_path: Path, *, language: str | None):
        with open(flac_path, "rb") as audio_file:
            kwargs: dict[str, object] = {
                "model": self.model,
                "file": audio_file,
                "response_format": "diarized_json",
                "chunking_strategy": "auto",
            }
            if language:
                kwargs["language"] = language
            return self._client.audio.transcriptions.create(**kwargs)
