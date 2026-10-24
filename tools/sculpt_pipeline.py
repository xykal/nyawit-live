#!/usr/bin/env python3
"""
Nyawit Live 3D v4.0 — Realistic UV-Mapped PBR 3D Asset & Anatomy Sculpt Pipeline

Builds 57 precision UV-mapped 3D models x 3 LODs = 171 GPU meshes mapped onto the
2048x2048 RGBA8 PBR & Alpha-Cutout Texture Atlas (Assets/Textures/nyawit_pbr_atlas.png):
  - Authentic Indonesian Cab-Over-Engine (COE) Mitsubishi Fuso Canter FE 74 HD Bak Kayu
    (curved flat-nose COE cab, raked reflective windshield + wipers, dipped door window,
     chrome honeycomb 3-diamond grille, crystal swept-back headlamps + amber signals,
     BM 8899 XY plate, amber fog lights, dual bracket mirrors, tall Kepala Bak header,
      bolted Meranti wood planks with white/red reflective tape, black C-channel steel frame,
     GS battery box, fuel tank, mudflaps, interior dashboard & rotatable 3D steering wheel)
  - 6-Lug Heavy-Duty Radial Off-Road Truck Tire & Recessed Gunmetal Steel Wheel Rim
  - Seamless Organic Ball-Jointed 11-Part Human Anatomy + Complete Indonesian Accessories
    (Caping Bambu, Helm Safety Proyek, Topi Rimba, Ikat Kepala, Mahkota Sultan,
     Kacamata Hitam Wrap-Around, Parang/Golok Pinggang, Keranjang Rotan Sawit, Ransel Lapangan,
     Jubah, Sayap Garuda Emas, Egrek Baja Melengkung, Dodos Baja Lebar, Tojok Pengait TBS)
  - Botanical Elaeis guineensis Tenera Oil Palm (diamond petiole bark + epiphytic trunk ferns
     + 26 arching V-folded alpha-cutout pinnate fronds with 88 leaflets each — 75% fewer tris!)
  - Photorealistic Spiky Ripe TBS Fruit Bunch & Roadside TPH Stack
  - Dedicated 3D Tropical Plantation Garage / Workshop Showroom Scene (100% separate Lobby!)
"""

from __future__ import annotations
import json
import math
import os
import struct
from dataclasses import dataclass
from typing import Callable, List, Tuple
import numpy as np

# ── Exact UV Rectangles inside 2048x2048 nyawit_pbr_atlas.png (u0, v0, u1, v1) ──
UV_GRASS           = (0.002, 0.002, 0.248, 0.248)
UV_DIRT            = (0.252, 0.002, 0.498, 0.248)
UV_PALM_BARK       = (0.502, 0.002, 0.748, 0.248)
UV_TBS_FRUIT       = (0.752, 0.002, 0.998, 0.248)

UV_PALM_FROND      = (0.001, 0.251, 0.249, 0.499)
UV_FERN            = (0.251, 0.251, 0.499, 0.499)
UV_WOOD_BAK        = (0.502, 0.252, 0.748, 0.498)
UV_WOOD_PLAIN      = (0.502, 0.252, 0.748, 0.365)
UV_TIRE_TREAD      = (0.752, 0.252, 0.873, 0.498)
UV_WHEEL_CENTER    = (0.9375, 0.375, 0.0605)  # (cx, cy, radius)

UV_CANTER_GLASS    = (0.003, 0.503, 0.247, 0.622)
UV_CANTER_SIDE_GLS = (0.010, 0.506, 0.240, 0.590)
UV_CANTER_GRILLE   = (0.003, 0.626, 0.123, 0.694)
UV_CANTER_HEADLAMP = (0.126, 0.626, 0.248, 0.694)
UV_CANTER_PLATE    = (0.002, 0.696, 0.165, 0.748)
UV_CANTER_FOGLAMP  = (0.168, 0.696, 0.248, 0.748)
UV_CANTER_PAINT    = (0.254, 0.504, 0.415, 0.655)
UV_CANTER_HANDLE   = (0.418, 0.662, 0.474, 0.694)

UV_FACE            = (0.502, 0.502, 0.623, 0.623)
UV_HAIR            = (0.627, 0.502, 0.748, 0.623)
UV_SKIN            = (0.502, 0.627, 0.623, 0.748)
UV_DENIM           = (0.627, 0.627, 0.748, 0.748)

UV_SHIRT_FRONT     = (0.752, 0.502, 0.873, 0.623)
UV_SHIRT_PLAIN     = (0.754, 0.568, 0.812, 0.622)
UV_WOVEN           = (0.877, 0.502, 0.998, 0.623)
UV_BOOT            = (0.752, 0.627, 0.873, 0.748)
UV_STEEL           = (0.877, 0.627, 0.998, 0.748)

UV_CORRUGATED      = (0.002, 0.752, 0.248, 0.998)
UV_CONCRETE        = (0.252, 0.752, 0.498, 0.998)
UV_CONCRETE_CLEAN  = (0.254, 0.754, 0.496, 0.955)
UV_ROCK            = (0.502, 0.752, 0.748, 0.998)
UV_PUFF_ALPHA      = (0.752, 0.752, 0.998, 0.998)


@dataclass
class MeshPart:
    pos: np.ndarray
    uv: np.ndarray
    col: np.ndarray
    idx: np.ndarray
    nrm: np.ndarray | None = None


def rgba(r: int = 255, g: int = 255, b: int = 255, gloss: int = 90) -> np.ndarray:
    return np.array([int(np.clip(r, 0, 255)), int(np.clip(g, 0, 255)), int(np.clip(b, 0, 255)), int(np.clip(gloss, 0, 255))], dtype=np.uint8)


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


def map_uv(uv01: np.ndarray, rect: Tuple[float, float, float, float], dyeable: bool = False) -> np.ndarray:
    u0, v0, u1, v1 = rect
    out = np.empty_like(uv01, dtype=np.float32)
    out[:, 0] = u0 + np.clip(uv01[:, 0], 0.0, 1.0) * (u1 - u0) + (2.0 if dyeable else 0.0)
    out[:, 1] = v0 + np.clip(uv01[:, 1], 0.0, 1.0) * (v1 - v0)
    return out


def make_quad(p0, p1, p2, p3, uv_rect, col=None, dyeable=False, flip_u=False, flip_v=False, double_sided=False) -> MeshPart:
    c = rgba(255, 255, 255, 95) if col is None else col
    pos = np.array([p0, p1, p2, p3], dtype=np.float32)
    u_a, u_b = (1.0, 0.0) if flip_u else (0.0, 1.0)
    v_a, v_b = (0.0, 1.0) if flip_v else (1.0, 0.0)
    # p0=bottom-left, p1=bottom-right, p2=top-right, p3=top-left
    uv01 = np.array([[u_a, v_a], [u_b, v_a], [u_b, v_b], [u_a, v_b]], dtype=np.float32)
    uv = map_uv(uv01, uv_rect, dyeable=dyeable)
    cols = np.broadcast_to(c, (4, 4)).copy()
    tris = [[0, 1, 2], [0, 2, 3]]
    if double_sided:
        pos = np.vstack([pos, pos])
        uv = np.vstack([uv, uv])
        cols = np.vstack([cols, cols])
        tris.extend([[4, 6, 5], [4, 7, 6]])
    return MeshPart(pos, uv, cols, np.array(tris, dtype=np.int32))


def make_bevel_box(sx: float, sy: float, sz: float, uv_rect, col=None, dyeable=False, center=(0.0, 0.0, 0.0), bev: float = 0.022) -> MeshPart:
    """True 3D beveled hard-surface box (catches real specular & rim highlights on every chamfered edge just like Blender BevelModifier!)."""
    b = min(bev, sx * 0.28, sy * 0.28, sz * 0.28)
    hx, hy, hz = sx * 0.5, sy * 0.5, sz * 0.5
    cx, cy, cz = center
    c = rgba(255, 255, 255, 95) if col is None else col
    stations = [
        (-hy,       hx - b, hz - b),
        (-hy + b,   hx,     hz),
        ( hy - b,   hx,     hz),
        ( hy,       hx - b, hz - b),
    ]
    rings = []
    for y_off, wx, wz in stations:
        cb = b * 0.85
        pts = [
            (cx - wx + cb, cy + y_off, cz + wz), (cx + wx - cb, cy + y_off, cz + wz),
            (cx + wx,      cy + y_off, cz + wz - cb), (cx + wx, cy + y_off, cz - wz + cb),
            (cx + wx - cb, cy + y_off, cz - wz), (cx - wx + cb, cy + y_off, cz - wz),
            (cx - wx,      cy + y_off, cz - wz + cb), (cx - wx, cy + y_off, cz + wz - cb),
        ]
        rings.append(np.array(pts, dtype=np.float32))
    return make_loft(rings, uv_rect, col=c, dyeable=dyeable, cap_start=True, cap_end=True)


def make_box(sx: float, sy: float, sz: float, uv_rect, col=None, dyeable=False, center=(0.0, 0.0, 0.0)) -> MeshPart:
    hx, hy, hz = sx * 0.5, sy * 0.5, sz * 0.5
    cx, cy, cz = center
    c = rgba(255, 255, 255, 90) if col is None else col
    faces = [
        # +Z front
        make_quad((cx - hx, cy - hy, cz + hz), (cx + hx, cy - hy, cz + hz), (cx + hx, cy + hy, cz + hz), (cx - hx, cy + hy, cz + hz), uv_rect, c, dyeable),
        # -Z back
        make_quad((cx + hx, cy - hy, cz - hz), (cx - hx, cy - hy, cz - hz), (cx - hx, cy + hy, cz - hz), (cx + hx, cy + hy, cz - hz), uv_rect, c, dyeable),
        # +X right
        make_quad((cx + hx, cy - hy, cz + hz), (cx + hx, cy - hy, cz - hz), (cx + hx, cy + hy, cz - hz), (cx + hx, cy + hy, cz + hz), uv_rect, c, dyeable),
        # -X left
        make_quad((cx - hx, cy - hy, cz - hz), (cx - hx, cy - hy, cz + hz), (cx - hx, cy + hy, cz + hz), (cx - hx, cy + hy, cz - hz), uv_rect, c, dyeable),
        # +Y top
        make_quad((cx - hx, cy + hy, cz + hz), (cx + hx, cy + hy, cz + hz), (cx + hx, cy + hy, cz - hz), (cx - hx, cy + hy, cz - hz), uv_rect, c, dyeable),
        # -Y bottom
        make_quad((cx - hx, cy - hy, cz - hz), (cx + hx, cy - hy, cz - hz), (cx + hx, cy - hy, cz + hz), (cx - hx, cy - hy, cz + hz), uv_rect, c, dyeable),
    ]
    return merge_parts(faces)


def make_loft(
    rings_xyz: List[np.ndarray],
    uv_rect: Tuple[float, float, float, float],
    col=None,
    dyeable: bool = False,
    cap_start: bool = True,
    cap_end: bool = True,
    u_rep: float = 1.0,
    v_rep: float = 1.0,
) -> MeshPart:
    """Watertight seam-wrapped UV loft across N cross-section rings of M points (+1 seam vertex)."""
    c = rgba(255, 255, 255, 90) if col is None else col
    n_rings = len(rings_xyz)
    seg = len(rings_xyz[0])
    pos_rows, uv_rows = [], []

    for ri, ring in enumerate(rings_xyz):
        v_raw = (1.0 - (ri / max(1, n_rings - 1)) * v_rep) % 1.00001
        if ri == n_rings - 1 and v_rep == 1.0:
            v_raw = 0.0
        # Duplicate vertex 0 at seam (u = 1.0) so cylindrical UVs NEVER wrap backwards across back triangle!
        ring_closed = np.vstack([ring, ring[0:1]])
        u_vals = np.linspace(0.0, 1.0, seg + 1, dtype=np.float32) * u_rep
        if u_rep > 1.0:
            u_vals = np.mod(u_vals, 1.0)
            u_vals[-1] = 1.0
        v_vals = np.full(seg + 1, v_raw, dtype=np.float32)
        pos_rows.append(ring_closed.astype(np.float32))
        uv_rows.append(map_uv(np.stack([u_vals, v_vals], axis=1), uv_rect, dyeable=dyeable))

    pos_a = np.vstack(pos_rows)
    uv_a = np.vstack(uv_rows)
    tris = []
    stride = seg + 1
    for ri in range(n_rings - 1):
        b0 = ri * stride
        b1 = (ri + 1) * stride
        for j in range(seg):
            tris.append([b0 + j, b0 + j + 1, b1 + j + 1])
            tris.append([b0 + j, b1 + j + 1, b1 + j])

    extra_pos, extra_uv = [], []
    base_idx = len(pos_a)
    if cap_start:
        c0 = rings_xyz[0].mean(axis=0)
        extra_pos.append(c0)
        extra_uv.append(map_uv(np.array([[0.5, 0.98]], np.float32), uv_rect, dyeable)[0])
        ci = base_idx + len(extra_pos) - 1
        for j in range(seg):
            tris.append([ci, j + 1, j])
    if cap_end:
        c1 = rings_xyz[-1].mean(axis=0)
        extra_pos.append(c1)
        extra_uv.append(map_uv(np.array([[0.5, 0.02]], np.float32), uv_rect, dyeable)[0])
        ci = base_idx + len(extra_pos) - 1
        top_b = (n_rings - 1) * stride
        for j in range(seg):
            tris.append([ci, top_b + j, top_b + j + 1])

    if extra_pos:
        pos_a = np.vstack([pos_a, np.array(extra_pos, np.float32)])
        uv_a = np.vstack([uv_a, np.array(extra_uv, np.float32)])

    idx_a = np.array(tris, dtype=np.int32)
    # Outward winding check (closed signed-volume OR open radial normal check) for clean GL_FRONT anime outlines!
    if len(idx_a) >= 4:
        v0, v1, v2 = pos_a[idx_a[:, 0]], pos_a[idx_a[:, 1]], pos_a[idx_a[:, 2]]
        if cap_start and cap_end:
            vol6 = float(np.sum(np.einsum("ij,ij->i", v0, np.cross(v1, v2))))
            if vol6 < 0.0:
                idx_a = idx_a[:, [0, 2, 1]]
        else:
            axis_ctr = np.mean(np.stack([r.mean(axis=0) for r in rings_xyz], axis=0), axis=0)
            fn = np.cross(v1 - v0, v2 - v0)
            rad_vec = ((v0 + v1 + v2) / 3.0) - axis_ctr[None, :]
            if float(np.sum(np.einsum("ij,ij->i", fn, rad_vec))) < 0.0:
                idx_a = idx_a[:, [0, 2, 1]]

    cols = np.broadcast_to(c, (len(pos_a), 4)).copy()
    return MeshPart(pos_a, uv_a, cols, idx_a)


def ring_ellipse(rx: float, rz: float, y: float, seg: int, cx: float = 0.0, cz: float = 0.0, phase: float = 0.0) -> np.ndarray:
    # Angle 0 points along +Z (front face sits cleanly centered at u = 0.5!)
    # Wait: make angle -pi..+pi map u=0..1 so u=0.5 is EXACTLY +Z (front face)!
    ang = np.linspace(-math.pi, math.pi, seg, endpoint=False, dtype=np.float32) + phase
    return np.stack([cx + np.sin(ang) * rx, np.full_like(ang, y), cz + np.cos(ang) * rz], axis=1)


def make_sphere_uv(rx: float, ry: float, rz: float, uv_rect, seg: int = 14, rings: int = 9, col=None, dyeable=False, center=(0.0, 0.0, 0.0)) -> MeshPart:
    cx, cy, cz = center
    rs = []
    for i in range(rings):
        t = (i / (rings - 1) - 0.5) * math.pi * 0.97
        ct, st = math.cos(t), math.sin(t)
        rs.append(ring_ellipse(rx * ct, rz * ct, cy + st * ry, seg, cx=cx, cz=cz))
    return make_loft(rs, uv_rect, col=col, dyeable=dyeable, cap_start=True, cap_end=True)


def make_tube_segment(p0, p1, r0: float, r1: float, uv_rect, seg: int = 10, col=None, dyeable=False, ball_caps=True) -> MeshPart:
    p0 = np.asarray(p0, np.float32)
    p1 = np.asarray(p1, np.float32)
    d = p1 - p0
    length = float(np.linalg.norm(d))
    if length < 1e-5:
        return make_sphere_uv(r0, r0, r0, uv_rect, seg=seg, rings=6, col=col, dyeable=dyeable, center=tuple(p0))
    up = d / length
    ref = np.array([0.0, 0.0, 1.0], np.float32) if abs(up[2]) < 0.92 else np.array([1.0, 0.0, 0.0], np.float32)
    side = np.cross(ref, up)
    side /= np.linalg.norm(side)
    fwd = np.cross(up, side)

    steps = [(-0.35 * r0, 0.35 * r0), (0.0, r0), (0.35 * length, r0 * 0.72 + r1 * 0.28),
             (0.72 * length, r0 * 0.30 + r1 * 0.70), (length, r1), (length + 0.35 * r1, 0.35 * r1)] if ball_caps else [
             (0.0, r0), (0.5 * length, 0.5 * (r0 + r1)), (length, r1)]
    ang = np.linspace(-math.pi, math.pi, seg, endpoint=False, dtype=np.float32)
    rings = []
    for s_dist, rad in steps:
        ctr = p0 + up * s_dist
        pts = ctr[None, :] + (np.sin(ang)[:, None] * side[None, :] + np.cos(ang)[:, None] * fwd[None, :]) * rad
        rings.append(pts)
    return make_loft(rings, uv_rect, col=col, dyeable=dyeable, cap_start=True, cap_end=True)


# ═══════════════════════════════════════════════════════════════════════════
# 1. AUTHENTIC BOTANICAL OIL PALM, SPIKY TBS & TROPICAL UNDERGROWTH
# ═══════════════════════════════════════════════════════════════════════════

def build_palm_trunk(lod: int) -> MeshPart:
    seg = (18, 12, 7)[lod]
    n_rings = (15, 9, 5)[lod]
    rings = []
    cols = []
    for i in range(n_rings):
        t = i / (n_rings - 1)
        y = t * 6.55
        lean_x = 0.26 * (t ** 1.38)
        lean_z = 0.18 * math.sin(t * 1.48)
        # Characteristic swollen root-bole at base + subtle petiole ring reliefs + crown neck!
        base_swell = 0.29 * math.exp(-t * 5.6)
        swell_neck = 0.085 * math.exp(-((t - 0.96) ** 2) / 0.007)
        r = 0.35 - 0.085 * t + base_swell + swell_neck + 0.016 * math.sin(t * 30.0)
        rings.append(ring_ellipse(r, r, y, seg, cx=lean_x, cz=lean_z))

    trunk = make_loft(rings, UV_PALM_BARK, col=rgba(244, 240, 232, 36), cap_start=True, cap_end=True, u_rep=2.0, v_rep=3.0)
    # Darken muddy root base & under-crown shadow naturally in vertex color
    vy = np.clip(trunk.pos[:, 1] / 6.55, 0.0, 1.0)
    shade = np.clip(0.62 + 0.42 * np.sin(vy * math.pi * 0.88), 0.58, 1.0)
    trunk.col[:, 0] = (trunk.col[:, 0].astype(np.float32) * shade).astype(np.uint8)
    trunk.col[:, 1] = (trunk.col[:, 1].astype(np.float32) * shade).astype(np.uint8)
    trunk.col[:, 2] = (trunk.col[:, 2].astype(np.float32) * shade).astype(np.uint8)
    parts = [trunk]

    # Authentic Sumatran trunk epiphytic ferns ("pakis batang sawit")
    if lod <= 1:
        n_ferns = 9 if lod == 0 else 4
        for fi in range(n_ferns):
            ft = 0.16 + 0.66 * (fi / max(1, n_ferns - 1))
            fy = ft * 6.55
            fa = fi * 2.39996
            fx = 0.26 * (ft ** 1.38) + math.sin(fa) * 0.32
            fz = 0.18 * math.sin(ft * 1.48) + math.cos(fa) * 0.32
            blade = make_quad((-0.46, 0.0, 0.0), (0.46, 0.0, 0.0), (0.56, 0.82, 0.32), (-0.56, 0.82, 0.32),
                              UV_FERN, col=rgba(225, 238, 212, 48), double_sided=True)
            parts.append(xform(blade, rx=0.46, ry=fa, translate=(fx, fy, fz)))
    return merge_parts(parts)


