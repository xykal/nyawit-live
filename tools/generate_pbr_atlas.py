#!/usr/bin/env python3
"""
Nyawit Live 3D v6.0 — High-Craft Sumatran Estate PBR & Stylized Anime 2048x2048 Texture Atlas
Generates src/Nyawit.Android/Assets/Textures/nyawit_pbr_atlas.png (4x4 grid of 512x512 tiles, 2x supersampled).

Designed for 'Bussid / GTA SA Mod ENB Dingin Sumatera' + Clean Stylized Anime Outline aesthetics:
  - Wet dark reddish-chocolate Sumatran peat/laterite mud road with dual tire lug ruts & crushed gravel
  - Rich natural dark tropical plantation undergrowth (piringan & gawangan moss/fern grass — zero neon lime)
  - Botanical Elaeis guineensis pruned diamond petiole bark & 42-pair slender pinnate oil palm frond alpha
  - Authentic Mitsubishi Fuso Canter FE 74 HD crystal multi-reflector swept headlamps, Fuso 3-diamond grille,
    sleek black rubber windshield gasket (zero cartoon cyan bars) & rich factory canary-gold automotive enamel
  - Sharp modern stylized anime harvester face, rugged field workwear, AP Boots & true FBM volumetric smoke puff
"""
import math
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

TILE = 512
SS = 1024  # 2x supersampling per tile -> Lanczos downsampled to 512x512
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


def fbm(shape, base_freq=4, octaves=4, seed=1):
    val = np.zeros(shape, dtype=np.float32)
    amp = 0.54
    freq = base_freq
    norm = 0.0
    for o in range(octaves):
        val += amp * smooth_noise(shape, freq, seed + o * 43)
        norm += amp
        amp *= 0.5
        freq *= 2
    return val / norm


def downsample(img: Image.Image) -> np.ndarray:
    if img.size != (TILE, TILE):
        img = img.resize((TILE, TILE), Image.Resampling.LANCZOS)
    return np.array(img, dtype=np.uint8)


def make_grass_tile():
    # Deep natural Sumatran oil palm estate groundcover (dark moss-emerald, damp soil patches & fallen frond litter)
    n1 = fbm((TILE, TILE), 5, 4, 10)
    n2 = fbm((TILE, TILE), 16, 3, 22)
    soil = np.clip((0.44 - n1) * 2.2, 0.0, 1.0)
    lush = np.clip((n1 - 0.48) * 2.1, 0.0, 1.0)

    r = 34 + n1 * 24 + lush * 18 + soil * 24 + n2 * 10
    g = 64 + n1 * 36 + lush * 28 - soil * 8 + n2 * 16
    b = 24 + n1 * 14 + lush * 8 + soil * 6 + n2 * 7
    arr = np.stack([r, g, b, np.full((TILE, TILE), 255.0, np.float32)], axis=-1)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    dr = ImageDraw.Draw(img)

    rng = np.random.default_rng(101)
    # Fallen dried palm pinnae litter ('serasah daun sawit kering')
    for _ in range(85):
        lx, ly = rng.uniform(6, TILE - 6), rng.uniform(6, TILE - 6)
        ang = rng.uniform(0, math.tau)
        ln = rng.uniform(14, 28)
        dx, dy = math.cos(ang) * ln, math.sin(ang) * ln
        dr.line([(lx - dx * 0.5, ly - dy * 0.5), (lx + dx * 0.5, ly + dy * 0.5)],
                fill=(int(rng.uniform(72, 98)), int(rng.uniform(56, 74)), int(rng.uniform(32, 44)), 255), width=2)

    # Rich dark-olive & forest-emerald grass/fern tufts
    for _ in range(420):
        bx, by = rng.uniform(6, TILE - 6), rng.uniform(10, TILE - 6)
        ln = rng.uniform(7, 15)
        lean = rng.uniform(-5, 5)
        sh = rng.uniform(0.78, 1.22)
        col = (int(min(255, 48 * sh)), int(min(255, 92 * sh)), int(min(255, 32 * sh)), 255)
        dr.polygon([(bx - 1.8, by), (bx + lean, by - ln), (bx + 1.8, by)], fill=col)
    return np.array(img, dtype=np.uint8)


