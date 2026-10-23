#!/usr/bin/env python3
"""
Nyawit Live 3D v5.0 — Authentic ArtStation / Blender Hand-Painted Stylized 2048x2048 Texture Atlas
Generates src/Nyawit.Android/Assets/Textures/nyawit_pbr_atlas.png (4x4 grid of 512x512 tiles).

Designed specifically to match our Blender 4.2 Stylized 3D Asset Pack:
  - Painterly broad brushstrokes & clean gradients (ZERO noisy photorealistic grain!)
  - Hand-painted bevel top highlights & warm cavity shadows on wood planks, bark segments & crates
  - Turquoise cel-reflection cab glass with clear viewport cutouts revealing the 3D cabin seats & steering wheel!
  - Bold feathered stylized palm fronds (lime-to-emerald gradient) that read crisply from 2m to 180m at 60-120 FPS
  - Terracotta 8-spoke inner truck rim + deep chunky stylized tire lugs
"""
import math
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

TILE = 512
ATLAS = TILE * 4  # 2048 x 2048


def smooth_noise(shape, freq, seed=0):
    rng = np.random.default_rng(seed)
    g = rng.random((freq, freq), dtype=np.float32)
    g_pad = np.pad(g, ((0, 1), (0, 1)), mode="wrap")
    ys = np.linspace(0, freq, shape[0], endpoint=False, dtype=np.float32)
    xs = np.linspace(0, freq, shape[1], endpoint=False, dtype=np.float32)
    yi = np.floor(ys).astype(np.int32)
    xi = np.floor(xs).astype(np.int32)
    yf = ys - yi
    xf = xs - xi
    yf = yf * yf * (3.0 - 2.0 * yf)
    xf = xf * xf * (3.0 - 2.0 * xf)
    c00 = g_pad[yi[:, None], xi[None, :]]
    c10 = g_pad[yi[:, None], xi[None, :] + 1]
    c01 = g_pad[yi[:, None] + 1, xi[None, :]]
    c11 = g_pad[yi[:, None] + 1, xi[None, :] + 1]
    top = c00 * (1.0 - xf[None, :]) + c10 * xf[None, :]
    bot = c01 * (1.0 - xf[None, :]) + c11 * xf[None, :]
    return top * (1.0 - yf[:, None]) + bot * yf[:, None]


def painterly_fbm(shape, base_freq=4, octaves=3, seed=1):
    val = np.zeros(shape, dtype=np.float32)
    amp = 0.55
    freq = base_freq
    norm = 0.0
    for o in range(octaves):
        val += amp * smooth_noise(shape, freq, seed + o * 37)
        norm += amp
        amp *= 0.5
        freq *= 2
    return val / norm


def make_grass_tile():
    # Stylized Genshin / Sea-of-Thieves lush meadow grass: broad painterly patches + clover clusters + sunlit lime strokes!
    n1 = painterly_fbm((TILE, TILE), 5, 3, 10)
    n2 = painterly_fbm((TILE, TILE), 12, 2, 22)
    warm_sun = np.clip((n1 - 0.52) * 2.4, 0.0, 1.0)

    r = 46 + n1 * 34 + warm_sun * 36 + n2 * 14
    g = 104 + n1 * 48 + warm_sun * 34 + n2 * 22
    b = 34 + n1 * 18 + warm_sun * 10 + n2 * 10
    arr = np.stack([r, g, b, np.full((TILE, TILE), 255.0, np.float32)], axis=-1)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    dr = ImageDraw.Draw(img)

    # Hand-painted stylized grass blade strokes & tiny sunlit clover dots
    rng = np.random.default_rng(101)
    for _ in range(260):
        bx = rng.uniform(8, TILE - 8)
        by = rng.uniform(12, TILE - 8)
        ln = rng.uniform(9, 18)
        lean = rng.uniform(-5, 5)
        shade = rng.uniform(0.88, 1.24)
        col = (int(min(255, 76 * shade)), int(min(255, 152 * shade)), int(min(255, 46 * shade)), 255)
        dr.polygon([(bx - 2.4, by), (bx + lean, by - ln), (bx + 2.4, by)], fill=col)
    return np.array(img, dtype=np.uint8)


