# Transcriptor

Aplicación de transcripción automática de audio y video a texto (Etapa 3, incremento 1).

Estado actual: sube un archivo (de cualquier duración razonable), transcribe con `gpt-4o-transcribe-diarize` (timestamps + identificación de hablantes incluidos), parte automáticamente los audios largos en trozos y reconstruye los timestamps globales, muestra el resultado en un editor y permite descargarlo en TXT. Renombrado interactivo de hablantes, otros formatos de exportación (DOCX/SRT/VTT/JSON), glosario/contexto real, barra de progreso por trozo, historial y motor local llegan en incrementos siguientes.

## Requisitos

- Python 3.11 o superior (si usas 3.9/3.10, ver nota abajo)
- FFmpeg instalado en el sistema (no es una librería de Python, es un programa aparte):
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - Windows: descargar desde [ffmpeg.org](https://ffmpeg.org/download.html) y agregarlo al PATH
- Una API key de OpenAI con acceso al modelo `gpt-4o-transcribe-diarize`

## Instalación

```bash
python -m venv .venv
```

Activar el entorno virtual:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

Instalar dependencias:

```bash
pip install -r requirements.txt
```

Configurar la API key:

```bash
cp .env.example .env
```

Y editar `.env` reemplazando `sk-...` por tu API key real.

### Nota para Python 3.9

Si tu `python3` es la versión 3.9 (Mac trae esta versión preinstalada por defecto), vas a necesitar además:

```bash
pip install eval_type_backport
```

(Ya está declarado como dependencia condicional en `requirements.txt`, así que `pip install -r requirements.txt` ya lo instala solo si tu Python es &lt; 3.10.)

## Ejecutar

```bash
streamlit run app/app.py
```

Se abrirá automáticamente en el navegador (normalmente en `http://localhost:8501`).

## Uso

1. Arrastra un archivo de audio o video (MP3, WAV, M4A, MP4, MPEG, WEBM, OGG) o selecciónalo con el botón.
2. Elige el idioma o deja "Detectar automáticamente".
3. Presiona "Transcribir" y espera a que termine (los audios largos tardan más porque se procesan en varios trozos).
4. Corrige el texto directamente en el editor si es necesario.
5. Descarga el resultado en TXT.

Si el audio tuvo que dividirse en varios trozos, vas a ver una advertencia: la identificación de hablantes se hace por separado en cada trozo, así que "Hablante A" de un trozo no necesariamente es la misma persona que "Hablante A" de otro. Revísalo con cuidado en esos casos.

## Privacidad

El audio se envía a la API de OpenAI para procesarse (sujeto a la política de datos de OpenAI). No se almacena de forma permanente en el servidor de la aplicación: se guarda en un directorio temporal exclusivo para cada transcripción (incluyendo los trozos intermedios si el audio se partió) y se elimina automáticamente al terminar. El motor local (sin salida de datos, para audios confidenciales) se agrega en un incremento posterior.

## Cómo se manejan los audios largos

FFmpeg detecta silencios en el audio y usa esos puntos para partirlo en trozos de ~15 minutos (evitando cortar una palabra o intervención a la mitad). Cada trozo se transcodea a FLAC (compresión sin pérdida) antes de subirlo, para quedar cómodamente bajo el límite de 25 MB por solicitud de la API. Los timestamps de cada trozo se ajustan sumando su posición real en el audio original, así que el resultado final tiene timestamps continuos de principio a fin.

## Límites conocidos de este incremento

- Sin renombrado interactivo de hablantes en la interfaz todavía (por ahora, edítalo directamente en el texto).
- El campo de contexto/glosario está deshabilitado: `gpt-4o-transcribe-diarize` todavía no acepta ese parámetro en la API de OpenAI.
- Solo exportación a TXT (con timestamps y hablante incluidos en el texto).
- Streamlit acepta subir hasta 1 GB por defecto (configurado en `.streamlit/config.toml`); si necesitas más, sube ese número.

## Estructura del proyecto

```text
app/
├── app.py                        # Interfaz Streamlit (orquesta, sin lógica de transcripción)
├── transcribers/
│   ├── base.py                   # Interfaz común Transcriber
│   ├── openai_transcriber.py     # Motor OpenAI (gpt-4o-transcribe-diarize, con partición de audios largos)
│   └── local_transcriber.py      # Motor local — placeholder, incremento futuro
├── services/
│   └── audio.py                  # Normalización, detección de silencios y partición con FFmpeg
├── models/
│   └── transcript.py             # Transcript, Segment
└── utils/
    └── files.py                  # Manejo de temporales
```

## Compartir la app con otra persona (sin que instale nada)

Para darle a alguien un link donde pueda usar la app desde su navegador, sin instalar Python ni FFmpeg, se despliega en [Streamlit Community Cloud](https://streamlit.io/cloud) (gratis). Tu API key de OpenAI queda guardada del lado del servidor como "secret" — la otra persona nunca la ve, solo usa la app.

### 1. Sube el proyecto a GitHub

Streamlit Community Cloud despliega desde un repositorio de GitHub (puede ser privado).

```bash
cd ~/Downloads/transcriptor-etapa3-parte1
git init
git add .
git commit -m "Primera versión del transcriptor"
```

Luego crea un repositorio vacío en [github.com/new](https://github.com/new) y sigue las instrucciones que te muestra GitHub para conectar tu carpeta local con ese repositorio (algo como `git remote add origin ...` y `git push -u origin main`). `.env` y `.streamlit/secrets.toml` no se suben nunca — ya están en `.gitignore`.

### 2. Despliega en Streamlit Community Cloud

1. Entra a [share.streamlit.io](https://share.streamlit.io) e inicia sesión con tu cuenta de GitHub.
2. "New app" → elige el repositorio que acabas de crear.
3. Main file path: `app/app.py`.
4. Antes de desplegar, ve a "Advanced settings" → "Secrets" y pega:

```toml
OPENAI_API_KEY = "sk-tu-api-key-real"
APP_PASSWORD = "una-clave-simple-que-le-pasas-a-la-otra-persona"
```

5. Despliega. Te va a dar un link tipo `https://tu-app.streamlit.app`.

### 3. Comparte el link y la contraseña

Mándale a la otra persona el link y, por separado (ej. por WhatsApp, no por el mismo canal que el link), la contraseña que puso en `APP_PASSWORD`. Así, aunque alguien más encuentre el link, no puede usar la app sin esa clave — y por lo tanto no puede gastar tu saldo de OpenAI.

### Limitaciones de este despliegue

- El plan gratuito de Streamlit Community Cloud tiene recursos limitados (CPU/memoria compartida). Para audios muy largos puede ser más lento que corriendo en tu propio computador, o quedarse sin memoria en casos extremos.
- Cualquiera con el link **y** la contraseña puede usar tu API key — no hay límite de gasto por persona. Si quieres controlar esto más fino (por ejemplo, un tope de minutos por mes), es una mejora posible pero no está implementada todavía.
- Si cambias la contraseña más adelante, hazlo desde "Settings" → "Secrets" de la app en share.streamlit.io; no necesitas volver a desplegar.