def make_dirt_road_tile():
    # Authentic Bussid / Sumatran Wet Laterite & Peat Mud Road ('Jalan Kebun Sawit Berlumpur Basah')
    y, x = np.mgrid[0:TILE, 0:TILE].astype(np.float32) / TILE
    n_macro = fbm((TILE, TILE), 4, 4, 41)
    n_micro = fbm((TILE, TILE), 18, 3, 73)

    rut_l = np.exp(-((x - 0.26) ** 2) / 0.0085)
    rut_r = np.exp(-((x - 0.74) ** 2) / 0.0085)
    rut = np.clip(rut_l + rut_r, 0.0, 1.0)
    ridge = np.exp(-((x - 0.50) ** 2) / 0.018) * 0.45 + (
        np.exp(-((x - 0.12) ** 2) / 0.006) + np.exp(-((x - 0.88) ** 2) / 0.006)
    ) * 0.35

    chevron = 0.5 + 0.5 * np.sin((y * 32.0 + np.abs(x - 0.5) * 5.0) * math.tau)
    tread_cut = rut * (0.62 + 0.38 * chevron)
    wet_puddle = np.clip((rut * 0.75 + (0.52 - n_macro) * 0.85) - 0.32, 0.0, 1.0)

    r = 96 + n_macro * 32 + n_micro * 14 + ridge * 18 - tread_cut * 28 - wet_puddle * 24
    g = 63 + n_macro * 22 + n_micro * 10 + ridge * 12 - tread_cut * 20 - wet_puddle * 18
    b = 42 + n_macro * 14 + n_micro * 8 + ridge * 7 - tread_cut * 14 - wet_puddle * 10

    arr = np.stack([r, g, b, np.full((TILE, TILE), 255.0, np.float32)], axis=-1)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    dr = ImageDraw.Draw(img)
    rng = np.random.default_rng(202)
    # Crushed limestone road-hardening stones ('batu pengeras jalan kebun') along road shoulders & center crown
    for _ in range(95):
        px, py = rng.uniform(6, TILE - 6), rng.uniform(6, TILE - 6)
        pr = rng.uniform(2.0, 5.2)
        v = int(rng.uniform(118, 158))
        dr.ellipse([px - pr, py - pr * 0.75, px + pr, py + pr * 0.75],
                   fill=(v, int(v * 0.90), int(v * 0.78), 255),
                   outline=(58, 40, 28, 255))
    return np.array(img, dtype=np.uint8)


def make_palm_bark_tile():
    # Authentic Elaeis guineensis Pruned Diamond Petiole Bark ('Batang Sawit Pelepah Potong Berlian')
    img = Image.new("RGBA", (SS, SS), (34, 24, 17, 255))
    dr = ImageDraw.Draw(img)
    rng = np.random.default_rng(707)

    rows = 10
    cols = 6
    rh = SS / rows
    cw = SS / cols

    for ry in range(-1, rows + 1):
        y_mid = (ry + 0.5) * rh
        x_shift = (ry % 2) * (cw * 0.5)
        for cx_i in range(-1, cols + 2):
            x_mid = cx_i * cw + x_shift + rng.uniform(-6, 6)
            w = cw * 0.54
            h = rh * 0.62
            tone = rng.uniform(0.84, 1.16)

            # Dark outer fibrous shadow socket
            pts_outer = [
                (x_mid, y_mid - h * 1.05),
                (x_mid + w * 1.04, y_mid + h * 0.08),
                (x_mid + w * 0.62, y_mid + h * 0.95),
                (x_mid - w * 0.62, y_mid + h * 0.95),
                (x_mid - w * 1.04, y_mid + h * 0.08),
            ]
            dr.polygon(pts_outer, fill=(26, 18, 13, 255))

            # Layered pruned petiole shield ('bantalan pelepah')
            for k in range(5):
                f = 1.0 - k * 0.15
                sh = tone * (0.68 + k * 0.11)
                pts = [
                    (x_mid, y_mid - h * 0.92 * f - k * 2.5),
                    (x_mid + w * 0.94 * f, y_mid + h * 0.05 * f),
                    (x_mid + w * 0.54 * f, y_mid + h * 0.82 * f),
                    (x_mid - w * 0.54 * f, y_mid + h * 0.82 * f),
                    (x_mid - w * 0.94 * f, y_mid + h * 0.05 * f),
                ]
                col = (int(min(255, 108 * sh)), int(min(255, 78 * sh)), int(min(255, 52 * sh)), 255)
                dr.polygon(pts, fill=col)

            # Cut vascular bundle bevel face at top of petiole stub + subtle green epiphytic moss
            pts_cut = [
                (x_mid, y_mid - h * 0.84),
                (x_mid + w * 0.58, y_mid - h * 0.16),
                (x_mid, y_mid + h * 0.04),
                (x_mid - w * 0.58, y_mid - h * 0.16),
            ]
            dr.polygon(pts_cut, fill=(int(134 * tone), int(98 * tone), int(66 * tone), 255))
            if rng.random() < 0.42:
                mx = x_mid + rng.uniform(-w * 0.35, w * 0.35)
                my = y_mid + h * 0.45
                dr.ellipse([mx - 16, my - 9, mx + 16, my + 9], fill=(48, 74, 34, 175))

    return downsample(img)