def make_arching_pinnate_frond(length: float, width: float, arch_up: float, droop: float, segs: int, tint_g: int = 255) -> MeshPart:
    """Curved V-folded 3D pinnate oil palm frond + woody petiole spine mapped onto Alpha-Cutout UV_PALM_FROND!"""
    pos, uv01, cols, tris = [], [], [], []
    # 3 vertices across width per station: left leaflet tips (-w), raised woody central rachis (0, +fold), right tips (+w)
    for i in range(segs + 1):
        t = i / segs  # 0 = trunk petiole base, 1 = drooping frond tip
        z = t * length
        y = math.sin(t * math.pi * 0.56) * arch_up - (t ** 2.25) * droop
        w = width * (0.20 + 0.88 * math.sin(min(1.0, t * 1.10) * math.pi * 0.84))
        fold = 0.095 * width * (1.0 - 0.45 * t)
        v_coord = 1.0 - t  # v=1 at base, v=0 at tip
        pos.extend([(-w, y - fold, z), (0.0, y + fold, z), (w, y - fold, z)])
        uv01.extend([[0.0, v_coord], [0.5, v_coord], [1.0, v_coord]])
        # Subtle crown-interior AO near base (t=0) brightening along sunlit arch!
        ao = 0.72 + 0.28 * min(1.0, t * 2.1)
        cb = int(np.clip(tint_g * ao, 90, 255))
        ct = int(np.clip(tint_g * (0.92 * ao), 85, 255))
        cols.extend([rgba(ct, cb, ct, 56), rgba(min(255, cb + 12), min(255, cb + 14), ct, 64), rgba(ct, cb, ct, 56)])

    for i in range(segs):
        b0, b1 = i * 3, (i + 1) * 3
        tris.extend([
            [b0 + 0, b0 + 1, b1 + 1], [b0 + 0, b1 + 1, b1 + 0],
            [b0 + 1, b0 + 2, b1 + 2], [b0 + 1, b1 + 2, b1 + 1],
        ])
    return MeshPart(np.array(pos, np.float32), map_uv(np.array(uv01, np.float32), UV_PALM_FROND),
                    np.array(cols, np.uint8), np.array(tris, np.int32))


def build_palm_crown(lod: int) -> MeshPart:
    # Lush Sumatran Tenera Oil Palm Crown: pruned petiole collar + 3 hanging ripe TBS clusters + 34 arching fronds!
    whorls = [
        # (count, y_off, length, width, arch_up, droop, pitch_rx, brightness)
        ((10, 7, 4)[lod], -0.22, 4.15, 1.02, 0.82, 2.25,  0.18, 204), # Skirt of heavy mature lower fronds
        ((10, 7, 4)[lod],  0.02, 4.25, 1.06, 1.48, 1.65, -0.06, 232), # Full mid-canopy fountain fronds
        ((8,  5, 3)[lod],  0.24, 3.75, 0.94, 1.88, 1.02, -0.34, 248), # Upper sunlit fountain fronds
        ((6,  4, 2)[lod],  0.42, 2.80, 0.68, 1.98, 0.36, -0.70, 255), # Central young spear whorl ('pucuk tombak')
    ]
    segs = (7, 4, 3)[lod]
    parts = [
        # Swollen woody crown meristem + pruned petiole collar so zero gap between trunk & fronds!
        make_sphere_uv(0.42, 0.34, 0.42, UV_PALM_BARK, seg=(12, 8, 6)[lod], rings=5,
                       col=rgba(165, 152, 132, 38), center=(0.0, -0.06, 0.0))
    ]
    # Fruiting crimson-black TBS bunches nestled at the frond axils!
    if lod <= 1:
        for bi in range(3 if lod == 0 else 2):
            ba = bi * 2.094 + 0.55
            parts.append(make_sphere_uv(0.24, 0.22, 0.24, UV_TBS_FRUIT, seg=8, rings=5,
                                        col=rgba(235, 210, 195, 145),
                                        center=(math.sin(ba) * 0.40, -0.10, math.cos(ba) * 0.40)))
    golden_angle = 2.399963
    idx_f = 0
    for count, y_off, ln, wd, up, drp, rx, br in whorls:
        frond = make_arching_pinnate_frond(ln, wd, up, drp, segs, tint_g=br)
        for k in range(count):
            az = idx_f * golden_angle
            idx_f += 1
            parts.append(xform(frond, rx=rx, ry=az, rz=0.055 * math.sin(idx_f * 1.3), translate=(0.0, y_off, 0.0)))
    return merge_parts(parts)


def build_palm_sapling(lod: int) -> MeshPart:
    """A juvenile oil palm with a short ringed bole, emerging spear, and compact pinnate crown."""
    seg = (12, 9, 6)[lod]
    ring_count = (6, 4, 3)[lod]
    rings = []
    for i in range(ring_count):
        t = i / max(1, ring_count - 1)
        y = 0.88 * t
        radius = 0.105 - 0.032 * t + 0.009 * math.sin(t * 25.0)
        rings.append(ring_ellipse(radius, radius, y, seg, cx=0.035 * t, cz=0.018 * math.sin(t * 3.0)))
    parts = [make_loft(rings, UV_PALM_BARK, col=rgba(255, 255, 255, 48), cap_start=True, cap_end=True)]
    # Young spear leaves emerge upright from the crown, visibly different from mature palms.
    parts.append(make_tube_segment((0.0, 0.73, 0.0), (0.035, 1.43, 0.025), 0.045, 0.012,
                                   UV_PALM_FROND, seg=(8, 6, 5)[lod], col=rgba(184, 255, 118, 42), ball_caps=False))
    frond = make_arching_pinnate_frond(0.95, 0.245, 0.40, 0.24, (6, 4, 3)[lod], tint_g=232)
    n_fronds = (7, 5, 3)[lod]
    for i in range(n_fronds):
        az = i * (2.0 * math.pi / n_fronds) + 0.34
        pitch = -0.06 + 0.13 * math.sin(i * 1.7)
        parts.append(xform(frond, rx=pitch, ry=az, rz=0.03 * math.cos(i * 2.1),
                           translate=(0.0, 0.69 + 0.035 * math.sin(az), 0.0)))
    return merge_parts(parts)


def build_tbs_bunch(lod: int) -> MeshPart:
    # Super-detailed Stylized Multi-Berry Fresh Fruit Bunch (Tandan Buah Segar Elaeis guineensis)
    seg = (16, 11, 7)[lod]
    n_rings = (11, 8, 5)[lod]
    rings = []
    ang = np.linspace(-math.pi, math.pi, seg, endpoint=False, dtype=np.float32)
    for i in range(n_rings):
        t = i / (n_rings - 1)
        phi = (t - 0.5) * math.pi * 0.96
        cp, sp = math.cos(phi), math.sin(phi)
        lobe = 1.0 + 0.14 * np.cos(ang * 5.0 + t * 4.2) + 0.09 * np.sin(ang * 3.0 - t * 3.0)
        heart = 1.12 - 0.23 * t
        rings.append(np.stack([np.sin(ang) * 0.24 * cp * heart * lobe, np.full_like(ang, 0.02 + sp * 0.27), np.cos(ang) * 0.23 * cp * heart * lobe], axis=1))

    parts = [make_loft(rings, UV_TBS_FRUIT, col=rgba(255, 255, 255, 168), u_rep=1.0, v_rep=1.0)]
    if lod <= 1:
        n_berries = 22 if lod == 0 else 10
        ga = 2.399963
        for bi in range(n_berries):
            bt = (bi + 0.5) / n_berries
            ph = math.acos(1.0 - 2.0 * bt)
            th = bi * ga
            bx = math.sin(ph) * math.cos(th) * 0.218
            bz = math.sin(ph) * math.sin(th) * 0.208
            by = 0.02 + math.cos(ph) * 0.228
            parts.append(make_sphere_uv(0.080, 0.076, 0.080, UV_TBS_FRUIT, seg=8 if lod == 0 else 5, rings=5,
                                        col=rgba(255, 232, 210, 178), center=(bx, by, bz)))
            if lod == 0 and bi % 2 == 0:
                # Crisp spiny bract tips ('duri tandan sawit') for iconic silhouette!
                nx, ny, nz = math.sin(ph) * math.cos(th), math.cos(ph), math.sin(ph) * math.sin(th)
                parts.append(make_tube_segment(
                    (bx + nx * 0.045, by + ny * 0.045, bz + nz * 0.045),
                    (bx + nx * 0.105, by + ny * 0.105, bz + nz * 0.105),
                    0.014, 0.002, UV_WOOD_PLAIN, seg=4, col=rgba(86, 52, 28, 95), ball_caps=False))
    # Fibrous cut peduncle stalk + green calyx collar
    parts.append(make_sphere_uv(0.11, 0.045, 0.11, UV_PALM_FROND, seg=8, rings=4, col=rgba(142, 176, 72, 80), center=(0.01, 0.24, 0.01)))
    stalk = make_tube_segment((0.0, 0.24, 0.0), (0.03, 0.40, 0.02), 0.058, 0.038, UV_WOOD_PLAIN,
                              seg=(9, 6, 5)[lod], col=rgba(205, 226, 128, 72), ball_caps=True)
    parts.append(stalk)
    return merge_parts(parts)


def build_truck_cargo_heap(lod: int) -> MeshPart:
    # Realistic mound of 16 tightly stacked harvested TBS bunches inside the Canter Bak Kayu!
    single = build_tbs_bunch(min(2, lod + 1))
    rng = np.random.default_rng(88)
    parts = []
    # Bed floor mound base so zero gap between bunches
    mound_rings = []
    seg = (12, 9, 6)[lod]
    for i in range(5):
        t = i / 4.0
        sc = math.cos(t * math.pi * 0.48)
        mound_rings.append(ring_ellipse(0.84 * sc, 1.28 * sc, 0.10 + t * 0.62, seg, cz=-0.95))
    parts.append(make_loft(mound_rings, UV_TBS_FRUIT, col=rgba(235, 235, 235, 125)))

    n_b = (16, 10, 6)[lod]
    for i in range(n_b):
        gx = rng.uniform(-0.66, 0.66)
        gz = rng.uniform(-2.05, 0.12)
        gy = 0.56 + 0.30 * (1.0 - (gx / 0.85) ** 2) * (1.0 - ((gz + 0.96) / 1.35) ** 2)
        parts.append(xform(single, scale=(1.12, 1.08, 1.12),
                           rx=rng.uniform(-0.6, 0.6), ry=rng.uniform(0, 6.28), rz=rng.uniform(-0.5, 0.5),
                           translate=(gx, gy, gz)))
    return merge_parts(parts)


def build_tropical_fern(lod: int) -> MeshPart:
    n_blades = (7, 5, 3)[lod]
    parts = []
    for i in range(n_blades):
        az = i * (2.0 * math.pi / n_blades) + 0.3
        b = make_quad((-0.48, 0.0, 0.0), (0.48, 0.0, 0.0), (0.62, 0.86, 0.42), (-0.62, 0.86, 0.42),
                      UV_FERN, col=rgba(255, 255, 255, 58), double_sided=True)
        parts.append(xform(b, rx=0.22, ry=az))
    return merge_parts(parts)


def build_tire_track_segment(lod: int) -> MeshPart:
    """Flat raised herringbone tread lugs for persistent mud/road tire-mark decals."""
    rows = (5, 4, 3)[lod]
    spacing = 0.72 / rows
    parts = []
    for i in range(rows):
        z_hi = 0.36 - i * spacing
        z_lo = z_hi - spacing * 0.78
        shade = 48 + (i % 2) * 8
        tread = rgba(shade, max(28, shade - 12), max(17, shade - 24), 205)
        # Left and right angled lugs form a chevron, with narrow gaps to read as a real tire imprint.
        parts.append(make_quad((-0.145, 0.018, z_hi), (-0.045, 0.018, z_hi), (0.015, 0.018, z_lo), (-0.085, 0.018, z_lo),
                               UV_DIRT, col=tread))
        parts.append(make_quad((0.045, 0.018, z_hi), (0.145, 0.018, z_hi), (0.085, 0.018, z_lo), (-0.015, 0.018, z_lo),
                               UV_DIRT, col=tread))
    return merge_parts(parts)


def build_rock_boulder(lod: int) -> MeshPart:
    seg = (14, 10, 6)[lod]
    nr = (9, 6, 4)[lod]
    ang = np.linspace(-math.pi, math.pi, seg, endpoint=False, dtype=np.float32)
    rings = []
    for i in range(nr):
        t = i / (nr - 1)
        phi = (t - 0.42) * math.pi * 0.90
        cp = max(0.06, math.cos(phi))
        crag = 1.0 + 0.14 * np.cos(ang * 3.0 + t * 2.2) + 0.09 * np.sin(ang * 5.0)
        rings.append(np.stack([np.sin(ang) * 0.95 * cp * crag,
                               np.full_like(ang, max(-0.05, math.sin(phi) * 0.68 + 0.24)),
                               np.cos(ang) * 0.82 * cp * crag], axis=1))
    return make_loft(rings, UV_ROCK, col=rgba(255, 255, 255, 45))


# ═══════════════════════════════════════════════════════════════════════════
# 2. AUTHENTIC MITSUBISHI FUSO CANTER FE 74 HD CAB-OVER-ENGINE (COE) BAK KAYU
# ═══════════════════════════════════════════════════════════════════════════

