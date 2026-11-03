import os
import uuid
import shutil
import subprocess
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "jobs"
WORK.mkdir(exist_ok=True)

app = FastAPI(title="Yuzuru Enhance API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

RESOLUTIONS = {
    "180p": 320, "240p": 426, "360p": 640, "480p": 854,
    "720p": 1280, "1080p": 1920, "1440p": 2560, "2k": 2560,
}
FPS_ALLOWED = {24, 30, 60, 120, 144, 240}
PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm"}


def run(cmd):
    process = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if process.returncode:
        raise RuntimeError(process.stderr[-2500:] or "Proses gagal")
    return process


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "realesrgan": shutil.which("realesrgan-ncnn-vulkan") is not None,
    }


@app.post("/api/enhance")
async def enhance(
    file: UploadFile = File(...),
    kind: str = Form(...),
    resolution: str = Form("1080p"),
    fps: int = Form(60),
    ai_mode: bool = Form(True),
):
    name = Path(file.filename or "upload").name
    ext = Path(name).suffix.lower()

    if kind not in {"photo", "video"}:
        raise HTTPException(400, "Jenis media tidak valid.")
    if resolution not in RESOLUTIONS:
        raise HTTPException(400, "Resolusi tidak valid.")
    if fps not in FPS_ALLOWED:
        raise HTTPException(400, "FPS tidak valid.")
    if kind == "photo" and ext not in PHOTO_EXT:
        raise HTTPException(400, "Unggah file foto untuk mode foto.")
    if kind == "video" and ext not in VIDEO_EXT:
        raise HTTPException(400, "Unggah file video untuk mode video.")

    job_id = uuid.uuid4().hex[:12]
    folder = WORK / job_id
    folder.mkdir(parents=True, exist_ok=False)
    source = folder / ("original" + ext)
    output = folder / ("enhanced.png" if kind == "photo" else "enhanced.mp4")

    # Limit upload size to 100 MiB to protect the small hosting instance.
    total = 0
    try:
        with source.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > 100 * 1024 * 1024:
                    raise HTTPException(413, "Ukuran file maksimal 100 MB.")
                destination.write(chunk)

        width = RESOLUTIONS[resolution]
        if kind == "photo":
            realesrgan = shutil.which("realesrgan-ncnn-vulkan") if ai_mode else None
            if realesrgan:
                temporary = folder / "ai.png"
                run([
                    realesrgan, "-i", str(source), "-o", str(temporary),
                    "-n", "realesrgan-x4plus", "-s", "4",
                ])
                run([
                    "ffmpeg", "-y", "-i", str(temporary), "-vf",
                    f"scale={width}:-2:flags=lanczos", "-frames:v", "1",
                    str(output),
                ])
                method = "Real-ESRGAN + Lanczos"
            else:
                run([
                    "ffmpeg", "-y", "-i", str(source), "-vf",
                    f"scale={width}:-2:flags=lanczos", "-frames:v", "1",
                    str(output),
                ])
                method = "Lanczos (non-AI fallback)"
        else:
            video_filter = f"scale={width}:-2:flags=lanczos,fps={fps}:round=near"
            run([
                "ffmpeg", "-y", "-i", str(source), "-vf", video_filter,
                "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                str(output),
            ])
            method = "FFmpeg scaling + frame-rate conversion (not AI interpolation)"

        return {
            "job_id": job_id,
            "download_url": f"/api/download/{job_id}",
            "original_url": f"/api/preview/{job_id}/original",
            "result_url": f"/api/preview/{job_id}/result",
            "method": method,
            "message": "Selesai diproses.",
        }
    except HTTPException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    except Exception as error:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(500, f"Gagal memproses: {str(error)}")
    finally:
        await file.close()


@app.get("/api/preview/{job_id}/{which}")
def preview(job_id: str, which: str):
    # Accept only generated IDs and the two known preview types.
    if len(job_id) != 12 or any(ch not in "0123456789abcdef" for ch in job_id):
        raise HTTPException(404, "Hasil tidak ditemukan.")
    if which not in {"original", "result"}:
        raise HTTPException(404, "Preview tidak ditemukan.")

    folder = WORK / job_id
    if not folder.is_dir():
        raise HTTPException(404, "Hasil tidak ditemukan.")

    if which == "result":
        candidates = list(folder.glob("enhanced.*"))
        target = candidates[0] if candidates else None
    else:
        candidates = [
            path for path in folder.glob("original.*")
            if path.suffix.lower() in PHOTO_EXT
        ]
        target = candidates[0] if candidates else None

    if target is None or not target.is_file():
        raise HTTPException(404, "Preview tidak tersedia.")
    return FileResponse(target)


@app.get("/api/download/{job_id}")
def download(job_id: str):
    if len(job_id) != 12 or any(ch not in "0123456789abcdef" for ch in job_id):
        raise HTTPException(404, "Hasil tidak ditemukan.")
    folder = WORK / job_id
    if not folder.is_dir():
        raise HTTPException(404, "Hasil tidak ditemukan.")
    candidates = list(folder.glob("enhanced.*"))
    if not candidates:
        raise HTTPException(404, "Hasil belum tersedia.")
    target = candidates[0]
    return FileResponse(
        target,
        filename="yuzuru-enhanced" + target.suffix,
    )


@app.get("/")
def home():
    return FileResponse(ROOT / "static" / "index.html")
