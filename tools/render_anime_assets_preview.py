#!/usr/bin/env python3
"""
High-Resolution Studio 3D Asset & Shader Showcase for NYAWIT LIVE 3D v6.0.0:
Renders 6 close-up hero panels from the actual nyawit_models.npak + nyawit_pbr_atlas.png
with Anime Cel-Shaded Ink Outlines (Inverted-Hull + Normal/Depth Crease Ink) plus
Semi-ENB Dingin & Fog Asap Karhutla atmospheric color grading.
"""
import math
import os
import struct
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def load_npak(path: str):
    with open(path, "rb") as f:
        data = f.read()
    magic, _, count = struct.unpack_from("<4sII", data, 0)
    assert magic == b"NPAK"
    off = 12
    models = {}
    dtype_v = np.dtype([("pos", "<f4", (3,)), ("nrm", "<f4", (3,)), ("uv", "<f4", (2,)), ("col", "u1", (4,))])
    for _ in range(count):
        nlen, _, _, _, _, _, _, _, lods = struct.unpack_from("<BfffffffB", data, off)
        off += 30
        name = data[off:off + nlen].decode("utf-8")
        off += nlen
        lod_list = []
        for _ in range(lods):
            vc, ic = struct.unpack_from("<II", data, off)
            off += 8
            verts = np.frombuffer(data, dtype=dtype_v, count=vc, offset=off).copy()
            off += vc * 36
            idx = np.frombuffer(data, dtype="<u2", count=ic, offset=off).reshape(-1, 3).copy()
            off += ic * 2
            lod_list.append((verts, idx))
        models[name] = lod_list
    return models


def mat_trs(tx=0.0, ty=0.0, tz=0.0, rx=0.0, ry=0.0, rz=0.0, sx=1.0, sy=1.0, sz=1.0) -> np.ndarray:
    cx, s_x = math.cos(rx), math.sin(rx)
    cy, s_y = math.cos(ry), math.sin(ry)
    cz, s_z = math.cos(rz), math.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -s_x], [0, s_x, cx]], np.float32)
    Ry = np.array([[cy, 0, s_y], [0, 1, 0], [-s_y, 0, cy]], np.float32)
    Rz = np.array([[cz, -s_z, 0], [s_z, cz, 0], [0, 0, 1]], np.float32)
    R = Ry @ Rx @ Rz
    M = np.eye(4, dtype=np.float32)
    M[:3, :3] = R @ np.diag([sx, sy, sz]).astype(np.float32)
    M[:3, 3] = [tx, ty, tz]
    return M


def look_at(eye, target, up=(0.0, 1.0, 0.0)) -> np.ndarray:
    e = np.array(eye, np.float32)
    t = np.array(target, np.float32)
    f = t - e
    f /= np.linalg.norm(f)
    s = np.cross(f, np.array(up, np.float32))
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    M = np.eye(4, dtype=np.float32)
    M[0, :3], M[1, :3], M[2, :3] = s, u, -f
    M[0, 3], M[1, 3], M[2, 3] = -np.dot(s, e), -np.dot(u, e), np.dot(f, e)
    return M


def perspective(fov_deg: float, aspect: float, zn: float, zf: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_deg) * 0.5)
    P = np.zeros((4, 4), dtype=np.float32)
    P[0, 0] = f / aspect
    P[1, 1] = f
    P[2, 2] = (zf + zn) / (zn - zf)
    P[2, 3] = (2.0 * zf * zn) / (zn - zf)
    P[3, 2] = -1.0
    return P