def make_dirt_road_tile():
    # Stylized warm Sumatran terracotta-ochre red clay plantation road with soft tire tracks & rounded stylized stones!
    y, x = np.mgrid[0:TILE, 0:TILE].astype(np.float32) / TILE
    n1 = painterly_fbm((TILE, TILE), 5, 3, 41)
    rut = np.exp(-((x - 0.27) ** 2) / 0.010) + np.exp(-((x - 0.73) ** 2) / 0.010)
    chevron = 0.5 + 0.5 * np.sin((y * 28.0 + np.abs(x - 0.5) * 6.0) * math.tau)
    rut_tex = rut * (0.72 + 0.28 * chevron)

    r = 166 + n1 * 38 - rut_tex * 28
    g = 108 + n1 * 28 - rut_tex * 20
    b = 68 + n1 * 18 - rut_tex * 14
    arr = np.stack([r, g, b, np.full((TILE, TILE), 255.0, np.float32)], axis=-1)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    dr = ImageDraw.Draw(img)
    rng = np.random.default_rng(202)
    for _ in range(55):
        px, py = rng.uniform(10, TILE - 10), rng.uniform(10, TILE - 10)
        pr = rng.uniform(3.5, 7.5)
        dr.ellipse([px - pr, py - pr * 0.75, px + pr, py + pr * 0.75], fill=(132, 92, 64, 255), outline=(198, 148, 108, 255))
    return np.array(img, dtype=np.uint8)


def make_palm_bark_tile():
    # Hand-painted Stylized Tropical Palm Trunk Segments (clean chiseled horizontal bands + warm top bevels, ZERO dark noise!)
    img = Image.new("RGBA", (TILE, TILE), (122, 86, 56, 255))
    dr = ImageDraw.Draw(img)
    n_bands = 9
    band_h = TILE / n_bands
    rng = np.random.default_rng(77)

    for b in range(n_bands):
        y0 = int(b * band_h)
        y1 = int((b + 1) * band_h)
        tone = rng.uniform(0.93, 1.07)
        for py in range(y0, y1):
            t = (py - y0) / max(1, y1 - y0 - 1)
            # Stylized hand-painted gradient per bark ring: bright warm top bevel -> rich medium brown -> dark under-ring AO!
            g_mul = (1.24 - 0.36 * (t ** 0.85)) * tone
            if t < 0.11:
                g_mul = 1.34 * tone
            elif t > 0.90:
                g_mul = 0.62 * tone
            col = (int(min(255, 136 * g_mul)), int(min(255, 96 * g_mul)), int(min(255, 62 * g_mul)), 255)
            dr.line([(0, py), (TILE, py)], fill=col)

        # Subtle painterly vertical bark fissures inside each band
        for _ in range(14):
            fx = rng.uniform(6, TILE - 6)
            dr.line([(fx, y0 + 6), (fx + rng.uniform(-4, 4), y1 - 6)], fill=(96, 66, 42, 160), width=2)
    return np.array(img, dtype=np.uint8)


def make_tbs_fruit_tile():
    # Vibrant Stylized Glossy Crimson-Red & Warm Orange TBS Fruitlets!
    rng = np.random.default_rng(2026)
    py_grid, px_grid = np.mgrid[0:TILE, 0:TILE].astype(np.float32)
    best_h = np.full((TILE, TILE), -1.0, dtype=np.float32)
    rgb = np.zeros((TILE, TILE, 3), dtype=np.float32)
    rgb[:] = [52.0, 10.0, 6.0]

    rows, cols = 12, 12
    for ry in range(-1, rows + 2):
        for cx in range(-1, cols + 2):
            fx = (cx + (ry % 2) * 0.5 + rng.uniform(-0.14, 0.14)) * (TILE / cols)
            fy = (ry + rng.uniform(-0.14, 0.14)) * (TILE / rows)
            rad = (TILE / cols) * rng.uniform(0.56, 0.68)
            x0, x1 = max(0, int(fx - rad - 1)), min(TILE, int(fx + rad + 2))
            y0, y1 = max(0, int(fy - rad - 1)), min(TILE, int(fy + rad + 2))
            if x0 >= x1 or y0 >= y1:
                continue
            dx = (px_grid[y0:y1, x0:x1] - fx) / rad
            dy = (py_grid[y0:y1, x0:x1] - fy) / (rad * 0.94)
            r2 = dx * dx + dy * dy
            mask = r2 < 1.0
            if not np.any(mask):
                continue
            nz = np.sqrt(np.maximum(0.0, 1.0 - r2))
            win = mask & (nz > best_h[y0:y1, x0:x1])
            best_h[y0:y1, x0:x1][win] = nz[win]

            ndl = np.clip(-0.32 * dx - 0.42 * dy + 0.85 * nz, 0.22, 1.0)
            rim_orange = np.clip(1.0 - nz, 0.0, 1.0) ** 1.6
            spec = np.power(np.clip(-0.26 * dx - 0.36 * dy + 0.89 * nz, 0.0, 1.0), 18.0)

            cr = (196 + 56 * rim_orange) * (0.55 + 0.55 * ndl) + spec * 150.0
            cg = (22 + 78 * rim_orange) * (0.55 + 0.55 * ndl) + spec * 115.0
            cb = (10 + 12 * rim_orange) * (0.55 + 0.55 * ndl) + spec * 90.0

            sub = rgb[y0:y1, x0:x1]
            sub[win, 0] = cr[win]
            sub[win, 1] = cg[win]
            sub[win, 2] = cb[win]

    return np.clip(np.concatenate([rgb, np.full((TILE, TILE, 1), 255.0, np.float32)], axis=-1), 0, 255).astype(np.uint8)


