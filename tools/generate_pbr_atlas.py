#!/usr/bin/env python3
"""
Generates a 2048x2048 RGBA8 high-detail PBR Albedo + Baked Micro-AO + Alpha-Cutout Texture Atlas
for Nyawit Live 3D v4.0 (src/Nyawit.Android/Assets/Textures/nyawit_pbr_atlas.png).

4x4 Grid of 512x512 Tiles (UV origin top-left -> flipped or standard V=0 top in GL):
  Row 0 (y = 0..512):
    [0,0] Lush Plantation Grass & Mossy Ground Cover
    [1,0] Compacted Tropical Laterite Dirt Road with Tire Ruts & Pebbles
    [2,0] Oil Palm Trunk Bark (Overlapping Diamond Pruned Petiole Scales + Moss)
    [3,0] Spiky Ripe TBS Fruit Cluster (Deep Crimson-Black-Orange Fruitlets + Spines)
  Row 1 (y = 512..1024):
    [0,1] Alpha-Cutout Pinnate Oil Palm Frond (88 Realistic Curved Leaflets + Central Rachis!)
    [1,1] Alpha-Cutout Tropical Epiphytic & Ground Fern Fronds
    [2,1] Weathered Teak / Meranti Bak Kayu Planks + Iron Bolts & Grain
    [3,1] Heavy Off-Road Radial Truck Tire Tread & 6-Lug Steel Wheel Rim
  Row 2 (y = 1024..1536):
    [0,2] Mitsubishi Canter Front Grille Mesh + Chrome Bezel + Crystal Headlamp & Signal Atlas
    [1,2] Canter Yellow Enamel Paint + Door Seam + Black Trim + Safety Stripes + Glass Reflection
    [2,2] Character Skin + Expressive Realistic Face (Eyes, Iris, Brows, Nose, Lips, Hair)
    [3,2] Character Clothing & Gear (Work Shirt Weave, Denim Jeans, Woven Caping, Rattan, Brushed Steel)
  Row 3 (y = 1536..2048):
    [0,3] Industrial Corrugated Steel Siding / Garage Roof + Structural Beams
    [1,3] Brushed Concrete Workshop / RAM Weighbridge Pad with Hazard Stripes
    [2,3] Natural River Boulder Granite & Mossy Rock
    [3,3] Soft Radial Volumetric Smoke / Dust / Sunlight Flare Sprite (Alpha)
"""
import math
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

TILE = 512
ATLAS = TILE * 4  # 2048 x 2048


def hash_noise(shape, freq, seed=0):
    rng = np.random.default_rng(seed)
    g = rng.random((freq, freq), dtype=np.float32)
    # Seamless tile wrap
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


def fbm(shape, base_freq=8, octaves=5, seed=1):
    val = np.zeros(shape, dtype=np.float32)
    amp = 0.5
    freq = base_freq
    norm = 0.0
    for o in range(octaves):
        val += amp * hash_noise(shape, freq, seed + o * 37)
        norm += amp
        amp *= 0.5
        freq *= 2
    return val / norm


def make_grass_tile():
    n1 = fbm((TILE, TILE), 8, 5, 10)
    n2 = fbm((TILE, TILE), 32, 4, 22)
    blades = hash_noise((TILE, TILE), 128, 33)
    dry_patch = np.clip((n1 - 0.54) * 3.0, 0.0, 1.0)

    # Natural Indonesian plantation grass (olive-forest green + warm dry thatch, ZERO neon green!)
    r = 44 + n1 * 38 + dry_patch * 48 + blades * 18
    g = 76 + n1 * 48 + dry_patch * 24 + n2 * 22 + blades * 24
    b = 30 + n1 * 20 + dry_patch * 14 + blades * 10
    ao = 0.78 + 0.30 * blades
    rgb = np.stack([r * ao, g * ao, b * ao], axis=-1)
    a = np.full((TILE, TILE, 1), 255.0, dtype=np.float32)
    return np.clip(np.concatenate([rgb, a], axis=-1), 0, 255).astype(np.uint8)


def make_dirt_road_tile():
    y, x = np.mgrid[0:TILE, 0:TILE].astype(np.float32) / TILE
    n1 = fbm((TILE, TILE), 8, 5, 41)
    gravel = hash_noise((TILE, TILE), 96, 55)
    fine = hash_noise((TILE, TILE), 192, 66)

    # Dual tire tracks along V axis with subtle diagonal tread marks
    rut = np.exp(-((x - 0.27) ** 2) / 0.008) + np.exp(-((x - 0.73) ** 2) / 0.008)
    tread = 0.5 + 0.5 * np.sin((y * 46.0 + np.abs(x - 0.5) * 8.0) * math.pi * 2.0)
    rut_tex = rut * (0.68 + 0.32 * tread)

    # Warm Indonesian Sumatran red-brown sandy laterite soil
    r = 126 + n1 * 42 + gravel * 22 - rut_tex * 26 + fine * 12
    g = 94 + n1 * 32 + gravel * 18 - rut_tex * 22 + fine * 10
    b = 66 + n1 * 22 + gravel * 15 - rut_tex * 16 + fine * 8
    rgb = np.stack([r, g, b], axis=-1)
    a = np.full((TILE, TILE, 1), 255.0, dtype=np.float32)
    return np.clip(np.concatenate([rgb, a], axis=-1), 0, 255).astype(np.uint8)