def render_anime_scene(instances, atlas_rgba: np.ndarray, w: int, h: int, eye, target, fov=36.0, preset="enb_cold"):
    ss = 2
    rw, rh = w * ss, h * ss
    zb = np.full((rh, rw), 1e9, dtype=np.float32)
    nb = np.zeros((rh, rw, 3), dtype=np.float32)
    hit_mask = np.zeros((rh, rw), dtype=bool)
    fb = np.zeros((rh, rw, 3), dtype=np.float32)

    gy = np.linspace(0.0, 1.0, rh, dtype=np.float32)[:, None]
    if preset == "karhutla":
        # Smoky Sumatra Karhutla Peatland Haze
        sky_top = np.array([108, 76, 52], np.float32)
        sky_hor = np.array([208, 158, 106], np.float32)
        sky_low = np.array([142, 106, 74], np.float32)
        fog_col = np.array([206, 156, 104], np.float32)
        sun_dir = np.array([0.46, 0.62, 0.64], np.float32)
        sun_col = np.array([1.28, 0.80, 0.44], np.float32)
        sky_amb = np.array([0.52, 0.40, 0.30], np.float32)
        rim_col = np.array([1.15, 0.68, 0.34], np.float32)
        ink_rgb = np.array([34, 22, 16], np.float32)
    else:
        # Cool Cinematic Semi-ENB Dingin
        sky_top = np.array([20, 48, 92], np.float32)
        sky_hor = np.array([138, 178, 214], np.float32)
        sky_low = np.array([34, 54, 76], np.float32)
        fog_col = np.array([144, 184, 218], np.float32)
        sun_dir = np.array([0.52, 0.72, 0.46], np.float32)
        sun_col = np.array([1.06, 1.14, 1.25], np.float32)
        sky_amb = np.array([0.36, 0.48, 0.64], np.float32)
        rim_col = np.array([0.52, 0.84, 1.18], np.float32)
        ink_rgb = np.array([10, 16, 28], np.float32)

    sun_dir /= np.linalg.norm(sun_dir)
    upper = gy <= 0.62
    t_up = np.clip(gy / 0.62, 0.0, 1.0) ** 0.78
    t_lo = np.clip((gy - 0.62) / 0.38, 0.0, 1.0)
    fb[:] = np.where(upper[:, :, None],
                     sky_top[None, None, :] * (1.0 - t_up[:, :, None]) + sky_hor[None, None, :] * t_up[:, :, None],
                     sky_hor[None, None, :] * (1.0 - t_lo[:, :, None]) + sky_low[None, None, :] * t_lo[:, :, None])

    V = look_at(eye, target)
    P = perspective(fov, rw / rh, 0.15, 160.0)
    VP = P @ V
    eye_v = np.array(eye, np.float32)
    ah, aw, _ = atlas_rgba.shape

    for verts, idx, M, tint_rgb, allow_outline in instances:
        pos_l = verts["pos"]
        nrm_l = verts["nrm"]
        uv_raw = verts["uv"].copy()
        col_v = verts["col"].astype(np.float32) / 255.0

        dye_mask = uv_raw[:, 0] > 1.5
        if np.any(dye_mask):
            uv_raw[dye_mask, 0] -= 2.0

        ones = np.ones((len(pos_l), 1), np.float32)
        wpos = (M @ np.hstack([pos_l, ones]).T).T[:, :3]
        wnrm = (M[:3, :3] @ nrm_l.T).T
        wnrm /= np.maximum(1e-8, np.linalg.norm(wnrm, axis=1, keepdims=True))

        # Pass 1: Opaque Cel-PBR Surface Rasterization
        clip = (VP @ np.hstack([wpos, ones]).T).T
        w_c = clip[:, 3]
        valid_v = w_c > 0.12
        inv_w = np.where(valid_v, 1.0 / np.maximum(w_c, 1e-5), 0.0)
        sx = (clip[:, 0] * inv_w * 0.5 + 0.5) * (rw - 1)
        sy = (0.5 - clip[:, 1] * inv_w * 0.5) * (rh - 1)

        view_d = eye_v[None, :] - wpos
        dist_v = np.maximum(1e-5, np.linalg.norm(view_d, axis=1, keepdims=True))
        view_d /= dist_v
        ndotl_raw = np.sum(wnrm * sun_dir[None, :], axis=1)
        # 3-Band Anime Cel Ramp!
        cel_band = (
            0.22
            + 0.42 * np.clip((ndotl_raw + 0.05) / 0.10, 0.0, 1.0)
            + 0.36 * np.clip((ndotl_raw - 0.46) / 0.10, 0.0, 1.0)
        )
        half_v = view_d + sun_dir[None, :]
        half_v /= np.maximum(1e-8, np.linalg.norm(half_v, axis=1, keepdims=True))
        gloss = col_v[:, 3]
        emissive = gloss > 0.96
        ndoth = np.maximum(0.0, np.sum(wnrm * half_v, axis=1))
        # Sharp Anime Specular Glint
        spec_step = np.clip(((ndoth ** (8.0 + gloss * 48.0)) - 0.42) / 0.14, 0.0, 1.0) * (0.12 + gloss * 0.52)
        ndotv = np.maximum(0.0, np.sum(wnrm * view_d, axis=1))
        rim = np.clip(((1.0 - ndotv) ** 3.2 - 0.38) / 0.22, 0.0, 1.0) * 0.34

        tint_arr = np.where(dye_mask[:, None], np.array(tint_rgb, np.float32)[None, :], 1.0)
        base_mult = col_v[:, :3] * tint_arr
        lit = sky_amb[None, :] + sun_col[None, :] * cel_band[:, None] + rim_col[None, :] * rim[:, None]
        shade = np.where(emissive[:, None], base_mult * 1.42, base_mult * lit)
        spec_rgb = np.where(emissive[:, None], 0.0, sun_col[None, :] * spec_step[:, None] * 255.0)
        uv_over_w = uv_raw * inv_w[:, None]
        nrm_over_w = wnrm * inv_w[:, None]

        for t0, t1, t2 in idx:
            if not (valid_v[t0] and valid_v[t1] and valid_v[t2]):
                continue
            x0, y0 = sx[t0], sy[t0]
            x1, y1 = sx[t1], sy[t1]
            x2, y2 = sx[t2], sy[t2]
            area = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)
            if abs(area) < 0.25:
                continue
            minx = max(0, int(min(x0, x1, x2)))
            maxx = min(rw - 1, int(math.ceil(max(x0, x1, x2))))
            miny = max(0, int(min(y0, y1, y2)))
            maxy = min(rh - 1, int(math.ceil(max(y0, y1, y2))))
            if minx > maxx or miny > maxy:
                continue

            px = np.arange(minx, maxx + 1, dtype=np.float32)[None, :]
            py = np.arange(miny, maxy + 1, dtype=np.float32)[:, None]
            inv_area = 1.0 / area
            w0 = ((x1 - px) * (y2 - py) - (y1 - py) * (x2 - px)) * inv_area
            w1 = ((x2 - px) * (y0 - py) - (y2 - py) * (x0 - px)) * inv_area
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
            hit_mask[miny:maxy + 1, minx:maxx + 1][vis_mask] = allow_outline

            n_interp = (w0[vis_mask, None] * nrm_over_w[t0] + w1[vis_mask, None] * nrm_over_w[t1] + w2[vis_mask, None] * nrm_over_w[t2]) * z_cam[vis_mask, None]
            n_interp /= np.maximum(1e-6, np.linalg.norm(n_interp, axis=1, keepdims=True))
            if area > 0:
                # Backfacing double-sided quad: flip normal toward camera
                n_interp = -n_interp
            nb[miny:maxy + 1, minx:maxx + 1][vis_mask] = n_interp

            sh_p = (w0[vis_mask, None] * shade[t0] + w1[vis_mask, None] * shade[t1] + w2[vis_mask, None] * shade[t2])
            sp_p = (w0[vis_mask, None] * spec_rgb[t0] + w1[vis_mask, None] * spec_rgb[t1] + w2[vis_mask, None] * spec_rgb[t2])
            lit_rgb = texel[alpha_ok, :3].astype(np.float32) * sh_p + sp_p

            # Atmospheric Fog (Karhutla Smoke or Semi-ENB Cold Mist)
            d_pix = z_cam[vis_mask, None]
            if preset == "karhutla":
                fog_f = np.clip((d_pix - 5.5) / 26.0, 0.0, 0.62)
            else:
                fog_f = np.clip((d_pix - 9.0) / 48.0, 0.0, 0.34)
            lit_rgb = lit_rgb * (1.0 - fog_f) + fog_col[None, :] * fog_f
            fb[miny:maxy + 1, minx:maxx + 1][vis_mask] = np.clip(lit_rgb, 0.0, 255.0)

    # Pass 2: Anime Silhouette + Crease Ink Outline Filter (Depth + Normal Edge Detection!)
    z_clamped = np.where(zb < 1e8, zb, 80.0)
    dz_x = np.abs(z_clamped[1:-1, 2:] - z_clamped[1:-1, :-2]) / np.maximum(0.6, z_clamped[1:-1, 1:-1])
    dz_y = np.abs(z_clamped[2:, 1:-1] - z_clamped[:-2, 1:-1]) / np.maximum(0.6, z_clamped[1:-1, 1:-1])
    depth_edge = np.clip((np.hypot(dz_x, dz_y) - 0.055) / 0.055, 0.0, 1.0)

    dn_x = np.linalg.norm(nb[1:-1, 2:] - nb[1:-1, :-2], axis=2)
    dn_y = np.linalg.norm(nb[2:, 1:-1] - nb[:-2, 1:-1], axis=2)
    nrm_edge = np.clip((np.hypot(dn_x, dn_y) - 0.62) / 0.45, 0.0, 0.82)

    near_outline = (
        hit_mask[1:-1, 1:-1]
        | hit_mask[:-2, 1:-1] | hit_mask[2:, 1:-1]
        | hit_mask[1:-1, :-2] | hit_mask[1:-1, 2:]
    )
    ink_strength = np.where(near_outline, np.maximum(depth_edge, nrm_edge), 0.0)
    # Dilate silhouette slightly for bold 2px anime contour
    sil = np.where(near_outline, depth_edge, 0.0)
    sil_dil = np.maximum.reduce([
        sil,
        np.pad(sil[1:, :], ((0, 1), (0, 0))),
        np.pad(sil[:-1, :], ((1, 0), (0, 0))),
        np.pad(sil[:, 1:], ((0, 0), (0, 1))),
        np.pad(sil[:, :-1], ((0, 0), (1, 0))),
    ])
    ink_total = np.clip(np.maximum(ink_strength, sil_dil * 0.94), 0.0, 0.96)
    fb_inner = fb[1:-1, 1:-1]
    fb[1:-1, 1:-1] = fb_inner * (1.0 - ink_total[:, :, None]) + ink_rgb[None, None, :] * ink_total[:, :, None]

    # Semi-ENB Cinematic S-Curve Contrast & Color Grade
    norm_fb = np.clip(fb / 255.0, 0.0, 1.0)
    scurve = norm_fb * norm_fb * (3.0 - 2.0 * norm_fb)
    graded = norm_fb * 0.35 + scurve * 0.65
    if preset == "enb_cold":
        luma = graded[:, :, 0:1] * 0.299 + graded[:, :, 1:2] * 0.587 + graded[:, :, 2:3] * 0.114
        graded[:, :, 0] *= 0.96
        graded[:, :, 2] = np.clip(graded[:, :, 2] * 1.06 + (1.0 - luma[:, :, 0]) * 0.03, 0.0, 1.0)
    else:
        graded[:, :, 0] = np.clip(graded[:, :, 0] * 1.05, 0.0, 1.0)
        graded[:, :, 2] *= 0.92
    fb_final = np.clip(graded * 255.0, 0.0, 255.0).astype(np.uint8)
    return Image.fromarray(fb_final).resize((w, h), Image.Resampling.LANCZOS)


