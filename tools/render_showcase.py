#!/usr/bin/env python3
"""
Renders Studio 3D Asset Verification Sheet + Android Launcher Icons + 1200x630 OG Banner
using the exact GPU shader dye mask (uv.x >= 0.75) and official XyVerse Display glyph subset!
"""

from __future__ import annotations
import math
import os
import struct
from typing import Dict, List, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def load_npak(path: str):
    blob = open(path, "rb").read()
    magic, ver, count = struct.unpack_from("<4sII", blob, 0)
    assert magic == b"NPAK" and ver == 1
    off = 12
    dtype_v = np.dtype([("pos", "<f4", (3,)), ("nrm", "<f4", (3,)), ("uv", "<f4", (2,)), ("col", "u1", (4,))])
    lib = {}
    for _ in range(count):
        nlen, rad, b0, b1, b2, x0, x1, x2, lods = struct.unpack_from("<BfffffffB", blob, off)
        off += 30
        name = blob[off:off + nlen].decode("utf-8")
        off += nlen
        lod_list = []
        for _ in range(lods):
            vcnt, icnt = struct.unpack_from("<II", blob, off)
            off += 8
            v_arr = np.frombuffer(blob, dtype=dtype_v, count=vcnt, offset=off).copy()
            off += vcnt * 36
            i_arr = np.frombuffer(blob, dtype="<u2", count=icnt, offset=off).reshape(-1, 3).copy()
            off += icnt * 2
            lod_list.append((v_arr["pos"], v_arr["nrm"], v_arr["uv"], v_arr["col"], i_arr))
        lib[name] = lod_list
    return lib


def mat_trs(tx=0.0, ty=0.0, tz=0.0, rx=0.0, ry=0.0, rz=0.0, sx=1.0, sy=1.0, sz=1.0) -> np.ndarray:
    cx, sxn = math.cos(rx), math.sin(rx)
    cy, syn = math.cos(ry), math.sin(ry)
    cz, szn = math.cos(rz), math.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sxn], [0, sxn, cx]], dtype=np.float32)
    my = np.array([[cy, 0, syn], [0, 1, 0], [-syn, 0, cy]], dtype=np.float32)
    mz = np.array([[cz, -szn, 0], [szn, cz, 0], [0, 0, 1]], dtype=np.float32)
    m = np.eye(4, dtype=np.float32)
    m[:3, :3] = (my @ mx @ mz) * np.array([sx, sy, sz], dtype=np.float32)[None, :]
    m[:3, 3] = [tx, ty, tz]
    return m