def make_tbs_fruit_tile():
    # Authentic Tenera Oil Palm Ripe TBS Fruitlets: deep plum-black crowns blending into glowing crimson-orange bases!
    rng = np.random.default_rng(2026)
    py_grid, px_grid = np.mgrid[0:TILE, 0:TILE].astype(np.float32)
    best_h = np.full((TILE, TILE), -1.0, dtype=np.float32)
    rgb = np.zeros((TILE, TILE, 3), dtype=np.float32)
    rgb[:] = [28.0, 8.0, 6.0]

    rows, cols = 13, 13
    for ry in range(-1, rows + 2):
        for cx in range(-1, cols + 2):
            fx = (cx + (ry % 2) * 0.5 + rng.uniform(-0.14, 0.14)) * (TILE / cols)
            fy = (ry + rng.uniform(-0.14, 0.14)) * (TILE / rows)
            rad = (TILE / cols) * rng.uniform(0.57, 0.69)
            x0, x1 = max(0, int(fx - rad - 1)), min(TILE, int(fx + rad + 2))
            y0, y1 = max(0, int(fy - rad - 1)), min(TILE, int(fy + rad + 2))
            if x0 >= x1 or y0 >= y1:
                continue
            dx = (px_grid[y0:y1, x0:x1] - fx) / rad
            dy = (py_grid[y0:y1, x0:x1] - fy) / rad
            r2 = dx * dx + dy * dy
            h = np.sqrt(np.clip(1.0 - r2, 0.0, 1.0))
            win = (r2 <= 1.0) & (h > best_h[y0:y1, x0:x1])
            best_h[y0:y1, x0:x1] = np.where(win, h, best_h[y0:y1, x0:x1])

            # Tenera ripeness gradient: deep maroon-violet apex + fiery orange-red lower drupe + glossy catchlight
            apex = np.clip(h ** 1.8, 0.0, 1.0)
            lit = np.clip(0.35 + (-dx * 0.38 - dy * 0.46 + h * 0.72), 0.12, 1.25)
            spec = np.clip((-dx * 0.35 - dy * 0.45 + h * 0.82), 0.0, 1.0) ** 14.0
            warm = rng.uniform(0.88, 1.12)

            cr = (218 * (1.0 - apex * 0.52) * warm) * lit + spec * 145
            cg = (68 * (1.0 - apex * 0.72) + 26 * (1.0 - h)) * lit + spec * 110
            cb = (18 + 24 * apex) * lit + spec * 85

            sub = rgb[y0:y1, x0:x1]
            sub[win, 0] = cr[win]
            sub[win, 1] = cg[win]
            sub[win, 2] = cb[win]

    return np.clip(np.concatenate([rgb, np.full((TILE, TILE, 1), 255.0, np.float32)], axis=-1), 0, 255).astype(np.uint8)


def make_palm_frond_alpha_tile():
    # Botanical 36-Pair Pinnate Oil Palm Frond with RGB color-bleed padding for lush zero-fringe mipmaps!
    img = Image.new("RGBA", (SS, SS), (38, 82, 24, 0))
    dr = ImageDraw.Draw(img)
    rng = np.random.default_rng(515)

    cx = SS * 0.5
    n_pairs = 34
    for i in range(n_pairs):
        t = (i + 0.35) / n_pairs  # 0 = petiole base (bottom y=SS), 1 = frond apex (top y=0)
        y0 = SS * (0.985 - t * 0.955)
        env = math.sin(math.pow(t, 0.60) * math.pi * 0.96)
        half_w = SS * (0.08 + 0.415 * env)
        droop = SS * (0.018 + 0.062 * (t ** 1.15))
        blade_w = (SS / n_pairs) * (0.96 - 0.16 * t)

        # Deep tropical forest emerald with natural sun-warmth toward rachis & upper crown
        sh = rng.uniform(0.91, 1.09)
        r_c = int(min(255, (42 + 34 * (t ** 1.3)) * sh))
        g_c = int(min(255, (96 + 46 * t) * sh))
        b_c = int(min(255, (26 + 12 * t) * sh))
        midrib_c = (int(min(255, r_c * 1.32 + 20)), int(min(255, g_c * 1.22 + 16)), int(min(255, b_c * 1.10 + 8)), 255)

        for side in (-1.0, 1.0):
            jitter = rng.uniform(-0.009, 0.009) * SS
            mx = cx + side * half_w * 0.56
            my = y0 - droop * 0.25 + jitter * 0.4
            tx = cx + side * half_w
            ty = y0 + droop + jitter
            pts = [
                (cx - side * 4.0, y0 - blade_w * 0.56),
                (mx, my - blade_w * 0.44),
                (tx, ty),
                (mx, my + blade_w * 0.38),
                (cx - side * 4.0, y0 + blade_w * 0.54),
            ]
            dr.polygon(pts, fill=(r_c, g_c, b_c, 255))
            dr.line([(cx + side * 4.0, y0), (mx, my - blade_w * 0.06), (tx, ty)], fill=midrib_c, width=3)

    # Woody olive-ochre central rachis spine ('tulang pelepah sawit')
    dr.polygon([(cx - 16, SS), (cx + 16, SS), (cx + 4, 16), (cx - 4, 16)], fill=(108, 126, 46, 255))
    dr.polygon([(cx - 7, SS), (cx + 7, SS), (cx + 2, 16), (cx - 2, 16)], fill=(146, 162, 66, 255))
    return downsample(img)


def make_fern_alpha_tile():
    # Multi-frond Nephrolepis Sword Fern ('Pakis Batang & Gawangan Sawit') with green color-bleed padding
    img = Image.new("RGBA", (SS, SS), (44, 96, 28, 0))
    dr = ImageDraw.Draw(img)
    for f in range(5):
        ang = -0.62 + f * 0.31
        length = SS * (0.84 if f % 2 == 0 else 0.93)
        bx, by = SS * 0.5, SS * 0.98
        ca, sa = math.cos(ang), math.sin(ang)
        ex, ey = bx + sa * length, by - ca * length
        # Draw 18 serrated pinnae along each sword-fern stem
        for p in range(18):
            pt = (p + 0.5) / 18.0
            sx = bx + sa * length * pt
            sy = by - ca * length * pt
            pw = SS * 0.095 * math.sin(pt * math.pi * 0.94)
            nx, ny = ca, sa
            col = (int(44 + f * 6 + pt * 22), int(102 + f * 8 + pt * 36), 30, 255)
            dr.polygon([
                (sx, sy - 8),
                (sx - nx * pw, sy - ny * pw + 6),
                (sx, sy + 9),
                (sx + nx * pw, sy + ny * pw + 6),
            ], fill=col)
        dr.line([(bx, by), (ex, ey)], fill=(96, 138, 48, 255), width=5)
    return downsample(img)


