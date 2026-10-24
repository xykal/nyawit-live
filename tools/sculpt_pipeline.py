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
    # Global signed-volume outward check!
    if cap_start and cap_end and len(idx_a) >= 4:
        v0, v1, v2 = pos_a[idx_a[:, 0]], pos_a[idx_a[:, 1]], pos_a[idx_a[:, 2]]
        vol6 = float(np.sum(np.einsum("ij,ij->i", v0, np.cross(v1, v2))))
        if vol6 < 0.0:
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
    seg = (16, 11, 7)[lod]
    n_rings = (14, 9, 5)[lod]
    rings = []
    for i in range(n_rings):
        t = i / (n_rings - 1)
        y = t * 6.45
        lean_x = 0.28 * (t ** 1.35)
        lean_z = 0.20 * math.sin(t * 1.45)
        # Characteristic swollen bole at base tapering cleanly up to crown neck!
        base_swell = 0.26 * math.exp(-t * 5.2)
        swell_neck = 0.06 * math.exp(-((t - 0.96) ** 2) / 0.008)
        r = 0.34 - 0.08 * t + base_swell + swell_neck + 0.018 * math.sin(t * 26.0)
        rings.append(ring_ellipse(r, r, y, seg, cx=lean_x, cz=lean_z))

    parts = [make_loft(rings, UV_PALM_BARK, col=rgba(255, 255, 255, 42), cap_start=True, cap_end=True)]

    # Authentic Indonesian trunk epiphytic ferns ("pakis batang sawit" — see real plantation photo!)
    if lod <= 1:
        n_ferns = 8 if lod == 0 else 4
        for fi in range(n_ferns):
            ft = 0.18 + 0.62 * (fi / max(1, n_ferns - 1))
            fy = ft * 6.45
            fa = fi * 2.39996
            fx = 0.28 * (ft ** 1.35) + math.sin(fa) * 0.31
            fz = 0.20 * math.sin(ft * 1.45) + math.cos(fa) * 0.31
            blade = make_quad((-0.44, 0.0, 0.0), (0.44, 0.0, 0.0), (0.52, 0.78, 0.28), (-0.52, 0.78, 0.28),
                              UV_FERN, col=rgba(245, 255, 235, 55), double_sided=True)
            parts.append(xform(blade, rx=0.42, ry=fa, translate=(fx, fy, fz)))
    return merge_parts(parts)


def make_arching_pinnate_frond(length: float, width: float, arch_up: float, droop: float, segs: int, tint_g: int = 255) -> MeshPart:
    """Curved V-folded 3D pinnate oil palm frond sheet mapped directly onto 88-leaflet Alpha-Cutout UV_PALM_FROND!"""
    pos, uv01, tris = [], [], []
    # 3 vertices across width per station: left edge (-w), raised central midrib (0, +fold), right edge (+w)
    for i in range(segs + 1):
        t = i / segs  # 0 = trunk petiole base, 1 = drooping frond tip
        z = t * length
        y = math.sin(t * math.pi * 0.58) * arch_up - (t ** 2.35) * droop
        w = width * (0.22 + 0.85 * math.sin(min(1.0, t * 1.12) * math.pi * 0.82))
        fold = 0.075 * width * (1.0 - 0.5 * t)
        v_coord = 1.0 - t  # v=1 at base (bottom of tile), v=0 at tip (top of tile)
        pos.extend([(-w, y - fold, z), (0.0, y + fold, z), (w, y - fold, z)])
        uv01.extend([[0.0, v_coord], [0.5, v_coord], [1.0, v_coord]])

    for i in range(segs):
        b0, b1 = i * 3, (i + 1) * 3
        tris.extend([
            [b0 + 0, b0 + 1, b1 + 1], [b0 + 0, b1 + 1, b1 + 0],
            [b0 + 1, b0 + 2, b1 + 2], [b0 + 1, b1 + 2, b1 + 1],
        ])
    c = rgba(tint_g, tint_g, tint_g, 68)
    return MeshPart(np.array(pos, np.float32), map_uv(np.array(uv01, np.float32), UV_PALM_FROND),
                    np.broadcast_to(c, (len(pos), 4)).copy(), np.array(tris, np.int32))