def rasterize_scene(instances, w: int, h: int, eye, target, fov_deg: float = 40.0, bg_top=(18, 30, 26), bg_bot=(9, 13, 12)) -> Image.Image:
    sw, sh = w * 2, h * 2
    ys = np.linspace(0.0, 1.0, sh, dtype=np.float32)[:, None, None]
    fb = np.broadcast_to(
        np.asarray(bg_top, dtype=np.float32)[None, None, :] * (1.0 - ys)
        + np.asarray(bg_bot, dtype=np.float32)[None, None, :] * ys,
        (sh, sw, 3),
    ).copy()
    zb = np.full((sh, sw), 1e9, dtype=np.float32)

    eye_v, tgt_v = np.asarray(eye, dtype=np.float32), np.asarray(target, dtype=np.float32)
    fwd = tgt_v - eye_v
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, np.array([0.0, 1.0, 0.0], dtype=np.float32))
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)

    f = 1.0 / math.tan(math.radians(fov_deg) * 0.5)
    aspect = sw / sh
    sun = np.array([0.48, 0.76, 0.44], dtype=np.float32)
    sun /= np.linalg.norm(sun)
    rim_dir = np.array([-0.55, 0.42, -0.72], dtype=np.float32)
    rim_dir /= np.linalg.norm(rim_dir)

    for pos, nrm, uv, col, idx, world_m, tint in instances:
        rmat = world_m[:3, :3]
        wpos = (pos @ rmat.T) + world_m[:3, 3]
        wnrm = nrm @ rmat.T
        wnrm /= np.maximum(np.linalg.norm(wnrm, axis=1, keepdims=True), 1e-6)

        rel = wpos - eye_v
        cx, cy, cz = rel @ right, rel @ up, rel @ fwd

        ndotl = np.clip(wnrm @ sun, 0.0, 1.0)
        hemi = 0.36 + 0.24 * (wnrm[:, 1] * 0.5 + 0.5)
        rim = np.clip(wnrm @ rim_dir, 0.0, 1.0) ** 2.2 * 0.28
        spec = (np.clip(wnrm @ sun, 0.0, 1.0) ** 14.0) * 0.18
        ao = col[:, 3:4].astype(np.float32) / 255.0
        dye_mask = (uv[:, 0:1] >= 0.75).astype(np.float32)
        eff_tint = (1.0 - dye_mask) + dye_mask * np.asarray(tint, dtype=np.float32)[None, :]
        albedo = (col[:, :3].astype(np.float32) / 255.0) * eff_tint
        lit = np.clip((albedo * (hemi[:, None] + 0.86 * ndotl[:, None] + rim[:, None]) + spec[:, None]) * (0.48 + 0.52 * ao), 0.0, 1.0) * 255.0

        sx_p = (cx / np.maximum(cz, 0.1) * (f / aspect) * 0.5 + 0.5) * sw
        sy_p = (0.5 - cy / np.maximum(cz, 0.1) * f * 0.5) * sh

        for t0, t1, t2 in idx:
            z0, z1, z2 = float(cz[t0]), float(cz[t1]), float(cz[t2])
            if z0 < 0.2 or z1 < 0.2 or z2 < 0.2:
                continue
            x0, y0 = float(sx_p[t0]), float(sy_p[t0])
            x1, y1 = float(sx_p[t1]), float(sy_p[t1])
            x2, y2 = float(sx_p[t2]), float(sy_p[t2])
            # True GL_CCW screen-space backface culling (y screen is downward so CCW 3D has area < 0)
            area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
            if area >= -0.25:
                continue
            minx, maxx = max(0, int(min(x0, x1, x2))), min(sw - 1, int(math.ceil(max(x0, x1, x2))))
            miny, maxy = max(0, int(min(y0, y1, y2))), min(sh - 1, int(math.ceil(max(y0, y1, y2))))
            if minx > maxx or miny > maxy:
                continue
            xs_g = np.arange(minx, maxx + 1, dtype=np.float32)[None, :] + 0.5
            ys_g = np.arange(miny, maxy + 1, dtype=np.float32)[:, None] + 0.5
            inv_a = 1.0 / area
            w0 = ((x1 - xs_g) * (y2 - ys_g) - (x2 - xs_g) * (y1 - ys_g)) * inv_a
            w1 = ((x2 - xs_g) * (y0 - ys_g) - (x0 - xs_g) * (y2 - ys_g)) * inv_a
            w2 = 1.0 - w0 - w1
            inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
            if not np.any(inside):
                continue
            z_interp = w0 * z0 + w1 * z1 + w2 * z2
            sub_z = zb[miny:maxy + 1, minx:maxx + 1]
            vis = inside & (z_interp < sub_z)
            if not np.any(vis):
                continue
            sub_z[vis] = z_interp[vis]
            fb[miny:maxy + 1, minx:maxx + 1][vis] = (w0[..., None] * lit[t0] + w1[..., None] * lit[t1] + w2[..., None] * lit[t2])[vis]

    return Image.fromarray(fb.astype(np.uint8)).resize((w, h), Image.Resampling.LANCZOS)


def assemble_palm(lib, gold_fruit=False):
    out = [
        (*lib["palm_trunk"][0], mat_trs(0, 0, 0), (1.0, 1.0, 1.0)),
        (*lib["palm_crown"][0], mat_trs(0.30, 6.28, 0.24), (1.0, 1.0, 1.0)),
        (*lib["tropical_fern"][0], mat_trs(0.55, 0.0, 0.45), (1.0, 1.0, 1.0)),
    ]
    for i in range(6):
        ang = i * (2 * math.pi / 6) + 0.4
        tint = (1.15, 1.55, 0.40) if (gold_fruit or i == 1) else (1.0, 1.0, 1.0)
        out.append((*lib["tbs_bunch"][0], mat_trs(0.30 + math.sin(ang) * 0.46, 5.95 - (i % 2) * 0.22, 0.24 + math.cos(ang) * 0.46, ry=ang), tint))
    return out


def assemble_truck(lib):
    body_m = mat_trs(0, 0.04, 0, rz=-0.045, rx=-0.015)
    out = [
        (*lib["canter_truck_body"][0], body_m, (1.0, 1.0, 1.0)),
        (*lib["truck_cargo_heap"][0], body_m @ mat_trs(0, 0.82, 0), (1.0, 1.0, 1.0)),
    ]
    for sx, susp_y in ((-0.88, 0.46), (0.88, 0.52)):
        # Front wheels turned 22 degrees (steering animation!) + independent suspension travel!
        out.append((*lib["truck_wheel"][0], mat_trs(sx, susp_y, 1.55, ry=0.38, rx=0.65), (1.0, 1.0, 1.0)))
        out.append((*lib["truck_wheel"][0], mat_trs(sx, susp_y, -1.25, rx=0.65), (1.0, 1.0, 1.0)))
    return out