def ground_disc(lib, scale=9.0):
    # Subtle concrete/earth turntable pad under studio showcase assets
    return (*lib["garage_showroom"][1], mat_trs(0, -0.02, 0, sx=scale / 14.0, sy=0.05, sz=scale / 14.0), (0.85, 0.88, 0.92), False)


def assemble_canter_hero(lib):
    body_m = mat_trs(0, 0.02, 0, rz=-0.02, rx=-0.008)
    out = [
        (*lib["canter_truck_body"][0], body_m, (1.0, 1.0, 1.0), True),
        (*lib["canter_steering_wheel"][0], body_m @ mat_trs(0.42, 1.46, 1.88, rx=0.62, rz=-0.42), (1.0, 1.0, 1.0), True),
        (*lib["truck_cargo_heap"][0], body_m @ mat_trs(0, 0.80, 0), (1.0, 1.0, 1.0), True),
        (*lib["canter_axle_suspension"][0], mat_trs(0.0, 0.48, 1.55), (1.0, 1.0, 1.0), True),
        (*lib["canter_axle_suspension"][0], mat_trs(0.0, 0.48, -1.25), (1.0, 1.0, 1.0), True),
        (*lib["canter_driveshaft"][0], mat_trs(0.0, 0.50, -1.25, sz=2.4), (1.0, 1.0, 1.0), True),
    ]
    for sx, susp_y in ((-0.88, 0.48), (0.88, 0.48)):
        out.append((*lib["truck_wheel"][0], mat_trs(sx, susp_y, 1.55, ry=0.32, rx=0.45), (1.0, 1.0, 1.0), True))
        out.append((*lib["truck_wheel"][0], mat_trs(sx * 0.84, susp_y, -1.25, rx=0.45), (1.0, 1.0, 1.0), True))
        out.append((*lib["truck_wheel"][0], mat_trs(sx * 1.03, susp_y, -1.25, rx=0.45), (1.0, 1.0, 1.0), True))
    return out


