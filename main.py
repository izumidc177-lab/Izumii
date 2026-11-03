import os, uuid, shutil, subprocess
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "jobs"
WORK.mkdir(exist_ok=True)
app = FastAPI(title="AI Media Enhancer API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

RESOLUTIONS = {
    "180p": 320, "240p": 426, "360p": 640, "480p": 854,
    "720p": 1280, "1080p": 1920, "1440p": 2560, "2k": 2560
}
FPS_ALLOWED = {24, 30, 60, 120, 144, 240}

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-2500:] or "Proses gagal")
    return p

@app.get("/api/health")
def health():
    return {"ok": True, "ffmpeg": shutil.which("ffmpeg") is not None,
            "realesrgan": shutil.which("realesrgan-ncnn-vulkan") is not None}

@app.post("/api/enhance")
async def enhance(file: UploadFile = File(...), kind: str = Form(...),
                  resolution: str = Form("1080p"), fps: int = Form(60),
                  ai_mode: bool = Form(True)):
    name = Path(file.filename or "upload").name
    ext = Path(name).suffix.lower()
    if ext not in {".jpg",".jpeg",".png",".webp",".mp4",".mov",".mkv",".webm"}:
        raise HTTPException(400, "Format file tidak didukung.")
    if kind not in {"photo","video"}: raise HTTPException(400, "Jenis media tidak valid.")
    if resolution not in RESOLUTIONS: raise HTTPException(400, "Resolusi tidak valid.")
    if fps not in FPS_ALLOWED: raise HTTPException(400, "FPS tidak valid.")
    if kind == "photo" and ext not in {".jpg",".jpeg",".png",".webp"}:
        raise HTTPException(400, "Unggah file foto untuk mode foto.")
    if kind == "video" and ext not in {".mp4",".mov",".mkv",".webm"}:
        raise HTTPException(400, "Unggah file video untuk mode video.")
    job = uuid.uuid4().hex[:12]
    folder = WORK / job
    folder.mkdir()
    src = folder / ("input" + ext)
    out_ext = ".png" if kind == "photo" else ".mp4"
    out = folder / ("enhanced" + out_ext)
    with src.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)
    try:
        width = RESOLUTIONS[resolution]
        if kind == "photo":
            realesrgan = shutil.which("realesrgan-ncnn-vulkan") if ai_mode else None
            if realesrgan:
                # Model binary chooses a scale; final dimensions are normalized afterward.
                tmp = folder / "ai.png"
                run([realesrgan, "-i", str(src), "-o", str(tmp), "-n", "realesrgan-x4plus", "-s", "4"])
                run(["ffmpeg","-y","-i",str(tmp),"-vf",f"scale={width}:-2:flags=lanczos","-frames:v","1",str(out)])
                method = "Real-ESRGAN + Lanczos"
            else:
                run(["ffmpeg","-y","-i",str(src),"-vf",f"scale={width}:-2:flags=lanczos","-frames:v","1",str(out)])
                method = "Lanczos (non-AI fallback)"
        else:
            # Preserve aspect ratio; scale to selected width, then interpolate frames.
            vf = f"scale={width}:-2:flags=lanczos,fps={fps}:round=near"
            run(["ffmpeg","-y","-i",str(src),"-vf",vf,"-c:v","libx264","-preset","medium","-crf","19","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k",str(out)])
            method = "FFmpeg scaling + frame-rate conversion (not AI interpolation)"
        return {"job_id": job, "download_url": f"/api/download/{job}", "method": method,
                "message": "Selesai diproses."}
    except Exception as e:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(500, f"Gagal memproses: {str(e)}")

@app.get("/api/download/{job_id}")
def download(job_id: str):
    folder = WORK / job_id
    if not folder.exists(): raise HTTPException(404, "Hasil tidak ditemukan.")
    candidates = list(folder.glob("enhanced.*"))
    if not candidates: raise HTTPException(404, "Hasil belum tersedia.")
    return FileResponse(candidates[0], filename="media-enhanced"+candidates[0].suffix)

@app.get("/")
def home():
    return FileResponse(ROOT / "static" / "index.html")