def build_palm_crown(lod: int) -> MeshPart:
    # Lush fountain of 4 phyllotactic whorls just like mature Indonesian Tenera palms!
    whorls = [
        # (count, y_off, length, width, arch_up, droop, pitch_rx, brightness)
        ((9, 6, 4)[lod], -0.18, 3.85, 0.92, 0.85, 2.05, 0.16, 222),  # Lower mature drooping fronds
        ((9, 6, 4)[lod],  0.05, 3.95, 0.95, 1.45, 1.55, -0.08, 244), # Mid fountain fronds
        ((7, 5, 3)[lod],  0.26, 3.55, 0.86, 1.85, 0.95, -0.36, 255), # Upper sunlit fronds
        ((4, 3, 2)[lod],  0.42, 2.65, 0.62, 1.95, 0.35, -0.72, 255), # Central young spear leaves!
    ]
    segs = (6, 4, 3)[lod]
    parts = []
    golden_angle = 2.399963
    idx_f = 0
    for count, y_off, ln, wd, up, drp, rx, br in whorls:
        frond = make_arching_pinnate_frond(ln, wd, up, drp, segs, tint_g=br)
        for k in range(count):
            az = idx_f * golden_angle
            idx_f += 1
            parts.append(xform(frond, rx=rx, ry=az, rz=0.05 * math.sin(idx_f), translate=(0.0, y_off, 0.0)))
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
    # Plump Stylized Multi-Berry Fresh Fruit Bunch (Tandan Buah Segar — matches Blender 4.2 Stylized Sawit!)
    seg = (14, 10, 7)[lod]
    n_rings = (9, 7, 5)[lod]
    rings = []
    ang = np.linspace(-math.pi, math.pi, seg, endpoint=False, dtype=np.float32)
    for i in range(n_rings):
        t = i / (n_rings - 1)
        phi = (t - 0.5) * math.pi * 0.96
        cp, sp = math.cos(phi), math.sin(phi)
        lobe = 1.0 + 0.13 * np.cos(ang * 5.0 + t * 4.0) + 0.08 * np.sin(ang * 3.0 - t * 3.0)
        heart = 1.10 - 0.22 * t
        rings.append(np.stack([np.sin(ang) * 0.24 * cp * heart * lobe, np.full_like(ang, 0.02 + sp * 0.27), np.cos(ang) * 0.23 * cp * heart * lobe], axis=1))

    parts = [make_loft(rings, UV_TBS_FRUIT, col=rgba(255, 255, 255, 165), u_rep=1.0, v_rep=1.0)]
    if lod <= 1:
        n_berries = 16 if lod == 0 else 8
        ga = 2.399963
        for bi in range(n_berries):
            bt = (bi + 0.5) / n_berries
            ph = math.acos(1.0 - 2.0 * bt)
            th = bi * ga
            bx = math.sin(ph) * math.cos(th) * 0.215
            bz = math.sin(ph) * math.sin(th) * 0.205
            by = 0.02 + math.cos(ph) * 0.225
            parts.append(make_sphere_uv(0.082, 0.082, 0.082, UV_TBS_FRUIT, seg=7 if lod == 0 else 5, rings=5, col=rgba(255, 255, 255, 175), center=(bx, by, bz)))
    stalk = make_tube_segment((0.0, 0.24, 0.0), (0.03, 0.39, 0.02), 0.056, 0.040, UV_WOOD_PLAIN,
                              seg=(8, 6, 5)[lod], col=rgba(195, 222, 118, 65), ball_caps=False)
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
    c_paint  = rgba(255, 255, 255, 168)  # Glossy automotive canary-gold enamel
    c_frame  = rgba(38, 41, 46, 85)      # Matte heavy black steel chassis frame
    c_chrome = rgba(248, 250, 255, 215)  # High-gloss chrome / silver steel
    c_lamp   = rgba(255, 255, 255, 252)  # Emissive-capable crystal headlamp lens!
    c_wood   = rgba(255, 255, 255, 82)   # Natural oiled Meranti timber

    # ── A. Heavy Twin C-Channel Steel Chassis Frame Rails + Crossmembers ──
    for sx in (-0.44, 0.44):
        parts.append(make_box(0.11, 0.16, 4.72, UV_STEEL, c_frame, center=(sx, 0.62, -0.10)))
    for cz in (-2.25, -1.25, -0.25, 0.75, 1.75):
        parts.append(make_box(0.88, 0.11, 0.10, UV_STEEL, c_frame, center=(0.0, 0.62, cz)))
    # Differential housing + driveshaft + axle beams + leaf spring packs!
    parts.append(make_sphere_uv(0.20, 0.20, 0.22, UV_STEEL, seg=8, rings=5, col=c_frame, center=(0.0, 0.48, -1.25)))
    parts.append(make_tube_segment((0.0, 0.50, -1.25), (0.0, 0.56, 1.15), 0.055, 0.055, UV_STEEL, seg=6, col=c_frame, ball_caps=False))
    parts.append(make_box(1.56, 0.08, 0.08, UV_STEEL, c_frame, center=(0.0, 0.48, 1.55)))
    parts.append(make_box(1.56, 0.09, 0.09, UV_STEEL, c_frame, center=(0.0, 0.48, -1.25)))

    # ── B. HOLLOW STYLIZED 3D COE MITSUBISHI CANTER CAB (WITH VISIBLE 3D SEATS, DASHBOARD & BEVELS!) ──
    # Lower Cab Body Tub (y = 0.70 .. 1.34) — leaves upper window zone 100% HOLLOW so players see right into the 3D cabin!
    low_cab = [
        (0.70, 0.93, 0.58, 2.16),
        (1.02, 0.96, 0.58, 2.21),
        (1.33, 0.95, 0.58, 2.17),
    ]
    low_rings = []
    for y, hw, zb, zf in low_cab:
        low_rings.append(np.array([
            (-hw * 0.86, y, zf), (0.0, y, zf + 0.028), (hw * 0.86, y, zf),
            (hw, y, zf - 0.13), (hw, y, (zf + zb) * 0.5), (hw, y, zb + 0.10),
            (hw * 0.88, y, zb), (0.0, y, zb), (-hw * 0.88, y, zb),
            (-hw, y, zb + 0.10), (-hw, y, (zf + zb) * 0.5), (-hw, y, zf - 0.13),
        ], dtype=np.float32))
    parts.append(make_loft(low_rings, UV_CANTER_PAINT, col=c_paint, cap_start=True, cap_end=True))

    # Rounded Beveled Aero Roof Cap (y = 2.00 .. 2.16)
    roof_rings = []
    for y, hw, zb, zf in [(2.00, 0.88, 0.62, 1.84), (2.11, 0.84, 0.65, 1.76), (2.16, 0.77, 0.70, 1.66)]:
        roof_rings.append(np.array([
            (-hw * 0.86, y, zf), (0.0, y, zf + 0.02), (hw * 0.86, y, zf),
            (hw, y, zf - 0.12), (hw, y, (zf + zb) * 0.5), (hw, y, zb + 0.10),
            (hw * 0.88, y, zb), (0.0, y, zb), (-hw * 0.88, y, zb),
            (-hw, y, zb + 0.10), (-hw, y, (zf + zb) * 0.5), (-hw, y, zf - 0.12),
        ], dtype=np.float32))
    parts.append(make_loft(roof_rings, UV_CANTER_PAINT, col=c_paint, cap_start=True, cap_end=True))

    # Real 3D Slanted A-Pillars + Rear B-Pillars + Lower Rear Wall
    for sx in (-1.0, 1.0):
        parts.append(make_tube_segment((sx * 0.88, 1.32, 2.13), (sx * 0.82, 2.02, 1.81), 0.055, 0.048, UV_CANTER_PAINT, seg=6, col=c_paint, ball_caps=False))
        parts.append(make_bevel_box(0.13, 0.72, 0.22, UV_CANTER_PAINT, c_paint, center=(sx * 0.86, 1.67, 0.72), bev=0.02))
    parts.append(make_bevel_box(1.74, 0.26, 0.10, UV_CANTER_PAINT, c_paint, center=(0.0, 1.44, 0.63), bev=0.02))

    # REAL 3D CABIN INTERIOR: Recessed Floor + Pedals + Shifter + Beveled Dashboard + Steering Column + TWO TAN RIBBED SEATS!
    parts.append(make_box(1.66, 0.08, 1.34, UV_STEEL, rgba(34, 38, 44, 55), center=(0.0, 1.02, 1.36)))
    parts.append(make_bevel_box(1.64, 0.28, 0.34, UV_STEEL, rgba(44, 48, 56, 75), center=(0.0, 1.24, 1.92), bev=0.03))
    # Solid steering column housing connecting steering wheel hub (0.42, 1.44, 1.86) directly down into dash & floor!
    parts.append(make_tube_segment((0.42, 1.06, 1.98), (0.42, 1.44, 1.86), 0.042, 0.034, UV_STEEL, seg=8, col=rgba(36, 40, 48, 95), ball_caps=True))
    # Center 5-speed Canter gear stick + boot + driver gas/brake pedals + twin roof Basuri horns + amber roof markers!
    parts.append(make_tube_segment((0.04, 1.05, 1.48), (0.08, 1.36, 1.44), 0.022, 0.014, UV_STEEL, seg=6, col=rgba(40, 44, 52, 110)))
    parts.append(make_sphere_uv(0.032, 0.038, 0.032, UV_STEEL, seg=8, rings=5, col=rgba(28, 30, 36, 150), center=(0.08, 1.38, 1.44)))
    for px_ped in (0.32, 0.44, 0.54):
        parts.append(make_box(0.055, 0.09, 0.02, UV_STEEL, rgba(58, 64, 72, 120), center=(px_ped, 1.12, 1.90)))
    if lod <= 1:
        for hx_h in (-0.34, -0.22, 0.22, 0.34):
            parts.append(make_tube_segment((hx_h, 2.20, 1.34), (hx_h, 2.24, 1.78), 0.018, 0.052, UV_STEEL, seg=8, col=c_chrome, ball_caps=False))
        for mx_m in (-0.52, 0.0, 0.52):
            parts.append(make_bevel_box(0.11, 0.055, 0.08, UV_CANTER_FOGLAMP, rgba(255, 188, 36, 250), center=(mx_m, 2.18, 1.72), bev=0.01))
    c_seat = rgba(235, 168, 112, 85)
    for sx_s in (-0.44, 0.44):
        parts.append(make_bevel_box(0.48, 0.14, 0.46, UV_WOOD_PLAIN, c_seat, center=(sx_s, 1.18, 1.26), bev=0.03))
        if lod <= 1:
            for rib in range(3):
                parts.append(make_bevel_box(0.45, 0.16, 0.12, UV_WOOD_PLAIN, c_seat, center=(sx_s, 1.34 + rib * 0.165, 1.04 - rib * 0.015), bev=0.025))

    # 1. Flush Front Turquoise Cel-Reflection Windshield (alpha-cutout viewport reveals 3D seats & steering wheel!)
    parts.append(make_quad(
        (-0.84, 1.33, 2.16), (0.84, 1.33, 2.16),
        (0.79, 2.01, 1.83), (-0.79, 2.01, 1.83),
        UV_CANTER_GLASS, col=rgba(255, 255, 255, 215), double_sided=True
    ))
    # 2. Side Cab Turquoise Cel-Reflection Windows (double-sided so visible from all angles!)
    parts.append(make_quad(
        (0.90, 1.32, 2.06), (0.90, 1.32, 0.84),
        (0.84, 2.00, 0.84), (0.84, 2.00, 1.79),
        UV_CANTER_SIDE_GLS, col=rgba(255, 255, 255, 215), double_sided=True
    ))
    parts.append(make_quad(
        (-0.90, 1.32, 0.84), (-0.90, 1.32, 2.06),
        (-0.84, 2.00, 1.79), (-0.84, 2.00, 0.84),
        UV_CANTER_SIDE_GLS, col=rgba(255, 255, 255, 215), double_sided=True
    ))
    # Recessed black door handles on both doors!
    parts.append(make_quad((0.964, 1.10, 0.96), (0.964, 1.10, 0.76), (0.964, 1.20, 0.76), (0.964, 1.20, 0.96), UV_CANTER_HANDLE, col=c_paint))
    parts.append(make_quad((-0.964, 1.10, 0.76), (-0.964, 1.10, 0.96), (-0.964, 1.20, 0.96), (-0.964, 1.20, 0.76), UV_CANTER_HANDLE, col=c_paint))

    # 3. Center Black Honeycomb Grille + Chrome Bezel & 3-Diamond Crest!
    parts.append(make_quad(
        (-0.48, 0.80, 2.262), (0.48, 0.80, 2.262),
        (0.51, 1.11, 2.272), (-0.51, 1.11, 2.272),
        UV_CANTER_GRILLE, col=c_chrome
    ))

    # 4. Swept-Back Crystal Multi-Reflector Headlamps + Outer Amber Turn Signals (cleanly proud of cab corners!)
    parts.append(make_quad(
        (-0.93, 0.81, 2.222), (-0.50, 0.80, 2.264),
        (-0.52, 1.13, 2.274), (-0.935, 1.15, 2.212),
        UV_CANTER_HEADLAMP, col=c_lamp, flip_u=True
    ))
    parts.append(make_quad(
        (0.50, 0.80, 2.264), (0.93, 0.81, 2.222),
        (0.935, 1.15, 2.212), (0.52, 1.13, 2.274),
        UV_CANTER_HEADLAMP, col=c_lamp, flip_u=False
    ))

    # 5. Front Yellow Steel Bumper + Black Corner Caps + BM 8899 XY License Plate + Twin Amber Fog Lamps!
    parts.append(make_box(1.94, 0.25, 0.16, UV_CANTER_PAINT, c_paint, center=(0.0, 0.62, 2.22)))
    for sx in (-0.92, 0.92):
        parts.append(make_box(0.16, 0.26, 0.22, UV_STEEL, c_frame, center=(sx, 0.62, 2.18)))
    parts.append(make_quad((-0.26, 0.52, 2.306), (0.26, 0.52, 2.306), (0.26, 0.70, 2.306), (-0.26, 0.70, 2.306), UV_CANTER_PLATE, col=rgba(255, 255, 255, 160)))
    for sx in (-0.64, 0.64):
        parts.append(make_quad((sx - 0.13, 0.55, 2.305), (sx + 0.13, 0.55, 2.305), (sx + 0.13, 0.68, 2.305), (sx - 0.13, 0.68, 2.305), UV_CANTER_FOGLAMP, col=c_lamp))

    # 6. Black Plastic Front Wheel Arch Fender Flares + Step Footboards + Dual Tubular Side Mirrors!
    if lod <= 1:
        for sx in (-1.0, 1.0):
            for ai in range(6):
                a0 = -0.95 + ai * 0.38
                a1 = a0 + 0.38
                r_arch = 0.56
                parts.append(make_tube_segment(
                    (sx * 0.93, 0.48 + math.cos(a0) * r_arch, 1.55 + math.sin(a0) * r_arch),
                    (sx * 0.93, 0.48 + math.cos(a1) * r_arch, 1.55 + math.sin(a1) * r_arch),
                    0.048, 0.048, UV_STEEL, seg=6, col=c_frame, ball_caps=False
                ))
            # Tubular steel mirror arm + tall black rectangular mirror housing!
            parts.append(make_tube_segment((sx * 0.90, 1.86, 1.84), (sx * 1.12, 1.80, 2.02), 0.016, 0.016, UV_STEEL, seg=5, col=c_frame, ball_caps=False))
            parts.append(make_tube_segment((sx * 1.12, 1.80, 2.02), (sx * 1.12, 1.44, 2.02), 0.016, 0.016, UV_STEEL, seg=5, col=c_frame, ball_caps=False))
            parts.append(make_tube_segment((sx * 1.12, 1.44, 2.02), (sx * 0.94, 1.38, 1.94), 0.016, 0.016, UV_STEEL, seg=5, col=c_frame, ball_caps=False))
            parts.append(make_box(0.06, 0.32, 0.15, UV_STEEL, c_frame, center=(sx * 1.13, 1.63, 2.02)))

    # ── C. STYLIZED PLANK-BY-PLANK BEVELED MERANTI "BAK KAYU" SAWIT CARGO BED (Matches Blender 4.2 Canter!) ──
    parts.append(make_bevel_box(2.00, 0.11, 2.94, UV_WOOD_PLAIN, c_wood, center=(0.0, 0.80, -0.96), bev=0.02))
    n_planks = 6 if lod <= 1 else 3
    for pi in range(n_planks):
        py = 0.92 + pi * (1.06 / max(1, n_planks - 1))
        ph = (1.02 / n_planks)
        flare = 0.96 + (pi / max(1, n_planks - 1)) * 0.045
        for sx in (-1.0, 1.0):
            parts.append(make_bevel_box(0.065, ph, 2.92, UV_WOOD_PLAIN, c_wood, center=(sx * flare, py, -0.96), bev=0.015))
        parts.append(make_bevel_box(flare * 2.0, ph, 0.065, UV_WOOD_PLAIN, c_wood, center=(0.0, py, -2.40), bev=0.015))
        parts.append(make_bevel_box(2.00, ph, 0.065, UV_WOOD_PLAIN, c_wood, center=(0.0, py, 0.49), bev=0.015))
    # Extra tall cab protector top header planks ("Kepala Bak")
    parts.append(make_bevel_box(2.02, 0.16, 0.065, UV_WOOD_PLAIN, c_wood, center=(0.0, 2.15, 0.49), bev=0.015))
    parts.append(make_bevel_box(2.06, 0.15, 0.14, UV_WOOD_PLAIN, c_wood, center=(0.0, 2.33, 0.52), bev=0.02))
    for sx in (-0.92, 0.92):
        parts.append(make_bevel_box(0.11, 0.08, 0.06, UV_CANTER_FOGLAMP, c_lamp, center=(sx, 2.34, 0.62), bev=0.01))
    # Red/White Safety Reflector Strips along both sides!
    for seg_i in range(6):
        rz_s = 0.22 - seg_i * 0.48
        s_col = rgba(242, 58, 44, 150) if seg_i % 2 == 0 else rgba(248, 250, 252, 150)
        for sx in (-1.015, 1.015):
            parts.append(make_box(0.02, 0.055, 0.40, UV_CONCRETE_CLEAN, s_col, center=(sx, 1.34, rz_s)))
    parts.append(make_bevel_box(1.94, 0.16, 0.14, UV_STEEL, c_frame, center=(0.0, 0.60, -2.44), bev=0.025))
    for sx in (-0.74, 0.74):
        parts.append(make_bevel_box(0.24, 0.13, 0.07, UV_CANTER_FOGLAMP, rgba(255, 96, 48, 252), center=(sx, 0.62, -2.50), bev=0.015))

    # External Vertical Steel Stakes + Strapped Terracotta Diesel Tank + Battery Box!
    if lod <= 1:
        for rz in (-2.28, -1.72, -1.16, -0.60, -0.04, 0.44):
            for sx in (-1.015, 1.015):
                parts.append(make_bevel_box(0.062, 1.24, 0.070, UV_STEEL, c_frame, center=(sx, 1.40, rz), bev=0.012))
        for sx in (-0.92, 0.92):
            parts.append(make_box(0.42, 0.34, 0.02, UV_STEEL, c_frame, center=(sx, 0.34, -1.82)))
        parts.append(make_bevel_box(0.34, 0.25, 0.46, UV_STEEL, c_frame, center=(0.68, 0.56, 0.72), bev=0.02))
        parts.append(make_tube_segment((-0.68, 0.54, 0.34), (-0.68, 0.54, 1.08), 0.19, 0.19, UV_WOOD_PLAIN, seg=12, col=rgba(186, 86, 56, 130), ball_caps=True))
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
    """Heavy-duty 7.50-16 Radial Truck Tire & 6-Lug Steel Rim mapped onto UV_TIRE_TREAD & UV_WHEEL_CENTER!"""
    seg = (20, 14, 9)[lod]
    R = 0.48
    hw = 0.145
    ang = np.linspace(0.0, 2.0 * math.pi, seg + 1, dtype=np.float32)

    # 1. Outer tire tread band with beveled shoulders
    tread_profile = [(-hw, R * 0.90), (-hw * 0.82, R), (hw * 0.82, R), (hw, R * 0.90)]
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

    # Check outward winding on tread
    # Outer face on +X and -X mapped radially onto UV_WHEEL_CENTER (6-lug steel rim + sidewall ribs!)
    parts = [tread]
    ucx, ucy, urad = UV_WHEEL_CENTER
    for side in (-1.0, 1.0):
        # 4 concentric profile rings for realistic 3D recessed steel wheel dish + protruding axle hub!
        rad_steps = [(R * 0.90, hw * side), (R * 0.62, hw * 0.92 * side), (R * 0.44, hw * 0.56 * side),
                     (R * 0.20, hw * 0.88 * side), (0.0, hw * 0.94 * side)]
        f_pos, f_uv, f_tris = [], [], []
        for rad, x_off in rad_steps:
            for j in range(seg):
                a = j * 2.0 * math.pi / seg
                sy, cz = math.sin(a), math.cos(a)
                f_pos.append([x_off, sy * rad, cz * rad])
                f_uv.append([ucx + (cz * rad / (R * 0.90)) * urad, ucy - (sy * rad / (R * 0.90)) * urad])
        for ri in range(len(rad_steps) - 1):
            b0, b1 = ri * seg, (ri + 1) * seg
            for j in range(seg):
                jn = (j + 1) % seg
                if side > 0:
                    f_tris.extend([[b0 + j, b0 + jn, b1 + jn], [b0 + j, b1 + jn, b1 + j]])
                else:
                    f_tris.extend([[b0 + j, b1 + jn, b0 + jn], [b0 + j, b1 + j, b1 + jn]])
        parts.append(MeshPart(np.array(f_pos, np.float32), np.array(f_uv, np.float32),
                              np.broadcast_to(rgba(255, 255, 255, 115), (len(f_pos), 4)).copy(), np.array(f_tris, np.int32)))

    merged = merge_parts(parts)
    # Verify positive signed volume on closed wheel!
    v0, v1, v2 = merged.pos[merged.idx[:, 0]], merged.pos[merged.idx[:, 1]], merged.pos[merged.idx[:, 2]]
    if float(np.sum(np.einsum("ij,ij->i", v0, np.cross(v1, v2)))) < 0.0:
        merged.idx = merged.idx[:, [0, 2, 1]]
    return merged