def assemble_harvester_hero(lib):
    shirt_rgb = (0.14, 0.56, 0.36)
    hip_m = mat_trs(-0.42, 0.88, 0.15, ry=0.22)
    head_m = hip_m @ mat_trs(0, 0.58, 0.01, ry=-0.12)
    th_l = hip_m @ mat_trs(-0.105, 0.0, 0.0, rx=-0.12, rz=-0.03)
    cf_l = th_l @ mat_trs(0.0, -0.43, 0.0, rx=0.14)
    th_r = hip_m @ mat_trs(0.105, 0.0, 0.0, rx=0.14, rz=0.03)
    cf_r = th_r @ mat_trs(0.0, -0.43, 0.0, rx=0.04)
    ua_l = hip_m @ mat_trs(-0.215, 0.46, 0.01, rx=-0.76, rz=-0.24)
    fa_l = ua_l @ mat_trs(0.0, -0.27, 0.01, rx=-0.42, ry=0.26)
    ua_r = hip_m @ mat_trs(0.215, 0.46, 0.01, rx=-0.52, rz=0.22)
    fa_r = ua_r @ mat_trs(0.0, -0.27, 0.01, rx=-0.56, ry=-0.18)

    out = [
        (*lib["char_torso_head"][0], hip_m, shirt_rgb, True),
        (*lib["char_head"][0], head_m, (1.0, 1.0, 1.0), True),
        (*lib["char_face_neutral"][0], head_m, (1.0, 1.0, 1.0), False),
        (*lib["char_leg"][0], th_l, (1.0, 1.0, 1.0), True),
        (*lib["char_calf_boot"][0], cf_l, (1.0, 1.0, 1.0), True),
        (*lib["char_leg"][0], th_r, (1.0, 1.0, 1.0), True),
        (*lib["char_calf_boot"][0], cf_r, (1.0, 1.0, 1.0), True),
        (*lib["char_arm"][0], ua_l, shirt_rgb, True),
        (*lib["char_forearm_hand"][0], fa_l, (1.0, 1.0, 1.0), True),
        (*lib["char_arm"][0], ua_r, shirt_rgb, True),
        (*lib["char_forearm_hand"][0], fa_r, (1.0, 1.0, 1.0), True),
        (*lib["hat_caping"][0], head_m @ mat_trs(0, 0.21, 0.0), shirt_rgb, True),
        (*lib["acc_glasses"][0], head_m, (1.0, 1.0, 1.0), True),
        (*lib["acc_parang_waist"][0], hip_m @ mat_trs(0.175, 0.10, -0.02), (1.0, 1.0, 1.0), True),
        (*lib["back_basket"][0], hip_m @ mat_trs(0, 0.34, -0.14), shirt_rgb, True),
        # Angled Egrek Naga so the golden dragon horns, emerald gem & sickle blade sit cleanly inside camera frame!
        (*lib["tool_egrek_dragon"][0], mat_trs(-0.62, 0.28, 0.42, rx=0.38, rz=-0.52, sx=0.46, sy=0.46, sz=0.46), (1.0, 1.0, 1.0), True),
        # Close-up hero TBS bunch + Angkong + Sultan Chest right beside harvester!
        (*lib["angkong_cart"][0], mat_trs(0.82, 0.0, 0.10, ry=-0.48), (1.0, 1.0, 1.0), True),
        (*lib["truck_wheel"][0], mat_trs(0.82 + math.sin(-0.48) * 0.80, 0.29, 0.10 + math.cos(-0.48) * 0.80, ry=-0.48, sx=0.60, sy=0.60, sz=0.60), (1.0, 1.0, 1.0), True),
        (*lib["tbs_bunch"][0], mat_trs(0.18, 0.26, 0.92, rx=0.25, ry=0.6, sx=1.25, sy=1.25, sz=1.25), (1.0, 1.0, 1.0), True),
        (*lib["item_cuan_crate"][0], mat_trs(-0.95, 0.0, 0.72, ry=0.45), (1.0, 1.0, 1.0), True),
    ]
    return out