def make_wood_planks_tile():
    # Heavy Oiled Sumatran Meranti / Kulim Hardwood "Bak Kayu" Planks + Recessed Bolts & DOT Reflector
    img = Image.new("RGBA", (SS, SS), (112, 58, 24, 255))
    dr = ImageDraw.Draw(img)
    n_planks = 6
    ph = SS / n_planks
    rng = np.random.default_rng(313)

    for p in range(n_planks):
        y0 = int(p * ph)
        y1 = int((p + 1) * ph)
        tone = rng.uniform(0.88, 1.10)
        for py in range(y0, y1):
            t = (py - y0) / max(1, y1 - y0 - 1)
            mul = (1.10 - 0.22 * t) * tone
            if t < 0.05 or t > 0.94:
                mul = 0.28  # Deep shadow gap between Meranti planks
            elif t < 0.12:
                mul = 1.26 * tone  # Clean top chamfer highlight
            col = (int(min(255, 138 * mul)), int(min(255, 74 * mul)), int(min(255, 32 * mul)), 255)
            dr.line([(0, py), (SS, py)], fill=col)

        for _ in range(14):
            gy = rng.uniform(y0 + 18, y1 - 16)
            gx0 = rng.uniform(0, SS * 0.65)
            gx1 = gx0 + rng.uniform(140, 420)
            dr.line([(gx0, gy), (min(SS, gx1), gy + rng.uniform(-5, 5))],
                    fill=(int(92 * tone), int(46 * tone), int(18 * tone), 190), width=3)

    tape_y = int(SS * 0.50)
    for dash in range(8):
        x0 = dash * (SS // 8) + 8
        c = (236, 240, 246, 255) if dash % 2 == 0 else (206, 38, 28, 255)
        dr.rounded_rectangle([x0, tape_y - 12, x0 + (SS // 8) - 16, tape_y + 12], radius=5, fill=c,
                             outline=(36, 24, 18, 255), width=2)
    for bx in range(72, SS, 256):
        for by_i in range(n_planks):
            by = int((by_i + 0.5) * ph)
            dr.ellipse([bx - 12, by - 12, bx + 12, by + 12], fill=(38, 42, 48, 255), outline=(146, 154, 166, 255), width=3)
    return downsample(img)


def make_tire_and_wheel_tile():
    # Heavy-Duty Off-Road Mud-Lug Radial Tire + Authentic 6-Hole Sumatran Crimson/Steel Canter Rim
    img = Image.new("RGBA", (SS, SS), (22, 25, 30, 255))
    dr = ImageDraw.Draw(img)

    # Left half (0..512): Deep chevron/shoulder off-road mud-terrain tread blocks
    dr.rectangle([0, 0, 511, SS], fill=(16, 18, 22, 255))
    for row in range(0, SS, 56):
        dr.polygon([(18, row + 8), (226, row + 18), (226, row + 46), (18, row + 38)],
                   fill=(42, 46, 53, 255), outline=(64, 70, 80, 255))
        dr.polygon([(286, row + 18), (494, row + 8), (494, row + 38), (286, row + 46)],
                   fill=(42, 46, 53, 255), outline=(64, 70, 80, 255))
        dr.rectangle([238, row + 6, 274, row + 48], fill=(36, 40, 46, 255))

    # Right half: Circular Canter Wheel centered at (768, 512), radius 252
    cx, cy = 768, 512
    dr.ellipse([cx - 252, cy - 252, cx + 252, cy + 252], fill=(22, 25, 30, 255))
    dr.ellipse([cx - 220, cy - 220, cx + 220, cy + 220], outline=(48, 54, 62, 255), width=8)
    # Brushed steel outer rim flange + deep crimson-red Sumatran heavy steel wheel disc
    dr.ellipse([cx - 166, cy - 166, cx + 166, cy + 166], fill=(154, 38, 28, 255), outline=(186, 196, 208, 255), width=12)
    dr.ellipse([cx - 142, cy - 142, cx + 142, cy + 142], outline=(112, 24, 18, 255), width=6)

    # 6 Authentic Canter Oval Hand/Ventilation Holes ('lubang velg truk 6 baut')
    for i in range(6):
        a = i * math.tau / 6.0
        hx = cx + math.cos(a) * 106
        hy = cy + math.sin(a) * 106
        dr.ellipse([hx - 24, hy - 24, hx + 24, hy + 24], fill=(18, 20, 24, 255), outline=(196, 74, 58, 255), width=4)

    # Heavy planetary axle hub + 6 chrome lug nuts
    dr.ellipse([cx - 62, cy - 62, cx + 62, cy + 62], fill=(38, 43, 50, 255), outline=(168, 178, 190, 255), width=6)
    dr.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], fill=(24, 28, 34, 255), outline=(96, 106, 118, 255), width=4)
    for i in range(6):
        a = i * math.tau / 6.0 + 0.52
        lx = cx + math.cos(a) * 46
        ly = cy + math.sin(a) * 46
        dr.ellipse([lx - 8, ly - 8, lx + 8, ly + 8], fill=(224, 230, 238, 255))
    return downsample(img)


def make_canter_front_atlas_tile():
    # Authentic Mitsubishi Fuso Canter FE 74 HD Front Fascia, Crystal Multi-Reflector Headlamp & Smoked Rubber Glass!
    img = Image.new("RGBA", (SS, SS), (20, 24, 30, 255))
    dr = ImageDraw.Draw(img)

    # 1. Top half (y = 0..511): Sleek Automotive Black Rubber Gasket + Smoked Sun-Strip + Subtle Sky Reflection (alpha=0 center!)
    dr.rectangle([0, 0, SS - 1, 511], fill=(0, 0, 0, 0))
    # Matte black automotive rubber weatherstrip bezel (ZERO neon cyan!)
    dr.rectangle([0, 0, SS - 1, 511], outline=(18, 21, 26, 255), width=26)
    dr.rectangle([26, 26, SS - 27, 485], outline=(38, 46, 56, 255), width=8)
    # Dark smoked upper windshield sun-visor band + crisp subtle cool-silver ENB sky reflection slash
    dr.rectangle([26, 26, SS - 27, 96], fill=(22, 30, 40, 255))
    dr.line([(26, 96), (SS - 27, 96)], fill=(64, 82, 102, 255), width=4)
    dr.polygon([(92, 485), (236, 26), (294, 26), (150, 485)], fill=(156, 184, 208, 255))
    dr.polygon([(334, 485), (478, 26), (504, 26), (360, 485)], fill=(112, 138, 162, 255))

    # 2. Mid-Left (0..511, 512..799): Authentic Fuso Canter FE 74 HD Matte-Black Slotted Grille + Chrome 3-Diamond Badge!
    dr.rectangle([0, 512, 511, 799], fill=(22, 25, 30, 255))
    dr.rounded_rectangle([14, 524, 497, 787], radius=20, fill=(30, 34, 41, 255), outline=(74, 82, 94, 255), width=8)
    # Top chrome garnish bar ("FUSO" trim strip)
    dr.rounded_rectangle([34, 538, 477, 564], radius=6, fill=(196, 204, 216, 255))
    # 3 Horizontal aerodynamic intake slots with dark honeycomb mesh
    for sy in (582, 646, 710):
        dr.rounded_rectangle([38, sy, 473, sy + 44], radius=8, fill=(14, 16, 20, 255), outline=(56, 62, 72, 255), width=3)
        for hx in range(56, 462, 26):
            dr.line([(hx, sy + 6), (hx, sy + 38)], fill=(32, 36, 44, 255), width=3)
    # Central Chrome Shield & Crisp 3-Diamond Mitsubishi Emblem
    cx_g, cy_g = 256, 662
    dr.polygon([(cx_g - 58, cy_g - 56), (cx_g + 58, cy_g - 56), (cx_g + 46, cy_g + 54), (cx_g - 46, cy_g + 54)],
               fill=(26, 30, 36, 255), outline=(148, 156, 168, 255), width=4)
    for pts in [
        [(cx_g, cy_g - 44), (cx_g + 22, cy_g - 8), (cx_g, cy_g + 8), (cx_g - 22, cy_g - 8)],
        [(cx_g - 6, cy_g + 10), (cx_g - 42, cy_g + 38), (cx_g - 28, cy_g + 8)],
        [(cx_g + 6, cy_g + 10), (cx_g + 42, cy_g + 38), (cx_g + 28, cy_g + 8)],
    ]:
        dr.polygon(pts, fill=(242, 246, 252, 255))

    # 3. Mid-Right (512..1023, 512..799): Angular Swept Crystal Multi-Reflector Canter Headlamp + Corner Turn Signal!
    dr.rounded_rectangle([512, 512, 1023, 799], radius=22, fill=(24, 28, 34, 255), outline=(68, 76, 88, 255), width=8)
    # Dual-chamber faceted chrome halogen reflector housing (fills trapezoid cleanly — ZERO round circle!)
    dr.polygon([(534, 534), (856, 530), (842, 778), (534, 774)],
               fill=(192, 202, 214, 255), outline=(112, 122, 136, 255), width=6)
    # Inner dual parabolic reflector bowls + halogen bulb shields + fluted crystal lens ribs
    dr.polygon([(550, 548), (692, 546), (684, 760), (550, 758)], fill=(238, 244, 252, 255), outline=(148, 158, 172, 255), width=4)
    dr.polygon([(702, 546), (840, 544), (828, 762), (694, 760)], fill=(232, 240, 250, 255), outline=(148, 158, 172, 255), width=4)
    for bx_b in (618, 766):
        dr.ellipse([bx_b - 38, 616, bx_b + 38, 692], fill=(255, 252, 232, 255), outline=(176, 186, 198, 255), width=4)
        dr.ellipse([bx_b - 14, 640, bx_b + 14, 668], fill=(138, 148, 162, 255))
    for ly in range(556, 760, 24):
        dr.line([(542, ly), (838, ly)], fill=(255, 255, 255, 165), width=2)
    # Integrated outer vertical amber crystal turn signal ('lampu sein sudut Canter')
    dr.polygon([(868, 532), (1002, 542), (1002, 768), (856, 778)],
               fill=(238, 128, 14, 255), outline=(255, 196, 86, 255), width=5)
    for ay in range(554, 762, 22):
        dr.line([(872, ay), (996, ay)], fill=(255, 184, 58, 210), width=3)

    # 4. Bottom (0..1023, 800..1023): Indonesian Riau Plate ("BM 8899 XY") + Ribbed Rectangular Crystal Foglamp
    dr.rounded_rectangle([8, 808, 676, 1014], radius=14, fill=(16, 18, 22, 255), outline=(232, 236, 242, 255), width=8)
    plate_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 74)
    sub_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    dr.text((92, 838), "BM 8899 XY", font=plate_font, fill=(246, 248, 252, 255))
    dr.text((292, 956), "10 . 30", font=sub_font, fill=(216, 222, 230, 255))

    dr.rounded_rectangle([688, 808, 1014, 1014], radius=18, fill=(242, 168, 24, 255), outline=(92, 98, 110, 255), width=8)
    dr.rounded_rectangle([712, 830, 990, 992], radius=10, fill=(255, 214, 92, 255))
    for fy in range(846, 984, 20):
        dr.line([(718, fy), (984, fy)], fill=(232, 152, 18, 255), width=3)
    return downsample(img)