def make_palm_bark_tile():
    # Authentic diamond-spiral pruned petiole bases + fibrous bark + green moss patches!
    y, x = np.mgrid[0:TILE, 0:TILE].astype(np.float32) / TILE
    fib = fbm((TILE, TILE), 24, 4, 77)
    moss_n = fbm((TILE, TILE), 6, 4, 88)

    # Staggered diamond leaf-base lattice
    u = x * 7.0
    v = y * 11.0
    row = np.floor(v)
    u_shift = (u + (row % 2) * 0.5) % 1.0 - 0.5
    v_local = (v % 1.0) - 0.5
    diamond = 1.0 - np.clip((np.abs(u_shift) * 1.45 + np.abs(v_local) * 1.55), 0.0, 1.0)
    cut_face = np.clip((v_local + 0.25) * 2.2, 0.0, 1.0) * (diamond > 0.28)
    crevice = np.clip(diamond * 1.6, 0.22, 1.0)

    r = (58 + fib * 34 + cut_face * 36) * crevice
    g = (45 + fib * 27 + cut_face * 27) * crevice
    b = (33 + fib * 19 + cut_face * 18) * crevice

    # Epiphytic moss / lichen tint in humid bark crevices
    moss = np.clip((moss_n - 0.56) * 3.4, 0.0, 0.85) * (1.0 - cut_face * 0.5)
    r = r * (1.0 - moss) + (48 + fib * 28) * moss
    g = g * (1.0 - moss) + (84 + fib * 42) * moss
    b = b * (1.0 - moss) + (34 + fib * 18) * moss

    rgb = np.stack([r, g, b], axis=-1)
    a = np.full((TILE, TILE, 1), 255.0, dtype=np.float32)
    return np.clip(np.concatenate([rgb, a], axis=-1), 0, 255).astype(np.uint8)


def make_tbs_fruit_tile():
    # Per-pixel 3D shaded glossy teardrop oil-palm fruitlets + bristling fibrous spines!
    rng = np.random.default_rng(2026)
    py_grid, px_grid = np.mgrid[0:TILE, 0:TILE].astype(np.float32)
    best_h = np.full((TILE, TILE), -1.0, dtype=np.float32)
    rgb = np.zeros((TILE, TILE, 3), dtype=np.float32)
    rgb[:] = [20.0, 9.0, 7.0]

    rows, cols = 16, 16
    for ry in range(-1, rows + 2):
        for cx in range(-1, cols + 2):
            fx = (cx + (ry % 2) * 0.5 + rng.uniform(-0.18, 0.18)) * (TILE / cols)
            fy = (ry + rng.uniform(-0.18, 0.18)) * (TILE / rows)
            rad = (TILE / cols) * rng.uniform(0.50, 0.66)
            x0, x1 = max(0, int(fx - rad - 1)), min(TILE, int(fx + rad + 2))
            y0, y1 = max(0, int(fy - rad - 1)), min(TILE, int(fy + rad + 2))
            if x0 >= x1 or y0 >= y1:
                continue
            dx = (px_grid[y0:y1, x0:x1] - fx) / rad
            dy = (py_grid[y0:y1, x0:x1] - fy) / (rad * 0.92)
            r2 = dx * dx + dy * dy
            mask = r2 < 1.0
            if not np.any(mask):
                continue
            nz = np.sqrt(np.maximum(0.0, 1.0 - r2))
            win = mask & (nz > best_h[y0:y1, x0:x1])
            best_h[y0:y1, x0:x1][win] = nz[win]

            # Real Tenera TBS color gradient: fiery vermilion-orange base -> deep glossy plum-maroon-black apex!
            ripeness = rng.uniform(0.15, 1.0)
            apex = np.clip((nz - 0.32) * 1.45, 0.0, 1.0)
            ndl = np.clip(-0.35 * dx - 0.45 * dy + 0.82 * nz, 0.08, 1.0)
            spec = np.power(np.clip(-0.28 * dx - 0.38 * dy + 0.88 * nz, 0.0, 1.0), 22.0)

            cr = (228 * (1.0 - apex * 0.72) + 34 * apex) * (0.42 + 0.72 * ndl) * (0.85 + 0.25 * ripeness) + spec * 185.0
            cg = (68 * (1.0 - apex * 0.84) + 8 * apex) * (0.42 + 0.72 * ndl) + spec * 145.0
            cb = (14 * (1.0 - apex * 0.55) + 12 * apex) * (0.42 + 0.72 * ndl) + spec * 120.0

            sub = rgb[y0:y1, x0:x1]
            sub[win, 0] = cr[win]
            sub[win, 1] = cg[win]
            sub[win, 2] = cb[win]

    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    dr = ImageDraw.Draw(img)
    for _ in range(420):
        sx = rng.uniform(0, TILE)
        sy = rng.uniform(0, TILE)
        ang = rng.uniform(0, math.pi * 2)
        ln = rng.uniform(7.0, 15.0)
        dr.line([(sx, sy), (sx + math.cos(ang) * ln, sy + math.sin(ang) * ln)],
                fill=(152, 114, 66, 205), width=1)
    return np.array(img, dtype=np.uint8)


