"""
Erzeugt das Bildmaterial für "Interaktiv animierte Scheibe" – Variante Rennrad.

  1) Vorderrad und Hinterrad: je 60 Einzelbilder (0°, 6°, ... 354°)  -> img/vorderrad/, img/hinterrad/
  2) Rahmen-Overlay (transparentes PNG, liegt ÜBER den Rädern)        -> img/rahmen.png
  3) Positionen der Räder als CSS (aus derselben Geometrie)           -> bike-layout.css
  4) Sprite-Sheet eines hüpfenden Hasen (12 Frames, 1 Zeile)          -> img/hase_sprite.png

Ausgangsmaterial der Räder: img/quelle/Vorderrad.png, img/quelle/Hinterrad.png (KI-generiert).
Der Rahmen wird vollständig hier im Skript gezeichnet.

Warum 6°-Schritte? Beide Räder haben 24 Speichen, das Speichenbild wiederholt sich also alle 15°.
Bei 15°-Schritten sähen alle Frames bis auf Logo und Ventil gleich aus; bei 10° liefen die
Speichen scheinbar rückwärts (Wagenrad-Effekt). 6° liegt unter der halben Periode (7,5°),
dadurch laufen Speichen, Logo und Ventil sichtbar in dieselbe Richtung.

Aufruf:  python3 tools/generate_assets.py     (benötigt Pillow, NumPy, SciPy)
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT, "img", "quelle")
OUT_SPRITE = os.path.join(ROOT, "img", "hase_sprite.png")
OUT_FRAME = os.path.join(ROOT, "img", "rahmen.png")
OUT_CSS = os.path.join(ROOT, "bike-layout.css")

SS = 4                   # Supersampling (Hase)
FRAMES = 60
STEP = 360 / FRAMES      # 6°
WHEEL_PX = 600           # Kantenlänge eines Rad-Frames

# ------------------------------------------------------------------ Geometrie (mm)
# Ursprung = Hinterradachse, x nach rechts (Fahrtrichtung), y nach oben.
R_TIRE = 340             # Außenradius 700c-Reifen
REAR = (0, 0)
FRONT = (990, 0)         # Radstand 990 mm
BB = (404, -70)          # Tretlager: Kettenstrebe ~410 mm, Absenkung 70 mm
HT_TOP = (789, 490)      # Stack 560 / Reach 385 ab Tretlager
HT_ANGLE = 73            # Lenkwinkel
HT_LEN = 150
ST_ANGLE = 73.5          # Sitzwinkel
ST_LEN = 540

X_MIN, X_MAX = -380, 1380
Y_MIN, Y_MAX = -370, 700
FRAME_W = 1600           # Pixelbreite des Rahmen-PNGs
PX_PER_MM = FRAME_W / (X_MAX - X_MIN)
FRAME_H = round((Y_MAX - Y_MIN) * PX_PER_MM)


# ================================================================== Laufräder
def fit_circle(points):
    p = np.asarray(points, float)
    a = np.c_[2 * p, np.ones(len(p))]
    b = (p ** 2).sum(1)
    sx, sy, k = np.linalg.lstsq(a, b, rcond=None)[0]
    return sx, sy, math.sqrt(k + sx * sx + sy * sy)


def tire_circle(gray):
    """Außenkante des Reifens: pro Richtung den äußersten dunklen Pixel suchen, Kreis fitten."""
    h, w = gray.shape
    ys, xs = np.where(gray < 90)
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    r0 = max(xs.max() - xs.min(), ys.max() - ys.min()) / 2
    pts = []
    for t in np.linspace(0, 2 * math.pi, 720, endpoint=False):
        for r in np.arange(r0 + 25, r0 - 40, -1):
            x, y = int(round(cx + r * math.cos(t))), int(round(cy + r * math.sin(t)))
            if 0 <= x < w and 0 <= y < h and gray[y, x] < 90:
                pts.append((x, y))
                break
    return fit_circle(pts)


def hub_center(img_l, guess, search=12):
    """Nabenmitte über Rotationssymmetrie: der Punkt, um den die Nabe beim Drehen am wenigsten 'eiert'."""
    best = None
    for dx in range(-search, search + 1):
        for dy in range(-search, search + 1):
            cx, cy = guess[0] + dx, guess[1] + dy
            box = (int(cx) - 60, int(cy) - 60, int(cx) + 60, int(cy) + 60)
            crop = img_l.crop(box)
            lx, ly = cx - box[0], cy - box[1]
            a = np.asarray(crop, float)
            yy, xx = np.mgrid[0:120, 0:120]
            m = (xx - lx) ** 2 + (yy - ly) ** 2 < 40 ** 2
            err = sum(np.abs(a - np.asarray(crop.rotate(th, Image.BILINEAR, center=(lx, ly)), float))[m].mean()
                      for th in (40, 90, 150))
            if best is None or err < best[0]:
                best = (err, cx, cy)
    return best[1], best[2]


def prepare_wheel(path):
    """Rad freistellen, Nabe exakt auf die Reifenmitte schieben, quadratisch zuschneiden."""
    src = Image.open(path).convert("RGB")
    rgb = np.asarray(src, float)
    gray = np.asarray(src.convert("L"), float)
    tcx, tcy, tr = tire_circle(gray)
    hcx, hcy = hub_center(src.convert("L"), (tcx, tcy))
    off = (hcx - tcx, hcy - tcy)
    print(f"  {os.path.basename(path)}: Reifen-Mitte ({tcx:.1f}|{tcy:.1f}) r={tr:.1f}, "
          f"Naben-Versatz ({off[0]:+.1f}|{off[1]:+.1f}) px -> wird korrigiert")

    # Ziel: Quadrat mit Seitenlänge 2*tr, Mitte = Reifenmitte
    n = int(round(2 * tr))
    yy, xx = np.mgrid[0:n, 0:n].astype(float)
    dx, dy = xx - n / 2, yy - n / 2
    r = np.hypot(dx, dy)
    # Verschiebung nur im Nabenbereich, weich ausgeblendet zu den Speichen hin (Speichen biegen sich unmerklich)
    r1, r2 = 0.30 * tr, 0.58 * tr
    t = np.clip((r - r1) / (r2 - r1), 0, 1)
    wgt = 1 - t * t * (3 - 2 * t)
    sx = tcx + dx + off[0] * wgt
    sy = tcy + dy + off[1] * wgt
    out = np.stack([ndimage.map_coordinates(rgb[..., c], [sy, sx], order=3, mode="nearest") for c in range(3)], -1)
    out = np.clip(out, 0, 255)

    # Weißen Hintergrund (zwischen den Speichen und außen) transparent machen
    light = out.mean(-1)
    sat = out.max(-1) - out.min(-1)
    inner = r < 0.30 * tr                         # Bremsscheibe/Kassette: nur reines Weiß entfernen
    lo = np.where(inner, 246, 228)
    hi = np.where(inner, 253, 247)
    alpha = np.clip((hi - light) / (hi - lo), 0, 1)
    alpha = np.where(sat > 22, 1.0, alpha)
    # Außenkante: weicher Kreis knapp innerhalb der Reifenkante (entfernt hellen Saum)
    edge = np.clip(tr - 2.0 - r, 0, 1)
    alpha = alpha * edge
    # Farbsaum an halbtransparenten Kanten entfernen (weiß herausrechnen)
    a3 = np.maximum(alpha, 1e-3)[..., None]
    out = np.where(alpha[..., None] < 0.999, (out - 255 * (1 - a3)) / a3, out)
    out = np.clip(out, 0, 255)
    rgba = np.dstack([out, alpha * 255]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def make_wheel_frames(src_name, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        os.remove(os.path.join(out_dir, f))
    wheel = prepare_wheel(os.path.join(SRC_DIR, src_name))
    n = wheel.size[0]
    for i in range(FRAMES):
        # PIL dreht gegen den Uhrzeigersinn -> negativer Winkel = Uhrzeigersinn = vorwärts (Rad fährt nach rechts)
        fr = wheel.rotate(-i * STEP, resample=Image.BICUBIC, center=(n / 2, n / 2))
        fr = fr.resize((WHEEL_PX, WHEEL_PX), Image.LANCZOS)
        fr.save(os.path.join(out_dir, f"rad_{i:02d}.webp"), quality=80, method=4)
    print(f"  {FRAMES} Frames -> {os.path.relpath(out_dir, ROOT)}")


# ================================================================== Rahmen
FS = 2  # Supersampling Rahmen


def P(pt):
    """mm -> Pixel (supersampled)."""
    return ((pt[0] - X_MIN) * PX_PER_MM * FS, (Y_MAX - pt[1]) * PX_PER_MM * FS)


def mm(v):
    return v * PX_PER_MM * FS


def add(a, b, k=1.0):
    return (a[0] + b[0] * k, a[1] + b[1] * k)


def unit(deg):
    return (math.cos(math.radians(deg)), math.sin(math.radians(deg)))


def tube(d, p1, p2, w1, w2, color):
    """Konisches Rohr von p1 nach p2 (mm), Breiten w1/w2 (mm), runde Enden."""
    a, b = P(p1), P(p2)
    vx, vy = b[0] - a[0], b[1] - a[1]
    ln = math.hypot(vx, vy) or 1
    nx, ny = -vy / ln, vx / ln
    h1, h2 = mm(w1) / 2, mm(w2) / 2
    d.polygon([(a[0] + nx * h1, a[1] + ny * h1), (b[0] + nx * h2, b[1] + ny * h2),
               (b[0] - nx * h2, b[1] - ny * h2), (a[0] - nx * h1, a[1] - ny * h1)], fill=color)
    d.ellipse([a[0] - h1, a[1] - h1, a[0] + h1, a[1] + h1], fill=color)
    d.ellipse([b[0] - h2, b[1] - h2, b[0] + h2, b[1] + h2], fill=color)


def shaded_tube(d, hl, p1, p2, w1, w2, base=(26, 28, 32, 255)):
    """Rohr in Carbon-Schwarz plus schmaler Glanzstreif (auf eigener Ebene hl, wird später weichgezeichnet)."""
    tube(d, p1, p2, w1, w2, base)
    vx, vy = p2[0] - p1[0], p2[1] - p1[1]
    ln = math.hypot(vx, vy) or 1
    nx, ny = -vy / ln, vx / ln
    if ny < 0:                                   # Glanz immer auf der oberen Seite
        nx, ny = -nx, -ny
    o1, o2 = w1 * 0.22, w2 * 0.22
    tube(hl, (p1[0] + nx * o1, p1[1] + ny * o1), (p2[0] + nx * o2, p2[1] + ny * o2), w1 * 0.22, w2 * 0.22,
         (120, 128, 140, 150))


def bezier(p0, p1, p2, n=24):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in np.linspace(0, 1, n)]


def tangent_lines(c1, r1, c2, r2):
    """Äußere Tangenten (oben, unten) zwischen zwei Kreisen – für die Kette."""
    dx, dy = c2[0] - c1[0], c2[1] - c1[1]
    dist = math.hypot(dx, dy)
    base = math.atan2(dy, dx)
    phi = math.acos((r1 - r2) / dist)
    res = []
    for s in (1, -1):
        ang = base + s * phi
        n = (math.cos(ang), math.sin(ang))
        res.append(((c1[0] + n[0] * r1, c1[1] + n[1] * r1), (c2[0] + n[0] * r2, c2[1] + n[1] * r2)))
    return res


def make_frame():
    W, H = FRAME_W * FS, FRAME_H * FS
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    hl_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d, hl = ImageDraw.Draw(img), ImageDraw.Draw(hl_layer)
    dark = (26, 28, 32, 255)
    metal = (150, 154, 160, 255)

    ht_dir = unit(-HT_ANGLE)                      # entlang Steuerrohr nach unten-vorne
    ht_bot = add(HT_TOP, (ht_dir[0] * HT_LEN, ht_dir[1] * HT_LEN))
    st_dir = unit(180 - ST_ANGLE)                 # Sitzrohr nach oben-hinten
    st_top = add(BB, st_dir, ST_LEN)
    seat_junction = add(BB, st_dir, 415)
    up = (-ht_dir[0], -ht_dir[1])

    # --- Kette (hinter Kurbel, über Kassette)
    chain_r_rear, chain_r_front = 46, 100
    for a, b in tangent_lines(REAR, chain_r_rear, BB, chain_r_front):
        d.line([P(a), P(b)], fill=(58, 60, 66, 255), width=int(mm(7)))
        d.line([P(a), P(b)], fill=(110, 114, 120, 255), width=max(1, int(mm(2))))

    # --- Hinterbau
    shaded_tube(d, hl, REAR, BB, 22, 32)                          # Kettenstrebe
    shaded_tube(d, hl, REAR, seat_junction, 17, 22)               # Sitzstrebe
    # --- Hauptrahmen
    shaded_tube(d, hl, BB, add(ht_bot, up, 18), 60, 50)           # Unterrohr
    shaded_tube(d, hl, BB, st_top, 40, 36)                        # Sitzrohr
    shaded_tube(d, hl, add(st_top, st_dir, -22), add(HT_TOP, ht_dir, 24), 34, 38)   # Oberrohr
    shaded_tube(d, hl, HT_TOP, ht_bot, 46, 56)                    # Steuerrohr
    # Gabel (gebogen, verjüngt)
    crown = add(ht_bot, ht_dir, 8)
    mid = add(ht_bot, ht_dir, 0.62 * 370)
    pts = bezier(crown, (mid[0] + 10, mid[1]), FRONT)
    for k in range(len(pts) - 1):
        w1 = 38 - 18 * k / (len(pts) - 1)
        w2 = 38 - 18 * (k + 1) / (len(pts) - 1)
        shaded_tube(d, hl, pts[k], pts[k + 1], w1, w2)

    # Schriftzug auf dem Unterrohr
    dt_a, dt_b = BB, add(ht_bot, up, 18)
    ang = math.degrees(math.atan2(dt_b[1] - dt_a[1], dt_b[0] - dt_a[0]))
    label = Image.new("RGBA", (int(mm(330)), int(mm(40))), (0, 0, 0, 0))
    ld = ImageDraw.Draw(label)
    try:
        f = ImageFont.truetype("DejaVuSans-Bold.ttf", int(mm(26)))
    except OSError:
        f = ImageFont.load_default()
    ld.text((label.width / 2, label.height / 2), "BHT  BERLIN", font=f, fill=(205, 210, 216, 255), anchor="mm")
    label = label.rotate(ang, expand=True, resample=Image.BICUBIC)
    c = P(add(dt_a, ((dt_b[0] - dt_a[0]) * 0.55, (dt_b[1] - dt_a[1]) * 0.55)))
    img.alpha_composite(label, (int(c[0] - label.width / 2), int(c[1] - label.height / 2)))

    # --- Sattelstütze + Sattel
    post_top = add(st_top, st_dir, 150)
    tube(d, add(st_top, st_dir, -30), post_top, 28, 26, (40, 42, 47, 255))
    tube(d, add(st_top, st_dir, -6), add(st_top, st_dir, 10), 44, 44, dark)      # Sattelklemme
    sx, sy = post_top
    saddle = [(sx - 150, sy + 18), (sx - 135, sy + 32), (sx - 40, sy + 30), (sx + 60, sy + 22),
              (sx + 125, sy + 16), (sx + 128, sy + 10), (sx + 60, sy + 8), (sx - 40, sy + 6), (sx - 140, sy + 6)]
    d.polygon([P(p) for p in saddle], fill=(22, 23, 26, 255))
    d.line([P((sx - 110, sy + 6)), P((sx + 70, sy + 6))], fill=metal, width=int(mm(6)))

    # --- Steuersatz-Spacer, Vorbau, Lenker
    steer_top = add(HT_TOP, up, 30)
    tube(d, HT_TOP, steer_top, 40, 38, (36, 38, 43, 255))
    stem_end = add(add(HT_TOP, up, 18), unit(-6), 110)
    shaded_tube(d, hl, add(HT_TOP, up, 18), stem_end, 38, 34)
    bx, by = stem_end
    bar = [(bx, by), (bx + 40, by - 4), (bx + 70, by - 14), (bx + 86, by - 40), (bx + 86, by - 80),
           (bx + 70, by - 112), (bx + 40, by - 126), (bx, by - 124)]
    for k in range(len(bar) - 1):
        tube(d, bar[k], bar[k + 1], 26, 26, (20, 21, 24, 255))
    # Bremsgriff/Schalthebel
    hood = [(bx + 58, by - 2), (bx + 92, by + 6), (bx + 100, by - 10), (bx + 96, by - 60),
            (bx + 84, by - 70), (bx + 78, by - 30)]
    d.polygon([P(p) for p in hood], fill=(34, 36, 40, 255))
    tube(d, (bx, by), (bx, by), 34, 34, (40, 42, 47, 255))                    # Lenkerklemmung

    # --- Bremssättel
    for center, deg in ((FRONT, 118), (REAR, 4)):
        cpt = add(center, unit(deg), 96)
        tube(d, add(cpt, unit(deg + 90), -26), add(cpt, unit(deg + 90), 26), 30, 30, (44, 46, 52, 255))

    # --- Kurbel, Kettenblatt (eigene Ebene, damit das Loch im Kettenblatt den Rahmen nicht löscht)
    ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    cbb = P(BB)
    for r_mm, col in ((104, (54, 56, 62, 255)), (96, (30, 32, 36, 255)), (70, (0, 0, 0, 0))):
        rr = mm(r_mm)
        rd.ellipse([cbb[0] - rr, cbb[1] - rr, cbb[0] + rr, cbb[1] + rr], fill=col)
    for k in range(4):
        tube(rd, BB, add(BB, unit(45 + k * 90), 72), 20, 14, (40, 42, 47, 255))
    img.alpha_composite(ring)
    d = ImageDraw.Draw(img)
    crank_end = add(BB, unit(-62), 172)
    shaded_tube(d, hl, BB, crank_end, 30, 22, base=(32, 34, 38, 255))
    tube(d, add(crank_end, (-45, 0)), add(crank_end, (45, 0)), 18, 18, (24, 25, 28, 255))   # Pedal
    tube(d, BB, BB, 34, 34, metal)

    # --- Ausfallenden + Steckachsen (statisch, verdecken die Nabenmitte)
    for c in (REAR, FRONT):
        tube(d, c, c, 40, 40, dark)
        tube(d, c, c, 26, 26, metal)
        tube(d, c, c, 14, 14, (60, 62, 68, 255))

    hl_layer = hl_layer.filter(ImageFilter.GaussianBlur(mm(3)))
    # Glanz nur dort, wo Rahmen ist
    mask = img.split()[3]
    a = Image.fromarray(np.minimum(np.asarray(hl_layer.split()[3]), np.asarray(mask)))
    hl_layer.putalpha(a)
    img.alpha_composite(hl_layer)
    img = img.resize((FRAME_W, FRAME_H), Image.LANCZOS)
    img.save(OUT_FRAME, optimize=True)
    print(f"  Rahmen-Overlay {FRAME_W}x{FRAME_H}px -> img/rahmen.png")


def write_layout_css():
    """Positionen der Räder in Prozent der Bühne – exakt aus derselben Geometrie wie der Rahmen."""
    w, h = X_MAX - X_MIN, Y_MAX - Y_MIN

    def box(c):
        return ((c[0] - R_TIRE - X_MIN) / w * 100, (Y_MAX - (c[1] + R_TIRE)) / h * 100)

    rl, rt = box(REAR)
    fl, ft = box(FRONT)
    size = 2 * R_TIRE / w * 100
    ground = (Y_MAX - (-R_TIRE)) / h * 100
    css = f"""/* automatisch erzeugt von tools/generate_assets.py – nicht von Hand ändern */