def build_canter_truck_body(lod: int) -> MeshPart:
    parts = []
    c_paint  = rgba(255, 255, 255, 178)  # Factory Mitsubishi Canary-Gold automotive clearcoat
    c_frame  = rgba(30, 33, 38, 82)      # Matte heavy chassis steel
    c_rubber = rgba(22, 24, 28, 52)      # Matte black rubber gaskets / mudflaps / trim
    c_chrome = rgba(242, 246, 252, 222)  # High-gloss chrome / stainless garnish
    c_lamp   = rgba(255, 255, 255, 252)  # Emissive-capable crystal headlamp & fog lens
    c_wood   = rgba(255, 255, 255, 86)   # Oiled Sumatran Meranti timber

    # ── A. Heavy Twin C-Channel Steel Chassis Frame Rails + Crossmembers ──
    for sx in (-0.44, 0.44):
        parts.append(make_box(0.11, 0.16, 4.76, UV_STEEL, c_frame, center=(sx, 0.62, -0.10)))
    for cz in (-2.28, -1.25, -0.25, 0.75, 1.75):
        parts.append(make_box(0.88, 0.11, 0.10, UV_STEEL, c_frame, center=(0.0, 0.62, cz)))
    # Differential housing + driveshaft + front/rear solid axles
    parts.append(make_sphere_uv(0.20, 0.20, 0.22, UV_STEEL, seg=8, rings=5, col=c_frame, center=(0.0, 0.48, -1.25)))
    parts.append(make_tube_segment((0.0, 0.50, -1.25), (0.0, 0.56, 1.15), 0.055, 0.055, UV_STEEL, seg=6, col=c_frame, ball_caps=False))
    parts.append(make_box(1.56, 0.08, 0.08, UV_STEEL, c_frame, center=(0.0, 0.48, 1.55)))
    parts.append(make_box(1.56, 0.09, 0.09, UV_STEEL, c_frame, center=(0.0, 0.48, -1.25)))

    # ── B. AUTHENTIC SCULPTED COE MITSUBISHI FUSO CANTER FE 74 HD CAB ──
    # Raked aerodynamic lower COE nose tub (y = 0.70 .. 1.20 full wrap, curving from z=2.255 at grille level back to z=2.165 at cowl)
    low_cab = [
        (0.70, 0.935, 0.58, 2.205),
        (0.84, 0.960, 0.58, 2.234),
        (1.08, 0.962, 0.58, 2.228),
        (1.21, 0.955, 0.58, 2.192),
    ]
    low_rings = []
    for y, hw, zb, zf in low_cab:
        low_rings.append(np.array([
            (-hw * 0.82, y, zf), (0.0, y, zf + 0.032), (hw * 0.82, y, zf),
            (hw, y, zf - 0.16), (hw, y, (zf + zb) * 0.5), (hw, y, zb + 0.10),
            (hw * 0.89, y, zb), (0.0, y, zb), (-hw * 0.89, y, zb),
            (-hw, y, zb + 0.10), (-hw, y, (zf + zb) * 0.5), (-hw, y, zf - 0.16),
        ], dtype=np.float32))
    parts.append(make_loft(low_rings, UV_CANTER_PAINT, col=c_paint, cap_start=True, cap_end=True))

    # Front windshield cowl panel (y = 1.20 .. 1.34) + Black Wiper Cowl Air Vent Grille!
    parts.append(make_bevel_box(1.84, 0.14, 0.24, UV_CANTER_PAINT, c_paint, center=(0.0, 1.27, 2.08), bev=0.022))
    parts.append(make_bevel_box(1.52, 0.045, 0.08, UV_STEEL, c_rubber, center=(0.0, 1.335, 2.13), bev=0.008))

    # Signature Canter FE 74 HD Dipped Door Beltline ('lekukan pintu kaca Canter'):
    # Rear half of door rises to y=1.34 (z=0.58..1.48), front half dips down to y=1.21 near the mirror/A-pillar!
    for sx in (-1.0, 1.0):
        parts.append(make_bevel_box(0.085, 0.15, 0.90, UV_CANTER_PAINT, c_paint, center=(sx * 0.915, 1.27, 1.03), bev=0.016))
        # Diagonal door-sill ramp connecting z=1.48 (y=1.34) down to z=1.82 (y=1.21)
        parts.append(xform(make_bevel_box(0.082, 0.11, 0.38, UV_CANTER_PAINT, c_paint, bev=0.014),
                           rx=0.34, translate=(sx * 0.912, 1.255, 1.63)))

    # Rounded Beveled Aero Roof Cap (y = 2.00 .. 2.17)
    roof_rings = []
    for y, hw, zb, zf in [(2.00, 0.88, 0.62, 1.83), (2.11, 0.84, 0.65, 1.75), (2.17, 0.76, 0.70, 1.65)]:
        roof_rings.append(np.array([
            (-hw * 0.85, y, zf), (0.0, y, zf + 0.022), (hw * 0.85, y, zf),
            (hw, y, zf - 0.12), (hw, y, (zf + zb) * 0.5), (hw, y, zb + 0.10),
            (hw * 0.88, y, zb), (0.0, y, zb), (-hw * 0.88, y, zb),
            (-hw, y, zb + 0.10), (-hw, y, (zf + zb) * 0.5), (-hw, y, zf - 0.12),
        ], dtype=np.float32))
    parts.append(make_loft(roof_rings, UV_CANTER_PAINT, col=c_paint, cap_start=True, cap_end=True))

    # Real 3D Raked A-Pillars + Rear B-Pillars + Upper Roof Window Drip Rails + Rear Cab Panel
    for sx in (-1.0, 1.0):
        parts.append(make_tube_segment((sx * 0.89, 1.22, 2.13), (sx * 0.82, 2.02, 1.80), 0.052, 0.046, UV_CANTER_PAINT, seg=6, col=c_paint, ball_caps=False))
        parts.append(make_bevel_box(0.13, 0.72, 0.24, UV_CANTER_PAINT, c_paint, center=(sx * 0.86, 1.67, 0.71), bev=0.02))
        parts.append(make_tube_segment((sx * 0.83, 2.00, 1.80), (sx * 0.85, 2.00, 0.72), 0.028, 0.028, UV_CANTER_PAINT, seg=5, col=c_paint, ball_caps=False))
    parts.append(make_bevel_box(1.74, 0.34, 0.10, UV_CANTER_PAINT, c_paint, center=(0.0, 1.46, 0.63), bev=0.02))

    # ── REAL 3D CABIN INTERIOR (Clean Matte Charcoal Dash + Subtle Instrument Cluster + Tan Vinyl Seats) ──
    parts.append(make_box(1.66, 0.08, 1.34, UV_STEEL, rgba(28, 31, 36, 48), center=(0.0, 1.02, 1.36)))
    parts.append(make_bevel_box(1.64, 0.28, 0.34, UV_STEEL, rgba(36, 40, 46, 68), center=(0.0, 1.24, 1.92), bev=0.03))
    parts.append(make_tube_segment((0.42, 1.06, 1.98), (0.42, 1.44, 1.86), 0.042, 0.034, UV_STEEL, seg=8, col=rgba(32, 36, 42, 90), ball_caps=True))
    parts.append(make_tube_segment((0.04, 1.05, 1.48), (0.08, 1.36, 1.44), 0.020, 0.013, UV_STEEL, seg=6, col=rgba(36, 40, 48, 105)))
    parts.append(make_sphere_uv(0.030, 0.036, 0.030, UV_STEEL, seg=8, rings=5, col=rgba(22, 24, 28, 145), center=(0.08, 1.38, 1.44)))
    parts.append(make_tube_segment((0.18, 1.08, 1.32), (0.18, 1.24, 1.48), 0.016, 0.014, UV_STEEL, seg=5, col=rgba(28, 32, 38, 130)))
    parts.append(make_bevel_box(0.42, 0.13, 0.20, UV_STEEL, rgba(24, 27, 32, 105), center=(0.42, 1.40, 1.94), bev=0.022))
    # Subtle dark instrument dial face (soft warm amber-green OEM gauges, zero neon cyan!)
    parts.append(make_quad((0.26, 1.35, 1.835), (0.58, 1.35, 1.835), (0.58, 1.44, 1.855), (0.26, 1.44, 1.855),
                           UV_STEEL, col=rgba(46, 58, 52, 175), flip_u=True))
    parts.append(make_bevel_box(0.22, 0.052, 0.03, UV_STEEL, rgba(30, 34, 40, 130), center=(0.0, 1.94, 1.77), bev=0.008))
    for px_ped in (0.32, 0.44, 0.54):
        parts.append(make_box(0.055, 0.09, 0.02, UV_STEEL, rgba(48, 54, 62, 110), center=(px_ped, 1.12, 1.90)))
    if lod <= 1:
        # Custom Sumatera Cab Aero Sun-Visor ('Topi Kabin Canter') + 5 Warm Amber Marker LEDs + Twin Chrome Roof Horns!
        visor = make_bevel_box(1.72, 0.085, 0.22, UV_CANTER_PAINT, c_paint, center=(0.0, 0.0, 0.0), bev=0.02)
        parts.append(xform(visor, rx=0.28, translate=(0.0, 2.06, 1.90)))
        for sx_v in (-0.81, 0.81):
            parts.append(make_box(0.035, 0.075, 0.15, UV_STEEL, c_rubber, center=(sx_v, 2.03, 1.86)))
        for hx_h in (-0.34, 0.34):
            parts.append(make_tube_segment((hx_h, 2.18, 1.24), (hx_h, 2.22, 1.68), 0.016, 0.044, UV_STEEL, seg=8, col=c_chrome, ball_caps=False))
            parts.append(make_box(0.028, 0.045, 0.04, UV_STEEL, c_rubber, center=(hx_h, 2.15, 1.34)))
        for mx_m in (-0.62, -0.31, 0.0, 0.31, 0.62):
            parts.append(make_bevel_box(0.082, 0.036, 0.042, UV_CANTER_FOGLAMP, rgba(255, 178, 36, 248), center=(mx_m, 2.075, 2.005), bev=0.007))
    c_seat = rgba(168, 118, 78, 72)
    for sx_s in (-0.44, 0.44):
        parts.append(make_bevel_box(0.48, 0.14, 0.46, UV_WOOD_PLAIN, c_seat, center=(sx_s, 1.18, 1.26), bev=0.03))
        if lod <= 1:
            for rib in range(3):
                parts.append(make_bevel_box(0.45, 0.16, 0.12, UV_WOOD_PLAIN, c_seat, center=(sx_s, 1.34 + rib * 0.165, 1.04 - rib * 0.015), bev=0.025))
            parts.append(make_bevel_box(0.26, 0.15, 0.10, UV_WOOD_PLAIN, c_seat, center=(sx_s, 1.86, 0.99), bev=0.025))

    # 1. Flush Smoked Laminated Windshield + Matte Rubber Gasket + Twin Black Wiper Blades
    parts.append(make_quad(
        (-0.85, 1.335, 2.148), (0.85, 1.335, 2.148),
        (0.79, 2.005, 1.815), (-0.79, 2.005, 1.815),
        UV_CANTER_GLASS, col=rgba(240, 244, 248, 228), double_sided=True
    ))
    if lod <= 1:
        for wx_piv in (-0.44, 0.18):
            parts.append(make_tube_segment((wx_piv, 1.34, 2.165), (wx_piv + 0.32, 1.56, 2.058), 0.011, 0.008, UV_STEEL, seg=5, col=c_rubber, ball_caps=False))
            parts.append(make_tube_segment((wx_piv + 0.14, 1.46, 2.108), (wx_piv + 0.48, 1.66, 2.008), 0.010, 0.009, UV_STEEL, seg=4, col=c_rubber, ball_caps=False))

    # 2. Side Cab Smoked Windows (matching the dipped Canter front door sill!)
    parts.append(make_quad(
        (0.905, 1.22, 2.08), (0.905, 1.33, 0.83),
        (0.842, 2.00, 0.83), (0.842, 2.00, 1.78),
        UV_CANTER_SIDE_GLS, col=rgba(240, 244, 248, 224), double_sided=True
    ))
    parts.append(make_quad(
        (-0.905, 1.33, 0.83), (-0.905, 1.22, 2.08),
        (-0.842, 2.00, 1.78), (-0.842, 2.00, 0.83),
        UV_CANTER_SIDE_GLS, col=rgba(240, 244, 248, 224), double_sided=True
    ))
    # Recessed black vertical Canter door handles + fender turn-signal repeaters
    parts.append(make_quad((0.962, 1.08, 0.96), (0.962, 1.08, 0.76), (0.962, 1.18, 0.76), (0.962, 1.18, 0.96), UV_CANTER_HANDLE, col=c_paint))
    parts.append(make_quad((-0.962, 1.08, 0.76), (-0.962, 1.08, 0.96), (-0.962, 1.18, 0.96), (-0.962, 1.18, 0.76), UV_CANTER_HANDLE, col=c_paint))
    if lod <= 1:
        for sx in (-1.0, 1.0):
            parts.append(make_bevel_box(0.028, 0.052, 0.11, UV_CANTER_FOGLAMP, rgba(255, 172, 28, 245), center=(sx * 0.962, 0.94, 1.86), bev=0.006))

    # 3. 3D Sculpted Recessed FUSO Front Grille Bezel + Chrome Top Alis Garnish + 3-Diamond Crest!
    parts.append(make_bevel_box(0.98, 0.30, 0.055, UV_STEEL, c_rubber, center=(0.0, 0.94, 2.248), bev=0.014))
    parts.append(make_bevel_box(0.96, 0.036, 0.062, UV_STEEL, c_chrome, center=(0.0, 1.095, 2.252), bev=0.008))
    parts.append(make_quad(
        (-0.47, 0.80, 2.279), (0.47, 0.80, 2.279),
        (0.49, 1.08, 2.274), (-0.49, 1.08, 2.274),
        UV_CANTER_GRILLE, col=rgba(250, 252, 255, 195)
    ))

    # 4. 3D Sculpted Swept Canter FE 74 HD Crystal Headlamp Housings + Corner Wrap-Around Amber Turn Signals!
    for sx in (-1.0, 1.0):
        bezel = make_bevel_box(0.45, 0.33, 0.055, UV_STEEL, c_rubber, bev=0.012)
        parts.append(xform(bezel, ry=sx * 0.075, translate=(sx * 0.715, 0.96, 2.226)))
        # Wrap-around corner amber signal housing on cab cheek (z = 2.06..2.24)
        parts.append(make_bevel_box(0.042, 0.31, 0.17, UV_CANTER_FOGLAMP, rgba(255, 164, 24, 248), center=(sx * 0.946, 0.96, 2.145), bev=0.008))
    parts.append(make_quad(
        (-0.935, 0.805, 2.248), (-0.495, 0.800, 2.282),
        (-0.505, 1.115, 2.275), (-0.940, 1.125, 2.238),
        UV_CANTER_HEADLAMP, col=c_lamp, flip_u=True
    ))
    parts.append(make_quad(
        (0.495, 0.800, 2.282), (0.935, 0.805, 2.248),
        (0.940, 1.125, 2.238), (0.505, 1.115, 2.275),
        UV_CANTER_HEADLAMP, col=c_lamp, flip_u=False
    ))

    # 5. Sumatera Heavy Steel Front Bumper + Air-Dam Slat Grille + Foot Steps + BM 8899 XY Plate + Recessed Fog Lamps!
    parts.append(make_bevel_box(1.95, 0.27, 0.19, UV_CANTER_PAINT, c_paint, center=(0.0, 0.61, 2.23), bev=0.028))
    parts.append(make_bevel_box(0.82, 0.085, 0.05, UV_STEEL, c_rubber, center=(0.0, 0.66, 2.31), bev=0.010))
    for sx in (-0.92, 0.92):
        parts.append(make_bevel_box(0.16, 0.27, 0.23, UV_STEEL, c_rubber, center=(sx, 0.61, 2.19), bev=0.022))
    for sx_h in (-0.42, 0.42):
        parts.append(make_bevel_box(0.05, 0.06, 0.09, UV_STEEL, c_frame, center=(sx_h, 0.47, 2.26), bev=0.01))
    parts.append(make_quad((-0.25, 0.50, 2.332), (0.25, 0.50, 2.332), (0.25, 0.65, 2.332), (-0.25, 0.65, 2.332), UV_CANTER_PLATE, col=rgba(255, 255, 255, 155)))
    for sx in (-0.65, 0.65):
        parts.append(make_bevel_box(0.26, 0.13, 0.04, UV_STEEL, c_rubber, center=(sx, 0.59, 2.315), bev=0.008))
        parts.append(make_quad((sx - 0.115, 0.54, 2.338), (sx + 0.115, 0.54, 2.338), (sx + 0.115, 0.64, 2.338), (sx - 0.115, 0.64, 2.338), UV_CANTER_FOGLAMP, col=c_lamp))

    # 6. Molded Black Wheel Arch Flares + Front Kepet Mudflaps + Boarding Stirrups + Dual Sumatera Stay Mirrors!
    if lod <= 1:
        for sx in (-1.0, 1.0):
            for ai in range(6):
                a0 = -0.95 + ai * 0.38
                a1 = a0 + 0.38
                r_arch = 0.56
                parts.append(make_tube_segment(
                    (sx * 0.935, 0.48 + math.cos(a0) * r_arch, 1.55 + math.sin(a0) * r_arch),
                    (sx * 0.935, 0.48 + math.cos(a1) * r_arch, 1.55 + math.sin(a1) * r_arch),
                    0.048, 0.048, UV_STEEL, seg=6, col=c_rubber, ball_caps=False
                ))
            # Front rubber mudflap ('kepet lumpur depan') behind front wheel
            parts.append(make_box(0.32, 0.28, 0.022, UV_STEEL, c_rubber, center=(sx * 0.84, 0.32, 1.02)))
            # Cab boarding step stirrup with diamond steel tread
            parts.append(make_bevel_box(0.16, 0.042, 0.42, UV_STEEL, c_chrome, center=(sx * 0.95, 0.56, 1.02), bev=0.008))
            parts.append(make_box(0.04, 0.18, 0.40, UV_STEEL, c_frame, center=(sx * 0.88, 0.64, 1.02)))
            # Tubular steel mirror C-stay + tall black aero mirror + round convex blind-spot mirror
            parts.append(make_tube_segment((sx * 0.89, 1.88, 1.83), (sx * 1.12, 1.82, 2.02), 0.015, 0.015, UV_STEEL, seg=5, col=c_rubber, ball_caps=False))
            parts.append(make_tube_segment((sx * 1.12, 1.82, 2.02), (sx * 1.12, 1.44, 2.02), 0.015, 0.015, UV_STEEL, seg=5, col=c_rubber, ball_caps=False))
            parts.append(make_tube_segment((sx * 1.12, 1.44, 2.02), (sx * 0.93, 1.36, 1.94), 0.015, 0.015, UV_STEEL, seg=5, col=c_rubber, ball_caps=False))
            parts.append(make_bevel_box(0.055, 0.30, 0.15, UV_STEEL, c_rubber, center=(sx * 1.13, 1.65, 2.02), bev=0.012))
            parts.append(make_sphere_uv(0.030, 0.062, 0.062, UV_STEEL, seg=8, rings=5, col=c_rubber, center=(sx * 1.13, 1.43, 2.02)))

    # ── C. AUTHENTIC SUMATRAN BOLTED MERANTI "BAK KAYU" SAWIT CARGO BED ──
    # Heavy steel bed subframe runners + floor deck + full-height UV_WOOD_BAK bolted plank walls!
    for sx_sub in (-0.44, 0.44):
        parts.append(make_box(0.09, 0.09, 2.94, UV_STEEL, c_frame, center=(sx_sub, 0.73, -0.96)))
    parts.append(make_bevel_box(2.02, 0.11, 2.96, UV_WOOD_PLAIN, c_wood, center=(0.0, 0.80, -0.96), bev=0.02))
    # Full bolted Meranti side walls & tailgate mapped directly to UV_WOOD_BAK (carriage bolts + grain + reflector tape!)
    for sx in (-1.0, 1.0):
        parts.append(make_bevel_box(0.072, 1.14, 2.94, UV_WOOD_BAK, c_wood, center=(sx * 0.985, 1.41, -0.96), bev=0.016))
        # Top cap rail & bottom steel rub-rail along cargo bed
        parts.append(make_bevel_box(0.092, 0.055, 2.98, UV_STEEL, c_frame, center=(sx * 0.99, 2.00, -0.96), bev=0.010))
        parts.append(make_bevel_box(0.095, 0.070, 2.98, UV_STEEL, c_frame, center=(sx * 0.99, 0.83, -0.96), bev=0.010))
    # Tailgate + Front Bulkhead wall mapped to UV_WOOD_BAK + heavy black corner steel angle-posts!
    parts.append(make_bevel_box(1.98, 1.14, 0.072, UV_WOOD_BAK, c_wood, center=(0.0, 1.41, -2.41), bev=0.016))
    parts.append(make_bevel_box(1.98, 1.16, 0.072, UV_WOOD_BAK, c_wood, center=(0.0, 1.42, 0.49), bev=0.016))
    for sx_c in (-1.00, 1.00):
        for cz_c in (-2.42, 0.50):
            parts.append(make_bevel_box(0.085, 1.24, 0.085, UV_STEEL, c_frame, center=(sx_c, 1.42, cz_c), bev=0.012))

    # Tall cab-protector header rack ('Kepala Bak Sawit Sumatera') + steel pipe guard
    parts.append(make_bevel_box(2.02, 0.16, 0.068, UV_WOOD_PLAIN, c_wood, center=(0.0, 2.14, 0.49), bev=0.015))
    parts.append(make_bevel_box(2.06, 0.14, 0.13, UV_WOOD_PLAIN, c_wood, center=(0.0, 2.31, 0.51), bev=0.02))
    parts.append(make_tube_segment((-0.96, 2.43, 0.51), (0.96, 2.43, 0.51), 0.022, 0.022, UV_STEEL, seg=6, col=c_frame))
    for sx in (-0.92, 0.92):
        parts.append(make_bevel_box(0.10, 0.07, 0.055, UV_CANTER_FOGLAMP, rgba(255, 182, 32, 248), center=(sx, 2.32, 0.60), bev=0.01))

    # Rear heavy underrun bumper + 3-chamber red/amber/white taillights + rear BM 8899 XY plate!
    parts.append(make_bevel_box(1.94, 0.15, 0.14, UV_STEEL, c_frame, center=(0.0, 0.58, -2.44), bev=0.022))
    parts.append(make_quad((0.24, 0.51, -2.515), (-0.24, 0.51, -2.515), (-0.24, 0.66, -2.515), (0.24, 0.66, -2.515), UV_CANTER_PLATE, col=rgba(255, 255, 255, 155)))
    for sx in (-0.72, 0.72):
        parts.append(make_bevel_box(0.34, 0.14, 0.08, UV_STEEL, c_rubber, center=(sx, 0.60, -2.49), bev=0.012))
        parts.append(make_bevel_box(0.11, 0.10, 0.04, UV_CANTER_FOGLAMP, rgba(255, 38, 32, 253), center=(sx + (0.095 if sx > 0 else -0.095), 0.60, -2.525), bev=0.008))
        parts.append(make_bevel_box(0.09, 0.10, 0.04, UV_CANTER_FOGLAMP, rgba(255, 178, 26, 252), center=(sx, 0.60, -2.525), bev=0.008))
        parts.append(make_bevel_box(0.07, 0.10, 0.04, UV_CONCRETE_CLEAN, rgba(245, 248, 252, 248), center=(sx - (0.085 if sx > 0 else -0.085), 0.60, -2.525), bev=0.008))

    # External Vertical Steel Stakes + Diagonal Gussets + Underslung Spare Tire + Battery/Air/Fuel/Knalpot Srigala!
    if lod <= 1:
        for rz in (-1.92, -1.36, -0.80, -0.24, 0.24):
            for sx in (-1.015, 1.015):
                parts.append(make_bevel_box(0.058, 1.20, 0.068, UV_STEEL, c_frame, center=(sx, 1.41, rz), bev=0.010))
                if lod == 0:
                    # Diagonal under-bed steel gusset brace + rope J-hook!
                    parts.append(make_tube_segment((sx * 0.46, 0.64, rz), (sx * 0.96, 0.80, rz), 0.018, 0.018, UV_STEEL, seg=4, col=c_frame, ball_caps=False))
                    parts.append(make_tube_segment((sx * 1.03, 1.02, rz), (sx * 1.06, 0.95, rz), 0.010, 0.008, UV_STEEL, seg=4, col=c_chrome, ball_caps=False))
        # Rear tailgate vertical steel locking bars + chains
        for sx_l in (-0.62, 0.62):
            parts.append(make_tube_segment((sx_l, 0.86, -2.455), (sx_l, 1.98, -2.455), 0.018, 0.018, UV_STEEL, seg=6, col=c_chrome))
        # Heavy Sumatran rear rubber mudflaps ('kepet lumpur belakang') + steel fender arch guards
        for sx in (-0.90, 0.90):
            parts.append(make_box(0.44, 0.04, 0.96, UV_STEEL, c_frame, center=(sx, 0.76, -1.25)))
            parts.append(make_box(0.44, 0.38, 0.026, UV_STEEL, c_rubber, center=(sx, 0.36, -1.80)))
        # Authentic Underslung Rear Spare Wheel ('ban serep kolong belakang Canter')!
        spare = make_tube_segment((0.0, 0.44, -2.02), (0.0, 0.56, -2.02), 0.40, 0.40, UV_TIRE_TREAD, seg=14 if lod == 0 else 8, col=c_rubber, ball_caps=True)
        parts.append(xform(spare, rx=0.14))
        # Right rail: GS Battery Box + Black Compressed-Air Tank + Chrome Side Exhaust ('Knalpot Srigala')!
        parts.append(make_bevel_box(0.34, 0.25, 0.46, UV_STEEL, c_frame, center=(0.68, 0.56, 0.72), bev=0.02))
        parts.append(make_tube_segment((0.66, 0.54, -0.36), (0.66, 0.54, 0.18), 0.135, 0.135, UV_STEEL, seg=10, col=c_frame, ball_caps=True))
        parts.append(make_sphere_uv(0.030, 0.030, 0.030, UV_CANTER_PAINT, seg=6, rings=4, col=rgba(215, 42, 34, 175), center=(0.80, 0.54, -0.10)))
        parts.append(make_tube_segment((0.56, 0.42, 0.20), (0.88, 0.37, -0.58), 0.038, 0.044, UV_STEEL, seg=8, col=c_chrome, ball_caps=False))
        # Left rail: Strapped Dark-Steel Biosolar Fuel Tank + Chrome Filler Neck!
        parts.append(make_tube_segment((-0.68, 0.54, 0.32), (-0.68, 0.54, 1.08), 0.19, 0.19, UV_STEEL, seg=12, col=rgba(46, 50, 56, 138), ball_caps=True))
        parts.append(make_tube_segment((-0.78, 0.68, 0.88), (-0.84, 0.75, 0.88), 0.036, 0.042, UV_STEEL, seg=8, col=c_chrome))
        for sz_st in (0.52, 0.90):
            parts.append(make_tube_segment((-0.68, 0.54, sz_st - 0.03), (-0.68, 0.54, sz_st + 0.03), 0.202, 0.202, UV_STEEL, seg=12, col=c_chrome, ball_caps=False))

    return merge_parts(parts)


def build_canter_steering_wheel(lod: int) -> MeshPart:
    seg = (14, 10, 6)[lod]
    parts = [make_sphere_uv(0.06, 0.03, 0.06, UV_STEEL, seg=8, rings=5, col=rgba(36, 40, 46, 110))]
    R = 0.21
    for i in range(seg):
        a0 = i * 2.0 * math.pi / seg
        a1 = (i + 1) * 2.0 * math.pi / seg
        parts.append(make_tube_segment(
            (math.cos(a0) * R, 0.0, math.sin(a0) * R),
            (math.cos(a1) * R, 0.0, math.sin(a1) * R),
            0.021, 0.021, UV_STEEL, seg=5, col=rgba(32, 35, 40, 125), ball_caps=False
        ))
    for sa in (0.0, 2.25, -2.25):
        parts.append(make_tube_segment((0.0, 0.0, 0.0), (math.cos(sa) * R, 0.0, math.sin(sa) * R),
                                       0.020, 0.016, UV_STEEL, seg=5, col=rgba(42, 46, 52, 110), ball_caps=False))
    return merge_parts(parts)