# ═══════════════════════════════════════════════════════════════════════════
# 3. ORGANIC SEAMLESS BALL-JOINTED HUMAN ANATOMY & COMPLETE ACCESSORIES
# ═══════════════════════════════════════════════════════════════════════════

def build_char_torso_head(lod: int) -> MeshPart:
    """Athletic seamless human pelvis + work belt + V-tapered collared field shirt (y = -0.10 .. +0.58)."""
    seg = (16, 12, 8)[lod]
    # 1. Pelvis / hips in dark stitched work trousers (y = -0.11 .. +0.10) so zero gap when legs stride!
    pelvis_rings = [
        ring_ellipse(0.145, 0.105, -0.10, seg),
        ring_ellipse(0.168, 0.122, -0.02, seg),
        ring_ellipse(0.162, 0.116,  0.09, seg),
    ]
    pelvis = make_loft(pelvis_rings, UV_DENIM, col=rgba(255, 255, 255, 60))

    # 2. Leather utility belt + brass buckle (y = 0.08 .. 0.135)
    belt = make_loft([ring_ellipse(0.168, 0.122, 0.08, seg), ring_ellipse(0.168, 0.122, 0.135, seg)],
                     UV_WOOD_PLAIN, col=rgba(72, 48, 30, 95))
    buckle = make_box(0.065, 0.052, 0.025, UV_STEEL, rgba(238, 196, 68, 190), center=(0.0, 0.108, 0.126))

    # 3. Athletic dyeable field shirt with natural chest/lat taper, collar & spherical shoulder sockets (y = 0.12 .. 0.53)
    shirt_stations = [
        (0.12, 0.162, 0.115, 0.00),
        (0.24, 0.172, 0.122, 0.005),
        (0.37, 0.205, 0.138, 0.012),  # Pectoral / ribcage fullness
        (0.47, 0.222, 0.132, 0.008),  # Broad natural deltoid/clavicle line
        (0.525, 0.115, 0.092, 0.004), # Smooth trapezius slope into collar
    ]
    shirt_rings = [ring_ellipse(rx, rz, y, seg, cz=cz) for y, rx, rz, cz in shirt_stations]
    shirt = make_loft(shirt_rings, UV_SHIRT_FRONT, col=rgba(255, 255, 255, 58), dyeable=True)

    # Folded shirt collar + seamless skin neck column rising into head socket (y = 0.50 .. 0.61)
    collar = make_loft([ring_ellipse(0.092, 0.088, 0.505, seg, cz=0.005), ring_ellipse(0.082, 0.080, 0.555, seg, cz=0.008)],
                       UV_SHIRT_PLAIN, col=rgba(240, 240, 240, 55), dyeable=True)
    neck = make_loft([ring_ellipse(0.064, 0.062, 0.52, seg, cz=0.008), ring_ellipse(0.058, 0.058, 0.61, seg, cz=0.010)],
                     UV_SKIN, col=rgba(255, 255, 255, 65))
    return merge_parts([pelvis, belt, buckle, shirt, collar, neck])