.bike {{ aspect-ratio: {w} / {h}; }}
.wheel {{ width: {size:.4f}%; }}
.wheel-rear  {{ left: {rl:.4f}%; top: {rt:.4f}%; }}
.wheel-front {{ left: {fl:.4f}%; top: {ft:.4f}%; }}
.ground-shadow {{ top: {ground:.4f}%; }}
.ground-shadow-rear  {{ left: {(REAR[0] - X_MIN) / w * 100:.4f}%; }}
.ground-shadow-front {{ left: {(FRONT[0] - X_MIN) / w * 100:.4f}%; }}
"""
    with open(OUT_CSS, "w") as fh:
        fh.write(css)
    print("  Layout -> bike-layout.css")


# ---------------------------------------------------------------- Hase
def ellipse_poly(cx, cy, rx, ry, rot_deg=0, n=48):
    a = math.radians(rot_deg)
    pts = []
    for k in range(n):
        t = 2 * math.pi * k / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        pts.append((cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)))
    return pts


def draw_bunny(S, ear_tilt, leg_stretch):
    """Hase im Profil (schaut nach rechts) auf eigener Ebene, Fußpunkt unten Mitte."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fur = (236, 232, 222)
    line = (60, 58, 66)
    pink = (232, 150, 150)
    w = max(2, S // 110)
    cx, base = S * 0.5, S * 0.96

    # Hinterbein (länger beim Absprung)
    d.polygon(ellipse_poly(cx - S * 0.10, base - S * 0.08, S * 0.17, S * 0.06 + leg_stretch * S * 0.03, 15 + leg_stretch * 25),
              fill=fur, outline=line, width=w)
    # Körper
    d.polygon(ellipse_poly(cx - S * 0.02, base - S * 0.25, S * 0.25, S * 0.19, -12), fill=fur, outline=line, width=w)
    # Schwanz
    d.ellipse([cx - S * 0.31, base - S * 0.36, cx - S * 0.19, base - S * 0.24], fill=(255, 255, 255), outline=line, width=w)
    # Vorderpfote
    d.polygon(ellipse_poly(cx + S * 0.15, base - S * 0.06 - leg_stretch * S * 0.02, S * 0.07, S * 0.04, -10),
              fill=fur, outline=line, width=w)
    # Ohren (Neigung abhängig von Bewegung)
    hx, hy = cx + S * 0.20, base - S * 0.45
    for off, tilt in ((-S * 0.035, -28), (S * 0.03, -12)):
        ex, ey = hx + off, hy - S * 0.17
        ang = tilt + ear_tilt
        d.polygon(ellipse_poly(ex, ey, S * 0.05, S * 0.17, ang), fill=fur, outline=line, width=w)
        d.polygon(ellipse_poly(ex, ey + S * 0.01, S * 0.022, S * 0.12, ang), fill=pink)
    # Kopf
    d.ellipse([hx - S * 0.14, hy - S * 0.11, hx + S * 0.14, hy + S * 0.13], fill=fur, outline=line, width=w)
    # Auge, Nase, Wange
    d.ellipse([hx + S * 0.03, hy - S * 0.03, hx + S * 0.07, hy + S * 0.02], fill=line)
    d.ellipse([hx + S * 0.045, hy - S * 0.022, hx + S * 0.058, hy - S * 0.008], fill=(255, 255, 255))
    d.ellipse([hx + S * 0.115, hy + S * 0.03, hx + S * 0.145, hy + S * 0.055], fill=pink)
    d.ellipse([hx - S * 0.01, hy + S * 0.05, hx + S * 0.06, hy + S * 0.09], fill=(245, 200, 195))
    return img


def make_bunny_sheet():
    n, fw, fh = 12, 220, 220
    S = fw * SS
    sheet = Image.new("RGBA", (fw * n, fh), (0, 0, 0, 0))
    jump_h = 0.34          # Sprunghöhe relativ zur Frame-Höhe
    body = int(S * 0.62)   # Hasengröße innerhalb des Frames
    for i in range(n):
        t = i / n
        # Phasen: 0-0.17 Ducken, 0.17-0.83 Flug, 0.83-1 Landen
        if t < 1 / 6:
            p = t * 6
            y, sx, sy, ear, leg = 0, 1 + 0.12 * math.sin(p * math.pi), 1 - 0.14 * math.sin(p * math.pi), 18, 0
        elif t < 5 / 6:
            p = (t - 1 / 6) * 1.5
            y = math.sin(p * math.pi)
            stretch = 0.10 * math.cos(p * math.pi)       # oben gestreckt, unten normal
            sx, sy = 1 - stretch * 0.5, 1 + abs(stretch)
            ear = 30 * math.cos(p * math.pi)             # Ohren hinten beim Steigen, vorne beim Fallen
            leg = max(0, math.cos(p * math.pi))
        else:
            p = (t - 5 / 6) * 6
            y, sx, sy, ear, leg = 0, 1 + 0.16 * math.sin(p * math.pi), 1 - 0.18 * math.sin(p * math.pi), 10, 0

        frame = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ground = S * 0.93
        # Bodenschatten (kleiner/heller je höher)
        k = 1 - 0.55 * y
        sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(sh).ellipse([S / 2 - S * 0.2 * k, ground - S * 0.03 * k,
                                    S / 2 + S * 0.2 * k, ground + S * 0.03 * k],
                                   fill=(20, 30, 40, int(110 * k)))
        frame.alpha_composite(sh.filter(ImageFilter.GaussianBlur(S * 0.012)))

        bunny = draw_bunny(body, ear, leg)
        bw, bh = int(body * sx), int(body * sy)
        bunny = bunny.resize((bw, bh), Image.LANCZOS)
        x0 = int(S / 2 - bw / 2)
        y0 = int(ground - bh - y * jump_h * S)
        frame.alpha_composite(bunny, (x0, y0))

        frame = frame.resize((fw, fh), Image.LANCZOS)
        sheet.alpha_composite(frame, (i * fw, 0))
    sheet.save(OUT_SPRITE, optimize=True)
    print(f"Hasen-Sprite-Sheet ({n} x {fw}x{fh}px) -> {OUT_SPRITE}")


if __name__ == "__main__":
    import sys
    if "--nur-rahmen" in sys.argv:
        make_frame()
        write_layout_css()
        sys.exit()
    print("Laufräder:")
    make_wheel_frames("Vorderrad.png", os.path.join(ROOT, "img", "vorderrad"))
    make_wheel_frames("Hinterrad.png", os.path.join(ROOT, "img", "hinterrad"))
    print("Rahmen:")
    make_frame()
    write_layout_css()
    print("Hase:")
    make_bunny_sheet()