def build_truck_wheel(lod: int) -> MeshPart:
    """Heavy-duty 7.50-16 Mud-Terrain Radial Truck Tire & 6-Lug Steel Rim mapped onto UV_TIRE_TREAD & UV_WHEEL_CENTER!"""
    seg = (28, 18, 10)[lod]
    R = 0.48
    hw = 0.145
    ang = np.linspace(0.0, 2.0 * math.pi, seg + 1, dtype=np.float32)

    # 1. Outer tire tread band with crisp multi-step beveled mud shoulders
    tread_profile = [(-hw, R * 0.88), (-hw * 0.88, R * 0.96), (-hw * 0.72, R), (hw * 0.72, R), (hw * 0.88, R * 0.96), (hw, R * 0.88)]
    pos_t, uv_t, tris_t = [], [], []
    for ri, (x_off, rad) in enumerate(tread_profile):
        u_val = ri / (len(tread_profile) - 1.0)
        for j in range(seg + 1):
            a = float(ang[j])
            pos_t.append([x_off, math.sin(a) * rad, math.cos(a) * rad])
            uv_t.append([u_val, (j / seg) * 2.0 % 1.0 if j < seg else 1.0])
    stride = seg + 1
    for ri in range(len(tread_profile) - 1):
        b0, b1 = ri * stride, (ri + 1) * stride
        for j in range(seg):
            tris_t.extend([[b0 + j, b1 + j, b1 + j + 1], [b0 + j, b1 + j + 1, b0 + j + 1]])
    tread = MeshPart(np.array(pos_t, np.float32), map_uv(np.array(uv_t, np.float32), UV_TIRE_TREAD),
                     np.broadcast_to(rgba(255, 255, 255, 62), (len(pos_t), 4)).copy(), np.array(tris_t, np.int32))

    # Outer face on +X and -X mapped radially onto UV_WHEEL_CENTER (6-lug steel rim + sidewall ribs!)
    parts = [tread]
    ucx, ucy, urad = UV_WHEEL_CENTER
    for side in (-1.0, 1.0):
        # 5 concentric profile rings for realistic 3D recessed steel wheel dish + protruding axle hub!
        rad_steps = [(R * 0.88, hw * side), (R * 0.64, hw * 0.94 * side), (R * 0.56, hw * 0.78 * side),
                     (R * 0.42, hw * 0.54 * side), (R * 0.19, hw * 0.90 * side), (0.0, hw * 0.96 * side)]
        f_pos, f_uv, f_tris = [], [], []
        for rad, x_off in rad_steps:
            for j in range(seg):
                a = j * 2.0 * math.pi / seg
                sy, cz = math.sin(a), math.cos(a)
                f_pos.append([x_off, sy * rad, cz * rad])
                f_uv.append([ucx + (cz * rad / (R * 0.88)) * urad, ucy - (sy * rad / (R * 0.88)) * urad])
        for ri in range(len(rad_steps) - 1):
            b0, b1 = ri * seg, (ri + 1) * seg
            for j in range(seg):
                jn = (j + 1) % seg
                if side > 0:
                    f_tris.extend([[b0 + j, b0 + jn, b1 + jn], [b0 + j, b1 + jn, b1 + j]])
                else:
                    f_tris.extend([[b0 + j, b1 + jn, b0 + jn], [b0 + j, b1 + j, b1 + jn]])
        parts.append(MeshPart(np.array(f_pos, np.float32), np.array(f_uv, np.float32),
                              np.broadcast_to(rgba(255, 255, 255, 118), (len(f_pos), 4)).copy(), np.array(f_tris, np.int32)))

    merged = merge_parts(parts)
    v0, v1, v2 = merged.pos[merged.idx[:, 0]], merged.pos[merged.idx[:, 1]], merged.pos[merged.idx[:, 2]]
    if float(np.sum(np.einsum("ij,ij->i", v0, np.cross(v1, v2)))) < 0.0:
        merged.idx = merged.idx[:, [0, 2, 1]]

    # 3D sculpted 6-lug chrome wheel nuts + aggressive mud shoulder lugs on LOD0!
    extra = [merged]
    if lod == 0:
        for side in (-1.0, 1.0):
            for li in range(6):
                la = li * (math.pi / 3.0)
                extra.append(make_sphere_uv(0.020, 0.022, 0.022, UV_STEEL, seg=6, rings=4,
                                            col=rgba(242, 246, 252, 225),
                                            center=(side * (hw * 0.72), math.sin(la) * (R * 0.31), math.cos(la) * (R * 0.31))))
        for ti in range(14):
            ta = ti * (2.0 * math.pi / 14.0)
            lug = make_box(hw * 1.56, 0.028, 0.052, UV_TIRE_TREAD, rgba(36, 38, 42, 70))
            extra.append(xform(lug, rx=-ta, translate=(0.0, math.sin(ta) * (R * 0.992), math.cos(ta) * (R * 0.992))))
    return merge_parts(extra)


# ═══════════════════════════════════════════════════════════════════════════
# 3. ORGANIC SEAMLESS BALL-JOINTED HUMAN ANATOMY & COMPLETE ACCESSORIES
# ═══════════════════════════════════════════════════════════════════════════

def build_char_torso_head(lod: int) -> MeshPart:
    """Athletic seamless harvester pelvis + utility belt + V-tapered collared field work shirt (y = -0.10 .. +0.60)."""
    seg = (16, 12, 8)[lod]
    # 1. Pelvis / hips in dark ripstop field trousers (y = -0.11 .. +0.10)
    pelvis_rings = [
        ring_ellipse(0.142, 0.102, -0.10, seg),
        ring_ellipse(0.164, 0.118, -0.02, seg),
        ring_ellipse(0.158, 0.112,  0.09, seg),
    ]
    pelvis = make_loft(pelvis_rings, UV_DENIM, col=rgba(255, 255, 255, 52))

    # 2. Heavy leather plantation belt + brushed steel buckle + utility pouch (y = 0.08 .. 0.135)
    belt = make_loft([ring_ellipse(0.165, 0.120, 0.08, seg), ring_ellipse(0.165, 0.120, 0.135, seg)],
                     UV_WOOD_PLAIN, col=rgba(58, 38, 24, 88))
    buckle = make_bevel_box(0.062, 0.050, 0.024, UV_STEEL, rgba(212, 182, 88, 185), center=(0.0, 0.108, 0.124), bev=0.005)

    # 3. Athletic dyeable field work shirt with clean collar lapels & shoulder structure (y = 0.12 .. 0.53)
    shirt_stations = [
        (0.12, 0.158, 0.112, 0.00),
        (0.24, 0.168, 0.118, 0.005),
        (0.37, 0.200, 0.134, 0.012),
        (0.47, 0.218, 0.128, 0.008),
        (0.525, 0.112, 0.088, 0.004),
    ]
    shirt_rings = [ring_ellipse(rx, rz, y, seg, cz=cz) for y, rx, rz, cz in shirt_stations]
    shirt = make_loft(shirt_rings, UV_SHIRT_FRONT, col=rgba(255, 255, 255, 52), dyeable=True)

    # Crisp V-neck shirt collar + seamless tanned neck column rising into head socket
    collar = make_loft([ring_ellipse(0.094, 0.090, 0.502, seg, cz=0.005), ring_ellipse(0.084, 0.082, 0.558, seg, cz=0.008)],
                       UV_SHIRT_PLAIN, col=rgba(242, 244, 248, 52), dyeable=True)
    neck = make_loft([ring_ellipse(0.060, 0.058, 0.52, seg, cz=0.008), ring_ellipse(0.054, 0.054, 0.61, seg, cz=0.010)],
                     UV_SKIN, col=rgba(255, 255, 255, 58))
    parts = [pelvis, belt, buckle, shirt, collar, neck]
    if lod <= 1:
        # Side belt whetstone/tool pouch ('kantong batu asah egrek')
        parts.append(make_bevel_box(0.045, 0.075, 0.058, UV_WOOD_PLAIN, rgba(64, 42, 26, 78), center=(-0.168, 0.092, 0.02), bev=0.008))
    return merge_parts(parts)


def build_char_head(lod: int) -> MeshPart:
    """Clean Stylized Anime Head with crisp V-jawline, sculpted nose bridge, ears & 3D layered hair locks mapped onto UV_FACE!"""
    seg = (20, 14, 9)[lod]
    ang = np.linspace(-math.pi, math.pi, seg, endpoint=False, dtype=np.float32)
    profile = [
        (0.020, 0.044, 0.052, 0.020),  # Crisp stylized chin apex
        (0.054, 0.076, 0.085, 0.012),  # Tapered anime jawline
        (0.098, 0.090, 0.100, 0.006),  # Cheekbones / mouth level
        (0.144, 0.094, 0.104, 0.004),  # Anime iris / brow plane
        (0.196, 0.093, 0.103, -0.002), # Forehead
        (0.236, 0.078, 0.088, -0.006), # Upper cranium
        (0.256, 0.042, 0.048, -0.008), # Crown apex
    ]
    pos_rows, uv_rows = [], []
    u0, v0, u1, v1 = UV_FACE
    for ri, (y, rx, rz, cz) in enumerate(profile):
        v_t = 1.0 - (ri / (len(profile) - 1.0))
        ring = np.stack([np.sin(ang) * rx, np.full_like(ang, y), cz + np.cos(ang) * rz], axis=1)
        if ri in (2, 3):
            nose_push = np.maximum(0.0, np.cos(ang)) ** 12.0 * (0.017 if ri == 2 else 0.010)
            ring[:, 2] += nose_push
        ring_closed = np.vstack([ring, ring[0:1]])
        pos_rows.append(ring_closed.astype(np.float32))

        u_row = np.empty((seg + 1, 2), dtype=np.float32)
        for j in range(seg + 1):
            a = -math.pi + (j / seg) * 2.0 * math.pi
            fu = 0.5 + (a / 2.15)
            u_row[j, 0] = u0 + np.clip(fu, 0.02, 0.98) * (u1 - u0)
            u_row[j, 1] = v0 + np.clip(0.10 + v_t * 0.82, 0.02, 0.98) * (v1 - v0)
        uv_rows.append(u_row)

    pos_a = np.vstack(pos_rows)
    uv_a = np.vstack(uv_rows)
    tris = []
    stride = seg + 1
    for ri in range(len(profile) - 1):
        b0, b1 = ri * stride, (ri + 1) * stride
        for j in range(seg):
            tris.extend([[b0 + j, b0 + j + 1, b1 + j + 1], [b0 + j, b1 + j + 1, b1 + j]])
    c_bot, c_top = profile[0], profile[-1]
    pos_a = np.vstack([pos_a, [[0.0, c_bot[0], c_bot[3]], [0.0, c_top[0], c_top[3]]]])
    uv_a = np.vstack([uv_a, [[(u0 + u1) * 0.5, v1], [(u0 + u1) * 0.5, v0]]])
    ib, it = len(pos_a) - 2, len(pos_a) - 1
    top_b = (len(profile) - 1) * stride
    for j in range(seg):
        tris.append([ib, j + 1, j])
        tris.append([it, top_b + j, top_b + j + 1])

    idx_a = np.array(tris, np.int32)
    vv0, vv1, vv2 = pos_a[idx_a[:, 0]], pos_a[idx_a[:, 1]], pos_a[idx_a[:, 2]]
    if float(np.sum(np.einsum("ij,ij->i", vv0, np.cross(vv1, vv2)))) < 0.0:
        idx_a = idx_a[:, [0, 2, 1]]
    head_mesh = MeshPart(pos_a, uv_a, np.broadcast_to(rgba(255, 255, 255, 62), (len(pos_a), 4)).copy(), idx_a)

    # Sculpted 3D Anime Hair Volume + Feathered Forehead Fringe & Sideburn Locks!
    hair_rings = []
    h_seg = (16, 12, 8)[lod]
    hang = np.linspace(-math.pi, math.pi, h_seg, endpoint=False, dtype=np.float32)
    for hy, hrx, hrz in [
        (0.088, 0.095, 0.104),
        (0.152, 0.103, 0.112),
        (0.208, 0.105, 0.115),
        (0.254, 0.086, 0.096),
        (0.276, 0.040, 0.046),
    ]:
        front_mask = np.clip(1.42 - np.abs(hang), 0.0, 1.0)
        tuck = front_mask * (0.070 if hy < 0.192 else 0.010)
        pts = np.stack([np.sin(hang) * (hrx - tuck * 0.45), np.full_like(hang, hy), -0.012 + np.cos(hang) * (hrz - tuck)], axis=1)
        hair_rings.append(pts)
    hair = make_loft(hair_rings, UV_HAIR, col=rgba(255, 255, 255, 82))

    parts = [head_mesh, hair]
    if lod <= 1:
        # 5 tapered 3D anime forehead bangs & temple sideburn locks (stay cleanly above y=0.192 so brows & eyes remain 100% clear!)
        bang_specs = [
            (-0.072, 0.218, 0.074, -0.082, 0.156, 0.062, 0.016),
            (-0.036, 0.226, 0.092, -0.040, 0.193, 0.096, 0.014),
            ( 0.002, 0.228, 0.096,  0.006, 0.195, 0.100, 0.015),
            ( 0.038, 0.226, 0.092,  0.042, 0.193, 0.095, 0.014),
            ( 0.072, 0.218, 0.074,  0.082, 0.156, 0.062, 0.016),
        ]
        for x0, y0, z0, x1, y1, z1, r0 in bang_specs:
            parts.append(make_tube_segment((x0, y0, z0), (x1, y1, z1), r0, 0.004, UV_HAIR, seg=5, col=rgba(255, 255, 255, 84), ball_caps=False))
        # Sculpted human ears on both sides
        for sx in (-1.0, 1.0):
            parts.append(make_sphere_uv(0.015, 0.028, 0.019, UV_SKIN, seg=7, rings=5, col=rgba(245, 238, 234, 58), center=(sx * 0.092, 0.132, -0.004)))
    return merge_parts(parts)


def build_char_face_neutral(lod: int) -> MeshPart:
    """Flush-contoured 3D anime upper-eyelash arcs + expressive tapered brows (zero protruding bug-eyeball spheres!)."""
    seg = (8, 6, 5)[lod]
    parts = []
    for sx in (-1.0, 1.0):
        # Sleek upper eyelash fold sitting cleanly along the top of the UV_FACE anime iris
        parts.append(make_tube_segment((sx * 0.052, 0.153, 0.093), (sx * 0.022, 0.155, 0.101),
                                       0.0032, 0.0028, UV_HAIR, seg=seg, col=rgba(24, 18, 15, 210), ball_caps=False))
        # Confident tapered 3D eyebrow above the brow ridge
        parts.append(make_tube_segment((sx * 0.060, 0.173, 0.084), (sx * 0.018, 0.176, 0.101),
                                       0.0042, 0.0052, UV_HAIR, seg=seg, col=rgba(36, 26, 20, 215), ball_caps=False))
    # Subtle flush lower-lip shadow crease
    parts.append(make_tube_segment((-0.012, 0.072, 0.097), (0.012, 0.072, 0.097),
                                   0.0024, 0.0024, UV_SKIN, seg=seg, col=rgba(148, 86, 68, 165), ball_caps=False))
    return merge_parts(parts)


def build_char_face_strain(lod: int) -> MeshPart:
    """Determined anime effort expression for heavy TBS hoist pose (furrowed brows + grit mouth, flush to face)."""
    parts = []
    seg = (8, 6, 5)[lod]
    for sx in (-1.0, 1.0):
        parts.append(make_tube_segment((sx * 0.052, 0.150, 0.094), (sx * 0.020, 0.148, 0.102),
                                       0.0038, 0.0038, UV_HAIR, seg=seg, col=rgba(24, 18, 15, 225), ball_caps=False))
        parts.append(make_tube_segment((sx * 0.062, 0.178, 0.082), (sx * 0.016, 0.165, 0.103),
                                       0.0055, 0.0065, UV_HAIR, seg=seg, col=rgba(34, 24, 18, 225), ball_caps=False))
    parts.append(make_sphere_uv(0.016, 0.012, 0.005, UV_STEEL, seg=seg, rings=5,
                                col=rgba(78, 34, 30, 215), center=(0.0, 0.075, 0.099)))
    parts.append(make_tube_segment((-0.011, 0.081, 0.102), (0.011, 0.081, 0.102),
                                   0.0028, 0.0028, UV_CONCRETE_CLEAN, seg=6, col=rgba(242, 238, 228, 220), ball_caps=False))
    return merge_parts(parts)


def build_char_arm(lod: int) -> MeshPart:
    """Seamless ball-jointed upper arm: rolled field-shirt sleeve cuff + toned bicep/tricep!"""
    seg = (12, 9, 6)[lod]
    sleeve = make_loft([
        ring_ellipse(0.056, 0.056,  0.045, seg),
        ring_ellipse(0.062, 0.062, -0.015, seg),
        ring_ellipse(0.055, 0.055, -0.105, seg),
    ], UV_SHIRT_PLAIN, col=rgba(255, 255, 255, 52), dyeable=True)
    cuff = make_loft([
        ring_ellipse(0.060, 0.060, -0.095, seg),
        ring_ellipse(0.059, 0.059, -0.122, seg),
    ], UV_SHIRT_PLAIN, col=rgba(235, 238, 242, 50), dyeable=True)
    bicep = make_tube_segment((0.0, -0.112, 0.0), (0.0, -0.275, 0.0), 0.046, 0.040, UV_SKIN, seg=seg, col=rgba(255, 255, 255, 62), ball_caps=True)
    return merge_parts([sleeve, cuff, bicep])


def build_char_forearm_hand(lod: int) -> MeshPart:
    """Seamless forearm + wrist + anatomically curved palm, thumb & fingers (grips tools & TBS naturally!)."""
    seg = (12, 9, 6)[lod]
    forearm = make_tube_segment((0.0, 0.015, 0.0), (0.0, -0.235, 0.010), 0.042, 0.032, UV_SKIN, seg=seg, col=rgba(255, 255, 255, 68), ball_caps=True)
    wristband = make_loft([ring_ellipse(0.035, 0.035, -0.215, seg, cz=0.009), ring_ellipse(0.034, 0.034, -0.238, seg, cz=0.010)],
                          UV_DENIM, col=rgba(40, 44, 52, 80))
    # Natural palm + curved gripping fingers & opposable thumb!
    palm = make_sphere_uv(0.038, 0.046, 0.022, UV_SKIN, seg=9, rings=6, col=rgba(255, 255, 255, 68), center=(0.0, -0.272, 0.016))
    parts = [forearm, wristband, palm]
    if lod <= 1:
        for fx in (-0.024, -0.008, 0.008, 0.024):
            parts.append(make_tube_segment((fx, -0.305, 0.018), (fx * 0.92, -0.348, 0.038), 0.0095, 0.0075, UV_SKIN, seg=6, col=rgba(250, 245, 242, 68)))
        parts.append(make_tube_segment((0.030, -0.268, 0.020), (0.044, -0.306, 0.044), 0.011, 0.0085, UV_SKIN, seg=6, col=rgba(250, 245, 242, 68)))
    return merge_parts(parts)


def build_char_leg(lod: int) -> MeshPart:
    """Seamless hip-ball-capped athletic thigh + knee pad in rugged stitched dark denim (y = +0.04 .. -0.44)."""
    seg = (12, 9, 6)[lod]
    return make_tube_segment((0.0, 0.035, 0.0), (0.0, -0.430, 0.0), 0.082, 0.062, UV_DENIM, seg=seg, col=rgba(255, 255, 255, 62), ball_caps=True)