def build_char_head(lod: int) -> MeshPart:
    """Natural 3D sculpted human head with smooth cranium, jawline, 3D nose, ears & layered hair mapped onto UV_FACE!"""
    seg = (20, 14, 9)[lod]
    ang = np.linspace(-math.pi, math.pi, seg, endpoint=False, dtype=np.float32)
    # Profile from chin (y=0.02) to crown (y=0.255)
    profile = [
        (0.020, 0.048, 0.055, 0.022),  # Chin tip
        (0.052, 0.078, 0.086, 0.012),  # Jawline
        (0.098, 0.092, 0.102, 0.006),  # Cheekbones / mouth level
        (0.142, 0.096, 0.106, 0.004),  # Eye / brow ridge level
        (0.195, 0.095, 0.105, -0.002), # Forehead
        (0.236, 0.078, 0.088, -0.006), # Upper cranium
        (0.256, 0.042, 0.048, -0.008), # Crown apex
    ]
    pos_rows, uv_rows = [], []
    u0, v0, u1, v1 = UV_FACE
    hu0, hv0, hu1, hv1 = UV_HAIR
    for ri, (y, rx, rz, cz) in enumerate(profile):
        v_t = 1.0 - (ri / (len(profile) - 1.0))  # 1 at chin, 0 at top of forehead
        ring = np.stack([np.sin(ang) * rx, np.full_like(ang, y), cz + np.cos(ang) * rz], axis=1)
        # Subtle 3D nose bridge bulge right at front (ang == 0 -> cos(ang) == 1)!
        if ri in (2, 3):
            nose_push = np.maximum(0.0, np.cos(ang)) ** 10.0 * (0.020 if ri == 2 else 0.012)
            ring[:, 2] += nose_push
        ring_closed = np.vstack([ring, ring[0:1]])
        pos_rows.append(ring_closed.astype(np.float32))

        # Front half (-pi/2 .. +pi/2) maps cleanly across UV_FACE; back of head maps onto skin/hair!
        u_row = np.empty((seg + 1, 2), dtype=np.float32)
        for j in range(seg + 1):
            a = -math.pi + (j / seg) * 2.0 * math.pi
            # Map -1.05 .. +1.05 radians directly across full UV_FACE width!
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
    # Cap chin & crown
    c_bot = profile[0]
    c_top = profile[-1]
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
    head_mesh = MeshPart(pos_a, uv_a, np.broadcast_to(rgba(255, 255, 255, 68), (len(pos_a), 4)).copy(), idx_a)

    # Natural sculpted 3D hair volume cap covering back of head, sideburns & forehead fringe (leaves face open!)
    hair_rings = []
    h_seg = (16, 12, 8)[lod]
    hang = np.linspace(-math.pi, math.pi, h_seg, endpoint=False, dtype=np.float32)
    for hi, (hy, hrx, hrz) in enumerate([
        (0.095, 0.096, 0.104),
        (0.155, 0.103, 0.112),
        (0.208, 0.103, 0.113),
        (0.252, 0.084, 0.094),
        (0.272, 0.042, 0.048),
    ]):
        # Pull hair cleanly behind front face hemisphere so zero dark hair ever clips temples or brows!
        front_mask = np.clip(1.45 - np.abs(hang), 0.0, 1.0)
        tuck = front_mask * (0.068 if hy < 0.19 else 0.012)
        pts = np.stack([np.sin(hang) * (hrx - tuck * 0.45), np.full_like(hang, hy), -0.012 + np.cos(hang) * (hrz - tuck)], axis=1)
        hair_rings.append(pts)
    hair = make_loft(hair_rings, UV_HAIR, col=rgba(255, 255, 255, 78))

    parts = [head_mesh, hair]
    if lod <= 1:
        # Sculpted human ears on both sides!
        for sx in (-1.0, 1.0):
            parts.append(make_sphere_uv(0.016, 0.030, 0.020, UV_SKIN, seg=7, rings=5, col=rgba(245, 240, 238, 65), center=(sx * 0.094, 0.132, -0.004)))
    return merge_parts(parts)


