#!/usr/bin/env python3
"""
Perspective-correct UV-Textured PBR + Alpha-Cutout Showcase Renderer for Nyawit Live 3D v4.0.
Verifies exact UV alignment, alpha-cutout pinnate fronds, COE Mitsubishi Canter FE 74 HD details,
seamless human anatomy, accessories, and the separate 3D Garage Lobby scene on docs/screenshots/models_showcase.png!
"""
import math
import os
import struct
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def load_npak(path: str):
    with open(path, "rb") as f:
        data = f.read()
    pos = 0
    magic, ver, count = struct.unpack_from("<4sII", data, pos)
    pos += 12
    assert magic == b"NPAK" and ver == 1
    dtype_v = np.dtype([("pos", "<f4", (3,)), ("nrm", "<f4", (3,)), ("uv", "<f4", (2,)), ("col", "u1", (4,))])
    lib = {}
    for _ in range(count):
        nlen = data[pos]
        lod_cnt = data[pos + 29]
        pos += 30
        name = data[pos:pos + nlen].decode("utf-8")
        pos += nlen
        lods = []
        for _ in range(lod_cnt):
            vcnt, icnt = struct.unpack_from("<II", data, pos)
            pos += 8
            vbytes = vcnt * 36
            ibytes = icnt * 2
            verts = np.frombuffer(data[pos:pos + vbytes], dtype=dtype_v).copy()
            pos += vbytes
            idx = np.frombuffer(data[pos:pos + ibytes], dtype="<u2").reshape(-1, 3).astype(np.int32).copy()
            pos += ibytes
            lods.append((verts, idx))
        lib[name] = lods
    return lib