def make_canter_paint_tile():
    # Rich Mitsubishi Canter Factory Canary-Gold Enamel (warm automotive yellow-ochre — ZERO neon lemon!)
    img = Image.new("RGBA", (SS, SS), (222, 160, 18, 255))
    dr = ImageDraw.Draw(img)
    for y in range(SS):
        t = y / (SS - 1.0)
        # Subtle automotive horizon reflection gradient + lower rocker panel warmth
        curve = math.sin(t * math.pi * 0.85)
        r = int(np.clip(226 - 26 * t + 10 * curve, 0, 255))
        g = int(np.clip(164 - 28 * t + 10 * curve, 0, 255))
        b = int(np.clip(20 - 8 * t + 4 * curve, 0, 255))
        dr.line([(0, y), (SS, y)], fill=(r, g, b, 255))

    # Recessed matte-black vertical/flush Canter door handle + key cylinder at UV_CANTER_HANDLE
    dr.rounded_rectangle([696, 676, 920, 784], radius=16, fill=(24, 28, 34, 255), outline=(158, 110, 10, 255), width=6)
    dr.rounded_rectangle([724, 712, 862, 748], radius=8, fill=(58, 64, 74, 255))
    dr.ellipse([876, 718, 902, 744], fill=(176, 184, 196, 255))
    return downsample(img)