def build_char_face_neutral(lod: int) -> MeshPart:
    """Visible low-poly facial details: expressive eyes, brows, and a relaxed mouth."""
    seg = (9, 7, 5)[lod]
    parts = []
    for sx in (-1.0, 1.0):
        parts.append(make_sphere_uv(0.013, 0.010, 0.008, UV_SKIN, seg=seg, rings=5,
                                    col=rgba(250, 246, 230, 245), center=(sx * 0.037, 0.146, 0.094)))
        parts.append(make_sphere_uv(0.0055, 0.0065, 0.004, UV_STEEL, seg=6, rings=4,
                                    col=rgba(22, 24, 26, 245), center=(sx * 0.037, 0.145, 0.102)))
        parts.append(make_tube_segment((sx * 0.066, 0.173, 0.079), (sx * 0.012, 0.178, 0.101),
                                       0.007, 0.008, UV_HAIR, seg=6, col=rgba(54, 38, 28, 235), ball_caps=False))
    parts.append(make_tube_segment((-0.020, 0.073, 0.099), (0.020, 0.073, 0.099),
                                   0.0045, 0.0045, UV_SKIN, seg=6, col=rgba(104, 43, 39, 230), ball_caps=False))
    return merge_parts(parts)


def build_char_face_strain(lod: int) -> MeshPart:
    """Strained brow, open-mouth effort expression and sweat bead for the heavy TBS hoist pose."""
    parts = []
    seg = (8, 6, 5)[lod]
    for sx in (-1.0, 1.0):
        # Narrowed eyes and brows pinched toward the nose under load.
        parts.append(make_tube_segment((sx * 0.052, 0.148, 0.095), (sx * 0.020, 0.147, 0.108),
                                       0.0055, 0.0055, UV_STEEL, seg=seg, col=rgba(25, 28, 31, 245), ball_caps=False))
        parts.append(make_tube_segment((sx * 0.066, 0.179, 0.078), (sx * 0.012, 0.162, 0.104),
                                       0.009, 0.010, UV_HAIR, seg=seg, col=rgba(48, 33, 24, 245), ball_caps=False))
    parts.append(make_sphere_uv(0.020, 0.027, 0.010, UV_STEEL, seg=seg, rings=5,
                                col=rgba(70, 30, 27, 242), center=(0.0, 0.074, 0.105)))
    parts.append(make_sphere_uv(0.010, 0.004, 0.004, UV_SKIN, seg=6, rings=4,
                                col=rgba(250, 240, 218, 245), center=(0.0, 0.092, 0.113)))
    parts.append(make_sphere_uv(0.010, 0.016, 0.010, UV_CANTER_GLASS, seg=seg, rings=5,
                                col=rgba(120, 226, 248, 220), center=(0.104, 0.205, 0.025)))
    return merge_parts(parts)