def mat_trs(tx=0.0, ty=0.0, tz=0.0, rx=0.0, ry=0.0, rz=0.0, sx=1.0, sy=1.0, sz=1.0) -> np.ndarray:
    cx, s_x = math.cos(rx), math.sin(rx)
    cy, s_y = math.cos(ry), math.sin(ry)
    cz, s_z = math.cos(rz), math.sin(rz)
    mx = np.array([[1, 0, 0, 0], [0, cx, -s_x, 0], [0, s_x, cx, 0], [0, 0, 0, 1]], np.float32)
    my = np.array([[cy, 0, s_y, 0], [0, 1, 0, 0], [-s_y, 0, cy, 0], [0, 0, 0, 1]], np.float32)
    mz = np.array([[cz, -s_z, 0, 0], [s_z, cz, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], np.float32)
    ms = np.diag([sx, sy, sz, 1.0]).astype(np.float32)
    mt = np.array([[1, 0, 0, tx], [0, 1, 0, ty], [0, 0, 1, tz], [0, 0, 0, 1]], np.float32)
    return mt @ my @ mx @ mz @ ms


def look_at(eye, target, up=(0.0, 1.0, 0.0)) -> np.ndarray:
    e, t, u = np.asarray(eye, np.float32), np.asarray(target, np.float32), np.asarray(up, np.float32)
    f = t - e
    f /= np.linalg.norm(f)
    s = np.cross(f, u)
    s /= np.linalg.norm(s)
    v = np.cross(s, f)
    m = np.eye(4, dtype=np.float32)
    m[0, :3], m[1, :3], m[2, :3] = s, v, -f
    m[0, 3], m[1, 3], m[2, 3] = -np.dot(s, e), -np.dot(v, e), np.dot(f, e)
    return m


def perspective(fov_rad: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(fov_rad * 0.5)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2.0 * far * near) / (near - far)
    m[3, 2] = -1.0
    return m


def rasterize_scene(instances, atlas_rgba: np.ndarray, w: int, h: int, eye, target, fov_deg: float = 39.0) -> Image.Image:
    ss = 2
    W, H = w * ss, h * ss
    fb = np.zeros((H, W, 3), dtype=np.float32)
    gy = np.linspace(0.0, 1.0, H, dtype=np.float32)[:, None]
    # Rich atmospheric studio background gradient
    fb[..., 0] = 24.0 + 26.0 * (1.0 - gy)
    fb[..., 1] = 34.0 + 38.0 * (1.0 - gy)
    fb[..., 2] = 44.0 + 52.0 * (1.0 - gy)
    zb = np.full((H, W), 1e9, dtype=np.float32)

    ah, aw = atlas_rgba.shape[0], atlas_rgba.shape[1]
    vp = perspective(math.radians(fov_deg), W / H, 0.25, 220.0) @ look_at(eye, target)
    sun = np.array([0.48, 0.76, 0.44], dtype=np.float32)
    sun /= np.linalg.norm(sun)
    view_dir = np.asarray(eye, np.float32) - np.asarray(target, np.float32)
    view_dir /= np.linalg.norm(view_dir)
    half_v = (sun + view_dir)
    half_v /= np.linalg.norm(half_v)

    for verts, idx, model, tint in instances:
        pos4 = np.hstack([verts["pos"], np.ones((len(verts), 1), np.float32)])
        wpos = (pos4 @ model.T)[:, :3]
        wnrm = verts["nrm"] @ model[:3, :3].T
        nl = np.linalg.norm(wnrm, axis=1, keepdims=True)
        wnrm = wnrm / np.maximum(1e-6, nl)

        clip = np.hstack([wpos, np.ones((len(verts), 1), np.float32)]) @ vp.T
        cw = clip[:, 3]
        inv_w = 1.0 / np.maximum(1e-4, cw)
        sx = (clip[:, 0] * inv_w * 0.5 + 0.5) * W
        sy = (0.5 - clip[:, 1] * inv_w * 0.5) * H

        vcol = verts["col"].astype(np.float32) / 255.0
        gloss = vcol[:, 3]
        raw_uv = verts["uv"].copy()
        is_dye = (raw_uv[:, 0] > 1.5).astype(np.float32)
        raw_uv[:, 0] -= is_dye * 2.0
        tint_arr = np.asarray(tint, np.float32)[None, :]
        eff_tint = (1.0 - is_dye[:, None]) + is_dye[:, None] * tint_arr

        # Vertex lighting term (sun + warm tropical sky bounce + specular)
        ndl = np.maximum(0.0, wnrm @ sun)
        # Double-sided leaf translucency for thin botanical sheets!
        back_light = np.maximum(0.0, -(wnrm @ sun)) * 0.42
        sky = 0.36 + 0.16 * (wnrm[:, 1] * 0.5 + 0.5)
        spec = (np.maximum(0.0, wnrm @ half_v) ** (8.0 + gloss * 40.0)) * gloss * 0.55
        emissive = (gloss > 0.97).astype(np.float32) * 0.85

        shade = (sky + (ndl + back_light) * 0.86 + emissive)[:, None] * vcol[:, :3] * eff_tint
        spec_rgb = spec[:, None] * np.array([[255.0, 248.0, 232.0]], np.float32)

        uv_over_w = raw_uv * inv_w[:, None]

        for t0, t1, t2 in idx:
            if cw[t0] <= 0.25 or cw[t1] <= 0.25 or cw[t2] <= 0.25:
                continue
            x0, y0 = sx[t0], sy[t0]
            x1, y1 = sx[t1], sy[t1]
            x2, y2 = sx[t2], sy[t2]
            area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
            if abs(area) < 1e-3:
                continue
            minx = max(0, int(min(x0, x1, x2)))
            maxx = min(W - 1, int(max(x0, x1, x2)) + 1)
            miny = max(0, int(min(y0, y1, y2)))
            maxy = min(H - 1, int(max(y0, y1, y2)) + 1)
            if minx > maxx or miny > maxy:
                continue

            py, px = np.mgrid[miny:maxy + 1, minx:maxx + 1]
            px = px.astype(np.float32) + 0.5
            py = py.astype(np.float32) + 0.5
            inv_area = 1.0 / area
            w0 = ((x1 - px) * (y2 - py) - (x2 - px) * (y1 - py)) * inv_area
            w1 = ((x2 - px) * (y0 - py) - (x0 - px) * (y2 - py)) * inv_area
            w2 = 1.0 - w0 - w1
            inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
            if not np.any(inside):
                continue

            one_over_w = w0 * inv_w[t0] + w1 * inv_w[t1] + w2 * inv_w[t2]
            z_cam = 1.0 / np.maximum(1e-6, one_over_w)
            sub_z = zb[miny:maxy + 1, minx:maxx + 1]
            cand = inside & (z_cam < sub_z)
            if not np.any(cand):
                continue

            u_p = ((w0 * uv_over_w[t0, 0] + w1 * uv_over_w[t1, 0] + w2 * uv_over_w[t2, 0]) * z_cam)[cand]
            v_p = ((w0 * uv_over_w[t0, 1] + w1 * uv_over_w[t1, 1] + w2 * uv_over_w[t2, 1]) * z_cam)[cand]
            tx_i = np.clip((np.mod(u_p, 1.0) * (aw - 1)).astype(np.int32), 0, aw - 1)
            ty_i = np.clip((np.mod(v_p, 1.0) * (ah - 1)).astype(np.int32), 0, ah - 1)
            texel = atlas_rgba[ty_i, tx_i]

            alpha_ok = texel[:, 3] >= 115
            if not np.any(alpha_ok):
                continue

            vis_mask = np.zeros_like(cand)
            vis_mask[cand] = alpha_ok
            sub_z[vis_mask] = z_cam[vis_mask]

            sh_p = (w0[vis_mask, None] * shade[t0] + w1[vis_mask, None] * shade[t1] + w2[vis_mask, None] * shade[t2])
            sp_p = (w0[vis_mask, None] * spec_rgb[t0] + w1[vis_mask, None] * spec_rgb[t1] + w2[vis_mask, None] * spec_rgb[t2])
            lit_rgb = texel[alpha_ok, :3].astype(np.float32) * sh_p + sp_p
            fb[miny:maxy + 1, minx:maxx + 1][vis_mask] = np.clip(lit_rgb, 0.0, 255.0)

    return Image.fromarray(fb.astype(np.uint8)).resize((w, h), Image.Resampling.LANCZOS)


def assemble_palm(lib):
    out = [
        (*lib["palm_trunk"][0], mat_trs(0, 0, 0), (1.0, 1.0, 1.0)),
        (*lib["palm_crown"][0], mat_trs(0.28, 6.32, 0.20), (1.0, 1.0, 1.0)),
        (*lib["tropical_fern"][0], mat_trs(0.55, 0.0, 0.45), (1.0, 1.0, 1.0)),
    ]
    for i in range(6):
        ang = i * (2 * math.pi / 6) + 0.4
        out.append((*lib["tbs_bunch"][0], mat_trs(0.28 + math.sin(ang) * 0.42, 5.96 - (i % 2) * 0.20, 0.20 + math.cos(ang) * 0.42, ry=ang), (1.0, 1.0, 1.0)))
    return out


def assemble_truck(lib):
    body_m = mat_trs(0, 0.02, 0, rz=-0.035, rx=-0.01)
    out = [
        (*lib["canter_truck_body"][0], body_m, (1.0, 1.0, 1.0)),
        (*lib["canter_steering_wheel"][0], body_m @ mat_trs(0.42, 1.46, 1.88, rx=0.62, rz=-0.42), (1.0, 1.0, 1.0)),
        (*lib["truck_cargo_heap"][0], body_m @ mat_trs(0, 0.80, 0), (1.0, 1.0, 1.0)),
    ]
    for sx, susp_y in ((-0.88, 0.46), (0.88, 0.50)):
        # Steered single front wheels + authentic DUAL rear Canter wheels!
        out.append((*lib["truck_wheel"][0], mat_trs(sx, susp_y, 1.55, ry=0.38, rx=0.55), (1.0, 1.0, 1.0)))
        out.append((*lib["truck_wheel"][0], mat_trs(sx * 0.84, susp_y, -1.25, rx=0.55), (1.0, 1.0, 1.0)))
        out.append((*lib["truck_wheel"][0], mat_trs(sx * 1.03, susp_y, -1.25, rx=0.55), (1.0, 1.0, 1.0)))
    return out


def assemble_harvester(lib, shirt_rgb, hat_key, back_key, tool_key, holding_tbs=False, glasses=False, parang=True):
    hip_m = mat_trs(0, 0.88, 0, rx=(0.04 if holding_tbs else 0.0), ry=0.06)
    head_m = hip_m @ mat_trs(0, 0.58, 0.01, ry=-0.08, rx=-0.02)

    th_l = hip_m @ mat_trs(-0.105, 0.0, 0.0, rx=-0.10, rz=-0.03)
    cf_l = th_l @ mat_trs(0.0, -0.43, 0.0, rx=0.14)
    th_r = hip_m @ mat_trs(0.105, 0.0, 0.0, rx=0.12, rz=0.03)
    cf_r = th_r @ mat_trs(0.0, -0.43, 0.0, rx=0.05)

    if holding_tbs:
        ua_l = hip_m @ mat_trs(-0.215, 0.46, 0.01, rx=-0.72, rz=-0.18)
        fa_l = ua_l @ mat_trs(0.0, -0.27, 0.01, rx=-0.76, ry=0.28)
        ua_r = hip_m @ mat_trs(0.215, 0.46, 0.01, rx=-0.72, rz=0.18)
        fa_r = ua_r @ mat_trs(0.0, -0.27, 0.01, rx=-0.76, ry=-0.28)
    else:
        ua_l = hip_m @ mat_trs(-0.215, 0.46, 0.01, rx=-0.78, rz=-0.26)
        fa_l = ua_l @ mat_trs(0.0, -0.27, 0.01, rx=-0.42, ry=0.26)
        ua_r = hip_m @ mat_trs(0.215, 0.46, 0.01, rx=-0.52, rz=0.22)
        fa_r = ua_r @ mat_trs(0.0, -0.27, 0.01, rx=-0.56, ry=-0.18)

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
    ]
    if back_key:
        out.append((*lib[back_key][0], hip_m @ mat_trs(0, 0.34, -0.14), shirt_rgb))
    if parang:
        out.append((*lib["acc_parang_waist"][0], hip_m @ mat_trs(0.175, 0.10, -0.02), (1.0, 1.0, 1.0)))
    if glasses:
        out.append((*lib["acc_glasses"][0], head_m, (1.0, 1.0, 1.0)))
    if hat_key:
        out.append((*lib[hat_key][0], head_m @ mat_trs(0, 0.21, 0.0), shirt_rgb))
    if holding_tbs:
        out.append((*lib["tbs_bunch"][0], hip_m @ mat_trs(0.0, 0.30, 0.38, rx=0.35, sx=0.88, sy=0.88, sz=0.88), (1.0, 1.0, 1.0)))
    elif tool_key:
        out.append((*lib[tool_key][0], hip_m @ mat_trs(0.03, 0.22, 0.34, rx=0.14, rz=0.08), (1.0, 1.0, 1.0)))
    return out