def make_character_atlas_tile():
    # Sharp Modern Stylized Anime Harvester Face + Layered Espresso Hair + Rugged Cargo Trousers!
    img = Image.new("RGBA", (SS, SS), (198, 142, 104, 255))
    yy, xx = np.mgrid[0:512, 0:512].astype(np.float32) / 511.0
    temple = 1.0 - 0.14 * (np.abs(xx - 0.5) * 2.0) ** 2.1
    jaw_ao = 1.0 - 0.10 * np.clip((yy - 0.78) * 4.0, 0.0, 1.0)
    shade = temple * jaw_ao

    q0 = np.zeros((512, 512, 4), dtype=np.uint8)
    q0[..., 0] = np.clip(204 * shade, 0, 255).astype(np.uint8)
    q0[..., 1] = np.clip(146 * shade, 0, 255).astype(np.uint8)
    q0[..., 2] = np.clip(108 * shade, 0, 255).astype(np.uint8)
    q0[..., 3] = 255

    q2 = q0.copy()
    img.paste(Image.fromarray(q0, "RGBA"), (0, 0))
    img.paste(Image.fromarray(q2, "RGBA"), (0, 512))

    dr = ImageDraw.Draw(img)
    # Sharp confident anime eyebrows
    dr.polygon([(112, 182), (218, 170), (222, 186), (118, 196)], fill=(28, 20, 16, 255))
    dr.polygon([(400, 182), (294, 170), (290, 186), (394, 196)], fill=(28, 20, 16, 255))

    # Crisp layered anime eyes (bold upper lash wing, warm dark-amber iris gradient, deep pupil & dual catchlights)
    for ex, side in ((172, -1), (340, 1)):
        # Sclera almond shape
        dr.polygon([
            (ex - 42, 224), (ex - 20, 206), (ex + 24, 206),
            (ex + 42, 224), (ex + 26, 248), (ex - 26, 248),
        ], fill=(244, 246, 250, 255))
        # Iris + lower warm amber rim + dark pupil
        dr.ellipse([ex - 22, 208, ex + 22, 248], fill=(46, 28, 18, 255))
        dr.ellipse([ex - 17, 216, ex + 17, 246], fill=(96, 56, 28, 255))
        dr.ellipse([ex - 10, 216, ex + 10, 238], fill=(14, 12, 14, 255))
        # Crisp anime specular catchlights
        dr.ellipse([ex + 5, 212, ex + 15, 222], fill=(255, 255, 255, 255))
        dr.ellipse([ex - 11, 234, ex - 5, 240], fill=(235, 242, 255, 230))
        # Bold anime upper lash arch
        dr.polygon([
            (ex - 46, 226), (ex - 22, 200), (ex + 26, 200),
            (ex + 46, 222), (ex + 38, 228), (ex + 22, 210),
            (ex - 20, 210), (ex - 40, 230),
        ], fill=(18, 14, 14, 255))

    # Clean cel-shaded anime nose wedge shadow + confident determined mouth line
    dr.polygon([(256, 254), (240, 300), (262, 304)], fill=(156, 104, 74, 255))
    dr.line([(218, 344), (254, 350), (296, 338)], fill=(104, 54, 42, 255), width=6)
    dr.line([(240, 366), (272, 366)], fill=(164, 112, 82, 200), width=4)

    # Q1 (512..1023, 0..511): Layered anime dark-espresso hair with cool slate highlight halo!
    dr.rectangle([512, 0, 1023, 511], fill=(22, 18, 18, 255))
    for hx in range(524, 1016, 28):
        dr.polygon([(hx, 0), (hx + 18, 0), (hx + 12, 490), (hx + 3, 490)], fill=(38, 30, 28, 255))
    # Anime hair specular band
    dr.rectangle([512, 150, 1023, 186], fill=(64, 58, 66, 180))

    # Q3 (512..1023, 512..1023): Rugged Dark Slate-Indigo Plantation Cargo Trousers with Mud-Dusted Hem
    for py in range(512, 1024):
        t = (py - 512) / 511.0
        mud = max(0.0, (t - 0.72) / 0.28)
        r_d = int(38 * (1 - mud * 0.3) + 68 * mud * 0.4)
        g_d = int(56 * (1 - mud * 0.4) + 52 * mud * 0.4)
        b_d = int(78 * (1 - mud * 0.5) + 38 * mud * 0.3)
        dr.line([(512, py), (1023, py)], fill=(r_d, g_d, b_d, 255))
    dr.line([(548, 512), (548, 1023)], fill=(142, 118, 68, 255), width=4)
    dr.rounded_rectangle([596, 680, 948, 856], radius=16, fill=(44, 64, 88, 255), outline=(128, 108, 64, 255), width=4)
    dr.line([(596, 732), (948, 732)], fill=(28, 42, 58, 255), width=5)
    return downsample(img)