def assemble_spbu_hero(lib):
    return [
        (*lib["spbu_solar"][0], mat_trs(0, 0, 0), (1.0, 1.0, 1.0), True),
        (*lib["item_solar_can"][0], mat_trs(1.85, 0.16, 1.25, ry=0.4, sx=1.35, sy=1.35, sz=1.35), (1.0, 1.0, 1.0), True),
    ]


def assemble_warung_hero(lib):
    return [
        (*lib["warung_kopi"][0], mat_trs(0, 0, 0), (1.0, 1.0, 1.0), True),
        (*lib["item_coffee_cup"][0], mat_trs(0.45, 0.56, 1.02, sx=0.85, sy=0.85, sz=0.85), (1.0, 1.0, 1.0), True),
    ]


def assemble_pks_gudang_hero(lib):
    return [
        (*lib["pks_factory"][0], mat_trs(-2.2, 0, -3.5, ry=0.18), (1.0, 1.0, 1.0), True),
        (*lib["weighbridge_ram"][0], mat_trs(-1.2, 0, 5.8, ry=0.18), (1.0, 1.0, 1.0), True),
        (*lib["gudang_pupuk"][0], mat_trs(7.6, 0, 2.2, ry=-0.32), (1.0, 1.0, 1.0), True),
    ]


