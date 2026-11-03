# Nova Enhance — Premium Media Enhancer Starter

## Yang sudah berfungsi
- Web UI premium responsif.
- Upload foto/video.
- Output lebar 180p hingga 2K.
- Video frame-rate conversion 24/30/60/120/144/240 FPS via FFmpeg.
- Foto: Real-ESRGAN ncnn Vulkan jika binary tersedia; fallback Lanczos.
- Download hasil proses.

## Batasan penting
Ini adalah starter full-stack yang bisa dijalankan sendiri, bukan layanan AI cloud siap pakai.
- Upscaling foto benar-benar memakai AI hanya jika `realesrgan-ncnn-vulkan` beserta model `realesrgan-x4plus` terpasang dan dapat diakses server.
- Jika tidak ada, foto diproses dengan Lanczos (bukan AI).
- Video pada starter ini memakai FFmpeg scaling dan frame-rate conversion, bukan AI super-resolution atau AI motion interpolation. Mengubah FPS ke 120/240 tidak menjamin gerakan lebih alami dan dapat menghasilkan artefak.
- Untuk video AI sungguhan, integrasikan model video super-resolution dan frame interpolation (mis. RIFE) pada backend GPU. Perlu GPU yang sesuai, model weights, pengujian, dan pengelolaan antrean.

## Jalankan lokal
Perlu Python 3.11+ dan FFmpeg tersedia di PATH.
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```
Buka http://127.0.0.1:8000/static/index.html

## Jalankan dengan Docker
```bash
docker build -t nova-enhance .
docker run --rm -p 8000:8000 nova-enhance
```
Lalu buka http://localhost:8000/static/index.html

## Catatan produksi
Tambahkan autentikasi, batas ukuran upload, penyimpanan terisolasi, penghapusan file otomatis, job queue, rate limit, HTTPS, dan worker GPU sebelum dipublikasikan ke internet. Jangan gunakan server development `--reload` untuk produksi.