def make_palm_frond_alpha_tile():
    # ALPHA-CUTOUT PINNATE OIL PALM FROND:
    # Central woody-green rachis running vertically (y = 0 -> base, y = TILE -> tip)
    # with 44 pairs (88 total!) crisp arching V-ranked leaflets + subtle sun variation!
    img = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    rng = np.random.default_rng(707)

    cx = TILE * 0.5
    # Draw leaflets first from base to tip
    n_pairs = 46
    for i in range(n_pairs):
        t = (i + 0.5) / n_pairs  # 0 = petiole base, 1 = frond tip
        y0 = TILE * (0.98 - t * 0.95)
        span_profile = math.sin(math.pow(t, 0.62) * math.pi * 0.94)
        half_w = TILE * (0.08 + 0.40 * span_profile) * rng.uniform(0.92, 1.05)
        droop = TILE * (0.03 + 0.085 * t)
        leaf_w = max(3.2, (TILE / n_pairs) * 0.72)

        for side in (-1.0, 1.0):
            # Alternate slight rank jitter just like real Elaeis guineensis!
            jy = y0 + rng.uniform(-2.5, 2.5)
            mx = cx + side * half_w * 0.56
            my = jy - droop * 0.34
            tx = cx + side * half_w
            ty = jy + droop * rng.uniform(0.75, 1.25)

            shade = rng.uniform(0.82, 1.16)
            sun_tip = 1.0 + 0.14 * t
            col = (
                int(min(255, 52 * shade * sun_tip)),
                int(min(255, 98 * shade * sun_tip)),
                int(min(255, 34 * shade)),
                255,
            )
            pts = [
                (cx + side * 2.0, jy - leaf_w * 0.52),
                (mx, my - leaf_w * 0.42),
                (tx, ty),
                (mx, my + leaf_w * 0.36),
                (cx + side * 2.0, jy + leaf_w * 0.48),
            ]
            dr.polygon(pts, fill=col)
            # Central midrib vein on leaflet
            dr.line([(cx + side * 2.0, jy), (mx, my), (tx, ty)], fill=(78, 124, 46, 255), width=1)

    # Central rachis spine
    for y in range(12, TILE):
        t = 1.0 - y / TILE
        rw = max(1.5, 6.5 * (1.0 - t * 0.82))
        rc = (int(96 - 24 * t), int(112 + 12 * t), int(50 - 8 * t), 255)
        dr.line([(cx - rw, y), (cx + rw, y)], fill=rc, width=1)

    return np.array(img, dtype=np.uint8)


def make_fern_alpha_tile():
    img = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    rng = np.random.default_rng(909)
    # 5 lush overlapping fern fronds radiating from bottom center
    for f in range(5):
        ang = -0.68 + f * 0.34
        length = TILE * rng.uniform(0.78, 0.94)
        bx, by = TILE * 0.5, TILE * 0.98
        for s in range(28):
            t = s / 28.0
            sx = bx + math.sin(ang) * length * t + math.sin(t * 3.0) * 8.0 * ang
            sy = by - math.cos(ang * 0.65) * length * t
            lw = (1.0 - t) * math.sin(min(1.0, t * 2.4) * math.pi * 0.5) * 52.0
            nx, ny = math.cos(ang), math.sin(ang * 0.65)
            col = (int(56 + 34 * t), int(112 + 44 * t), int(42 + 16 * t), 255)
            for side in (-1.0, 1.0):
                dr.polygon([
                    (sx, sy - 4),
                    (sx + side * nx * lw, sy + side * ny * lw + 5),
                    (sx, sy + 4),
                ], fill=col)
        dr.line([(bx, by), (bx + math.sin(ang) * length, by - math.cos(ang * 0.65) * length)],
                fill=(74, 128, 48, 255), width=3)
    return np.array(img, dtype=np.uint8)


