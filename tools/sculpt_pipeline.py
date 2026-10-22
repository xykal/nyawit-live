#!/usr/bin/env python3
"""
Nyawit Live 3D — Parametric Multi-Resolution 3D Asset & AO Pipeline (tools/sculpt_pipeline.py)

Generates 29 complex, non-primitive 3D models with TRUE multi-resolution parametric LODs:
  - Zero coplanar Z-fighting (all trim/windows/hubs offset cleanly outside base surfaces for mobile 24-bit depth buffers!)
  - UV.x material channel convention:
      uv.x >= 0.75 -> Outfit / primary customizable dye zone (multiplied by dynamic player outfit/truck tint on GPU!)
      uv.x <  0.50 -> Fixed material albedo (skin, hair, chrome, glass, gold, rubber boots, bark, foliage — NEVER muddied by outfit tint!)
  - Binary output (.npak v1): 36-byte GPU-native interleaved vertex stream [pos:3xf32, nrm:3xf32, uv:2xf32, rgba_ao:4xu8] + uint16 indices.
"""

from __future__ import annotations
import json
import math
import os
import struct
from dataclasses import dataclass
from typing import Callable, List, Tuple
import numpy as np


@dataclass
class MeshPart:
    pos: np.ndarray
    uv: np.ndarray
    col: np.ndarray
    idx: np.ndarray
    nrm: np.ndarray | None = None


def rot_x(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float32)


def rot_y(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float32)


def rot_z(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float32)


def xform(part: MeshPart, scale=(1.0, 1.0, 1.0), rx=0.0, ry=0.0, rz=0.0, translate=(0.0, 0.0, 0.0)) -> MeshPart:
    p = part.pos.astype(np.float32) * np.asarray(scale, dtype=np.float32)
    m = rot_y(ry) @ rot_x(rx) @ rot_z(rz)
    p = (p @ m.T) + np.asarray(translate, dtype=np.float32)
    return MeshPart(p, part.uv.copy(), part.col.copy(), part.idx.copy())


def tag_dyeable(part: MeshPart, dyeable: bool = True) -> MeshPart:
    uv = part.uv.copy()
    uv[:, 0] = 0.88 if dyeable else 0.18
    return MeshPart(part.pos, uv, part.col, part.idx)


def merge_parts(parts: List[MeshPart]) -> MeshPart:
    pos_list, uv_list, col_list, idx_list = [], [], [], []
    offset = 0
    for pt in parts:
        if len(pt.pos) == 0 or len(pt.idx) == 0:
            continue
        pos_list.append(pt.pos.astype(np.float32))
        uv_list.append(pt.uv.astype(np.float32))
        col_list.append(pt.col.astype(np.uint8))
        idx_list.append(pt.idx.astype(np.int32) + offset)
        offset += len(pt.pos)
    return MeshPart(np.vstack(pos_list), np.vstack(uv_list), np.vstack(col_list), np.vstack(idx_list))


def rgba(r: int, g: int, b: int, ao: int = 255) -> np.ndarray:
    return np.array([int(np.clip(r, 0, 255)), int(np.clip(g, 0, 255)), int(np.clip(b, 0, 255)), int(np.clip(ao, 0, 255))], dtype=np.uint8)