def build_char_calf_boot(lod: int) -> MeshPart:
    """Seamless knee-capped calf tapering into authentic Indonesian tall green/yellow plantation rubber boot!"""
    seg = (12, 9, 6)[lod]
    upper_calf = make_tube_segment((0.0, 0.02, 0.0), (0.0, -0.16, 0.0), 0.060, 0.054, UV_DENIM, seg=seg, col=rgba(255, 255, 255, 60), ball_caps=True)
    boot_rings = [
        ring_ellipse(0.064, 0.072, -0.445, seg, cz=0.032),  # Lugged rubber sole
        ring_ellipse(0.062, 0.070, -0.405, seg, cz=0.026),  # Instep / ankle
        ring_ellipse(0.056, 0.058, -0.310, seg, cz=0.004),  # Boot shaft
        ring_ellipse(0.062, 0.064, -0.155, seg, cz=0.000),  # Yellow top boot cuff!
    ]
    boot = make_loft(boot_rings, UV_BOOT, col=rgba(255, 255, 255, 108))
    toe = make_sphere_uv(0.058, 0.042, 0.078, UV_BOOT, seg=9, rings=6, col=rgba(255, 255, 255, 96), center=(0.0, -0.415, 0.062))
    return merge_parts([upper_calf, boot, toe])


# ── Complete Authentic Indonesian Headgear, Eyewear, Back/Waist Gear & Tools ──

def build_hat_caping(lod: int) -> MeshPart:
    seg = (20, 14, 9)[lod]
    rings = [
        ring_ellipse(0.30, 0.30, -0.015, seg),
        ring_ellipse(0.21, 0.21,  0.045, seg),
        ring_ellipse(0.11, 0.11,  0.105, seg),
        ring_ellipse(0.025, 0.025, 0.155, seg),
    ]
    cone = make_loft(rings, UV_WOVEN, col=rgba(255, 255, 255, 72))
    rim = make_tube_segment((0.0, -0.015, 0.0), (0.0, -0.020, 0.0), 0.302, 0.296, UV_WOOD_PLAIN, seg=seg, col=rgba(110, 68, 34, 80), ball_caps=False)
    return merge_parts([cone, rim])


def build_hat_safety(lod: int) -> MeshPart:
    seg = (18, 12, 8)[lod]
    dome = make_sphere_uv(0.116, 0.095, 0.132, UV_CANTER_PAINT, seg=seg, rings=7, col=rgba(255, 255, 255, 175), center=(0.0, 0.02, 0.0))
    brim = make_loft([ring_ellipse(0.122, 0.155, -0.012, seg, cz=0.022), ring_ellipse(0.118, 0.148, 0.004, seg, cz=0.020)],
                     UV_CANTER_PAINT, col=rgba(255, 255, 255, 175))
    ridge = make_box(0.032, 0.026, 0.21, UV_CANTER_PAINT, rgba(255, 255, 255, 185), center=(0.0, 0.098, 0.0))
    return merge_parts([dome, brim, ridge])


def build_hat_headband(lod: int) -> MeshPart:
    seg = (16, 12, 8)[lod]
    band = make_loft([ring_ellipse(0.103, 0.114, -0.055, seg), ring_ellipse(0.104, 0.115, -0.012, seg)],
                     UV_SHIRT_PLAIN, col=rgba(220, 38, 38, 65), dyeable=True)
    tail1 = make_box(0.026, 0.11, 0.012, UV_SHIRT_PLAIN, rgba(220, 38, 38, 65), dyeable=True, center=(-0.025, -0.09, -0.125))
    tail2 = make_box(0.026, 0.10, 0.012, UV_SHIRT_PLAIN, rgba(220, 38, 38, 65), dyeable=True, center=(0.025, -0.085, -0.125))
    return merge_parts([band, xform(tail1, rz=0.22), xform(tail2, rz=-0.25)])


def build_hat_cowboy(lod: int) -> MeshPart:
    # Authentic Indonesian Field "Topi Rimba" / Plantation Boonie Hat!
    seg = (18, 12, 8)[lod]
    brim = make_loft([ring_ellipse(0.21, 0.22, -0.020, seg), ring_ellipse(0.118, 0.128, 0.005, seg)],
                     UV_SHIRT_PLAIN, col=rgba(195, 185, 160, 58), dyeable=True)
    crown = make_loft([ring_ellipse(0.112, 0.122, 0.0, seg), ring_ellipse(0.104, 0.114, 0.078, seg)],
                      UV_SHIRT_PLAIN, col=rgba(210, 200, 175, 58), dyeable=True)
    ribbon = make_loft([ring_ellipse(0.115, 0.125, 0.004, seg), ring_ellipse(0.114, 0.124, 0.026, seg)],
                       UV_WOOD_PLAIN, col=rgba(64, 48, 32, 75))
    return merge_parts([brim, crown, ribbon])


def build_hat_crown_gold(lod: int) -> MeshPart:
    seg = (16, 12, 8)[lod]
    gold = rgba(255, 208, 48, 228)
    gem  = rgba(36, 225, 130, 245)
    parts = [make_loft([ring_ellipse(0.106, 0.116, -0.03, seg), ring_ellipse(0.112, 0.122, 0.035, seg)], UV_STEEL, col=gold)]
    n_sp = 8 if lod == 0 else 6
    for i in range(n_sp):
        a = i * 2.0 * math.pi / n_sp
        parts.append(make_tube_segment((math.sin(a) * 0.108, 0.03, math.cos(a) * 0.118),
                                       (math.sin(a) * 0.118, 0.125, math.cos(a) * 0.128), 0.018, 0.004, UV_STEEL, seg=5, col=gold, ball_caps=False))
        parts.append(make_sphere_uv(0.012, 0.014, 0.010, UV_STEEL, seg=6, rings=4, col=gem, center=(math.sin(a) * 0.112, 0.012, math.cos(a) * 0.122)))
    return merge_parts(parts)


def build_acc_glasses(lod: int) -> MeshPart:
    """Wraparound UV Tactical Cyan-Tinted Sunglasses on Head bone (solid glossy lenses, never cutout)!"""
    frame = rgba(24, 26, 30, 155)
    lens  = rgba(32, 168, 196, 242)
    parts = [
        make_box(0.195, 0.012, 0.014, UV_STEEL, frame, center=(0.0, 0.158, 0.106)),
        make_box(0.074, 0.036, 0.012, UV_CONCRETE_CLEAN, lens, center=(-0.048, 0.142, 0.108)),
        make_box(0.074, 0.036, 0.012, UV_CONCRETE_CLEAN, lens, center=( 0.048, 0.142, 0.108)),
        make_box(0.009, 0.009, 0.115, UV_STEEL, frame, center=(-0.096, 0.152, 0.048)),
        make_box(0.009, 0.009, 0.115, UV_STEEL, frame, center=( 0.096, 0.152, 0.048)),
    ]
    return merge_parts(parts)


def build_acc_parang_waist(lod: int) -> MeshPart:
    """Authentic Carved Wooden Machete/Golok Sheath ('Parang Sawit') strapped to right hip!"""
    scabbard = make_box(0.030, 0.34, 0.068, UV_WOOD_PLAIN, rgba(132, 76, 34, 95), center=(0.0, -0.14, 0.0))
    bands = [make_box(0.036, 0.022, 0.074, UV_STEEL, rgba(210, 175, 58, 175), center=(0.0, y, 0.0)) for y in (-0.02, -0.15, -0.27)]
    hilt = make_tube_segment((0.0, 0.03, 0.0), (0.01, 0.15, 0.03), 0.022, 0.026, UV_WOOD_PLAIN, seg=7, col=rgba(72, 42, 20, 105))
    return xform(merge_parts([scabbard, hilt, *bands]), rx=0.42, rz=-0.12)


def build_back_basket(lod: int) -> MeshPart:
    seg = (16, 12, 8)[lod]
    basket = make_loft([
        ring_ellipse(0.135, 0.115, -0.18, seg),
        ring_ellipse(0.165, 0.140, -0.02, seg),
        ring_ellipse(0.195, 0.165,  0.16, seg),
    ], UV_WOVEN, col=rgba(255, 255, 255, 68))
    rim = make_tube_segment((0.0, 0.155, 0.0), (0.0, 0.172, 0.0), 0.198, 0.198, UV_WOOD_PLAIN, seg=seg, col=rgba(118, 76, 36, 80), ball_caps=False)
    tbs = xform(build_tbs_bunch(2), scale=(0.62, 0.62, 0.62), translate=(0.0, 0.14, 0.0))
    return merge_parts([basket, rim, tbs])


def build_back_pack(lod: int) -> MeshPart:
    pack = make_sphere_uv(0.155, 0.215, 0.095, UV_DENIM, seg=12, rings=8, col=rgba(78, 96, 68, 65), center=(0.0, 0.0, -0.02))
    pouch = make_box(0.21, 0.15, 0.065, UV_DENIM, rgba(64, 78, 56, 62), center=(0.0, -0.06, -0.09))
    roll = make_tube_segment((-0.15, 0.21, -0.02), (0.15, 0.21, -0.02), 0.052, 0.052, UV_WOVEN, seg=8, col=rgba(195, 165, 110, 60))
    canteen = make_tube_segment((0.155, -0.12, -0.02), (0.155, 0.02, -0.02), 0.042, 0.036, UV_STEEL, seg=8, col=rgba(52, 118, 78, 120))
    return merge_parts([pack, pouch, roll, canteen])


def build_back_cape(lod: int) -> MeshPart:
    pts = []
    segs = 6 if lod == 0 else 4
    pos, uv01, tris = [], [], []
    for i in range(segs + 1):
        t = i / segs
        w = 0.20 + 0.16 * t
        y = 0.14 - t * 0.72
        z = -0.02 - 0.11 * (t ** 1.5)
        for j in range(5):
            u = j / 4.0
            ripple = math.sin(u * math.pi * 3.0) * 0.025 * t
            pos.append([(u - 0.5) * 2.0 * w, y, z + ripple])
            uv01.append([u, t])
    for i in range(segs):
        for j in range(4):
            b0, b1 = i * 5 + j, (i + 1) * 5 + j
            tris.extend([[b0, b0 + 1, b1 + 1], [b0, b1 + 1, b1]])
    return make_quad((-0.24, -0.58, -0.12), (0.24, -0.58, -0.12), (0.20, 0.14, -0.02), (-0.20, 0.14, -0.02),
                     UV_SHIRT_PLAIN, col=rgba(235, 235, 235, 65), dyeable=True, double_sided=True) if len(tris) == 0 else MeshPart(
        np.vstack([pos, pos]).astype(np.float32),
        np.vstack([map_uv(np.array(uv01, np.float32), UV_SHIRT_PLAIN, True)] * 2),
        np.broadcast_to(rgba(240, 240, 240, 68), (len(pos) * 2, 4)).copy(),
        np.vstack([np.array(tris, np.int32), np.array(tris, np.int32)[:, [0, 2, 1]] + len(pos)])
    )


def build_back_wings_gold(lod: int) -> MeshPart:
    gold = rgba(255, 210, 56, 228)
    parts = [make_sphere_uv(0.075, 0.095, 0.055, UV_STEEL, seg=8, rings=5, col=gold)]
    n_f = (7, 5, 4)[lod]
    for side in (-1.0, 1.0):
        parts.append(make_tube_segment((side * 0.05, 0.04, 0.0), (side * 0.42, 0.28, -0.06), 0.026, 0.018, UV_STEEL, seg=6, col=gold))
        parts.append(make_tube_segment((side * 0.42, 0.28, -0.06), (side * 0.78, 0.14, -0.12), 0.018, 0.010, UV_STEEL, seg=6, col=gold))
        for k in range(n_f):
            t = k / (n_f - 1.0)
            ax = side * (0.14 + t * 0.58)
            ay = 0.08 + math.sin(t * math.pi * 0.85) * 0.18
            ln = 0.46 - 0.16 * (1.0 - t)
            ang = side * (0.35 + t * 0.65)
            feather = make_box(0.048, ln, 0.010, UV_STEEL, gold, center=(0.0, -ln * 0.5, 0.0))
            parts.append(xform(feather, rz=ang, rx=-0.10, translate=(ax, ay, -0.06 - t * 0.05)))
    return merge_parts(parts)


def build_tool_egrek(lod: int) -> MeshPart:
    """
    Authentic Indonesian 5.05m 3-Stage Telescopic Sawit Egrek ('Galah Sawit Tinggi + Pisau Egrek SBL Baja Putih')!
    Exact Hand Grip Anchors in Local Pole Space (0.0mm slip):
      - Lower Power Hand Grip: y = -0.18m  (rubberized red anti-slip sleeve y = -0.42 .. +0.04)
      - Upper Guide Hand Grip: y = +0.44m  (rubberized emerald grip sleeve y = +0.25 .. +0.64)
      - Stage 1 Anodized Alloy Pole: y = -0.46 .. +1.46  (Dia 38mm) + Red Twist-Lock Clamp Collar #1
      - Stage 2 Telescopic Mid Pole: y = +1.52 .. +3.06  (Dia 31mm) + Gold Twist-Lock Clamp Collar #2
      - Stage 3 Slim Upper Whip Pole: y = +3.11 .. +4.04 (Dia 24mm) + Bolted SBL Holder Bracket
      - High-Carbon Curved Pull-Cut Sickle Blade ('Pisau Egrek SBL'): y = +4.12 .. +4.57m;
        complete butt-cap-to-tip length = 5.03m, within 20mm of the 5.05m tool spec.
    """
    seg = (10, 7, 5)[lod]
    parts = [
        make_sphere_uv(0.026, 0.024, 0.026, UV_STEEL, seg=8, rings=5, col=rgba(30, 34, 40, 120), center=(0.0, -0.46, 0.0)),
        make_tube_segment((0.0, -0.46, 0.0), (0.0, 1.46, 0.0), 0.0195, 0.0175, UV_STEEL, seg=seg, col=rgba(210, 218, 228, 175), ball_caps=False),
        make_tube_segment((0.0, -0.42, 0.0), (0.0, 0.04, 0.0), 0.0235, 0.0230, UV_DENIM, seg=seg, col=rgba(214, 46, 38, 85), ball_caps=False),
        make_tube_segment((0.0, 0.25, 0.0), (0.0, 0.64, 0.0), 0.0225, 0.0220, UV_BOOT, seg=seg, col=rgba(46, 158, 92, 90), ball_caps=False),
        make_tube_segment((0.0, 1.40, 0.0), (0.0, 1.54, 0.0), 0.0255, 0.0245, UV_CANTER_PAINT, seg=seg, col=rgba(235, 68, 42, 185), ball_caps=False),
        make_tube_segment((0.0, 1.52, 0.0), (0.0, 3.06, 0.0), 0.0155, 0.0140, UV_STEEL, seg=seg, col=rgba(226, 234, 242, 185), ball_caps=False),
        make_tube_segment((0.0, 3.00, 0.0), (0.0, 3.13, 0.0), 0.0220, 0.0210, UV_CANTER_PAINT, seg=seg, col=rgba(245, 192, 32, 190), ball_caps=False),
        make_tube_segment((0.0, 3.11, 0.0), (0.0, 4.04, 0.02), 0.0125, 0.0108, UV_STEEL, seg=seg, col=rgba(234, 240, 248, 195), ball_caps=False),
        make_bevel_box(0.044, 0.16, 0.048, UV_STEEL, rgba(238, 184, 34, 205), center=(0.0, 4.08, 0.022), bev=0.008),
    ]
    b_steps = 10 if lod == 0 else 6
    for i in range(b_steps):
        t0, t1 = i / b_steps, (i + 1) / b_steps
        a0, a1 = t0 * 2.38, t1 * 2.38
        p0 = (0.0, 4.12 + math.sin(a0 * 0.62) * 0.45, 0.022 + (1.0 - math.cos(a0)) * 0.21)
        p1 = (0.0, 4.12 + math.sin(a1 * 0.62) * 0.45, 0.022 + (1.0 - math.cos(a1)) * 0.21)
        w = 0.036 * (1.0 - 0.72 * t0)
        parts.append(make_tube_segment(p0, p1, w, max(0.004, w * 0.84), UV_STEEL, seg=5, col=rgba(250, 253, 255, 238), ball_caps=False))
    return merge_parts(parts)


def build_tool_dodos(lod: int) -> MeshPart:
    """Authentic Long Heavy Iron-Wood & Steel 'Dodos Sawit Lebar' (2.35m) with Two-Hand Grip Locks!"""
    seg = (10, 7, 5)[lod]
    shaft = make_tube_segment((0.0, -0.44, 0.0), (0.0, 1.12, 0.0), 0.022, 0.019, UV_WOOD_PLAIN, seg=seg, col=rgba(168, 108, 54, 80))
    grip_lo = make_tube_segment((0.0, -0.38, 0.0), (0.0, 0.02, 0.0), 0.025, 0.025, UV_DENIM, seg=seg, col=rgba(42, 46, 54, 85), ball_caps=False)
    grip_hi = make_tube_segment((0.0, 0.28, 0.0), (0.0, 0.62, 0.0), 0.024, 0.024, UV_DENIM, seg=seg, col=rgba(204, 48, 38, 85), ball_caps=False)
    socket = make_tube_segment((0.0, 1.06, 0.0), (0.0, 1.24, 0.0), 0.028, 0.032, UV_STEEL, seg=seg, col=rgba(74, 80, 90, 165), ball_caps=False)
    chisel = make_loft([
        ring_ellipse(0.036, 0.012, 1.24, 6),
        ring_ellipse(0.078, 0.010, 1.58, 6),
        ring_ellipse(0.098, 0.003, 1.91, 6),
    ], UV_STEEL, col=rgba(245, 250, 255, 225))
    return merge_parts([shaft, grip_lo, grip_hi, socket, chisel])


def build_tool_tojok(lod: int) -> MeshPart:
    """Authentic Indonesian 'Tojok Sawit Baja' (1.55m) T-Bar Loading Spear!"""
    seg = (10, 7, 5)[lod]
    t_bar = make_tube_segment((-0.14, -0.44, 0.0), (0.14, -0.44, 0.0), 0.018, 0.018, UV_STEEL, seg=seg, col=rgba(214, 48, 38, 130))
    rod = make_tube_segment((0.0, -0.44, 0.0), (0.0, 0.95, 0.0), 0.017, 0.014, UV_STEEL, seg=seg, col=rgba(208, 216, 226, 185))
    spike = make_tube_segment((0.0, 0.95, 0.0), (0.0, 1.11, 0.04), 0.015, 0.002, UV_STEEL, seg=seg, col=rgba(250, 252, 255, 238), ball_caps=False)
    return merge_parts([t_bar, rod, spike])


def build_tool_egrek_dragon(lod: int) -> MeshPart:
    """Legendary Golden Sultan 5.05m Carbon-Gold Egrek Naga with Sculpted Twin Dragon Horns, Emerald Core & Golden Spine!"""
    base = build_tool_egrek(lod)
    gold = rgba(255, 208, 48, 238)
    carbon = rgba(28, 32, 40, 175)
    parts = [
        base,
        # Carbon-black & royal-gold banded telescopic mid pole
        make_tube_segment((0.0, 1.54, 0.0), (0.0, 3.00, 0.0), 0.0175, 0.0160, UV_STEEL, seg=8, col=carbon, ball_caps=False),
        make_tube_segment((0.0, 1.82, 0.0), (0.0, 1.96, 0.0), 0.0195, 0.0195, UV_STEEL, seg=8, col=gold, ball_caps=False),
        make_tube_segment((0.0, 2.38, 0.0), (0.0, 2.52, 0.0), 0.0188, 0.0188, UV_STEEL, seg=8, col=gold, ball_caps=False),
        # Sculpted Dragon Head Crest Guard + Glowing Emerald Core + Twin Swept Golden Horns!
        make_sphere_uv(0.056, 0.082, 0.080, UV_STEEL, seg=9, rings=6, col=gold, center=(0.0, 4.10, 0.032)),
        make_sphere_uv(0.028, 0.038, 0.028, UV_CONCRETE_CLEAN, seg=7, rings=5, col=rgba(40, 248, 152, 253), center=(0.0, 4.10, 0.092)),
    ]
    if lod <= 1:
        for sx in (-1.0, 1.0):
            parts.append(make_tube_segment((sx * 0.038, 4.11, 0.02), (sx * 0.115, 4.24, -0.045), 0.018, 0.004, UV_STEEL, seg=6, col=gold, ball_caps=False))
            parts.append(make_tube_segment((sx * 0.032, 4.06, 0.03), (sx * 0.085, 3.98, -0.025), 0.013, 0.003, UV_STEEL, seg=5, col=gold, ball_caps=False))
        # Golden dragon dorsal rib backing along upper crescent blade
        for i in range(5):
            a0, a1 = (i / 5.0) * 1.9, ((i + 1) / 5.0) * 1.9
            p0 = (0.0, 4.12 + math.sin(a0 * 0.62) * 0.44, 0.008 + (1.0 - math.cos(a0)) * 0.20)
            p1 = (0.0, 4.12 + math.sin(a1 * 0.62) * 0.44, 0.008 + (1.0 - math.cos(a1)) * 0.20)
            parts.append(make_tube_segment(p0, p1, 0.014, 0.006, UV_STEEL, seg=5, col=gold, ball_caps=False))
    return merge_parts(parts)