def build_char_arm(lod: int) -> MeshPart:
    """Seamless ball-jointed upper arm: rolled shirt sleeve deltoid top + muscular bicep/tricep + spherical elbow cap!"""
    seg = (12, 9, 6)[lod]
    # Rolled sleeve covering shoulder ball socket (y = +0.045 .. -0.115)
    sleeve = make_loft([
        ring_ellipse(0.058, 0.058,  0.045, seg),
        ring_ellipse(0.064, 0.064, -0.015, seg),
        ring_ellipse(0.056, 0.056, -0.115, seg),
    ], UV_SHIRT_PLAIN, col=rgba(255, 255, 255, 58), dyeable=True)
    # Bare muscular upper arm + spherical elbow ball cap (y = -0.105 .. -0.295)
    bicep = make_tube_segment((0.0, -0.105, 0.0), (0.0, -0.275, 0.0), 0.048, 0.041, UV_SKIN, seg=seg, col=rgba(255, 255, 255, 68), ball_caps=True)
    return merge_parts([sleeve, bicep])


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
    """Legendary Golden Sultan 5.05m Carbon-Gold Egrek Naga with Emerald Gem & Gold Dragon Guard!"""
    base = build_tool_egrek(lod)
    gold_sleeve = make_tube_segment((0.0, 1.54, 0.0), (0.0, 3.00, 0.0), 0.0172, 0.0158, UV_STEEL, seg=8, col=rgba(255, 206, 48, 225), ball_caps=False)
    guard = make_sphere_uv(0.052, 0.075, 0.075, UV_STEEL, seg=8, rings=5, col=rgba(255, 206, 48, 238), center=(0.0, 4.10, 0.03))
    gem = make_sphere_uv(0.026, 0.034, 0.026, UV_STEEL, seg=6, rings=4, col=rgba(40, 244, 148, 252), center=(0.0, 4.10, 0.085))
    return merge_parts([base, gold_sleeve, guard, gem])


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

    # Solid steel axle shaft passing straight through wheel center (0.000, 0.290, 0.800)!
    parts.append(make_tube_segment((-0.135, 0.290, 0.800), (0.135, 0.290, 0.800), 0.022, 0.022, UV_STEEL, seg=8, col=rgba(62, 68, 78, 175)))
    parts.append(make_tube_segment((-0.26, 0.38, -0.42), (0.26, 0.38, -0.42), 0.020, 0.020, UV_STEEL, seg=6, col=rgba(54, 60, 68, 145)))

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
    parts = [
        # Concrete forecourt slab + raised pump island
        make_box(9.6, 0.16, 8.2, UV_CONCRETE, rgba(226, 230, 236, 95), center=(0.0, 0.08, 0.0)),
        make_bevel_box(3.8, 0.22, 1.5, UV_CONCRETE_CLEAN, rgba(235, 196, 34, 125), center=(0.0, 0.22, 0.0), bev=0.03),
        # Four white canopy steel columns + crisp red-white Pertashop canopy fascia!
        make_box(7.8, 0.56, 6.2, UV_CONCRETE_CLEAN, red_brand, center=(0.0, 4.18, 0.0)),
        make_box(7.92, 0.16, 6.32, UV_CONCRETE_CLEAN, white_clean, center=(0.0, 3.88, 0.0)),
        # Twin Digital Biosolar B35 Fuel Dispensers + Glowing Cyan LCD Meter + Nozzle Hoses!
        make_bevel_box(0.76, 1.68, 0.52, UV_CONCRETE_CLEAN, white_clean, center=(-0.95, 1.12, 0.0), bev=0.03),
        make_bevel_box(0.76, 1.68, 0.52, UV_CONCRETE_CLEAN, white_clean, center=( 0.95, 1.12, 0.0), bev=0.03),
        make_box(0.78, 0.42, 0.54, UV_CONCRETE_CLEAN, red_brand, center=(-0.95, 1.72, 0.0)),
        make_box(0.78, 0.42, 0.54, UV_CONCRETE_CLEAN, rgba(32, 158, 92, 165), center=( 0.95, 1.72, 0.0)),
        make_box(0.48, 0.26, 0.55, UV_CONCRETE_CLEAN, rgba(56, 232, 178, 252), center=(-0.95, 1.30, 0.0)),
        make_box(0.48, 0.26, 0.55, UV_CONCRETE_CLEAN, rgba(56, 232, 178, 252), center=( 0.95, 1.30, 0.0)),
        # Side Truck Tire & Suspension Service Bay Ramps!
        xform(make_box(0.68, 0.34, 2.8, UV_STEEL, rgba(242, 192, 28, 165)), rx=0.11, translate=(-3.35, 0.20, 0.4)),
        xform(make_box(0.68, 0.34, 2.8, UV_STEEL, rgba(242, 192, 28, 165)), rx=0.11, translate=(-1.95, 0.20, 0.4)),
        make_tube_segment((3.4, 0.36, -2.4), (4.4, 0.36, -2.4), 0.26, 0.26, UV_STEEL, seg=10, col=rgba(36, 124, 208, 165)),
    ]
    for cx in (-3.1, 3.1):
        for cz in (-2.4, 2.4):
            parts.append(make_box(0.24, 3.85, 0.24, UV_CONCRETE_CLEAN, white_clean, center=(cx, 1.95, cz)))
    if lod <= 1:
        for hx in (-0.52, 1.38):
            parts.append(make_tube_segment((hx, 1.38, 0.12), (hx + 0.14, 0.62, 0.22), 0.022, 0.022, UV_STEEL, seg=5, col=steel_c))
    return merge_parts(parts)


