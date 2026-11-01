"""Procedural DEMONSTRATION line art for the seeded sample project.

These drawings are produced by this file's code (simple shapes: ellipses, polygons, arcs). They
are not AI output and are not commercially reviewed artwork. They exist so the sample book can be
exported end-to-end; the owner should replace them with their own or properly licensed art.
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw

W_DESIGN, H_DESIGN = 1000, 1333
SUPERSAMPLE = 2
LINE = 6.0  # design units -> ~13 px at 300 DPI after downsampling

ANIMALS = ["turtle", "crab", "parrot", "monkey", "frog", "piglet", "bunny", "kitten"]
SCENES = ["palm_beach", "sandcastle", "surfing", "sailboat", "beach_umbrella"]
SCENE_TEXT = {
    "palm_beach": ("waving hello", "a sunny beach with a palm tree and seashells"),
    "sandcastle": ("building a sandcastle", "the sandy shore with a bucket and spade"),
    "surfing": ("riding a surfboard", "a big rolling wave under the sun"),
    "sailboat": ("sailing a little boat", "calm sea with fluffy clouds"),
    "beach_umbrella": ("enjoying an ice cream", "under a striped beach umbrella with a beach ball"),
}


class Pen:
    def __init__(self, px_w: int, px_h: int):
        self.k = px_w * SUPERSAMPLE / W_DESIGN
        self.im = Image.new("L", (px_w * SUPERSAMPLE, px_h * SUPERSAMPLE), 255)
        self.d = ImageDraw.Draw(self.im)
        self.lw = max(2, int(round(LINE * self.k)))

    def p(self, x, y):
        return (x * self.k, y * self.k)

    def ellipse(self, cx, cy, rx, ry, fill=255, width=None):
        w = self.lw if width is None else max(1, int(width * self.k))
        self.d.ellipse([self.p(cx - rx, cy - ry), self.p(cx + rx, cy + ry)], fill=fill, outline=0, width=w)

    def dot(self, cx, cy, r):
        self.d.ellipse([self.p(cx - r, cy - r), self.p(cx + r, cy + r)], fill=0)

    def poly(self, pts, fill=255, width=None):
        w = self.lw if width is None else max(1, int(width * self.k))
        self.d.polygon([self.p(*q) for q in pts], fill=fill, outline=0, width=w)

    def line(self, pts, width=None):
        w = self.lw if width is None else max(1, int(width * self.k))
        self.d.line([self.p(*q) for q in pts], fill=0, width=w, joint="curve")
        for q in (pts[0], pts[-1]):
            r = w / 2 / self.k
            self.dot(q[0], q[1], r * 0.95)

    def arc(self, cx, cy, rx, ry, a0, a1, width=None):
        pts = [(cx + rx * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a)))
               for a in _frange(a0, a1, 4)]
        self.line(pts, width)

    def rect(self, x, y, w, h, fill=255):
        self.poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], fill)

    def finish(self, px_w, px_h) -> Image.Image:
        return self.im.resize((px_w, px_h), Image.LANCZOS)


def _frange(a, b, step):
    n = max(2, int(abs(b - a) / step) + 1)
    return [a + (b - a) * i / (n - 1) for i in range(n)]


# --- faces & animals ----------------------------------------------------------------------

def face(pen: Pen, cx, cy, s, d=1, cheeks=True):
    for ex in (-0.32, 0.32):
        x = cx + ex * s + 0.05 * s * d
        pen.ellipse(x, cy - 0.1 * s, 0.11 * s, 0.14 * s, fill=0)
        pen.ellipse(x + 0.035 * s, cy - 0.15 * s, 0.035 * s, 0.035 * s, fill=255, width=1)
    pen.arc(cx + 0.05 * s * d, cy + 0.12 * s, 0.22 * s, 0.14 * s, 15, 165)
    if cheeks:
        for ex in (-0.55, 0.6):
            pen.ellipse(cx + ex * s, cy + 0.12 * s, 0.1 * s, 0.07 * s)


def draw_animal(pen: Pen, kind: str, cx: float, cy: float, s: float, d: int = 1, pose: str = "stand"):
    """Draw an original cartoon animal whose body center is (cx, cy); s ~ head radius."""
    if kind == "turtle":
        for lx in (-0.9, 0.9):
            pen.ellipse(cx + lx * s, cy + 0.85 * s, 0.32 * s, 0.25 * s)
        pen.ellipse(cx + 1.5 * s * d, cy - 0.1 * s, 0.6 * s, 0.55 * s)  # head
        face(pen, cx + 1.55 * s * d, cy - 0.12 * s, 0.6 * s, d, cheeks=False)
        pen.poly([(cx - 1.3 * s, cy + 0.6 * s)] + [(cx + 1.3 * s * math.cos(math.radians(a)), cy + 0.6 * s - 1.25 * s * math.sin(math.radians(a))) for a in range(0, 181, 10)])
        pen.poly([(cx - 0.35 * s, cy - 0.35 * s), (cx + 0.35 * s, cy - 0.35 * s), (cx + 0.5 * s, cy + 0.1 * s), (cx, cy + 0.4 * s), (cx - 0.5 * s, cy + 0.1 * s)])
        pen.line([(cx - 1.3 * s, cy + 0.6 * s), (cx + 1.3 * s, cy + 0.6 * s)])
    elif kind == "crab":
        for i in range(3):
            for sd in (-1, 1):
                x0 = cx + sd * 0.9 * s
                pen.line([(x0, cy + (0.1 + i * 0.25) * s), (x0 + sd * 0.6 * s, cy + (0.3 + i * 0.3) * s), (x0 + sd * 0.7 * s, cy + (0.75 + i * 0.25) * s)])
        for sd in (-1, 1):
            pen.line([(cx + sd * 0.8 * s, cy - 0.3 * s), (cx + sd * 1.4 * s, cy - 0.9 * s)])
            pen.poly([(cx + sd * 1.15 * s, cy - 1.0 * s), (cx + sd * 1.45 * s, cy - 1.55 * s), (cx + sd * 1.55 * s, cy - 1.15 * s), (cx + sd * 1.85 * s, cy - 1.45 * s), (cx + sd * 1.75 * s, cy - 0.75 * s), (cx + sd * 1.35 * s, cy - 0.6 * s)])
            pen.line([(cx + sd * 0.3 * s, cy - 0.6 * s), (cx + sd * 0.35 * s, cy - 1.15 * s)])
            pen.ellipse(cx + sd * 0.35 * s, cy - 1.25 * s, 0.2 * s, 0.22 * s)
            pen.ellipse(cx + sd * 0.35 * s, cy - 1.25 * s, 0.08 * s, 0.1 * s, fill=0)
        pen.ellipse(cx, cy, 1.05 * s, 0.7 * s)
        pen.arc(cx, cy + 0.05 * s, 0.35 * s, 0.22 * s, 15, 165)
    elif kind == "parrot":
        pen.poly([(cx - 0.2 * s * d, cy + 0.9 * s), (cx - 0.7 * s * d, cy + 2.0 * s), (cx - 0.2 * s * d, cy + 1.9 * s), (cx + 0.2 * s * d, cy + 0.9 * s)])
        pen.ellipse(cx, cy + 0.3 * s, 0.75 * s, 1.0 * s)
        pen.ellipse(cx - 0.25 * s * d, cy + 0.35 * s, 0.45 * s, 0.7 * s)
        pen.ellipse(cx + 0.15 * s * d, cy - 0.95 * s, 0.75 * s, 0.7 * s)
        pen.poly([(cx + 0.75 * s * d, cy - 1.05 * s), (cx + 1.35 * s * d, cy - 0.85 * s), (cx + 0.85 * s * d, cy - 0.45 * s)])
        pen.ellipse(cx + 0.35 * s * d, cy - 1.1 * s, 0.13 * s, 0.15 * s, fill=0)
        pen.ellipse(cx + 0.39 * s * d, cy - 1.16 * s, 0.04 * s, 0.04 * s, fill=255, width=1)
        for lx in (-0.25, 0.25):
            pen.line([(cx + lx * s, cy + 1.25 * s), (cx + lx * s, cy + 1.55 * s)])
    elif kind == "monkey":
        pen.arc(cx - 1.1 * s * d, cy + 0.6 * s, 0.5 * s, 0.6 * s, -90, 200)
        pen.ellipse(cx, cy + 0.9 * s, 0.8 * s, 0.85 * s)
        pen.ellipse(cx, cy + 1.0 * s, 0.5 * s, 0.55 * s)
        for sd in (-1, 1):
            pen.ellipse(cx + sd * 0.6 * s, cy + 1.75 * s, 0.32 * s, 0.2 * s)
            pen.ellipse(cx + sd * 1.0 * s, cy - 0.85 * s, 0.32 * s, 0.32 * s)
            pen.ellipse(cx + sd * 1.0 * s, cy - 0.85 * s, 0.16 * s, 0.16 * s)
        pen.ellipse(cx, cy - 0.85 * s, 0.95 * s, 0.85 * s)
        pen.ellipse(cx, cy - 0.65 * s, 0.7 * s, 0.55 * s)
        face(pen, cx, cy - 0.75 * s, 0.6 * s, d, cheeks=False)
    elif kind == "frog":
        for sd in (-1, 1):
            pen.ellipse(cx + sd * 0.9 * s, cy + 0.85 * s, 0.55 * s, 0.3 * s)
        pen.ellipse(cx, cy + 0.3 * s, 1.15 * s, 0.85 * s)
        pen.ellipse(cx, cy + 0.45 * s, 0.6 * s, 0.5 * s)
        for sd in (-1, 1):
            pen.ellipse(cx + sd * 0.55 * s, cy - 0.55 * s, 0.4 * s, 0.4 * s)
            pen.ellipse(cx + sd * 0.55 * s, cy - 0.55 * s, 0.16 * s, 0.2 * s, fill=0)
        pen.arc(cx, cy - 0.05 * s, 0.6 * s, 0.25 * s, 10, 170)
    elif kind in ("piglet", "bunny", "kitten"):
        pen.ellipse(cx, cy + 1.05 * s, 0.85 * s, 0.9 * s)
        pen.ellipse(cx, cy + 1.15 * s, 0.5 * s, 0.55 * s)
        for sd in (-1, 1):
            pen.ellipse(cx + sd * 0.5 * s, cy + 1.95 * s, 0.32 * s, 0.18 * s)
        if kind == "piglet":
            pen.arc(cx - 0.95 * s * d, cy + 1.2 * s, 0.15 * s, 0.15 * s, 0, 330, width=LINE * 0.9)
            for sd in (-1, 1):
                pen.poly([(cx + sd * 0.45 * s, cy - 1.55 * s), (cx + sd * 1.05 * s, cy - 1.85 * s), (cx + sd * 0.9 * s, cy - 1.1 * s)])
        if kind == "bunny":
            for sd in (-1, 1):
                pen.ellipse(cx + sd * 0.42 * s, cy - 2.1 * s, 0.28 * s, 0.85 * s)
                pen.ellipse(cx + sd * 0.42 * s, cy - 2.05 * s, 0.13 * s, 0.6 * s)
            pen.ellipse(cx - 0.85 * s * d, cy + 1.45 * s, 0.25 * s, 0.25 * s)
        if kind == "kitten":
            pen.arc(cx - 1.25 * s * d, cy + 0.8 * s, 0.4 * s, 0.9 * s, 0, 200)
            for sd in (-1, 1):
                pen.poly([(cx + sd * 0.35 * s, cy - 1.5 * s), (cx + sd * 0.95 * s, cy - 2.0 * s), (cx + sd * 0.95 * s, cy - 1.1 * s)])
                pen.poly([(cx + sd * 0.55 * s, cy - 1.45 * s), (cx + sd * 0.82 * s, cy - 1.7 * s), (cx + sd * 0.82 * s, cy - 1.3 * s)], width=LINE * 0.6)
        pen.ellipse(cx, cy - 0.85 * s, 1.0 * s, 0.85 * s)
        face(pen, cx, cy - 0.85 * s, 0.7 * s, d)
        if kind == "piglet":
            pen.ellipse(cx + 0.05 * s * d, cy - 0.68 * s, 0.25 * s, 0.17 * s)
            for sd in (-1, 1):
                pen.ellipse(cx + 0.05 * s * d + sd * 0.09 * s, cy - 0.68 * s, 0.04 * s, 0.06 * s, fill=0)
        if kind == "kitten":
            for sd in (-1, 1):
                for dy in (-0.05, 0.08):
                    pen.line([(cx + sd * 0.55 * s, cy - 0.75 * s + dy * s), (cx + sd * 1.15 * s, cy - 0.78 * s + dy * 1.6 * s)], width=LINE * 0.5)


# --- scenes -------------------------------------------------------------------------------

def sun(pen, cx, cy, r):
    for a in range(0, 360, 40):
        ra = math.radians(a)
        pen.line([(cx + math.cos(ra) * r * 1.3, cy + math.sin(ra) * r * 1.3), (cx + math.cos(ra) * r * 1.75, cy + math.sin(ra) * r * 1.75)])
    pen.ellipse(cx, cy, r, r)


def cloud(pen, cx, cy, s):
    for dx, dy, r in ((-0.6, 0.1, 0.45), (0, -0.15, 0.6), (0.65, 0.1, 0.45)):
        pen.ellipse(cx + dx * s, cy + dy * s, r * s, r * s * 0.85)
    pen.poly([(cx - 0.95 * s, cy + 0.2 * s), (cx + 1.0 * s, cy + 0.2 * s), (cx + 0.9 * s, cy + 0.45 * s), (cx - 0.9 * s, cy + 0.45 * s)])


def palm(pen, x, ground, h, d=1):
    segs = 6
    for i in range(segs):
        y0 = ground - h * i / segs
        y1 = ground - h * (i + 1) / segs
        bend = lambda y: d * 40 * ((ground - y) / h) ** 2
        pen.poly([(x - 26 + bend(y0), y0), (x + 26 + bend(y0), y0), (x + 22 + bend(y1), y1), (x - 22 + bend(y1), y1)])
    tx, ty = x + d * 40, ground - h
    for a in (200, 240, 290, 330, 20):
        ra = math.radians(a)
        ex, ey = tx + math.cos(ra) * 190, ty + math.sin(ra) * 120 + 40
        mx, my = tx + math.cos(ra) * 95, ty + math.sin(ra) * 60 - 25
        nx, ny = -math.sin(ra) * 28, math.cos(ra) * 28
        pen.poly([(tx, ty), (mx + nx, my + ny), (ex, ey), (mx - nx, my - ny)])
    for dx in (-22, 18):
        pen.ellipse(tx + dx, ty + 30, 22, 22)


def waves(pen, y, x0=60, x1=940, amp=18, n=7):
    step = (x1 - x0) / n
    for i in range(n):
        pen.arc(x0 + step * (i + 0.5), y, step / 2, amp, 180, 360)


def starfish(pen, cx, cy, r):
    pts = []
    for i in range(10):
        rr = r if i % 2 == 0 else r * 0.45
        a = math.radians(-90 + i * 36)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    pen.poly(pts)


def shell(pen, cx, cy, r):
    pen.poly([(cx, cy + r * 0.6)] + [(cx + r * math.cos(math.radians(a)), cy - r * 0.2 + r * 0.8 * math.sin(math.radians(a))) for a in range(180, 361, 15)])
    for dx in (-0.45, 0, 0.45):
        pen.line([(cx, cy + r * 0.55), (cx + dx * r * 1.6, cy - r * 0.75)], width=LINE * 0.6)


def draw_scene(index: int, px_w: int = 2250, px_h: int = 3000) -> Image.Image:
    """Return demonstration design #index (0..39) as a grayscale image."""
    animal = ANIMALS[index % len(ANIMALS)]
    scene = SCENES[(index // len(ANIMALS)) % len(SCENES)]
    rnd = random.Random(1000 + index)
    d = 1 if (index // 3) % 2 == 0 else -1
    pen = Pen(px_w, px_h)
    ground = 1040
    s = 115 if animal not in ("crab", "turtle", "frog") else 125
    ax = 500 + rnd.choice([-120, -60, 60, 120])

    if scene == "palm_beach":
        sun(pen, 820 if d > 0 else 180, 170, 75)
        cloud(pen, 300 if d > 0 else 700, 210, 110)
        pen.line([(40, 700), (960, 700)])
        waves(pen, 760, amp=16)
        palm(pen, 170 if d > 0 else 830, ground - 20, 520, d)
        pen.line([(40, ground), (960, ground)])
        starfish(pen, 820 if d > 0 else 180, ground + 120, 70)
        shell(pen, 640, ground + 170, 55)
        starfish(pen, 300, ground + 180, 45)
        draw_animal(pen, animal, ax + d * 60, ground - 210, s, d)
    elif scene == "sandcastle":
        sun(pen, 160 if d > 0 else 840, 160, 70)
        pen.line([(40, 560), (960, 560)])
        waves(pen, 610, amp=14)
        pen.line([(40, ground), (960, ground)])
        cxs = 650 if d > 0 else 350
        pen.rect(cxs - 170, ground - 260, 340, 260)
        for tx in (-170, 110):
            pen.rect(cxs + tx, ground - 380, 60, 380)
            for k in range(3):
                pen.rect(cxs + tx + k * 20, ground - 405, 20, 25)
        pen.poly([(cxs - 50, ground), (cxs - 50, ground - 110), (cxs, ground - 160), (cxs + 50, ground - 110), (cxs + 50, ground)])
        pen.line([(cxs + 140, ground - 405), (cxs + 140, ground - 520)])
        pen.poly([(cxs + 140, ground - 520), (cxs + 230, ground - 490), (cxs + 140, ground - 460)])
        bx = 200 if d > 0 else 800
        pen.poly([(bx - 80, ground + 40), (bx + 80, ground + 40), (bx + 60, ground + 210), (bx - 60, ground + 210)])
        pen.arc(bx, ground + 40, 80, 70, 180, 360)
        pen.line([(bx + d * 150, ground + 230), (bx + d * 230, ground + 80)])
        pen.poly([(bx + d * 215, ground + 85), (bx + d * 270, ground - 5), (bx + d * 300, ground + 40), (bx + d * 250, ground + 120)])
        draw_animal(pen, animal, (cxs - 330) if d > 0 else (cxs + 330), ground - 200, s * 0.9, d)
        shell(pen, 520, ground + 200, 50)
    elif scene == "surfing":
        sun(pen, 820 if d < 0 else 180, 150, 65)
        for bx in (420, 520):
            pen.arc(bx, 200, 30, 18, 200, 340)
            pen.arc(bx + 58, 200, 30, 18, 200, 340)
        wx = 740 if d > 0 else 260
        pen.line([(40, 860), (960, 860)])
        # rolling curl: outer arc, inner spiral, foam bumps
        pen.arc(wx, 640, 200, 220, 90, 360 if d > 0 else -180)
        pen.arc(wx + d * 30, 610, 120, 130, 0 if d > 0 else 180, 300 if d > 0 else -120)
        pen.arc(wx + d * 45, 600, 50, 55, 0 if d > 0 else 180, 270 if d > 0 else -90)
        for k in range(4):
            pen.arc(wx - d * (40 + k * 70), 860, 35, 25, 180, 360)
        waves(pen, 1100, amp=20, n=6)
        bx0 = 500 - d * 120
        pen.ellipse(bx0, 900, 250, 45)
        pen.line([(bx0 - 190, 900), (bx0 + 190, 900)], width=LINE * 0.7)
        draw_animal(pen, animal, bx0, 900 - 2.0 * s * 0.85 - 20, s * 0.85, d)
    elif scene == "sailboat":
        cloud(pen, 230, 200, 120)
        cloud(pen, 760, 300, 95)
        hx = 500
        pen.line([(hx, 360), (hx, 880)])
        pen.poly([(hx + 10 * d, 380), (hx + 10 * d, 840), (hx + 300 * d, 840)])
        pen.poly([(hx - 10 * d, 470), (hx - 10 * d, 840), (hx - 190 * d, 840)])
        pen.poly([(hx, 360), (hx + 70 * d, 385), (hx, 410)])
        draw_animal(pen, animal, hx - 150 * d, 880 - 1.3 * s * 0.75, s * 0.75, d)
        pen.poly([(180, 880), (820, 880), (720, 1020), (280, 1020)])
        for x in (360, 500, 640):
            pen.ellipse(x, 950, 32, 32)
        waves(pen, 1060, amp=22, n=6)
        waves(pen, 1170, amp=22, n=5, x0=120, x1=880)
        pen.line([(40, 1250), (960, 1250)])
    else:  # beach_umbrella
        ux = 640 if d > 0 else 360
        pen.line([(40, ground), (960, ground)])
        pen.line([(ux, 380), (ux, ground + 60)])
        pts = [(ux - 300, 470)] + [(ux + 300 * math.cos(math.radians(a)), 470 - 230 * math.sin(math.radians(a))) for a in range(180, -1, -10)]
        pen.poly(pts)
        for a in (135, 90, 45):
            ra = math.radians(a)
            pen.line([(ux, 470 - 230), (ux + 300 * math.cos(ra) * 0.98, 470 - 230 * math.sin(ra) * 0.02)], width=LINE * 0.8)
        for i in range(4):
            pen.arc(ux - 225 + i * 150, 470, 75, 30, 0, 180)
        ox = 0 if d > 0 else 280
        pen.poly([(140 + ox, ground + 60), (560 + ox, ground + 40), (600 + ox, ground + 200), (180 + ox, ground + 230)])
        for k in (1, 2):
            pen.line([(140 + ox + k * 140, ground + 55 - k * 7), (180 + ox + k * 140, ground + 225 - k * 9)], width=LINE * 0.8)
        bx, by = (840 if d > 0 else 160), ground + 150
        pen.ellipse(bx, by, 90, 90)
        pen.arc(bx, by, 40, 90, -90, 90)
        pen.arc(bx, by, 40, 90, 90, 270)
        pen.line([(bx - 90, by), (bx + 90, by)], width=LINE * 0.8)
        axx = 300 if d > 0 else 700
        draw_animal(pen, animal, axx, ground - 210, s, d)
        cx_, cy_ = axx + d * 180, ground - 330
        pen.poly([(cx_ - 35, cy_), (cx_ + 35, cy_), (cx_, cy_ + 110)])
        pen.ellipse(cx_, cy_ - 25, 45, 40)
        sun(pen, 160 if d > 0 else 840, 150, 60)
    return pen.finish(px_w, px_h)


def design_description(index: int) -> dict:
    animal = ANIMALS[index % len(ANIMALS)]
    scene = SCENES[(index // len(ANIMALS)) % len(SCENES)]
    action, setting = SCENE_TEXT[scene]
    return {
        "subject": f"A friendly cartoon {animal}",
        "action": action,
        "setting": setting,
        "composition": "character large in the foreground, simple background, bold outlines",
        "complexity": "large enclosed shapes, no gray shading",
        "demo_design_key": f"{animal}-{scene}",
    }