# ═══════════════════════════════════════════════════════════════════════════
# 4. DEDICATED 3D GARAGE / WORKSHOP LOBBY SCENE + WORLD BUILDINGS & VEHICLES
# ═══════════════════════════════════════════════════════════════════════════

def build_garage_showroom(lod: int) -> MeshPart:
    """
    DEDICATED 3D GARAGE / WORKSHOP LOBBY SCENE (100% SEPARATE FROM GAMEPLAY MAP!):
    - Brushed concrete workshop floor pad (18m x 14m) with yellow industrial stripes
    - Circular raised steel-rimmed showroom turntable pad for Hero Character & Canter
    - Open-bay structural steel columns, timber roof trusses & gabled corrugated steel roof
    - Back workshop wall, tool pegboard, spare tires & stacked sawit crates + warm overhead lamps!
    """
    parts = []
    # 1. Workshop concrete floor slab + raised circular turntable pad at origin (0, 0, 0)
    parts.append(make_box(18.0, 0.24, 15.0, UV_CONCRETE, rgba(245, 245, 245, 85), center=(0.0, -0.12, 0.0)))
    parts.append(make_loft([ring_ellipse(4.35, 4.35, 0.0, 24), ring_ellipse(4.28, 4.28, 0.075, 24)],
                           UV_CONCRETE_CLEAN, col=rgba(62, 68, 76, 135)))
    parts.append(make_loft([ring_ellipse(4.42, 4.42, 0.005, 24), ring_ellipse(4.35, 4.35, 0.065, 24)],
                           UV_CANTER_PAINT, col=rgba(245, 196, 24, 165)))

    # 2. Structural steel H-columns around open-air tropical garage bay
    col_metal = rgba(48, 56, 66, 125)
    for gx in (-6.8, 6.8):
        for gz in (-5.6, 0.0, 5.6):
            parts.append(make_box(0.26, 4.90, 0.26, UV_STEEL, col_metal, center=(gx, 2.45, gz)))
            parts.append(make_box(0.46, 0.14, 0.46, UV_CANTER_PAINT, rgba(235, 185, 24, 130), center=(gx, 0.07, gz)))

    # 3. Gabled corrugated steel roof + steel roof trusses + warm emissive workshop light bars!
    left_roof = make_box(8.2, 0.10, 12.6, UV_CORRUGATED, rgba(215, 222, 230, 135), center=(0.0, 0.0, 0.0))
    parts.append(xform(left_roof, rz=0.19, translate=(-3.75, 5.55, 0.0)))
    parts.append(xform(left_roof, rz=-0.19, translate=(3.75, 5.55, 0.0)))
    for gz in (-5.6, 0.0, 5.6):
        parts.append(make_box(14.0, 0.18, 0.16, UV_STEEL, col_metal, center=(0.0, 4.82, gz)))
        parts.append(make_box(1.85, 0.09, 0.14, UV_CANTER_HEADLAMP, rgba(255, 248, 228, 253), center=(0.0, 4.70, gz)))

    # 4. Back workshop wall (-Z = -5.7m) with open tropical breeze louver gap at top + workbench + oil drums + crates!
    parts.append(make_box(13.8, 2.95, 0.22, UV_WOOD_PLAIN, rgba(196, 175, 148, 65), center=(0.0, 1.48, -5.72)))
    parts.append(make_box(4.6, 1.45, 0.08, UV_STEEL, rgba(38, 44, 52, 115), center=(-3.2, 2.05, -5.56)))
    parts.append(make_box(4.8, 0.92, 0.85, UV_WOOD_BAK, rgba(235, 220, 205, 85), center=(-3.2, 0.46, -5.05)))
    if lod == 0:
        for di, dx in enumerate((3.8, 4.65, 5.45)):
            drum_col = rgba(38, 112, 192, 140) if di % 2 == 0 else rgba(212, 62, 42, 140)
            parts.append(make_tube_segment((dx, 0.0, -4.85), (dx, 0.94, -4.85), 0.30, 0.30, UV_STEEL, seg=12, col=drum_col, ball_caps=False))
        # Stacked spare Canter tires in corner!
        w_spare = build_truck_wheel(1)
        parts.append(xform(w_spare, rz=math.pi * 0.5, translate=(-5.55, 0.16, -4.65)))
        parts.append(xform(w_spare, rz=math.pi * 0.5, translate=(-5.50, 0.46, -4.62)))
        parts.append(xform(build_tbs_bunch(1), scale=(1.2, 1.2, 1.2), translate=(3.15, 0.26, -4.75)))
        parts.append(xform(build_tbs_bunch(1), scale=(1.15, 1.15, 1.15), ry=1.4, translate=(2.55, 0.24, -4.60)))
    return merge_parts(parts)


def build_angkong_cart(lod: int) -> MeshPart:
    """
    Millimeter-Precision Indonesian Sawit 'Angkong' Wheelbarrow (0.0mm Floating Wheel or Floating Hands!):
      - Bolted steel front axle bearing brackets lock directly around spinning wheel hub (0.000, 0.290, +0.800)
      - Ergonomically rising tubular push shafts curve smoothly to waist-height red rubber grips (±0.310, 0.800, -0.960)
      - Solid ground rest skids touch terrain cleanly at y = 0.000m when parked!
    """
    parts = [make_bevel_box(0.56, 0.055, 0.90, UV_WOOD_PLAIN, rgba(255, 255, 255, 85), center=(0.0, 0.37, 0.05), bev=0.012)]
    n_p = 4 if lod == 0 else 2
    for p in range(n_p):
        py = 0.42 + p * (0.28 / max(1, n_p - 1))
        ph = 0.082 if lod == 0 else 0.16
        flare = 0.29 + p * 0.045
        for sx in (-1.0, 1.0):
            parts.append(xform(make_bevel_box(0.042, ph, 0.96 + p * 0.05, UV_WOOD_PLAIN, rgba(255, 255, 255, 85), bev=0.01), rz=sx * -0.22, translate=(sx * flare, py, 0.05)))
        parts.append(xform(make_bevel_box(flare * 2.0, ph, 0.042, UV_WOOD_PLAIN, rgba(255, 255, 255, 85), bev=0.01), rx=0.24, translate=(0.0, py, 0.52 + p * 0.03)))
        parts.append(xform(make_bevel_box(flare * 2.0, ph, 0.042, UV_WOOD_PLAIN, rgba(255, 255, 255, 85), bev=0.01), rx=-0.16, translate=(0.0, py, -0.42 - p * 0.02)))

    # Solid steel axle shaft passing straight through wheel center (0.000, 0.290, 0.800) + front tubular bumper hoop!
    parts.append(make_tube_segment((-0.135, 0.290, 0.800), (0.135, 0.290, 0.800), 0.022, 0.022, UV_STEEL, seg=8, col=rgba(62, 68, 78, 175)))
    parts.append(make_tube_segment((-0.26, 0.38, -0.42), (0.26, 0.38, -0.42), 0.020, 0.020, UV_STEEL, seg=6, col=rgba(54, 60, 68, 145)))
    if lod <= 1:
        # Protective steel front bumper hoop around Angkong wheel + top tub steel rim rail!
        parts.append(make_tube_segment((-0.115, 0.290, 0.800), (-0.145, 0.310, 1.120), 0.018, 0.018, UV_STEEL, seg=6, col=rgba(52, 58, 66, 165)))
        parts.append(make_tube_segment(( 0.115, 0.290, 0.800), ( 0.145, 0.310, 1.120), 0.018, 0.018, UV_STEEL, seg=6, col=rgba(52, 58, 66, 165)))
        parts.append(make_tube_segment((-0.145, 0.310, 1.120), ( 0.145, 0.310, 1.120), 0.019, 0.019, UV_STEEL, seg=6, col=rgba(52, 58, 66, 165)))
        parts.append(make_tube_segment((-0.44, 0.74, 0.62), (0.44, 0.74, 0.62), 0.016, 0.016, UV_STEEL, seg=6, col=rgba(52, 58, 68, 165)))
        parts.append(make_tube_segment((-0.44, 0.74, -0.48), (0.44, 0.74, -0.48), 0.016, 0.016, UV_STEEL, seg=6, col=rgba(52, 58, 68, 165)))
        for sx_r in (-0.44, 0.44):
            parts.append(make_tube_segment((sx_r, 0.74, -0.48), (sx_r, 0.74, 0.62), 0.016, 0.016, UV_STEEL, seg=6, col=rgba(52, 58, 68, 165)))

    for sx in (-1.0, 1.0):
        # Front steel fork chassis rails meeting exact axle bearing block at (sx * 0.115, 0.290, 0.800)!
        parts.append(make_bevel_box(0.042, 0.075, 0.095, UV_STEEL, rgba(52, 58, 66, 165), center=(sx * 0.115, 0.290, 0.800), bev=0.008))
        parts.append(make_tube_segment((sx * 0.26, 0.36, 0.42), (sx * 0.115, 0.290, 0.800), 0.026, 0.024, UV_STEEL, seg=6, col=rgba(62, 68, 76, 155)))
        parts.append(make_tube_segment((sx * 0.26, 0.36, 0.42), (sx * 0.28, 0.56, -0.46), 0.028, 0.028, UV_STEEL, seg=6, col=rgba(62, 68, 76, 155)))
        # Ergonomic rising handle bars curving cleanly up to exact waist grip center (sx * 0.310, 0.800, -0.960)!
        parts.append(make_tube_segment((sx * 0.28, 0.56, -0.46), (sx * 0.305, 0.775, -0.84), 0.026, 0.025, UV_STEEL, seg=6, col=rgba(74, 82, 92, 165)))
        parts.append(make_tube_segment((sx * 0.305, 0.775, -0.84), (sx * 0.315, 0.825, -1.08), 0.032, 0.031, UV_DENIM, seg=8, col=rgba(228, 52, 38, 105)))
        # Solid rear support legs touching y = 0.000m cleanly when resting + front brace
        parts.append(make_tube_segment((sx * 0.27, 0.48, -0.36), (sx * 0.27, 0.02, -0.44), 0.024, 0.022, UV_STEEL, seg=6, col=rgba(54, 60, 68, 145)))
        parts.append(make_tube_segment((sx * 0.27, 0.02, -0.44), (sx * 0.26, 0.36, 0.08), 0.020, 0.020, UV_STEEL, seg=6, col=rgba(54, 60, 68, 145)))
        parts.append(make_box(0.05, 0.34, 0.05, UV_STEEL, rgba(54, 60, 68, 125), center=(sx * 0.38, 0.54, 0.42)))
    parts.append(xform(build_tbs_bunch(2), scale=(0.88, 0.88, 0.88), translate=(-0.10, 0.62, 0.14)))
    parts.append(xform(build_tbs_bunch(2), scale=(0.84, 0.84, 0.84), ry=1.7, translate=(0.12, 0.60, -0.14)))
    return merge_parts(parts)


def build_canter_axle_suspension(lod: int) -> MeshPart:
    """
    Real Heavy-Duty Mitsubishi Canter FE 74 HD Live Solid Axle + Differential Pumpkin ('Gardan') +
    7-Layer Semi-Elliptical Multi-Leaf Spring Packs ('Per Daun Baja') + Twin Yellow Telescopic Shocks!
    Origin (0, 0, 0) = Exact Wheel Axle Centerline; Top Shackle Mounts sit at y = +0.260m (dynamically compressed per frame!).
    """
    seg = (12, 8, 6)[lod]
    steel_dark = rgba(44, 50, 58, 155)
    spring_steel = rgba(62, 68, 78, 168)
    shock_yellow = rgba(248, 198, 28, 195)
    chrome_rod = rgba(236, 242, 248, 232)

    parts = [
        # Solid forged steel live axle tube spanning full track width (-0.82m .. +0.82m) right into brake drums!
        make_tube_segment((-0.82, 0.0, 0.0), (0.82, 0.0, 0.0), 0.054, 0.054, UV_STEEL, seg=seg, col=steel_dark),
        # Central cast-iron Differential Banjo Housing ('Gardan Canter') + pinion yoke flange!
        make_sphere_uv(0.155, 0.165, 0.165, UV_STEEL, seg=seg, rings=7, col=steel_dark, center=(0.0, 0.0, 0.0)),
        make_tube_segment((0.0, 0.0, 0.10), (0.0, 0.015, 0.24), 0.068, 0.052, UV_STEEL, seg=8, col=spring_steel),
    ]
    for sx in (-1.0, 1.0):
        # Inner steel brake drum / steering knuckle backing plates flush against wheel hubs!
        parts.append(make_tube_segment((sx * 0.72, 0.0, 0.0), (sx * 0.83, 0.0, 0.0), 0.175, 0.165, UV_STEEL, seg=seg, col=rgba(54, 60, 70, 160), ball_caps=False))
        # U-bolt center clamp block locking 7-layer leaf spring pack onto axle tube at x = ±0.54m
        parts.append(make_bevel_box(0.11, 0.13, 0.14, UV_STEEL, rgba(34, 38, 46, 175), center=(sx * 0.54, 0.055, 0.0), bev=0.01))
        # 5 visible stacked arched semi-elliptical spring leaves curving cleanly up to front/rear frame shackles (y = +0.260m)!
        n_leaves = 5 if lod == 0 else 3
        for li in range(n_leaves):
            frac = 1.0 - li * 0.14
            half_len = 0.48 * frac
            base_y = 0.032 + li * 0.021
            for si in range(6):
                t0, t1 = -1.0 + si * (2.0 / 6.0), -1.0 + (si + 1) * (2.0 / 6.0)
                z0, z1 = t0 * half_len, t1 * half_len
                y0 = base_y + (t0 * t0) * (0.228 - base_y * 0.45)
                y1 = base_y + (t1 * t1) * (0.228 - base_y * 0.45)
                parts.append(make_tube_segment((sx * 0.54, y0, z0), (sx * 0.54, y1, z1), 0.016, 0.016, UV_STEEL, seg=4, col=spring_steel, ball_caps=False))
        # Front & rear shackle brackets meeting chassis rails at y = +0.260m!
        for sz in (-0.47, 0.47):
            parts.append(make_bevel_box(0.09, 0.08, 0.08, UV_STEEL, steel_dark, center=(sx * 0.54, 0.255, sz), bev=0.008))
        # Angled Heavy-Duty Yellow Hydraulic Telescopic Shock Absorbers + Chrome Piston Rod!
        parts.append(make_tube_segment((sx * 0.63, -0.02, -0.08), (sx * 0.58, 0.145, -0.05), 0.038, 0.036, UV_CANTER_PAINT, seg=8, col=shock_yellow))
        parts.append(make_tube_segment((sx * 0.58, 0.135, -0.05), (sx * 0.53, 0.265, -0.02), 0.020, 0.020, UV_STEEL, seg=8, col=chrome_rod))
    return merge_parts(parts)