def build_warung_kopi(lod: int) -> MeshPart:
    """Traditional Sumatran Plantation 'Warung Kopi & Istirahat Pemanen' with Wooden Bench, Counter & Kettle!"""
    parts = [
        make_box(5.4, 0.16, 4.6, UV_WOOD_PLAIN, rgba(206, 182, 152, 75), center=(0.0, 0.08, 0.0)),
        make_box(4.6, 1.05, 1.8, UV_WOOD_BAK, rgba(228, 196, 158, 82), center=(0.0, 0.68, -0.95)),
        make_box(4.75, 0.09, 0.92, UV_WOOD_PLAIN, rgba(244, 224, 192, 95), center=(0.0, 1.24, -0.42)),
        make_box(4.6, 2.25, 0.16, UV_WOOD_BAK, rgba(212, 186, 152, 78), center=(0.0, 1.28, -1.82)),
        xform(make_box(5.8, 0.12, 3.2, UV_CORRUGATED, rgba(44, 146, 96, 128)), rx=0.22, translate=(0.0, 2.86, -0.95)),
        xform(make_box(5.8, 0.12, 2.8, UV_CORRUGATED, rgba(218, 92, 48, 128)), rx=-0.26, translate=(0.0, 2.74, 0.95)),
        # Long wooden harvester bench in front of counter + glowing warm hanging lantern + brass coffee kettle!
        make_bevel_box(3.6, 0.08, 0.44, UV_WOOD_PLAIN, rgba(232, 204, 168, 85), center=(0.0, 0.50, 0.98), bev=0.015),
        make_box(0.18, 0.48, 0.38, UV_WOOD_PLAIN, rgba(148, 102, 58, 75), center=(-1.4, 0.24, 0.98)),
        make_box(0.18, 0.48, 0.38, UV_WOOD_PLAIN, rgba(148, 102, 58, 75), center=( 1.4, 0.24, 0.98)),
        make_sphere_uv(0.16, 0.20, 0.16, UV_CANTER_HEADLAMP, seg=10, rings=6, col=rgba(255, 226, 128, 253), center=(0.0, 2.28, 0.42)),
        make_tube_segment((-0.85, 1.28, -0.38), (-0.85, 1.62, -0.38), 0.16, 0.12, UV_STEEL, seg=10, col=rgba(232, 188, 64, 205)),
    ]
    for px in (-2.35, 2.35):
        for pz in (-1.75, 1.75):
            parts.append(make_box(0.16, 2.65, 0.16, UV_WOOD_PLAIN, rgba(132, 88, 48, 75), center=(px, 1.38, pz)))
    return merge_parts(parts)


def build_gudang_pupuk(lod: int) -> MeshPart:
    """Plantation 'Gudang Pupuk NPK Mutiara' Warehouse with Concrete Dock & Stacked 50kg NPK Sacks!"""
    parts = [
        make_box(8.4, 0.42, 7.2, UV_CONCRETE, rgba(218, 224, 230, 92), center=(0.0, 0.21, 0.0)),
        make_box(7.6, 3.85, 5.4, UV_CORRUGATED, rgba(226, 236, 228, 112), center=(0.0, 2.34, -0.65)),
        xform(make_box(4.4, 0.15, 6.0, UV_CORRUGATED, rgba(36, 134, 82, 132)), rz=0.24, translate=(-1.98, 4.68, -0.65)),
        xform(make_box(4.4, 0.15, 6.0, UV_CORRUGATED, rgba(36, 134, 82, 132)), rz=-0.24, translate=( 1.98, 4.68, -0.65)),
        make_box(3.2, 2.65, 0.18, UV_STEEL, rgba(32, 42, 52, 95), center=(0.0, 1.74, 2.08)),
    ]
    # Stacked blue/white 50kg NPK fertilizer sacks on front concrete dock!
    for si, (sx, sy, sz) in enumerate([(-2.2, 0.56, 2.55), (-1.35, 0.56, 2.55), (-1.78, 0.80, 2.55),
                                       ( 2.2, 0.56, 2.55), ( 1.35, 0.56, 2.55), ( 1.78, 0.80, 2.55)]):
        sack_col = rgba(52, 152, 235, 95) if si % 2 == 0 else rgba(245, 206, 62, 110)
        parts.append(make_sphere_uv(0.38, 0.15, 0.26, UV_WOVEN, seg=8, rings=5, col=sack_col, center=(sx, sy, sz)))
    return merge_parts(parts)


