from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import subprocess
import os
import uuid
import shutil
import yt_dlp

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
    """Extrai áudio do vídeo usando ffmpeg."""
    result = subprocess.run(
        ["ffmpeg", "-i", video_path, "-vn", "-acodec", "mp3", "-y", audio_path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise Exception(f"Erro ao extrair áudio: {result.stderr}")


# ──────────────────────────────────────────────
# FLUXO 1 — Upload direto de vídeo
# ──────────────────────────────────────────────
@app.post("/upload-video")
async def upload_video(file: UploadFile = File(...)):
    """
    Recebe um arquivo de vídeo, extrai o áudio e retorna o .mp3.
    """
    if not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Envie um arquivo de vídeo válido.")

    session_id = str(uuid.uuid4())
    video_path = f"{UPLOAD_DIR}/{session_id}_video{os.path.splitext(file.filename)[1]}"
    audio_path = f"{UPLOAD_DIR}/{session_id}_audio.mp3"

    # Salva o vídeo
    with open(video_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Extrai o áudio
    try:
        extract_audio(video_path, audio_path)
    except Exception as e:
        os.remove(video_path)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)

    return FileResponse(
        path=audio_path,
        media_type="audio/mpeg",
        filename="audio.mp3",
        background=None  # arquivo será deletado manualmente após download
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
    baixa o vídeo com yt-dlp, extrai o áudio e retorna
    { audio_url, legenda, autor }.
    """
    session_id = str(uuid.uuid4())
    video_path = f"{UPLOAD_DIR}/{session_id}_video.mp4"
    audio_path = f"{UPLOAD_DIR}/{session_id}_audio.mp3"

    # Opções do yt-dlp
    ydl_opts = {
        "outtmpl": video_path,
        "format": "mp4/bestvideo+bestaudio/best",
        "quiet": True,
    }

    # Baixa o vídeo e coleta metadados
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(body.url, download=True)
            legenda = info.get("description", "")
            autor = info.get("uploader", "")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao baixar vídeo: {str(e)}")

    # Extrai o áudio
    try:
        extract_audio(video_path, audio_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)

    # Retorna o áudio como arquivo + metadados no header
    return FileResponse(
        path=audio_path,
        media_type="audio/mpeg",
        filename="audio.mp3",
        headers={
            "X-Legenda": legenda[:500],  # máx 500 chars no header
            "X-Autor": autor,
        }
    )


@app.get("/")
def health_check():
    return {"status": "ok", "message": "Backend rodando!"}