def assemble_karhutla_arch_hero(lib):
    boar_m = mat_trs(-1.25, 0.02, 2.35, ry=0.48)
    out = [
        (*lib["offroad_arch"][0], mat_trs(0, 0, 0), (1.0, 1.0, 1.0), True),
        (*lib["palm_trunk"][0], mat_trs(-4.6, 0, -1.8), (1.0, 1.0, 1.0), True),
        (*lib["palm_crown"][0], mat_trs(-4.32, 6.32, -1.60), (1.0, 1.0, 1.0), False),
        (*lib["palm_trunk"][0], mat_trs(4.6, 0, -2.2, ry=1.4), (1.0, 1.0, 1.0), True),
        (*lib["palm_crown"][0], mat_trs(4.88, 6.32, -2.00, ry=1.4), (1.0, 1.0, 1.0), False),
        (*lib["celeng_boar"][0], boar_m, (1.0, 1.0, 1.0), True),
        (*lib["item_npk_sack"][0], mat_trs(1.65, 0.0, 2.1, ry=-0.4, sx=1.2, sy=1.2, sz=1.2), (1.0, 1.0, 1.0), True),
    ]
    for lx, lz in ((-0.16, 0.26), (0.16, 0.26), (-0.15, -0.34), (0.15, -0.34)):
        out.append((*lib["boar_leg"][0], boar_m @ mat_trs(lx, 0.46, lz), (1.0, 1.0, 1.0), True))
    for v, i, m, t, ao in assemble_canter_hero(lib):
        out.append((v, i, mat_trs(0.55, 0.0, -2.4, ry=0.14) @ m, t, ao))
    return out