def loft_profile(
    stations: List[Tuple[np.ndarray, np.ndarray, float]],
    cap_start: bool = True,
    cap_end: bool = True,
    u_fixed: float = 0.18,
) -> MeshPart:
    rings = len(stations)
    seg = len(stations[0][0])
    pos, uv, col = [], [], []
    for pts, c, v_val in stations:
        c_arr = np.broadcast_to(np.asarray(c, dtype=np.uint8), (seg, 4)).copy()
        u_vals = np.full(seg, u_fixed, dtype=np.float32)
        v_vals = np.full(seg, v_val, dtype=np.float32)
        pos.append(pts.astype(np.float32))
        uv.append(np.stack([u_vals, v_vals], axis=1))
        col.append(c_arr)

    pos_a = np.vstack(pos)
    uv_a = np.vstack(uv)
    col_a = np.vstack(col)
    tris = []
    for si in range(rings - 1):
        b0 = si * seg
        b1 = (si + 1) * seg
        for j in range(seg):
            jn = (j + 1) % seg
            tris.append([b0 + j, b1 + j, b1 + jn])
            tris.append([b0 + j, b1 + jn, b0 + jn])

    extra_pos, extra_uv, extra_col = [pos_a], [uv_a], [col_a]
    next_idx = len(pos_a)

    if cap_start:
        c_pt = stations[0][0].mean(axis=0, keepdims=True).astype(np.float32)
        c_col = np.mean(stations[0][1].reshape(-1, 4), axis=0, keepdims=True).astype(np.uint8)
        extra_pos.append(c_pt)
        extra_uv.append(np.array([[u_fixed, 0.0]], dtype=np.float32))
        extra_col.append(c_col)
        ci = next_idx
        next_idx += 1
        for j in range(seg):
            jn = (j + 1) % seg
            tris.append([ci, j, jn])

    if cap_end:
        base = (rings - 1) * seg
        c_pt = stations[-1][0].mean(axis=0, keepdims=True).astype(np.float32)
        c_col = np.mean(stations[-1][1].reshape(-1, 4), axis=0, keepdims=True).astype(np.uint8)
        extra_pos.append(c_pt)
        extra_uv.append(np.array([[u_fixed, 1.0]], dtype=np.float32))
        extra_col.append(c_col)
        ci = next_idx
        for j in range(seg):
            jn = (j + 1) % seg
            tris.append([ci, base + jn, base + j])

    part = MeshPart(np.vstack(extra_pos), np.vstack(extra_uv), np.vstack(extra_col), np.asarray(tris, dtype=np.int32))
    # Per-triangle outward CCW enforcement relative to station spine centers -> 100% GL_CCW hardware backface-cull safe!
    spine_centers = np.vstack([st[0].mean(axis=0, keepdims=True) for st in stations])
    vert_spine = np.repeat(spine_centers, seg, axis=0)
    if cap_start or cap_end:
        extra_sp = []
        if cap_start:
            extra_sp.append(stations[0][0].mean(axis=0, keepdims=True) + (stations[0][0].mean(axis=0) - stations[-1][0].mean(axis=0)) * 0.05)
        if cap_end:
            extra_sp.append(stations[-1][0].mean(axis=0, keepdims=True) + (stations[-1][0].mean(axis=0) - stations[0][0].mean(axis=0)) * 0.05)
        vert_spine = np.vstack([vert_spine] + extra_sp)
    v0, v1, v2 = part.pos[part.idx[:, 0]], part.pos[part.idx[:, 1]], part.pos[part.idx[:, 2]]
    in0, in1, in2 = vert_spine[part.idx[:, 0]], vert_spine[part.idx[:, 1]], vert_spine[part.idx[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)
    outward = (v0 + v1 + v2) / 3.0 - (in0 + in1 + in2) / 3.0
    flip = np.sum(fn * outward, axis=1) < 0.0
    if np.any(flip):
        part.idx[flip] = part.idx[flip][:, [0, 2, 1]]
    return part


def chamfer_box(
    size: Tuple[float, float, float],
    chamfer: float,
    col: np.ndarray,
    taper_top: Tuple[float, float] = (1.0, 1.0),
    shear_z_top: float = 0.0,
    arch_top: float = 0.0,
    dyeable: bool = False,
) -> MeshPart:
    """
    True 8-corner chamfered hard-surface architectural / automotive panel!
    Flat crisp walls + clean 45-degree bevelled corners -> ZERO wavy octagon look AND ZERO coplanar Z-fighting!
    """
    sx, sy, sz = size[0] * 0.5, size[1] * 0.5, size[2] * 0.5
    ch = min(chamfer, sx * 0.42, sz * 0.42)
    ch_y = min(chamfer * 0.85, sy * 0.42)
    # 8-vertex CCW chamfered rectangle in XZ plane
    base_xz = np.array([
        [sx - ch, -sz],
        [sx, -sz + ch],
        [sx, sz - ch],
        [sx - ch, sz],
        [-sx + ch, sz],
        [-sx, sz - ch],
        [-sx, -sz + ch],
        [-sx + ch, -sz],
    ], dtype=np.float32)

    levels = [
        (-sy, 0.90, 0.0, 0.80),
        (-sy + ch_y, 1.0, 0.0, 0.94),
        (sy - ch_y, 1.0, shear_z_top * 0.88, 1.0),
        (sy, 0.90, shear_z_top, 1.0),
    ]
    stations = []
    for li, (yy, ins, shz, ao_k) in enumerate(levels):
        t = li / 3.0
        tx = 1.0 + (taper_top[0] - 1.0) * t
        tz = 1.0 + (taper_top[1] - 1.0) * t
        xs = base_xz[:, 0] * ins * tx
        zs = base_xz[:, 1] * ins * tz + shz
        ys = np.full_like(xs, yy) + (arch_top * np.clip(1.0 - (xs / max(sx, 1e-4)) ** 2, 0.0, 1.0) if li >= 2 else 0.0)
        c = col.copy()
        c[3] = int(min(255, c[3] * ao_k))
        stations.append((np.stack([xs, ys, zs], axis=1), c, t))
    return loft_profile(stations, cap_start=True, cap_end=True, u_fixed=0.88 if dyeable else 0.18)


def tube_along_curve(
    pts: np.ndarray,
    radii: np.ndarray,
    seg: int,
    color_fn: Callable[[float, np.ndarray], np.ndarray],
    profile_mod: Callable[[float, np.ndarray], np.ndarray] | None = None,
    cap_ends: bool = True,
    dyeable: bool = False,
) -> MeshPart:
    n = len(pts)
    tangents = np.zeros_like(pts, dtype=np.float32)
    tangents[0] = pts[1] - pts[0]
    tangents[-1] = pts[-1] - pts[-2]
    if n > 2:
        tangents[1:-1] = pts[2:] - pts[:-2]
    tangents /= np.maximum(np.linalg.norm(tangents, axis=1, keepdims=True), 1e-6)

    up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    if abs(float(np.dot(tangents[0], up))) > 0.92:
        up = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    normal = np.cross(up, tangents[0])
    normal /= max(np.linalg.norm(normal), 1e-6)

    thetas = np.linspace(0.0, 2.0 * math.pi, seg, endpoint=False, dtype=np.float32)
    stations = []
    for i in range(n):
        t = i / max(1, n - 1)
        if i > 0:
            axis = np.cross(tangents[i - 1], tangents[i])
            s_len = np.linalg.norm(axis)
            if s_len > 1e-6:
                axis /= s_len
                ang = math.asin(min(1.0, float(s_len)))
                c, s = math.cos(ang), math.sin(ang)
                normal = normal * c + np.cross(axis, normal) * s + axis * np.dot(axis, normal) * (1.0 - c)
                normal /= max(np.linalg.norm(normal), 1e-6)
        binorm = np.cross(tangents[i], normal)
        r = radii[i] * (profile_mod(t, thetas) if profile_mod else np.ones_like(thetas))
        ring = pts[i][None, :] + (np.cos(thetas) * r)[:, None] * normal[None, :] + (np.sin(thetas) * r)[:, None] * binorm[None, :]
        stations.append((ring, color_fn(t, thetas), t))
    return loft_profile(stations, cap_start=cap_ends, cap_end=cap_ends, u_fixed=0.88 if dyeable else 0.18)


def organic_ellipsoid(
    rx: float, ry: float, rz: float,
    rings: int, seg: int,
    col_fn: Callable[[float, np.ndarray], np.ndarray],
    disp_fn: Callable[[np.ndarray, np.ndarray], np.ndarray] | None = None,
    phi_range: Tuple[float, float] = (-math.pi * 0.485, math.pi * 0.485),
    dyeable: bool = False,
) -> MeshPart:
    phis = np.linspace(phi_range[0], phi_range[1], rings, dtype=np.float32)
    thetas = np.linspace(0.0, 2.0 * math.pi, seg, endpoint=False, dtype=np.float32)
    stations = []
    for i, phi in enumerate(phis):
        t = i / max(1, rings - 1)
        cp, sp = math.cos(phi), math.sin(phi)
        rad_k = disp_fn(np.full_like(thetas, phi), thetas) if disp_fn else np.ones_like(thetas)
        ring = np.stack([np.cos(thetas) * cp * rx * rad_k, np.full_like(thetas, sp * ry) * rad_k, np.sin(thetas) * cp * rz * rad_k], axis=1)
        stations.append((ring, col_fn(t, thetas), t))
    return loft_profile(stations, cap_start=True, cap_end=True, u_fixed=0.88 if dyeable else 0.18)


def finalize_normals_and_ao(part: MeshPart, ao_strength: float = 0.46) -> Tuple[np.ndarray, MeshPart]:
    pos = part.pos.astype(np.float32)
    idx = part.idx.astype(np.int32)
    v0, v1, v2 = pos[idx[:, 0]], pos[idx[:, 1]], pos[idx[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)
    fl = np.linalg.norm(fn, axis=1, keepdims=True)
    fn = np.where(fl > 1e-9, fn / np.maximum(fl, 1e-9), np.array([0.0, 1.0, 0.0], dtype=np.float32))

    vn = np.zeros_like(pos, dtype=np.float32)
    np.add.at(vn, idx[:, 0], fn)
    np.add.at(vn, idx[:, 1], fn)
    np.add.at(vn, idx[:, 2], fn)
    vl = np.linalg.norm(vn, axis=1, keepdims=True)
    nrm = np.where(vl > 1e-8, vn / np.maximum(vl, 1e-8), np.array([0.0, 1.0, 0.0], dtype=np.float32))

    cos_thresh = math.cos(math.radians(48.0))
    dots = np.sum(nrm[idx] * fn[:, None, :], axis=2)
    sharp_mask = np.any(dots < cos_thresh, axis=1)
    if np.any(sharp_mask):
        smooth_idx = idx[~sharp_mask]
        st = idx[sharp_mask]
        sf = fn[sharp_mask]
        s_pos = pos[st].reshape(-1, 3)
        s_uv = part.uv[st].reshape(-1, 2)
        s_col = part.col[st].reshape(-1, 4)
        s_nrm = np.repeat(sf, 3, axis=0)
        base = len(pos)
        s_idx = np.arange(base, base + len(s_pos), dtype=np.int32).reshape(-1, 3)
        pos = np.vstack([pos, s_pos])
        uv = np.vstack([part.uv, s_uv])
        col = np.vstack([part.col, s_col])
        nrm = np.vstack([nrm, s_nrm])
        idx = np.vstack([smooth_idx, s_idx])
    else:
        uv = part.uv
        col = part.col.copy()

    occ = np.zeros(len(pos), dtype=np.float32)
    golden = math.pi * (3.0 - math.sqrt(5.0))
    RES = 26
    for i in range(12):
        y = 0.24 + 0.76 * (i + 0.5) / 12.0
        r = math.sqrt(max(0.0, 1.0 - y * y))
        th = golden * i
        d = np.array([math.cos(th) * r, y, math.sin(th) * r], dtype=np.float32)
        up_ref = np.array([0.0, 0.0, 1.0], dtype=np.float32) if abs(d[2]) < 0.9 else np.array([1.0, 0.0, 0.0], dtype=np.float32)
        u_ax = np.cross(up_ref, d)
        u_ax /= np.linalg.norm(u_ax)
        v_ax = np.cross(d, u_ax)
        pu, pv, pw = pos @ u_ax, pos @ v_ax, pos @ d
        su = max(float(pu.max() - pu.min()), 1e-4)
        sv = max(float(pv.max() - pv.min()), 1e-4)
        iu = np.clip(((pu - float(pu.min())) / su * (RES - 1)).astype(np.int32), 0, RES - 1)
        iv = np.clip(((pv - float(pv.min())) / sv * (RES - 1)).astype(np.int32), 0, RES - 1)
        max_w = np.full((RES, RES), -1e9, dtype=np.float32)
        np.maximum.at(max_w, (iu, iv), pw)
        depth = max_w[iu, iv] - pw
        facing = np.clip(nrm @ d, 0.0, 1.0)
        span = max(float(pw.max() - pw.min()), 1e-3)
        occ += np.where((depth > span * 0.055) & (facing > 0.05), np.minimum(1.0, depth / (span * 0.35)) * facing, 0.0)

    ao_geom = 1.0 - ao_strength * np.clip(occ / 6.8, 0.0, 0.68)
    col_out = col.copy()
    col_out[:, 3] = np.clip(col_out[:, 3].astype(np.float32) * ao_geom, 78.0, 255.0).astype(np.uint8)
    return nrm.astype(np.float32), MeshPart(pos, uv, col_out, idx, nrm.astype(np.float32))


# ==============================================================================
#  29 CRISP ZERO-Z-FIGHTING PARAMETRIC MODELS
# ==============================================================================

def build_palm_trunk(lod: int) -> MeshPart:
    parts = []
    n = [32, 16, 8][lod]
    seg = [16, 10, 6][lod]
    ts = np.linspace(0.0, 1.0, n, dtype=np.float32)
    pts = np.stack([0.22 * np.sin(ts * 2.3) + 0.08 * ts * ts, ts * 6.4, 0.15 * (1.0 - np.cos(ts * 1.9))], axis=1)
    radii = 0.56 * ((1.0 - ts) ** 2.4) * 0.45 + 0.34 - 0.10 * ts

    def mod(t: float, th: np.ndarray) -> np.ndarray:
        diamond = np.maximum(0.0, np.sin(8.0 * th + t * 46.0) * np.sin(5.0 * th - t * 31.0))
        buttress = (1.0 - min(1.0, t / 0.16)) * 0.22 * (0.5 + 0.5 * np.cos(7.0 * th + 0.4))
        return 1.0 + 0.14 * diamond * (0.35 + 0.65 * t) + buttress

    def col_fn(t: float, th: np.ndarray) -> np.ndarray:
        scar = np.clip(np.sin(8.0 * th + t * 46.0) * np.sin(5.0 * th - t * 31.0), 0.0, 1.0)
        moss = np.clip(1.0 - t * 2.8, 0.0, 1.0) * 0.45
        return np.stack([94 + 48 * scar - 22 * moss, 74 + 40 * scar + 24 * moss, 52 + 24 * scar - 8 * moss, 180 + 72 * scar], axis=1).astype(np.uint8)

    parts.append(tube_along_curve(pts, radii, seg=seg, color_fn=col_fn, profile_mod=mod))
    stub_count = [24, 8, 0][lod]
    for i in range(stub_count):
        t = 0.30 + 0.68 * (i / max(1, stub_count))
        ang = i * 2.39996
        cx, cy, cz = 0.22 * math.sin(t * 2.3) + 0.08 * t * t, t * 6.4, 0.15 * (1.0 - math.cos(t * 1.9))
        base_r = 0.34 - 0.09 * t
        stub = tube_along_curve(
            np.array([[0.0, 0.0, 0.0], [0.0, 0.07, 0.16], [0.0, 0.15, 0.30]], dtype=np.float32),
            np.array([0.13, 0.10, 0.05], dtype=np.float32), seg=6 if lod == 0 else 4,
            color_fn=lambda tt, th: rgba(124 + int(28 * tt), 94 + int(22 * tt), 58, 205 + int(45 * tt)),
            profile_mod=lambda tt, th: 1.0 + 0.35 * np.cos(2.0 * th),
        )
        parts.append(xform(stub, ry=ang, translate=(cx + math.sin(ang) * base_r * 0.85, cy, cz + math.cos(ang) * base_r * 0.85)))
    return merge_parts(parts)


def build_single_frond(length: float, droop: float, leaflet_pairs: int, tint_shift: float, lod: int) -> MeshPart:
    parts = []
    n = [11, 7, 5][lod]
    ts = np.linspace(0.0, 1.0, n, dtype=np.float32)
    spine_pts = np.stack([np.zeros_like(ts), 0.85 * length * 0.34 * np.sin(ts * 1.45) - droop * (ts ** 2.35), ts * length], axis=1)
    parts.append(tube_along_curve(spine_pts, 0.072 * ((1.0 - ts) ** 0.75) + 0.015, seg=5 if lod == 0 else 4, color_fn=lambda t, th: rgba(int(78 + 36 * t), int(126 + 46 * t), int(42 + 16 * t), 234)))

    pairs = leaflet_pairs if lod == 0 else (max(5, leaflet_pairs // 2) if lod == 1 else 3)
    width_boost = [1.0, 1.85, 3.1][lod]
    for li in range(pairs):
        t = 0.14 + 0.84 * (li / max(1, pairs - 1))
        idx_f = t * (n - 1)
        i0 = min(n - 2, int(idx_f))
        frac = idx_f - i0
        anchor = spine_pts[i0] * (1.0 - frac) + spine_pts[i0 + 1] * frac
        size_env = math.sin(math.pi * min(1.0, 0.14 + 0.86 * t)) ** 0.62
        leaf_len = (0.86 + 0.12 * ((li % 2) * 2 - 1)) * size_env
        for side in (-1.0, 1.0):
            rank_tilt = (0.22 if (li % 2 == 0) else -0.15) * side
            st_defs = [(0.0, 0.032, 0.0), (0.42, 0.072 * width_boost, -0.07), (1.0, 0.006, -0.38)] if lod >= 1 else [(0.0, 0.030, 0.0), (0.35, 0.070, -0.05), (0.72, 0.050, -0.20), (1.0, 0.005, -0.40)]
            stations = []
            for s_frac, width_k, drop_k in st_defs:
                dist = leaf_len * s_frac
                w = width_k * size_env
                pts4 = np.array([
                    [side * dist, drop_k * leaf_len - w * 0.32, -w],
                    [side * dist, drop_k * leaf_len + w * 0.28, 0.0],
                    [side * dist, drop_k * leaf_len - w * 0.32, w],
                    [side * dist, drop_k * leaf_len + w * 0.06, 0.0],
                ], dtype=np.float32)
                g_val = int(np.clip(126 + 62 * t + 28 * tint_shift - 16 * s_frac, 45, 240))
                r_val = int(np.clip(56 + 48 * t + 24 * tint_shift + 12 * s_frac, 25, 225))
                b_val = int(np.clip(36 + 18 * t, 20, 145))
                stations.append((pts4, rgba(r_val, g_val, b_val, int(208 + 45 * s_frac)), s_frac))
            parts.append(xform(loft_profile(stations, cap_start=False, cap_end=False), rz=rank_tilt, ry=side * 0.28 * t, translate=tuple(anchor)))
    return merge_parts(parts)


def build_palm_crown(lod: int) -> MeshPart:
    parts = []
    spear_n, upper_n, lower_n = [3, 2, 1][lod], [6, 4, 3][lod], [7, 5, 3][lod]
    for s in range(spear_n):
        parts.append(xform(build_single_frond(1.95, 0.18, 7, 0.55, lod), rx=-1.18, ry=s * (2.0 * math.pi / spear_n), translate=(0.0, 0.25, 0.0)))
    for i in range(upper_n):
        parts.append(xform(build_single_frond(3.35, 0.88, 10, 0.25, lod), rx=-0.42, ry=i * (2.0 * math.pi / upper_n) + 0.31, translate=(0.0, 0.14, 0.0)))
    for i in range(lower_n):
        parts.append(xform(build_single_frond(3.75, 1.52, 11, -0.10, lod), rx=-0.06, ry=i * (2.0 * math.pi / lower_n), translate=(0.0, 0.0, 0.0)))
    return merge_parts(parts)


def build_tbs_bunch(lod: int) -> MeshPart:
    # UV.x = 0.88 so GPU tint converts regular red-orange TBS into radiant 24K Sawit Emas cleanly!
    parts = [
        tag_dyeable(organic_ellipsoid(0.22, 0.28, 0.22, rings=[8, 6, 5][lod], seg=[10, 8, 6][lod], col_fn=lambda t, th: rgba(214, 74, 24, 212), disp_fn=lambda ph, th: 1.0 + 0.14 * np.sin(6.0 * th) * np.cos(4.0 * ph)), True),
        tube_along_curve(np.array([[0.0, 0.24, 0.0], [0.04, 0.46, 0.04]], dtype=np.float32), np.array([0.085, 0.055], dtype=np.float32), seg=6 if lod == 0 else 4, color_fn=lambda t, th: rgba(174, 160, 78, 238)),
    ]
    fruit_n = [36, 14, 0][lod]
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(fruit_n):
        y_n = 1.0 - 2.0 * (i + 0.5) / fruit_n
        rad = math.sqrt(max(0.0, 1.0 - y_n * y_n))
        ang = golden * i
        lobe = 1.0 + 0.14 * math.sin(3.0 * ang + y_n * 2.0)
        px, py, pz = math.cos(ang) * rad * 0.255 * lobe, y_n * 0.29, math.sin(ang) * rad * 0.255 * lobe
        rp = 0.5 + 0.5 * math.sin(i * 1.7)
        fruitlet = tag_dyeable(organic_ellipsoid(
            0.076, 0.088, 0.076, rings=5, seg=6,
            col_fn=lambda t, th, rpp=rp: rgba(int(228 + 26 * (1.0 - t)), int(68 + 96 * (1.0 - t) * rpp), int(20 + 20 * (1.0 - t)), int(188 + 65 * t)),
        ), True)
        parts.append(xform(fruitlet, ry=ang, rx=y_n * 0.6, translate=(px, py, pz)))
        if lod == 0 and i % 2 == 0:
            spine = tube_along_curve(np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.12]], dtype=np.float32), np.array([0.015, 0.002], dtype=np.float32), seg=4, color_fn=lambda t, th: rgba(138, 94, 46, 228))
            parts.append(xform(spine, ry=ang, rx=-y_n * 0.75, translate=(px * 1.08, py, pz * 1.08)))
    return merge_parts(parts)


def build_tropical_fern(lod: int) -> MeshPart:
    cnt = [8, 5, 3][lod]
    return merge_parts([xform(build_single_frond(0.95 + 0.18 * (i % 2), 0.34, 6, 0.35, lod), rx=-0.45 - 0.22 * (i % 2), ry=i * (2.0 * math.pi / cnt), scale=(0.65, 0.65, 0.65), translate=(0.0, 0.08, 0.0)) for i in range(cnt)])


def build_rock_boulder(lod: int) -> MeshPart:
    parts = []
    for k, (sx, sy, sz, ox, oz) in enumerate([(0.75, 0.52, 0.64, 0.0, 0.0), (0.44, 0.34, 0.42, 0.48, 0.24), (0.36, 0.26, 0.32, -0.38, 0.30)][:(3 if lod < 2 else 1)]):
        rock = organic_ellipsoid(sx, sy, sz, rings=[7, 5, 4][lod], seg=[9, 7, 5][lod], col_fn=lambda t, th: rgba(int(116 + 20 * t), int(100 + 26 * t), int(84 + 12 * t), int(178 + 75 * t)), disp_fn=lambda ph, th, kk=k: 1.0 + 0.16 * np.sin(3.0 * th + kk * 1.7) * np.cos(2.0 * ph) + 0.09 * np.cos(5.0 * th))
        parts.append(xform(rock, ry=k * 1.1, translate=(ox, sy * 0.55, oz)))
    return merge_parts(parts)


def build_canter_truck_body(lod: int) -> MeshPart:
    """Crisp chamfered automotive Canter Kebun dump truck — every glass/grille/bumper surface offset cleanly proud with ZERO overlap!"""
    parts = []
    cab_col = rgba(244, 190, 28, 250)      # Classic Canter Yellow (also dyeable!)
    cab_dk = rgba(206, 152, 18, 238)
    steel = rgba(64, 70, 78, 236)
    chrome = rgba(222, 230, 238, 252)
    glass = rgba(28, 46, 62, 250)
    wood_red = rgba(152, 70, 38, 240)
    wood_tan = rgba(184, 118, 58, 240)

    # Chassis rails (y = 0.50..0.66)
    for sx in (-0.46, 0.46):
        parts.append(xform(chamfer_box((0.12, 0.16, 4.90), 0.02, steel), translate=(sx, 0.58, -0.02)))

    # Lower Cab (z = 1.02..2.38, y = 0.66..1.32, x = -0.95..0.95)
    parts.append(xform(chamfer_box((1.90, 0.66, 1.36), 0.07, cab_col, dyeable=True), translate=(0.0, 0.99, 1.70)))
    # Upper Greenhouse Cab (z = 1.04..2.24, y = 1.30..2.02, sloped windshield!)
    parts.append(xform(chamfer_box((1.82, 0.72, 1.20), 0.07, cab_col, taper_top=(0.92, 0.84), shear_z_top=-0.14, arch_top=0.04, dyeable=True), translate=(0.0, 1.66, 1.64)))
    # Roof aero spoiler cap sitting ABOVE roof at y = 2.11
    parts.append(xform(chamfer_box((1.56, 0.16, 0.68), 0.05, cab_dk, taper_top=(0.82, 0.62), arch_top=0.05, dyeable=True), translate=(0.0, 2.11, 1.54)))

    # Tinted Windshield & Side Windows placed PROUD +4.5cm outside cab walls -> ZERO Z-FIGHTING EVER!
    parts.append(xform(chamfer_box((1.56, 0.46, 0.06), 0.02, glass), rx=-0.20, translate=(0.0, 1.68, 2.23)))
    for sx in (-1.0, 1.0):
        parts.append(xform(chamfer_box((0.06, 0.42, 0.74), 0.02, glass, shear_z_top=-0.10), translate=(sx * 0.92, 1.68, 1.66)))

    # Radiator Grille, Chrome Strip, Crystal Headlights & Amber Blinkers PROUD at z = 2.43..2.46
    parts.append(xform(chamfer_box((1.28, 0.24, 0.06), 0.02, rgba(28, 31, 36, 240)), translate=(0.0, 0.92, 2.41)))
    parts.append(xform(chamfer_box((1.22, 0.05, 0.07), 0.015, chrome), translate=(0.0, 0.93, 2.45)))
    for sx in (-1.0, 1.0):
        parts.append(xform(chamfer_box((0.28, 0.18, 0.06), 0.02, rgba(248, 252, 255, 255)), translate=(sx * 0.72, 0.92, 2.42)))
        parts.append(xform(chamfer_box((0.11, 0.18, 0.06), 0.02, rgba(255, 148, 20, 255)), translate=(sx * 0.91, 0.92, 2.38)))

    # Heavy Steel Bumper + Bullbar at z = 2.52
    parts.append(xform(chamfer_box((1.98, 0.22, 0.18), 0.03, steel), translate=(0.0, 0.58, 2.49)))
    if lod < 2:
        bull_pts = np.array([[-0.80, 0.62, 2.60], [-0.70, 1.08, 2.62], [0.70, 1.08, 2.62], [0.80, 0.62, 2.60]], dtype=np.float32)
        parts.append(tube_along_curve(bull_pts, np.full(4, 0.035, dtype=np.float32), seg=6, color_fn=lambda t, th: chrome))
        for sx in (-1.0, 1.0):
            arm = np.array([[sx * 0.92, 1.82, 2.02], [sx * 1.12, 1.80, 2.08], [sx * 1.12, 1.48, 2.06]], dtype=np.float32)
            parts.append(tube_along_curve(arm, np.full(3, 0.020, dtype=np.float32), seg=5, color_fn=lambda t, th: steel))
            parts.append(xform(chamfer_box((0.07, 0.26, 0.15), 0.02, rgba(38, 42, 48, 248)), translate=(sx * 1.13, 1.65, 2.08)))
        exh = np.array([[0.74, 0.62, 0.94], [0.78, 2.18, 0.94], [0.84, 2.36, 0.88]], dtype=np.float32)
        parts.append(tube_along_curve(exh, np.array([0.048, 0.044, 0.038], dtype=np.float32), seg=7, color_fn=lambda t, th: chrome))

    # Slatted Timber 'Bak Kayu Sawit' Dump Bed (z = -2.40 .. +0.82)
    parts.append(xform(chamfer_box((2.04, 0.13, 3.24), 0.03, wood_red), translate=(0.0, 0.74, -0.79)))
    plank_rows = [5, 3, 2][lod]
    for plank_i in range(plank_rows):
        py = 0.92 + plank_i * (0.86 / max(1, plank_rows - 1))
        h_p = 0.145 if lod == 0 else 0.27
        c_pl = wood_red if plank_i % 2 == 0 else wood_tan
        for sx in (-0.98, 0.98):
            parts.append(xform(chamfer_box((0.06, h_p, 3.16), 0.015, c_pl), translate=(sx, py, -0.79)))
        parts.append(xform(chamfer_box((1.92, h_p, 0.06), 0.015, c_pl), translate=(0.0, py, 0.79)))
        parts.append(xform(chamfer_box((1.92, h_p, 0.06), 0.015, c_pl), translate=(0.0, py, -2.37)))

    if lod < 2:
        for sz in (-2.28, -1.52, -0.76, 0.0, 0.72):
            for sx in (-1.04, 1.04):
                parts.append(xform(chamfer_box((0.06, 1.10, 0.07), 0.015, steel), translate=(sx, 1.35, sz)))
    return merge_parts(parts)


def build_truck_wheel(lod: int) -> MeshPart:
    """Zero-overlap continuous lathe profile tire + steel rim + center hub — ZERO Z-fighting!"""
    seg = [20, 12, 8][lod]
    thetas = np.linspace(0.0, 2.0 * math.pi, seg, endpoint=False, dtype=np.float32)
    prof = [
        (-0.21, 0.10, rgba(64, 68, 76, 250)),
        (-0.17, 0.24, rgba(236, 188, 38, 245)),
        (-0.19, 0.35, rgba(34, 36, 40, 238)),
        (-0.14, 0.46, rgba(28, 30, 34, 252)),
        (0.00, 0.475, rgba(26, 28, 32, 255)),
        (0.14, 0.46, rgba(28, 30, 34, 252)),
        (0.19, 0.35, rgba(34, 36, 40, 238)),
        (0.17, 0.24, rgba(236, 188, 38, 245)),
        (0.21, 0.10, rgba(64, 68, 76, 250)),
    ]
    stations = []
    for si, (xx, rr, c) in enumerate(prof):
        lugs = 1.0 + (0.042 * np.sign(np.sin(10.0 * thetas)) if (lod == 0 and 3 <= si <= 5) else 0.0)
        ring = np.stack([np.full_like(thetas, xx), np.sin(thetas) * rr * lugs, np.cos(thetas) * rr * lugs], axis=1)
        stations.append((ring, c, si / (len(prof) - 1)))
    return loft_profile(stations, cap_start=True, cap_end=True)


def build_truck_cargo_heap(lod: int) -> MeshPart:
    parts = []
    positions = [
        (-0.52, 0.18, -1.65, 0.2), (0.50, 0.18, -1.60, 1.3), (0.0, 0.20, -1.10, 2.4),
        (-0.54, 0.18, -0.55, 0.9), (0.52, 0.18, -0.50, 2.9), (0.0, 0.20, 0.05, 1.7),
        (-0.48, 0.18, 0.48, 2.1), (0.48, 0.18, 0.45, 0.5),
        (-0.28, 0.54, -1.25, 1.1), (0.30, 0.56, -0.80, 2.6), (-0.24, 0.55, -0.15, 0.4), (0.22, 0.52, 0.28, 1.9),
        (0.0, 0.84, -0.65, 0.8), (0.04, 0.80, -0.05, 2.2),
    ]
    mini_tbs = organic_ellipsoid(
        0.34, 0.28, 0.38, rings=[6, 4, 4][lod], seg=[8, 6, 5][lod],
        col_fn=lambda t, th: rgba(int(228 + 26 * (1.0 - t)), int(76 + 82 * (1.0 - t)), 22, int(188 + 65 * t)),
        disp_fn=lambda ph, th: 1.0 + 0.15 * np.sin(6.0 * th) * np.cos(4.0 * ph),
    )
    for px, py, pz, ry in positions[:([14, 10, 6][lod])]:
        parts.append(xform(mini_tbs, ry=ry, translate=(px, py, pz)))
    return merge_parts(parts)


def build_angkong_cart(lod: int) -> MeshPart:
    parts = [xform(chamfer_box((0.76, 0.42, 1.02), 0.08, rgba(36, 146, 166, 246), taper_top=(1.30, 1.26), shear_z_top=0.14), translate=(0.0, 0.58, 0.08))]
    for sx in (-1.0, 1.0):
        frame = np.array([[sx * 0.14, 0.32, 0.72], [sx * 0.30, 0.36, -0.25], [sx * 0.35, 0.68, -0.94]], dtype=np.float32)
        parts.append(tube_along_curve(frame, np.full(3, 0.024, dtype=np.float32), seg=5, color_fn=lambda t, th: rgba(68, 74, 82, 240)))
        leg = np.array([[sx * 0.30, 0.36, -0.32], [sx * 0.32, 0.04, -0.36], [sx * 0.30, 0.36, -0.44]], dtype=np.float32)
        parts.append(tube_along_curve(leg, np.full(3, 0.018, dtype=np.float32), seg=4, color_fn=lambda t, th: rgba(68, 74, 82, 240)))
    parts.append(xform(build_truck_wheel(lod), scale=(0.60, 0.60, 0.60), translate=(0.0, 0.29, 0.78)))
    # Heap 3 TBS bunches inside the wheelbarrow!
    for ox, oz in ((-0.15, 0.05), (0.16, 0.08), (0.0, 0.28)):
        parts.append(xform(organic_ellipsoid(0.20, 0.17, 0.22, 5, 6, col_fn=lambda t, th: rgba(232, 86, 24, 246)), translate=(ox, 0.84, oz)))
    return merge_parts(parts)


def build_pks_factory(lod: int) -> MeshPart:
    """Crisp architectural Pabrik Kelapa Sawit (PKS) industrial hall + boiler chimneys + CPO silos!"""
    parts = []
    wall = rgba(214, 220, 226, 242)
    roof_green = rgba(34, 126, 82, 248)
    steel = rgba(58, 64, 72, 232)
    accent = rgba(242, 180, 28, 252)

    parts.append(xform(chamfer_box((10.6, 5.4, 8.4), 0.12, wall), translate=(0.0, 2.7, 0.0)))
    parts.append(xform(chamfer_box((11.4, 1.5, 9.2), 0.10, roof_green, taper_top=(0.08, 0.98)), translate=(0.0, 6.12, 0.0)))
    parts.append(xform(chamfer_box((5.0, 1.1, 6.6), 0.10, wall), translate=(0.0, 7.05, 0.0)))
    parts.append(xform(chamfer_box((5.6, 0.65, 7.0), 0.08, roof_green, taper_top=(0.12, 0.98)), translate=(0.0, 7.90, 0.0)))

    for sx in (-5.38, -2.65, 2.65, 5.38):
        for sz in (-4.28, 4.28):
            parts.append(xform(chamfer_box((0.28, 5.3, 0.28), 0.03, steel), translate=(sx, 2.65, sz)))

    # Loading bay dark portal + overhanging yellow canopy cleanly offset at z = 4.30+
    parts.append(xform(chamfer_box((3.6, 3.4, 0.24), 0.04, rgba(24, 28, 34, 210)), translate=(0.0, 1.72, 4.32)))
    parts.append(xform(chamfer_box((4.6, 0.28, 2.6), 0.05, accent), rx=0.06, translate=(0.0, 3.85, 5.35)))

    for cx in (-3.2, -1.2):
        ch_pts = np.array([[cx, 5.4, -2.2], [cx, 9.6, -2.2], [cx, 13.4, -2.2]], dtype=np.float32)
        parts.append(tube_along_curve(ch_pts, np.array([0.62, 0.50, 0.40], dtype=np.float32), seg=[12, 8, 6][lod], color_fn=lambda t, th: rgba(192, 76, 54, 248) if (int(t * 9) % 2 == 0) else rgba(238, 240, 244, 250)))
    for tx, tz in ((7.3, -1.9), (7.3, 2.1)):
        silo = np.array([[tx, 0.0, tz], [tx, 4.8, tz], [tx, 5.5, tz]], dtype=np.float32)
        parts.append(tube_along_curve(silo, np.array([1.75, 1.75, 0.15], dtype=np.float32), seg=[14, 10, 6][lod], color_fn=lambda t, th: rgba(196, 204, 212, 242)))
    return merge_parts(parts)


def build_weighbridge_ram(lod: int) -> MeshPart:
    parts = []
    steel = rgba(58, 66, 76, 240)
    yellow = rgba(242, 184, 24, 252)
    parts.append(xform(chamfer_box((4.4, 0.26, 7.4), 0.04, steel), translate=(0.0, 0.13, 0.0)))
    for sz, tilt in ((4.55, 0.12), (-4.55, -0.12)):
        parts.append(xform(chamfer_box((4.2, 0.18, 1.6), 0.04, yellow), rx=tilt, translate=(0.0, 0.08, sz)))
    for sx in (-2.08, 2.08):
        rail = np.array([[sx, 0.26, -3.5], [sx, 0.72, -3.1], [sx, 0.72, 3.1], [sx, 0.26, 3.5]], dtype=np.float32)
        parts.append(tube_along_curve(rail, np.full(4, 0.085, dtype=np.float32), seg=6, color_fn=lambda t, th: yellow))
        parts.append(xform(chamfer_box((0.26, 4.2, 0.26), 0.03, steel), translate=(sx, 2.2, 0.0)))
    parts.append(xform(chamfer_box((4.8, 0.92, 0.40), 0.05, rgba(20, 24, 28, 250)), translate=(0.0, 4.35, 0.0)))
    parts.append(xform(chamfer_box((4.2, 0.22, 0.10), 0.02, rgba(34, 218, 126, 255)), translate=(0.0, 4.35, 0.24)))
    parts.append(xform(chamfer_box((4.2, 0.22, 0.10), 0.02, rgba(34, 218, 126, 255)), translate=(0.0, 4.35, -0.24)))
    return merge_parts(parts)


def build_mandor_post(lod: int) -> MeshPart:
    parts = []
    timber = rgba(136, 86, 48, 236)
    for sx in (-1.55, 1.55):
        for sz in (-1.55, 1.55):
            parts.append(xform(chamfer_box((0.20, 1.1, 0.20), 0.03, timber), translate=(sx, 0.55, sz)))
    parts.append(xform(chamfer_box((3.6, 0.18, 3.8), 0.04, timber), translate=(0.0, 1.05, 0.0)))
    parts.append(xform(chamfer_box((3.2, 2.1, 2.8), 0.05, rgba(168, 118, 70, 240)), translate=(0.0, 2.18, -0.35)))
    parts.append(xform(chamfer_box((4.1, 0.92, 4.5), 0.06, rgba(154, 164, 172, 244), taper_top=(0.08, 0.98)), translate=(0.0, 3.68, 0.0)))
    for step_i in range(3):
        parts.append(xform(chamfer_box((1.2, 0.16, 0.36), 0.03, timber), translate=(0.0, 0.26 + step_i * 0.30, 2.35 - step_i * 0.30)))
    return merge_parts(parts)


def build_wooden_bridge(lod: int) -> MeshPart:
    parts = []
    log_col, plank_col = rgba(116, 74, 40, 232), rgba(158, 110, 62, 242)
    n = [9, 6, 4][lod]
    zs = np.linspace(-4.2, 4.2, n, dtype=np.float32)
    arch_y = 0.52 * (1.0 - (zs / 4.2) ** 2)
    for sx in (-1.45, 0.0, 1.45):
        parts.append(tube_along_curve(np.stack([np.full_like(zs, sx), arch_y + 0.10, zs], axis=1), np.full(n, 0.15, dtype=np.float32), seg=6, color_fn=lambda t, th: log_col))
    planks = [14, 8, 5][lod]
    for pi in range(planks):
        zz = -3.9 + pi * (7.8 / max(1, planks - 1))
        yy = 0.52 * (1.0 - (zz / 4.2) ** 2) + 0.31
        parts.append(xform(chamfer_box((3.5, 0.10, 7.8 / planks * 0.84), 0.02, plank_col), translate=(0.0, yy, zz)))
    for sx in (-1.68, 1.68):
        parts.append(tube_along_curve(np.stack([np.full_like(zs, sx), arch_y + 1.06, zs], axis=1), np.full(n, 0.06, dtype=np.float32), seg=5, color_fn=lambda t, th: log_col))
    return merge_parts(parts)


def build_celeng_boar(lod: int) -> MeshPart:
    parts = []
    spine = np.array([[0.0, 0.56, -0.58], [0.0, 0.66, -0.15], [0.0, 0.72, 0.25], [0.0, 0.54, 0.62], [0.0, 0.44, 0.88]], dtype=np.float32)
    parts.append(tube_along_curve(spine, np.array([0.24, 0.34, 0.38, 0.24, 0.11], dtype=np.float32), seg=[12, 8, 6][lod], color_fn=lambda t, th: rgba(int(78 + 18 * t), int(58 + 14 * t), 44, 238), profile_mod=lambda t, th: 1.0 + 0.14 * np.maximum(0.0, np.sin(th))))
    for sx in (-1.0, 1.0):
        tusk = np.array([[sx * 0.11, 0.44, 0.78], [sx * 0.22, 0.52, 0.90], [sx * 0.18, 0.66, 0.88]], dtype=np.float32)
        parts.append(tube_along_curve(tusk, np.array([0.032, 0.022, 0.005], dtype=np.float32), seg=5, color_fn=lambda t, th: rgba(246, 240, 220, 255)))
        for sz in (-0.42, 0.36):
            leg = np.array([[sx * 0.20, 0.52, sz], [sx * 0.20, 0.26, sz - 0.04], [sx * 0.20, 0.02, sz + 0.02]], dtype=np.float32)
            parts.append(tube_along_curve(leg, np.array([0.095, 0.065, 0.048], dtype=np.float32), seg=6, color_fn=lambda t, th: rgba(58, 42, 34, 232)))
    return merge_parts(parts)


def build_char_torso_head(lod: int) -> MeshPart:
    """
    ONLY the athletic shirt/jersey uses dyeable=True (uv.x=0.88)!
    Face skin, sunglasses, belt, brass buckle, and hair keep crisp fixed natural colors (uv.x=0.18),
    and upper hair dome uses upper-hemisphere phi_range=(0.05..0.485*pi) so ZERO Z-fighting with face!
    """
    parts = [
        xform(chamfer_box((0.36, 0.10, 0.25), 0.04, rgba(52, 42, 34, 240)), translate=(0.0, 0.04, 0.0)),
        xform(chamfer_box((0.09, 0.09, 0.04), 0.015, rgba(244, 196, 48, 255)), translate=(0.0, 0.04, 0.145)),
        tube_along_curve(
            np.array([[0.0, 0.08, 0.0], [0.0, 0.23, 0.01], [0.0, 0.40, 0.02], [0.0, 0.54, 0.0]], dtype=np.float32),
            np.array([0.165, 0.195, 0.235, 0.155], dtype=np.float32), seg=[14, 10, 7][lod],
            color_fn=lambda t, th: rgba(int(232 + 22 * t), int(232 + 22 * t), int(232 + 22 * t), int(214 + 40 * t)),
            profile_mod=lambda t, th: 1.0 + 0.22 * np.cos(2.0 * th + math.pi),
            dyeable=True,
        ),
    ]
    skin = rgba(224, 172, 132, 248)
    parts.append(tube_along_curve(np.array([[0.0, 0.53, 0.0], [0.0, 0.65, 0.01]], dtype=np.float32), np.array([0.078, 0.072], dtype=np.float32), seg=8, color_fn=lambda t, th: skin))
    head = organic_ellipsoid(0.165, 0.195, 0.175, rings=[10, 7, 5][lod], seg=[14, 10, 7][lod], col_fn=lambda t, th: skin, disp_fn=lambda ph, th: 1.0 - 0.08 * np.maximum(0.0, -np.sin(ph)) * np.cos(th))
    parts.append(xform(head, translate=(0.0, 0.79, 0.02)))
    if lod < 2:
        parts.append(xform(chamfer_box((0.042, 0.068, 0.055), 0.015, skin, taper_top=(0.65, 0.5)), translate=(0.0, 0.78, 0.205)))
        # Cool dark wraparound sporty visor sunglasses proud of face at z = 0.202!
        parts.append(xform(chamfer_box((0.235, 0.052, 0.040), 0.015, rgba(22, 28, 36, 255)), translate=(0.0, 0.815, 0.192)))
    # Upper crown hair dome ONLY above forehead (phi >= 0.12*pi) -> ZERO face overlap!
    hair_cap = organic_ellipsoid(0.184, 0.185, 0.194, rings=6, seg=[12, 8, 6][lod], col_fn=lambda t, th: rgba(34, 28, 26, 246), phi_range=(math.pi * 0.06, math.pi * 0.485))
    parts.append(xform(hair_cap, rx=-0.16, translate=(0.0, 0.81, -0.005)))
    return merge_parts(parts)


def build_char_arm(lod: int) -> MeshPart:
    sg = [9, 6, 5][lod]
    return merge_parts([
        tube_along_curve(np.array([[0.0, 0.0, 0.0], [0.0, -0.19, 0.01]], dtype=np.float32), np.array([0.078, 0.068], dtype=np.float32), seg=sg, color_fn=lambda t, th: rgba(244, 244, 244, 242), dyeable=True),
        tube_along_curve(np.array([[0.0, -0.19, 0.01], [0.0, -0.34, 0.04], [0.0, -0.46, 0.07]], dtype=np.float32), np.array([0.060, 0.052, 0.044], dtype=np.float32), seg=sg, color_fn=lambda t, th: rgba(220, 168, 128, 246)),
        xform(chamfer_box((0.095, 0.11, 0.105), 0.025, rgba(52, 58, 66, 248)), translate=(0.0, -0.51, 0.08)),
    ])


def build_char_leg(lod: int) -> MeshPart:
    sg = [10, 7, 5][lod]
    return merge_parts([
        tube_along_curve(np.array([[0.0, 0.0, 0.0], [0.0, -0.26, 0.02], [0.0, -0.49, 0.0]], dtype=np.float32), np.array([0.098, 0.084, 0.074], dtype=np.float32), seg=sg, color_fn=lambda t, th: rgba(68, 76, 86, 238)),
        tube_along_curve(np.array([[0.0, -0.49, 0.0], [0.0, -0.79, -0.01]], dtype=np.float32), np.array([0.084, 0.074], dtype=np.float32), seg=sg, color_fn=lambda t, th: rgba(44, 102, 66, 242) if t > 0.18 else rgba(238, 190, 38, 250)),
        xform(chamfer_box((0.15, 0.12, 0.27), 0.03, rgba(34, 38, 42, 248)), translate=(0.0, -0.85, 0.05)),
    ])


def build_hat_caping(lod: int) -> MeshPart:
    return tube_along_curve(
        np.array([[0.0, 0.0, 0.0], [0.0, 0.10, 0.0], [0.0, 0.20, 0.0], [0.0, 0.28, 0.0]], dtype=np.float32),
        np.array([0.42, 0.27, 0.12, 0.015], dtype=np.float32), seg=[20, 12, 8][lod],
        color_fn=lambda t, th: rgba(224, 58, 42, 250) if t < 0.08 else rgba(int(220 - 26 * t), int(180 - 22 * t), int(106 - 14 * t), int(222 + 32 * t)),
        profile_mod=lambda t, th: 1.0 + 0.025 * np.cos(10.0 * th),
    )


def build_hat_safety(lod: int) -> MeshPart:
    return merge_parts([
        xform(organic_ellipsoid(0.205, 0.155, 0.235, rings=[7, 5, 4][lod], seg=[14, 10, 7][lod], col_fn=lambda t, th: rgba(248, 194, 26, 250), phi_range=(-0.15, math.pi * 0.485)), translate=(0.0, 0.05, 0.0)),
        xform(chamfer_box((0.06, 0.08, 0.36), 0.02, rgba(255, 214, 56, 255)), translate=(0.0, 0.19, 0.0)),
        xform(chamfer_box((0.34, 0.035, 0.15), 0.015, rgba(234, 176, 18, 246)), rx=0.14, translate=(0.0, 0.02, 0.21)),
    ])


def build_hat_headband(lod: int) -> MeshPart:
    parts = [tube_along_curve(np.array([[0.0, -0.02, 0.01], [0.0, 0.05, 0.01]], dtype=np.float32), np.array([0.192, 0.192], dtype=np.float32), seg=[16, 10, 7][lod], color_fn=lambda t, th: rgba(224, 40, 44, 248))]
    for sx in (-1.0, 1.0):
        tail = np.array([[sx * 0.05, 0.02, -0.20], [sx * 0.13, -0.10, -0.35], [sx * 0.19, -0.26, -0.49]], dtype=np.float32)
        parts.append(tube_along_curve(tail, np.array([0.038, 0.048, 0.018], dtype=np.float32), seg=5, color_fn=lambda t, th: rgba(236, 50, 54, 250)))
    return merge_parts(parts)


def build_hat_cowboy(lod: int) -> MeshPart:
    seg = [18, 12, 8][lod]
    th = np.linspace(0, 2 * math.pi, seg, endpoint=False, dtype=np.float32)
    curl = 0.075 * (np.cos(th) ** 2)
    brim = loft_profile([
        (np.stack([np.cos(th) * 0.16, np.zeros_like(th), np.sin(th) * 0.19], axis=1), rgba(118, 72, 42, 240), 0.0),
        (np.stack([np.cos(th) * 0.36, curl, np.sin(th) * 0.40], axis=1), rgba(134, 84, 48, 250), 1.0),
    ], cap_start=False, cap_end=False)
    return merge_parts([
        brim,
        xform(chamfer_box((0.29, 0.17, 0.34), 0.06, rgba(124, 76, 44, 246), taper_top=(0.76, 0.80)), translate=(0.0, 0.10, 0.0)),
        xform(chamfer_box((0.31, 0.035, 0.36), 0.05, rgba(244, 194, 46, 255)), translate=(0.0, 0.03, 0.0)),
    ])


def build_hat_crown_gold(lod: int) -> MeshPart:
    gold, gem = rgba(255, 208, 48, 255), rgba(28, 236, 142, 255)
    parts = [tube_along_curve(np.array([[0.0, 0.0, 0.0], [0.0, 0.085, 0.0]], dtype=np.float32), np.array([0.190, 0.204], dtype=np.float32), seg=[16, 10, 8][lod], color_fn=lambda t, th: gold)]
    spikes = [8, 6, 4][lod]
    for i in range(spikes):
        ang = i * (2.0 * math.pi / spikes)
        h = 0.22 if i % 2 == 0 else 0.15
        parts.append(xform(chamfer_box((0.065, h, 0.035), 0.012, gold, taper_top=(0.14, 0.4)), ry=ang, translate=(math.sin(ang) * 0.198, 0.085 + h * 0.42, math.cos(ang) * 0.198)))
        if lod < 2 and i % 2 == 0:
            parts.append(xform(chamfer_box((0.044, 0.054, 0.032), 0.01, gem), ry=ang, translate=(math.sin(ang) * 0.222, 0.045, math.cos(ang) * 0.222)))
    return merge_parts(parts)


def build_back_basket(lod: int) -> MeshPart:
    pts = np.array([[0.0, -0.22, -0.10], [0.0, 0.02, -0.13], [0.0, 0.24, -0.16]], dtype=np.float32)
    parts = [tube_along_curve(pts, np.array([0.14, 0.19, 0.24], dtype=np.float32), seg=[14, 9, 6][lod], color_fn=lambda t, th: rgba(int(182 + 32 * ((int(t * 10)) % 2)), int(138 + 24 * t), 72, 242))]
    for ox, oz in ((-0.08, -0.13), (0.09, -0.15), (0.0, -0.22)):
        parts.append(xform(organic_ellipsoid(0.09, 0.09, 0.09, 5, 6, col_fn=lambda t, th: rgba(236, 92, 26, 248)), translate=(ox, 0.26, oz)))
    return merge_parts(parts)


def build_back_pack(lod: int) -> MeshPart:
    return merge_parts([
        xform(chamfer_box((0.30, 0.38, 0.18), 0.04, rgba(56, 76, 60, 240)), translate=(0.0, 0.0, -0.09)),
        xform(chamfer_box((0.24, 0.18, 0.07), 0.02, rgba(242, 180, 28, 250)), translate=(0.0, -0.05, -0.21)),
        tube_along_curve(np.array([[0.11, 0.18, -0.10], [0.14, 0.64, -0.16]], dtype=np.float32), np.array([0.016, 0.005], dtype=np.float32), seg=5, color_fn=lambda t, th: rgba(214, 218, 224, 250)),
    ])


def build_back_cape(lod: int) -> MeshPart:
    stations = []
    xs = np.linspace(-0.22, 0.22, [9, 6, 4][lod], dtype=np.float32)
    for row_i, (yy, zz, spread, fold) in enumerate([(0.18, -0.04, 0.9, 0.01), (-0.08, -0.10, 1.15, 0.025), (-0.36, -0.18, 1.45, 0.045), (-0.66, -0.26, 1.72, 0.065)]):
        ring = [[x * spread, yy, zz + math.sin(x * 26.0) * fold] for x in xs] + [[x * spread, yy, zz + math.sin(x * 26.0) * fold - 0.024] for x in reversed(xs)]
        stations.append((np.asarray(ring, dtype=np.float32), rgba(238, 188, 38, 255) if row_i == 0 else rgba(222, 40, 50, 246), row_i / 3.0))
    return loft_profile(stations, cap_start=True, cap_end=True)


def build_back_wings_gold(lod: int) -> MeshPart:
    """Spread wide along +/-X behind the shoulders like radiant golden palm phoenix wings!"""
    parts = []
    for sx in (-1.0, 1.0):
        for fi, (ln, pitch_up) in enumerate([(0.98, -0.46), (0.82, -0.14), (0.64, 0.18)][:([3, 2, 2][lod])]):
            fr = build_single_frond(ln, 0.16, 7, 0.9, lod)
            fr.col = np.broadcast_to(rgba(255, 208 - fi * 14, 44, 252), fr.col.shape).copy()
            parts.append(xform(fr, rx=pitch_up, ry=sx * (math.pi * 0.56), translate=(sx * 0.14, 0.16 - fi * 0.08, -0.10)))
    return merge_parts(parts)


def build_tool_egrek(lod: int) -> MeshPart:
    return merge_parts([
        tube_along_curve(np.array([[0.0, -0.22, 0.0], [0.0, 1.05, 0.0], [0.0, 2.05, 0.0]], dtype=np.float32), np.array([0.028, 0.024, 0.019], dtype=np.float32), seg=6, color_fn=lambda t, th: rgba(218, 54, 44, 250) if t < 0.22 else rgba(202, 212, 222, 248)),
        xform(chamfer_box((0.075, 0.11, 0.075), 0.02, rgba(232, 178, 26, 255)), translate=(0.0, 2.04, 0.0)),
        tube_along_curve(
            np.array([[0.0, 2.06, 0.0], [0.02, 2.26, 0.08], [0.02, 2.44, 0.02], [0.0, 2.52, -0.18], [-0.01, 2.44, -0.34]], dtype=np.float32),
            np.array([0.028, 0.044, 0.040, 0.026, 0.004], dtype=np.float32), seg=6,
            color_fn=lambda t, th: rgba(236, 242, 250, 255),
            profile_mod=lambda t, th: np.where(np.abs(np.cos(th)) > 0.5, 0.22, 1.38),
        ),
    ])


def build_tool_dodos(lod: int) -> MeshPart:
    return merge_parts([
        tube_along_curve(np.array([[0.0, -0.20, 0.0], [0.0, 0.95, 0.0]], dtype=np.float32), np.array([0.030, 0.026], dtype=np.float32), seg=6, color_fn=lambda t, th: rgba(156, 102, 54, 246)),
        xform(chamfer_box((0.038, 0.42, 0.20), 0.012, rgba(222, 232, 242, 255), taper_top=(0.35, 1.45)), translate=(0.0, 1.16, 0.0)),
    ])


def build_tool_egrek_dragon(lod: int) -> MeshPart:
    return merge_parts([
        tube_along_curve(np.array([[0.0, -0.22, 0.0], [0.0, 2.10, 0.0]], dtype=np.float32), np.array([0.032, 0.022], dtype=np.float32), seg=7, color_fn=lambda t, th: rgba(36, 36, 44, 248) if (int(t * 12) % 2 == 0) else rgba(250, 198, 40, 255)),
        xform(chamfer_box((0.10, 0.16, 0.22), 0.025, rgba(255, 200, 44, 255)), translate=(0.0, 2.08, 0.0)),
        tube_along_curve(
            np.array([[0.0, 2.10, 0.02], [0.0, 2.38, 0.14], [0.0, 2.62, -0.02], [0.0, 2.70, -0.28], [0.0, 2.54, -0.46]], dtype=np.float32),
            np.array([0.036, 0.064, 0.056, 0.038, 0.005], dtype=np.float32), seg=6,
            color_fn=lambda t, th: rgba(255, 198, 48, 255) if t < 0.45 else rgba(255, 96, 36, 255),
            profile_mod=lambda t, th: np.where(np.abs(np.cos(th)) > 0.5, 0.20, 1.45),
        ),
    ])


MODEL_SPECS: List[Tuple[str, Callable[[int], MeshPart]]] = [
    ("palm_trunk", build_palm_trunk),
    ("palm_crown", build_palm_crown),
    ("tbs_bunch", build_tbs_bunch),
    ("tropical_fern", build_tropical_fern),
    ("rock_boulder", build_rock_boulder),
    ("canter_truck_body", build_canter_truck_body),
    ("truck_wheel", build_truck_wheel),
    ("truck_cargo_heap", build_truck_cargo_heap),
    ("angkong_cart", build_angkong_cart),
    ("pks_factory", build_pks_factory),
    ("weighbridge_ram", build_weighbridge_ram),
    ("mandor_post", build_mandor_post),
    ("wooden_bridge", build_wooden_bridge),
    ("celeng_boar", build_celeng_boar),
    ("char_torso_head", build_char_torso_head),
    ("char_arm", build_char_arm),
    ("char_leg", build_char_leg),
    ("hat_caping", build_hat_caping),
    ("hat_safety", build_hat_safety),
    ("hat_headband", build_hat_headband),
    ("hat_cowboy", build_hat_cowboy),
    ("hat_crown_gold", build_hat_crown_gold),
    ("back_basket", build_back_basket),
    ("back_pack", build_back_pack),
    ("back_cape", build_back_cape),
    ("back_wings_gold", build_back_wings_gold),
    ("tool_egrek", build_tool_egrek),
    ("tool_dodos", build_tool_dodos),
    ("tool_egrek_dragon", build_tool_egrek_dragon),
]


def pack_vertex_stream(part: MeshPart, nrm: np.ndarray) -> Tuple[bytes, bytes]:
    n = len(part.pos)
    dtype_v = np.dtype([("pos", "<f4", (3,)), ("nrm", "<f4", (3,)), ("uv", "<f4", (2,)), ("col", "u1", (4,))])
    arr = np.empty(n, dtype=dtype_v)
    arr["pos"] = part.pos.astype("<f4")
    arr["nrm"] = nrm.astype("<f4")
    arr["uv"] = part.uv.astype("<f4")
    arr["col"] = part.col.astype("u1")
    return arr.tobytes(), part.idx.reshape(-1).astype("<u2").tobytes()


def main() -> None:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out_android = os.path.join(root, "src", "Nyawit.Android", "Assets", "Meshes", "nyawit_models.npak")
    out_web = os.path.join(root, "server", "public", "assets", "nyawit_models.npak")
    out_manifest = os.path.join(root, "docs", "mesh_manifest.json")

    chunks = [struct.pack("<4sII", b"NPAK", 1, len(MODEL_SPECS))]
    manifest = {"version": 1, "stride_bytes": 36, "models": []}
    tot0, tot1, tot2 = 0, 0, 0

    for name, fn in MODEL_SPECS:
        lods = [finalize_normals_and_ao(fn(li)) for li in (0, 1, 2)]
        lod0_part = lods[0][1]
        bmin, bmax = lod0_part.pos.min(axis=0), lod0_part.pos.max(axis=0)
        radius = float(np.linalg.norm(lod0_part.pos, axis=1).max())

        name_bytes = name.encode("utf-8")
        chunks.append(struct.pack("<BfffffffB", len(name_bytes), radius, bmin[0], bmin[1], bmin[2], bmax[0], bmax[1], bmax[2], 3))
        chunks.append(name_bytes)

        stats = []
        for li, (ln, lp) in enumerate(lods):
            vb, ib = pack_vertex_stream(lp, ln)
            chunks.append(struct.pack("<II", len(lp.pos), len(lp.idx) * 3))
            chunks.append(vb)
            chunks.append(ib)
            stats.append({"lod": li, "verts": int(len(lp.pos)), "tris": int(len(lp.idx))})

        tot0 += stats[0]["tris"]
        tot1 += stats[1]["tris"]
        tot2 += stats[2]["tris"]
        manifest["models"].append({"name": name, "radius": round(radius, 3), "lods": stats})
        print(f"  [OK] {name:<20} LOD0={stats[0]['tris']:>4} | LOD1={stats[1]['tris']:>4} | LOD2={stats[2]['tris']:>4}")

    blob = b"".join(chunks)
    for dst in (out_android, out_web):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(blob)

    manifest["total_lod0_tris"] = tot0
    manifest["total_lod1_tris"] = tot1
    manifest["total_lod2_tris"] = tot2
    manifest["binary_bytes"] = len(blob)
    with open(out_manifest, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n=== NPAK BUILT: {len(MODEL_SPECS)} models x 3 LODs = {len(MODEL_SPECS)*3} GPU meshes ===")
    print(f"    LOD0={tot0:,} tris -> LOD1={tot1:,} tris -> LOD2={tot2:,} tris | Size={len(blob)/1024/1024:.2f} MB")


if __name__ == "__main__":
    main()
