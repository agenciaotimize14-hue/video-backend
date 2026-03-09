# backend v2 
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import subprocess
import os
import uuid
import shutil
import yt_dlp
import imageio_ffmpeg

# Usa o ffmpeg bundled do imageio_ffmpeg (nao precisa instalar no sistema)
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

app = FastAPI(title="Video Audio Extractor API")

# Libera CORS pro frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "temp_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def extract_audio(video_path: str, audio_path: str):
    """Extrai audio do video usando ffmpeg bundled."""
    result = subprocess.run(
        [FFMPEG_PATH, "-i", video_path, "-vn", "-acodec", "mp3", "-y", audio_path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise Exception(f"Erro ao extrair audio: {result.stderr}")


# ──────────────────────────────────────────────
# FLUXO 1 — Upload direto de video
# ──────────────────────────────────────────────
@app.post("/upload-video")
async def upload_video(file: UploadFile = File(...)):
    """
    Recebe um arquivo de video, extrai o audio e retorna o .mp3.
    """
    if not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Envie um arquivo de video valido.")

    session_id = str(uuid.uuid4())
    video_path = f"{UPLOAD_DIR}/{session_id}_video{os.path.splitext(file.filename)[1]}"
    audio_path = f"{UPLOAD_DIR}/{session_id}_audio.mp3"

    # Salva o video
    with open(video_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Extrai o audio
    try:
        extract_audio(video_path, audio_path)
    except Exception as e:
        if os.path.exists(video_path):
            os.remove(video_path)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)

    return FileResponse(
        path=audio_path,
        media_type="audio/mpeg",
        filename="audio.mp3",
    )


# ──────────────────────────────────────────────
# FLUXO 2 — URL do Instagram (ou outro site)
# ──────────────────────────────────────────────
class URLRequest(BaseModel):
    url: str


@app.post("/extract-from-url")
async def extract_from_url(body: URLRequest):
    """
    Recebe uma URL do Instagram (ou YouTube, TikTok, etc.),
    baixa o video com yt-dlp, extrai o audio e retorna
    o audio + legenda e autor nos headers.
    """
    session_id = str(uuid.uuid4())
    video_path = f"{UPLOAD_DIR}/{session_id}_video.mp4"
    audio_path = f"{UPLOAD_DIR}/{session_id}_audio.mp3"

    ydl_opts = {
        "outtmpl": video_path,
        "format": "mp4/bestvideo+bestaudio/best",
        "quiet": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(body.url, download=True)
            legenda = info.get("description", "")
            autor = info.get("uploader", "")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao baixar video: {str(e)}")

    try:
        extract_audio(video_path, audio_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)

    return FileResponse(
        path=audio_path,
        media_type="audio/mpeg",
        filename="audio.mp3",
        headers={
            "X-Legenda": legenda[:500],
            "X-Autor": autor,
        }
    )


@app.get("/")
def health_check():
    return {"status": "ok", "message": "Backend rodando!"}