def make_palm_frond_alpha_tile():
    # BOLD ARTSTATION STYLIZED FEATHERED PALM FROND (14 chunky overlapping leaflets instead of noisy 1px needles!):
    # Warm golden-lime base -> lush tropical emerald mid-blade -> sunlit lime-gold tip!
    img = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)

    cx = TILE * 0.5
    n_pairs = 15
    for i in range(n_pairs):
        t = (i + 0.45) / n_pairs  # 0 = petiole base (bottom y=TILE), 1 = frond tip (top y=0)
        y0 = TILE * (0.97 - t * 0.93)
        span_profile = math.sin(math.pow(t, 0.58) * math.pi * 0.94)
        half_w = TILE * (0.12 + 0.37 * span_profile)
        droop = TILE * (0.02 + 0.055 * t)
        leaf_thick = (TILE / n_pairs) * 0.98

        # Stylized foliage gradient: rich emerald with golden-lime sun warmth toward tips & spine
        r_c = int(min(255, 68 + 64 * (t ** 1.4)))
        g_c = int(min(255, 148 + 52 * t))
        b_c = int(min(255, 34 + 14 * t))
        edge_c = (int(min(255, r_c * 1.18)), int(min(255, g_c * 1.12)), int(min(255, b_c * 1.10)), 255)

        for side in (-1.0, 1.0):
            mx = cx + side * half_w * 0.58
            my = y0 - droop * 0.25
            tx = cx + side * half_w
            ty = y0 + droop
            pts = [
                (cx - side * 4.0, y0 - leaf_thick * 0.62),
                (mx, my - leaf_thick * 0.50),
                (tx, ty),
                (mx, my + leaf_thick * 0.44),
                (cx - side * 4.0, y0 + leaf_thick * 0.58),
            ]
            dr.polygon(pts, fill=(r_c, g_c, b_c, 255))
            dr.line([(cx, y0 - leaf_thick * 0.42), (mx, my - leaf_thick * 0.38), (tx, ty)], fill=edge_c, width=3)

    # Bold golden-green central rachis spine
    dr.polygon([(cx - 10, TILE), (cx + 10, TILE), (cx + 2, 14), (cx - 2, 14)], fill=(146, 178, 52, 255))
    return np.array(img, dtype=np.uint8)


def make_fern_alpha_tile():
    img = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    for f in range(5):
        ang = -0.68 + f * 0.34
        length = TILE * (0.86 if f % 2 == 0 else 0.94)
        bx, by = TILE * 0.5, TILE * 0.98
        ex, ey = bx + math.sin(ang) * length, by - math.cos(ang * 0.62) * length
        nx, ny = math.cos(ang), math.sin(ang * 0.62)
        dr.polygon([
            (bx - nx * 14, by),
            (bx + math.sin(ang) * length * 0.52 - nx * 48, by - math.cos(ang * 0.62) * length * 0.52 - ny * 48),
            (ex, ey),
            (bx + math.sin(ang) * length * 0.52 + nx * 48, by - math.cos(ang * 0.62) * length * 0.52 + ny * 48),
            (bx + nx * 14, by),
        ], fill=(64 + f * 8, 152 + f * 8, 44, 255))
        dr.line([(bx, by), (ex, ey)], fill=(142, 198, 66, 255), width=4)
    return np.array(img, dtype=np.uint8)


