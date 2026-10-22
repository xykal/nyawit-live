#!/usr/bin/env python3
"""
Nyawit Live 3D v2.0 — Ultra-Crisp Hard-Surface & Organic 3D Asset + AO + Material Pipeline

Generates 29 complex, high-craft 3D models across 3 parametric LOD tiers (87 GPU meshes):
  - Sharp 28-degree hard-surface crease splitting so automotive panels, truck beds, roofs, crowns,
    and factory walls render with razor-sharp facets instead of mushy pillow normals!
  - Dual UV material channels (ZERO texture memory overhead on mobile GPUs!):
      uv.x >= 0.75 -> Customizable outfit / truck paint dye mask
      uv.x <  0.50 -> Fixed material color (skin, chrome, glass, gold, wood, foliage, bark)
      uv.y >= 0.92 -> HDR self-illuminated emissive glow (headlights, taillights, LED signage, floodlights, gems)
      uv.y in 0.55..0.88 -> High-gloss automotive clearcoat / metallic chrome / waxy palm frond specular
      uv.y <  0.50 -> Matte organic / timber / soil / fabric finish
  - 12-direction hemisphere raycast Ambient Occlusion baked directly into vertex alpha (col.a).
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


def mat(part: MeshPart, dyeable: bool = False, gloss: float = 0.30) -> MeshPart:
    uv = part.uv.copy()
    uv[:, 0] = 0.88 if dyeable else 0.18
    uv[:, 1] = float(gloss)
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
    dyeable: bool = False,
    gloss: float = 0.30,
) -> MeshPart:
    u_fixed = 0.88 if dyeable else 0.18
    rings = len(stations)
    seg = len(stations[0][0])
    pos, uv, col = [], [], []
    for pts, c, _ in stations:
        c_arr = np.broadcast_to(np.asarray(c, dtype=np.uint8), (seg, 4)).copy()
        u_vals = np.full(seg, u_fixed, dtype=np.float32)
        v_vals = np.full(seg, gloss, dtype=np.float32)
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
        extra_uv.append(np.array([[u_fixed, gloss]], dtype=np.float32))
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
        extra_uv.append(np.array([[u_fixed, gloss]], dtype=np.float32))
        extra_col.append(c_col)
        ci = next_idx
        for j in range(seg):
            jn = (j + 1) % seg
            tris.append([ci, base + jn, base + j])

    part = MeshPart(np.vstack(extra_pos), np.vstack(extra_uv), np.vstack(extra_col), np.asarray(tris, dtype=np.int32))
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
    gloss: float = 0.34,
) -> MeshPart:
    sx, sy, sz = size[0] * 0.5, size[1] * 0.5, size[2] * 0.5
    ch = min(chamfer, sx * 0.42, sz * 0.42)
    ch_y = min(chamfer * 0.85, sy * 0.42)
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
        (-sy, 0.90, 0.0, 0.82),
        (-sy + ch_y, 1.0, 0.0, 0.96),
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
    return loft_profile(stations, cap_start=True, cap_end=True, dyeable=dyeable, gloss=gloss)


def tube_along_curve(
    pts: np.ndarray,
    radii: np.ndarray,
    seg: int,
    color_fn: Callable[[float, np.ndarray], np.ndarray],
    profile_mod: Callable[[float, np.ndarray], np.ndarray] | None = None,
    cap_ends: bool = True,
    dyeable: bool = False,
    gloss: float = 0.28,
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
    return loft_profile(stations, cap_start=cap_ends, cap_end=cap_ends, dyeable=dyeable, gloss=gloss)


def organic_ellipsoid(
    rx: float, ry: float, rz: float,
    rings: int, seg: int,
    col_fn: Callable[[float, np.ndarray], np.ndarray],
    disp_fn: Callable[[np.ndarray, np.ndarray], np.ndarray] | None = None,
    phi_range: Tuple[float, float] = (-math.pi * 0.485, math.pi * 0.485),
    dyeable: bool = False,
    gloss: float = 0.32,
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
    return loft_profile(stations, cap_start=True, cap_end=True, dyeable=dyeable, gloss=gloss)


def finalize_normals_and_ao(part: MeshPart, ao_strength: float = 0.50) -> Tuple[np.ndarray, MeshPart]:
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

    # Crisp 39-degree hard-surface crease split -> 45/90-deg automotive & architectural edges split razor-sharp,
    # while 16..20-segment organic curves (22.5 deg < 39 deg) shade 100% silky smooth!
    cos_thresh = math.cos(math.radians(39.0))
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
        col = part.col.copy()
        col = np.vstack([col, s_col])
        nrm = np.vstack([nrm, s_nrm])
        idx = np.vstack([smooth_idx, s_idx])
    else:
        uv = part.uv
        col = part.col.copy()

    occ = np.zeros(len(pos), dtype=np.float32)
    golden = math.pi * (3.0 - math.sqrt(5.0))
    RES = 28
    for i in range(12):
        y = 0.22 + 0.78 * (i + 0.5) / 12.0
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
        span = max(float(pw.max() - pu.min()) if False else float(pw.max() - pw.min()), 1e-3)
        occ += np.where((depth > span * 0.05) & (facing > 0.05), np.minimum(1.0, depth / (span * 0.34)) * facing, 0.0)

    ao_geom = 1.0 - ao_strength * np.clip(occ / 6.4, 0.0, 0.72)
    col_out = col.copy()
    col_out[:, 3] = np.clip(col_out[:, 3].astype(np.float32) * ao_geom, 72.0, 255.0).astype(np.uint8)
    return nrm.astype(np.float32), MeshPart(pos, uv, col_out, idx, nrm.astype(np.float32))


# ==============================================================================
#  29 HIGH-CRAFT SCULPTED 3D MODELS (HERO DETAIL + ULTRA-LIGHT FAR LODS)
# ==============================================================================

def build_palm_trunk(lod: int) -> MeshPart:
    parts = []
    n = [34, 16, 7][lod]
    seg = [18, 10, 6][lod]
    ts = np.linspace(0.0, 1.0, n, dtype=np.float32)
    pts = np.stack([0.22 * np.sin(ts * 2.3) + 0.08 * ts * ts, ts * 6.4, 0.15 * (1.0 - np.cos(ts * 1.9))], axis=1)
    radii = 0.62 * ((1.0 - ts) ** 2.6) * 0.48 + 0.36 - 0.10 * ts

    def mod(t: float, th: np.ndarray) -> np.ndarray:
        diamond = np.maximum(0.0, np.sin(8.0 * th + t * 48.0) * np.sin(5.0 * th - t * 32.0))
        buttress = (1.0 - min(1.0, t / 0.18)) * 0.26 * (0.5 + 0.5 * np.cos(7.0 * th + 0.4))
        return 1.0 + 0.16 * diamond * (0.35 + 0.65 * t) + buttress

    def col_fn(t: float, th: np.ndarray) -> np.ndarray:
        scar = np.clip(np.sin(8.0 * th + t * 48.0) * np.sin(5.0 * th - t * 32.0), 0.0, 1.0)
        moss = np.clip(1.0 - t * 2.6, 0.0, 1.0) * 0.52
        return np.stack([
            86 + 56 * scar - 24 * moss,
            66 + 44 * scar + 32 * moss,
            46 + 24 * scar - 8 * moss,
            168 + 84 * scar,
        ], axis=1).astype(np.uint8)

    parts.append(tube_along_curve(pts, radii, seg=seg, color_fn=col_fn, profile_mod=mod, gloss=0.22))
    stub_count = [38, 10, 0][lod]
    for i in range(stub_count):
        t = 0.22 + 0.75 * (i / max(1, stub_count))
        ang = i * 2.39996
        cx, cy, cz = 0.22 * math.sin(t * 2.3) + 0.08 * t * t, t * 6.4, 0.15 * (1.0 - math.cos(t * 1.9))
        base_r = 0.36 - 0.095 * t
        stub = tube_along_curve(
            np.array([[0.0, -0.02, 0.0], [0.0, 0.08, 0.18], [0.0, 0.18, 0.34]], dtype=np.float32),
            np.array([0.145, 0.105, 0.045], dtype=np.float32), seg=6 if lod == 0 else 4,
            color_fn=lambda tt, th: rgba(118 + int(36 * tt), 88 + int(28 * tt), 52, 185 + int(65 * tt)),
            profile_mod=lambda tt, th: 1.0 + 0.42 * np.cos(2.0 * th),
            gloss=0.20,
        )
        parts.append(xform(stub, ry=ang, translate=(cx + math.sin(ang) * base_r * 0.84, cy, cz + math.cos(ang) * base_r * 0.84)))
    return merge_parts(parts)


def build_single_frond(length: float, droop: float, leaflet_pairs: int, tint_shift: float, lod: int) -> MeshPart:
    parts = []
    n = [9, 6, 4][lod]
    ts = np.linspace(0.0, 1.0, n, dtype=np.float32)
    spine_pts = np.stack([np.zeros_like(ts), 0.90 * length * 0.35 * np.sin(ts * 1.48) - droop * (ts ** 2.30), ts * length], axis=1)
    parts.append(tube_along_curve(
        spine_pts, 0.076 * ((1.0 - ts) ** 0.75) + 0.014, seg=4,
        color_fn=lambda t, th: rgba(int(72 + 40 * t), int(128 + 50 * t), int(38 + 16 * t), 232),
        gloss=0.58,
    ))

    pairs = leaflet_pairs if lod == 0 else (max(4, leaflet_pairs // 2) if lod == 1 else 2)
    width_boost = [1.35, 2.35, 3.80][lod]
    for li in range(pairs):
        t = 0.14 + 0.84 * (li / max(1, pairs - 1))
        idx_f = t * (n - 1)
        i0 = min(n - 2, int(idx_f))
        frac = idx_f - i0
        anchor = spine_pts[i0] * (1.0 - frac) + spine_pts[i0 + 1] * frac
        size_env = math.sin(math.pi * min(1.0, 0.16 + 0.84 * t)) ** 0.56
        leaf_len = (0.98 + 0.14 * ((li % 2) * 2 - 1)) * size_env
        for side in (-1.0, 1.0):
            rank_tilt = (0.24 if (li % 2 == 0) else -0.16) * side
            st_defs = [(0.0, 0.042, 0.0), (0.44, 0.095 * width_boost, -0.08), (1.0, 0.008, -0.42)]
            stations = []
            for s_frac, width_k, drop_k in st_defs:
                dist = leaf_len * s_frac
                w = width_k * size_env
                pts3 = np.array([
                    [side * dist, drop_k * leaf_len - w * 0.34, -w],
                    [side * dist, drop_k * leaf_len + w * 0.28, 0.0],
                    [side * dist, drop_k * leaf_len - w * 0.34, w],
                ], dtype=np.float32)
                g_val = int(np.clip(118 + 72 * t + 32 * tint_shift - 14 * s_frac, 42, 244))
                r_val = int(np.clip(48 + 46 * t + 26 * tint_shift + 14 * s_frac, 22, 225))
                b_val = int(np.clip(30 + 18 * t, 18, 130))
                stations.append((pts3, rgba(r_val, g_val, b_val, int(198 + 54 * s_frac)), s_frac))
            parts.append(xform(loft_profile(stations, cap_start=False, cap_end=False, gloss=0.64), rz=rank_tilt, ry=side * 0.28 * t, translate=tuple(anchor)))
    return merge_parts(parts)


def build_palm_crown(lod: int) -> MeshPart:
    parts = []
    # Lush 4-whorl tropical oil palm crown with 3.5x faster V-ridge botanical blades (LOD0 ~4.1K tris, LOD2 ~440 tris!)
    spear_n, upper_n, mid_n, lower_n = [3, 2, 1][lod], [5, 3, 2][lod], [5, 3, 2][lod], [5, 3, 2][lod]
    parts.append(organic_ellipsoid(0.42, 0.34, 0.42, 5, 8, col_fn=lambda t, th: rgba(88, 108, 44, 175), gloss=0.25))
    for s in range(spear_n):
        parts.append(xform(build_single_frond(2.15, 0.16, 6, 0.62, lod), rx=-1.22, ry=s * (2.0 * math.pi / spear_n), translate=(0.0, 0.28, 0.0)))
    for i in range(upper_n):
        parts.append(xform(build_single_frond(3.45, 0.72, 8, 0.32, lod), rx=-0.56, ry=i * (2.0 * math.pi / upper_n) + 0.26, translate=(0.0, 0.18, 0.0)))
    for i in range(mid_n):
        parts.append(xform(build_single_frond(3.85, 1.22, 8, 0.08, lod), rx=-0.22, ry=i * (2.0 * math.pi / mid_n) + 0.58, translate=(0.0, 0.08, 0.0)))
    for i in range(lower_n):
        parts.append(xform(build_single_frond(3.95, 1.75, 8, -0.18, lod), rx=0.06, ry=i * (2.0 * math.pi / lower_n), translate=(0.0, -0.02, 0.0)))
    return merge_parts(parts)


def build_tbs_bunch(lod: int) -> MeshPart:
    parts = [
        organic_ellipsoid(0.24, 0.30, 0.24, rings=[8, 6, 5][lod], seg=[10, 8, 6][lod], col_fn=lambda t, th: rgba(212, 62, 18, 200), disp_fn=lambda ph, th: 1.0 + 0.15 * np.sin(6.0 * th) * np.cos(4.0 * ph), dyeable=True, gloss=0.72),
        tube_along_curve(np.array([[0.0, 0.25, 0.0], [0.05, 0.48, 0.04]], dtype=np.float32), np.array([0.088, 0.055], dtype=np.float32), seg=6 if lod == 0 else 4, color_fn=lambda t, th: rgba(168, 156, 72, 238), gloss=0.25),
    ]
    fruit_n = [42, 16, 0][lod]
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(fruit_n):
        y_n = 1.0 - 2.0 * (i + 0.5) / fruit_n
        rad = math.sqrt(max(0.0, 1.0 - y_n * y_n))
        ang = golden * i
        lobe = 1.0 + 0.14 * np.sin(3.0 * ang + y_n * 2.0)
        px, py, pz = math.cos(ang) * rad * 0.27 * lobe, y_n * 0.31, math.sin(ang) * rad * 0.27 * lobe
        rp = 0.5 + 0.5 * math.sin(i * 1.7)
        fruitlet = organic_ellipsoid(
            0.080, 0.092, 0.080, rings=5, seg=6,
            col_fn=lambda t, th, rpp=rp: rgba(int(232 + 22 * (1.0 - t)), int(62 + 104 * (1.0 - t) * rpp), int(16 + 18 * (1.0 - t)), int(182 + 70 * t)),
            dyeable=True, gloss=0.78,
        )
        parts.append(xform(fruitlet, ry=ang, rx=y_n * 0.6, translate=(px, py, pz)))
        if lod == 0 and i % 2 == 0:
            spine = tube_along_curve(np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.13]], dtype=np.float32), np.array([0.015, 0.002], dtype=np.float32), seg=4, color_fn=lambda t, th: rgba(132, 86, 40, 226))
            parts.append(xform(spine, ry=ang, rx=-y_n * 0.75, translate=(px * 1.08, py, pz * 1.08)))
    return merge_parts(parts)


def build_tropical_fern(lod: int) -> MeshPart:
    cnt = [9, 5, 3][lod]
    return merge_parts([xform(build_single_frond(1.02 + 0.18 * (i % 2), 0.36, 6, 0.38, lod), rx=-0.45 - 0.22 * (i % 2), ry=i * (2.0 * math.pi / cnt), scale=(0.68, 0.68, 0.68), translate=(0.0, 0.08, 0.0)) for i in range(cnt)])


def build_rock_boulder(lod: int) -> MeshPart:
    parts = []
    for k, (sx, sy, sz, ox, oz) in enumerate([(0.78, 0.54, 0.66, 0.0, 0.0), (0.46, 0.36, 0.44, 0.50, 0.24), (0.38, 0.28, 0.34, -0.40, 0.32)][:(3 if lod < 2 else 1)]):
        rock = organic_ellipsoid(
            sx, sy, sz, rings=[7, 5, 4][lod], seg=[9, 7, 5][lod],
            col_fn=lambda t, th: rgba(int(114 + 28 * t), int(96 + 30 * t), int(80 + 18 * t), int(172 + 80 * t)),
            disp_fn=lambda ph, th, kk=k: 1.0 + 0.17 * np.sin(3.0 * th + kk * 1.7) * np.cos(2.0 * ph) + 0.09 * np.cos(5.0 * th),
            gloss=0.22,
        )
        parts.append(xform(rock, ry=k * 1.1, translate=(ox, sy * 0.52, oz)))
    return merge_parts(parts)


def build_canter_truck_body(lod: int) -> MeshPart:
    """High-Craft Indonesian Mitsubishi Canter 'Oleng Sawit HD' with automotive clearcoat, Basuri horns, LED lights & detailed chassis!"""
    parts = []
    cab_col = rgba(246, 196, 34, 252)
    cab_dk = rgba(212, 158, 22, 242)
    steel = rgba(48, 54, 62, 238)
    steel_lt = rgba(138, 148, 158, 246)
    chrome = rgba(232, 240, 248, 255)
    glass = rgba(20, 34, 48, 252)
    wood_red = rgba(148, 66, 34, 242)
    wood_tan = rgba(190, 124, 58, 244)
    headlight = rgba(255, 252, 236, 255)
    amber = rgba(255, 168, 24, 255)
    taillight = rgba(248, 36, 36, 255)

    # Heavy I-beam twin chassis rails + hydraulic dump ram + stainless fuel tank + battery box
    for sx in (-0.46, 0.46):
        parts.append(xform(chamfer_box((0.13, 0.18, 5.02), 0.02, steel, gloss=0.45), translate=(sx, 0.58, -0.02)))
    if lod < 2:
        # Stainless cylindrical fuel tank (right) & battery box (left)
        tank = tube_along_curve(np.array([[-0.76, 0.56, -0.35], [-0.76, 0.56, 0.45]], dtype=np.float32), np.array([0.20, 0.20], dtype=np.float32), seg=10 if lod == 0 else 6, color_fn=lambda t, th: chrome, gloss=0.84)
        parts.append(tank)
        parts.append(xform(chamfer_box((0.40, 0.30, 0.62), 0.03, steel, gloss=0.42), translate=(0.74, 0.56, 0.05)))
        # Side safety yellow under-run bars
        for sx in (-0.94, 0.94):
            parts.append(xform(chamfer_box((0.05, 0.08, 1.15), 0.015, cab_col, dyeable=True, gloss=0.72), translate=(sx, 0.56, -0.10)))

    # Sculpted Automotive Lower & Upper Cab (gloss=0.78 automotive clearcoat!)
    parts.append(xform(chamfer_box((1.92, 0.68, 1.38), 0.08, cab_col, dyeable=True, gloss=0.78), translate=(0.0, 0.99, 1.70)))
    parts.append(xform(chamfer_box((1.84, 0.74, 1.22), 0.08, cab_col, taper_top=(0.91, 0.83), shear_z_top=-0.15, arch_top=0.045, dyeable=True, gloss=0.78), translate=(0.0, 1.67, 1.64)))
    # Flared black wheel arches over front & rear axles
    for sx in (-0.94, 0.94):
        parts.append(xform(chamfer_box((0.16, 0.22, 0.98), 0.04, steel, arch_top=0.08, gloss=0.50), translate=(sx, 0.72, 1.62)))
        parts.append(xform(chamfer_box((0.16, 0.22, 1.02), 0.04, steel, arch_top=0.08, gloss=0.50), translate=(sx, 0.72, -1.18)))

    # Custom Roof Crown Visor + 3 Chrome Telolet Basuri Airhorns + Glowing Amber Clearance Lights!
    parts.append(xform(chamfer_box((1.62, 0.20, 0.74), 0.05, cab_dk, taper_top=(0.82, 0.60), arch_top=0.06, dyeable=True, gloss=0.76), translate=(0.0, 2.13, 1.54)))
    parts.append(xform(chamfer_box((1.72, 0.10, 0.22), 0.03, chrome, gloss=0.86), rx=0.18, translate=(0.0, 2.02, 2.06)))
    for hx in (-0.52, 0.0, 0.52):
        parts.append(xform(chamfer_box((0.14, 0.06, 0.05), 0.015, amber, gloss=0.96), translate=(hx, 2.22, 1.88)))
    if lod < 2:
        for hx, hl in ((-0.42, 0.52), (0.42, 0.58)):
            horn = tube_along_curve(np.array([[hx, 2.24, 1.38], [hx, 2.26, 1.38 + hl]], dtype=np.float32), np.array([0.026, 0.072], dtype=np.float32), seg=7, color_fn=lambda t, th: chrome, gloss=0.88)
            parts.append(horn)

    # Glossy Reflective Windshield, Side Windows & Wipers
    parts.append(xform(chamfer_box((1.58, 0.47, 0.06), 0.02, glass, gloss=0.88), rx=-0.20, translate=(0.0, 1.68, 2.24)))
    for sx in (-1.0, 1.0):
        parts.append(xform(chamfer_box((0.06, 0.43, 0.75), 0.02, glass, shear_z_top=-0.10, gloss=0.88), translate=(sx * 0.93, 1.68, 1.66)))
        parts.append(xform(chamfer_box((0.04, 0.05, 0.16), 0.01, chrome, gloss=0.86), translate=(sx * 0.96, 1.24, 1.52)))

    # 3-Bar Chrome Grille + Glowing LED Headlights, Fog Lamps & Turn Signals
    parts.append(xform(chamfer_box((1.30, 0.26, 0.06), 0.02, rgba(24, 28, 34, 244), gloss=0.45), translate=(0.0, 0.92, 2.42)))
    for gy in (0.86, 0.93, 1.00):
        parts.append(xform(chamfer_box((1.22, 0.032, 0.07), 0.01, chrome, gloss=0.88), translate=(0.0, gy, 2.46)))
    for sx in (-1.0, 1.0):
        parts.append(xform(chamfer_box((0.30, 0.19, 0.06), 0.02, headlight, gloss=0.97), translate=(sx * 0.72, 0.92, 2.43)))
        parts.append(xform(chamfer_box((0.12, 0.19, 0.06), 0.02, amber, gloss=0.96), translate=(sx * 0.91, 0.92, 2.39)))
        parts.append(xform(chamfer_box((0.16, 0.09, 0.06), 0.02, amber, gloss=0.96), translate=(sx * 0.68, 0.58, 2.59)))

    # Heavy Offroad Bumper + Twin-Tube Chrome Bullbar + Rear LED Taillights
    parts.append(xform(chamfer_box((2.00, 0.24, 0.20), 0.035, steel, gloss=0.52), translate=(0.0, 0.58, 2.50)))
    for sx in (-0.68, 0.68):
        parts.append(xform(chamfer_box((0.30, 0.12, 0.06), 0.02, taillight, gloss=0.96), translate=(sx, 0.62, -2.52)))
    if lod < 2:
        bull_pts = np.array([[-0.82, 0.60, 2.60], [-0.72, 1.12, 2.64], [0.72, 1.12, 2.64], [0.82, 0.60, 2.60]], dtype=np.float32)
        parts.append(tube_along_curve(bull_pts, np.full(4, 0.038, dtype=np.float32), seg=6, color_fn=lambda t, th: chrome, gloss=0.88))
        for sx in (-1.0, 1.0):
            arm = np.array([[sx * 0.93, 1.84, 2.02], [sx * 1.14, 1.82, 2.08], [sx * 1.14, 1.48, 2.06]], dtype=np.float32)
            parts.append(tube_along_curve(arm, np.full(3, 0.022, dtype=np.float32), seg=5, color_fn=lambda t, th: chrome, gloss=0.85))
            parts.append(xform(chamfer_box((0.08, 0.28, 0.16), 0.02, rgba(30, 34, 40, 250), gloss=0.70), translate=(sx * 1.15, 1.66, 2.08)))
        exh = np.array([[0.74, 0.62, 0.94], [0.78, 2.24, 0.94], [0.85, 2.44, 0.86]], dtype=np.float32)
        parts.append(tube_along_curve(exh, np.array([0.052, 0.048, 0.042], dtype=np.float32), seg=8, color_fn=lambda t, th: chrome, gloss=0.88))

    # Slatted Hardwood 'Bak Tinggi Sawit' Dump Bed + Headache Rack
    parts.append(xform(chamfer_box((2.06, 0.15, 3.28), 0.03, steel_lt, gloss=0.50), translate=(0.0, 0.74, -0.79)))
    plank_rows = [5, 3, 2][lod]
    for plank_i in range(plank_rows):
        py = 0.92 + plank_i * (0.90 / max(1, plank_rows - 1))
        h_p = 0.15 if lod == 0 else 0.28
        c_pl = wood_red if plank_i % 2 == 0 else wood_tan
        for sx in (-0.99, 0.99):
            parts.append(xform(chamfer_box((0.065, h_p, 3.20), 0.015, c_pl, gloss=0.38), translate=(sx, py, -0.79)))
        parts.append(xform(chamfer_box((1.94, h_p, 0.065), 0.015, c_pl, gloss=0.38), translate=(0.0, py, 0.80)))
        parts.append(xform(chamfer_box((1.94, h_p, 0.065), 0.015, c_pl, gloss=0.38), translate=(0.0, py, -2.38)))

    if lod < 2:
        for sz in (-2.30, -1.52, -0.76, 0.0, 0.74):
            for sx in (-1.05, 1.05):
                parts.append(xform(chamfer_box((0.065, 1.14, 0.075), 0.015, steel, gloss=0.55), translate=(sx, 1.36, sz)))
    return merge_parts(parts)


def build_truck_wheel(lod: int) -> MeshPart:
    seg = [22, 12, 8][lod]
    thetas = np.linspace(0.0, 2.0 * math.pi, seg, endpoint=False, dtype=np.float32)
    prof = [
        (-0.22, 0.11, rgba(210, 218, 228, 255)),
        (-0.17, 0.25, rgba(242, 192, 34, 248)),
        (-0.20, 0.36, rgba(32, 34, 38, 238)),
        (-0.15, 0.47, rgba(24, 26, 30, 252)),
        (0.00, 0.485, rgba(22, 24, 28, 255)),
        (0.15, 0.47, rgba(24, 26, 30, 252)),
        (0.20, 0.36, rgba(32, 34, 38, 238)),
        (0.17, 0.25, rgba(242, 192, 34, 248)),
        (0.22, 0.11, rgba(210, 218, 228, 255)),
    ]
    stations = []
    for si, (xx, rr, c) in enumerate(prof):
        lugs = 1.0 + (0.048 * np.sign(np.sin(11.0 * thetas)) if (lod == 0 and 3 <= si <= 5) else 0.0)
        ring = np.stack([np.full_like(thetas, xx), np.sin(thetas) * rr * lugs, np.cos(thetas) * rr * lugs], axis=1)
        stations.append((ring, c, si / (len(prof) - 1)))
    return loft_profile(stations, cap_start=True, cap_end=True, gloss=0.44)


def build_truck_cargo_heap(lod: int) -> MeshPart:
    parts = []
    positions = [
        (-0.54, 0.18, -1.65, 0.2), (0.52, 0.18, -1.60, 1.3), (0.0, 0.22, -1.10, 2.4),
        (-0.56, 0.18, -0.55, 0.9), (0.54, 0.18, -0.50, 2.9), (0.0, 0.22, 0.05, 1.7),
        (-0.50, 0.18, 0.48, 2.1), (0.50, 0.18, 0.45, 0.5),
        (-0.30, 0.56, -1.25, 1.1), (0.32, 0.58, -0.80, 2.6), (-0.26, 0.56, -0.15, 0.4), (0.24, 0.54, 0.28, 1.9),
        (0.0, 0.88, -0.65, 0.8), (0.04, 0.84, -0.05, 2.2),
    ]
    mini_tbs = organic_ellipsoid(
        0.36, 0.30, 0.40, rings=[6, 4, 4][lod], seg=[8, 6, 5][lod],
        col_fn=lambda t, th: rgba(int(232 + 22 * (1.0 - t)), int(68 + 90 * (1.0 - t)), 20, int(184 + 70 * t)),
        disp_fn=lambda ph, th: 1.0 + 0.16 * np.sin(6.0 * th) * np.cos(4.0 * ph),
        gloss=0.72,
    )
    for px, py, pz, ry in positions[:([14, 10, 6][lod])]:
        parts.append(xform(mini_tbs, ry=ry, translate=(px, py, pz)))
    return merge_parts(parts)


def build_angkong_cart(lod: int) -> MeshPart:
    parts = [xform(chamfer_box((0.78, 0.44, 1.04), 0.08, rgba(30, 152, 174, 248), taper_top=(1.32, 1.28), shear_z_top=0.14, gloss=0.68), translate=(0.0, 0.58, 0.08))]
    for sx in (-1.0, 1.0):
        frame = np.array([[sx * 0.14, 0.32, 0.72], [sx * 0.30, 0.36, -0.25], [sx * 0.35, 0.68, -0.94]], dtype=np.float32)
        parts.append(tube_along_curve(frame, np.full(3, 0.025, dtype=np.float32), seg=5, color_fn=lambda t, th: rgba(60, 66, 74, 242), gloss=0.55))
        leg = np.array([[sx * 0.30, 0.36, -0.32], [sx * 0.32, 0.04, -0.36], [sx * 0.30, 0.36, -0.44]], dtype=np.float32)
        parts.append(tube_along_curve(leg, np.full(3, 0.019, dtype=np.float32), seg=4, color_fn=lambda t, th: rgba(60, 66, 74, 242)))
    parts.append(xform(build_truck_wheel(lod), scale=(0.60, 0.60, 0.60), translate=(0.0, 0.29, 0.78)))
    for ox, oz in ((-0.15, 0.05), (0.16, 0.08), (0.0, 0.28), (0.0, 0.06)):
        parts.append(xform(organic_ellipsoid(0.21, 0.18, 0.23, 8, 14, col_fn=lambda t, th: rgba(236 + int(18 * (1.0 - t)), 74 + int(42 * (1.0 - t)), 20, int(190 + 62 * t)), disp_fn=lambda ph, th: 1.0 + 0.08 * np.sin(6.0 * th) * np.cos(4.0 * ph), gloss=0.72), translate=(ox, 0.86, oz)))
    return merge_parts(parts)


def build_pks_factory(lod: int) -> MeshPart:
    """Crisp Industrial Pabrik Kelapa Sawit (PKS) Complex with silos, boiler stacks, clerestory windows & floodlights!"""
    parts = []
    wall = rgba(224, 228, 234, 246)
    wall_band = rgba(44, 134, 88, 246)
    roof_green = rgba(28, 118, 76, 250)
    steel = rgba(52, 58, 68, 238)
    accent = rgba(244, 184, 28, 252)
    flood = rgba(255, 244, 204, 255)

    # Concrete plinth foundation + Main industrial hall + emerald accent band
    parts.append(xform(chamfer_box((11.2, 0.45, 9.0), 0.06, rgba(132, 138, 144, 230), gloss=0.20), translate=(0.0, 0.22, 0.0)))
    parts.append(xform(chamfer_box((10.6, 5.2, 8.4), 0.10, wall, gloss=0.35), translate=(0.0, 2.95, 0.0)))
    parts.append(xform(chamfer_box((10.74, 0.65, 8.54), 0.06, wall_band, gloss=0.52), translate=(0.0, 4.65, 0.0)))
    parts.append(xform(chamfer_box((11.5, 1.55, 9.3), 0.09, roof_green, taper_top=(0.06, 0.98), gloss=0.58), translate=(0.0, 6.28, 0.0)))
    parts.append(xform(chamfer_box((5.2, 1.15, 6.8), 0.08, wall, gloss=0.35), translate=(0.0, 7.20, 0.0)))
    parts.append(xform(chamfer_box((5.8, 0.68, 7.2), 0.07, roof_green, taper_top=(0.10, 0.98), gloss=0.58), translate=(0.0, 8.05, 0.0)))

    # Structural I-columns + glowing industrial floodlights on front facade
    for sx in (-5.36, -2.68, 2.68, 5.36):
        for sz in (-4.26, 4.26):
            parts.append(xform(chamfer_box((0.28, 5.25, 0.28), 0.03, steel, gloss=0.52), translate=(sx, 2.85, sz)))
    for lx in (-3.6, 0.0, 3.6):
        parts.append(xform(chamfer_box((0.55, 0.24, 0.14), 0.02, flood, gloss=0.97), translate=(lx, 4.65, 4.34)))

    # Loading bay portal + hazard canopy + TBS hopper chute
    parts.append(xform(chamfer_box((3.8, 3.5, 0.24), 0.04, rgba(20, 24, 30, 220), gloss=0.40), translate=(0.0, 1.85, 4.32)))
    parts.append(xform(chamfer_box((4.9, 0.30, 2.7), 0.05, accent, gloss=0.68), rx=0.06, translate=(0.0, 3.95, 5.40)))

    # Twin Tall Red-White Boiler Chimneys + 3 Stainless CPO Storage Silos + Catwalk
    for cx in (-3.2, -1.0):
        ch_pts = np.array([[cx, 5.6, -2.2], [cx, 9.8, -2.2], [cx, 14.0, -2.2]], dtype=np.float32)
        parts.append(tube_along_curve(ch_pts, np.array([0.64, 0.52, 0.40], dtype=np.float32), seg=[14, 8, 6][lod], color_fn=lambda t, th: rgba(204, 68, 48, 250) if (int(t * 9) % 2 == 0) else rgba(242, 244, 248, 252), gloss=0.50))
    for tx, tz in ((7.3, -2.3), (7.3, 1.9), (-7.3, 0.2)):
        silo = np.array([[tx, 0.0, tz], [tx, 5.0, tz], [tx, 5.8, tz]], dtype=np.float32)
        parts.append(tube_along_curve(silo, np.array([1.75, 1.75, 0.14], dtype=np.float32), seg=[16, 10, 6][lod], color_fn=lambda t, th: rgba(206, 214, 224, 248), gloss=0.78))
    if lod < 2:
        parts.append(xform(chamfer_box((3.2, 0.18, 0.65), 0.02, accent, gloss=0.60), translate=(5.6, 4.6, -0.2)))
    return merge_parts(parts)


def build_weighbridge_ram(lod: int) -> MeshPart:
    parts = []
    steel = rgba(52, 60, 70, 242)
    yellow = rgba(246, 188, 24, 252)
    led_green = rgba(46, 255, 138, 255)

    parts.append(xform(chamfer_box((4.5, 0.28, 7.6), 0.04, steel, gloss=0.58), translate=(0.0, 0.14, 0.0)))
    for sz, tilt in ((4.65, 0.12), (-4.65, -0.12)):
        parts.append(xform(chamfer_box((4.3, 0.18, 1.7), 0.04, yellow, gloss=0.64), rx=tilt, translate=(0.0, 0.08, sz)))
    for sx in (-2.12, 2.12):
        rail = np.array([[sx, 0.28, -3.6], [sx, 0.78, -3.1], [sx, 0.78, 3.1], [sx, 0.28, 3.6]], dtype=np.float32)
        parts.append(tube_along_curve(rail, np.full(4, 0.085, dtype=np.float32), seg=6, color_fn=lambda t, th: yellow, gloss=0.68))
        parts.append(xform(chamfer_box((0.28, 4.3, 0.28), 0.03, steel, gloss=0.58), translate=(sx, 2.25, 0.0)))
    # Digital Gantry Sign + Operator Booth beside weighbridge!
    parts.append(xform(chamfer_box((4.9, 0.96, 0.42), 0.05, rgba(18, 22, 28, 252), gloss=0.50), translate=(0.0, 4.40, 0.0)))
    for side_z in (0.25, -0.25):
        parts.append(xform(chamfer_box((4.2, 0.24, 0.08), 0.02, led_green, gloss=0.98), translate=(0.0, 4.40, side_z)))
    if lod < 2:
        parts.append(xform(chamfer_box((1.55, 2.25, 1.65), 0.05, rgba(226, 232, 238, 246), gloss=0.45), translate=(3.35, 1.15, 0.0)))
        parts.append(xform(chamfer_box((1.85, 0.22, 1.95), 0.04, rgba(30, 126, 82, 250), gloss=0.55), translate=(3.35, 2.38, 0.0)))
        parts.append(xform(chamfer_box((0.08, 0.78, 1.10), 0.02, rgba(24, 42, 58, 252), gloss=0.88), translate=(2.55, 1.38, 0.0)))
    return merge_parts(parts)


def build_mandor_post(lod: int) -> MeshPart:
    parts = []
    timber = rgba(132, 82, 44, 238)
    wall_wood = rgba(176, 124, 72, 244)
    for sx in (-1.55, 1.55):
        for sz in (-1.55, 1.55):
            parts.append(xform(chamfer_box((0.22, 1.12, 0.22), 0.03, timber), translate=(sx, 0.56, sz)))
    parts.append(xform(chamfer_box((3.7, 0.20, 3.9), 0.04, timber), translate=(0.0, 1.06, 0.0)))
    parts.append(xform(chamfer_box((3.2, 2.15, 2.8), 0.05, wall_wood), translate=(0.0, 2.20, -0.35)))
    parts.append(xform(chamfer_box((4.2, 0.96, 4.6), 0.06, rgba(162, 68, 46, 248), taper_top=(0.08, 0.98), gloss=0.48), translate=(0.0, 3.72, 0.0)))
    # Warm glowing porch lantern + steps + blue water drums
    parts.append(xform(chamfer_box((0.22, 0.28, 0.22), 0.03, rgba(255, 214, 112, 255), gloss=0.97), translate=(1.25, 2.85, 1.35)))
    for step_i in range(3):
        parts.append(xform(chamfer_box((1.25, 0.16, 0.36), 0.03, timber), translate=(0.0, 0.26 + step_i * 0.30, 2.35 - step_i * 0.30)))
    if lod < 2:
        for dx, dz in ((-2.25, 0.8), (-2.25, -0.2)):
            drum = tube_along_curve(np.array([[dx, 0.0, dz], [dx, 0.88, dz]], dtype=np.float32), np.array([0.30, 0.30], dtype=np.float32), seg=10, color_fn=lambda t, th: rgba(34, 108, 196, 246), gloss=0.68)
            parts.append(drum)
    return merge_parts(parts)


def build_wooden_bridge(lod: int) -> MeshPart:
    parts = []
    log_col, plank_col = rgba(112, 70, 38, 234), rgba(164, 114, 64, 244)
    n = [9, 6, 4][lod]
    zs = np.linspace(-4.2, 4.2, n, dtype=np.float32)
    arch_y = 0.52 * (1.0 - (zs / 4.2) ** 2)
    for sx in (-1.45, 0.0, 1.45):
        parts.append(tube_along_curve(np.stack([np.full_like(zs, sx), arch_y + 0.10, zs], axis=1), np.full(n, 0.16, dtype=np.float32), seg=6, color_fn=lambda t, th: log_col))
    planks = [15, 9, 5][lod]
    for pi in range(planks):
        zz = -3.9 + pi * (7.8 / max(1, planks - 1))
        yy = 0.52 * (1.0 - (zz / 4.2) ** 2) + 0.31
        parts.append(xform(chamfer_box((3.6, 0.11, 7.8 / planks * 0.85), 0.02, plank_col), translate=(0.0, yy, zz)))
    for sx in (-1.70, 1.70):
        parts.append(tube_along_curve(np.stack([np.full_like(zs, sx), arch_y + 1.08, zs], axis=1), np.full(n, 0.065, dtype=np.float32), seg=5, color_fn=lambda t, th: log_col))
        if lod < 2:
            for pz in (-3.6, -1.8, 0.0, 1.8, 3.6):
                py_b = 0.52 * (1.0 - (pz / 4.2) ** 2)
                parts.append(xform(chamfer_box((0.11, 0.85, 0.11), 0.02, log_col), translate=(sx, py_b + 0.68, pz)))
    return merge_parts(parts)


def build_celeng_boar(lod: int) -> MeshPart:
    parts = []
    sg = [16, 10, 6][lod]
    spine = np.array([[0.0, 0.56, -0.64], [0.0, 0.70, -0.22], [0.0, 0.78, 0.18], [0.0, 0.62, 0.54], [0.0, 0.48, 0.84], [0.0, 0.43, 1.02]], dtype=np.float32)
    parts.append(tube_along_curve(
        spine, np.array([0.22, 0.35, 0.41, 0.32, 0.18, 0.11], dtype=np.float32), seg=sg,
        color_fn=lambda t, th: rgba(int(64 + 34 * t), int(46 + 22 * t), int(34 + 12 * t), int(214 + 40 * t)),
        profile_mod=lambda t, th: 1.0 + 0.14 * np.maximum(0.0, np.sin(th)),
        gloss=0.36,
    ))
    # Snout disc + spiky dark dorsal mane + tail
    parts.append(xform(chamfer_box((0.20, 0.15, 0.07), 0.03, rgba(168, 114, 104, 248), gloss=0.52), translate=(0.0, 0.43, 1.05)))
    for mi in range(5 if lod < 2 else 3):
        mz = -0.34 + mi * 0.19
        parts.append(xform(chamfer_box((0.07, 0.19, 0.20), 0.02, rgba(28, 20, 18, 246), taper_top=(0.18, 0.55)), rx=-0.24, translate=(0.0, 1.08 - abs(mi - 2) * 0.03, mz)))
    tail = np.array([[0.0, 0.62, -0.62], [0.0, 0.74, -0.78], [0.04, 0.86, -0.74]], dtype=np.float32)
    parts.append(tube_along_curve(tail, np.array([0.045, 0.028, 0.014], dtype=np.float32), seg=6, color_fn=lambda t, th: rgba(42, 30, 24, 240)))
    for sx in (-1.0, 1.0):
        tusk = np.array([[sx * 0.11, 0.44, 0.84], [sx * 0.25, 0.55, 0.98], [sx * 0.20, 0.72, 0.95]], dtype=np.float32)
        parts.append(tube_along_curve(tusk, np.array([0.038, 0.026, 0.005], dtype=np.float32), seg=8, color_fn=lambda t, th: rgba(250, 245, 228, 255), gloss=0.78))
        # Fierce glowing amber-red eyes & pointed ears!
        parts.append(xform(chamfer_box((0.045, 0.045, 0.055), 0.01, rgba(255, 96, 28, 255), gloss=0.97), translate=(sx * 0.22, 0.65, 0.68)))
        parts.append(xform(chamfer_box((0.09, 0.18, 0.13), 0.02, rgba(58, 42, 34, 244), taper_top=(0.30, 0.45)), rz=-sx * 0.42, translate=(sx * 0.20, 0.88, 0.46)))
        for sz in (-0.42, 0.36):
            leg = np.array([[sx * 0.21, 0.54, sz], [sx * 0.21, 0.27, sz - 0.04], [sx * 0.21, 0.02, sz + 0.02]], dtype=np.float32)
            parts.append(tube_along_curve(leg, np.array([0.105, 0.072, 0.054], dtype=np.float32), seg=10 if lod == 0 else 6, color_fn=lambda t, th: rgba(48, 34, 28, 236)))
    return merge_parts(parts)


def build_char_torso_head(lod: int) -> MeshPart:
    sg = [18, 12, 8][lod]
    parts = [
        # Tactical utility belt + side pouch + golden buckle
        xform(chamfer_box((0.37, 0.10, 0.26), 0.04, rgba(44, 38, 34, 244), gloss=0.48), translate=(0.0, 0.04, 0.0)),
        xform(chamfer_box((0.10, 0.095, 0.045), 0.015, rgba(250, 202, 48, 255), gloss=0.86), translate=(0.0, 0.04, 0.15)),
        # Athletic V-taper jersey/jacket torso (dyeable=True, silky smooth 18-seg!)
        tube_along_curve(
            np.array([[0.0, 0.08, 0.0], [0.0, 0.24, 0.01], [0.0, 0.42, 0.02], [0.0, 0.55, 0.0]], dtype=np.float32),
            np.array([0.168, 0.202, 0.244, 0.162], dtype=np.float32), seg=sg,
            color_fn=lambda t, th: rgba(int(232 + 22 * t), int(232 + 22 * t), int(232 + 22 * t), int(212 + 42 * t)),
            profile_mod=lambda t, th: 1.0 + 0.22 * np.cos(2.0 * th + math.pi),
            dyeable=True, gloss=0.42,
        ),
        tube_along_curve(np.array([[0.0, 0.51, 0.01], [0.0, 0.56, 0.01]], dtype=np.float32), np.array([0.135, 0.105], dtype=np.float32), seg=14, color_fn=lambda t, th: rgba(34, 40, 48, 246), gloss=0.45),
    ]
    skin = rgba(226, 174, 134, 250)
    parts.append(tube_along_curve(np.array([[0.0, 0.54, 0.0], [0.0, 0.65, 0.01]], dtype=np.float32), np.array([0.078, 0.072], dtype=np.float32), seg=12, color_fn=lambda t, th: skin, gloss=0.30))
    head = organic_ellipsoid(0.168, 0.198, 0.178, rings=[12, 8, 6][lod], seg=sg, col_fn=lambda t, th: skin, disp_fn=lambda ph, th: 1.0 - 0.07 * np.maximum(0.0, -np.sin(ph)) * np.cos(th), gloss=0.32)
    parts.append(xform(head, translate=(0.0, 0.79, 0.02)))
    if lod < 2:
        parts.append(xform(chamfer_box((0.042, 0.068, 0.055), 0.015, skin, taper_top=(0.65, 0.5), gloss=0.32), translate=(0.0, 0.78, 0.208)))
        for sx in (-1.0, 1.0):
            parts.append(xform(chamfer_box((0.04, 0.075, 0.05), 0.015, skin, gloss=0.30), translate=(sx * 0.172, 0.79, 0.02)))
        parts.append(xform(chamfer_box((0.245, 0.058, 0.045), 0.015, rgba(18, 28, 44, 255), gloss=0.90), translate=(0.0, 0.818, 0.194)))
    hair_cap = organic_ellipsoid(0.188, 0.188, 0.198, rings=8, seg=sg, col_fn=lambda t, th: rgba(30, 24, 22, 248), phi_range=(math.pi * 0.055, math.pi * 0.485), gloss=0.46)
    parts.append(xform(hair_cap, rx=-0.16, translate=(0.0, 0.812, -0.005)))
    return merge_parts(parts)


def build_char_arm(lod: int) -> MeshPart:
    sg = [14, 9, 6][lod]
    return merge_parts([
        tube_along_curve(np.array([[0.0, 0.02, 0.0], [0.0, -0.19, 0.01]], dtype=np.float32), np.array([0.084, 0.070], dtype=np.float32), seg=sg, color_fn=lambda t, th: rgba(244, 244, 244, 244), dyeable=True, gloss=0.40),
        tube_along_curve(np.array([[0.0, -0.19, 0.01], [0.0, -0.34, 0.04], [0.0, -0.46, 0.07]], dtype=np.float32), np.array([0.062, 0.054, 0.046], dtype=np.float32), seg=sg, color_fn=lambda t, th: rgba(222, 170, 130, 248), gloss=0.30),
        xform(chamfer_box((0.098, 0.115, 0.11), 0.025, rgba(42, 48, 56, 250), gloss=0.48), translate=(0.0, -0.51, 0.08)),
    ])


def build_char_leg(lod: int) -> MeshPart:
    sg = [14, 9, 6][lod]
    return merge_parts([
        tube_along_curve(np.array([[0.0, 0.0, 0.0], [0.0, -0.26, 0.02], [0.0, -0.49, 0.0]], dtype=np.float32), np.array([0.102, 0.086, 0.076], dtype=np.float32), seg=sg, color_fn=lambda t, th: rgba(58, 66, 78, 240), gloss=0.34),
        tube_along_curve(np.array([[0.0, -0.49, 0.0], [0.0, -0.79, -0.01]], dtype=np.float32), np.array([0.088, 0.078], dtype=np.float32), seg=sg, color_fn=lambda t, th: rgba(38, 108, 68, 246) if t > 0.18 else rgba(244, 196, 36, 252), gloss=0.62),
        xform(chamfer_box((0.155, 0.125, 0.28), 0.03, rgba(28, 32, 36, 250), gloss=0.52), translate=(0.0, -0.85, 0.05)),
    ])


def build_hat_caping(lod: int) -> MeshPart:
    return tube_along_curve(
        np.array([[0.0, 0.0, 0.0], [0.0, 0.10, 0.0], [0.0, 0.20, 0.0], [0.0, 0.29, 0.0]], dtype=np.float32),
        np.array([0.43, 0.28, 0.13, 0.015], dtype=np.float32), seg=[22, 12, 8][lod],
        color_fn=lambda t, th: rgba(232, 54, 38, 252) if t < 0.09 else rgba(int(226 - 26 * t), int(184 - 22 * t), int(108 - 14 * t), int(224 + 30 * t)),
        profile_mod=lambda t, th: 1.0 + 0.025 * np.cos(12.0 * th),
        gloss=0.42,
    )


def build_hat_safety(lod: int) -> MeshPart:
    return merge_parts([
        xform(organic_ellipsoid(0.21, 0.16, 0.24, rings=[7, 5, 4][lod], seg=[14, 10, 7][lod], col_fn=lambda t, th: rgba(250, 198, 26, 252), phi_range=(-0.15, math.pi * 0.485), gloss=0.78), translate=(0.0, 0.05, 0.0)),
        xform(chamfer_box((0.065, 0.085, 0.37), 0.02, rgba(255, 218, 56, 255), gloss=0.80), translate=(0.0, 0.19, 0.0)),
        xform(chamfer_box((0.35, 0.035, 0.15), 0.015, rgba(236, 178, 18, 248), gloss=0.75), rx=0.14, translate=(0.0, 0.02, 0.21)),
        xform(chamfer_box((0.09, 0.07, 0.05), 0.015, rgba(255, 252, 224, 255), gloss=0.97), translate=(0.0, 0.13, 0.23)),
    ])


def build_hat_headband(lod: int) -> MeshPart:
    parts = [tube_along_curve(np.array([[0.0, -0.02, 0.01], [0.0, 0.055, 0.01]], dtype=np.float32), np.array([0.194, 0.194], dtype=np.float32), seg=[16, 10, 7][lod], color_fn=lambda t, th: rgba(232, 38, 42, 250), gloss=0.45)]
    parts.append(xform(chamfer_box((0.11, 0.065, 0.03), 0.01, rgba(246, 202, 48, 255), gloss=0.88), translate=(0.0, 0.02, 0.205)))
    for sx in (-1.0, 1.0):
        tail = np.array([[sx * 0.05, 0.02, -0.20], [sx * 0.14, -0.10, -0.36], [sx * 0.20, -0.28, -0.50]], dtype=np.float32)
        parts.append(tube_along_curve(tail, np.array([0.040, 0.050, 0.018], dtype=np.float32), seg=5, color_fn=lambda t, th: rgba(240, 48, 52, 252), gloss=0.45))
    return merge_parts(parts)


def build_hat_cowboy(lod: int) -> MeshPart:
    seg = [18, 12, 8][lod]
    th = np.linspace(0, 2 * math.pi, seg, endpoint=False, dtype=np.float32)
    curl = 0.08 * (np.cos(th) ** 2)
    brim = loft_profile([
        (np.stack([np.cos(th) * 0.16, np.zeros_like(th), np.sin(th) * 0.19], axis=1), rgba(118, 72, 42, 242), 0.0),
        (np.stack([np.cos(th) * 0.37, curl, np.sin(th) * 0.41], axis=1), rgba(138, 86, 48, 252), 1.0),
    ], cap_start=False, cap_end=False, gloss=0.45)
    return merge_parts([
        brim,
        xform(chamfer_box((0.29, 0.175, 0.34), 0.06, rgba(126, 78, 44, 248), taper_top=(0.76, 0.80), gloss=0.45), translate=(0.0, 0.10, 0.0)),
        xform(chamfer_box((0.31, 0.038, 0.36), 0.05, rgba(250, 202, 48, 255), gloss=0.86), translate=(0.0, 0.03, 0.0)),
    ])


def build_hat_crown_gold(lod: int) -> MeshPart:
    gold, gem = rgba(255, 212, 48, 255), rgba(32, 250, 152, 255)
    parts = [tube_along_curve(np.array([[0.0, 0.0, 0.0], [0.0, 0.09, 0.0]], dtype=np.float32), np.array([0.192, 0.208], dtype=np.float32), seg=[16, 10, 8][lod], color_fn=lambda t, th: gold, gloss=0.88)]
    spikes = [8, 6, 4][lod]
    for i in range(spikes):
        ang = i * (2.0 * math.pi / spikes)
        h = 0.23 if i % 2 == 0 else 0.155
        parts.append(xform(chamfer_box((0.068, h, 0.038), 0.012, gold, taper_top=(0.14, 0.4), gloss=0.88), ry=ang, translate=(math.sin(ang) * 0.200, 0.09 + h * 0.42, math.cos(ang) * 0.200)))
        if lod < 2 and i % 2 == 0:
            parts.append(xform(chamfer_box((0.048, 0.058, 0.035), 0.01, gem, gloss=0.97), ry=ang, translate=(math.sin(ang) * 0.224, 0.048, math.cos(ang) * 0.224)))
    return merge_parts(parts)


def build_back_basket(lod: int) -> MeshPart:
    pts = np.array([[0.0, -0.22, -0.10], [0.0, 0.02, -0.13], [0.0, 0.25, -0.16]], dtype=np.float32)
    parts = [tube_along_curve(pts, np.array([0.145, 0.195, 0.245], dtype=np.float32), seg=[14, 9, 6][lod], color_fn=lambda t, th: rgba(int(184 + 34 * ((int(t * 10)) % 2)), int(140 + 24 * t), 72, 244), gloss=0.34)]
    for ox, oz in ((-0.08, -0.13), (0.09, -0.15), (0.0, -0.22)):
        parts.append(xform(organic_ellipsoid(0.095, 0.095, 0.095, 5, 6, col_fn=lambda t, th: rgba(242, 88, 22, 250), gloss=0.74), translate=(ox, 0.27, oz)))
    return merge_parts(parts)


def build_back_pack(lod: int) -> MeshPart:
    return merge_parts([
        xform(chamfer_box((0.31, 0.39, 0.18), 0.04, rgba(48, 72, 56, 244), gloss=0.52), translate=(0.0, 0.0, -0.09)),
        xform(chamfer_box((0.24, 0.18, 0.07), 0.02, rgba(248, 188, 28, 252), gloss=0.76), translate=(0.0, -0.05, -0.21)),
        tube_along_curve(np.array([[0.11, 0.18, -0.10], [0.14, 0.66, -0.16]], dtype=np.float32), np.array([0.016, 0.005], dtype=np.float32), seg=5, color_fn=lambda t, th: rgba(224, 230, 238, 252), gloss=0.85),
    ])


def build_back_cape(lod: int) -> MeshPart:
    stations = []
    xs = np.linspace(-0.23, 0.23, [9, 6, 4][lod], dtype=np.float32)
    for row_i, (yy, zz, spread, fold) in enumerate([(0.18, -0.04, 0.9, 0.01), (-0.08, -0.10, 1.16, 0.025), (-0.36, -0.18, 1.48, 0.045), (-0.68, -0.27, 1.76, 0.065)]):
        ring = [[x * spread, yy, zz + math.sin(x * 26.0) * fold] for x in xs] + [[x * spread, yy, zz + math.sin(x * 26.0) * fold - 0.024] for x in reversed(xs)]
        stations.append((np.asarray(ring, dtype=np.float32), rgba(248, 198, 42, 255) if row_i == 0 else rgba(228, 36, 48, 248), row_i / 3.0))
    return loft_profile(stations, cap_start=True, cap_end=True, gloss=0.52)


def build_back_wings_gold(lod: int) -> MeshPart:
    """Mythic Sultan Golden Phoenix Wings fanning cleanly along +/-X behind the shoulders — ZERO chest overlap!"""
    parts = [
        # Glowing emerald-set golden power core emblem centered between shoulder blades
        xform(chamfer_box((0.20, 0.24, 0.07), 0.025, rgba(255, 208, 48, 255), gloss=0.90), translate=(0.0, 0.14, -0.08)),
        xform(chamfer_box((0.09, 0.12, 0.05), 0.015, rgba(34, 252, 154, 255), gloss=0.98), translate=(0.0, 0.14, -0.11)),
    ]
    feather_n = [7, 5, 4][lod]
    for sx in (-1.0, 1.0):
        # Sweeping golden wing spar rising outward & upward behind back
        spar = np.array([
            [sx * 0.08, 0.14, -0.09],
            [sx * 0.34, 0.42, -0.15],
            [sx * 0.68, 0.56, -0.22],
            [sx * 0.98, 0.44, -0.28],
        ], dtype=np.float32)
        parts.append(tube_along_curve(spar, np.array([0.042, 0.036, 0.028, 0.015], dtype=np.float32), seg=8, color_fn=lambda t, th: rgba(255, 214, 56, 255), gloss=0.90))
        for fi in range(feather_n):
            frac = fi / max(1, feather_n - 1)
            bx = sx * (0.18 + 0.72 * frac)
            by = 0.24 + 0.28 * math.sin(frac * math.pi * 0.85)
            bz = -0.12 - 0.14 * frac
            flen = 0.72 - 0.18 * (1.0 - frac) + 0.14 * math.sin(frac * math.pi)
            tilt_z = sx * (0.42 + 0.82 * frac)
            col_f = rgba(255, int(224 - 46 * frac), int(64 - 28 * frac), 255)
            blade = chamfer_box((0.105, flen, 0.028), 0.010, col_f, taper_top=(0.18, 0.45), gloss=0.92)
            parts.append(xform(blade, rz=-tilt_z, rx=-0.12, translate=(bx + sx * flen * 0.34, by - flen * 0.32, bz)))
    return merge_parts(parts)


def build_tool_egrek(lod: int) -> MeshPart:
    return merge_parts([
        tube_along_curve(np.array([[0.0, -0.22, 0.0], [0.0, 1.05, 0.0], [0.0, 2.05, 0.0]], dtype=np.float32), np.array([0.029, 0.024, 0.019], dtype=np.float32), seg=6, color_fn=lambda t, th: rgba(224, 50, 40, 250) if t < 0.22 else rgba(214, 224, 234, 250), gloss=0.72),
        xform(chamfer_box((0.078, 0.115, 0.078), 0.02, rgba(242, 186, 28, 255), gloss=0.84), translate=(0.0, 2.04, 0.0)),
        tube_along_curve(
            np.array([[0.0, 2.06, 0.0], [0.02, 2.27, 0.09], [0.02, 2.46, 0.02], [0.0, 2.54, -0.19], [-0.01, 2.45, -0.36]], dtype=np.float32),
            np.array([0.030, 0.048, 0.042, 0.028, 0.004], dtype=np.float32), seg=6,
            color_fn=lambda t, th: rgba(240, 246, 255, 255),
            profile_mod=lambda t, th: np.where(np.abs(np.cos(th)) > 0.5, 0.22, 1.42),
            gloss=0.88,
        ),
    ])


def build_tool_dodos(lod: int) -> MeshPart:
    return merge_parts([
        tube_along_curve(np.array([[0.0, -0.20, 0.0], [0.0, 0.95, 0.0]], dtype=np.float32), np.array([0.031, 0.027], dtype=np.float32), seg=6, color_fn=lambda t, th: rgba(158, 102, 52, 248), gloss=0.38),
        xform(chamfer_box((0.040, 0.44, 0.22), 0.012, rgba(232, 240, 250, 255), taper_top=(0.35, 1.48), gloss=0.88), translate=(0.0, 1.16, 0.0)),
    ])


def build_tool_egrek_dragon(lod: int) -> MeshPart:
    return merge_parts([
        tube_along_curve(np.array([[0.0, -0.22, 0.0], [0.0, 2.10, 0.0]], dtype=np.float32), np.array([0.033, 0.023], dtype=np.float32), seg=7, color_fn=lambda t, th: rgba(30, 32, 40, 250) if (int(t * 12) % 2 == 0) else rgba(255, 204, 42, 255), gloss=0.84),
        xform(chamfer_box((0.11, 0.17, 0.23), 0.025, rgba(255, 206, 48, 255), gloss=0.88), translate=(0.0, 2.08, 0.0)),
        tube_along_curve(
            np.array([[0.0, 2.10, 0.02], [0.0, 2.40, 0.15], [0.0, 2.65, -0.02], [0.0, 2.74, -0.29], [0.0, 2.56, -0.48]], dtype=np.float32),
            np.array([0.038, 0.068, 0.058, 0.040, 0.005], dtype=np.float32), seg=6,
            color_fn=lambda t, th: rgba(255, 206, 48, 255) if t < 0.45 else rgba(255, 108, 34, 255),
            profile_mod=lambda t, th: np.where(np.abs(np.cos(th)) > 0.5, 0.20, 1.48),
            gloss=0.94,
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
            stats.append({"lod": li, "verts": int(len(lp.pos)), "tris": int(lp.idx.shape[0])})

        tot0 += stats[0]["tris"]
        tot1 += stats[1]["tris"]
        tot2 += stats[2]["tris"]
        manifest["models"].append({"name": name, "radius": round(radius, 3), "lods": stats})
        print(f"  [OK] {name:<20} LOD0={stats[0]['tris']:>5} | LOD1={stats[1]['tris']:>5} | LOD2={stats[2]['tris']:>5}")

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

    print(f"\n=== NPAK v2.0 BUILT: {len(MODEL_SPECS)} models x 3 LODs = {len(MODEL_SPECS)*3} GPU meshes ===")
    print(f"    LOD0={tot0:,} tris -> LOD1={tot1:,} tris -> LOD2={tot2:,} tris | Size={len(blob)/1024/1024:.2f} MB")


if __name__ == "__main__":
    main()
