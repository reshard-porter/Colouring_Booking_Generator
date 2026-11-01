"""Optional short vertical promotional video (silent MP4) rendered locally with FFmpeg.

It shows simulated page movement (page reveal, coloring reveal, gentle zoom). It is not character
animation, the printed book does not move, and the video is not part of a Kindle product."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import FONT_DIR
from .db import new_id
from .imaging import apply_operation, open_flat
from .jobs import handler

W, H, FPS = 1080, 1920, 30


def available() -> dict:
    ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ff or not fp:
        return {"available": False, "reason": "FFmpeg/ffprobe were not found on PATH. Install FFmpeg to enable promo videos; "
                                              "book exports are unaffected."}
    return {"available": True, "ffmpeg": "found on PATH"}


def _font(size):
    return ImageFont.truetype(str(FONT_DIR / "DejaVuSans-Bold.ttf"), size)


def _page_card(art: Image.Image, scale: float) -> Image.Image:
    pw = int(860 * scale)
    ph = int(pw * 11 / 8.5)
    page = Image.new("RGB", (pw, ph), "white")
    a = art.copy()
    a.thumbnail((int(pw * 0.88), int(ph * 0.88)), Image.LANCZOS)
    page.paste(a, ((pw - a.width) // 2, (ph - a.height) // 2))
    return page


def _frame(bg, title, caption, card, reveal: float, colored: Image.Image | None, color_mix: float, zoom: float):
    f = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(f)
    ft = _font(64)
    tw = d.textlength(title, font=ft)
    d.text(((W - tw) / 2, 120), title, font=ft, fill=(29, 53, 87))
    c = card if colored is None or color_mix <= 0 else Image.blend(card, colored, min(1, color_mix))
    if zoom != 1:
        c = c.resize((int(c.width * zoom), int(c.height * zoom)), Image.LANCZOS)
    x, y = (W - c.width) // 2, 300 + (1180 - c.height) // 2
    visible = int(c.height * max(0.0, min(1.0, reveal)))
    if visible > 0:
        shadow = Image.new("RGB", (c.width, visible), (0, 0, 0))
        f.paste(Image.blend(Image.new("RGB", shadow.size, bg), shadow, 0.18), (x + 14, y + 16))
        f.paste(c.crop((0, 0, c.width, visible)), (x, y))
    fc = _font(40)
    for i, line in enumerate(caption.split("\n")):
        lw = d.textlength(line, font=fc)
        d.text(((W - lw) / 2, 1620 + i * 56), line, font=fc, fill=(29, 53, 87))
    fs = _font(26)
    note = "Preview video – the printed book contains black-and-white line art."
    d.text(((W - d.textlength(note, font=fs)) / 2, 1840), note, font=fs, fill=(70, 90, 110))
    return f


def render_promo(images: list[Image.Image], title: str, captions: list[str], duration_s: float, out: Path, progress=None, cancelled=None) -> dict:
    av = available()
    if not av["available"]:
        raise RuntimeError(av["reason"])
    bg = (143, 211, 244)
    frames_total = int(duration_s * FPS)
    per = max(1, frames_total // len(images))
    cards = []
    for im in images:
        line = im.convert("L")
        card = _page_card(line.convert("RGB"), 1.0)
        colored = _page_card(apply_operation(line, {"type": "colorize"}), 1.0)
        cards.append((card, colored))
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    n = 0
    try:
        for idx, (card, colored) in enumerate(cards):
            cap = captions[idx % len(captions)] if captions else ""
            count = per if idx < len(cards) - 1 else frames_total - per * (len(cards) - 1)
            for k in range(count):
                if cancelled and k % 15 == 0 and cancelled():
                    raise InterruptedError()
                t = k / max(1, count - 1)
                reveal = min(1.0, t / 0.3)
                mix = 0.0 if t < 0.4 else min(1.0, (t - 0.4) / 0.3)
                zoom = 1.0 + 0.06 * t
                proc.stdin.write(_frame(bg, title, cap, card, reveal, colored, mix, zoom).tobytes())
                n += 1
                if progress and n % 15 == 0:
                    progress(n / frames_total, f"Frame {n} of {frames_total}")
        proc.stdin.close()
        err = proc.stderr.read().decode()
        if proc.wait() != 0:
            raise RuntimeError(f"FFmpeg failed: {err[-500:]}")
    except BaseException:
        proc.kill()
        out.unlink(missing_ok=True)
        raise
    return verify_mp4(out, duration_s)


def verify_mp4(path: Path, expected_s: float) -> dict:
    p = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
                       capture_output=True, text=True, check=True)
    info = json.loads(p.stdout)
    v = [s for s in info["streams"] if s["codec_type"] == "video"]
    a = [s for s in info["streams"] if s["codec_type"] == "audio"]
    dec = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], capture_output=True, text=True)
    dur = float(info["format"]["duration"])
    res = {"width": v[0]["width"], "height": v[0]["height"], "codec": v[0]["codec_name"], "duration_s": round(dur, 2),
           "audio_streams": len(a), "decode_ok": dec.returncode == 0 and not dec.stderr.strip(), "size_bytes": path.stat().st_size}
    res["ok"] = (res["width"], res["height"]) == (W, H) and res["decode_ok"] and abs(dur - expected_s) < 0.5 and not a
    return res


@handler("promo_video")
def promo_job(studio, ctx, params) -> dict:
    pid = ctx.job["project_id"]
    pages = [p for p in studio.pages(pid) if p["kind"] == "illustration" and p["approved"]]
    vids = [e["asset_version_id"] for p in pages for e in p["elements"] if e["kind"] == "image"][: int(params.get("max_pages", 4))]
    if not vids:
        raise RuntimeError("Approve at least one illustration page first; the promo uses approved artwork only.")
    images = [open_flat(studio.version_bytes(v)) for v in vids]
    out_dir = studio.settings.exports_dir / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    vid_id = new_id("vid")
    out = out_dir / f"{vid_id}.mp4"
    spec = studio.spec(pid)
    captions = [c for c in params.get("captions", []) if c] or [f"{len(pages)} pages of island fun", "Big shapes for little hands"]
    try:
        res = render_promo(images, params.get("title") or spec["title"], captions, float(params.get("duration_s", 12)), out,
                           progress=lambda f, l: ctx.progress(f, l), cancelled=ctx.cancelled)
    except InterruptedError:
        from .jobs import JobCancelled
        raise JobCancelled()
    if not res["ok"]:
        raise RuntimeError(f"Video verification failed: {res}")
    return {"video_id": vid_id, "file": out.name, "verification": res}
