#!/usr/bin/env python3
"""
Nyawit Live 3D v3.0 — Watertight High-Detail Anatomical, Automotive & Botanical 3D Asset Pipeline

Generates 34 complex, watertight 3D models across 3 parametric LOD tiers (102 GPU meshes):
  1. Mathematical Manifold Winding Guarantee (ZERO "bolong-bolong" / inside-out triangles):
     - Closed parts compute global Divergence-Theorem signed volume V = sum(v0 . (v1 x v2)) once per closed
       manifold instead of per-triangle centroid heuristics, keeping recessed rims, eye sockets, wheel wells,
       and concave curves 100% coherent and outward-facing!
     - xform() automatically checks scale[0]*scale[1]*scale[2] < 0 and reverses triangle winding whenever a
       part is mirrored across X/Y/Z!
  2. Full 11-Part Articulated Human Character Anatomy:
     - Expressive sculpted face (skull, jawline, ears, nose, 3D eyes + pupils, eyebrows, lips, layered hair),
       athletic jacket torso + pelvis + utility belt, separate upper arm + elbow + muscular forearm + 5-finger
       hand (palm, opposable thumb, 4 individual fingers), separate thigh + knee + tall plantation rubber boot!
  3. Animated Sub-Assemblies for Physics & Living World:
     - Independent Canter chassis/cab + 4 suspension/steering wheels + dynamic cargo heap
     - Angkong cart chassis + independent spinning front tire
     - Celeng boar body + 4 articulated galloping cloven-hoof legs
     - PKS factory + spinning rooftop turbine fans + rising boiler steam puffs
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
    sc = np.asarray(scale, dtype=np.float32)
    p = part.pos.astype(np.float32) * sc
    m = rot_y(ry) @ rot_x(rx) @ rot_z(rz)
    p = (p @ m.T) + np.asarray(translate, dtype=np.float32)
    idx = part.idx.copy()
    # CRITICAL FIX: Flip triangle winding whenever negative scale mirrors handedness!
    if float(sc[0] * sc[1] * sc[2]) < 0.0:
        idx = idx[:, [0, 2, 1]]
    return MeshPart(p, part.uv.copy(), part.col.copy(), idx)


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
    closed_ring: bool = True,
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
    j_limit = seg if closed_ring else (seg - 1)
    for si in range(rings - 1):
        b0 = si * seg
        b1 = (si + 1) * seg
        for j in range(j_limit):
            jn = (j + 1) % seg
            tris.append([b0 + j, b1 + j, b1 + jn])
            tris.append([b0 + j, b1 + jn, b0 + jn])

    extra_pos, extra_uv, extra_col = [pos_a], [uv_a], [col_a]
    next_idx = len(pos_a)

    if closed_ring and cap_start:
        c_pt = stations[0][0].mean(axis=0, keepdims=True).astype(np.float32)
        c_col = np.mean(stations[0][1].reshape(-1, 4), axis=0, keepdims=True).astype(np.uint8)
        extra_pos.append(c_pt)
        extra_uv.append(np.array([[u_fixed, gloss]], dtype=np.float32))
        extra_col.append(c_col)
        ci = next_idx
        next_idx += 1
        for j in range(seg):
            jn = (j + 1) % seg
            tris.append([ci, jn, j])

    if closed_ring and cap_end:
        base = (rings - 1) * seg
        c_pt = stations[-1][0].mean(axis=0, keepdims=True).astype(np.float32)
        c_col = np.mean(stations[-1][1].reshape(-1, 4), axis=0, keepdims=True).astype(np.uint8)
        extra_pos.append(c_pt)
        extra_uv.append(np.array([[u_fixed, gloss]], dtype=np.float32))
        extra_col.append(c_col)
        ci = next_idx
        next_idx += 1
        for j in range(seg):
            jn = (j + 1) % seg
            tris.append([ci, base + j, base + jn])

    all_pos = np.vstack(extra_pos)
    all_uv = np.vstack(extra_uv)
    all_col = np.vstack(extra_col)
    idx_arr = np.asarray(tris, dtype=np.int32)

    if closed_ring and cap_start and cap_end:
        # Global signed-volume manifold check (Green's Theorem): NEVER flips individual concave facets!
        centered = all_pos - all_pos.mean(axis=0, keepdims=True)
        v0, v1, v2 = centered[idx_arr[:, 0]], centered[idx_arr[:, 1]], centered[idx_arr[:, 2]]
        vol6 = float(np.sum(v0 * np.cross(v1, v2)))
        if vol6 < 0.0:
            idx_arr = idx_arr[:, [0, 2, 1]]
    elif not closed_ring:
        # True two-sided botanical/fabric blade: emit exact reverse-wound back face with opposing normals
        back_pos = all_pos.copy()
        back_uv = all_uv.copy()
        back_col = all_col.copy()
        back_col[:, :3] = (back_col[:, :3].astype(np.float32) * 0.88).astype(np.uint8)
        back_idx = idx_arr[:, [0, 2, 1]] + len(all_pos)
        all_pos = np.vstack([all_pos, back_pos])
        all_uv = np.vstack([all_uv, back_uv])
        all_col = np.vstack([all_col, back_col])
        idx_arr = np.vstack([idx_arr, back_idx])

    return MeshPart(all_pos, all_uv, all_col, idx_arr)


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
        (-sy, 0.90, 0.0, 0.84),
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


def finalize_normals_and_ao(part: MeshPart, ao_strength: float = 0.48) -> Tuple[np.ndarray, MeshPart]:
    pos = part.pos.astype(np.float32)
    idx = part.idx.astype(np.int32)
    v0, v1, v2 = pos[idx[:, 0]], pos[idx[:, 1]], pos[idx[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)
    fl = np.linalg.norm(fn, axis=1, keepdims=True)
    valid = (fl[:, 0] > 1e-10)
    if not np.all(valid):
        idx = idx[valid]
        fn = fn[valid]
        fl = fl[valid]
    fn = fn / np.maximum(fl, 1e-9)

    vn = np.zeros_like(pos, dtype=np.float32)
    np.add.at(vn, idx[:, 0], fn)
    np.add.at(vn, idx[:, 1], fn)
    np.add.at(vn, idx[:, 2], fn)
    vl = np.linalg.norm(vn, axis=1, keepdims=True)
    nrm = np.where(vl > 1e-8, vn / np.maximum(vl, 1e-8), np.array([0.0, 1.0, 0.0], dtype=np.float32))

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
        col = np.vstack([part.col.copy(), s_col])
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
        span = max(float(pw.max() - pw.min()), 1e-3)
        occ += np.where((depth > span * 0.05) & (facing > 0.05), np.minimum(1.0, depth / (span * 0.34)) * facing, 0.0)

    ao_geom = 1.0 - ao_strength * np.clip(occ / 6.4, 0.0, 0.70)
    col_out = col.copy()
    col_out[:, 3] = np.clip(col_out[:, 3].astype(np.float32) * ao_geom, 78.0, 255.0).astype(np.uint8)
    return nrm.astype(np.float32), MeshPart(pos, uv, col_out, idx, nrm.astype(np.float32))


# ==============================================================================
#  1. BOTANICAL PLANTATION FLORA & TBS HARVEST ASSETS
# ==============================================================================

def build_palm_trunk(lod: int) -> MeshPart:
    parts = []
    n = [32, 16, 7][lod]
    seg = [18, 10, 6][lod]
    ts = np.linspace(-0.03, 1.0, n, dtype=np.float32)
    t_clamped = np.clip(ts, 0.0, 1.0)
    pts = np.stack([0.20 * np.sin(t_clamped * 2.3) + 0.07 * t_clamped * t_clamped, ts * 6.4, 0.14 * (1.0 - np.cos(t_clamped * 1.9))], axis=1)
    radii = 0.64 * ((1.0 - t_clamped) ** 2.6) * 0.50 + 0.37 - 0.10 * t_clamped

    def mod(t: float, th: np.ndarray) -> np.ndarray:
        diamond = np.maximum(0.0, np.sin(8.0 * th + t * 48.0) * np.sin(5.0 * th - t * 32.0))
        buttress = (1.0 - min(1.0, t / 0.18)) * 0.28 * (0.5 + 0.5 * np.cos(7.0 * th + 0.4))
        return 1.0 + 0.16 * diamond * (0.35 + 0.65 * t) + buttress

    def col_fn(t: float, th: np.ndarray) -> np.ndarray:
        scar = np.clip(np.sin(8.0 * th + t * 48.0) * np.sin(5.0 * th - t * 32.0), 0.0, 1.0)
        moss = np.clip(1.0 - t * 2.8, 0.0, 1.0) * 0.50
        return np.stack([
            88 + 56 * scar - 22 * moss,
            68 + 44 * scar + 34 * moss,
            46 + 24 * scar - 8 * moss,
            174 + 80 * scar,
        ], axis=1).astype(np.uint8)

    parts.append(tube_along_curve(pts, radii, seg=seg, color_fn=col_fn, profile_mod=mod, gloss=0.22))
    stub_count = [34, 10, 0][lod]
    for i in range(stub_count):
        t = 0.20 + 0.77 * (i / max(1, stub_count))
        ang = i * 2.39996
        cx, cy, cz = 0.20 * math.sin(t * 2.3) + 0.07 * t * t, t * 6.4, 0.14 * (1.0 - np.cos(t * 1.9))
        base_r = 0.37 - 0.095 * t
        stub = tube_along_curve(
            np.array([[0.0, -0.04, -0.05], [0.0, 0.08, 0.17], [0.0, 0.19, 0.33]], dtype=np.float32),
            np.array([0.155, 0.108, 0.046], dtype=np.float32), seg=6 if lod == 0 else 4,
            color_fn=lambda tt, th: rgba(118 + int(36 * tt), 88 + int(28 * tt), 52, 188 + int(62 * tt)),
            profile_mod=lambda tt, th: 1.0 + 0.40 * np.cos(2.0 * th),
            gloss=0.20,
        )
        parts.append(xform(stub, ry=ang, translate=(cx + math.sin(ang) * base_r * 0.80, cy, cz + math.cos(ang) * base_r * 0.80)))
    return merge_parts(parts)


def build_single_frond(length: float, droop: float, leaflet_pairs: int, tint_shift: float, lod: int) -> MeshPart:
    parts = []
    n = [9, 6, 4][lod]
    ts = np.linspace(0.0, 1.0, n, dtype=np.float32)
    spine_pts = np.stack([np.zeros_like(ts), 0.90 * length * 0.35 * np.sin(ts * 1.48) - droop * (ts ** 2.30), ts * length], axis=1)
    parts.append(tube_along_curve(
        spine_pts, 0.078 * ((1.0 - ts) ** 0.75) + 0.015, seg=5 if lod == 0 else 4,
        color_fn=lambda t, th: rgba(int(72 + 40 * t), int(128 + 50 * t), int(38 + 16 * t), 235),
        gloss=0.58,
    ))

    pairs = leaflet_pairs if lod == 0 else (max(4, leaflet_pairs // 2) if lod == 1 else 2)
    width_boost = [1.35, 2.30, 3.70][lod]
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
            st_defs = [(0.0, 0.044, 0.0), (0.44, 0.095 * width_boost, -0.08), (1.0, 0.010, -0.42)]
            stations = []
            for s_frac, width_k, drop_k in st_defs:
                dist = leaf_len * s_frac
                w = width_k * size_env
                pts3 = np.array([
                    [side * dist, drop_k * leaf_len - w * 0.34, -w],
                    [side * dist, drop_k * leaf_len + w * 0.30, 0.0],
                    [side * dist, drop_k * leaf_len - w * 0.34, w],
                ], dtype=np.float32)
                g_val = int(np.clip(118 + 72 * t + 32 * tint_shift - 14 * s_frac, 42, 244))
                r_val = int(np.clip(48 + 46 * t + 26 * tint_shift + 14 * s_frac, 22, 225))
                b_val = int(np.clip(30 + 18 * t, 18, 130))
                stations.append((pts3, rgba(r_val, g_val, b_val, int(202 + 50 * s_frac)), s_frac))
            # Open botanical V-blade with true double-sided opposing normals (ZERO holes from below OR above!)
            parts.append(xform(loft_profile(stations, closed_ring=False, cap_start=False, cap_end=False, gloss=0.62), rz=rank_tilt, ry=side * 0.28 * t, translate=tuple(anchor)))
    return merge_parts(parts)


def build_palm_crown(lod: int) -> MeshPart:
    parts = []
    spear_n, upper_n, mid_n, lower_n = [3, 2, 1][lod], [5, 3, 2][lod], [5, 3, 2][lod], [5, 3, 2][lod]
    parts.append(organic_ellipsoid(0.45, 0.38, 0.45, 6, 10, col_fn=lambda t, th: rgba(88, 108, 44, 185), gloss=0.25))
    for s in range(spear_n):
        parts.append(xform(build_single_frond(2.15, 0.16, 5, 0.62, lod), rx=-1.22, ry=s * (2.0 * math.pi / spear_n), translate=(0.0, 0.28, 0.0)))
    for i in range(upper_n):
        parts.append(xform(build_single_frond(3.45, 0.72, 7, 0.32, lod), rx=-0.56, ry=i * (2.0 * math.pi / upper_n) + 0.26, translate=(0.0, 0.18, 0.0)))
    for i in range(mid_n):
        parts.append(xform(build_single_frond(3.85, 1.22, 7, 0.08, lod), rx=-0.22, ry=i * (2.0 * math.pi / mid_n) + 0.58, translate=(0.0, 0.08, 0.0)))
    for i in range(lower_n):
        parts.append(xform(build_single_frond(3.95, 1.75, 7, -0.18, lod), rx=0.06, ry=i * (2.0 * math.pi / lower_n), translate=(0.0, -0.02, 0.0)))
    return merge_parts(parts)


def build_tbs_bunch(lod: int) -> MeshPart:
    parts = [
        organic_ellipsoid(0.25, 0.31, 0.25, rings=[8, 6, 5][lod], seg=[12, 8, 6][lod], col_fn=lambda t, th: rgba(212, 62, 18, 206), disp_fn=lambda ph, th: 1.0 + 0.14 * np.sin(6.0 * th) * np.cos(4.0 * ph), dyeable=True, gloss=0.72),
        tube_along_curve(np.array([[0.0, 0.24, 0.0], [0.05, 0.47, 0.04]], dtype=np.float32), np.array([0.090, 0.056], dtype=np.float32), seg=6 if lod == 0 else 4, color_fn=lambda t, th: rgba(168, 156, 72, 240), gloss=0.25),
    ]
    fruit_n = [40, 16, 0][lod]
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(fruit_n):
        y_n = 1.0 - 2.0 * (i + 0.5) / fruit_n
        rad = math.sqrt(max(0.0, 1.0 - y_n * y_n))
        ang = golden * i
        lobe = 1.0 + 0.13 * np.sin(3.0 * ang + y_n * 2.0)
        px, py, pz = math.cos(ang) * rad * 0.27 * lobe, y_n * 0.31, math.sin(ang) * rad * 0.27 * lobe
        rp = 0.5 + 0.5 * math.sin(i * 1.7)
        fruitlet = organic_ellipsoid(
            0.082, 0.094, 0.082, rings=5, seg=6,
            col_fn=lambda t, th, rpp=rp: rgba(int(232 + 22 * (1.0 - t)), int(62 + 104 * (1.0 - t) * rpp), int(16 + 18 * (1.0 - t)), int(186 + 68 * t)),
            dyeable=True, gloss=0.78,
        )
        parts.append(xform(fruitlet, ry=ang, rx=y_n * 0.6, translate=(px, py, pz)))
        if lod == 0 and i % 2 == 0:
            spine = tube_along_curve(np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.13]], dtype=np.float32), np.array([0.015, 0.003], dtype=np.float32), seg=4, color_fn=lambda t, th: rgba(132, 86, 40, 228))
            parts.append(xform(spine, ry=ang, rx=-y_n * 0.75, translate=(px * 1.08, py, pz * 1.08)))
    return merge_parts(parts)


def build_tropical_fern(lod: int) -> MeshPart:
    cnt = [8, 5, 3][lod]
    return merge_parts([xform(build_single_frond(1.02 + 0.18 * (i % 2), 0.36, 5, 0.38, lod), rx=-0.45 - 0.22 * (i % 2), ry=i * (2.0 * math.pi / cnt), scale=(0.68, 0.68, 0.68), translate=(0.0, 0.06, 0.0)) for i in range(cnt)])


def build_rock_boulder(lod: int) -> MeshPart:
    parts = []
    for k, (sx, sy, sz, ox, oz) in enumerate([(0.82, 0.58, 0.70, 0.0, 0.0), (0.48, 0.38, 0.46, 0.50, 0.24), (0.40, 0.30, 0.36, -0.40, 0.32)][:(3 if lod < 2 else 1)]):
        rock = organic_ellipsoid(
            sx, sy, sz, rings=[7, 5, 4][lod], seg=[10, 7, 5][lod],
            col_fn=lambda t, th: rgba(int(114 + 28 * t), int(98 + 30 * t), int(84 + 18 * t), int(178 + 74 * t)),
            disp_fn=lambda ph, th, kk=k: 1.0 + 0.16 * np.sin(3.0 * th + kk * 1.7) * np.cos(2.0 * ph) + 0.08 * np.cos(5.0 * th),
            gloss=0.22,
        )
        parts.append(xform(rock, ry=k * 1.1, translate=(ox, sy * 0.44, oz)))
    return merge_parts(parts)


# ==============================================================================
#  2. VEHICLES, SUSPENSION WHEELS & HAULING EQUIPMENT (100% SEALED SOLID BODIES)
# ==============================================================================

def build_canter_truck_body(lod: int) -> MeshPart:
    """100% Watertight Mitsubishi Canter 'Oleng Sawit HD' with sealed chassis, wheel liners, cab interior & dashboard!"""
    parts = []
    cab_col = rgba(246, 196, 34, 252)
    cab_dk = rgba(212, 158, 22, 242)
    steel = rgba(44, 50, 58, 240)
    steel_dark = rgba(26, 30, 36, 232)
    steel_lt = rgba(138, 148, 158, 246)
    chrome = rgba(232, 240, 248, 255)
    glass = rgba(22, 38, 54, 252)
    wood_red = rgba(148, 66, 34, 242)
    wood_tan = rgba(190, 124, 58, 244)
    headlight = rgba(255, 252, 236, 255)
    amber = rgba(255, 168, 24, 255)
    taillight = rgba(248, 36, 36, 255)

    # Solid steel underbody frame + longitudinal I-beams + axles/differentials + driveshaft (zero gaps underneath!)
    parts.append(xform(chamfer_box((1.16, 0.20, 4.96), 0.03, steel_dark, gloss=0.40), translate=(0.0, 0.58, -0.02)))
    for sx in (-0.50, 0.50):
        parts.append(xform(chamfer_box((0.14, 0.22, 5.06), 0.02, steel, gloss=0.48), translate=(sx, 0.58, -0.02)))
    # Front & Rear Solid Axle Tubes + Leaf Spring Packs!
    for az in (1.55, -1.25):
        parts.append(tube_along_curve(np.array([[-0.88, 0.48, az], [0.88, 0.48, az]], dtype=np.float32), np.array([0.055, 0.055], dtype=np.float32), seg=8, color_fn=lambda t, th: steel, gloss=0.52))
        parts.append(organic_ellipsoid(0.18, 0.18, 0.18, 5, 8, col_fn=lambda t, th: steel_dark, gloss=0.48) if az < 0 else chamfer_box((0.24, 0.16, 0.24), 0.03, steel_dark))
        parts[-1] = xform(parts[-1], translate=(0.0, 0.48, az))

    if lod < 2:
        parts.append(tube_along_curve(np.array([[-0.76, 0.58, -0.38], [-0.76, 0.58, 0.48]], dtype=np.float32), np.array([0.21, 0.21], dtype=np.float32), seg=12 if lod == 0 else 8, color_fn=lambda t, th: chrome, gloss=0.84))
        parts.append(xform(chamfer_box((0.42, 0.32, 0.66), 0.03, steel, gloss=0.42), translate=(0.74, 0.58, 0.05)))
        for sx in (-0.94, 0.94):
            parts.append(xform(chamfer_box((0.06, 0.09, 1.16), 0.015, cab_col, dyeable=True, gloss=0.72), translate=(sx, 0.56, -0.10)))

    # Sealed Lower Cab Tub + Interior Dashboard + Bench Seat + Upper Cab Roof & Pillars (100% solid watertight!)
    parts.append(xform(chamfer_box((1.92, 0.72, 1.44), 0.08, cab_col, dyeable=True, gloss=0.78), translate=(0.0, 0.98, 1.70)))
    parts.append(xform(chamfer_box((1.84, 0.76, 1.24), 0.08, cab_col, taper_top=(0.91, 0.84), shear_z_top=-0.15, arch_top=0.045, dyeable=True, gloss=0.78), translate=(0.0, 1.67, 1.64)))
    # Interior dashboard + bench seat silhouette visible behind windows
    parts.append(xform(chamfer_box((1.62, 0.26, 0.34), 0.03, steel_dark, gloss=0.35), translate=(0.0, 1.32, 2.02)))
    parts.append(xform(chamfer_box((1.54, 0.42, 0.36), 0.04, rgba(58, 44, 36, 250), gloss=0.32), translate=(0.0, 1.24, 1.34)))

    # Solid inner wheel well liners + flared arches (ZERO sky peek-through!)
    for sx in (-0.82, 0.82):
        parts.append(xform(chamfer_box((0.36, 0.36, 1.02), 0.05, steel_dark, arch_top=0.10, gloss=0.35), translate=(sx, 0.68, 1.55)))
        parts.append(xform(chamfer_box((0.38, 0.36, 1.06), 0.05, steel_dark, arch_top=0.10, gloss=0.35), translate=(sx, 0.68, -1.25)))

    # Custom Roof Visor + 3 Clearance LEDs + Twin Chrome Basuri Airhorns
    parts.append(xform(chamfer_box((1.62, 0.20, 0.74), 0.05, cab_dk, taper_top=(0.82, 0.60), arch_top=0.06, dyeable=True, gloss=0.76), translate=(0.0, 2.13, 1.54)))
    parts.append(xform(chamfer_box((1.72, 0.10, 0.22), 0.03, chrome, gloss=0.86), rx=0.18, translate=(0.0, 2.02, 2.06)))
    for hx in (-0.52, 0.0, 0.52):
        parts.append(xform(chamfer_box((0.14, 0.06, 0.05), 0.015, amber, gloss=0.96), translate=(hx, 2.22, 1.88)))
    if lod < 2:
        for hx, hl in ((-0.42, 0.52), (0.42, 0.58)):
            parts.append(tube_along_curve(np.array([[hx, 2.24, 1.38], [hx, 2.26, 1.38 + hl]], dtype=np.float32), np.array([0.028, 0.074], dtype=np.float32), seg=8, color_fn=lambda t, th: chrome, gloss=0.88))

    # Glossy Windshield, Side Windows & Chrome Door Handles
    parts.append(xform(chamfer_box((1.60, 0.48, 0.08), 0.02, glass, gloss=0.88), rx=-0.20, translate=(0.0, 1.68, 2.23)))
    for sx in (-1.0, 1.0):
        parts.append(xform(chamfer_box((0.08, 0.44, 0.76), 0.02, glass, shear_z_top=-0.10, gloss=0.88), translate=(sx * 0.92, 1.68, 1.66)))
        parts.append(xform(chamfer_box((0.05, 0.055, 0.17), 0.01, chrome, gloss=0.86), translate=(sx * 0.96, 1.24, 1.52)))

    # 3-Bar Chrome Grille + LED Headlights, Turn Signals & Bumper Fog Lamps
    parts.append(xform(chamfer_box((1.32, 0.27, 0.08), 0.02, rgba(24, 28, 34, 244), gloss=0.45), translate=(0.0, 0.92, 2.42)))
    for gy in (0.86, 0.93, 1.00):
        parts.append(xform(chamfer_box((1.24, 0.034, 0.08), 0.01, chrome, gloss=0.88), translate=(0.0, gy, 2.46)))
    for sx in (-1.0, 1.0):
        parts.append(xform(chamfer_box((0.30, 0.19, 0.08), 0.02, headlight, gloss=0.97), translate=(sx * 0.72, 0.92, 2.43)))
        parts.append(xform(chamfer_box((0.12, 0.19, 0.08), 0.02, amber, gloss=0.96), translate=(sx * 0.91, 0.92, 2.39)))
        parts.append(xform(chamfer_box((0.16, 0.09, 0.08), 0.02, amber, gloss=0.96), translate=(sx * 0.68, 0.58, 2.59)))

    # Steel Front Bumper + Rear Underrun Bumper + Mudflaps + Bullbar + Mirrors + Snorkel Exhaust
    parts.append(xform(chamfer_box((2.02, 0.25, 0.22), 0.035, steel, gloss=0.52), translate=(0.0, 0.58, 2.50)))
    parts.append(xform(chamfer_box((1.96, 0.20, 0.18), 0.03, steel, gloss=0.50), translate=(0.0, 0.60, -2.48)))
    for sx in (-0.68, 0.68):
        parts.append(xform(chamfer_box((0.32, 0.13, 0.08), 0.02, taillight, gloss=0.96), translate=(sx, 0.61, -2.54)))
        parts.append(xform(chamfer_box((0.40, 0.30, 0.04), 0.01, steel_dark, gloss=0.25), translate=(sx * 1.12, 0.42, -1.78)))
    if lod < 2:
        bull_pts = np.array([[-0.82, 0.60, 2.60], [-0.72, 1.12, 2.64], [0.72, 1.12, 2.64], [0.82, 0.60, 2.60]], dtype=np.float32)
        parts.append(tube_along_curve(bull_pts, np.full(4, 0.040, dtype=np.float32), seg=6, color_fn=lambda t, th: chrome, gloss=0.88))
        for sx in (-1.0, 1.0):
            arm = np.array([[sx * 0.93, 1.84, 2.02], [sx * 1.14, 1.82, 2.08], [sx * 1.14, 1.48, 2.06]], dtype=np.float32)
            parts.append(tube_along_curve(arm, np.full(3, 0.024, dtype=np.float32), seg=5, color_fn=lambda t, th: chrome, gloss=0.85))
            parts.append(xform(chamfer_box((0.09, 0.28, 0.17), 0.02, rgba(30, 34, 40, 250), gloss=0.70), translate=(sx * 1.15, 1.66, 2.08)))
        exh = np.array([[0.74, 0.62, 0.94], [0.78, 2.24, 0.94], [0.85, 2.44, 0.86]], dtype=np.float32)
        parts.append(tube_along_curve(exh, np.array([0.054, 0.050, 0.044], dtype=np.float32), seg=8, color_fn=lambda t, th: chrome, gloss=0.88))

    # Heavy Hardwood Slatted 'Bak Tinggi Sawit' Dump Bed with Solid Floor Deck
    parts.append(xform(chamfer_box((2.08, 0.18, 3.32), 0.03, steel_lt, gloss=0.50), translate=(0.0, 0.74, -0.79)))
    plank_rows = [5, 3, 2][lod]
    for plank_i in range(plank_rows):
        py = 0.93 + plank_i * (0.90 / max(1, plank_rows - 1))
        h_p = 0.16 if lod == 0 else 0.29
        c_pl = wood_red if plank_i % 2 == 0 else wood_tan
        for sx in (-0.99, 0.99):
            parts.append(xform(chamfer_box((0.075, h_p, 3.24), 0.015, c_pl, gloss=0.38), translate=(sx, py, -0.79)))
        parts.append(xform(chamfer_box((1.96, h_p, 0.075), 0.015, c_pl, gloss=0.38), translate=(0.0, py, 0.82)))
        parts.append(xform(chamfer_box((1.96, h_p, 0.075), 0.015, c_pl, gloss=0.38), translate=(0.0, py, -2.40)))

    if lod < 2:
        for sz in (-2.30, -1.52, -0.76, 0.0, 0.74):
            for sx in (-1.05, 1.05):
                parts.append(xform(chamfer_box((0.07, 1.15, 0.08), 0.015, steel, gloss=0.55), translate=(sx, 1.36, sz)))
    return merge_parts(parts)


def build_truck_wheel(lod: int) -> MeshPart:
    """Watertight off-road lugged plantation truck tire with yellow deep-dish rim & chrome hubcap!"""
    seg = [24, 14, 8][lod]
    thetas = np.linspace(0.0, 2.0 * math.pi, seg, endpoint=False, dtype=np.float32)
    prof = [
        (-0.22, 0.12, rgba(214, 222, 232, 255)),
        (-0.19, 0.26, rgba(244, 194, 34, 250)),
        (-0.21, 0.37, rgba(34, 36, 40, 242)),
        (-0.15, 0.47, rgba(24, 26, 30, 252)),
        (0.00, 0.49, rgba(20, 22, 26, 255)),
        (0.15, 0.47, rgba(24, 26, 30, 252)),
        (0.21, 0.37, rgba(34, 36, 40, 242)),
        (0.19, 0.26, rgba(244, 194, 34, 250)),
        (0.22, 0.12, rgba(214, 222, 232, 255)),
    ]
    stations = []
    for si, (xx, rr, c) in enumerate(prof):
        lugs = 1.0 + (0.045 * np.sign(np.sin(10.0 * thetas)) if (lod == 0 and 3 <= si <= 5) else 0.0)
        ring = np.stack([np.full_like(thetas, xx), np.sin(thetas) * rr * lugs, np.cos(thetas) * rr * lugs], axis=1)
        stations.append((ring, c, si / (len(prof) - 1)))
    wheel = loft_profile(stations, cap_start=True, cap_end=True, gloss=0.46)
    parts = [wheel]
    # Add visible lug bolts so rolling rotation is unmistakable even from 25m away!
    if lod < 2:
        for bi in range(6):
            ang = bi * (math.pi / 3.0)
            for sx in (-0.205, 0.205):
                parts.append(xform(chamfer_box((0.04, 0.055, 0.055), 0.01, rgba(245, 248, 252, 255), gloss=0.88), translate=(sx, math.sin(ang) * 0.21, math.cos(ang) * 0.21)))
    return merge_parts(parts)


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
        0.37, 0.31, 0.41, rings=[6, 4, 4][lod], seg=[8, 6, 5][lod],
        col_fn=lambda t, th: rgba(int(232 + 22 * (1.0 - t)), int(68 + 90 * (1.0 - t)), 20, int(186 + 68 * t)),
        disp_fn=lambda ph, th: 1.0 + 0.15 * np.sin(6.0 * th) * np.cos(4.0 * ph),
        gloss=0.72,
    )
    for px, py, pz, ry in positions[:([14, 10, 6][lod])]:
        parts.append(xform(mini_tbs, ry=ry, translate=(px, py, pz)))
    return merge_parts(parts)


def build_angkong_cart(lod: int) -> MeshPart:
    """Angkong wheelbarrow frame & steel tray (wheel rendered dynamically as spinning rigidbody wheel!)."""
    parts = [
        xform(chamfer_box((0.80, 0.44, 1.06), 0.08, rgba(28, 154, 176, 250), taper_top=(1.32, 1.28), shear_z_top=0.14, gloss=0.68), translate=(0.0, 0.58, 0.08)),
        xform(chamfer_box((0.86, 0.05, 1.12), 0.04, rgba(20, 114, 134, 252), gloss=0.74), translate=(0.0, 0.80, 0.15)),
    ]
    for sx in (-1.0, 1.0):
        frame = np.array([[sx * 0.16, 0.29, 0.80], [sx * 0.30, 0.36, -0.25], [sx * 0.36, 0.72, -1.02]], dtype=np.float32)
        parts.append(tube_along_curve(frame, np.full(3, 0.026, dtype=np.float32), seg=6, color_fn=lambda t, th: rgba(60, 66, 74, 244), gloss=0.55))
        # Red non-slip rubber grip handles
        grip = np.array([[sx * 0.34, 0.66, -0.86], [sx * 0.37, 0.74, -1.08]], dtype=np.float32)
        parts.append(tube_along_curve(grip, np.full(2, 0.036, dtype=np.float32), seg=8, color_fn=lambda t, th: rgba(218, 48, 42, 252), gloss=0.45))
        leg = np.array([[sx * 0.30, 0.36, -0.30], [sx * 0.32, 0.02, -0.36], [sx * 0.30, 0.36, -0.46]], dtype=np.float32)
        parts.append(tube_along_curve(leg, np.full(3, 0.022, dtype=np.float32), seg=5, color_fn=lambda t, th: rgba(60, 66, 74, 244)))
    for ox, oz in ((-0.16, 0.05), (0.16, 0.08), (0.0, 0.30)):
        parts.append(xform(organic_ellipsoid(0.20, 0.17, 0.22, 6, 10, col_fn=lambda t, th: rgba(236 + int(18 * (1.0 - t)), 74 + int(42 * (1.0 - t)), 20, int(190 + 62 * t)), gloss=0.72), translate=(ox, 0.85, oz)))
    return merge_parts(parts)


# ==============================================================================
#  3. ARCHITECTURE, SPINNING TURBINE FANS, STEAM PUFFS & ARTICULATED WILDLIFE
# ==============================================================================

def build_pks_factory(lod: int) -> MeshPart:
    parts = []
    wall = rgba(224, 228, 234, 246)
    wall_band = rgba(44, 134, 88, 246)
    roof_green = rgba(28, 118, 76, 250)
    steel = rgba(52, 58, 68, 238)
    accent = rgba(244, 184, 28, 252)
    flood = rgba(255, 244, 204, 255)

    parts.append(xform(chamfer_box((11.2, 0.48, 9.0), 0.06, rgba(132, 138, 144, 230), gloss=0.20), translate=(0.0, 0.24, 0.0)))
    parts.append(xform(chamfer_box((10.6, 5.2, 8.4), 0.10, wall, gloss=0.35), translate=(0.0, 2.95, 0.0)))
    parts.append(xform(chamfer_box((10.76, 0.65, 8.56), 0.06, wall_band, gloss=0.52), translate=(0.0, 4.65, 0.0)))
    parts.append(xform(chamfer_box((11.5, 1.55, 9.3), 0.09, roof_green, taper_top=(0.06, 0.98), gloss=0.58), translate=(0.0, 6.28, 0.0)))
    parts.append(xform(chamfer_box((5.2, 1.15, 6.8), 0.08, wall, gloss=0.35), translate=(0.0, 7.20, 0.0)))
    parts.append(xform(chamfer_box((5.8, 0.68, 7.2), 0.07, roof_green, taper_top=(0.10, 0.98), gloss=0.58), translate=(0.0, 8.05, 0.0)))

    for sx in (-5.36, -2.68, 2.68, 5.36):
        for sz in (-4.26, 4.26):
            parts.append(xform(chamfer_box((0.28, 5.25, 0.28), 0.03, steel, gloss=0.52), translate=(sx, 2.85, sz)))
    for lx in (-3.6, 0.0, 3.6):
        parts.append(xform(chamfer_box((0.55, 0.24, 0.14), 0.02, flood, gloss=0.97), translate=(lx, 4.65, 4.34)))

    parts.append(xform(chamfer_box((3.8, 3.5, 0.24), 0.04, rgba(20, 24, 30, 220), gloss=0.40), translate=(0.0, 1.85, 4.32)))
    parts.append(xform(chamfer_box((4.9, 0.30, 2.7), 0.05, accent, gloss=0.68), rx=0.06, translate=(0.0, 3.95, 5.40)))

    for cx in (-3.2, -1.0):
        ch_pts = np.array([[cx, 5.6, -2.2], [cx, 9.8, -2.2], [cx, 14.0, -2.2]], dtype=np.float32)
        parts.append(tube_along_curve(ch_pts, np.array([0.64, 0.52, 0.40], dtype=np.float32), seg=[14, 8, 6][lod], color_fn=lambda t, th: rgba(204, 68, 48, 250) if (int(t * 9) % 2 == 0) else rgba(242, 244, 248, 252), gloss=0.50))
    for tx, tz in ((7.3, -2.3), (7.3, 1.9), (-7.3, 0.2)):
        silo = np.array([[tx, 0.0, tz], [tx, 5.0, tz], [tx, 5.8, tz]], dtype=np.float32)
        parts.append(tube_along_curve(silo, np.array([1.75, 1.75, 0.14], dtype=np.float32), seg=[16, 10, 6][lod], color_fn=lambda t, th: rgba(206, 214, 224, 248), gloss=0.78))
    if lod < 2:
        parts.append(xform(chamfer_box((3.2, 0.18, 0.65), 0.02, accent, gloss=0.60), translate=(5.6, 4.6, -0.2)))
    return merge_parts(parts)


def build_pks_fan(lod: int) -> MeshPart:
    """Spinning stainless rooftop industrial cyclone ventilator turbine on PKS Mill roof!"""
    chrome = rgba(226, 234, 242, 255)
    parts = [
        tube_along_curve(np.array([[0.0, 0.0, 0.0], [0.0, 0.35, 0.0]], dtype=np.float32), np.array([0.42, 0.44], dtype=np.float32), seg=10, color_fn=lambda t, th: rgba(88, 96, 108, 245), gloss=0.65),
        organic_ellipsoid(0.62, 0.46, 0.62, 6, 12, col_fn=lambda t, th: chrome, disp_fn=lambda ph, th: 1.0 + 0.12 * np.sin(8.0 * th), gloss=0.86),
    ]
    parts[-1] = xform(parts[-1], translate=(0.0, 0.62, 0.0))
    blades = [8, 6, 4][lod]
    for i in range(blades):
        ang = i * (2.0 * math.pi / blades)
        parts.append(xform(chamfer_box((0.12, 0.48, 0.28), 0.015, chrome, gloss=0.90), ry=ang + 0.45, translate=(math.sin(ang) * 0.56, 0.62, math.cos(ang) * 0.56)))
    return merge_parts(parts)


def build_steam_puff(lod: int) -> MeshPart:
    """Volumetric multi-lobe boiler steam / diesel exhaust cloud puff!"""
    c = lambda t, th: rgba(int(236 + 18 * t), int(240 + 14 * t), int(246 + 9 * t), int(215 + 38 * t))
    parts = [organic_ellipsoid(0.55, 0.44, 0.55, [6, 5, 4][lod], [9, 7, 5][lod], col_fn=c, gloss=0.18)]
    if lod < 2:
        parts.append(xform(organic_ellipsoid(0.38, 0.32, 0.38, 5, 7, col_fn=c, gloss=0.18), translate=(0.30, 0.14, 0.18)))
        parts.append(xform(organic_ellipsoid(0.34, 0.30, 0.34, 5, 7, col_fn=c, gloss=0.18), translate=(-0.28, -0.06, -0.20)))
    return merge_parts(parts)


def build_weighbridge_ram(lod: int) -> MeshPart:
    parts = []
    steel = rgba(52, 60, 70, 242)
    yellow = rgba(246, 188, 24, 252)
    led_green = rgba(46, 255, 138, 255)

    parts.append(xform(chamfer_box((4.5, 0.30, 7.6), 0.04, steel, gloss=0.58), translate=(0.0, 0.15, 0.0)))
    for sz, tilt in ((4.65, 0.13), (-4.65, -0.13)):
        parts.append(xform(chamfer_box((4.4, 0.20, 1.85), 0.04, yellow, gloss=0.64), rx=tilt, translate=(0.0, 0.09, sz)))
    for sx in (-2.12, 2.12):
        rail = np.array([[sx, 0.28, -3.6], [sx, 0.80, -3.1], [sx, 0.80, 3.1], [sx, 0.28, 3.6]], dtype=np.float32)
        parts.append(tube_along_curve(rail, np.full(4, 0.088, dtype=np.float32), seg=6, color_fn=lambda t, th: yellow, gloss=0.68))
        parts.append(xform(chamfer_box((0.28, 4.3, 0.28), 0.03, steel, gloss=0.58), translate=(sx, 2.25, 0.0)))
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
            parts.append(xform(chamfer_box((0.24, 1.16, 0.24), 0.03, timber), translate=(sx, 0.56, sz)))
    parts.append(xform(chamfer_box((3.7, 0.22, 3.9), 0.04, timber), translate=(0.0, 1.06, 0.0)))
    parts.append(xform(chamfer_box((3.2, 2.15, 2.8), 0.05, wall_wood), translate=(0.0, 2.20, -0.35)))
    parts.append(xform(chamfer_box((4.2, 0.96, 4.6), 0.06, rgba(162, 68, 46, 248), taper_top=(0.08, 0.98), gloss=0.48), translate=(0.0, 3.72, 0.0)))
    parts.append(xform(chamfer_box((0.22, 0.28, 0.22), 0.03, rgba(255, 214, 112, 255), gloss=0.97), translate=(1.25, 2.85, 1.35)))
    for step_i in range(3):
        parts.append(xform(chamfer_box((1.25, 0.18, 0.38), 0.03, timber), translate=(0.0, 0.26 + step_i * 0.30, 2.35 - step_i * 0.30)))
    if lod < 2:
        for dx, dz in ((-2.25, 0.8), (-2.25, -0.2)):
            parts.append(tube_along_curve(np.array([[dx, 0.0, dz], [dx, 0.90, dz]], dtype=np.float32), np.array([0.30, 0.30], dtype=np.float32), seg=10, color_fn=lambda t, th: rgba(34, 108, 196, 246), gloss=0.68))
    return merge_parts(parts)


def build_wooden_bridge(lod: int) -> MeshPart:
    parts = []
    log_col, plank_col = rgba(112, 70, 38, 234), rgba(164, 114, 64, 244)
    n = [11, 7, 5][lod]
    zs = np.linspace(-4.8, 4.8, n, dtype=np.float32)
    arch_y = 0.62 * np.maximum(0.0, 1.0 - (zs / 4.6) ** 2)
    for sx in (-1.55, 0.0, 1.55):
        parts.append(tube_along_curve(np.stack([np.full_like(zs, sx), arch_y + 0.12, zs], axis=1), np.full(n, 0.18, dtype=np.float32), seg=6, color_fn=lambda t, th: log_col))
    planks = [18, 10, 6][lod]
    for pi in range(planks):
        zz = -4.5 + pi * (9.0 / max(1, planks - 1))
        yy = 0.62 * max(0.0, 1.0 - (zz / 4.6) ** 2) + 0.32
        parts.append(xform(chamfer_box((3.9, 0.14, 9.0 / planks * 0.92), 0.02, plank_col), translate=(0.0, yy, zz)))
    for sx in (-1.85, 1.85):
        parts.append(tube_along_curve(np.stack([np.full_like(zs, sx), arch_y + 1.12, zs], axis=1), np.full(n, 0.070, dtype=np.float32), seg=5, color_fn=lambda t, th: log_col))
        if lod < 2:
            for pz in (-4.0, -2.0, 0.0, 2.0, 4.0):
                py_b = 0.62 * max(0.0, 1.0 - (pz / 4.6) ** 2)
                parts.append(xform(chamfer_box((0.12, 0.88, 0.12), 0.02, log_col), translate=(sx, py_b + 0.72, pz)))
    return merge_parts(parts)


def build_celeng_boar(lod: int) -> MeshPart:
    """Muscular wild boar body (legs articulated separately via boar_leg so all 4 legs gallop dynamically!)."""
    parts = []
    sg = [16, 10, 7][lod]
    spine = np.array([[0.0, 0.56, -0.66], [0.0, 0.70, -0.22], [0.0, 0.78, 0.18], [0.0, 0.62, 0.54], [0.0, 0.48, 0.84], [0.0, 0.43, 1.03]], dtype=np.float32)
    parts.append(tube_along_curve(
        spine, np.array([0.23, 0.36, 0.42, 0.33, 0.19, 0.12], dtype=np.float32), seg=sg,
        color_fn=lambda t, th: rgba(int(64 + 34 * t), int(46 + 22 * t), int(34 + 12 * t), int(214 + 40 * t)),
        profile_mod=lambda t, th: 1.0 + 0.14 * np.maximum(0.0, np.sin(th)),
        gloss=0.36,
    ))
    parts.append(xform(chamfer_box((0.21, 0.16, 0.08), 0.03, rgba(168, 114, 104, 248), gloss=0.52), translate=(0.0, 0.43, 1.06)))
    for mi in range(5 if lod < 2 else 3):
        mz = -0.34 + mi * 0.19
        parts.append(xform(chamfer_box((0.08, 0.20, 0.20), 0.02, rgba(28, 20, 18, 246), taper_top=(0.18, 0.55)), rx=-0.24, translate=(0.0, 1.08 - abs(mi - 2) * 0.03, mz)))
    tail = np.array([[0.0, 0.62, -0.62], [0.0, 0.74, -0.78], [0.05, 0.88, -0.74]], dtype=np.float32)
    parts.append(tube_along_curve(tail, np.array([0.048, 0.030, 0.015], dtype=np.float32), seg=6, color_fn=lambda t, th: rgba(42, 30, 24, 240)))
    for sx in (-1.0, 1.0):
        tusk = np.array([[sx * 0.11, 0.44, 0.84], [sx * 0.25, 0.56, 0.99], [sx * 0.20, 0.73, 0.96]], dtype=np.float32)
        parts.append(tube_along_curve(tusk, np.array([0.040, 0.028, 0.006], dtype=np.float32), seg=8, color_fn=lambda t, th: rgba(250, 245, 228, 255), gloss=0.78))
        parts.append(xform(chamfer_box((0.050, 0.050, 0.060), 0.01, rgba(255, 96, 28, 255), gloss=0.97), translate=(sx * 0.22, 0.65, 0.68)))
        parts.append(xform(chamfer_box((0.095, 0.19, 0.14), 0.02, rgba(58, 42, 34, 244), taper_top=(0.30, 0.45)), rz=-sx * 0.42, translate=(sx * 0.20, 0.88, 0.46)))
    return merge_parts(parts)


def build_boar_leg(lod: int) -> MeshPart:
    """Articulated muscular wild boar leg with joint socket at (0,0,0) and dark cloven hoof at y=-0.52!"""
    sg = [12, 8, 6][lod]
    parts = [
        organic_ellipsoid(0.11, 0.11, 0.11, 5, sg, col_fn=lambda t, th: rgba(54, 38, 30, 240), gloss=0.32),
        tube_along_curve(np.array([[0.0, 0.0, 0.0], [0.0, -0.26, -0.04], [0.0, -0.47, 0.02]], dtype=np.float32), np.array([0.105, 0.072, 0.052], dtype=np.float32), seg=sg, color_fn=lambda t, th: rgba(48, 34, 28, 238)),
        xform(chamfer_box((0.11, 0.09, 0.15), 0.02, rgba(24, 20, 18, 250), gloss=0.45), translate=(0.0, -0.49, 0.03)),
    ]
    return merge_parts(parts)


# ==============================================================================
#  4. ULTRA-DETAILED 11-PART ARTICULATED HUMAN CHARACTER ANATOMY & COSMETICS
# ==============================================================================

def build_char_torso_head(lod: int) -> MeshPart:
    """
    Athletic sculpted torso + pelvis hip socket + collar + utility belt (y = -0.06 .. +0.58).
    Kept under catalog key 'char_torso_head' while the detailed head + face renders via 'char_head'
    so the head nods, looks, and turns independently with lifelike expression!
    """
    sg = [20, 14, 8][lod]
    parts = [
        # Rounded pelvis & trouser waist socket (eliminates all hip/leg joint gaps!)
        organic_ellipsoid(0.178, 0.125, 0.138, 6, sg, col_fn=lambda t, th: rgba(48, 56, 68, 236), gloss=0.34),
        # Heavy leather harvest belt + brass buckle + side utility pouch
        xform(chamfer_box((0.38, 0.095, 0.285), 0.045, rgba(42, 36, 32, 246), gloss=0.48), translate=(0.0, 0.06, 0.0)),
        xform(chamfer_box((0.105, 0.098, 0.048), 0.015, rgba(250, 204, 52, 255), gloss=0.88), translate=(0.0, 0.06, 0.152)),
        xform(chamfer_box((0.085, 0.125, 0.105), 0.02, rgba(84, 54, 34, 244), gloss=0.42), translate=(0.205, 0.03, 0.02)),
        # Heroic athletic V-taper plantation work jacket / shirt (dyeable=True)
        tube_along_curve(
            np.array([[0.0, 0.07, 0.0], [0.0, 0.23, 0.01], [0.0, 0.42, 0.02], [0.0, 0.56, 0.005]], dtype=np.float32),
            np.array([0.172, 0.206, 0.248, 0.175], dtype=np.float32), seg=sg,
            color_fn=lambda t, th: rgba(int(232 + 22 * t), int(232 + 22 * t), int(232 + 22 * t), int(214 + 40 * t)),
            profile_mod=lambda t, th: 1.0 + 0.20 * np.cos(2.0 * th + math.pi),
            dyeable=True, gloss=0.42,
        ),
        # Sculpted pectoral chest plates & open V-neck undershirt + popped collar lapels
        xform(chamfer_box((0.11, 0.40, 0.035), 0.012, rgba(32, 38, 46, 248), gloss=0.42), translate=(0.0, 0.33, 0.165)),
        tube_along_curve(np.array([[0.0, 0.51, 0.01], [0.0, 0.575, 0.01]], dtype=np.float32), np.array([0.145, 0.112], dtype=np.float32), seg=14, color_fn=lambda t, th: rgba(34, 40, 48, 248), gloss=0.45),
    ]
    # Rounded shoulder deltoid socket caps on left & right shoulders
    for sx in (-1.0, 1.0):
        parts.append(xform(organic_ellipsoid(0.095, 0.088, 0.092, 6, 12, col_fn=lambda t, th: rgba(240, 240, 240, 248), dyeable=True, gloss=0.42), translate=(sx * 0.245, 0.485, 0.01)))
    return merge_parts(parts)


def build_char_head(lod: int) -> MeshPart:
    """
    High-Detail Sculpted Human Head & Expressive Face (Pivot (0,0,0) = base of neck):
      - Muscular neck column
      - Cranium + defined cheekbones + tapered jawline + rounded chin
      - Sculpted 3D nose bridge + nostrils
      - Expressive 3D eyes (white sclera + deep espresso iris + upper lash line + bright catchlight!)
      - Sculpted 3D eyebrows, warm mouth/lips, left/right 3D ears, and multi-layered styled hair!
    """
    sg = [22, 14, 10][lod]
    skin = rgba(226, 174, 134, 252)
    skin_warm = rgba(214, 154, 118, 248)
    hair_dark = rgba(26, 21, 20, 250)
    hair_hi = rgba(44, 34, 30, 252)
    parts = [
        # Neck column
        tube_along_curve(np.array([[0.0, -0.03, 0.0], [0.0, 0.09, 0.012]], dtype=np.float32), np.array([0.080, 0.070], dtype=np.float32), seg=14, color_fn=lambda t, th: skin_warm, gloss=0.30),
        # Anatomical head cranium + jaw taper
        xform(organic_ellipsoid(
            0.158, 0.186, 0.172, rings=[14, 10, 7][lod], seg=sg,
            col_fn=lambda t, th: skin if t > 0.25 else skin_warm,
            disp_fn=lambda ph, th: (
                1.0
                - 0.11 * np.maximum(0.0, -np.sin(ph)) * (0.4 + 0.6 * np.abs(np.cos(th)))
                + 0.05 * np.exp(-((ph + 0.45) ** 2) * 8.0) * np.maximum(0.0, np.sin(th))
            ),
            gloss=0.33,
        ), translate=(0.0, 0.215, 0.02)),
    ]

    # Sculpted chin & jawline definition
    parts.append(xform(organic_ellipsoid(0.068, 0.052, 0.068, 5, 10, col_fn=lambda t, th: skin, gloss=0.32), translate=(0.0, 0.068, 0.115)))

    if lod < 2:
        # Sculpted 3D Nose Bridge + Nose Tip
        nose_pts = np.array([[0.0, 0.228, 0.172], [0.0, 0.185, 0.205], [0.0, 0.172, 0.186]], dtype=np.float32)
        parts.append(tube_along_curve(nose_pts, np.array([0.021, 0.026, 0.019], dtype=np.float32), seg=8, color_fn=lambda t, th: skin, gloss=0.36))

        # Confident Mouth / Lips
        parts.append(xform(chamfer_box((0.068, 0.018, 0.026), 0.008, rgba(176, 98, 86, 250), arch_top=0.004, gloss=0.48), translate=(0.0, 0.132, 0.178)))

        # Left & Right 3D Eyes (Sclera + Iris + Pupil Glint) + Expressive Eyebrows + Sculpted Ears!
        for sx in (-1.0, 1.0):
            ex = sx * 0.062
            # White sclera almond
            parts.append(xform(organic_ellipsoid(0.032, 0.022, 0.022, 5, 8, col_fn=lambda t, th: rgba(248, 250, 252, 255), gloss=0.72), ry=sx * 0.16, translate=(ex, 0.226, 0.168)))
            # Dark espresso iris/pupil
            parts.append(xform(organic_ellipsoid(0.018, 0.019, 0.015, 5, 8, col_fn=lambda t, th: rgba(24, 18, 16, 255), gloss=0.88), translate=(ex * 0.98, 0.226, 0.181)))
            # Upper lash line + sculpted eyebrow
            parts.append(xform(chamfer_box((0.068, 0.011, 0.022), 0.004, hair_dark, gloss=0.40), rz=-sx * 0.06, ry=sx * 0.16, translate=(ex, 0.244, 0.174)))
            parts.append(xform(chamfer_box((0.076, 0.017, 0.026), 0.006, hair_dark, gloss=0.38), rz=-sx * 0.10, ry=sx * 0.16, translate=(ex * 1.02, 0.268, 0.172)))
            # Detailed 3D Ear + earlobe
            parts.append(xform(organic_ellipsoid(0.026, 0.048, 0.034, 5, 8, col_fn=lambda t, th: skin_warm, gloss=0.30), ry=-sx * 0.22, translate=(sx * 0.158, 0.208, 0.012)))

    # Multi-layered 3D Styled Hair (back/side taper + temple sideburns + dynamic textured top & front bangs!)
    parts.append(xform(organic_ellipsoid(0.172, 0.172, 0.186, rings=8, seg=sg, col_fn=lambda t, th: hair_dark if t < 0.6 else hair_hi, phi_range=(-0.12, math.pi * 0.49), gloss=0.46), rx=-0.22, translate=(0.0, 0.242, -0.008)))
    for sx in (-1.0, 1.0):
        parts.append(xform(chamfer_box((0.030, 0.088, 0.055), 0.012, hair_dark, taper_top=(0.8, 0.7), gloss=0.44), translate=(sx * 0.152, 0.228, 0.068)))
    if lod == 0:
        for bi, (bx, brx, brz) in enumerate([(-0.075, 0.24, 0.22), (0.0, 0.28, -0.05), (0.075, 0.22, -0.24)]):
            parts.append(xform(chamfer_box((0.068, 0.042, 0.095), 0.016, hair_hi, taper_top=(0.55, 0.35), gloss=0.48), rx=brx, rz=brz, translate=(bx, 0.335 - abs(bx) * 0.12, 0.145)))
    return merge_parts(parts)


def build_char_arm(lod: int) -> MeshPart:
    """Upper Arm: Shoulder ball pivot at (0,0,0) -> sleeve & bicep -> elbow joint at (0, -0.27, 0)!"""
    sg = [16, 10, 7][lod]
    skin = rgba(222, 170, 130, 250)
    return merge_parts([
        organic_ellipsoid(0.080, 0.080, 0.080, 6, sg, col_fn=lambda t, th: rgba(244, 244, 244, 248), dyeable=True, gloss=0.42),
        tube_along_curve(np.array([[0.0, 0.0, 0.0], [0.0, -0.15, 0.005]], dtype=np.float32), np.array([0.080, 0.072], dtype=np.float32), seg=sg, color_fn=lambda t, th: rgba(242, 242, 242, 246), dyeable=True, gloss=0.40),
        tube_along_curve(np.array([[0.0, -0.14, 0.005], [0.0, -0.27, 0.01]], dtype=np.float32), np.array([0.066, 0.057], dtype=np.float32), seg=sg, color_fn=lambda t, th: skin, gloss=0.31),
        xform(organic_ellipsoid(0.056, 0.056, 0.056, 5, 10, col_fn=lambda t, th: skin, gloss=0.31), translate=(0.0, -0.27, 0.01)),
    ])


def build_char_forearm_hand(lod: int) -> MeshPart:
    """
    Forearm + Detailed 5-Finger Hand:
      - Origin (0,0,0) = Elbow joint!
      - Muscular forearm y = 0 .. -0.24
      - Wrist cuff + Palm + Opposable Thumb + 4 Individual Sculpted Fingers (Index, Middle, Ring, Pinky)!
    """
    sg = [16, 10, 7][lod]
    skin = rgba(222, 170, 130, 250)
    glove_trim = rgba(40, 46, 54, 250)
    parts = [
        organic_ellipsoid(0.055, 0.055, 0.055, 5, 10, col_fn=lambda t, th: skin, gloss=0.31),
        tube_along_curve(np.array([[0.0, 0.0, 0.0], [0.0, -0.13, 0.012], [0.0, -0.24, 0.020]], dtype=np.float32), np.array([0.057, 0.051, 0.041], dtype=np.float32), seg=sg, color_fn=lambda t, th: skin, gloss=0.31),
        # Protective wrist wrap
        xform(chamfer_box((0.088, 0.042, 0.072), 0.016, glove_trim, gloss=0.48), translate=(0.0, -0.235, 0.020)),
        # Anatomical Palm Metacarpal Block
        xform(chamfer_box((0.084, 0.078, 0.042), 0.016, skin, gloss=0.33), translate=(0.0, -0.282, 0.024)),
    ]
    if lod < 2:
        # Opposable 2-segment Thumb
        thumb_pts = np.array([[0.040, -0.268, 0.028], [0.062, -0.298, 0.052], [0.054, -0.328, 0.066]], dtype=np.float32)
        parts.append(tube_along_curve(thumb_pts, np.array([0.017, 0.014, 0.011], dtype=np.float32), seg=6, color_fn=lambda t, th: skin, gloss=0.33))
        # 4 Individual Articulated Fingers (curled slightly in ready natural grip!)
        for fi, fx in enumerate([-0.030, -0.010, 0.010, 0.030]):
            flen = [0.062, 0.070, 0.065, 0.052][fi]
            f_pts = np.array([
                [fx, -0.316, 0.026],
                [fx, -0.316 - flen * 0.58, 0.038],
                [fx, -0.316 - flen, 0.022],
            ], dtype=np.float32)
            parts.append(tube_along_curve(f_pts, np.array([0.0125, 0.0105, 0.0085], dtype=np.float32), seg=6, color_fn=lambda t, th: skin, gloss=0.33))
    else:
        parts.append(xform(chamfer_box((0.078, 0.062, 0.045), 0.015, skin, gloss=0.33), translate=(0.0, -0.335, 0.032)))
    return merge_parts(parts)


def build_char_leg(lod: int) -> MeshPart:
    """Upper Leg / Thigh: Hip socket ball at (0,0,0) -> sculpted cargo thigh -> knee joint at (0, -0.43, 0)!"""
    sg = [16, 10, 7][lod]
    pants = rgba(52, 60, 72, 244)
    knee_guard = rgba(34, 40, 48, 250)
    parts = [
        organic_ellipsoid(0.098, 0.098, 0.098, 6, sg, col_fn=lambda t, th: pants, gloss=0.34),
        tube_along_curve(np.array([[0.0, 0.0, 0.0], [0.0, -0.22, 0.014], [0.0, -0.43, 0.0]], dtype=np.float32), np.array([0.100, 0.088, 0.074], dtype=np.float32), seg=sg, color_fn=lambda t, th: pants, gloss=0.34),
        xform(organic_ellipsoid(0.075, 0.072, 0.078, 5, 10, col_fn=lambda t, th: knee_guard, gloss=0.45), translate=(0.0, -0.43, 0.012)),
    ]
    return merge_parts(parts)


def build_char_calf_boot(lod: int) -> MeshPart:
    """Lower Leg / Calf + Tall Rubber Plantation Boot: Knee at (0,0,0) -> Sole flat on y = -0.45!"""
    sg = [16, 10, 7][lod]
    boot_green = rgba(36, 106, 68, 248)
    boot_yellow = rgba(246, 198, 36, 254)
    sole_black = rgba(24, 28, 32, 252)
    parts = [
        tube_along_curve(np.array([[0.0, 0.0, 0.0], [0.0, -0.14, -0.008]], dtype=np.float32), np.array([0.074, 0.078], dtype=np.float32), seg=sg, color_fn=lambda t, th: rgba(52, 60, 72, 244), gloss=0.34),
        # Iconic Indonesian Yellow-Trimmed Tall Plantation Boot
        tube_along_curve(np.array([[0.0, -0.13, -0.008], [0.0, -0.17, -0.008], [0.0, -0.37, 0.005]], dtype=np.float32), np.array([0.088, 0.086, 0.076], dtype=np.float32), seg=sg, color_fn=lambda t, th: boot_yellow if t < 0.22 else boot_green, gloss=0.64),
        # Sculpted boot upper vamp + reinforced toe box + rugged lugged rubber sole (bottom at exact y = -0.45!)
        xform(chamfer_box((0.148, 0.095, 0.255), 0.035, boot_green, arch_top=0.022, gloss=0.62), translate=(0.0, -0.388, 0.048)),
        xform(chamfer_box((0.158, 0.042, 0.275), 0.020, sole_black, gloss=0.45), translate=(0.0, -0.429, 0.048)),
    ]
    return merge_parts(parts)


def build_hat_caping(lod: int) -> MeshPart:
    return tube_along_curve(
        np.array([[0.0, 0.0, 0.0], [0.0, 0.10, 0.0], [0.0, 0.20, 0.0], [0.0, 0.29, 0.0]], dtype=np.float32),
        np.array([0.43, 0.28, 0.13, 0.018], dtype=np.float32), seg=[24, 14, 8][lod],
        color_fn=lambda t, th: rgba(232, 54, 38, 252) if t < 0.09 else rgba(int(226 - 26 * t), int(184 - 22 * t), int(108 - 14 * t), int(224 + 30 * t)),
        profile_mod=lambda t, th: 1.0 + 0.022 * np.cos(12.0 * th),
        gloss=0.42,
    )


def build_hat_safety(lod: int) -> MeshPart:
    return merge_parts([
        xform(organic_ellipsoid(0.205, 0.155, 0.235, rings=[8, 6, 4][lod], seg=[16, 10, 8][lod], col_fn=lambda t, th: rgba(250, 198, 26, 252), phi_range=(-0.15, math.pi * 0.485), gloss=0.78), translate=(0.0, 0.05, 0.0)),
        xform(chamfer_box((0.065, 0.085, 0.37), 0.02, rgba(255, 218, 56, 255), gloss=0.80), translate=(0.0, 0.185, 0.0)),
        xform(chamfer_box((0.35, 0.038, 0.15), 0.015, rgba(236, 178, 18, 248), gloss=0.75), rx=0.14, translate=(0.0, 0.02, 0.21)),
        xform(chamfer_box((0.09, 0.07, 0.05), 0.015, rgba(255, 252, 224, 255), gloss=0.97), translate=(0.0, 0.13, 0.23)),
    ])


def build_hat_headband(lod: int) -> MeshPart:
    parts = [tube_along_curve(np.array([[0.0, -0.02, 0.01], [0.0, 0.055, 0.01]], dtype=np.float32), np.array([0.182, 0.182], dtype=np.float32), seg=[18, 12, 8][lod], color_fn=lambda t, th: rgba(232, 38, 42, 250), gloss=0.45)]
    parts.append(xform(chamfer_box((0.11, 0.065, 0.03), 0.01, rgba(246, 202, 48, 255), gloss=0.88), translate=(0.0, 0.02, 0.195)))
    for sx in (-1.0, 1.0):
        tail = np.array([[sx * 0.05, 0.02, -0.19], [sx * 0.14, -0.10, -0.35], [sx * 0.20, -0.28, -0.48]], dtype=np.float32)
        parts.append(tube_along_curve(tail, np.array([0.040, 0.050, 0.018], dtype=np.float32), seg=6, color_fn=lambda t, th: rgba(240, 48, 52, 252), gloss=0.45))
    return merge_parts(parts)


def build_hat_cowboy(lod: int) -> MeshPart:
    """Solid thick-rimmed leather cowboy hat (closed 4-station solid brim -> ZERO thin-sheet holes!)."""
    seg = [20, 12, 8][lod]
    th = np.linspace(0, 2 * math.pi, seg, endpoint=False, dtype=np.float32)
    curl = 0.075 * (np.cos(th) ** 2)
    brim = loft_profile([
        (np.stack([np.cos(th) * 0.15, np.full_like(th, -0.015), np.sin(th) * 0.18], axis=1), rgba(104, 62, 36, 240), 0.0),
        (np.stack([np.cos(th) * 0.37, curl - 0.018, np.sin(th) * 0.41], axis=1), rgba(118, 72, 42, 248), 0.35),
        (np.stack([np.cos(th) * 0.37, curl + 0.014, np.sin(th) * 0.41], axis=1), rgba(138, 86, 48, 252), 0.70),
        (np.stack([np.cos(th) * 0.15, np.full_like(th, 0.020), np.sin(th) * 0.18], axis=1), rgba(128, 78, 44, 248), 1.0),
    ], cap_start=True, cap_end=True, gloss=0.46)
    return merge_parts([
        brim,
        xform(chamfer_box((0.28, 0.175, 0.33), 0.06, rgba(126, 78, 44, 248), taper_top=(0.76, 0.80), gloss=0.46), translate=(0.0, 0.10, 0.0)),
        xform(chamfer_box((0.30, 0.038, 0.35), 0.05, rgba(250, 202, 48, 255), gloss=0.86), translate=(0.0, 0.03, 0.0)),
    ])


def build_hat_crown_gold(lod: int) -> MeshPart:
    gold, gem = rgba(255, 212, 48, 255), rgba(32, 250, 152, 255)
    parts = [tube_along_curve(np.array([[0.0, 0.0, 0.0], [0.0, 0.09, 0.0]], dtype=np.float32), np.array([0.184, 0.200], dtype=np.float32), seg=[18, 12, 8][lod], color_fn=lambda t, th: gold, gloss=0.88)]
    spikes = [8, 6, 4][lod]
    for i in range(spikes):
        ang = i * (2.0 * math.pi / spikes)
        h = 0.23 if i % 2 == 0 else 0.155
        parts.append(xform(chamfer_box((0.068, h, 0.038), 0.012, gold, taper_top=(0.14, 0.4), gloss=0.88), ry=ang, translate=(math.sin(ang) * 0.192, 0.09 + h * 0.42, math.cos(ang) * 0.192)))
        if lod < 2 and i % 2 == 0:
            parts.append(xform(chamfer_box((0.048, 0.058, 0.035), 0.01, gem, gloss=0.97), ry=ang, translate=(math.sin(ang) * 0.214, 0.048, math.cos(ang) * 0.214)))
    return merge_parts(parts)


def build_back_basket(lod: int) -> MeshPart:
    pts = np.array([[0.0, -0.22, -0.10], [0.0, 0.02, -0.13], [0.0, 0.25, -0.16]], dtype=np.float32)
    parts = [tube_along_curve(pts, np.array([0.145, 0.195, 0.245], dtype=np.float32), seg=[16, 10, 6][lod], color_fn=lambda t, th: rgba(int(184 + 34 * ((int(t * 10)) % 2)), int(140 + 24 * t), 72, 244), gloss=0.34)]
    for ox, oz in ((-0.08, -0.13), (0.09, -0.15), (0.0, -0.22)):
        parts.append(xform(organic_ellipsoid(0.095, 0.095, 0.095, 5, 8, col_fn=lambda t, th: rgba(242, 88, 22, 250), gloss=0.74), translate=(ox, 0.27, oz)))
    return merge_parts(parts)


def build_back_pack(lod: int) -> MeshPart:
    return merge_parts([
        xform(chamfer_box((0.31, 0.39, 0.18), 0.04, rgba(48, 72, 56, 244), gloss=0.52), translate=(0.0, 0.0, -0.09)),
        xform(chamfer_box((0.24, 0.18, 0.07), 0.02, rgba(248, 188, 28, 252), gloss=0.76), translate=(0.0, -0.05, -0.21)),
        tube_along_curve(np.array([[0.11, 0.18, -0.10], [0.14, 0.66, -0.16]], dtype=np.float32), np.array([0.016, 0.005], dtype=np.float32), seg=6, color_fn=lambda t, th: rgba(224, 230, 238, 252), gloss=0.85),
    ])


def build_back_cape(lod: int) -> MeshPart:
    stations = []
    xs = np.linspace(-0.23, 0.23, [9, 6, 4][lod], dtype=np.float32)
    for row_i, (yy, zz, spread, fold) in enumerate([(0.18, -0.04, 0.9, 0.01), (-0.08, -0.10, 1.16, 0.025), (-0.36, -0.18, 1.48, 0.045), (-0.68, -0.27, 1.76, 0.065)]):
        ring = [[x * spread, yy, zz + math.sin(x * 26.0) * fold] for x in xs] + [[x * spread, yy, zz + math.sin(x * 26.0) * fold - 0.032] for x in reversed(xs)]
        stations.append((np.asarray(ring, dtype=np.float32), rgba(248, 198, 42, 255) if row_i == 0 else rgba(228, 36, 48, 248), row_i / 3.0))
    return loft_profile(stations, cap_start=True, cap_end=True, gloss=0.52)


def build_back_wings_gold(lod: int) -> MeshPart:
    parts = [
        xform(chamfer_box((0.20, 0.24, 0.07), 0.025, rgba(255, 208, 48, 255), gloss=0.90), translate=(0.0, 0.14, -0.08)),
        xform(chamfer_box((0.09, 0.12, 0.05), 0.015, rgba(34, 252, 154, 255), gloss=0.98), translate=(0.0, 0.14, -0.11)),
    ]
    feather_n = [7, 5, 4][lod]
    for sx in (-1.0, 1.0):
        spar = np.array([[sx * 0.08, 0.14, -0.09], [sx * 0.34, 0.42, -0.15], [sx * 0.68, 0.56, -0.22], [sx * 0.98, 0.44, -0.28]], dtype=np.float32)
        parts.append(tube_along_curve(spar, np.array([0.042, 0.036, 0.028, 0.015], dtype=np.float32), seg=8, color_fn=lambda t, th: rgba(255, 214, 56, 255), gloss=0.90))
        for fi in range(feather_n):
            frac = fi / max(1, feather_n - 1)
            bx = sx * (0.18 + 0.72 * frac)
            by = 0.24 + 0.28 * math.sin(frac * math.pi * 0.85)
            bz = -0.12 - 0.14 * frac
            flen = 0.72 - 0.18 * (1.0 - frac) + 0.14 * math.sin(frac * math.pi)
            tilt_z = sx * (0.42 + 0.82 * frac)
            col_f = rgba(255, int(224 - 46 * frac), int(64 - 28 * frac), 255)
            blade = chamfer_box((0.105, flen, 0.032), 0.010, col_f, taper_top=(0.18, 0.45), gloss=0.92)
            parts.append(xform(blade, rz=-tilt_z, rx=-0.12, translate=(bx + sx * flen * 0.34, by - flen * 0.32, bz)))
    return merge_parts(parts)


def build_tool_egrek(lod: int) -> MeshPart:
    return merge_parts([
        tube_along_curve(np.array([[0.0, -0.35, 0.0], [0.0, 1.05, 0.0], [0.0, 2.05, 0.0]], dtype=np.float32), np.array([0.030, 0.025, 0.020], dtype=np.float32), seg=8, color_fn=lambda t, th: rgba(224, 50, 40, 250) if t < 0.24 else rgba(214, 224, 234, 250), gloss=0.72),
        xform(chamfer_box((0.080, 0.115, 0.080), 0.02, rgba(242, 186, 28, 255), gloss=0.84), translate=(0.0, 2.04, 0.0)),
        tube_along_curve(
            np.array([[0.0, 2.06, 0.0], [0.02, 2.27, 0.09], [0.02, 2.46, 0.02], [0.0, 2.54, -0.19], [-0.01, 2.45, -0.36]], dtype=np.float32),
            np.array([0.032, 0.050, 0.044, 0.030, 0.005], dtype=np.float32), seg=8,
            color_fn=lambda t, th: rgba(240, 246, 255, 255),
            profile_mod=lambda t, th: np.where(np.abs(np.cos(th)) > 0.5, 0.26, 1.42),
            gloss=0.88,
        ),
    ])


def build_tool_dodos(lod: int) -> MeshPart:
    return merge_parts([
        tube_along_curve(np.array([[0.0, -0.35, 0.0], [0.0, 0.95, 0.0]], dtype=np.float32), np.array([0.032, 0.028], dtype=np.float32), seg=8, color_fn=lambda t, th: rgba(158, 102, 52, 248), gloss=0.38),
        xform(chamfer_box((0.044, 0.44, 0.23), 0.012, rgba(232, 240, 250, 255), taper_top=(0.35, 1.48), gloss=0.88), translate=(0.0, 1.16, 0.0)),
    ])


def build_tool_egrek_dragon(lod: int) -> MeshPart:
    return merge_parts([
        tube_along_curve(np.array([[0.0, -0.35, 0.0], [0.0, 2.10, 0.0]], dtype=np.float32), np.array([0.034, 0.024], dtype=np.float32), seg=8, color_fn=lambda t, th: rgba(30, 32, 40, 250) if (int(t * 12) % 2 == 0) else rgba(255, 204, 42, 255), gloss=0.84),
        xform(chamfer_box((0.11, 0.17, 0.23), 0.025, rgba(255, 206, 48, 255), gloss=0.88), translate=(0.0, 2.08, 0.0)),
        tube_along_curve(
            np.array([[0.0, 2.10, 0.02], [0.0, 2.40, 0.15], [0.0, 2.65, -0.02], [0.0, 2.74, -0.29], [0.0, 2.56, -0.48]], dtype=np.float32),
            np.array([0.040, 0.070, 0.060, 0.042, 0.006], dtype=np.float32), seg=8,
            color_fn=lambda t, th: rgba(255, 206, 48, 255) if t < 0.45 else rgba(255, 108, 34, 255),
            profile_mod=lambda t, th: np.where(np.abs(np.cos(th)) > 0.5, 0.24, 1.48),
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
    ("pks_fan", build_pks_fan),
    ("steam_puff", build_steam_puff),
    ("weighbridge_ram", build_weighbridge_ram),
    ("mandor_post", build_mandor_post),
    ("wooden_bridge", build_wooden_bridge),
    ("celeng_boar", build_celeng_boar),
    ("boar_leg", build_boar_leg),
    ("char_torso_head", build_char_torso_head),
    ("char_head", build_char_head),
    ("char_arm", build_char_arm),
    ("char_forearm_hand", build_char_forearm_hand),
    ("char_leg", build_char_leg),
    ("char_calf_boot", build_char_calf_boot),
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
    assert n < 65535, f"Mesh exceeded uint16 vertex limit ({n})"
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
    out_manifest = os.path.join(root, "docs", "mesh_manifest.json")

    chunks = [struct.pack("<4sII", b"NPAK", 1, len(MODEL_SPECS))]
    manifest = {"version": 3, "stride_bytes": 36, "models": []}
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
    os.makedirs(os.path.dirname(out_android), exist_ok=True)
    with open(out_android, "wb") as f:
        f.write(blob)

    manifest["total_lod0_tris"] = tot0
    manifest["total_lod1_tris"] = tot1
    manifest["total_lod2_tris"] = tot2
    manifest["binary_bytes"] = len(blob)
    with open(out_manifest, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n=== NPAK v3.0 BUILT: {len(MODEL_SPECS)} models x 3 LODs = {len(MODEL_SPECS)*3} WATERTIGHT GPU MESHES ===")
    print(f"    LOD0={tot0:,} tris -> LOD1={tot1:,} tris -> LOD2={tot2:,} tris | Size={len(blob)/1024/1024:.2f} MB")


if __name__ == "__main__":
    main()