def assemble_boar(lib):
    body = mat_trs(-0.92, 0.04, 0.20, ry=0.48, rx=-0.05)
    out = [(*lib["celeng_boar"][0], body, (1.0, 1.0, 1.0))]
    for sx, sz, swing in ((-0.20, 0.44, -0.42), (0.20, 0.44, 0.36), (-0.19, -0.44, 0.38), (0.19, -0.44, -0.35)):
        out.append((*lib["boar_leg"][0], body @ mat_trs(sx, 0.50, sz, rx=swing), (1.0, 1.0, 1.0)))
    return out


def assemble_angkong(lib):
    cart = mat_trs(0.95, 0.0, -0.10, ry=-0.42)
    return [
        (*lib["angkong_cart"][0], cart, (1.0, 1.0, 1.0)),
        (*lib["truck_wheel"][0], cart @ mat_trs(0.0, 0.29, 0.80, rx=0.85, sx=0.45, sy=0.59, sz=0.59), (1.0, 1.0, 1.0)),
    ]


def assemble_harvester(lib, shirt_rgb, hat_key, back_key, tool_key, holding_tbs=False):
    hip_m = mat_trs(0, 0.88, 0, rx=(0.06 if holding_tbs else 0.0))
    head_m = hip_m @ mat_trs(0, 0.56, 0.01, ry=0.10, rx=-0.04)

    # Articulated two-joint legs (Hip -> Thigh -> Knee -> Calf + Tall Rubber Boot!)
    th_l = hip_m @ mat_trs(-0.115, 0.0, 0.0, rx=-0.16)
    cf_l = th_l @ mat_trs(0.0, -0.43, 0.0, rx=0.22)
    th_r = hip_m @ mat_trs(0.115, 0.0, 0.0, rx=0.18)
    cf_r = th_r @ mat_trs(0.0, -0.43, 0.0, rx=0.06)

    if holding_tbs:
        # Two-handed TBS cradling pose in front of chest!
        ua_l = hip_m @ mat_trs(-0.245, 0.485, 0.01, rx=-0.78, rz=-0.22)
        fa_l = ua_l @ mat_trs(0.0, -0.27, 0.01, rx=-0.72, ry=0.26)
        ua_r = hip_m @ mat_trs(0.245, 0.485, 0.01, rx=-0.78, rz=0.22)
        fa_r = ua_r @ mat_trs(0.0, -0.27, 0.01, rx=-0.72, ry=-0.26)
    else:
        # Heroic two-handed Egrek / Dodos stance held clearly forward in both hands!
        ua_l = hip_m @ mat_trs(-0.245, 0.485, 0.01, rx=-0.92, rz=-0.34)
        fa_l = ua_l @ mat_trs(0.0, -0.27, 0.01, rx=-0.38, ry=0.28)
        ua_r = hip_m @ mat_trs(0.245, 0.485, 0.01, rx=-0.66, rz=0.26)
        fa_r = ua_r @ mat_trs(0.0, -0.27, 0.01, rx=-0.52, ry=-0.18)

    out = [
        (*lib["char_torso_head"][0], hip_m, shirt_rgb),
        (*lib["char_head"][0], head_m, (1.0, 1.0, 1.0)),
        (*lib["char_leg"][0], th_l, (1.0, 1.0, 1.0)),
        (*lib["char_calf_boot"][0], cf_l, (1.0, 1.0, 1.0)),
        (*lib["char_leg"][0], th_r, (1.0, 1.0, 1.0)),
        (*lib["char_calf_boot"][0], cf_r, (1.0, 1.0, 1.0)),
        (*lib["char_arm"][0], ua_l, shirt_rgb),
        (*lib["char_forearm_hand"][0], fa_l, (1.0, 1.0, 1.0)),
        (*lib["char_arm"][0], ua_r, shirt_rgb),
        (*lib["char_forearm_hand"][0], fa_r, (1.0, 1.0, 1.0)),
        (*lib[back_key][0], hip_m @ mat_trs(0, 0.36, -0.14), (1.0, 1.0, 1.0)),
    ]
    if hat_key:
        out.append((*lib[hat_key][0], head_m @ mat_trs(0, 0.255, 0.01), (1.0, 1.0, 1.0)))
    if holding_tbs:
        out.append((*lib["tbs_bunch"][0], hip_m @ mat_trs(0.0, 0.34, 0.44, rx=0.35, sx=0.82, sy=0.82, sz=0.82), (1.05, 1.15, 0.90)))
    elif tool_key:
        out.append((*lib[tool_key][0], hip_m @ mat_trs(0.04, 0.24, 0.38, rx=0.14, rz=0.10), (1.0, 1.0, 1.0)))
    return out


