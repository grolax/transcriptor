"""Modelos de datos centrales de la aplicación.

Estos modelos son el "contrato" interno: todos los motores de transcripción
(OpenAI, local, los que se agreguen después) deben producir un `Transcript`,
y todos los exportadores (TXT, DOCX, SRT, etc.) consumen un `Transcript`.
Así, ni la interfaz ni los exportadores necesitan saber qué motor generó
el texto.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Segment(BaseModel):
    """Un fragmento de la transcripción.

    `start`/`end` pueden no estar disponibles (motor sin timestamps) y
    `speaker` puede ser None (sin diarización).
    """

    text: str
    start: float | None = None
    end: float | None = None
    speaker: str | None = None


def _format_timestamp(seconds: float) -> str:
    """Convierte segundos a HH:MM:SS (o MM:SS si dura menos de una hora)."""
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class Transcript(BaseModel):
    """Resultado completo de transcribir un archivo."""

    language: str | None = None
    duration: float | None = None
    segments: list[Segment] = Field(default_factory=list)
    # Avisos para mostrar en la interfaz (ej. "hablantes pueden no ser
    # consistentes entre partes" cuando el audio se dividió en varios
    # trozos para poder enviarlo a la API).
    warnings: list[str] = Field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Texto plano, sin timestamps ni hablantes — para exportación simple."""
        return "\n".join(segment.text.strip() for segment in self.segments if segment.text.strip())

    @property
    def formatted_text(self) -> str:
        """Texto con timestamps y hablante cuando están disponibles.

        Ejemplo con diarización:
            [00:01:24 – 00:01:32] Hablante A
            Texto del segmento.

        Ejemplo sin timestamps (fallback, ej. motor que no los entrega):
            Texto del segmento.
        """
        lines: list[str] = []
        for segment in self.segments:
            text = segment.text.strip()
            if not text:
                continue
            if segment.start is not None and segment.end is not None:
                marca = f"[{_format_timestamp(segment.start)} – {_format_timestamp(segment.end)}]"
                encabezado = f"{marca} {segment.speaker}" if segment.speaker else marca
                lines.append(encabezado)
                lines.append(text)
                lines.append("")
            else:
                lines.append(text)
        return "\n".join(lines).strip()