def make_gear_and_fabric_tile():
    img = Image.new("RGBA", (SS, SS), (232, 236, 240, 255))
    dr = ImageDraw.Draw(img)

    # Q0 (0..511, 0..511): Rugged Dyeable Field Utility Shirt/Vest (neutral light base so vertex/instance dye tints cleanly!)
    for py in range(0, 512):
        t = py / 511.0
        g = int(236 - 34 * t)
        dr.line([(0, py), (511, py)], fill=(g, g, int(min(255, g * 1.02)), 255))
    # Center dark placket + buttons + twin utility chest pockets with flaps
    dr.rectangle([238, 0, 274, 511], fill=(64, 68, 74, 255))
    for by in range(64, 480, 84):
        dr.ellipse([250, by - 6, 262, by + 6], fill=(196, 200, 206, 255))
    for px0 in (48, 316):
        dr.rounded_rectangle([px0, 196, px0 + 148, 356], radius=14, fill=(214, 220, 226, 255), outline=(136, 144, 154, 255), width=5)
        dr.rounded_rectangle([px0 - 4, 192, px0 + 152, 242], radius=10, fill=(198, 204, 212, 255), outline=(124, 132, 142, 255), width=4)

    # Q1 (512..1023, 0..511): Authentic Diagonal Woven Bamboo Caping & Rattan Basket Texture
    dr.rectangle([512, 0, 1023, 511], fill=(168, 122, 62, 255))
    for wy in range(0, 512, 32):
        for wx in range(512, 1024, 48):
            shift = ((wy // 32) % 2) * 24
            x0 = wx + shift
            dr.rectangle([x0, wy + 2, min(1023, x0 + 38), wy + 24], fill=(198, 148, 78, 255), outline=(112, 76, 34, 255), width=3)

    # Q2 (0..511, 512..1023): Authentic Indonesian Dark-Green AP Boots Plantation Rubber Boot + Lugged Mud Sole!
    for py in range(512, 1024):
        t = (py - 512) / 511.0
        dr.line([(0, py), (511, py)], fill=(int(24 + 12 * (1 - t)), int(68 + 20 * (1 - t)), int(42 + 12 * (1 - t)), 255))
    dr.rectangle([0, 512, 511, 560], fill=(32, 36, 38, 255))  # Black top cuff trim
    for ry in range(620, 880, 44):
        dr.line([(36, ry), (475, ry)], fill=(18, 52, 32, 255), width=6)
    dr.rectangle([0, 944, 511, 1023], fill=(42, 30, 22, 255))  # Muddy heavy rubber lug sole

    # Q3 (512..1023, 512..1023): Brushed Forged High-Carbon Steel & Honed Silver Blade Edge
    for x in range(512, 1024):
        t = (x - 512) / 511.0
        v = int(min(255, 118 + 124 * (t ** 1.55)))
        dr.line([(x, 512), (x, 1023)], fill=(int(v * 0.95), int(v * 0.98), v, 255))
    dr.line([(1004, 512), (1004, 1023)], fill=(252, 254, 255, 255), width=14)
    return downsample(img)


def make_corrugated_tile():
    # Weathered Estate Zinc Corrugated Sheet ('Atap Seng Gudang & PKS') with Subtle Tropical Rain/Rust Patina
    img = Image.new("RGBA", (TILE, TILE), (156, 166, 178, 255))
    n = fbm((TILE, TILE), 8, 3, 808)
    arr = np.zeros((TILE, TILE, 4), dtype=np.uint8)
    xs = np.arange(TILE, dtype=np.float32)[None, :]
    rib = np.sin(xs * (math.tau / 28.0))
    rust = np.clip((n - 0.64) * 3.0, 0.0, 1.0)
    base = 152 + rib * 38 + (n - 0.5) * 24
    arr[..., 0] = np.clip(base * (1 - rust * 0.25) + 138 * rust * 0.45, 0, 255).astype(np.uint8)
    arr[..., 1] = np.clip((base + 6) * (1 - rust * 0.42) + 84 * rust * 0.45, 0, 255).astype(np.uint8)
    arr[..., 2] = np.clip((base + 14) * (1 - rust * 0.55) + 52 * rust * 0.45, 0, 255).astype(np.uint8)
    arr[..., 3] = 255
    out = Image.fromarray(arr, "RGBA")
    dr = ImageDraw.Draw(out)
    dr.rectangle([0, 244, TILE, 268], fill=(108, 116, 128, 255))
    return np.array(out, dtype=np.uint8)


def make_concrete_tile():
    # Weathered Industrial Weighbridge / PKS Yard Concrete + Crisp Safety Stripes
    n = fbm((TILE, TILE), 7, 4, 919)
    arr = np.zeros((TILE, TILE, 4), dtype=np.uint8)
    arr[..., 0] = np.clip(132 + n * 34, 0, 255).astype(np.uint8)
    arr[..., 1] = np.clip(138 + n * 34, 0, 255).astype(np.uint8)
    arr[..., 2] = np.clip(144 + n * 34, 0, 255).astype(np.uint8)
    arr[..., 3] = 255
    img = Image.fromarray(arr, "RGBA")
    dr = ImageDraw.Draw(img)
    dr.line([(0, 256), (TILE, 256)], fill=(88, 94, 102, 255), width=4)
    dr.line([(256, 0), (256, TILE)], fill=(88, 94, 102, 255), width=4)
    dr.rectangle([0, 474, TILE, 511], fill=(28, 32, 36, 255))
    for hx in range(-TILE, TILE * 2, 48):
        dr.polygon([(hx, 474), (hx + 24, 474), (hx + 8, 511), (hx - 16, 511)], fill=(224, 166, 22, 255))
    return np.array(img, dtype=np.uint8)


def make_rock_tile():
    n1 = fbm((TILE, TILE), 6, 4, 1212)
    n2 = fbm((TILE, TILE), 20, 3, 1313)
    moss = np.clip((n1 - 0.58) * 2.8, 0.0, 1.0)
    v = 86 + n1 * 56 + n2 * 24
    arr = np.zeros((TILE, TILE, 4), dtype=np.uint8)
    arr[..., 0] = np.clip(v * (1 - moss * 0.35) + 52 * moss * 0.35, 0, 255).astype(np.uint8)
    arr[..., 1] = np.clip((v + 4) * (1 - moss * 0.15) + 82 * moss * 0.35, 0, 255).astype(np.uint8)
    arr[..., 2] = np.clip((v + 8) * (1 - moss * 0.45) + 38 * moss * 0.35, 0, 255).astype(np.uint8)
    arr[..., 3] = 255
    return arr


def make_puff_sprite_tile():
    # True Soft Multi-Octave Volumetric Billowing Smoke / Dust Cloud (NO MORE STARFISH!)
    yy, xx = np.mgrid[0:TILE, 0:TILE].astype(np.float32) / (TILE - 1.0)
    dx, dy = (xx - 0.5) * 2.0, (yy - 0.5) * 2.0
    r = np.sqrt(dx * dx + dy * dy)
    n1 = fbm((TILE, TILE), 4, 4, 404)
    n2 = fbm((TILE, TILE), 9, 3, 505)
    cloud_noise = n1 * 0.68 + n2 * 0.32
    falloff = np.clip(1.0 - (r / 0.94) ** 2.0, 0.0, 1.0)
    alpha = np.clip((falloff * (0.58 + 0.62 * cloud_noise) - 0.12) * 1.45, 0.0, 1.0) ** 1.45
    # Self-shadowed volumetric cloud belly (brighter top-left, softer cooler bottom)
    shade = np.clip(0.84 - 0.14 * dy - 0.06 * dx + 0.14 * cloud_noise, 0.58, 1.0)
    out = np.zeros((TILE, TILE, 4), dtype=np.uint8)
    out[..., 0] = (246 * shade).astype(np.uint8)
    out[..., 1] = (246 * shade).astype(np.uint8)
    out[..., 2] = (248 * shade).astype(np.uint8)
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
    print(f"Generated High-Craft Sumatran ENB + Anime v6 Atlas -> {out_path} ({os.path.getsize(out_path)/1024:.1f} KB)")


if __name__ == "__main__":
    main()