def main() -> None:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    npak_path = os.path.join(root, "src", "Nyawit.Android", "Assets", "Meshes", "nyawit_models.npak")
    font_path = os.path.join(root, "src", "Nyawit.Android", "Assets", "Fonts", "XyVerseDisplay-Semibold.otf")
    mark_path = os.path.join(root, "src", "Nyawit.Android", "Assets", "Brand", "mark_kecil_transparan_putih.png")
    logo_path = os.path.join(root, "src", "Nyawit.Android", "Assets", "Brand", "logo_utama_horizontal_transparan_putih.png")

    lib = load_npak(npak_path)
    pks_scene = [
        (*lib["pks_factory"][0], mat_trs(0, 0, -2.8), (1, 1, 1)),
        (*lib["pks_fan"][0], mat_trs(-1.5, 8.35, -4.4, ry=0.4), (1, 1, 1)),
        (*lib["pks_fan"][0], mat_trs(1.5, 8.35, -1.2, ry=1.1), (1, 1, 1)),
        (*lib["steam_puff"][0], mat_trs(-3.2, 14.8, -5.0, sx=1.5, sy=1.4, sz=1.5), (1, 1, 1)),
        (*lib["steam_puff"][0], mat_trs(-2.8, 16.4, -5.6, sx=2.1, sy=1.8, sz=2.1), (1, 1, 1)),
        (*lib["weighbridge_ram"][0], mat_trs(0, 0, 7.0), (1, 1, 1)),
    ]
    cards = [
        ("POHON SAWIT TENERA DAN TBS EMAS", "DOUBLE-SIDED PELEPAH / ZERO BOLONG", assemble_palm(lib, True), (9.8, 6.4, 11.2), (0.2, 4.3, 0.2)),
        ("CANTER OLENG SUSPENSI DAN BELOK", "BAN DEPAN BELOK 22 DEG / SUSPENSI AKTIF", assemble_truck(lib), (4.8, 2.7, 5.2), (0.0, 1.12, 0.1)),
        ("ANATOMI SULTAN WAJAH DAN JARI", "11-PART RIG / WAJAH / JARI / SEPATU BOOT", assemble_harvester(lib, (0.14, 0.18, 0.28), "hat_crown_gold", "back_wings_gold", "tool_egrek_dragon", False), (2.25, 1.85, 3.15), (0.0, 1.15, 0.05)),
        ("ANIMASI PEGANG DAN ANGKAT SAWIT", "PEGANG DUA TANGAN / ANGKUT KE TRUK", assemble_harvester(lib, (0.16, 0.72, 0.44), None, "back_basket", "tool_egrek", True), (1.85, 1.72, 2.45), (0.0, 1.16, 0.12)),
        ("PABRIK PKS TURBIN DAN UAP AKTIF", "TURBIN BERPUTAR / UAP BOILER / RAM LED", pks_scene, (20.5, 14.5, 24.5), (0.4, 5.4, 0.8)),
        ("CELENG KAKI AKTIF DAN ANGKONG", "4 KAKI BERLARI / RODA ANGKONG BERPUTAR", assemble_boar(lib) + assemble_angkong(lib), (3.1, 2.0, 3.4), (0.0, 0.55, 0.0)),
    ]

    W, H = 1800, 1120
    sheet = Image.new("RGBA", (W, H), (11, 14, 13, 255))
    draw = ImageDraw.Draw(sheet)
    f_title = ImageFont.truetype(font_path, 34)
    f_card = ImageFont.truetype(font_path, 19)
    f_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)

    draw.text((48, 32), "NYAWIT LIVE  -  WATERTIGHT ANATOMY AND PHYSICS MODELS", font=f_title, fill=(255, 255, 255, 255))
    logo_img = Image.open(logo_path).convert("RGBA")
    lh = 44
    lw = int(logo_img.width * (lh / logo_img.height))
    sheet.alpha_composite(logo_img.resize((lw, lh), Image.Resampling.LANCZOS), (W - lw - 48, 28))

    cw, ch = 552, 476
    for idx_c, (title, sub, scene_inst, eye, tgt) in enumerate(cards):
        col_i, row_i = idx_c % 3, idx_c // 3
        x0, y0 = 42 + col_i * (cw + 30), 104 + row_i * (ch + 30)
        rendered = rasterize_scene(scene_inst, cw, ch - 68, eye, tgt, fov_deg=40.0).convert("RGBA")
        draw.rectangle([x0 - 2, y0 - 2, x0 + cw + 2, y0 + ch + 2], fill=(18, 24, 21, 255), outline=(48, 232, 138, 255), width=2)
        sheet.alpha_composite(rendered, (x0, y0))
        draw.text((x0 + 18, y0 + ch - 54), title, font=f_card, fill=(255, 255, 255, 255))
        draw.text((x0 + 18, y0 + ch - 27), sub, font=f_sub, fill=(48, 232, 138, 255))

    sheet.convert("RGB").save(os.path.join(root, "docs", "screenshots", "models_showcase.png"), quality=92)

    icon_scene = (
        [(a, b, u, c, d, mat_trs(-1.35, -3.2, -1.4) @ m, t) for (a, b, u, c, d, m, t) in assemble_palm(lib, True)]
        + [(a, b, u, c, d, mat_trs(1.15, 0.0, 0.65, ry=-0.55) @ m, t) for (a, b, u, c, d, m, t) in assemble_truck(lib)]
        + [(a, b, u, c, d, mat_trs(-0.75, 0.0, 2.35, ry=0.35) @ m, t) for (a, b, u, c, d, m, t) in assemble_harvester(lib, (0.16, 0.76, 0.44), "hat_caping", "back_basket", "tool_egrek")]
    )
    icon_base = rasterize_scene(icon_scene, 512, 512, (4.8, 3.2, 6.2), (0.15, 1.75, 0.2), fov_deg=44.0, bg_top=(24, 96, 64), bg_bot=(12, 26, 20)).convert("RGBA")
    idraw = ImageDraw.Draw(icon_base)
    idraw.rectangle([0, 412, 512, 512], fill=(13, 13, 13, 232))
    idraw.text((34, 432), "NYAWIT 3D", font=ImageFont.truetype(font_path, 56), fill=(255, 214, 58, 255))
    icon_base.alpha_composite(Image.open(mark_path).convert("RGBA").resize((44, 44), Image.Resampling.LANCZOS), (440, 434))

    for folder, sz in {"mipmap-mdpi": 48, "mipmap-hdpi": 72, "mipmap-xhdpi": 96, "mipmap-xxhdpi": 144, "mipmap-xxxhdpi": 192}.items():
        mdir = os.path.join(root, "src", "Nyawit.Android", "Resources", folder)
        os.makedirs(mdir, exist_ok=True)
        icon_base.resize((sz, sz), Image.Resampling.LANCZOS).save(os.path.join(mdir, "ic_launcher.png"))
        icon_base.resize((sz, sz), Image.Resampling.LANCZOS).save(os.path.join(mdir, "ic_launcher_round.png"))

    icon_base.resize((192, 192), Image.Resampling.LANCZOS).save(os.path.join(root, "server", "public", "assets", "icon-192.png"))
    icon_base.save(os.path.join(root, "server", "public", "assets", "icon-512.png"))

    og = rasterize_scene(icon_scene, 1200, 630, (5.8, 3.4, 7.2), (0.0, 1.85, 0.0), fov_deg=43.0, bg_top=(18, 68, 48), bg_bot=(11, 15, 14)).convert("RGBA")
    od = ImageDraw.Draw(og)
    od.rectangle([0, 470, 1200, 630], fill=(13, 13, 13, 234))
    od.text((48, 494), "NYAWIT LIVE 3D", font=ImageFont.truetype(font_path, 54), fill=(255, 255, 255, 255))
    od.text((48, 562), "LIVE MULTIPLAYER  /  GLOBAL RANKING  /  TURNAMEN MINGGUAN", font=ImageFont.truetype(font_path, 21), fill=(92, 224, 146, 255))
    lw2 = int(logo_img.width * (52 / logo_img.height))
    og.alpha_composite(logo_img.resize((lw2, 52), Image.Resampling.LANCZOS), (1200 - lw2 - 48, 520))
    og.convert("RGB").save(os.path.join(root, "server", "public", "assets", "og_banner.png"), quality=92)
    print("Clean re-render complete!")


if __name__ == "__main__":
    main()