def make_wood_planks_tile():
    # Rich Indonesian Meranti/Teak Bak Kayu planks with wood grain, plank seams & steel bolts!
    grain = fbm((TILE, TILE), 16, 5, 313)
    streak = hash_noise((TILE, TILE), 64, 414)
    img = Image.new("RGBA", (TILE, TILE), (150, 74, 24, 255))
    arr = np.array(img, dtype=np.float32)

    y, x = np.mgrid[0:TILE, 0:TILE].astype(np.float32)
    plank_idx = np.floor(y / (TILE / 6.0))
    plank_var = ((plank_idx * 37) % 7) / 7.0 - 0.5
    seam = (np.mod(y, TILE / 6.0) < 3.0) | (np.mod(y, TILE / 6.0) > (TILE / 6.0 - 2.0))

    arr[..., 0] = 158 + grain * 42 + streak * 16 + plank_var * 26
    arr[..., 1] = 78 + grain * 26 + streak * 10 + plank_var * 16
    arr[..., 2] = 26 + grain * 14 + streak * 6 + plank_var * 8
    arr[seam, :3] *= 0.42
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    dr = ImageDraw.Draw(out)
    # Reflective white/red Indonesian truck side tape along plank 3 + steel bolts!
    tape_y = int(TILE * 0.50)
    for dash in range(8):
        x0 = dash * (TILE // 8) + 4
        c = (238, 242, 246, 255) if dash % 2 == 0 else (212, 42, 34, 255)
        dr.rectangle([x0, tape_y - 6, x0 + (TILE // 8) - 8, tape_y + 6], fill=c)
    for bx in range(32, TILE, 128):
        for by_i in range(6):
            by = int((by_i + 0.5) * (TILE / 6.0))
            dr.ellipse([bx - 5, by - 5, bx + 5, by + 5], fill=(48, 52, 58, 255), outline=(145, 152, 160, 255))
    return np.array(out, dtype=np.uint8)


def make_tire_and_wheel_tile():
    # Left half (x = 0..256): Deep heavy-duty off-road radial lug tread
    # Right half (x = 256..512): Radial sidewall + 6-lug heavy black/gunmetal steel truck rim!
    img = Image.new("RGBA", (TILE, TILE), (28, 30, 33, 255))
    dr = ImageDraw.Draw(img)

    # Left half: Tire tread lugs
    dr.rectangle([0, 0, 255, TILE], fill=(24, 26, 29, 255))
    for row in range(0, TILE, 28):
        # Center circumferential ribs + shoulder lugs
        dr.rectangle([12, row + 4, 84, row + 21], fill=(44, 47, 52, 255))
        dr.rectangle([94, row + 2, 124, row + 24], fill=(40, 43, 48, 255))
        dr.rectangle([132, row + 4, 162, row + 25], fill=(40, 43, 48, 255))
        dr.rectangle([172, row + 8, 244, row + 25], fill=(44, 47, 52, 255))

    # Right half: Circular wheel face centered at (384, 256), radius 124
    cx, cy = 384, 256
    # Outer rubber tire sidewall
    dr.ellipse([cx - 126, cy - 126, cx + 126, cy + 126], fill=(26, 28, 32, 255))
    dr.ellipse([cx - 110, cy - 110, cx + 110, cy + 110], outline=(48, 52, 58, 255), width=4)
    dr.ellipse([cx - 94, cy - 94, cx + 94, cy + 94], outline=(38, 41, 46, 255), width=3)
    # Recessed black-gunmetal steel rim dish (authentic Indonesian Fuso Canter look!)
    dr.ellipse([cx - 76, cy - 76, cx + 76, cy + 76], fill=(38, 42, 48, 255), outline=(92, 98, 108, 255), width=4)
    dr.ellipse([cx - 56, cy - 56, cx + 56, cy + 56], fill=(24, 27, 32, 255))
    # Ventilation holes + 6 silver chrome lug nuts + heavy axle hub!
    for i in range(6):
        a = i * math.pi / 3.0
        vx, vy = cx + math.cos(a + 0.26) * 58, cy + math.sin(a + 0.26) * 58
        dr.ellipse([vx - 8, vy - 8, vx + 8, vy + 8], fill=(12, 13, 16, 255))
        lx, ly = cx + math.cos(a) * 38, cy + math.sin(a) * 38
        dr.ellipse([lx - 6, ly - 6, lx + 6, ly + 6], fill=(205, 212, 222, 255), outline=(60, 65, 72, 255))
    dr.ellipse([cx - 22, cy - 22, cx + 22, cy + 22], fill=(42, 46, 52, 255), outline=(120, 128, 138, 255), width=2)
    return np.array(img, dtype=np.uint8)


def make_canter_front_atlas_tile():
    # Dedicated PBR detail tile for Mitsubishi Canter Front Face:
    # Top half (y = 0..256): Dark reflective laminated windshield & side window with subtle sky horizon reflection + wipers!
    # Bottom-left (0..256, 256..400): Black honeycomb grille + chrome U-bar + silver three-diamond style emblem!
    # Bottom-right (256..512, 256..400): Swept-back crystal multi-reflector headlamp + amber corner signal!
    # Bottom strip (0..512, 400..512): Front black license plate ("BM 8899 XY") + amber fog lamp lens!
    img = Image.new("RGBA", (TILE, TILE), (24, 30, 38, 255))
    dr = ImageDraw.Draw(img)

    # 1. Realistic tinted glass with subtle sky-blue reflection band
    for y in range(256):
        t = y / 255.0
        sky = math.exp(-((t - 0.34) ** 2) / 0.035)
        c = (int(20 + 68 * sky), int(28 + 94 * sky), int(38 + 118 * sky), 255)
        dr.line([(0, y), (TILE, y)], fill=c)
    # Rubber window bezel + dual black wipers at bottom of windshield
    dr.rectangle([0, 0, TILE - 1, 255], outline=(14, 16, 20, 255), width=10)
    dr.line([(56, 244), (215, 198)], fill=(15, 17, 20, 255), width=7)
    dr.line([(265, 244), (435, 198)], fill=(15, 17, 20, 255), width=7)

    # 2. Chrome & Black Mesh Grille (0..256, 256..400)
    dr.rectangle([0, 256, 255, 399], fill=(22, 24, 28, 255))
    dr.rectangle([10, 266, 245, 390], outline=(214, 222, 232, 255), width=9)
    dr.rectangle([18, 276, 237, 294], fill=(208, 216, 226, 255))
    for gy in range(304, 382, 14):
        dr.line([(22, gy), (233, gy)], fill=(62, 68, 76, 255), width=3)
    for gx in range(28, 232, 18):
        dr.line([(gx, 298), (gx, 382)], fill=(48, 52, 58, 255), width=2)
    # Center silver diamond crest
    cx_g, cy_g = 128, 336
    dr.polygon([(cx_g, cy_g - 22), (cx_g + 12, cy_g - 4), (cx_g, cy_g + 4), (cx_g - 12, cy_g - 4)], fill=(235, 240, 246, 255))
    dr.polygon([(cx_g - 4, cy_g + 4), (cx_g - 22, cy_g + 18), (cx_g - 16, cy_g + 4)], fill=(235, 240, 246, 255))
    dr.polygon([(cx_g + 4, cy_g + 4), (cx_g + 22, cy_g + 18), (cx_g + 16, cy_g + 4)], fill=(235, 240, 246, 255))

    # 3. Crystal Multi-Reflector Headlamp + Amber Turn Indicator (256..512, 256..400)
    dr.rectangle([256, 256, 511, 399], fill=(195, 206, 220, 255), outline=(36, 40, 46, 255), width=6)
    # Upper amber corner turn signal
    dr.rectangle([424, 264, 503, 326], fill=(245, 148, 24, 255), outline=(145, 82, 12, 255), width=3)
    # Main halogen projector bulb bowls
    dr.ellipse([274, 274, 412, 386], fill=(238, 244, 252, 255), outline=(148, 160, 176, 255), width=4)
    dr.ellipse([316, 304, 370, 356], fill=(255, 255, 255, 255), outline=(175, 188, 205, 255), width=3)
    dr.rectangle([424, 330, 503, 390], fill=(228, 236, 246, 255), outline=(150, 162, 178, 255), width=3)

    # 4. Indonesian Black Truck Plate ("BM 8899 XY") + Amber Fog Lamp (0..512, 400..512)
    from PIL import ImageFont
    dr.rectangle([0, 400, 340, 511], fill=(16, 18, 22, 255), outline=(228, 232, 238, 255), width=5)
    plate_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
    plate_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 15)
    dr.text((52, 422), "BM 8899 XY", font=plate_font, fill=(244, 246, 250, 255))
    dr.text((134, 472), "10 . 30", font=plate_sub, fill=(215, 220, 228, 255))
    # Amber fog lamp lens (341..511, 400..511)
    dr.rectangle([342, 400, 511, 511], fill=(242, 162, 18, 255), outline=(120, 74, 8, 255), width=6)
    for fy in range(416, 500, 14):
        dr.line([(352, fy), (502, fy)], fill=(255, 210, 88, 255), width=3)

    return np.array(img, dtype=np.uint8)


def make_canter_paint_tile():
    # Iconic Mitsubishi Canter Canary-Gold Enamel Paint + Subtle Metallic Gradient + Door Handle & Trim!
    img = Image.new("RGBA", (TILE, TILE), (242, 196, 18, 255))
    dr = ImageDraw.Draw(img)
    for y in range(TILE):
        t = y / (TILE - 1.0)
        shade = 1.06 - 0.16 * t
        dr.line([(0, y), (TILE, y)], fill=(int(min(255, 244 * shade)), int(min(255, 196 * shade)), int(min(255, 18 * shade)), 255))
    # Crisp door panel shut-line & recessed black door handle in lower-right quadrant (optional UV zone)
    dr.rectangle([350, 340, 456, 392], fill=(26, 29, 34, 255), outline=(165, 130, 12, 255), width=3)
    dr.rectangle([366, 358, 440, 374], fill=(64, 68, 76, 255))
    return np.array(img, dtype=np.uint8)


def make_character_atlas_tile():
    # High-detail UV quadrants inside [2,2]:
    #   Q0 (0..256, 0..256): Expressive Indonesian Human Face (warm natural skin, brows, detailed almond eyes + iris + catchlight, nose shadow, lips)
    #   Q1 (256..512, 0..256): Natural Dark Layered Hair Texture
    #   Q2 (0..256, 256..512): Smooth Warm Southeast Asian Skin with subtle anatomical shading
    #   Q3 (256..512, 256..512): Dark Rugged Work Pants / Jeans Fabric Weave + Knee Reinforcement
    img = Image.new("RGBA", (TILE, TILE), (198, 146, 108, 255))
    dr = ImageDraw.Draw(img)

    # Q2 & Q0 Smooth Natural Southeast Asian Skin with continuous 3D anatomical shading (ZERO flat circles!)
    yy, xx = np.mgrid[0:256, 0:256].astype(np.float32) / 255.0
    skin_n = hash_noise((256, 256), 64, 515)
    # Smooth temple/jaw AO + gentle T-zone highlight
    temple_ao = 1.0 - 0.14 * np.clip(np.abs(xx - 0.5) * 2.0, 0.0, 1.0) ** 2.2
    eye_socket = np.exp(-((yy - 0.45) ** 2) / 0.0045) * np.exp(-((np.abs(xx - 0.5) - 0.15) ** 2) / 0.008)
    nose_hi = np.exp(-((xx - 0.5) ** 2) / 0.0018) * np.clip(1.0 - np.abs(yy - 0.53) * 7.5, 0.0, 1.0)

    face_shade = temple_ao - 0.10 * eye_socket + 0.06 * nose_hi
    q0 = np.zeros((256, 256, 4), dtype=np.uint8)
    q0[..., 0] = np.clip((196 + skin_n * 10) * face_shade, 0, 255).astype(np.uint8)
    q0[..., 1] = np.clip((144 + skin_n * 8) * face_shade, 0, 255).astype(np.uint8)
    q0[..., 2] = np.clip((106 + skin_n * 7) * face_shade, 0, 255).astype(np.uint8)
    q0[..., 3] = 255

    q2 = np.zeros((256, 256, 4), dtype=np.uint8)
    q2[..., 0] = np.clip(192 + skin_n * 11, 0, 255).astype(np.uint8)
    q2[..., 1] = np.clip(140 + skin_n * 9, 0, 255).astype(np.uint8)
    q2[..., 2] = np.clip(102 + skin_n * 8, 0, 255).astype(np.uint8)
    q2[..., 3] = 255

    img.paste(Image.fromarray(q0, "RGBA"), (0, 0))
    img.paste(Image.fromarray(q2, "RGBA"), (0, 256))

    # Paint natural athletic realistic eyes, eyebrows, nose shadow & mouth on Q0
    dr = ImageDraw.Draw(img)
    dr.polygon([(68, 97), (109, 93), (112, 99), (70, 102)], fill=(30, 22, 18, 255))
    dr.polygon([(188, 97), (147, 93), (144, 99), (186, 102)], fill=(30, 22, 18, 255))
    for ex in (90, 166):
        dr.line([(ex - 18, 105), (ex, 103), (ex + 18, 106)], fill=(128, 86, 62, 255), width=2)
        dr.polygon([(ex - 17, 117), (ex - 7, 109), (ex + 8, 109), (ex + 17, 117), (ex + 8, 123), (ex - 8, 123)],
                   fill=(242, 241, 242, 255))
        dr.ellipse([ex - 8, 109, ex + 8, 123], fill=(44, 26, 16, 255))
        dr.ellipse([ex - 4, 113, ex + 4, 120], fill=(12, 10, 10, 255))
        dr.ellipse([ex + 1, 111, ex + 4, 114], fill=(255, 255, 255, 255))
        dr.line([(ex - 18, 116), (ex - 6, 109), (ex + 8, 109), (ex + 18, 116)], fill=(24, 16, 14, 255), width=3)
    dr.ellipse([117, 149, 124, 154], fill=(134, 88, 64, 255))
    dr.ellipse([132, 149, 139, 154], fill=(134, 88, 64, 255))
    dr.polygon([(106, 173), (128, 170), (150, 173), (144, 181), (112, 181)], fill=(156, 98, 82, 255))
    dr.line([(105, 174), (128, 176), (151, 174)], fill=(104, 58, 48, 255), width=2)

    # Q1 (256..512, 0..256): Layered dark hair strands
    dr.rectangle([256, 0, 511, 255], fill=(24, 20, 18, 255))
    rng = np.random.default_rng(616)
    for _ in range(220):
        hx = rng.integers(258, 509)
        hy = rng.integers(0, 220)
        c = int(rng.integers(32, 58))
        dr.line([(hx, hy), (hx + rng.integers(-6, 7), hy + 36)], fill=(c, int(c * 0.85), int(c * 0.75), 255), width=2)

    # Q3 (256..512, 256..512): Rugged dark slate-denim field trousers with stitching
    denim_n = hash_noise((256, 256), 128, 717)
    denim = np.zeros((256, 256, 4), dtype=np.uint8)
    denim[..., 0] = np.clip(40 + denim_n * 22, 0, 255).astype(np.uint8)
    denim[..., 1] = np.clip(48 + denim_n * 24, 0, 255).astype(np.uint8)
    denim[..., 2] = np.clip(58 + denim_n * 26, 0, 255).astype(np.uint8)
    denim[..., 3] = 255
    img.paste(Image.fromarray(denim, "RGBA"), (256, 256))
    dr = ImageDraw.Draw(img)
    dr.line([(272, 256), (272, 512)], fill=(138, 112, 64, 255), width=2)
    dr.rectangle([296, 360, 472, 430], outline=(30, 36, 44, 255), width=3)

    return np.array(img, dtype=np.uint8)


def make_gear_and_fabric_tile():
    # [3,2] 4 sub-quadrants:
    #   Q0 (0..256, 0..256): White/Tintable Work Shirt Cotton Weave + Collar Placket, Buttons & Chest Pocket!
    #   Q1 (256..512, 0..256): Woven Bamboo Caping & Rattan Basket Weave!
    #   Q2 (0..256, 256..512): Tall Plantation Rubber Boot Texture (glossy dark olive/green rubber + muddy sole tread)
    #   Q3 (256..512, 256..512): Forged High-Carbon Steel Blade (Egrek / Dodos / Tojok) with bright bevel edge!
    img = Image.new("RGBA", (TILE, TILE), (235, 238, 240, 255))
    dr = ImageDraw.Draw(img)

    # Q0: Tintable white fabric weave (multiplied by outfit tint in shader!) with collar placket & chest pocket!
    fab = hash_noise((256, 256), 96, 818)
    q0 = np.clip(226 + fab[..., None] * 26, 0, 255).astype(np.uint8)
    q0_rgba = np.concatenate([np.repeat(q0, 3, axis=-1), np.full((256, 256, 1), 255, np.uint8)], axis=-1)
    img.paste(Image.fromarray(q0_rgba, "RGBA"), (0, 0))
    dr = ImageDraw.Draw(img)
    dr.rectangle([118, 8, 138, 128], fill=(205, 210, 215, 255), outline=(165, 170, 176, 255), width=2)
    for by in (34, 68, 102):
        dr.ellipse([124, by - 4, 132, by + 4], fill=(70, 74, 80, 255))
    dr.rectangle([152, 64, 206, 122], outline=(165, 170, 176, 255), width=3)
    dr.line([(152, 78), (206, 78)], fill=(165, 170, 176, 255), width=2)

    # Q1: Authentic Indonesian Woven Bamboo Caping / Rattan Basket Weave
    dr.rectangle([256, 0, 511, 255], fill=(184, 136, 72, 255))
    for wy in range(0, 256, 16):
        for wx in range(256, 512, 16):
            over = ((wx // 16 + wy // 16) % 2) == 0
            c1 = (206, 158, 88, 255) if over else (154, 108, 52, 255)
            dr.rectangle([wx + 1, wy + 1, wx + 14, wy + 14], fill=c1, outline=(112, 76, 34, 255))

    # Q2: Tall Plantation Rubber Boot with Mud Splatter & Yellow Top Cuff
    dr.rectangle([0, 256, 255, 511], fill=(34, 68, 46, 255))
    dr.rectangle([0, 256, 255, 278], fill=(214, 176, 38, 255))
    dr.rectangle([0, 456, 255, 511], fill=(42, 34, 28, 255))
    for rx in range(0, 256, 20):
        dr.rectangle([rx + 4, 480, rx + 14, 511], fill=(24, 20, 18, 255))

    # Q3: Forged Carbon-Steel Egrek/Dodos Blade (dark forged spine -> mirror-polished cutting bevel!)
    for x in range(256, 512):
        t = (x - 256) / 255.0
        v = int(88 + 158 * (t ** 1.5))
        dr.line([(x, 256), (x, 511)], fill=(v, int(v * 1.01), min(255, int(v * 1.04)), 255))

    return np.array(img, dtype=np.uint8)


def make_corrugated_metal_tile():
    y, x = np.mgrid[0:TILE, 0:TILE].astype(np.float32) / TILE
    rib = 0.5 + 0.5 * np.sin(x * math.pi * 2.0 * 16.0)
    weather = fbm((TILE, TILE), 12, 4, 919)
    val = 148 + rib * 52 + weather * 26
    rgb = np.stack([val * 0.96, val * 0.99, val * 1.02], axis=-1)
    a = np.full((TILE, TILE, 1), 255.0, dtype=np.float32)
    return np.clip(np.concatenate([rgb, a], axis=-1), 0, 255).astype(np.uint8)


def make_concrete_pad_tile():
    n1 = fbm((TILE, TILE), 16, 5, 1010)
    fine = hash_noise((TILE, TILE), 128, 1111)
    v = 132 + n1 * 38 + fine * 18
    arr = np.stack([v, v * 1.0, v * 0.98, np.full_like(v, 255.0)], axis=-1)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    dr = ImageDraw.Draw(img)
    # Expansion joint grid lines + crisp yellow industrial border stripe at bottom
    dr.line([(0, 256), (TILE, 256)], fill=(86, 88, 92, 255), width=4)
    dr.line([(256, 0), (256, TILE)], fill=(86, 88, 92, 255), width=4)
    for sx in range(-64, TILE + 64, 48):
        dr.polygon([(sx, 468), (sx + 24, 468), (sx + 8, 511), (sx - 16, 511)], fill=(232, 182, 24, 255))
    return np.array(img, dtype=np.uint8)


def make_granite_rock_tile():
    n1 = fbm((TILE, TILE), 12, 5, 1212)
    n2 = hash_noise((TILE, TILE), 96, 1313)
    v = 92 + n1 * 64 + n2 * 24
    rgb = np.stack([v * 1.02, v * 0.99, v * 0.94], axis=-1)
    a = np.full((TILE, TILE, 1), 255.0, dtype=np.float32)
    return np.clip(np.concatenate([rgb, a], axis=-1), 0, 255).astype(np.uint8)


def make_soft_puff_alpha_tile():
    y, x = np.mgrid[0:TILE, 0:TILE].astype(np.float32) / TILE - 0.5
    r = np.sqrt(x * x + y * y) * 2.0
    n = fbm((TILE, TILE), 6, 4, 1414)
    alpha = np.clip((1.0 - r) * 1.35 * (0.62 + 0.55 * n), 0.0, 1.0) ** 1.5
    lit = np.clip(0.72 + 0.28 * (0.5 - y) + 0.15 * n, 0.0, 1.0)
    rgb = np.stack([lit * 255.0, lit * 252.0, lit * 246.0, alpha * 255.0], axis=-1)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def main():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out_dir = os.path.join(root, "src", "Nyawit.Android", "Assets", "Textures")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "nyawit_pbr_atlas.png")

    atlas = np.zeros((ATLAS, ATLAS, 4), dtype=np.uint8)

    def put(col, row, data):
        atlas[row * TILE:(row + 1) * TILE, col * TILE:(col + 1) * TILE] = data

    put(0, 0, make_grass_tile())
    put(1, 0, make_dirt_road_tile())
    put(2, 0, make_palm_bark_tile())
    put(3, 0, make_tbs_fruit_tile())

    put(0, 1, make_palm_frond_alpha_tile())
    put(1, 1, make_fern_alpha_tile())
    put(2, 1, make_wood_planks_tile())
    put(3, 1, make_tire_and_wheel_tile())

    put(0, 2, make_canter_front_atlas_tile())
    put(1, 2, make_canter_paint_tile())
    put(2, 2, make_character_atlas_tile())
    put(3, 2, make_gear_and_fabric_tile())

    put(0, 3, make_corrugated_metal_tile())
    put(1, 3, make_concrete_pad_tile())
    put(2, 3, make_granite_rock_tile())
    put(3, 3, make_soft_puff_alpha_tile())

    img = Image.fromarray(atlas, "RGBA")
    img.save(out_path, optimize=True)
    sz_kb = os.path.getsize(out_path) / 1024.0
    print(f"Generated {out_path} ({ATLAS}x{ATLAS} RGBA8, {sz_kb:.1f} KB)")


if __name__ == "__main__":
    main()
