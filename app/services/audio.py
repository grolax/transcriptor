"""Validación y normalización de audio/video con FFmpeg.

Convertir siempre a WAV mono 16kHz antes de transcribir tiene dos
ventajas: (1) si el archivo de entrada es un video, FFmpeg extrae la
pista de audio automáticamente -no hace falta lógica separada para eso-
y (2) todos los motores reciben un formato uniforme, evitando sorpresas
por códecs raros (ej. audio de WhatsApp, videos de Zoom, etc.).

Se invoca FFmpeg por subprocess en vez de cargar el audio con librerías
como pydub, que decodifican el archivo completo en memoria: para
entrevistas de 1-2 horas eso puede ser cientos de MB innecesarios en RAM.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class AudioProcessingError(RuntimeError):
    """Error al validar o normalizar un archivo de audio/video."""


# Duración objetivo por trozo al partir audios largos. Con WAV mono 16kHz
# (~32 KB/s), 15 minutos pesan ~29 MB — por eso cada trozo se transcodea a
# FLAC (sin pérdida, pero bastante más liviano) antes de enviarlo a la API,
# lo que deja margen cómodo bajo el límite de 25 MB por solicitud.
DEFAULT_CHUNK_TARGET_SECONDS = 900  # 15 minutos
MIN_CHUNK_SECONDS = 60


@dataclass
class AudioChunk:
    """Un trozo de un audio más largo, con su ubicación en el original."""

    path: Path
    start_offset: float  # segundos, desde el inicio del audio completo
    end_offset: float


def normalize_to_wav(input_path: Path, workdir: Path) -> Path:
    """Convierte `input_path` a WAV mono 16kHz usando FFmpeg.

    Funciona igual para audio o video: FFmpeg toma solo la pista de audio.
    """
    output_path = workdir / "normalized.wav"
    command = [
        "ffmpeg",
        "-y",  # sobrescribe si ya existe
        "-i",
        str(input_path),
        "-vn",  # descarta cualquier pista de video
        "-ac",
        "1",  # mono
        "-ar",
        "16000",  # 16kHz, suficiente para los motores de transcripción
        "-f",
        "wav",
        str(output_path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=600,
    )

    if result.returncode != 0:
        raise AudioProcessingError(
            "No se pudo procesar el archivo con FFmpeg. "
            "Verifica que el archivo no esté corrupto.\n"
            f"Detalle: {result.stderr.strip()[-500:]}"
        )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise AudioProcessingError("FFmpeg no generó un archivo de audio válido.")

    return output_path


def get_duration_seconds(audio_path: Path) -> float:
    """Duración del archivo en segundos, vía ffprobe."""
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _detect_silences(
    audio_path: Path, noise_db: int = -30, min_silence_seconds: float = 0.5
) -> list[tuple[float, float]]:
    """Detecta tramos de silencio en el audio, vía el filtro `silencedetect` de FFmpeg.

    Se usan para elegir dónde cortar sin partir una palabra o intervención
    a la mitad. FFmpeg escribe esta información en stderr (no genera un
    archivo de salida real; se descarta con -f null).
    """
    command = [
        "ffmpeg",
        "-i",
        str(audio_path),
        "-af",
        f"silencedetect=noise={noise_db}dB:d={min_silence_seconds}",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=600)

    silences: list[tuple[float, float]] = []
    pending_start: float | None = None
    for line in result.stderr.splitlines():
        if "silence_start" in line:
            try:
                pending_start = float(line.split("silence_start:")[1].strip())
            except (IndexError, ValueError):
                pending_start = None
        elif "silence_end" in line and pending_start is not None:
            try:
                end_str = line.split("silence_end:")[1].split("|")[0].strip()
                silences.append((pending_start, float(end_str)))
            except (IndexError, ValueError):
                pass
            pending_start = None
    return silences


def _plan_cut_points(
    duration: float,
    silences: list[tuple[float, float]],
    target_seconds: float,
    min_seconds: float,
) -> list[float]:
    """Elige puntos de corte cercanos a `target_seconds`, alineados a silencios.

    Avanza por el audio en bloques de ~target_seconds y, en cada uno, busca
    el silencio más cercano al punto ideal de corte para no cortar una
    palabra o intervención a la mitad. Si no encuentra un silencio cercano,
    corta igual en el punto ideal (mejor eso que fallar por tamaño de
    archivo).
    """
    cuts: list[float] = []
    cursor = 0.0
    while duration - cursor > target_seconds * 1.2:
        ideal_cut = cursor + target_seconds
        ventana = target_seconds * 0.4
        candidatos = [
            s for s in silences if cursor + min_seconds < s[0] <= ideal_cut + ventana
        ]
        if candidatos:
            mejor = min(candidatos, key=lambda s: abs(s[0] - ideal_cut))
            cut_point = (mejor[0] + mejor[1]) / 2
        else:
            cut_point = ideal_cut
        cuts.append(cut_point)
        cursor = cut_point
    return cuts


def split_into_chunks(
    audio_path: Path,
    workdir: Path,
    target_seconds: float = DEFAULT_CHUNK_TARGET_SECONDS,
) -> list[AudioChunk]:
    """Parte un WAV largo en trozos de ~`target_seconds`, cortando en silencios.

    Si el audio ya es más corto que `target_seconds`, devuelve un único
    trozo (el archivo original, sin recortar) para no hacer trabajo de más.
    """
    duration = get_duration_seconds(audio_path)
    if duration <= target_seconds:
        return [AudioChunk(path=audio_path, start_offset=0.0, end_offset=duration)]

    silences = _detect_silences(audio_path)
    cut_points = _plan_cut_points(duration, silences, target_seconds, MIN_CHUNK_SECONDS)
    bounds = [0.0, *cut_points, duration]

    chunks: list[AudioChunk] = []
    for i in range(len(bounds) - 1):
        start, end = bounds[i], bounds[i + 1]
        chunk_path = workdir / f"chunk_{i:03d}.wav"
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(audio_path),
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-c",
            "copy",
            str(chunk_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
        if result.returncode != 0 or not chunk_path.exists():
            raise AudioProcessingError(
                "No se pudo partir el audio en trozos.\n"
                f"Detalle: {result.stderr.strip()[-500:]}"
            )
        chunks.append(AudioChunk(path=chunk_path, start_offset=start, end_offset=end))

    return chunks


def to_flac(wav_path: Path, workdir: Path) -> Path:
    """Transcodea un WAV a FLAC (sin pérdida, pero más liviano) para subir a la API."""
    output_path = workdir / f"{wav_path.stem}.flac"
    command = ["ffmpeg", "-y", "-i", str(wav_path), str(output_path)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    if result.returncode != 0 or not output_path.exists():
        raise AudioProcessingError(
            "No se pudo convertir el audio a FLAC.\n"
            f"Detalle: {result.stderr.strip()[-500:]}"
        )
    return output_path