def build_canter_driveshaft(lod: int) -> MeshPart:
    """Spinning Steel Propeller Driveshaft + Twin Universal Joints ('Kopel Gardan Canter') along unit +Z (0..1m)!"""
    seg = (10, 7, 5)[lod]
    shaft_col = rgba(68, 76, 88, 185)
    yoke_col = rgba(196, 206, 218, 215)
    return merge_parts([
        make_tube_segment((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 0.036, 0.036, UV_STEEL, seg=seg, col=shaft_col),
        make_bevel_box(0.095, 0.095, 0.10, UV_STEEL, yoke_col, center=(0.0, 0.0, 0.05), bev=0.012),
        make_bevel_box(0.095, 0.095, 0.10, UV_STEEL, yoke_col, center=(0.0, 0.0, 0.95), bev=0.012),
    ])


def build_canter_headlight_beam(lod: int) -> MeshPart:
    """Warm Halogen/LED Headlight Ground Projection Beam when Canter Headlights are switched ON!"""
    return merge_parts([
        make_quad((-0.26, 0.0, 0.0), (0.26, 0.0, 0.0), (1.85, -0.62, 11.5), (-1.85, -0.62, 11.5),
                  UV_PUFF_ALPHA, col=rgba(255, 246, 205, 95), double_sided=True),
        make_quad((0.0, -0.22, 0.0), (0.0, 0.22, 0.0), (0.0, 0.45, 10.5), (0.0, -0.72, 10.5),
                  UV_PUFF_ALPHA, col=rgba(255, 246, 205, 75), double_sided=True),
    ])


def build_cut_palm_frond(lod: int) -> MeshPart:
    """Freshly Severed Green Oil Palm Frond ('Pelepah Sawit Jatuh') that drops cleanly when harvested with Egrek!"""
    parts = [
        make_tube_segment((0.0, 0.0, -0.35), (0.0, 0.08, 1.95), 0.048, 0.012, UV_PALM_BARK, seg=6, col=rgba(118, 152, 58, 70))
    ]
    n_leaf = 6 if lod == 0 else 4
    for i in range(n_leaf):
        z0 = 0.05 + i * 0.30
        parts.append(make_quad(
            (-0.48, -0.04, z0), (0.48, -0.04, z0),
            (0.42, 0.06, z0 + 0.34), (-0.42, 0.06, z0 + 0.34),
            UV_PALM_FROND, col=rgba(255, 255, 255, 88), double_sided=True
        ))
    return merge_parts(parts)


# ── Expanded Kebun Raya Sumatera v6.0 Landmarks & Interactive Field Pickups ──

def build_spbu_solar(lod: int) -> MeshPart:
    """Indonesian Pertashop / SPBU Biosolar B35 & Bengkel Modif Canter Forecourt Station!"""
    red_brand = rgba(216, 38, 38, 155)
    white_clean = rgba(244, 246, 250, 120)
    steel_c = rgba(52, 58, 68, 145)
    yel_c = rgba(242, 192, 28, 165)
    parts = [
        # Concrete forecourt slab + chamfered yellow-curbed raised pump island
        make_bevel_box(9.6, 0.16, 8.2, UV_CONCRETE, rgba(226, 230, 236, 95), center=(0.0, 0.08, 0.0), bev=0.03),
        make_bevel_box(4.1, 0.22, 1.65, UV_CONCRETE_CLEAN, yel_c, center=(0.0, 0.22, 0.0), bev=0.04),
        make_bevel_box(3.86, 0.06, 1.42, UV_CONCRETE, rgba(210, 216, 224, 95), center=(0.0, 0.34, 0.0), bev=0.02),
        # Multi-layered Pertashop red/white/silver beveled canopy fascia + recessed warm LED soffit light strips!
        make_bevel_box(8.0, 0.52, 6.4, UV_CONCRETE_CLEAN, red_brand, center=(0.0, 4.22, 0.0), bev=0.05),
        make_bevel_box(8.14, 0.14, 6.54, UV_CONCRETE_CLEAN, white_clean, center=(0.0, 3.92, 0.0), bev=0.025),
        make_bevel_box(8.10, 0.11, 6.50, UV_STEEL, rgba(218, 226, 236, 175), center=(0.0, 4.52, 0.0), bev=0.02),
        make_box(7.4, 0.08, 5.8, UV_CONCRETE_CLEAN, rgba(236, 240, 246, 105), center=(0.0, 3.82, 0.0)),
        make_box(2.4, 0.05, 0.22, UV_CANTER_HEADLAMP, rgba(255, 250, 232, 253), center=(-1.8, 3.77, 1.2)),
        make_box(2.4, 0.05, 0.22, UV_CANTER_HEADLAMP, rgba(255, 250, 232, 253), center=( 1.8, 3.77, 1.2)),
        make_box(2.4, 0.05, 0.22, UV_CANTER_HEADLAMP, rgba(255, 250, 232, 253), center=( 0.0, 3.77, -1.2)),
        # Twin Digital Biosolar B35 & Dexlite Dispensers + Glowing Cyan LCD Meter + Nozzle Holsters!
        make_bevel_box(0.82, 1.72, 0.54, UV_CONCRETE_CLEAN, white_clean, center=(-0.98, 1.16, 0.0), bev=0.035),
        make_bevel_box(0.82, 1.72, 0.54, UV_CONCRETE_CLEAN, white_clean, center=( 0.98, 1.16, 0.0), bev=0.035),
        make_bevel_box(0.86, 0.40, 0.58, UV_CONCRETE_CLEAN, red_brand, center=(-0.98, 1.78, 0.0), bev=0.025),
        make_bevel_box(0.86, 0.40, 0.58, UV_CONCRETE_CLEAN, rgba(32, 158, 92, 165), center=( 0.98, 1.78, 0.0), bev=0.025),
        make_box(0.52, 0.28, 0.57, UV_CONCRETE_CLEAN, rgba(56, 236, 190, 252), center=(-0.98, 1.34, 0.0)),
        make_box(0.52, 0.28, 0.57, UV_CONCRETE_CLEAN, rgba(56, 236, 190, 252), center=( 0.98, 1.34, 0.0)),
        # Rear Elevated 5,000L Cylindrical White Biosolar Storage Tank on Steel Saddle Cradles!
        make_tube_segment((-1.65, 1.18, -2.85), (1.65, 1.18, -2.85), 0.72, 0.72, UV_CONCRETE_CLEAN, seg=(16, 12, 8)[lod], col=white_clean, ball_caps=True),
        make_tube_segment((-1.10, 1.18, -2.85), (-0.96, 1.18, -2.85), 0.74, 0.74, UV_CONCRETE_CLEAN, seg=12, col=red_brand, ball_caps=False),
        make_tube_segment(( 0.96, 1.18, -2.85), ( 1.10, 1.18, -2.85), 0.74, 0.74, UV_CONCRETE_CLEAN, seg=12, col=rgba(32, 158, 92, 165), ball_caps=False),
        make_box(0.22, 0.95, 1.15, UV_STEEL, steel_c, center=(-1.05, 0.52, -2.85)),
        make_box(0.22, 0.95, 1.15, UV_STEEL, steel_c, center=( 1.05, 0.52, -2.85)),
        # Side Truck Tire & Suspension Service Bay Ramps + Stacked Lubricant Drums!
        xform(make_bevel_box(0.68, 0.34, 2.8, UV_STEEL, yel_c, bev=0.02), rx=0.11, translate=(-3.35, 0.20, 0.4)),
        xform(make_bevel_box(0.68, 0.34, 2.8, UV_STEEL, yel_c, bev=0.02), rx=0.11, translate=(-1.95, 0.20, 0.4)),
        make_tube_segment((3.55, 0.16, -2.35), (3.55, 1.04, -2.35), 0.29, 0.29, UV_STEEL, seg=10, col=rgba(36, 124, 208, 165)),
        make_tube_segment((4.22, 0.16, -2.35), (4.22, 1.04, -2.35), 0.29, 0.29, UV_STEEL, seg=10, col=red_brand),
    ]
    for cx in (-3.1, 3.1):
        for cz in (-2.4, 2.4):
            parts.append(make_bevel_box(0.28, 3.80, 0.28, UV_CONCRETE_CLEAN, white_clean, center=(cx, 1.94, cz), bev=0.025))
            parts.append(make_bevel_box(0.42, 0.52, 0.42, UV_CANTER_PAINT, yel_c, center=(cx, 0.34, cz), bev=0.02))
    if lod <= 1:
        # Yellow U-shaped crash bollards at both ends of pump island + looped rubber fuel hoses & chrome nozzles!
        for bx_b in (-1.82, 1.82):
            parts.append(make_tube_segment((bx_b, 0.28, -0.45), (bx_b, 0.96, -0.45), 0.045, 0.045, UV_CANTER_PAINT, seg=6, col=yel_c))
            parts.append(make_tube_segment((bx_b, 0.28,  0.45), (bx_b, 0.96,  0.45), 0.045, 0.045, UV_CANTER_PAINT, seg=6, col=yel_c))
            parts.append(make_tube_segment((bx_b, 0.96, -0.45), (bx_b, 0.96,  0.45), 0.045, 0.045, UV_CANTER_PAINT, seg=6, col=yel_c))
        for hx in (-0.54, 1.42):
            parts.append(make_bevel_box(0.10, 0.22, 0.14, UV_STEEL, steel_c, center=(hx - 0.03, 1.24, 0.0), bev=0.01))
            parts.append(make_tube_segment((hx, 1.48, 0.10), (hx + 0.18, 0.68, 0.20), 0.022, 0.020, UV_STEEL, seg=6, col=rgba(28, 32, 38, 120)))
            parts.append(make_tube_segment((hx + 0.18, 0.68, 0.20), (hx + 0.02, 1.22, 0.06), 0.020, 0.018, UV_STEEL, seg=6, col=rgba(28, 32, 38, 120)))
            parts.append(make_tube_segment((0.0, 1.88, -2.85), (0.0, 2.55, -2.85), 0.032, 0.032, UV_STEEL, seg=6, col=steel_c))
    return merge_parts(parts)


def build_warung_kopi(lod: int) -> MeshPart:
    """Traditional Sumatran Plantation 'Warung Kopi & Istirahat Pemanen' with Glass Etalase, Kettle, Mugs & Benches!"""
    wood_d = rgba(132, 88, 48, 78)
    wood_m = rgba(214, 184, 146, 82)
    wood_l = rgba(244, 224, 192, 95)
    parts = [
        # Raised timber deck + front entry step plank
        make_bevel_box(5.4, 0.18, 4.6, UV_WOOD_PLAIN, rgba(198, 170, 138, 78), center=(0.0, 0.09, 0.0), bev=0.025),
        make_bevel_box(3.8, 0.10, 0.42, UV_WOOD_PLAIN, wood_m, center=(0.0, 0.05, 2.42), bev=0.015),
        # Beveled wooden service counter + overhanging polished counter top + back wall & shelf rack!
        make_bevel_box(4.6, 1.04, 1.75, UV_WOOD_BAK, wood_m, center=(0.0, 0.69, -0.95), bev=0.03),
        make_bevel_box(4.82, 0.09, 0.96, UV_WOOD_PLAIN, wood_l, center=(0.0, 1.25, -0.40), bev=0.02),
        make_bevel_box(4.6, 2.30, 0.16, UV_WOOD_BAK, rgba(208, 180, 146, 78), center=(0.0, 1.32, -1.82), bev=0.02),
        make_bevel_box(3.8, 0.07, 0.34, UV_WOOD_PLAIN, wood_l, center=(0.0, 1.88, -1.62), bev=0.012),
        # Dual-pitched corrugated tin roof with exposed timber ridge beam!
        xform(make_bevel_box(5.9, 0.11, 3.25, UV_CORRUGATED, rgba(42, 148, 96, 132), bev=0.015), rx=0.22, translate=(0.0, 2.88, -0.96)),
        xform(make_bevel_box(5.9, 0.11, 2.88, UV_CORRUGATED, rgba(218, 92, 48, 132), bev=0.015), rx=-0.26, translate=(0.0, 2.75, 0.96)),
        make_box(5.7, 0.14, 0.16, UV_WOOD_PLAIN, wood_d, center=(0.0, 3.12, -0.02)),
        # Harvester wooden bench + side bench + twin warm hanging Edison lanterns!
        make_bevel_box(3.6, 0.08, 0.44, UV_WOOD_PLAIN, wood_l, center=(0.0, 0.52, 1.02), bev=0.016),
        make_box(0.16, 0.46, 0.38, UV_WOOD_PLAIN, wood_d, center=(-1.42, 0.28, 1.02)),
        make_box(0.16, 0.46, 0.38, UV_WOOD_PLAIN, wood_d, center=( 1.42, 0.28, 1.02)),
        make_box(2.84, 0.08, 0.08, UV_WOOD_PLAIN, wood_d, center=(0.0, 0.28, 1.02)),
        make_sphere_uv(0.15, 0.19, 0.15, UV_CANTER_HEADLAMP, seg=10, rings=6, col=rgba(255, 228, 132, 253), center=(-1.05, 2.30, 0.46)),
        make_sphere_uv(0.15, 0.19, 0.15, UV_CANTER_HEADLAMP, seg=10, rings=6, col=rgba(255, 228, 132, 253), center=( 1.05, 2.30, 0.46)),
        # Countertop Props: Glass Gorengan Display Case ('Etalase Kaca'), Brass Kettle, Red Thermos & Ceramic Mugs!
        make_bevel_box(1.18, 0.56, 0.48, UV_CANTER_GLASS, rgba(165, 232, 245, 210), center=(1.15, 1.56, -0.36), bev=0.02),
        make_box(1.22, 0.05, 0.52, UV_STEEL, rgba(220, 228, 236, 185), center=(1.15, 1.85, -0.36)),
        make_tube_segment((-1.15, 1.29, -0.38), (-1.15, 1.66, -0.38), 0.17, 0.12, UV_STEEL, seg=10, col=rgba(236, 192, 66, 212)),
        make_tube_segment((-0.55, 1.29, -0.44), (-0.55, 1.74, -0.44), 0.11, 0.10, UV_CANTER_PAINT, seg=8, col=rgba(220, 48, 42, 165)),
    ]
    if lod <= 1:
        for mx_mug in (-0.12, 0.24):
            parts.append(make_tube_segment((mx_mug, 1.29, -0.32), (mx_mug, 1.45, -0.32), 0.058, 0.064, UV_CONCRETE_CLEAN, seg=8, col=rgba(248, 244, 232, 165)))
        for sx_j in (-1.35, -0.65, 0.15, 0.95):
            parts.append(make_bevel_box(0.32, 0.28, 0.22, UV_CANTER_PAINT, rgba(235, 178, 44, 145), center=(sx_j, 2.05, -1.60), bev=0.015))
    for px in (-2.38, 2.38):
        for pz in (-1.78, 1.78):
            parts.append(make_bevel_box(0.18, 2.68, 0.18, UV_WOOD_PLAIN, wood_d, center=(px, 1.40, pz), bev=0.018))
    return merge_parts(parts)


def build_gudang_pupuk(lod: int) -> MeshPart:
    """Plantation 'Gudang Pupuk NPK Mutiara' Warehouse with Sliding Doors, Roof Ventilator & Palletized NPK Sacks!"""
    parts = [
        # Heavy concrete loading dock + yellow hazard edge strip & rubber truck dock bumpers!
        make_bevel_box(8.4, 0.44, 7.2, UV_CONCRETE, rgba(216, 222, 228, 92), center=(0.0, 0.22, 0.0), bev=0.03),
        make_box(8.42, 0.09, 0.18, UV_CANTER_PAINT, rgba(242, 194, 28, 150), center=(0.0, 0.41, 3.53)),
        # Corrugated warehouse structure + green steel trim columns + gabled roof + ridge ventilator!
        make_bevel_box(7.6, 3.88, 5.4, UV_CORRUGATED, rgba(226, 236, 228, 115), center=(0.0, 2.36, -0.65), bev=0.04),
        xform(make_bevel_box(4.45, 0.16, 6.08, UV_CORRUGATED, rgba(34, 136, 84, 138), bev=0.02), rz=0.24, translate=(-1.98, 4.70, -0.65)),
        xform(make_bevel_box(4.45, 0.16, 6.08, UV_CORRUGATED, rgba(34, 136, 84, 138), bev=0.02), rz=-0.24, translate=( 1.98, 4.70, -0.65)),
        make_bevel_box(0.95, 0.48, 3.6, UV_CORRUGATED, rgba(206, 216, 224, 135), center=(0.0, 5.26, -0.65), bev=0.025),
        # Twin industrial sliding steel doors + overhead sliding rail + warm loading bay floodlight!
        make_box(4.2, 0.12, 0.14, UV_STEEL, rgba(46, 52, 62, 150), center=(0.0, 3.22, 2.12)),
        make_bevel_box(1.62, 2.68, 0.14, UV_CORRUGATED, rgba(52, 68, 84, 135), center=(-0.84, 1.78, 2.10), bev=0.02),
        make_bevel_box(1.62, 2.68, 0.14, UV_CORRUGATED, rgba(52, 68, 84, 135), center=( 0.84, 1.78, 2.10), bev=0.02),
        make_bevel_box(0.68, 0.16, 0.22, UV_CANTER_HEADLAMP, rgba(255, 244, 206, 252), center=(0.0, 3.56, 2.18), bev=0.015),
    ]
    for cx in (-3.76, 3.76):
        for cz in (-3.32, 2.02):
            parts.append(make_box(0.22, 3.90, 0.22, UV_STEEL, rgba(32, 118, 72, 125), center=(cx, 2.38, cz)))
    # Wooden pallets + neatly stacked blue/gold 50kg NPK Mutiara fertilizer sacks on front loading dock!
    for px_pal in (-2.25, 2.25):
        parts.append(make_bevel_box(1.55, 0.12, 1.05, UV_WOOD_PLAIN, rgba(188, 146, 96, 80), center=(px_pal, 0.50, 2.68), bev=0.015))
    for si, (sx, sy, sz) in enumerate([(-2.62, 0.68, 2.68), (-1.88, 0.68, 2.68), (-2.25, 0.92, 2.68), (-2.25, 1.14, 2.68),
                                       ( 2.62, 0.68, 2.68), ( 1.88, 0.68, 2.68), ( 2.25, 0.92, 2.68), ( 2.25, 1.14, 2.68)]):
        sack_col = rgba(48, 158, 242, 108) if si % 2 == 0 else rgba(248, 206, 56, 122)
        parts.append(make_sphere_uv(0.38, 0.15, 0.27, UV_WOVEN, seg=8, rings=5, col=sack_col, center=(sx, sy, sz)))
    return merge_parts(parts)


def build_offroad_arch(lod: int) -> MeshPart:
    """Heavy Timber Offroad Mud Hill Trailhead Arch ('Gapura Jalur Tanjakan Lumpur Sawit')!"""
    wood_log = rgba(146, 96, 52, 82)
    steel_b = rgba(40, 46, 56, 155)
    gold_b = rgba(246, 192, 28, 175)
    parts = [
        # Twin heavy braced timber A-frame towers centered cleanly on x = ±3.10m!
        make_tube_segment((-3.12, 0.0,  0.22), (-2.88, 4.35, 0.0), 0.21, 0.17, UV_WOOD_PLAIN, seg=9, col=wood_log),
        make_tube_segment((-3.12, 0.0, -0.22), (-2.88, 4.35, 0.0), 0.21, 0.17, UV_WOOD_PLAIN, seg=9, col=wood_log),
        make_tube_segment(( 3.12, 0.0,  0.22), ( 2.88, 4.35, 0.0), 0.21, 0.17, UV_WOOD_PLAIN, seg=9, col=wood_log),
        make_tube_segment(( 3.12, 0.0, -0.22), ( 2.88, 4.35, 0.0), 0.21, 0.17, UV_WOOD_PLAIN, seg=9, col=wood_log),
        make_bevel_box(0.68, 0.34, 0.78, UV_CONCRETE, rgba(196, 202, 210, 95), center=(-3.12, 0.17, 0.0), bev=0.03),
        make_bevel_box(0.68, 0.34, 0.78, UV_CONCRETE, rgba(196, 202, 210, 95), center=( 3.12, 0.17, 0.0), bev=0.03),
        # Overhead cross-braced gantry + chamfered black-and-gold signboard + knee braces + twin floodlights!
        make_tube_segment((-3.05, 4.28, 0.0), (3.05, 4.28, 0.0), 0.14, 0.14, UV_WOOD_PLAIN, seg=8, col=wood_log),
        make_tube_segment((-2.92, 2.75, 0.0), (-2.05, 3.65, 0.0), 0.11, 0.10, UV_WOOD_PLAIN, seg=6, col=wood_log),
        make_tube_segment(( 2.92, 2.75, 0.0), ( 2.05, 3.65, 0.0), 0.11, 0.10, UV_WOOD_PLAIN, seg=6, col=wood_log),
        make_bevel_box(6.5, 0.78, 0.28, UV_CANTER_PAINT, gold_b, center=(0.0, 3.88, 0.0), bev=0.035),
        make_bevel_box(5.85, 0.48, 0.33, UV_STEEL, steel_b, center=(0.0, 3.88, 0.0), bev=0.025),
        make_bevel_box(0.36, 0.16, 0.26, UV_CANTER_HEADLAMP, rgba(255, 242, 192, 252), center=(-1.85, 4.38, 0.14), bev=0.015),
        make_bevel_box(0.36, 0.16, 0.26, UV_CANTER_HEADLAMP, rgba(255, 242, 192, 252), center=( 1.85, 4.38, 0.14), bev=0.015),
    ]
    for sx in (-3.28, 3.28):
        parts.append(xform(build_truck_wheel(2), rz=math.pi * 0.5, translate=(sx, 0.18, 0.72)))
    return merge_parts(parts)


def build_item_solar_can(lod: int) -> MeshPart:
    """Interactive 25L Yellow Biosolar Turbo Jerrycan Pickup!"""
    return merge_parts([
        make_bevel_box(0.32, 0.46, 0.20, UV_CANTER_PAINT, rgba(250, 198, 28, 185), center=(0.0, 0.24, 0.0), bev=0.04),
        make_tube_segment((-0.07, 0.49, 0.0), (0.07, 0.49, 0.0), 0.022, 0.022, UV_CANTER_PAINT, seg=6, col=rgba(250, 198, 28, 185)),
        make_tube_segment((0.09, 0.45, 0.0), (0.14, 0.54, 0.0), 0.030, 0.026, UV_STEEL, seg=8, col=rgba(220, 42, 34, 195)),
    ])


def build_item_coffee_cup(lod: int) -> MeshPart:
    """Interactive Steaming Plantation 'Kopi Tubruk Stamina' Mug Pickup!"""
    seg = (12, 8, 6)[lod]
    return merge_parts([
        make_loft([ring_ellipse(0.13, 0.13, 0.02, seg), ring_ellipse(0.16, 0.16, 0.36, seg)], UV_CONCRETE_CLEAN, col=rgba(248, 244, 232, 165)),
        make_sphere_uv(0.145, 0.025, 0.145, UV_WOOD_PLAIN, seg=seg, rings=4, col=rgba(58, 34, 18, 215), center=(0.0, 0.34, 0.0)),
        make_tube_segment((0.15, 0.12, 0.0), (0.22, 0.20, 0.0), 0.022, 0.022, UV_CONCRETE_CLEAN, seg=6, col=rgba(248, 244, 232, 165)),
        make_tube_segment((0.22, 0.20, 0.0), (0.15, 0.29, 0.0), 0.022, 0.022, UV_CONCRETE_CLEAN, seg=6, col=rgba(248, 244, 232, 165)),
    ])


def build_item_npk_sack(lod: int) -> MeshPart:
    """Interactive 50kg 'Pupuk NPK Emas' Fertilizer Sack Pickup!"""
    return merge_parts([
        make_sphere_uv(0.28, 0.30, 0.19, UV_WOVEN, seg=(12, 8, 6)[lod], rings=6, col=rgba(56, 178, 248, 125), center=(0.0, 0.28, 0.0)),
        make_tube_segment((0.0, 0.52, 0.0), (0.0, 0.62, 0.0), 0.075, 0.11, UV_WOVEN, seg=8, col=rgba(250, 206, 48, 185)),
    ])


def build_item_cuan_crate(lod: int) -> MeshPart:
    """Interactive Glowing Golden 'Peti Sultan / Tiket Cuan' Field Chest!"""
    gold = rgba(255, 208, 44, 238)
    emerald = rgba(38, 232, 138, 248)
    return merge_parts([
        make_bevel_box(0.54, 0.34, 0.38, UV_WOOD_PLAIN, rgba(96, 52, 24, 135), center=(0.0, 0.18, 0.0), bev=0.03),
        make_bevel_box(0.56, 0.14, 0.40, UV_STEEL, gold, center=(0.0, 0.40, 0.0), bev=0.03),
        make_box(0.10, 0.42, 0.41, UV_STEEL, gold, center=(-0.16, 0.24, 0.0)),
        make_box(0.10, 0.42, 0.41, UV_STEEL, gold, center=( 0.16, 0.24, 0.0)),
        make_sphere_uv(0.055, 0.065, 0.035, UV_CONCRETE_CLEAN, seg=8, rings=5, col=emerald, center=(0.0, 0.30, 0.20)),
    ])


def build_celeng_boar(lod: int) -> MeshPart:
    seg = (16, 11, 7)[lod]
    fur = rgba(96, 68, 50, 62)
    mane = rgba(38, 28, 22, 72)
    rings = [
        ring_ellipse(0.11, 0.11, 0.44, seg, cz=0.70),   # Snout disc
        ring_ellipse(0.15, 0.14, 0.47, seg, cz=0.58),   # Upper snout bridge
        ring_ellipse(0.21, 0.21, 0.51, seg, cz=0.44),   # Skull / jaw
        ring_ellipse(0.31, 0.33, 0.58, seg, cz=0.16),   # Muscular shoulder hump
        ring_ellipse(0.29, 0.31, 0.54, seg, cz=-0.22),  # Flank
        ring_ellipse(0.17, 0.19, 0.48, seg, cz=-0.56),  # Rump
    ]
    parts = [
        make_loft(rings, UV_PALM_BARK, col=fur),
        # Pinkish-brown snout disc + nostrils
        make_sphere_uv(0.095, 0.085, 0.045, UV_WOOD_PLAIN, seg=8, rings=5, col=rgba(148, 92, 78, 85), center=(0.0, 0.44, 0.72)),
    ]
    # Curved ivory tusks + glowing amber boar eyes + alert ears + dark dorsal bristle mane + tail!
    for sx in (-1.0, 1.0):
        parts.append(make_tube_segment((sx * 0.10, 0.43, 0.58), (sx * 0.16, 0.49, 0.65), 0.024, 0.015, UV_STEEL, seg=6, col=rgba(248, 244, 228, 175), ball_caps=False))
        parts.append(make_tube_segment((sx * 0.16, 0.49, 0.65), (sx * 0.19, 0.59, 0.68), 0.015, 0.004, UV_STEEL, seg=6, col=rgba(252, 248, 236, 185), ball_caps=False))
        parts.append(make_sphere_uv(0.042, 0.088, 0.052, UV_PALM_BARK, seg=7, rings=4, col=fur, center=(sx * 0.17, 0.68, 0.40)))
        if lod <= 1:
            parts.append(make_sphere_uv(0.022, 0.020, 0.022, UV_CANTER_FOGLAMP, seg=6, rings=4, col=rgba(255, 168, 36, 250), center=(sx * 0.155, 0.56, 0.51)))
    if lod <= 1:
        for bi in range(5):
            bz = 0.34 - bi * 0.16
            by = 0.76 - abs(bi - 1.5) * 0.025
            parts.append(xform(make_box(0.055, 0.11, 0.13, UV_PALM_BARK, mane), rx=-0.28, translate=(0.0, by, bz)))
        parts.append(make_tube_segment((0.0, 0.52, -0.55), (0.0, 0.38, -0.74), 0.024, 0.012, UV_PALM_BARK, seg=5, col=mane))
    return merge_parts(parts)


def build_boar_leg(lod: int) -> MeshPart:
    return make_tube_segment((0.0, 0.0, 0.0), (0.0, -0.48, 0.02), 0.068, 0.036, UV_PALM_BARK, seg=(8, 6, 5)[lod], col=rgba(74, 52, 38, 55))


def build_pks_factory(lod: int) -> MeshPart:
    """Realistic Indonesian Palm Oil Mill (Pabrik Kelapa Sawit / PKS): Multi-Bay Halls, Conveyor Bridge, CPO Silos & Banded Chimneys!"""
    silo_seg = (20, 12, 8)[lod]
    green_roof = rgba(38, 132, 84, 138)
    silo_steel = rgba(232, 238, 246, 175)
    dark_steel = rgba(44, 52, 62, 145)
    parts = [
        # Main processing hall + concrete foundation plinth + side sterilizer annex bay
        make_bevel_box(13.6, 0.45, 11.0, UV_CONCRETE, rgba(196, 202, 210, 95), center=(0.0, 0.22, 0.0), bev=0.04),
        make_bevel_box(13.2, 6.8, 10.6, UV_CORRUGATED, rgba(220, 226, 232, 118), center=(0.0, 3.4, 0.0), bev=0.05),
        make_bevel_box(4.8, 4.4, 7.6, UV_CORRUGATED, rgba(206, 214, 222, 118), center=(-8.6, 2.2, -0.6), bev=0.04),
        xform(make_bevel_box(5.4, 0.16, 8.0, UV_CORRUGATED, green_roof, bev=0.02), rz=0.18, translate=(-8.6, 4.72, -0.6)),
        # Green factory gabled roof + rooftop monitor skylight vent
        xform(make_bevel_box(7.25, 0.18, 11.2, UV_CORRUGATED, green_roof, bev=0.02), rz=0.22, translate=(-3.3, 7.45, 0.0)),
        xform(make_bevel_box(7.25, 0.18, 11.2, UV_CORRUGATED, green_roof, bev=0.02), rz=-0.22, translate=( 3.3, 7.45, 0.0)),
        make_bevel_box(2.2, 0.72, 7.8, UV_CORRUGATED, rgba(212, 220, 228, 130), center=(0.0, 8.35, 0.0), bev=0.03),
        # FFB Receiving Hopper Canopy, Steel Pillars, Industrial Floodlights & Roll-Up Bay Door!
        make_bevel_box(5.8, 0.26, 3.6, UV_CANTER_PAINT, rgba(242, 192, 28, 155), center=(0.0, 4.45, 6.45), bev=0.03),
        make_box(0.24, 4.4, 0.24, UV_STEEL, dark_steel, center=(-2.6, 2.2, 7.9)),
        make_box(0.24, 4.4, 0.24, UV_STEEL, dark_steel, center=( 2.6, 2.2, 7.9)),
        make_box(4.2, 3.8, 0.3, UV_STEEL, rgba(26, 30, 36, 85), center=(0.0, 1.9, 5.25)),
        make_box(1.8, 0.14, 0.22, UV_CANTER_HEADLAMP, rgba(255, 242, 198, 253), center=(0.0, 4.26, 8.15)),
        # Overhead Inclined Pipe & Conveyor Gallery Bridge connecting Mill to Twin CPO Storage Silos!
        xform(make_bevel_box(4.6, 0.65, 0.85, UV_STEEL, dark_steel, bev=0.02), rz=0.14, translate=(6.2, 5.4, 1.2)),
        make_tube_segment((8.2, 0.0, 1.2), (8.2, 6.3, 1.2), 2.1, 2.1, UV_CORRUGATED, seg=silo_seg, col=silo_steel, ball_caps=True),
        make_tube_segment((8.4, 0.0, -3.4), (8.4, 5.7, -3.4), 1.85, 1.85, UV_CORRUGATED, seg=silo_seg, col=silo_steel, ball_caps=True),
        # Twin Tall Red-and-White Banded Industrial Boiler Smokestacks!
        make_tube_segment((-3.2, 6.5, -2.2), (-3.2, 11.4, -2.2), 0.58, 0.47, UV_CORRUGATED, seg=12, col=rgba(228, 232, 238, 125), ball_caps=False),
        make_tube_segment((-3.2, 11.4, -2.2), (-3.2, 13.0, -2.2), 0.48, 0.44, UV_CORRUGATED, seg=12, col=rgba(212, 54, 42, 140), ball_caps=False),
        make_tube_segment((-3.2, 13.0, -2.2), (-3.2, 14.6, -2.2), 0.44, 0.40, UV_CORRUGATED, seg=12, col=rgba(236, 240, 246, 135), ball_caps=False),
        make_tube_segment((-1.2, 6.5, -2.2), (-1.2, 10.8, -2.2), 0.52, 0.42, UV_CORRUGATED, seg=12, col=rgba(228, 232, 238, 125), ball_caps=False),
        make_tube_segment((-1.2, 10.8, -2.2), (-1.2, 12.2, -2.2), 0.43, 0.39, UV_CORRUGATED, seg=12, col=rgba(212, 54, 42, 140), ball_caps=False),
        make_tube_segment((-1.2, 12.2, -2.2), (-1.2, 13.7, -2.2), 0.39, 0.36, UV_CORRUGATED, seg=12, col=rgba(236, 240, 246, 135), ball_caps=False),
    ]
    if lod <= 1:
        # Structural stiffening rings around CPO Silos + vertical steel inspection ladder
        for ry_s in (2.0, 4.0, 5.8):
            parts.append(make_tube_segment((8.2, ry_s - 0.04, 1.2), (8.2, ry_s + 0.04, 1.2), 2.16, 2.16, UV_STEEL, seg=14, col=dark_steel, ball_caps=False))
        parts.append(make_box(0.08, 5.8, 0.36, UV_STEEL, rgba(242, 192, 28, 165), center=(6.06, 3.0, 1.2)))
    return merge_parts(parts)


def build_pks_fan(lod: int) -> MeshPart:
    parts = [make_tube_segment((0.0, -0.1, 0.0), (0.0, 0.2, 0.0), 0.22, 0.22, UV_STEEL, seg=8, col=rgba(70, 76, 84, 150))]
    for i in range(4):
        b = make_box(0.24, 0.02, 0.92, UV_STEEL, rgba(195, 204, 214, 175), center=(0.0, 0.08, 0.52))
        parts.append(xform(b, rz=0.22, ry=i * math.pi * 0.5))
    return merge_parts(parts)


def build_steam_puff(lod: int) -> MeshPart:
    return make_sphere_uv(0.62, 0.48, 0.62, UV_CONCRETE_CLEAN, seg=(12, 8, 6)[lod], rings=(8, 6, 4)[lod], col=rgba(246, 248, 252, 42))


def build_weighbridge_ram(lod: int) -> MeshPart:
    """Authentic RAM Sawit Truck Weighbridge Deck + Wheel Guide Rails + Operator Booth + Digital Tonnage Arch!"""
    yel_rail = rgba(244, 196, 32, 165)
    steel_d = rgba(42, 48, 58, 145)
    parts = [
        # Heavy concrete & diamond-steel deck + approach ramps with yellow hazard stripes!
        make_bevel_box(4.2, 0.34, 7.6, UV_CONCRETE, rgba(218, 224, 230, 98), center=(0.0, 0.17, 0.0), bev=0.03),
        make_box(3.75, 0.04, 7.4, UV_STEEL, rgba(72, 80, 92, 145), center=(0.0, 0.35, 0.0)),
        xform(make_bevel_box(4.2, 0.26, 2.4, UV_CONCRETE, yel_rail, bev=0.02), rx=0.13, translate=(0.0, 0.05, 4.85)),
        xform(make_bevel_box(4.2, 0.26, 2.4, UV_CONCRETE, yel_rail, bev=0.02), rx=-0.13, translate=(0.0, 0.05, -4.85)),
        # Side yellow tubular wheel guide rails along outer deck edges (x = ±1.98m, full 3.96m truck clearance!)
        make_tube_segment((-1.98, 0.52, -3.55), (-1.98, 0.52, 3.55), 0.055, 0.055, UV_CANTER_PAINT, seg=8, col=yel_rail),
        make_tube_segment(( 1.98, 0.52, -3.55), ( 1.98, 0.52, 3.55), 0.055, 0.055, UV_CANTER_PAINT, seg=8, col=yel_rail),
        # Operator cabin beside scale + window frame + split AC unit + overhanging roof!
        make_bevel_box(2.15, 2.48, 2.35, UV_CONCRETE_CLEAN, rgba(238, 242, 248, 92), center=(3.38, 1.24, 0.0), bev=0.03),
        make_bevel_box(2.50, 0.16, 2.70, UV_CORRUGATED, rgba(38, 136, 86, 135), center=(3.38, 2.54, 0.0), bev=0.02),
        make_box(0.08, 0.90, 1.42, UV_CANTER_GLASS, rgba(96, 214, 232, 225), center=(2.28, 1.56, 0.0)),
        make_bevel_box(0.32, 0.44, 0.62, UV_CONCRETE_CLEAN, rgba(220, 226, 232, 130), center=(4.56, 2.02, 0.0), bev=0.02),
        # Overhead steel gantry + glowing emerald LED weight indicator board
        make_bevel_box(0.16, 3.7, 0.16, UV_STEEL, steel_d, center=(-2.15, 1.85, -1.8), bev=0.015),
        make_bevel_box(0.16, 3.7, 0.16, UV_STEEL, steel_d, center=( 2.15, 1.85, -1.8), bev=0.015),
        make_bevel_box(4.6, 0.68, 0.26, UV_STEEL, rgba(20, 24, 30, 160), center=(0.0, 3.58, -1.8), bev=0.025),
        make_quad((-1.75, 3.38, -1.66), (1.75, 3.38, -1.66), (1.75, 3.78, -1.66), (-1.75, 3.78, -1.66),
                  UV_CONCRETE_CLEAN, col=rgba(52, 248, 152, 253)),
        make_quad((1.75, 3.38, -1.94), (-1.75, 3.38, -1.94), (-1.75, 3.78, -1.94), (1.75, 3.78, -1.94),
                  UV_CONCRETE_CLEAN, col=rgba(52, 248, 152, 253)),
    ]
    if lod <= 1:
        for sx_r in (-1.98, 1.98):
            for rz_p in (-3.3, -1.1, 1.1, 3.3):
                parts.append(make_box(0.08, 0.24, 0.08, UV_CANTER_PAINT, yel_rail, center=(sx_r, 0.40, rz_p)))
    return merge_parts(parts)


def build_mandor_post(lod: int) -> MeshPart:
    parts = [
        make_box(3.8, 0.22, 3.8, UV_WOOD_PLAIN, rgba(215, 195, 175, 75), center=(0.0, 0.68, 0.0)),
        make_box(3.4, 2.25, 3.4, UV_WOOD_BAK, rgba(235, 225, 210, 75), center=(0.0, 1.90, 0.0)),
        xform(make_box(2.6, 0.14, 4.4, UV_CORRUGATED, rgba(188, 72, 46, 115)), rz=0.34, translate=(-1.12, 3.35, 0.0)),
        xform(make_box(2.6, 0.14, 4.4, UV_CORRUGATED, rgba(188, 72, 46, 115)), rz=-0.34, translate=( 1.12, 3.35, 0.0)),
    ]
    for sx in (-1.65, 1.65):
        for sz in (-1.65, 1.65):
            parts.append(make_box(0.22, 0.72, 0.22, UV_WOOD_PLAIN, rgba(120, 82, 48, 70), center=(sx, 0.34, sz)))
    return merge_parts(parts)


def build_wooden_bridge(lod: int) -> MeshPart:
    """Heavy Timber Plantation Canal Bridge wide enough for Canter Trucks!"""
    parts = []
    n_planks = (18, 12, 8)[lod]
    for i in range(n_planks):
        t = i / (n_planks - 1.0)
        z = (t - 0.5) * 9.6
        arch_y = 0.22 + math.cos((t - 0.5) * math.pi) * 0.42
        parts.append(make_box(4.6, 0.14, 0.48, UV_WOOD_PLAIN, rgba(225, 205, 185, 75), center=(0.0, arch_y, z)))
    for sx in (-2.22, 2.22):
        for rz in (-4.2, -2.1, 0.0, 2.1, 4.2):
            ay = 0.22 + math.cos((rz / 9.6) * math.pi) * 0.42
            parts.append(make_box(0.14, 1.05, 0.14, UV_WOOD_PLAIN, rgba(145, 96, 52, 70), center=(sx, ay + 0.52, rz)))
        parts.append(make_box(0.10, 0.10, 9.6, UV_WOOD_BAK, rgba(235, 215, 195, 80), center=(sx, 1.38, 0.0)))
    return merge_parts(parts)


def build_vfx_puff_quad(lod: int) -> MeshPart:
    return make_quad((-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.5, 0.5, 0.0), (-0.5, 0.5, 0.0),
                     UV_PUFF_ALPHA, col=rgba(255, 255, 255, 40), double_sided=True)


# ── Smooth Angle-Weighted Normals & Baked Cavity Ambient Occlusion ──

def finalize_normals_and_ao(part: MeshPart) -> Tuple[np.ndarray, MeshPart]:
    pos = part.pos.astype(np.float64)
    idx = part.idx
    v0, v1, v2 = pos[idx[:, 0]], pos[idx[:, 1]], pos[idx[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)

    nrm = np.zeros_like(pos)
    np.add.at(nrm, idx[:, 0], fn)
    np.add.at(nrm, idx[:, 1], fn)
    np.add.at(nrm, idx[:, 2], fn)
    lens = np.linalg.norm(nrm, axis=1, keepdims=True)
    bad = lens[:, 0] < 1e-9
    nrm[~bad] /= lens[~bad]
    nrm[bad] = np.array([0.0, 1.0, 0.0])

    # Stylized Baked Ground-Bounce + Upward Sky Rim + Convex Edge Highlight (Blender Pointiness equivalent!)
    ymin, ymax = float(pos[:, 1].min()), float(pos[:, 1].max())
    h_norm = np.clip((pos[:, 1] - ymin) / max(0.25, ymax - ymin), 0.0, 1.0)
    tri_ctr = (v0 + v1 + v2) / 3.0
    lap = np.zeros_like(pos)
    deg = np.zeros((len(pos), 1), dtype=np.float64)
    for k in (0, 1, 2):
        np.add.at(lap, idx[:, k], tri_ctr - pos[idx[:, k]])
        np.add.at(deg, idx[:, k], 1.0)
    lap /= np.maximum(deg, 1.0)
    convex = np.clip(-np.einsum("ij,ij->i", lap, nrm) * 2.4, -0.06, 0.12)
    sky_vis = np.clip(0.87 + 0.08 * h_norm + 0.05 * nrm[:, 1] + convex, 0.80, 1.08)

    col = part.col.copy().astype(np.float32)
    col[:, :3] = np.clip(col[:, :3] * sky_vis[:, None], 0.0, 255.0)
    return nrm.astype(np.float32), MeshPart(part.pos, part.uv, col.astype(np.uint8), part.idx)


MODEL_SPECS: List[Tuple[str, Callable[[int], MeshPart]]] = [
    ("palm_trunk", build_palm_trunk),
    ("palm_crown", build_palm_crown),
    ("palm_sapling", build_palm_sapling),
    ("tbs_bunch", build_tbs_bunch),
    ("tropical_fern", build_tropical_fern),
    ("rock_boulder", build_rock_boulder),
    ("canter_truck_body", build_canter_truck_body),
    ("canter_steering_wheel", build_canter_steering_wheel),
    ("truck_wheel", build_truck_wheel),
    ("tire_track_segment", build_tire_track_segment),
    ("truck_cargo_heap", build_truck_cargo_heap),
    ("angkong_cart", build_angkong_cart),
    ("pks_factory", build_pks_factory),
    ("pks_fan", build_pks_fan),
    ("steam_puff", build_steam_puff),
    ("weighbridge_ram", build_weighbridge_ram),
    ("mandor_post", build_mandor_post),
    ("wooden_bridge", build_wooden_bridge),
    ("garage_showroom", build_garage_showroom),
    ("vfx_puff_quad", build_vfx_puff_quad),
    ("celeng_boar", build_celeng_boar),
    ("boar_leg", build_boar_leg),
    ("char_torso_head", build_char_torso_head),
    ("char_head", build_char_head),
    ("char_face_neutral", build_char_face_neutral),
    ("char_face_strain", build_char_face_strain),
    ("char_arm", build_char_arm),
    ("char_forearm_hand", build_char_forearm_hand),
    ("char_leg", build_char_leg),
    ("char_calf_boot", build_char_calf_boot),
    ("hat_caping", build_hat_caping),
    ("hat_safety", build_hat_safety),
    ("hat_headband", build_hat_headband),
    ("hat_cowboy", build_hat_cowboy),
    ("hat_crown_gold", build_hat_crown_gold),
    ("acc_glasses", build_acc_glasses),
    ("acc_parang_waist", build_acc_parang_waist),
    ("back_basket", build_back_basket),
    ("back_pack", build_back_pack),
    ("back_cape", build_back_cape),
    ("back_wings_gold", build_back_wings_gold),
    ("tool_egrek", build_tool_egrek),
    ("tool_dodos", build_tool_dodos),
    ("tool_tojok", build_tool_tojok),
    ("tool_egrek_dragon", build_tool_egrek_dragon),
    ("canter_axle_suspension", build_canter_axle_suspension),
    ("canter_driveshaft", build_canter_driveshaft),
    ("canter_headlight_beam", build_canter_headlight_beam),
    ("cut_palm_frond", build_cut_palm_frond),
    ("spbu_solar", build_spbu_solar),
    ("warung_kopi", build_warung_kopi),
    ("gudang_pupuk", build_gudang_pupuk),
    ("offroad_arch", build_offroad_arch),
    ("item_solar_can", build_item_solar_can),
    ("item_coffee_cup", build_item_coffee_cup),
    ("item_npk_sack", build_item_npk_sack),
    ("item_cuan_crate", build_item_cuan_crate),
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
    manifest = {"version": 4, "stride_bytes": 36, "models": []}
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
        print(f"  [OK] {name:<22} LOD0={stats[0]['tris']:>5} | LOD1={stats[1]['tris']:>5} | LOD2={stats[2]['tris']:>5}")

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

    print(f"\n=== NPAK v4.0 PBR BUILT: {len(MODEL_SPECS)} models x 3 LODs = {len(MODEL_SPECS)*3} GPU MESHES ===")
    print(f"    LOD0={tot0:,} tris -> LOD1={tot1:,} tris -> LOD2={tot2:,} tris | Size={len(blob)/1024/1024:.2f} MB")


if __name__ == "__main__":
    main()