def assemble_garage_lobby(lib):
    out = [(*lib["garage_showroom"][0], mat_trs(0, 0, 0), (1.0, 1.0, 1.0))]
    for v, i, m, t in assemble_truck(lib):
        out.append((v, i, mat_trs(1.35, 0.08, -0.45, ry=-0.58) @ m, t))
    for v, i, m, t in assemble_harvester(lib, (0.18, 0.56, 0.36), "hat_safety", "back_pack", "tool_tojok", holding_tbs=False, glasses=True, parang=True):
        out.append((v, i, mat_trs(-1.35, 0.08, 1.25, ry=0.35) @ m, t))
    return out


def main() -> None:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    npak_path = os.path.join(root, "src", "Nyawit.Android", "Assets", "Meshes", "nyawit_models.npak")
    atlas_path = os.path.join(root, "src", "Nyawit.Android", "Assets", "Textures", "nyawit_pbr_atlas.png")
    font_path = os.path.join(root, "src", "Nyawit.Android", "Assets", "Fonts", "XyVerseDisplay-Semibold.otf")
    logo_path = os.path.join(root, "src", "Nyawit.Android", "Assets", "Brand", "logo_utama_horizontal_transparan_putih.png")

    atlas = np.array(Image.open(atlas_path).convert("RGBA"), dtype=np.uint8)
    lib = load_npak(npak_path)

    pks_scene = [
        (*lib["pks_factory"][0], mat_trs(0, 0, -2.5), (1, 1, 1)),
        (*lib["pks_fan"][0], mat_trs(-1.5, 7.6, -2.0, ry=0.4), (1, 1, 1)),
        (*lib["weighbridge_ram"][0], mat_trs(0, 0, 7.2), (1, 1, 1)),
    ]
    cards = [
        ("MITSUBISHI CANTER COE BAK KAYU", "KABIN FLAT-NOSE / PLAT BM 8899 XY / BAN DOBEL", assemble_truck(lib), (4.4, 2.35, 4.9), (0.0, 1.15, 0.15)),
        ("GARASI SHOWROOM LOBBY TERPISAH", "BENGKEL SAWIT KHUSUS / 60-120 FPS RINGAN", assemble_garage_lobby(lib), (0.4, 2.35, 8.8), (0.0, 1.55, -0.5)),
        ("SAWIT TENERA PELEPAH ALPHA-CUTOUT", "88 ANAK DAUN PER PELEPAH / PAKIS BATANG", assemble_palm(lib), (8.2, 5.4, 9.2), (0.2, 4.2, 0.2)),
        ("KARAKTER PBR DAN AKSESORIS LENGKAP", "HELM PROYEK / KACAMATA / RANSEL / PARANG / TOJOK", assemble_harvester(lib, (0.20, 0.44, 0.72), "hat_safety", "back_pack", "tool_tojok", False, True, True), (1.75, 1.65, 2.55), (0.0, 1.18, 0.05)),
        ("PEMANEN CAPING BAMBU DAN TBS ASLI", "TEKSTUR TBS GLOSSY / SEPATU BOOT / KERANJANG", assemble_harvester(lib, (0.22, 0.58, 0.34), "hat_caping", "back_basket", "tool_egrek", True, False, True), (1.65, 1.58, 2.35), (0.0, 1.15, 0.10)),
        ("PABRIK PKS DAN TIMBANGAN RAM", "SILO CPO / SENG GELOMBANG / DEK BETON", pks_scene, (19.5, 12.0, 22.0), (1.2, 4.2, 1.2)),
    ]

    W, H = 1800, 1120
    sheet = Image.new("RGBA", (W, H), (11, 13, 15, 255))
    draw = ImageDraw.Draw(sheet)
    f_title = ImageFont.truetype(font_path, 34)
    f_card = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    f_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)

    draw.text((48, 30), "NYAWIT LIVE  -  REALISTIC PBR MODELS AND GARAGE SHOWROOM", font=f_title, fill=(255, 255, 255, 255))
    logo_img = Image.open(logo_path).convert("RGBA")
    lh = 44
    lw = int(logo_img.width * (lh / logo_img.height))
    sheet.alpha_composite(logo_img.resize((lw, lh), Image.Resampling.LANCZOS), (W - lw - 48, 28))

    cw, ch = 552, 476
    for idx_c, (title, sub, scene_inst, eye, tgt) in enumerate(cards):
        col_i, row_i = idx_c % 3, idx_c // 3
        x0, y0 = 42 + col_i * (cw + 30), 104 + row_i * (ch + 30)
        rendered = rasterize_scene(scene_inst, atlas, cw, ch - 68, eye, tgt, fov_deg=40.0).convert("RGBA")
        sheet.alpha_composite(rendered, (x0, y0))
        draw.rectangle([x0, y0 + ch - 68, x0 + cw, y0 + ch], fill=(16, 21, 25, 255))
        draw.rectangle([x0, y0, x0 + cw, y0 + ch], outline=(48, 214, 128, 210), width=2)
        draw.text((x0 + 18, y0 + ch - 54), title, font=f_card, fill=(255, 255, 255, 255))
        draw.text((x0 + 18, y0 + ch - 28), sub, font=f_sub, fill=(74, 222, 128, 255))

    out_path = os.path.join(root, "docs", "screenshots", "models_showcase.png")
    sheet.convert("RGB").save(out_path, optimize=True)
    print(f"Saved PBR textured showcase -> {out_path}")


if __name__ == "__main__":
    main()