def make_wood_planks_tile():
    # Hand-Painted ArtStation Stylized Meranti Wood Planks (warm golden top bevels, dark plank gaps, painted grain swirls & bolts!)
    img = Image.new("RGBA", (TILE, TILE), (156, 82, 30, 255))
    dr = ImageDraw.Draw(img)
    n_planks = 6
    ph = TILE / n_planks
    rng = np.random.default_rng(313)

    for p in range(n_planks):
        y0 = int(p * ph)
        y1 = int((p + 1) * ph)
        tone = rng.uniform(0.92, 1.09)
        for py in range(y0, y1):
            t = (py - y0) / max(1, y1 - y0 - 1)
            mul = (1.18 - 0.26 * t) * tone
            if t < 0.055 or t > 0.935:
                mul = 0.36  # Deep stylized plank groove
            elif t < 0.145:
                mul = 1.38 * tone  # Crisp warm golden bevel highlight!
            col = (int(min(255, 178 * mul)), int(min(255, 92 * mul)), int(min(255, 34 * mul)), 255)
            dr.line([(0, py), (TILE, py)], fill=col)

        # Painterly wood grain streaks
        for _ in range(5):
            gy = rng.uniform(y0 + 14, y1 - 10)
            gx0 = rng.uniform(0, TILE * 0.45)
            gx1 = gx0 + rng.uniform(90, 240)
            dr.line([(gx0, gy), (min(TILE, gx1), gy + rng.uniform(-3, 3))], fill=(134, 66, 22, 255), width=3)

    # Indonesian red/white safety reflector tape along plank 3 + stylized iron bolts!
    tape_y = int(TILE * 0.50)
    for dash in range(8):
        x0 = dash * (TILE // 8) + 5
        c = (246, 248, 252, 255) if dash % 2 == 0 else (228, 52, 38, 255)
        dr.rounded_rectangle([x0, tape_y - 7, x0 + (TILE // 8) - 10, tape_y + 7], radius=3, fill=c)
    for bx in range(36, TILE, 128):
        for by_i in range(n_planks):
            by = int((by_i + 0.5) * ph)
            dr.ellipse([bx - 6, by - 6, bx + 6, by + 6], fill=(54, 58, 66, 255), outline=(182, 190, 202, 255), width=2)
    return np.array(img, dtype=np.uint8)


def make_tire_and_wheel_tile():
    # Stylized Off-Road Radial Lug Tire + Signature Terracotta 8-Spoke Inner Rim (matches our Blender 4.2 Canter!)
    img = Image.new("RGBA", (TILE, TILE), (30, 33, 38, 255))
    dr = ImageDraw.Draw(img)

    # Left half (0..256): Bold beveled stylized tire tread blocks
    dr.rectangle([0, 0, 255, TILE], fill=(24, 27, 32, 255))
    for row in range(0, TILE, 32):
        dr.rounded_rectangle([10, row + 4, 118, row + 26], radius=5, fill=(52, 57, 65, 255), outline=(78, 85, 96, 255), width=2)
        dr.rounded_rectangle([136, row + 10, 244, row + 30], radius=5, fill=(52, 57, 65, 255), outline=(78, 85, 96, 255), width=2)

    # Right half: Circular wheel centered at (384, 256), radius 126
    cx, cy = 384, 256
    dr.ellipse([cx - 126, cy - 126, cx + 126, cy + 126], fill=(28, 31, 36, 255))
    dr.ellipse([cx - 108, cy - 108, cx + 108, cy + 108], outline=(64, 70, 80, 255), width=5)
    # Recessed dark gunmetal dish + bright silver beadlock rim
    dr.ellipse([cx - 80, cy - 80, cx + 80, cy + 80], fill=(32, 36, 42, 255), outline=(146, 156, 170, 255), width=5)
    # 8 Stylized Terracotta-Red Spokes (exact signature detail from our Blender 4.2 Canter!)
    for i in range(8):
        a = i * math.tau / 8.0
        ca, sa = math.cos(a), math.sin(a)
        px, py = -sa, ca
        dr.polygon([
            (cx + ca * 20 - px * 9, cy + sa * 20 - py * 9),
            (cx + ca * 74 - px * 6, cy + sa * 74 - py * 6),
            (cx + ca * 74 + px * 6, cy + sa * 74 + py * 6),
            (cx + ca * 20 + px * 9, cy + sa * 20 + py * 9),
        ], fill=(196, 68, 42, 255), outline=(238, 118, 78, 255))
    # Central steel hub cap + 6 silver lug bolts
    dr.ellipse([cx - 26, cy - 26, cx + 26, cy + 26], fill=(52, 58, 66, 255), outline=(168, 178, 190, 255), width=3)
    for i in range(6):
        a = i * math.tau / 6.0
        dr.ellipse([cx + math.cos(a) * 16 - 4, cy + math.sin(a) * 16 - 4, cx + math.cos(a) * 16 + 4, cy + math.sin(a) * 16 + 4], fill=(226, 232, 240, 255))
    return np.array(img, dtype=np.uint8)


def make_canter_front_atlas_tile():
    # Top half (y = 0..256): STYLIZED TURQUOISE CEL-REFLECTION GLASS WITH CLEAR CUTOUT VIEWPORT
    # SO PLAYERS SEE THE ACTUAL 3D CAB INTERIOR, TAN RIBBED SEATS, STEERING WHEEL & DRIVER AT ZERO ALPHA BLEND COST!
    img = Image.new("RGBA", (TILE, TILE), (24, 30, 38, 255))
    dr = ImageDraw.Draw(img)

    # Clear transparent center (`alpha = 0`) + Turquoise glass border & crisp diagonal cel-shaded sky reflection slashes (`alpha = 255`)!
    dr.rectangle([0, 0, TILE - 1, 255], fill=(0, 0, 0, 0))
    # Outer rubber gasket + turquoise tinted inner glass rim
    dr.rectangle([0, 0, TILE - 1, 255], outline=(22, 26, 32, 255), width=14)
    dr.rectangle([14, 14, TILE - 15, 241], outline=(58, 178, 192, 255), width=20)
    # Top sky-turquoise visor tint band + crisp diagonal stylized reflection slashes!
    dr.rectangle([14, 14, TILE - 15, 58], fill=(48, 162, 178, 255))
    dr.polygon([(54, 241), (146, 14), (192, 14), (100, 241)], fill=(138, 234, 242, 255))
    dr.polygon([(208, 241), (300, 14), (324, 14), (232, 241)], fill=(96, 206, 218, 255))

    # 2. Stylized Chunky Vertical-Slat Grille + 3-Diamond Crest (0..256, 256..400)
    dr.rectangle([0, 256, 255, 399], fill=(28, 32, 38, 255))
    dr.rounded_rectangle([8, 264, 247, 391], radius=12, fill=(38, 43, 50, 255), outline=(96, 104, 116, 255), width=6)
    for gx in range(28, 236, 24):
        dr.rounded_rectangle([gx - 5, 278, gx + 5, 378], radius=3, fill=(20, 23, 28, 255), outline=(120, 128, 140, 255), width=1)
    cx_g, cy_g = 128, 328
    for pts in [
        [(cx_g, cy_g - 24), (cx_g + 13, cy_g - 4), (cx_g, cy_g + 5), (cx_g - 13, cy_g - 4)],
        [(cx_g - 4, cy_g + 5), (cx_g - 24, cy_g + 20), (cx_g - 17, cy_g + 4)],
        [(cx_g + 4, cy_g + 5), (cx_g + 24, cy_g + 20), (cx_g + 17, cy_g + 4)],
    ]:
        dr.polygon(pts, fill=(238, 244, 252, 255))

    # 3. Stylized Round Glowing Headlamps + Warm Amber Corner Signal (256..512, 256..400)
    dr.rounded_rectangle([256, 256, 511, 399], radius=14, fill=(34, 38, 45, 255), outline=(78, 86, 98, 255), width=6)
    dr.ellipse([282, 268, 404, 388], fill=(255, 244, 188, 255), outline=(255, 252, 232, 255), width=6)
    dr.ellipse([308, 294, 378, 362], fill=(255, 255, 242, 255))
    dr.rounded_rectangle([422, 270, 498, 386], radius=10, fill=(255, 148, 22, 255), outline=(255, 206, 92, 255), width=4)

    # 4. License Plate ("BM 8899 XY") + Warm Amber Lamp (0..512, 400..512)
    dr.rounded_rectangle([4, 404, 338, 508], radius=8, fill=(20, 23, 28, 255), outline=(234, 238, 244, 255), width=5)
    plate_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
    dr.text((52, 430), "BM 8899 XY", font=plate_font, fill=(248, 250, 252, 255))
    dr.rounded_rectangle([344, 404, 508, 508], radius=10, fill=(255, 166, 28, 255), outline=(255, 220, 120, 255), width=5)
    return np.array(img, dtype=np.uint8)


def make_canter_paint_tile():
    # Smooth Rich Stylized Canter Golden-Amber Enamel with Warm Top Highlight Gradient!
    img = Image.new("RGBA", (TILE, TILE), (246, 178, 22, 255))
    dr = ImageDraw.Draw(img)
    for y in range(TILE):
        t = y / (TILE - 1.0)
        r = int(min(255, 252 - 22 * t))
        g = int(min(255, 192 - 34 * t))
        b = int(min(255, 34 - 16 * t))
        dr.line([(0, y), (TILE, y)], fill=(r, g, b, 255))
    dr.rounded_rectangle([350, 340, 456, 392], radius=8, fill=(32, 36, 42, 255), outline=(188, 128, 14, 255), width=3)
    dr.rounded_rectangle([366, 358, 440, 374], radius=4, fill=(84, 90, 100, 255))
    return np.array(img, dtype=np.uint8)


def make_character_atlas_tile():
    # Stylized Expressive Hero Face + Warm Subsurface Skin + Stylized Dark Hair + Stitched Indigo Cargo Denim!
    img = Image.new("RGBA", (TILE, TILE), (212, 152, 112, 255))
    yy, xx = np.mgrid[0:256, 0:256].astype(np.float32) / 255.0
    blush = np.exp(-((yy - 0.56) ** 2) / 0.006) * (np.exp(-((xx - 0.30) ** 2) / 0.008) + np.exp(-((xx - 0.70) ** 2) / 0.008))
    temple = 1.0 - 0.12 * (np.abs(xx - 0.5) * 2.0) ** 2.0

    q0 = np.zeros((256, 256, 4), dtype=np.uint8)
    q0[..., 0] = np.clip((216 + blush * 22) * temple, 0, 255).astype(np.uint8)
    q0[..., 1] = np.clip((154 - blush * 6) * temple, 0, 255).astype(np.uint8)
    q0[..., 2] = np.clip((114 - blush * 4) * temple, 0, 255).astype(np.uint8)
    q0[..., 3] = 255

    q2 = np.zeros((256, 256, 4), dtype=np.uint8)
    q2[..., 0] = np.clip(212 * temple, 0, 255).astype(np.uint8)
    q2[..., 1] = np.clip(150 * temple, 0, 255).astype(np.uint8)
    q2[..., 2] = np.clip(110 * temple, 0, 255).astype(np.uint8)
    q2[..., 3] = 255

    img.paste(Image.fromarray(q0, "RGBA"), (0, 0))
    img.paste(Image.fromarray(q2, "RGBA"), (0, 256))

    dr = ImageDraw.Draw(img)
    # Expressive Stylized Brows, Big Crisp Eyes with Catchlights, Nose Shade & Confident Smile!
    dr.polygon([(62, 92), (110, 86), (113, 95), (65, 100)], fill=(34, 24, 18, 255))
    dr.polygon([(194, 92), (146, 86), (143, 95), (191, 100)], fill=(34, 24, 18, 255))
    for ex in (88, 168):
        dr.rounded_rectangle([ex - 19, 104, ex + 19, 128], radius=9, fill=(248, 249, 252, 255))
        dr.ellipse([ex - 11, 106, ex + 11, 128], fill=(56, 32, 18, 255))
        dr.ellipse([ex - 6, 111, ex + 6, 123], fill=(14, 12, 12, 255))
        dr.ellipse([ex + 2, 108, ex + 7, 113], fill=(255, 255, 255, 255))
        dr.line([(ex - 19, 108), (ex + 19, 108)], fill=(24, 16, 14, 255), width=4)
    dr.polygon([(128, 132), (118, 152), (138, 152)], fill=(182, 120, 86, 255))
    dr.arc([104, 160, 152, 182], start=12, end=168, fill=(118, 58, 44, 255), width=4)

    # Q1: Stylized layered espresso hair bands
    dr.rectangle([256, 0, 511, 255], fill=(32, 24, 20, 255))
    for hx in range(264, 508, 18):
        dr.polygon([(hx, 0), (hx + 12, 0), (hx + 8, 240), (hx + 2, 240)], fill=(52, 38, 30, 255))

    # Q3: Stylized Indigo Cargo Jeans with Double Gold Stitching & Knee Patch!
    for py in range(256, 512):
        t = (py - 256) / 255.0
        dr.line([(256, py), (511, py)], fill=(int(48 - 10 * t), int(84 - 16 * t), int(134 - 22 * t), 255))
    dr.line([(272, 256), (272, 512)], fill=(214, 168, 72, 255), width=3)
    dr.rounded_rectangle([296, 352, 474, 434], radius=10, fill=(58, 98, 152, 255), outline=(214, 168, 72, 255), width=3)
    return np.array(img, dtype=np.uint8)


def make_gear_and_fabric_tile():
    img = Image.new("RGBA", (TILE, TILE), (242, 244, 248, 255))
    dr = ImageDraw.Draw(img)

    # Q0 (0..256, 0..256): Quilted Stylized Work Vest / Shirt Front with Zipper Placket & Twin Pockets!
    for py in range(0, 256):
        g = int(248 - 22 * (py / 255.0))
        dr.line([(0, py), (255, py)], fill=(g, g, g, 255))
    for qy in range(44, 244, 48):
        dr.line([(8, qy), (248, qy)], fill=(208, 214, 222, 255), width=3)
    dr.rectangle([118, 0, 138, 255], fill=(96, 78, 62, 255), outline=(228, 192, 96, 255), width=2)
    dr.rounded_rectangle([28, 136, 98, 212], radius=8, fill=(232, 236, 242, 255), outline=(176, 182, 192, 255), width=3)
    dr.rounded_rectangle([158, 136, 228, 212], radius=8, fill=(232, 236, 242, 255), outline=(176, 182, 192, 255), width=3)

    # Q1 (256..512, 0..256): Hand-Painted Golden Woven Caping Bamboo & Rattan Ribs
    dr.rectangle([256, 0, 511, 255], fill=(204, 152, 74, 255))
    for wy in range(0, 256, 22):
        dr.rectangle([256, wy, 511, wy + 12], fill=(228, 178, 96, 255))
        dr.line([(256, wy + 18), (511, wy + 18)], fill=(138, 94, 40, 255), width=3)
    for wx in range(268, 511, 32):
        dr.line([(wx, 0), (wx, 255)], fill=(162, 114, 52, 255), width=3)

    # Q2 (0..256, 256..512): Chunky Stylized Emerald Plantation Work Boot + Tan Top Cuff!
    dr.rectangle([0, 256, 255, 511], fill=(36, 98, 58, 255))
    dr.rectangle([0, 256, 255, 292], fill=(226, 184, 98, 255))
    dr.rectangle([0, 474, 255, 511], fill=(92, 58, 34, 255))

    # Q3 (256..512, 256..512): Hand-Painted Stylized Forged Steel with Bright Bevel Edge!
    for x in range(256, 512):
        t = (x - 256) / 255.0
        v = int(min(255, 146 + 98 * (t ** 1.6)))
        dr.line([(x, 256), (x, 511)], fill=(int(v * 0.96), int(v * 0.99), v, 255))
    dr.line([(500, 256), (500, 511)], fill=(255, 255, 255, 255), width=8)
    return np.array(img, dtype=np.uint8)


def make_corrugated_tile():
    img = Image.new("RGBA", (TILE, TILE), (196, 206, 218, 255))
    dr = ImageDraw.Draw(img)
    for x in range(0, TILE, 32):
        dr.rectangle([x, 0, x + 14, TILE], fill=(226, 234, 244, 255))
        dr.rectangle([x + 15, 0, x + 26, TILE], fill=(164, 176, 190, 255))
        dr.line([(x + 28, 0), (x + 28, TILE)], fill=(122, 134, 148, 255), width=3)
    dr.rectangle([0, 236, TILE, 268], fill=(138, 148, 162, 255))
    return np.array(img, dtype=np.uint8)


def make_concrete_tile():
    n = painterly_fbm((TILE, TILE), 6, 3, 919)
    arr = np.zeros((TILE, TILE, 4), dtype=np.uint8)
    arr[..., 0] = np.clip(168 + n * 28, 0, 255).astype(np.uint8)
    arr[..., 1] = np.clip(174 + n * 28, 0, 255).astype(np.uint8)
    arr[..., 2] = np.clip(182 + n * 28, 0, 255).astype(np.uint8)
    arr[..., 3] = 255
    img = Image.fromarray(arr, "RGBA")
    dr = ImageDraw.Draw(img)
    dr.line([(0, 256), (TILE, 256)], fill=(128, 134, 142, 255), width=4)
    dr.line([(256, 0), (256, TILE)], fill=(128, 134, 142, 255), width=4)
    for hx in range(-TILE, TILE * 2, 48):
        dr.polygon([(hx, 474), (hx + 24, 474), (hx + 8, 511), (hx - 16, 511)], fill=(246, 186, 24, 255))
    return np.array(img, dtype=np.uint8)


def make_rock_tile():
    img = Image.new("RGBA", (TILE, TILE), (118, 126, 136, 255))
    dr = ImageDraw.Draw(img)
    rng = np.random.default_rng(1212)
    for _ in range(42):
        cx, cy = rng.uniform(0, TILE), rng.uniform(0, TILE)
        r = rng.uniform(42, 98)
        pts = [(cx + math.cos(i * math.tau / 6) * r, cy + math.sin(i * math.tau / 6) * r * 0.8) for i in range(6)]
        v = int(rng.uniform(96, 164))
        dr.polygon(pts, fill=(v, int(v * 1.03), int(v * 1.08), 255), outline=(182, 192, 204, 255))
    return np.array(img, dtype=np.uint8)


def make_puff_sprite_tile():
    yy, xx = np.mgrid[0:TILE, 0:TILE].astype(np.float32) / (TILE - 1.0)
    dx, dy = (xx - 0.5) * 2.0, (yy - 0.5) * 2.0
    r = np.sqrt(dx * dx + dy * dy)
    ang = np.arctan2(dy, dx)
    lobes = 0.84 + 0.14 * np.cos(ang * 5.0) + 0.06 * np.sin(ang * 3.0)
    alpha = np.clip((lobes - r) * 2.8, 0.0, 1.0) ** 1.35
    shade = np.clip(0.82 - 0.18 * dy + 0.16 * (1.0 - r), 0.55, 1.0)
    out = np.zeros((TILE, TILE, 4), dtype=np.uint8)
    out[..., 0] = (252 * shade).astype(np.uint8)
    out[..., 1] = (250 * shade).astype(np.uint8)
    out[..., 2] = (246 * shade).astype(np.uint8)
    out[..., 3] = (255 * alpha).astype(np.uint8)
    return out


def main():
    atlas = np.zeros((ATLAS, ATLAS, 4), dtype=np.uint8)
    grid = [
        [make_grass_tile(), make_dirt_road_tile(), make_palm_bark_tile(), make_tbs_fruit_tile()],
        [make_palm_frond_alpha_tile(), make_fern_alpha_tile(), make_wood_planks_tile(), make_tire_and_wheel_tile()],
        [make_canter_front_atlas_tile(), make_canter_paint_tile(), make_character_atlas_tile(), make_gear_and_fabric_tile()],
        [make_corrugated_tile(), make_concrete_tile(), make_rock_tile(), make_puff_sprite_tile()],
    ]
    for ry in range(4):
        for cx in range(4):
            atlas[ry * TILE:(ry + 1) * TILE, cx * TILE:(cx + 1) * TILE] = grid[ry][cx]

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out_path = os.path.join(root, "src", "Nyawit.Android", "Assets", "Textures", "nyawit_pbr_atlas.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    Image.fromarray(atlas, "RGBA").save(out_path, optimize=True)
    print(f"Generated Hand-Painted Stylized v5.0 Atlas -> {out_path} ({os.path.getsize(out_path)/1024:.1f} KB)")


if __name__ == "__main__":
    main()