def main() -> None:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    npak_path = os.path.join(root, "src", "Nyawit.Android", "Assets", "Meshes", "nyawit_models.npak")
    atlas_path = os.path.join(root, "src", "Nyawit.Android", "Assets", "Textures", "nyawit_pbr_atlas.png")
    font_path = os.path.join(root, "src", "Nyawit.Android", "Assets", "Fonts", "XyVerseDisplay-Semibold.otf")
    logo_path = os.path.join(root, "src", "Nyawit.Android", "Assets", "Brand", "logo_utama_horizontal_transparan_putih.png")

    atlas = np.array(Image.open(atlas_path).convert("RGBA"), dtype=np.uint8)
    lib = load_npak(npak_path)

    cards = [
        ("CANTER FE 74 HD MODIF SUMATERA",
         "TOPI KABIN / 4 KLAKSON BASURI / WIPER / BAK KAYU MERANTI - MODE ENB DINGIN",
         assemble_canter_hero(lib), (4.15, 2.25, 4.55), (0.0, 1.22, 0.05), 35.0, "enb_cold"),
        ("PEMANEN / EGREK NAGA / ANGKONG TBS",
         "TANDAN BERDURI / EGREK NAGA BERTANDUK / ANGKONG BAJA - MODE ENB DINGIN",
         assemble_harvester_hero(lib), (2.55, 1.95, 3.65), (-0.02, 1.15, 0.28), 36.0, "enb_cold"),
        ("SPBU BIOSOLAR B35 / BENGKEL TRUK",
         "TANGKI 5000L / BOLLARD / SELANG DISPENSER DIGITAL / RAM SERVIS - MODE ENB DINGIN",
         assemble_spbu_hero(lib), (6.8, 3.6, 8.2), (0.0, 2.05, -0.35), 37.0, "enb_cold"),
        ("WARUNG KOPI / ISTIRAHAT PEMANEN",
         "ETALASE GORENGAN / CERET KUNINGAN / TERMOS / LAMPU GANTUNG - MODE ENB DINGIN",
         assemble_warung_hero(lib), (4.6, 2.65, 5.8), (0.0, 1.45, -0.25), 36.0, "enb_cold"),
        ("PABRIK PKS / RAM DIGITAL / GUDANG NPK",
         "SILO CPO KONVEYOR / CEROBONG BELANG / GUDANG PINTU GESER - MODE ENB DINGIN",
         assemble_pks_gudang_hero(lib), (13.5, 8.5, 19.5), (1.2, 3.6, 0.2), 38.0, "enb_cold"),
        ("FOG ASAP KARHUTLA / GAPURA / CELENG",
         "KABUT ASAP GAMBUT SUMATERA / GAPURA A-FRAME / CELENG BERTARING - MODE KARHUTLA",
         assemble_karhutla_arch_hero(lib), (4.8, 2.8, 8.8), (0.0, 1.95, 0.0), 38.0, "karhutla"),
    ]

    sheet = Image.new("RGB", (2400, 1480), (10, 18, 30))
    draw = ImageDraw.Draw(sheet)
    f_title = ImageFont.truetype(font_path, 38)
    f_sub = ImageFont.truetype(font_path, 19)
    f_card = ImageFont.truetype(font_path, 22)
    f_desc = ImageFont.truetype(font_path, 14)

    draw.rectangle([0, 0, 2400, 96], fill=(14, 26, 44))
    draw.line([(0, 96), (2400, 96)], fill=(64, 196, 245), width=3)
    if os.path.exists(logo_path):
        lg = Image.open(logo_path).convert("RGBA")
        lh = 56
        lw = int(lg.width * (lh / lg.height))
        lg = lg.resize((lw, lh), Image.Resampling.LANCZOS)
        sheet.paste(lg, (34, 20), lg)
    draw.text((295, 18), "NYAWIT LIVE 3D V6.0.0 - HIGH-DETAIL 3D ASSETS / ANIME ENB SHOWCASE", font=f_title, fill=(242, 248, 255))
    draw.text((297, 62), "57 MODEL NPAK V4.0 : 60.5K LOD0 TRIS / GAYA ANIME INK OUTLINE / PRESET SEMI-ENB DINGIN / FOG ASAP KARHUTLA", font=f_sub, fill=(108, 214, 252))

    cw, ch = 764, 646
    for idx_c, (title, sub, inst, eye, tgt, fov, preset) in enumerate(cards):
        col = idx_c % 3
        row = idx_c // 3
        x0 = 26 + col * (cw + 28)
        y0 = 118 + row * (ch + 28)
        print(f"Rendering [{idx_c + 1}/6] {title} ({preset})...")
        card_img = render_anime_scene(inst, atlas, cw, ch - 70, eye, tgt, fov=fov, preset=preset)
        border_col = (242, 168, 68) if preset == "karhutla" else (72, 194, 246)
        hdr_bg = (34, 24, 18) if preset == "karhutla" else (15, 28, 46)
        draw.rounded_rectangle([x0 - 2, y0 - 2, x0 + cw + 2, y0 + ch + 2], radius=12, fill=hdr_bg, outline=border_col, width=2)
        sheet.paste(card_img, (x0, y0))
        draw.rectangle([x0, y0 + ch - 70, x0 + cw, y0 + ch], fill=hdr_bg)
        draw.line([(x0, y0 + ch - 70), (x0 + cw, y0 + ch - 70)], fill=border_col, width=2)
        draw.text((x0 + 16, y0 + ch - 60), title, font=f_card, fill=(255, 224, 102) if preset == "karhutla" else (238, 248, 255))
        draw.text((x0 + 16, y0 + ch - 30), sub, font=f_desc, fill=(238, 186, 134) if preset == "karhutla" else (142, 206, 242))

    out_path = os.path.join(root, "docs", "screenshots", "v6_anime_assets_showcase.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    sheet.save(out_path, optimize=True)
    print(f"Saved showcase -> {out_path}")


if __name__ == "__main__":
    main()