def build_offroad_arch(lod: int) -> MeshPart:
    """Heavy Timber Offroad Mud Hill Trailhead Arch ('Jalur Tanjakan Lumpur Sitinjau Sawit')!"""
    parts = [
        make_tube_segment((-3.1, 0.0, 0.0), (-2.85, 4.2, 0.0), 0.22, 0.18, UV_WOOD_PLAIN, seg=8, col=rgba(148, 98, 54, 78)),
        make_tube_segment(( 3.1, 0.0, 0.0), ( 2.85, 4.2, 0.0), 0.22, 0.18, UV_WOOD_PLAIN, seg=8, col=rgba(148, 98, 54, 78)),
        make_bevel_box(6.4, 0.72, 0.26, UV_CANTER_PAINT, rgba(242, 188, 28, 165), center=(0.0, 3.85, 0.0), bev=0.03),
        make_bevel_box(5.6, 0.42, 0.30, UV_STEEL, rgba(28, 34, 42, 145), center=(0.0, 3.85, 0.0), bev=0.02),
    ]
    for sx in (-3.25, 3.25):
        parts.append(xform(build_truck_wheel(2), rz=math.pi * 0.5, translate=(sx, 0.18, 0.65)))
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
    seg = (14, 10, 7)[lod]
    fur = rgba(96, 68, 50, 58)
    rings = [
        ring_ellipse(0.11, 0.11, 0.44, seg, cz=0.68),   # Snout tip
        ring_ellipse(0.20, 0.20, 0.50, seg, cz=0.46),   # Skull / jaw
        ring_ellipse(0.30, 0.32, 0.56, seg, cz=0.16),   # Muscular shoulders / hump
        ring_ellipse(0.28, 0.30, 0.53, seg, cz=-0.22),  # Flank
        ring_ellipse(0.16, 0.18, 0.48, seg, cz=-0.56),  # Rump
    ]
    parts = [make_loft(rings, UV_PALM_BARK, col=fur)]
    # Curved white tusks + ears + dorsal bristle ridge!
    for sx in (-1.0, 1.0):
        parts.append(make_tube_segment((sx * 0.10, 0.44, 0.58), (sx * 0.17, 0.56, 0.66), 0.022, 0.005, UV_STEEL, seg=6, col=rgba(245, 240, 226, 165), ball_caps=False))
        parts.append(make_sphere_uv(0.04, 0.08, 0.05, UV_PALM_BARK, seg=6, rings=4, col=fur, center=(sx * 0.17, 0.66, 0.42)))
    return merge_parts(parts)


def build_boar_leg(lod: int) -> MeshPart:
    return make_tube_segment((0.0, 0.0, 0.0), (0.0, -0.48, 0.02), 0.068, 0.036, UV_PALM_BARK, seg=(8, 6, 5)[lod], col=rgba(74, 52, 38, 55))


def build_pks_factory(lod: int) -> MeshPart:
    """Realistic Indonesian Palm Oil Mill (Pabrik Kelapa Sawit / PKS): corrugated halls, CPO tanks & twin tall smokestacks!"""
    parts = [
        # Main processing hall
        make_box(13.2, 6.8, 10.6, UV_CORRUGATED, rgba(220, 226, 232, 115), center=(0.0, 3.4, 0.0)),
        # Green factory gabled roof
        xform(make_box(7.2, 0.18, 11.2, UV_CORRUGATED, rgba(42, 128, 82, 130)), rz=0.22, translate=(-3.3, 7.45, 0.0)),
        xform(make_box(7.2, 0.18, 11.2, UV_CORRUGATED, rgba(42, 128, 82, 130)), rz=-0.22, translate=(3.3, 7.45, 0.0)),
        # Receiving hopper canopy & loading bay door
        make_box(5.6, 0.22, 3.4, UV_CANTER_PAINT, rgba(235, 190, 28, 145), center=(0.0, 4.4, 6.4)),
        make_box(4.2, 3.8, 0.3, UV_STEEL, rgba(26, 30, 36, 65), center=(0.0, 1.9, 5.25)),
        # Twin silver Cylindrical CPO Storage Silos!
        make_tube_segment((8.2, 0.0, 1.2), (8.2, 6.2, 1.2), 2.1, 2.1, UV_CORRUGATED, seg=(18, 12, 8)[lod], col=rgba(235, 240, 245, 165), ball_caps=True),
        make_tube_segment((8.4, 0.0, -3.4), (8.4, 5.6, -3.4), 1.85, 1.85, UV_CORRUGATED, seg=(18, 12, 8)[lod], col=rgba(230, 236, 242, 165), ball_caps=True),
        # Twin tall industrial red/white boiler chimneys!
        make_tube_segment((-3.2, 6.5, -2.2), (-3.2, 14.5, -2.2), 0.56, 0.40, UV_CORRUGATED, seg=12, col=rgba(198, 68, 52, 110), ball_caps=False),
        make_tube_segment((-1.2, 6.5, -2.2), (-1.2, 13.6, -2.2), 0.50, 0.36, UV_CORRUGATED, seg=12, col=rgba(228, 232, 238, 110), ball_caps=False),
    ]
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
    """Authentic RAM Sawit Truck Weighbridge Deck + Operator Booth + LED Digital Tonnage Arch!"""
    parts = [
        # Heavy concrete & diamond-steel deck + approach ramps with yellow hazard stripes!
        make_box(4.2, 0.34, 7.6, UV_CONCRETE, rgba(225, 228, 232, 95), center=(0.0, 0.17, 0.0)),
        xform(make_box(4.2, 0.26, 2.4, UV_CONCRETE, rgba(235, 198, 38, 110)), rx=0.13, translate=(0.0, 0.05, 4.85)),
        xform(make_box(4.2, 0.26, 2.4, UV_CONCRETE, rgba(235, 198, 38, 110)), rx=-0.13, translate=(0.0, 0.05, -4.85)),
        # Operator cabin beside scale
        make_box(2.1, 2.45, 2.3, UV_CONCRETE_CLEAN, rgba(238, 242, 246, 85), center=(3.35, 1.22, 0.0)),
        make_box(2.4, 0.16, 2.6, UV_CORRUGATED, rgba(42, 132, 84, 125), center=(3.35, 2.52, 0.0)),
        make_box(0.08, 0.85, 1.35, UV_CONCRETE_CLEAN, rgba(64, 196, 214, 225), center=(2.28, 1.55, 0.0)),
        # Overhead gantry + glowing emerald LED weight indicator board
        make_box(0.14, 3.6, 0.14, UV_STEEL, rgba(44, 50, 58, 120), center=(-2.15, 1.8, -1.8)),
        make_box(0.14, 3.6, 0.14, UV_STEEL, rgba(44, 50, 58, 120), center=( 2.15, 1.8, -1.8)),
        make_box(4.5, 0.62, 0.22, UV_STEEL, rgba(22, 26, 32, 145), center=(0.0, 3.55, -1.8)),
        make_quad((-1.7, 3.36, -1.68), (1.7, 3.36, -1.68), (1.7, 3.74, -1.68), (-1.7, 3.74, -1.68),
                  UV_CONCRETE_CLEAN, col=rgba(52, 245, 148, 253)),
    ]
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
