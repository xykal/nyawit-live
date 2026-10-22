// Nyawit Live 3D — Custom WebGL2 Instanced Engine Client (100% Shared Protocol & Binary .npak Meshes with Native C# Android APK!)

const WORLD_SEED = 20261022;
const CANAL_Z = -48.0;
const PKS_POS = { x: 0.0, z: -26.0 };
const RAM_POS = { x: 0.0, z: -14.5 };
const MANDOR_POS = { x: -12.5, z: -11.0 };

function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function roadFactor(x, z) {
  const dNS = Math.abs(x);
  const dEW = Math.abs(z - 14.0);
  const rLoop = Math.abs(Math.hypot(x, z - 8.0) - 70.0);
  const dPlaza = Math.max(0.0, Math.hypot(x, z + 15.0) - 15.5);
  const dBL = Math.abs(x + 28.0) < 2.4 && Math.abs(z - CANAL_Z) < 6.5 ? 0.0 : 99.0;
  const dBR = Math.abs(x - 28.0) < 2.4 && Math.abs(z - CANAL_Z) < 6.5 ? 0.0 : 99.0;
  return Math.max(0.0, Math.min(1.0, 1.0 - (Math.min(dNS, dEW, rLoop, dPlaza, dBL, dBR) - 2.6) / 2.2));
}

function mudFactor(x, z) {
  const n = Math.sin(x * 0.075 + 1.1) * Math.cos(z * 0.068 - 0.7) + 0.5 * Math.sin((x + z) * 0.11);
  return Math.max(0.0, Math.min(1.0, (n - 0.28) * 1.35)) * (1.0 - roadFactor(x, z) * 0.65);
}

function terrainHeight(x, z) {
  const yardFlat = Math.max(0.0, Math.min(1.0, (Math.hypot(x, z + 16.0) - 18.0) / 10.0));
  let h = (Math.sin(x * 0.036) * Math.cos(z * 0.032) * 1.45 + Math.sin(x * 0.082 + 0.9) * Math.sin(z * 0.076) * 0.42) * yardFlat;
  const edge = Math.max(0.0, (Math.max(Math.abs(x), Math.abs(z)) - 86.0) / 22.0);
  h += edge * edge * 6.5;
  const dCanal = Math.abs(z - CANAL_Z);
  if (dCanal < 4.6) {
    const k = Math.cos((dCanal / 4.6) * Math.PI * 0.5);
    h -= k * k * 1.85;
  }
  return h;
}

function surfaceHeight(x, z) {
  // Walk/drive smoothly across arched wooden canal bridges at x = -28 and x = +28!
  if ((Math.abs(x + 28.0) < 2.2 || Math.abs(x - 28.0) < 2.2) && Math.abs(z - CANAL_Z) < 4.3) {
    const dz = z - CANAL_Z;
    return terrainHeight(x, CANAL_Z - 4.7) + 0.52 * (1.0 - (dz / 4.2) ** 2) + 0.32;
  }
  return terrainHeight(x, z);
}

function generatePlantationTrees() {
  const rng = mulberry32(WORLD_SEED);
  const trees = [];
  for (let gx = -94; gx <= 94 && trees.length < 180; gx += 11.5) {
    for (let gz = -92; gz <= 94 && trees.length < 180; gz += 11.5) {
      const x = +(gx + (rng() - 0.5) * 3.8).toFixed(2);
      const z = +(gz + (rng() - 0.5) * 3.8).toFixed(2);
      const rot = +(rng() * Math.PI * 2.0).toFixed(3);
      const scale = +(0.84 + rng() * 0.34).toFixed(3);
      if (Math.hypot(x, z + 15.0) < 22.0) continue;
      if (Math.abs(z - CANAL_Z) < 6.4) continue;
      if (roadFactor(x, z) > 0.35) continue;
      trees.push({ id: trees.length, x, y: +terrainHeight(x, z).toFixed(2), z, rot, scale, state: trees.length % 13 === 0 ? 2 : 1 });
    }
  }
  return trees;
}

// --- Matrix Math (Column-major Float32Array for WebGL2 / GLES3 parity) ---
function matPersp(out, fovRad, aspect, near, far) {
  const f = 1.0 / Math.tan(fovRad * 0.5);
  const nf = 1.0 / (near - far);
  out.fill(0);
  out[0] = f / aspect;
  out[5] = f;
  out[10] = (far + near) * nf;
  out[11] = -1.0;
  out[14] = 2.0 * far * near * nf;
  return out;
}

function matLookAt(out, ex, ey, ez, tx, ty, tz) {
  let zx = ex - tx, zy = ey - ty, zz = ez - tz;
  let l = Math.hypot(zx, zy, zz) || 1;
  zx /= l; zy /= l; zz /= l;
  let xx = zz, xy = 0, xz = -zx;
  l = Math.hypot(xx, xy, xz) || 1;
  xx /= l; xz /= l;
  const yx = zy * xz - zz * xy, yy = zz * xx - zx * xz, yz = zx * xy - zy * xx;
  out[0] = xx; out[1] = yx; out[2] = zx; out[3] = 0;
  out[4] = xy; out[5] = yy; out[6] = zy; out[7] = 0;
  out[8] = xz; out[9] = yz; out[10] = zz; out[11] = 0;
  out[12] = -(xx * ex + xy * ey + xz * ez);
  out[13] = -(yx * ex + yy * ey + yz * ez);
  out[14] = -(zx * ex + zy * ey + zz * ez);
  out[15] = 1;
  return out;
}

function matMul(out, a, b) {
  for (let c = 0; c < 4; c++) {
    const b0 = b[c * 4], b1 = b[c * 4 + 1], b2 = b[c * 4 + 2], b3 = b[c * 4 + 3];
    out[c * 4] = a[0] * b0 + a[4] * b1 + a[8] * b2 + a[12] * b3;
    out[c * 4 + 1] = a[1] * b0 + a[5] * b1 + a[9] * b2 + a[13] * b3;
    out[c * 4 + 2] = a[2] * b0 + a[6] * b1 + a[10] * b2 + a[14] * b3;
    out[c * 4 + 3] = a[3] * b0 + a[7] * b1 + a[11] * b2 + a[15] * b3;
  }
  return out;
}

// Pack 16 floats per hardware instance: 3x4 world row-major matrix + [tintR, tintG, tintB, windStrength]
function pushTRS(arr, cursor, tx, ty, tz, rx, ry, rz, sx, sy, sz, cr, cg, cb, wind) {
  const cx = Math.cos(rx), sxn = Math.sin(rx);
  const cy = Math.cos(ry), syn = Math.sin(ry);
  const cz = Math.cos(rz), szn = Math.sin(rz);
  // R = Ry * Rx * Rz
  const m00 = (cy * cz + syn * sxn * szn) * sx;
  const m01 = (-cy * szn + syn * sxn * cz) * sy;
  const m02 = (syn * cx) * sz;
  const m10 = (cx * szn) * sx;
  const m11 = (cx * cz) * sy;
  const m12 = (-sxn) * sz;
  const m20 = (-syn * cz + cy * sxn * szn) * sx;
  const m21 = (syn * szn + cy * sxn * cz) * sy;
  const m22 = (cy * cx) * sz;

  const base = cursor * 16;
  arr[base + 0] = m00; arr[base + 1] = m01; arr[base + 2] = m02; arr[base + 3] = tx;
  arr[base + 4] = m10; arr[base + 5] = m11; arr[base + 6] = m12; arr[base + 7] = ty;
  arr[base + 8] = m20; arr[base + 9] = m21; arr[base + 10] = m22; arr[base + 11] = tz;
  arr[base + 12] = cr; arr[base + 13] = cg; arr[base + 14] = cb; arr[base + 15] = wind;
  return cursor + 1;
}

function hexToRgb(hex) {
  const clean = (hex || "#27AE60").replace("#", "");
  const v = parseInt(clean, 16) || 0x27ae60;
  return [((v >> 16) & 255) / 255, ((v >> 8) & 255) / 255, (v & 255) / 255];
}

// --- Next-Gen GLSL ES 3.00 Shaders (100% Parity with Native C# Gles3InstancedRenderer.cs v2.0!) ---
const VS_SKY = `#version 300 es
precision highp float;
const vec2 kQuad[4] = vec2[4](vec2(-1.0, -1.0), vec2(1.0, -1.0), vec2(-1.0, 1.0), vec2(1.0, 1.0));
uniform mat4 uInvVP;
out vec3 vRay;
void main() {
  vec2 p = kQuad[gl_VertexID];
  vec4 farW = uInvVP * vec4(p, 1.0, 1.0);
  vec4 nearW = uInvVP * vec4(p, -1.0, 1.0);
  vRay = farW.xyz / max(farW.w, 1e-5) - nearW.xyz / max(nearW.w, 1e-5);
  gl_Position = vec4(p, 0.9999, 1.0);
}`;

const FS_SKY = `#version 300 es
precision highp float;
in vec3 vRay;
uniform vec3 uSkyZenith;
uniform vec3 uSkyHorizon;
uniform vec3 uSunDir;
uniform vec3 uSunColor;
out vec4 fragColor;
void main() {
  vec3 d = normalize(vRay);
  float up = clamp(d.y * 1.15 + 0.06, 0.0, 1.0);
  vec3 col = mix(uSkyHorizon, uSkyZenith, pow(up, 0.62));
  float sd = max(dot(d, normalize(uSunDir)), 0.0);
  col += uSunColor * (pow(sd, 12.0) * 0.28 + smoothstep(0.9965, 0.9994, sd) * 1.85);
  col = (col * (2.51 * col + 0.03)) / (col * (2.43 * col + 0.59) + 0.14);
  fragColor = vec4(pow(clamp(col, 0.0, 1.0), vec3(0.4545)), 1.0);
}`;

const VS_SHADOW = `#version 300 es
precision highp float;
layout(location=0) in vec3 aPos;
layout(location=3) in vec4 aCol;
layout(location=4) in vec4 iRow0;
layout(location=5) in vec4 iRow1;
layout(location=6) in vec4 iRow2;
layout(location=7) in vec4 iTintWind;
uniform mat4 uVP;
out float vAlpha;
void main() {
  vec4 p = vec4(aPos, 1.0);
  vec3 wp = vec3(dot(iRow0, p), dot(iRow1, p), dot(iRow2, p));
  vAlpha = aCol.a * iTintWind.r;
  gl_Position = uVP * vec4(wp, 1.0);
}`;

const FS_SHADOW = `#version 300 es
precision highp float;
in float vAlpha;
out vec4 fragColor;
void main() {
  fragColor = vec4(0.02, 0.05, 0.04, clamp(vAlpha * 0.56, 0.0, 0.62));
}`;

const VS_INSTANCED = `#version 300 es
precision highp float;
layout(location=0) in vec3 aPos;
layout(location=1) in vec3 aNrm;
layout(location=2) in vec2 aUV;
layout(location=3) in vec4 aCol;
layout(location=4) in vec4 iRow0;
layout(location=5) in vec4 iRow1;
layout(location=6) in vec4 iRow2;
layout(location=7) in vec4 iTintWind;

uniform mat4 uVP;
uniform float uTime;

out vec3 vNormal;
out vec3 vWorldPos;
out vec4 vColor;
out vec3 vTint;
out vec2 vUV;

void main() {
  vec4 localPos = vec4(aPos, 1.0);
  vec3 worldPos = vec3(dot(iRow0, localPos), dot(iRow1, localPos), dot(iRow2, localPos));
  float windAmp = iTintWind.w;
  if (windAmp > 0.001) {
    float h = max(0.0, aPos.y + length(aPos.xz) * 0.42);
    float gust = sin(uTime * 2.15 + iRow0.w * 0.14 + iRow2.w * 0.11);
    float flutter = cos(uTime * 4.30 + aPos.x * 2.4 + iRow2.w * 0.17);
    worldPos.x += gust * 0.052 * h * windAmp;
    worldPos.z += flutter * 0.028 * h * windAmp;
    worldPos.y -= abs(gust) * 0.012 * h * windAmp;
  }
  mat3 rotScale = mat3(
    iRow0.x, iRow1.x, iRow2.x,
    iRow0.y, iRow1.y, iRow2.y,
    iRow0.z, iRow1.z, iRow2.z
  );
  vNormal = normalize(rotScale * aNrm);
  vWorldPos = worldPos;
  vColor = aCol;
  vTint = iTintWind.rgb;
  vUV = aUV;
  gl_Position = uVP * vec4(worldPos, 1.0);
}`;

const FS_LIT = `#version 300 es
precision highp float;
in vec3 vNormal;
in vec3 vWorldPos;
in vec4 vColor;
in vec3 vTint;
in vec2 vUV;

uniform vec3 uCamPos;
uniform vec3 uSunDir;
uniform vec3 uSunColor;
uniform vec3 uSkyTop;
uniform vec3 uGroundBounce;
uniform vec3 uFogCol;
uniform float uFogDensity;
uniform float uTime;
uniform float uDetailStrength;

out vec4 fragColor;

float hash21(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

float vnoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  float a = hash21(i);
  float b = hash21(i + vec2(1.0, 0.0));
  float c = hash21(i + vec2(0.0, 1.0));
  float d = hash21(i + vec2(1.0, 1.0));
  return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

void main() {
  vec3 N = normalize(vNormal);
  vec3 L = normalize(uSunDir);
  vec3 V = normalize(uCamPos - vWorldPos);
  float dist = length(uCamPos - vWorldPos);

  vec3 effTint = mix(vec3(1.0), vTint, step(0.75, vUV.x));
  vec3 base = pow(max(vColor.rgb, vec3(0.001)), vec3(2.15)) * pow(max(effTint, vec3(0.001)), vec3(1.6));
  float ao = mix(0.22, 1.0, vColor.a);
  float gloss = vUV.y;

  if (vUV.y < 0.12 && dist < 38.0 && uDetailStrength > 0.01) {
    float fade = uDetailStrength * (1.0 - smoothstep(14.0, 38.0, dist));
    float n1 = vnoise(vWorldPos.xz * 2.6);
    float n2 = vnoise(vWorldPos.xz * 9.5);
    float micro = (n1 - 0.5) * 0.28 + (n2 - 0.5) * 0.16;
    base *= (1.0 + micro * fade);
    float hDetail = n1 * 0.65 + n2 * 0.35;
    vec3 dN = vec3(dFdx(hDetail), 0.0, dFdy(hDetail)) * 3.2 * fade;
    N = normalize(N - dN);
    gloss = mix(0.14, 0.80, clamp(vUV.x * 1.35 * n1, 0.0, 1.0));
  }

  if (vUV.y > 0.895 && vUV.y < 0.915) {
    float w1 = sin(vWorldPos.x * 1.35 + uTime * 2.2 + sin(vWorldPos.z * 1.8) * 0.8);
    float w2 = cos(vWorldPos.z * 2.65 - uTime * 1.7 + vWorldPos.x * 0.7);
    N = normalize(vec3(w1 * 0.15, 1.0, w2 * 0.17));
    float fres = pow(1.0 - max(dot(N, V), 0.0), 3.2);
    base = mix(vec3(0.012, 0.095, 0.135), uSkyTop * 0.85, clamp(fres * 0.85 + 0.12, 0.0, 1.0));
    float foam = smoothstep(3.55, 4.45, abs(vWorldPos.z + 48.0));
    base = mix(base, vec3(0.55, 0.72, 0.78), foam * 0.55);
    gloss = 0.92;
  }

  if (gloss >= 0.94) {
    vec3 hdrEm = base * 3.2;
    float fogEm = smoothstep(52.0, 190.0, dist) * 0.75;
    vec3 outEm = mix(hdrEm, uFogCol, fogEm);
    outEm = (outEm * (2.51 * outEm + 0.03)) / (outEm * (2.43 * outEm + 0.59) + 0.14);
    fragColor = vec4(pow(clamp(outEm, 0.0, 1.0), vec3(0.4545)), 1.0);
    return;
  }

  vec3 H = normalize(L + V);
  float ndl = max(dot(N, L), 0.0);
  float wrapNdl = max(dot(N, L) * 0.65 + 0.35, 0.0);
  vec3 hemi = mix(uGroundBounce, uSkyTop, clamp(N.y * 0.5 + 0.5, 0.0, 1.0));

  float isFoliage = step(0.55, gloss) * (1.0 - step(0.68, gloss));
  float sss = isFoliage * pow(clamp(dot(-V, L) * 0.5 + 0.5, 0.0, 1.0), 2.6) * 0.65;

  float shininess = mix(16.0, 110.0, clamp(gloss, 0.0, 1.0));
  float specStrength = mix(0.05, 0.95, clamp(gloss, 0.0, 1.0)) * ao;
  float spec = pow(max(dot(N, H), 0.0), shininess) * specStrength;
  float rim = pow(1.0 - max(dot(N, V), 0.0), 3.8) * 0.14 * ao;

  vec3 lit = base * (hemi * ao + uSunColor * (ndl * 1.15 + wrapNdl * 0.22 * ao + sss))
           + uSunColor * spec * 0.45
           + uSkyTop * rim;

  float fogAmt = smoothstep(48.0, 195.0, dist) * (0.82 + uFogDensity * 12.0);
  vec3 hdr = mix(lit, uFogCol, clamp(fogAmt, 0.0, 0.88));
  vec3 mapped = (hdr * (2.51 * hdr + 0.03)) / (hdr * (2.43 * hdr + 0.59) + 0.14);
  fragColor = vec4(pow(clamp(mapped, 0.0, 1.0), vec3(0.4545)), 1.0);
}`;

// --- Audio FX Synthesizer (Crisp WebAudio procedural SFX!) ---
let audioCtx = null;
function playSfx(kind) {
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === "suspended") audioCtx.resume();
    const now = audioCtx.currentTime;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    if (kind === "harvest") {
      osc.type = "triangle";
      osc.frequency.setValueAtTime(340, now);
      osc.frequency.exponentialRampToValueAtTime(110, now + 0.14);
      gain.gain.setValueAtTime(0.22, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
      osc.start(now); osc.stop(now + 0.16);
    } else if (kind === "sell") {
      osc.type = "sine";
      osc.frequency.setValueAtTime(523, now);
      osc.frequency.setValueAtTime(659, now + 0.08);
      osc.frequency.setValueAtTime(784, now + 0.16);
      gain.gain.setValueAtTime(0.2, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.36);
      osc.start(now); osc.stop(now + 0.38);
    } else if (kind === "horn") {
      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(285, now);
      osc.frequency.setValueAtTime(358, now + 0.12);
      osc.frequency.setValueAtTime(426, now + 0.24);
      gain.gain.setValueAtTime(0.14, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.42);
      osc.start(now); osc.stop(now + 0.44);
    }
  } catch {}
}

// --- Application & Engine State ---
const QUALITY_PRESETS = [
  { name: "SMOOTH", scale: 0.65, maxH: 540, lod0: 16, lod1: 38, maxDist: 102, ferns: false, detail: 0.25 },
  { name: "STD", scale: 0.85, maxH: 720, lod0: 24, lod1: 54, maxDist: 132, ferns: true, detail: 0.70 },
  { name: "ULTRA", scale: 1.0, maxH: 900, lod0: 34, lod1: 76, maxDist: 168, ferns: true, detail: 1.0 },
  { name: "MAX", scale: Math.min(window.devicePixelRatio || 1, 1.5), maxH: 1080, lod0: 46, lod1: 104, maxDist: 205, ferns: true, detail: 1.0 },
];

const state = {
  quality: 2,
  trees: generatePlantationTrees(),
  ferns: [],
  rocks: [],
  fallingFruits: [],
  particles: [],
  peers: new Map(),
  boars: [
    { id: "boar_1", x: -24, z: 54, yaw: 0 },
    { id: "boar_2", x: 30, z: 62, yaw: 0 },
  ],
  chatBubbles: new Map(),
  profile: {
    id: localStorage.getItem("nyawit_pid") || "",
    token: localStorage.getItem("nyawit_tok") || "",
    name: localStorage.getItem("nyawit_name") || "Juragan" + Math.floor(100 + Math.random() * 899),
    socialProvider: "guest",
    socialHandle: "",
    coins: 150000,
    gems: 25,
    totalKg: 0,
    allTimeScore: 0,
    weeklyPoints: 0,
    streakDay: 0,
    canClaimDaily: true,
    avatar: { hat: "hat_caping", back: "back_basket", tool: "tool_egrek", outfitHex: "#27AE60", aura: "leaf", title: "Pemanen Kebun" },
    unlocked: ["hat_caping", "back_basket", "tool_egrek"],
    claimedTiers: [],
  },
  event: { kind: "CERAH_PANEN", title: "PANEN RAYA CERAH", multiplier: 1.0, endsAt: Date.now() + 60000 },
  dailyRewards: [],
  globalLeaderboard: [],
  tournament: { weekId: "2026-W43", endsAtMs: Date.now() + 300000000, standings: [], myRank: 0, tiers: [] },
  player: {
    x: +((Math.random() - 0.5) * 9.0).toFixed(2),
    y: 0.0,
    z: +(3.0 + Math.random() * 4.5).toFixed(2),
    yaw: Math.PI,
    speed: 0,
    inTruck: false,
    cargo: 0,
    goldCargo: 0,
    maxCap: 12,
    swingTimer: 0,
    boostTimer: 0,
    walkPhase: 0,
  },
  cam: { yaw: 0.28, pitch: 0.30, dist: 8.6 },
  input: { jx: 0, jy: 0, keys: new Set() },
  net: { connected: false, pingMs: 24, ws: null },
};
window.__nyawit = { state };

// Scatter decorative ferns & boulders deterministically
{
  const rng = mulberry32(991177);
  for (let i = 0; i < 160; i++) {
    const x = (rng() - 0.5) * 190;
    const z = (rng() - 0.5) * 190;
    if (roadFactor(x, z) > 0.3 || Math.hypot(x, z + 15) < 18) continue;
    state.ferns.push({ x, y: terrainHeight(x, z) - 0.05, z, rot: rng() * 6.28, s: 0.75 + rng() * 0.55 });
  }
  for (let i = 0; i < 42; i++) {
    const x = (rng() - 0.5) * 195;
    const z = (rng() - 0.5) * 195;
    if (roadFactor(x, z) > 0.25 || Math.hypot(x, z + 15) < 20) continue;
    state.rocks.push({ x, y: terrainHeight(x, z) - 0.12, z, rot: rng() * 6.28, s: 0.7 + rng() * 0.8 });
  }
}

function showToast(txt) {
  const el = document.getElementById("toast");
  el.textContent = txt;
  el.classList.add("show");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => el.classList.remove("show"), 3100);
}

function updateHud() {
  document.getElementById("hudCoins").textContent = "Rp " + Number(state.profile.coins).toLocaleString("id-ID");
  const cap = state.player.inTruck ? 24 : 12;
  document.getElementById("hudCargo").textContent = `${state.player.cargo}/${cap}`;
  document.getElementById("hudGems").textContent = String(state.profile.gems);
  document.getElementById("eventTitle").textContent = state.event.title;
  document.getElementById("dailyDot").style.display = state.profile.canClaimDaily ? "inline-block" : "none";
  document.getElementById("btnTruck").innerHTML = state.player.inTruck ? "TURUN<br/>CANTER" : "NAIK<br/>CANTER";
}

function appendChatMessage(item) {
  const list = document.getElementById("chatList");
  const div = document.createElement("div");
  div.className = "chat-item";
  const tag = item.title ? `<span class="tag">[${item.title}]</span>` : "";
  div.innerHTML = `${tag}<b>${escapeDom(item.senderName)}:</b> ${escapeDom(item.text)}`;
  list.appendChild(div);
  while (list.children.length > 35) list.removeChild(list.firstChild);
  list.scrollTop = list.scrollHeight;
  state.chatBubbles.set(item.senderId, { text: item.text, until: performance.now() + 7000 });
}

function escapeDom(s) {
  return String(s || "").replace(/[&<>"]/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
}

// --- WebSocket Live Multiplayer Connection ---
function connectLiveServer() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const qs = new URLSearchParams({
    pid: state.profile.id,
    tok: state.profile.token,
    name: state.profile.name,
  });
  const ws = new WebSocket(`${proto}//${location.host}/ws?${qs}`);
  state.net.ws = ws;

  ws.addEventListener("open", () => {
    state.net.connected = true;
    ws.send(JSON.stringify({
      type: "hello",
      playerId: state.profile.id,
      token: state.profile.token,
      name: state.profile.name,
    }));
  });

  ws.addEventListener("message", (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    if (msg.type === "welcome") {
      Object.assign(state.profile, msg.profile);
      localStorage.setItem("nyawit_pid", state.profile.id);
      localStorage.setItem("nyawit_tok", state.profile.token);
      localStorage.setItem("nyawit_name", state.profile.name);
      if (Array.isArray(msg.trees)) {
        msg.trees.forEach((st, i) => { if (state.trees[i]) state.trees[i].state = st; });
      }
      if (msg.event) state.event = msg.event;
      state.dailyRewards = msg.dailyRewards || [];
      state.globalLeaderboard = msg.globalLeaderboard || [];
      state.tournament = msg.tournament || state.tournament;
      document.getElementById("chatList").innerHTML = "";
      (msg.chatHistory || []).forEach(appendChatMessage);
      updateHud();
    } else if (msg.type === "world") {
      const seen = new Set();
      for (const p of msg.peers) {
        if (p.id === state.profile.id) continue;
        seen.add(p.id);
        const cur = state.peers.get(p.id);
        if (!cur) {
          state.peers.set(p.id, { ...p, rx: p.x, ry: p.y, rz: p.z, ryaw: p.yaw, walk: 0 });
        } else {
          Object.assign(cur, p);
        }
      }
      for (const id of [...state.peers.keys()]) {
        if (!seen.has(id)) state.peers.delete(id);
      }
      if (msg.boars) state.boars = msg.boars;
    } else if (msg.type === "trees_delta") {
      for (const [idx, st] of msg.changes) {
        if (state.trees[idx]) state.trees[idx].state = st;
      }
    } else if (msg.type === "harvest_fx") {
      if (state.trees[msg.treeId]) state.trees[msg.treeId].state = 0;
      spawnFallingFruits(msg.x, msg.z, msg.isGold);
    } else if (msg.type === "cargo_sync") {
      state.player.cargo = msg.cargo;
      state.player.goldCargo = msg.goldCargo;
      playSfx("harvest");
      showToast(msg.isGold ? `SAWIT EMAS SULTAN! Combo x${msg.combo} (${msg.cargo}/${msg.maxCap})` : `Panen TBS Mantap! Combo x${msg.combo} (${msg.cargo}/${msg.maxCap})`);
      updateHud();
    } else if (msg.type === "sell_receipt") {
      state.player.cargo = 0;
      state.player.goldCargo = 0;
      Object.assign(state.profile, msg.profile);
      state.globalLeaderboard = msg.globalLeaderboard || state.globalLeaderboard;
      state.tournament = msg.tournament || state.tournament;
      playSfx("sell");
      showToast(`SETOR PKS SUKSES! +Rp ${Number(msg.rupiahEarned).toLocaleString("id-ID")} · +${msg.tourneyPts} Poin Turnamen!`);
      updateHud();
    } else if (msg.type === "chat") {
      appendChatMessage(msg);
    } else if (msg.type === "system_notice") {
      appendChatMessage({ senderId: "sys", senderName: "MANDOR PKS", title: "LIVE", text: msg.text });
    } else if (msg.type === "event") {
      state.event = msg.event;
      showToast(`EVENT DUNIA: ${msg.event.title}`);
      updateHud();
    } else if (msg.type === "profile_sync") {
      Object.assign(state.profile, msg.profile);
      localStorage.setItem("nyawit_name", state.profile.name);
      updateHud();
    } else if (msg.type === "daily_claimed") {
      Object.assign(state.profile, msg.profile);
      playSfx("sell");
      showToast(`Reward Hari ${msg.day} Diklaim! +Rp ${Number(msg.reward.coins).toLocaleString("id-ID")} & +${msg.reward.gems} Permata!`);
      updateHud();
      openDailyModal();
    } else if (msg.type === "tournament_claimed") {
      Object.assign(state.profile, msg.profile);
      state.tournament = msg.tournament;
      playSfx("sell");
      showToast(`HADIAH EKSKLUSIF TURNAMEN TERBUKA: ${msg.tier.label}!`);
      updateHud();
      openTourneyModal();
    } else if (msg.type === "social_linked") {
      Object.assign(state.profile, msg.profile);
      localStorage.setItem("nyawit_name", state.profile.name);
      playSfx("sell");
      showToast(`Akun ${state.profile.socialProvider.toUpperCase()} Terhubung! Bonus +30 Permata!`);
      updateHud();
      openSocialModal();
    } else if (msg.type === "boards") {
      state.globalLeaderboard = msg.globalLeaderboard || [];
      state.tournament = msg.tournament || state.tournament;
    } else if (msg.type === "pong") {
      state.net.pingMs = Math.max(8, Math.round(Date.now() - msg.clientTs));
    } else if (msg.type === "toast") {
      showToast(msg.text);
    }
  });

  ws.addEventListener("close", () => {
    state.net.connected = false;
    setTimeout(connectLiveServer, 2200);
  });
}

function sendNet(obj) {
  if (state.net.ws && state.net.ws.readyState === WebSocket.OPEN) {
    state.net.ws.send(JSON.stringify(obj));
  }
}

function spawnFallingFruits(x, z, isGold) {
  const gy = terrainHeight(x, z);
  for (let i = 0; i < 3; i++) {
    state.fallingFruits.push({
      x: x + (Math.random() - 0.5) * 1.1,
      y: gy + 5.8,
      z: z + (Math.random() - 0.5) * 1.1,
      vx: (Math.random() - 0.5) * 2.4,
      vy: 1.2 + Math.random() * 1.5,
      vz: (Math.random() - 0.5) * 2.4,
      rot: Math.random() * 6.28,
      groundY: gy + 0.28,
      isGold,
      life: 2.2,
    });
  }
}

// --- WebGL2 GPU Initialization & Binary .npak Uploader ---
const canvas = document.getElementById("gl");
const gl = canvas.getContext("webgl2", { antialias: true, powerPreference: "high-performance", alpha: false });
const labelsCanvas = document.getElementById("labels2d");
const lctx = labelsCanvas.getContext("2d");
const minimapCanvas = document.getElementById("minimap");
const mctx = minimapCanvas.getContext("2d");

function compileShader(type, src) {
  const sh = gl.createShader(type);
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh));
  return sh;
}

function buildProgram(vsSrc, fsSrc) {
  const p = gl.createProgram();
  gl.attachShader(p, compileShader(gl.VERTEX_SHADER, vsSrc));
  gl.attachShader(p, compileShader(gl.FRAGMENT_SHADER, fsSrc));
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
  return p;
}

const skyProg = buildProgram(VS_SKY, FS_SKY);
const skyVao = gl.createVertexArray();
const uSky = {
  invVp: gl.getUniformLocation(skyProg, "uInvVP"),
  zenith: gl.getUniformLocation(skyProg, "uSkyZenith"),
  horizon: gl.getUniformLocation(skyProg, "uSkyHorizon"),
  sunDir: gl.getUniformLocation(skyProg, "uSunDir"),
  sunColor: gl.getUniformLocation(skyProg, "uSunColor"),
};

const shadowProg = buildProgram(VS_SHADOW, FS_SHADOW);
const uShadowVp = gl.getUniformLocation(shadowProg, "uVP");

const prog = buildProgram(VS_INSTANCED, FS_LIT);
const uLoc = {
  vp: gl.getUniformLocation(prog, "uVP"),
  time: gl.getUniformLocation(prog, "uTime"),
  camPos: gl.getUniformLocation(prog, "uCamPos"),
  sunDir: gl.getUniformLocation(prog, "uSunDir"),
  sunColor: gl.getUniformLocation(prog, "uSunColor"),
  skyTop: gl.getUniformLocation(prog, "uSkyTop"),
  groundBounce: gl.getUniformLocation(prog, "uGroundBounce"),
  fogCol: gl.getUniformLocation(prog, "uFogCol"),
  fogDensity: gl.getUniformLocation(prog, "uFogDensity"),
  detailStrength: gl.getUniformLocation(prog, "uDetailStrength"),
};

const MAX_INSTANCES = 1024;
const sharedInstanceBuffer = gl.createBuffer();
gl.bindBuffer(gl.ARRAY_BUFFER, sharedInstanceBuffer);
gl.bufferData(gl.ARRAY_BUFFER, MAX_INSTANCES * 64, gl.DYNAMIC_DRAW);
const scratchInst = new Float32Array(MAX_INSTANCES * 16);
const shadowScratch = new Float32Array(MAX_INSTANCES * 16);

const gpuMeshes = new Map();

function createGpuVao(vertexBytes, indexBytes, indexCount) {
  const vao = gl.createVertexArray();
  gl.bindVertexArray(vao);

  const vbo = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
  gl.bufferData(gl.ARRAY_BUFFER, vertexBytes, gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 36, 0);
  gl.enableVertexAttribArray(1);
  gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 36, 12);
  gl.enableVertexAttribArray(2);
  gl.vertexAttribPointer(2, 2, gl.FLOAT, false, 36, 24);
  gl.enableVertexAttribArray(3);
  gl.vertexAttribPointer(3, 4, gl.UNSIGNED_BYTE, true, 36, 32);

  gl.bindBuffer(gl.ARRAY_BUFFER, sharedInstanceBuffer);
  for (let attr = 0; attr < 4; attr++) {
    const loc = 4 + attr;
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 4, gl.FLOAT, false, 64, attr * 16);
    gl.vertexAttribDivisor(loc, 1);
  }

  const ibo = gl.createBuffer();
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ibo);
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, indexBytes, gl.STATIC_DRAW);

  gl.bindVertexArray(null);
  return { vao, count: indexCount };
}

async function loadNpakGpuArchive() {
  const resp = await fetch("/assets/nyawit_models.npak");
  const buf = await resp.arrayBuffer();
  const dv = new DataView(buf);
  let off = 8;
  const meshCount = dv.getUint32(off, true);
  off += 4;
  const dec = new TextDecoder();

  for (let m = 0; m < meshCount; m++) {
    const nlen = dv.getUint8(off);
    const radius = dv.getFloat32(off + 1, true);
    const lodCount = dv.getUint8(off + 29);
    off += 30;
    const name = dec.decode(new Uint8Array(buf, off, nlen));
    off += nlen;
    const lods = [];
    for (let l = 0; l < lodCount; l++) {
      const vcnt = dv.getUint32(off, true);
      const icnt = dv.getUint32(off + 4, true);
      off += 8;
      const vBytes = new Uint8Array(buf, off, vcnt * 36);
      off += vcnt * 36;
      const iBytes = new Uint8Array(buf, off, icnt * 2);
      off += icnt * 2;
      lods.push(createGpuVao(vBytes, iBytes, icnt));
    }
    gpuMeshes.set(name, { name, radius, lods });
  }
}

function buildTerrainAndWaterMeshes() {
  // Build high-density 136x136 multi-biome splatted 3D terrain + 64-seg canal water + soft contact shadow disc!
  const N = 136;
  const span = 224.0;
  const vbuf = new ArrayBuffer(N * N * 36);
  const dv = new DataView(vbuf);
  let vo = 0;
  for (let zi = 0; zi < N; zi++) {
    const z = -span * 0.5 + (zi / (N - 1)) * span;
    for (let xi = 0; xi < N; xi++) {
      const x = -span * 0.5 + (xi / (N - 1)) * span;
      const h = terrainHeight(x, z);
      const hx = terrainHeight(x + 0.9, z) - terrainHeight(x - 0.9, z);
      const hz = terrainHeight(x, z + 0.9) - terrainHeight(x, z - 0.9);
      let nx = -hx, ny = 1.8, nz = -hz;
      const nl = Math.hypot(nx, ny, nz);
      nx /= nl; ny /= nl; nz /= nl;

      const rd = roadFactor(x, z);
      const md = mudFactor(x, z);
      const yard = Math.max(0, Math.min(1, 1.0 - (Math.hypot(x, z + 15.0) - 14.0) / 5.0));
      const dCanal = Math.max(0, Math.min(1, 1.0 - Math.abs(z - CANAL_Z) / 6.2));
      const lushWave = 0.5 + 0.5 * Math.sin(x * 0.14 + Math.cos(z * 0.13) * 1.6);

      let r = 42 + lushWave * 28, g = 112 + lushWave * 38, b = 36 + lushWave * 18;
      r = r * (1 - md) + 84 * md; g = g * (1 - md) + 58 * md; b = b * (1 - md) + 38 * md;
      r = r * (1 - rd) + 172 * rd; g = g * (1 - rd) + 122 * rd; b = b * (1 - rd) + 78 * rd;
      r = r * (1 - dCanal * 0.65) + 96 * (dCanal * 0.65);
      g = g * (1 - dCanal * 0.65) + 84 * (dCanal * 0.65);
      b = b * (1 - dCanal * 0.65) + 56 * (dCanal * 0.65);
      r = r * (1 - yard) + 128 * yard; g = g * (1 - yard) + 134 * yard; b = b * (1 - yard) + 142 * yard;
      const ao = Math.max(140, Math.min(255, 250 - dCanal * 48 - md * 18));

      dv.setFloat32(vo, x, true); dv.setFloat32(vo + 4, h, true); dv.setFloat32(vo + 8, z, true);
      dv.setFloat32(vo + 12, nx, true); dv.setFloat32(vo + 16, ny, true); dv.setFloat32(vo + 20, nz, true);
      dv.setFloat32(vo + 24, Math.min(0.7, md * 0.7 + rd * 0.25), true);
      dv.setFloat32(vo + 28, 0.05, true);
      dv.setUint8(vo + 32, Math.min(255, r));
      dv.setUint8(vo + 33, Math.min(255, g));
      dv.setUint8(vo + 34, Math.min(255, b));
      dv.setUint8(vo + 35, ao);
      vo += 36;
    }
  }
  const idx = new Uint16Array((N - 1) * (N - 1) * 6);
  let io = 0;
  for (let zi = 0; zi < N - 1; zi++) {
    for (let xi = 0; xi < N - 1; xi++) {
      const i0 = zi * N + xi, i1 = i0 + 1, i2 = i0 + N, i3 = i2 + 1;
      idx[io++] = i0; idx[io++] = i2; idx[io++] = i1;
      idx[io++] = i1; idx[io++] = i2; idx[io++] = i3;
    }
  }
  gpuMeshes.set("_terrain", { name: "_terrain", radius: 200, lods: [createGpuVao(new Uint8Array(vbuf), new Uint8Array(idx.buffer), idx.length)] });

  const segX = 64;
  const wv = new ArrayBuffer((segX + 1) * 2 * 36);
  const wdv = new DataView(wv);
  let wo = 0;
  for (let i = 0; i <= segX; i++) {
    const cx = -112 + (i / segX) * 224;
    for (let s = 0; s < 2; s++) {
      wdv.setFloat32(wo, cx, true); wdv.setFloat32(wo + 4, -0.78, true); wdv.setFloat32(wo + 8, CANAL_Z + (s === 0 ? -4.5 : 4.5), true);
      wdv.setFloat32(wo + 12, 0, true); wdv.setFloat32(wo + 16, 1, true); wdv.setFloat32(wo + 20, 0, true);
      wdv.setFloat32(wo + 24, s === 0 ? 0.0 : 0.4, true); wdv.setFloat32(wo + 28, 0.905, true);
      wdv.setUint8(wo + 32, 24); wdv.setUint8(wo + 33, 128); wdv.setUint8(wo + 34, 146); wdv.setUint8(wo + 35, 255);
      wo += 36;
    }
  }
  const widx = new Uint16Array(segX * 6);
  let wio = 0;
  for (let i = 0; i < segX; i++) {
    const b0 = i * 2, b1 = i * 2 + 1, b2 = i * 2 + 2, b3 = i * 2 + 3;
    widx[wio++] = b0; widx[wio++] = b1; widx[wio++] = b2;
    widx[wio++] = b2; widx[wio++] = b1; widx[wio++] = b3;
  }
  gpuMeshes.set("_water", { name: "_water", radius: 150, lods: [createGpuVao(new Uint8Array(wv), new Uint8Array(widx.buffer), widx.length)] });

  const sSeg = 16;
  const sv = new ArrayBuffer((sSeg + 1) * 36);
  const sdv = new DataView(sv);
  const putShadowVert = (vi, sx, sz, alpha) => {
    const o = vi * 36;
    sdv.setFloat32(o, sx, true); sdv.setFloat32(o + 4, 0.045, true); sdv.setFloat32(o + 8, sz, true);
    sdv.setFloat32(o + 12, 0, true); sdv.setFloat32(o + 16, 1, true); sdv.setFloat32(o + 20, 0, true);
    sdv.setFloat32(o + 24, 0, true); sdv.setFloat32(o + 28, 0, true);
    sdv.setUint8(o + 32, 8); sdv.setUint8(o + 33, 16); sdv.setUint8(o + 34, 12); sdv.setUint8(o + 35, alpha);
  };
  putShadowVert(0, 0, 0, 168);
  for (let i = 0; i < sSeg; i++) {
    const a = (i * Math.PI * 2) / sSeg;
    putShadowVert(1 + i, Math.cos(a), Math.sin(a), 0);
  }
  const sidx = new Uint16Array(sSeg * 3);
  for (let i = 0; i < sSeg; i++) {
    sidx[i * 3] = 0; sidx[i * 3 + 1] = 1 + ((i + 1) % sSeg); sidx[i * 3 + 2] = 1 + i;
  }
  gpuMeshes.set("_shadow", { name: "_shadow", radius: 4, lods: [createGpuVao(new Uint8Array(sv), new Uint8Array(sidx.buffer), sidx.length)] });
}

let frameDrawCalls = 0;
function drawMeshBatch(meshName, lodIdx, count) {
  if (count <= 0) return;
  const entry = gpuMeshes.get(meshName);
  if (!entry) return;
  const gpuLod = entry.lods[Math.min(lodIdx, entry.lods.length - 1)];
  gl.bindVertexArray(gpuLod.vao);
  gl.bindBuffer(gl.ARRAY_BUFFER, sharedInstanceBuffer);
  gl.bufferSubData(gl.ARRAY_BUFFER, 0, scratchInst.subarray(0, count * 16));
  gl.drawElementsInstanced(gl.TRIANGLES, gpuLod.count, gl.UNSIGNED_SHORT, 0, count);
  frameDrawCalls++;
}

// Assemble any local or remote character or Canter vehicle cleanly into per-part batch buckets!
const partBuckets = new Map();
function resetBuckets() {
  for (const b of partBuckets.values()) b.length = 0;
}
function enqueuePart(meshName, tx, ty, tz, rx, ry, rz, s, cr = 1, cg = 1, cb = 1, wind = 0) {
  let list = partBuckets.get(meshName);
  if (!list) { list = []; partBuckets.set(meshName, list); }
  list.push(tx, ty, tz, rx, ry, rz, s, cr, cg, cb, wind);
}
function flushBuckets(lodIdx = 0) {
  for (const [meshName, list] of partBuckets.entries()) {
    const total = list.length / 11;
    if (!total) continue;
    let cursor = 0;
    for (let i = 0; i < total && cursor < MAX_INSTANCES; i++) {
      const b = i * 11;
      cursor = pushTRS(scratchInst, cursor, list[b], list[b + 1], list[b + 2], list[b + 3], list[b + 4], list[b + 5], list[b + 6], list[b + 6], list[b + 6], list[b + 7], list[b + 8], list[b + 9], list[b + 10]);
    }
    drawMeshBatch(meshName, lodIdx, cursor);
  }
}

function stageActorVisual(x, y, z, yaw, walkPhase, swingT, inTruck, cargo, av) {
  const [cr, cg, cb] = hexToRgb(av?.outfitHex || "#27AE60");
  if (inTruck) {
    enqueuePart("canter_truck_body", x, y + 0.04, z, 0, yaw, 0, 1.0, cr * 0.35 + 0.65, cg * 0.35 + 0.60, cb * 0.25 + 0.12, 0);
    const spin = walkPhase * 1.4;
    const sinY = Math.sin(yaw), cosY = Math.cos(yaw);
    for (const [lx, lz] of [[-0.90, 1.62], [0.90, 1.62], [-0.90, -1.18], [0.90, -1.18]]) {
      const wx = x + lx * cosY + lz * sinY;
      const wz = z - lx * sinY + lz * cosY;
      enqueuePart("truck_wheel", wx, y + 0.50, wz, spin, yaw, 0, 1.0);
    }
    if (cargo > 0) {
      const heapScale = 0.55 + Math.min(1.0, cargo / 20) * 0.50;
      enqueuePart("truck_cargo_heap", x, y + 0.84, z, 0, yaw, 0, heapScale);
    }
    // Driver visible inside cab!
    enqueuePart("char_torso_head", x - 0.35 * Math.cos(yaw) + 1.55 * Math.sin(yaw), y + 0.92, z + 0.35 * Math.sin(yaw) + 1.55 * Math.cos(yaw), 0, yaw, 0, 0.88, cr, cg, cb);
    return;
  }

  const stride = Math.sin(walkPhase) * 0.55;
  const bob = Math.abs(Math.cos(walkPhase)) * 0.045;
  const sinY = Math.sin(yaw), cosY = Math.cos(yaw);
  const localToWorld = (lx, ly, lz) => [x + lx * cosY + lz * sinY, y + ly + bob, z - lx * sinY + lz * cosY];

  const [tx, ty, tz] = localToWorld(0, 0.92, 0);
  enqueuePart("char_torso_head", tx, ty, tz, 0, yaw, 0, 1.0, cr, cg, cb);

  const [llx, lly, llz] = localToWorld(-0.11, 0.92, 0);
  const [rlx, rly, rlz] = localToWorld(0.11, 0.92, 0);
  enqueuePart("char_leg", llx, lly, llz, stride, yaw, 0, 1.0);
  enqueuePart("char_leg", rlx, rly, rlz, -stride, yaw, 0, 1.0);

  const armSwingR = swingT > 0 ? -1.45 + Math.sin((1.0 - swingT) * Math.PI) * 1.9 : -stride * 0.7 - 0.35;
  const [lax, lay, laz] = localToWorld(-0.26, 1.40, 0);
  const [rax, ray, raz] = localToWorld(0.26, 1.40, 0);
  enqueuePart("char_arm", lax, lay, laz, stride * 0.7 - 0.25, yaw, 0, 1.0, cr, cg, cb);
  enqueuePart("char_arm", rax, ray, raz, armSwingR, yaw, 0, 1.0, cr, cg, cb);

  const hatKey = av?.hat || "hat_caping";
  const [hx, hy, hz] = localToWorld(0, 1.85, 0.02);
  enqueuePart(hatKey, hx, hy, hz, 0, yaw, 0, 1.0);

  const backKey = av?.back || "back_basket";
  const [bx, by, bz] = localToWorld(0, 1.28, -0.14);
  enqueuePart(backKey, bx, by, bz, 0, yaw, 0, 1.0, 1, 1, 1, backKey === "back_cape" ? 0.6 : 0.2);

  const toolKey = av?.tool || "tool_egrek";
  const [wx, wy, wz] = localToWorld(0.30, 1.08, 0.28);
  enqueuePart(toolKey, wx, wy, wz, 0.28 + (swingT > 0 ? Math.sin(swingT * Math.PI) * 1.15 : 0), yaw, 0, 1.0);
}

const mInvVP = new Float32Array(16);
function matInvert4(out, m) {
  const inv = mInvVP;
  inv[0] = m[5]*m[10]*m[15] - m[5]*m[11]*m[14] - m[9]*m[6]*m[15] + m[9]*m[7]*m[14] + m[13]*m[6]*m[11] - m[13]*m[7]*m[10];
  inv[4] = -m[4]*m[10]*m[15] + m[4]*m[11]*m[14] + m[8]*m[6]*m[15] - m[8]*m[7]*m[14] - m[12]*m[6]*m[11] + m[12]*m[7]*m[10];
  inv[8] = m[4]*m[9]*m[15] - m[4]*m[11]*m[13] - m[8]*m[5]*m[15] + m[8]*m[7]*m[13] + m[12]*m[5]*m[11] - m[12]*m[7]*m[9];
  inv[12] = -m[4]*m[9]*m[14] + m[4]*m[10]*m[13] + m[8]*m[5]*m[14] - m[8]*m[6]*m[13] - m[12]*m[5]*m[10] + m[12]*m[6]*m[9];
  inv[1] = -m[1]*m[10]*m[15] + m[1]*m[11]*m[14] + m[9]*m[2]*m[15] - m[9]*m[3]*m[14] - m[13]*m[2]*m[11] + m[13]*m[3]*m[10];
  inv[5] = m[0]*m[10]*m[15] - m[0]*m[11]*m[14] - m[8]*m[2]*m[15] + m[8]*m[3]*m[14] + m[12]*m[2]*m[11] - m[12]*m[3]*m[10];
  inv[9] = -m[0]*m[9]*m[15] + m[0]*m[11]*m[13] + m[8]*m[1]*m[15] - m[8]*m[3]*m[13] - m[12]*m[1]*m[11] + m[12]*m[3]*m[9];
  inv[13] = m[0]*m[9]*m[14] - m[0]*m[10]*m[13] - m[8]*m[1]*m[14] + m[8]*m[2]*m[13] + m[12]*m[1]*m[10] - m[12]*m[2]*m[9];
  inv[2] = m[1]*m[6]*m[15] - m[1]*m[7]*m[14] - m[5]*m[2]*m[15] + m[5]*m[3]*m[14] + m[13]*m[2]*m[7] - m[13]*m[3]*m[6];
  inv[6] = -m[0]*m[6]*m[15] + m[0]*m[7]*m[14] + m[4]*m[2]*m[15] - m[4]*m[3]*m[14] - m[12]*m[2]*m[7] + m[12]*m[3]*m[6];
  inv[10] = m[0]*m[5]*m[15] - m[0]*m[7]*m[13] - m[4]*m[1]*m[15] + m[4]*m[3]*m[13] + m[12]*m[1]*m[7] - m[12]*m[3]*m[5];
  inv[14] = -m[0]*m[5]*m[14] + m[0]*m[6]*m[13] + m[4]*m[1]*m[14] - m[4]*m[2]*m[13] - m[12]*m[1]*m[6] + m[12]*m[2]*m[5];
  inv[3] = -m[1]*m[6]*m[11] + m[1]*m[7]*m[10] + m[5]*m[2]*m[11] - m[5]*m[3]*m[10] - m[9]*m[2]*m[7] + m[9]*m[3]*m[6];
  inv[7] = m[0]*m[6]*m[11] - m[0]*m[7]*m[10] - m[4]*m[2]*m[11] + m[4]*m[3]*m[10] + m[8]*m[2]*m[7] - m[8]*m[3]*m[6];
  inv[11] = -m[0]*m[5]*m[11] + m[0]*m[7]*m[10] + m[4]*m[1]*m[11] - m[4]*m[3]*m[10] - m[8]*m[1]*m[7] + m[8]*m[3]*m[5];
  inv[15] = m[0]*m[5]*m[10] - m[0]*m[6]*m[9] - m[4]*m[1]*m[10] + m[4]*m[2]*m[9] + m[8]*m[1]*m[6] - m[8]*m[2]*m[5];
  const det = m[0]*inv[0] + m[1]*inv[4] + m[2]*inv[8] + m[3]*inv[12];
  if (Math.abs(det) > 1e-8) {
    const id = 1.0 / det;
    for (let i = 0; i < 16; i++) out[i] = inv[i] * id;
  }
  return out;
}
const mProj = new Float32Array(16);
const mView = new Float32Array(16);
const mVP = new Float32Array(16);
const labelAnchors = [];

let fpsAcc = 0, fpsFrames = 0, shownFps = 60, lastNetStateSent = 0;

function nearestHarvestableTree(maxDist = 6.2) {
  let best = null, bestD = maxDist;
  for (const t of state.trees) {
    if (t.state === 0) continue;
    const d = Math.hypot(t.x - state.player.x, t.z - state.player.z);
    if (d < bestD) { bestD = d; best = t; }
  }
  return best;
}

function triggerHarvestAction() {
  state.player.swingTimer = 1.0;
  const nearTree = nearestHarvestableTree(7.5);
  if (!nearTree) {
    playSfx("harvest");
    showToast("Dekati pohon sawit yang berbuah merah / emas lalu tekan EGREK!");
    return;
  }
  if (state.net.connected) {
    sendNet({ type: "harvest", treeId: nearTree.id });
  } else {
    const isGold = nearTree.state === 2;
    nearTree.state = 0;
    spawnFallingFruits(nearTree.x, nearTree.z, isGold);
    state.player.cargo = Math.min(state.player.inTruck ? 24 : 12, state.player.cargo + (isGold ? 3 : 2));
    playSfx("harvest");
    updateHud();
  }
}

function triggerSellAction() {
  const dRam = Math.hypot(RAM_POS.x - state.player.x, RAM_POS.z - state.player.z);
  if (state.player.cargo <= 0) {
    showToast("Panen buah sawit TBS dulu sebelum setor ke Pabrik PKS!");
    return;
  }
  if (dRam > 15.0) {
    showToast(`Arahkan Truk Canter ke Timbangan RAM PKS (${Math.round(dRam)}m di tengah peta)!`);
    return;
  }
  sendNet({ type: "sell" });
}

function projectToScreen(wx, wy, wz, w, h) {
  const x = mVP[0] * wx + mVP[4] * wy + mVP[8] * wz + mVP[12];
  const y = mVP[1] * wx + mVP[5] * wy + mVP[9] * wz + mVP[13];
  const ww = mVP[3] * wx + mVP[7] * wy + mVP[11] * wz + mVP[15];
  if (ww <= 0.1) return null;
  return [(x / ww * 0.5 + 0.5) * w, (0.5 - y / ww * 0.5) * h];
}

let prevTime = performance.now();
function frame(nowMs) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.05, Math.max(0.001, (nowMs - prevTime) / 1000));
  prevTime = nowMs;

  const q = QUALITY_PRESETS[state.quality];
  const capScale = Math.min(q.scale, (q.maxH || 1080) / Math.max(1, window.innerHeight));
  const targetW = Math.max(320, Math.floor(window.innerWidth * capScale));
  const targetH = Math.max(200, Math.floor(window.innerHeight * capScale));
  if (canvas.width !== targetW || canvas.height !== targetH) {
    canvas.width = targetW;
    canvas.height = targetH;
  }
  if (labelsCanvas.width !== window.innerWidth || labelsCanvas.height !== window.innerHeight) {
    labelsCanvas.width = window.innerWidth;
    labelsCanvas.height = window.innerHeight;
  }

  // 1. Local Player & Vehicle Physics Update
  const keys = state.input.keys;
  let ix = state.input.jx + (keys.has("KeyD") || keys.has("ArrowRight") ? 1 : 0) - (keys.has("KeyA") || keys.has("ArrowLeft") ? 1 : 0);
  let iz = state.input.jy + (keys.has("KeyW") || keys.has("ArrowUp") ? 1 : 0) - (keys.has("KeyS") || keys.has("ArrowDown") ? 1 : 0);
  const ilen = Math.hypot(ix, iz);
  if (ilen > 1) { ix /= ilen; iz /= ilen; }

  const p = state.player;
  if (p.boostTimer > 0) p.boostTimer = Math.max(0, p.boostTimer - dt);
  if (p.swingTimer > 0) p.swingTimer = Math.max(0, p.swingTimer - dt * 2.8);

  if (ilen > 0.05) {
    const camSin = Math.sin(state.cam.yaw), camCos = Math.cos(state.cam.yaw);
    const moveX = ix * camCos - iz * camSin;
    const moveZ = -ix * camSin - iz * camCos;
    const targetYaw = Math.atan2(moveX, moveZ);
    let diff = targetYaw - p.yaw;
    while (diff > Math.PI) diff -= Math.PI * 2;
    while (diff < -Math.PI) diff += Math.PI * 2;
    p.yaw += diff * Math.min(1, dt * (p.inTruck ? 4.5 : 10.5));

    const mud = mudFactor(p.x, p.z);
    const baseSpd = p.inTruck ? (p.boostTimer > 0 ? 22.5 : 15.2) : (p.boostTimer > 0 ? 9.5 : 6.8);
    const spd = baseSpd * (1.0 - mud * (p.boostTimer > 0 ? 0.08 : 0.30)) * Math.min(1, ilen);
    p.x = Math.max(-102, Math.min(102, p.x + Math.sin(p.yaw) * spd * dt));
    p.z = Math.max(-102, Math.min(102, p.z + Math.cos(p.yaw) * spd * dt));
    p.walkPhase += dt * (p.inTruck ? spd * 0.9 : spd * 1.65);
  }
  p.y = surfaceHeight(p.x, p.z);

  // Auto-prompt / smooth sell check on RAM platform
  if (p.cargo > 0 && Math.hypot(RAM_POS.x - p.x, RAM_POS.z - p.z) < 5.2 && (!p._autoSellCool || nowMs - p._autoSellCool > 2500)) {
    p._autoSellCool = nowMs;
    sendNet({ type: "sell" });
  }

  // Send compact network state at 12 Hz
  if (nowMs - lastNetStateSent > 85) {
    lastNetStateSent = nowMs;
    sendNet({
      type: "state",
      x: +p.x.toFixed(2),
      y: +p.y.toFixed(2),
      z: +p.z.toFixed(2),
      yaw: +p.yaw.toFixed(3),
      anim: p.swingTimer > 0 ? 2 : (ilen > 0.05 ? 1 : 0),
      inTruck: p.inTruck,
    });
  }

  // Smooth remote peer interpolation at 60-120 FPS!
  for (const peer of state.peers.values()) {
    const k = Math.min(1, dt * 9.5);
    const dx = peer.x - peer.rx, dz = peer.z - peer.rz;
    peer.rx += dx * k;
    peer.rz += dz * k;
    peer.ry = surfaceHeight(peer.rx, peer.rz);
    let dyaw = peer.yaw - peer.ryaw;
    while (dyaw > Math.PI) dyaw -= Math.PI * 2;
    while (dyaw < -Math.PI) dyaw += Math.PI * 2;
    peer.ryaw += dyaw * k;
    if (Math.hypot(dx, dz) > 0.03) peer.walk += dt * 9.0;
  }

  // Falling TBS physics
  for (let i = state.fallingFruits.length - 1; i >= 0; i--) {
    const f = state.fallingFruits[i];
    f.vy -= 15.5 * dt;
    f.x += f.vx * dt;
    f.y += f.vy * dt;
    f.z += f.vz * dt;
    f.rot += dt * 4.0;
    if (f.y < f.groundY) {
      f.y = f.groundY;
      f.vy = Math.abs(f.vy) * 0.35;
      f.vx *= 0.6;
      f.vz *= 0.6;
    }
    f.life -= dt;
    if (f.life <= 0) state.fallingFruits.splice(i, 1);
  }

  // 2. Camera Setup (Free-Fire Third-Person Shoulder/Orbit Camera!)
  const camDist = p.inTruck ? 11.8 : state.cam.dist;
  const eyeX = p.x + Math.sin(state.cam.yaw) * Math.cos(state.cam.pitch) * camDist;
  const eyeZ = p.z + Math.cos(state.cam.yaw) * Math.cos(state.cam.pitch) * camDist;
  const eyeY = Math.max(surfaceHeight(eyeX, eyeZ) + 1.2, p.y + 1.7 + Math.sin(state.cam.pitch) * camDist);

  matPersp(mProj, 50 * Math.PI / 180, canvas.width / canvas.height, 0.35, 290.0);
  matLookAt(mView, eyeX, eyeY, eyeZ, p.x, p.y + (p.inTruck ? 1.85 : 1.55), p.z);
  matMul(mVP, mProj, mView);

  // 3. Hardware-Instanced OpenGL ES 3.0 / WebGL2 Next-Gen HD Render Pass
  frameDrawCalls = 0;
  const storm = state.event.kind === "HUJAN_BADAI";
  const goldRush = state.event.kind === "DEMAM_SAWIT_EMAS";
  matInvert4(mInvVP, mVP);

  gl.viewport(0, 0, canvas.width, canvas.height);
  gl.clearColor(0.24, 0.56, 0.86, 1.0);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  gl.cullFace(gl.BACK);

  // Pass 0: Atmospheric Sky Gradient + Solar Disc Halo (1 ultra-fast draw call!)
  gl.disable(gl.DEPTH_TEST);
  gl.depthMask(false);
  gl.disable(gl.CULL_FACE);
  gl.useProgram(skyProg);
  gl.uniformMatrix4fv(uSky.invVp, false, mInvVP);
  gl.uniform3f(uSky.sunDir, 0.48, 0.72, 0.44);
  if (storm) {
    gl.uniform3f(uSky.zenith, 0.03, 0.06, 0.13);
    gl.uniform3f(uSky.horizon, 0.11, 0.16, 0.24);
    gl.uniform3f(uSky.sunColor, 0.28, 0.34, 0.48);
  } else if (goldRush) {
    gl.uniform3f(uSky.zenith, 0.05, 0.16, 0.46);
    gl.uniform3f(uSky.horizon, 0.72, 0.42, 0.14);
    gl.uniform3f(uSky.sunColor, 1.55, 0.95, 0.35);
  } else {
    gl.uniform3f(uSky.zenith, 0.035, 0.17, 0.58);
    gl.uniform3f(uSky.horizon, 0.34, 0.62, 0.88);
    gl.uniform3f(uSky.sunColor, 1.45, 1.25, 0.86);
  }
  gl.bindVertexArray(skyVao);
  gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  frameDrawCalls++;

  gl.enable(gl.DEPTH_TEST);
  gl.depthMask(true);
  gl.enable(gl.CULL_FACE);

  gl.useProgram(prog);
  gl.uniformMatrix4fv(uLoc.vp, false, mVP);
  gl.uniform1f(uLoc.time, nowMs * 0.001);
  gl.uniform3f(uLoc.camPos, eyeX, eyeY, eyeZ);
  gl.uniform3f(uLoc.sunDir, 0.48, 0.72, 0.44);
  gl.uniform1f(uLoc.detailStrength, q.detail);
  if (storm) {
    gl.uniform3f(uLoc.sunColor, 0.62, 0.72, 0.95);
    gl.uniform3f(uLoc.skyTop, 0.14, 0.20, 0.32);
    gl.uniform3f(uLoc.groundBounce, 0.05, 0.07, 0.05);
    gl.uniform3f(uLoc.fogCol, 0.11, 0.16, 0.24);
    gl.uniform1f(uLoc.fogDensity, 0.0090);
  } else if (goldRush) {
    gl.uniform3f(uLoc.sunColor, 2.35, 1.55, 0.72);
    gl.uniform3f(uLoc.skyTop, 0.42, 0.30, 0.22);
    gl.uniform3f(uLoc.groundBounce, 0.14, 0.10, 0.05);
    gl.uniform3f(uLoc.fogCol, 0.62, 0.38, 0.14);
    gl.uniform1f(uLoc.fogDensity, 0.0040);
  } else {
    gl.uniform3f(uLoc.sunColor, 2.15, 1.92, 1.48);
    gl.uniform3f(uLoc.skyTop, 0.26, 0.46, 0.76);
    gl.uniform3f(uLoc.groundBounce, 0.09, 0.14, 0.06);
    gl.uniform3f(uLoc.fogCol, 0.34, 0.60, 0.86);
    gl.uniform1f(uLoc.fogDensity, 0.0035);
  }

  if (gpuMeshes.size > 3) {
    // Pass A: HD Terrain & Specular Canal Water (2 draw calls!)
    pushTRS(scratchInst, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0);
    drawMeshBatch("_terrain", 0, 1);
    pushTRS(scratchInst, 0, 0, Math.sin(nowMs * 0.0014) * 0.03, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0);
    drawMeshBatch("_water", 0, 1);

    // Pass A2: 1-Draw-Call Hardware-Instanced Soft Canopy & Contact Ground Shadows!
    let cSh = 0;
    cSh = pushTRS(shadowScratch, cSh, PKS_POS.x, terrainHeight(PKS_POS.x, PKS_POS.z), PKS_POS.z, 0, 0, 0, 7.6, 1, 6.2, 0.95, 1, 1, 0);
    cSh = pushTRS(shadowScratch, cSh, MANDOR_POS.x, terrainHeight(MANDOR_POS.x, MANDOR_POS.z), MANDOR_POS.z, 0, 0, 0, 2.9, 1, 2.9, 0.85, 1, 1, 0);
    cSh = pushTRS(shadowScratch, cSh, p.x, p.y, p.z, 0, p.yaw, 0, p.inTruck ? 1.45 : 0.68, 1, p.inTruck ? 2.95 : 0.68, 1.0, 1, 1, 0);
    for (const peer of state.peers.values()) {
      cSh = pushTRS(shadowScratch, cSh, peer.rx, peer.ry, peer.rz, 0, peer.ryaw, 0, peer.tr ? 1.45 : 0.68, 1, peer.tr ? 2.95 : 0.68, 1.0, 1, 1, 0);
    }
    for (const b of state.boars) {
      cSh = pushTRS(shadowScratch, cSh, b.x, surfaceHeight(b.x, b.z), b.z, 0, b.yaw, 0, 0.72, 1, 0.98, 0.9, 1, 1, 0);
    }
    for (const t of state.trees) {
      const d = Math.hypot(t.x - eyeX, t.z - eyeZ);
      if (d > (state.quality === 0 ? q.lod1 : q.maxDist)) continue;
      cSh = pushTRS(shadowScratch, cSh, t.x + 0.45, t.y, t.z + 0.35, 0, 0, 0, 3.35 * t.scale, 1, 3.35 * t.scale, d > q.lod1 ? 0.55 : 0.85, 1, 1, 0);
    }
    if (cSh > 0 && gpuMeshes.has("_shadow")) {
      const shGpu = gpuMeshes.get("_shadow").lods[0];
      gl.useProgram(shadowProg);
      gl.uniformMatrix4fv(uShadowVp, false, mVP);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      gl.depthMask(false);
      gl.bindVertexArray(shGpu.vao);
      gl.bindBuffer(gl.ARRAY_BUFFER, sharedInstanceBuffer);
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, shadowScratch.subarray(0, cSh * 16));
      gl.drawElementsInstanced(gl.TRIANGLES, shGpu.count, gl.UNSIGNED_SHORT, 0, cSh);
      frameDrawCalls++;
      gl.depthMask(true);
      gl.disable(gl.BLEND);
      gl.useProgram(prog);
    }

    // Pass B: Multi-LOD Instanced Tenera Oil Palms (Grouped into LOD0, LOD1, LOD2 -> max 9 ultra-fast instanced draw calls for 180 complex trees!)
    const isStorm = storm ? 1.0 : 0.0;
    for (let lodTier = 0; lodTier < 3; lodTier++) {
      let cTrunk = 0;
      for (const t of state.trees) {
        const d = Math.hypot(t.x - eyeX, t.z - eyeZ);
        if (d > q.maxDist) continue;
        const tier = d < q.lod0 ? 0 : (d < q.lod1 ? 1 : 2);
        if (tier !== lodTier) continue;
        cTrunk = pushTRS(scratchInst, cTrunk, t.x, t.y - 0.12, t.z, 0, t.rot, 0, t.scale, t.scale, t.scale, 1, 1, 1, 0);
      }
      drawMeshBatch("palm_trunk", lodTier, cTrunk);

      let cCrown = 0;
      for (const t of state.trees) {
        const d = Math.hypot(t.x - eyeX, t.z - eyeZ);
        if (d > q.maxDist) continue;
        const tier = d < q.lod0 ? 0 : (d < q.lod1 ? 1 : 2);
        if (tier !== lodTier) continue;
        const cy = Math.cos(t.rot), sy = Math.sin(t.rot);
        cCrown = pushTRS(
          scratchInst, cCrown,
          t.x + (0.30 * cy + 0.24 * sy) * t.scale,
          t.y + 6.18 * t.scale,
          t.z + (-0.30 * sy + 0.24 * cy) * t.scale,
          0, t.rot, 0, t.scale, t.scale, t.scale,
          1, 1, 1, isStorm ? 2.1 : 0.85
        );
      }
      drawMeshBatch("palm_crown", lodTier, cCrown);

      // Ripe Red-Orange & Golden Sultan TBS bunches hanging under tree crowns
      let cFruit = 0;
      for (const t of state.trees) {
        if (t.state === 0) continue;
        const d = Math.hypot(t.x - eyeX, t.z - eyeZ);
        if (d > q.lod1 + 18) continue;
        const tier = d < q.lod0 ? 0 : (d < q.lod1 ? 1 : 2);
        if (tier !== lodTier) continue;
        const isGold = t.state === 2;
        const bunchesPerTree = tier === 0 ? 4 : 2;
        for (let bi = 0; bi < bunchesPerTree && cFruit < MAX_INSTANCES; bi++) {
          const ang = t.rot + bi * 1.57;
          cFruit = pushTRS(
            scratchInst, cFruit,
            t.x + Math.sin(ang) * 0.52 * t.scale,
            t.y + 5.82 * t.scale,
            t.z + Math.cos(ang) * 0.52 * t.scale,
            0, ang, 0, t.scale, t.scale, t.scale,
            isGold ? 1.18 : 1.0, isGold ? 1.62 : 1.0, isGold ? 0.36 : 1.0, 0.25
          );
        }
      }
      drawMeshBatch("tbs_bunch", lodTier, cFruit);
    }

    // Falling physics TBS bunches
    if (state.fallingFruits.length) {
      let cf = 0;
      for (const f of state.fallingFruits) {
        cf = pushTRS(scratchInst, cf, f.x, f.y, f.z, f.rot, f.rot, 0, 1.05, 1.05, 1.05, f.isGold ? 1.18 : 1, f.isGold ? 1.62 : 1, f.isGold ? 0.36 : 1, 0);
      }
      drawMeshBatch("tbs_bunch", 0, cf);
    }

    // Ferns & Boulders (2 instanced draw calls!)
    if (q.ferns) {
      let cf = 0;
      for (const f of state.ferns) {
        if (Math.hypot(f.x - eyeX, f.z - eyeZ) < 62 && cf < MAX_INSTANCES) {
          cf = pushTRS(scratchInst, cf, f.x, f.y, f.z, 0, f.rot, 0, f.s, f.s, f.s, 1, 1, 1, 0.7);
        }
      }
      drawMeshBatch("tropical_fern", 1, cf);
    }
    {
      let crk = 0;
      for (const r of state.rocks) {
        if (Math.hypot(r.x - eyeX, r.z - eyeZ) < 95 && crk < MAX_INSTANCES) {
          crk = pushTRS(scratchInst, crk, r.x, r.y, r.z, 0, r.rot, 0, r.s, r.s, r.s, 1, 1, 1, 0);
        }
      }
      drawMeshBatch("rock_boulder", 0, crk);
    }

    // Pass C: Landmarks, Wild Boars, Local Player & All Live Multiplayer Peers!
    resetBuckets();
    enqueuePart("pks_factory", PKS_POS.x, terrainHeight(PKS_POS.x, PKS_POS.z), PKS_POS.z, 0, 0, 0, 1.0);
    enqueuePart("weighbridge_ram", RAM_POS.x, terrainHeight(RAM_POS.x, RAM_POS.z), RAM_POS.z, 0, 0, 0, 1.0);
    enqueuePart("mandor_post", MANDOR_POS.x, terrainHeight(MANDOR_POS.x, MANDOR_POS.z), MANDOR_POS.z, 0, 0.45, 0, 1.0);
    enqueuePart("angkong_cart", -6.5, terrainHeight(-6.5, -8.5), -8.5, 0, 0.6, 0, 1.0);
    enqueuePart("angkong_cart", 7.2, terrainHeight(7.2, -9.2), -9.2, 0, -0.8, 0, 1.0);
    enqueuePart("wooden_bridge", -28.0, terrainHeight(-28.0, CANAL_Z - 4.7), CANAL_Z, 0, 0, 0, 1.0);
    enqueuePart("wooden_bridge", 28.0, terrainHeight(28.0, CANAL_Z - 4.7), CANAL_Z, 0, 0, 0, 1.0);

    for (const b of state.boars) {
      enqueuePart("celeng_boar", b.x, surfaceHeight(b.x, b.z), b.z, 0, b.yaw, 0, 1.15);
    }

    labelAnchors.length = 0;
    stageActorVisual(p.x, p.y, p.z, p.yaw, p.walkPhase, p.swingTimer, p.inTruck, p.cargo, state.profile.avatar);
    labelAnchors.push({ id: state.profile.id, name: state.profile.name + " (Kamu)", title: state.profile.avatar.title, x: p.x, y: p.y + (p.inTruck ? 2.65 : 2.35), z: p.z, self: true });

    for (const peer of state.peers.values()) {
      stageActorVisual(peer.rx, peer.ry, peer.rz, peer.ryaw, peer.walk, peer.a === 2 ? 0.65 : 0, !!peer.tr, peer.cg, peer.av);
      labelAnchors.push({ id: peer.id, name: peer.n, title: peer.av?.title || "", x: peer.rx, y: peer.ry + (peer.tr ? 2.65 : 2.35), z: peer.rz, self: false });
    }
    flushBuckets(0);
  }

  // 4. Crisp 2D Overlay for 3D Nameplates, Floating Chat Bubbles & World Landmarks
  lctx.clearRect(0, 0, labelsCanvas.width, labelsCanvas.height);
  lctx.textAlign = "center";
  const ramScr = projectToScreen(RAM_POS.x, terrainHeight(RAM_POS.x, RAM_POS.z) + 5.2, RAM_POS.z, labelsCanvas.width, labelsCanvas.height);
  if (ramScr) {
    lctx.fillStyle = "rgba(13,18,15,0.85)";
    lctx.fillRect(ramScr[0] - 78, ramScr[1] - 14, 156, 24);
    lctx.fillStyle = "#facc15";
    lctx.font = "bold 11px system-ui, sans-serif";
    lctx.fillText("TIMBANGAN SETOR PKS", ramScr[0], ramScr[1] + 2);
  }

  for (const a of labelAnchors) {
    const scr = projectToScreen(a.x, a.y, a.z, labelsCanvas.width, labelsCanvas.height);
    if (!scr) continue;
    lctx.font = "bold 12px system-ui, sans-serif";
    const tw = Math.max(70, lctx.measureText(a.name).width + 18);
    lctx.fillStyle = a.self ? "rgba(22, 101, 52, 0.88)" : "rgba(13, 17, 15, 0.82)";
    lctx.fillRect(scr[0] - tw * 0.5, scr[1] - 16, tw, 22);
    lctx.fillStyle = a.self ? "#86efac" : "#ffffff";
    lctx.fillText(a.name, scr[0], scr[1] - 1);

    const bub = state.chatBubbles.get(a.id);
    if (bub && bub.until > nowMs) {
      const bw = Math.min(240, Math.max(90, lctx.measureText(bub.text).width + 22));
      lctx.fillStyle = "rgba(255, 255, 255, 0.95)";
      lctx.fillRect(scr[0] - bw * 0.5, scr[1] - 46, bw, 25);
      lctx.fillStyle = "#0d1310";
      lctx.fillText(bub.text.slice(0, 34), scr[0], scr[1] - 29);
    }
  }

  // 5. Live Tactical Minimap Radar
  mctx.fillStyle = "#102118";
  mctx.fillRect(0, 0, 140, 140);
  mctx.strokeStyle = "#5a452e";
  mctx.lineWidth = 4;
  mctx.beginPath();
  mctx.moveTo(70, 0); mctx.lineTo(70, 140);
  mctx.moveTo(0, 70 - 14 * 0.62); mctx.lineTo(140, 70 - 14 * 0.62);
  mctx.stroke();
  mctx.strokeStyle = "#2292a6";
  mctx.lineWidth = 3;
  mctx.beginPath();
  mctx.moveTo(0, 70 - CANAL_Z * 0.62); mctx.lineTo(140, 70 - CANAL_Z * 0.62);
  mctx.stroke();

  for (const t of state.trees) {
    if (t.state === 0) continue;
    mctx.fillStyle = t.state === 2 ? "#facc15" : "#22c55e";
    const mx = 70 + t.x * 0.62, my = 70 - t.z * 0.62;
    mctx.fillRect(mx - 1.2, my - 1.2, t.state === 2 ? 3.5 : 2.2, t.state === 2 ? 3.5 : 2.2);
  }
  // PKS RAM icon
  mctx.fillStyle = "#f97316";
  mctx.fillRect(65, 70 - RAM_POS.z * 0.62 - 4, 10, 8);
  // Remote players
  for (const peer of state.peers.values()) {
    mctx.fillStyle = "#38bdf8";
    mctx.beginPath();
    mctx.arc(70 + peer.rx * 0.62, 70 - peer.rz * 0.62, 3.2, 0, 6.28);
    mctx.fill();
  }
  // Local player arrow
  mctx.fillStyle = "#ffffff";
  mctx.beginPath();
  mctx.arc(70 + p.x * 0.62, 70 - p.z * 0.62, 4.2, 0, 6.28);
  mctx.fill();

  // Telemetry counter
  fpsAcc += dt;
  fpsFrames++;
  if (fpsAcc >= 0.5) {
    shownFps = Math.round(fpsFrames / fpsAcc);
    fpsFrames = 0;
    fpsAcc = 0;
    const netLabel = state.net.connected ? `LIVE ${state.net.pingMs}ms · ${state.peers.size + 1} Pemain` : "CONNECTING...";
    document.getElementById("perfStats").textContent = `${shownFps} FPS · ${frameDrawCalls} DC · ${netLabel}`;
  }
}

// --- Input Bindings (Keyboard, Mouse/Touch Orbit, Virtual Joystick & Action Buttons) ---
window.addEventListener("keydown", (e) => {
  if (document.activeElement && document.activeElement.tagName === "INPUT") {
    if (e.key === "Enter" && document.activeElement.id === "chatInput") sendChatNow();
    return;
  }
  state.input.keys.add(e.code);
  if (e.code === "Space" || e.code === "KeyE") triggerHarvestAction();
  if (e.code === "KeyF") toggleTruck();
  if (e.code === "KeyR") triggerSellAction();
});
window.addEventListener("keyup", (e) => state.input.keys.delete(e.code));

let draggingCam = false, lastPtrX = 0, lastPtrY = 0;
canvas.addEventListener("pointerdown", (e) => { draggingCam = true; lastPtrX = e.clientX; lastPtrY = e.clientY; canvas.setPointerCapture(e.pointerId); });
canvas.addEventListener("pointermove", (e) => {
  if (!draggingCam) return;
  state.cam.yaw -= (e.clientX - lastPtrX) * 0.0065;
  state.cam.pitch = Math.max(0.10, Math.min(0.95, state.cam.pitch + (e.clientY - lastPtrY) * 0.005));
  lastPtrX = e.clientX; lastPtrY = e.clientY;
});
canvas.addEventListener("pointerup", () => { draggingCam = false; });

const joyZone = document.getElementById("joyZone");
const joyKnob = document.getElementById("joyKnob");
let joyActive = false;
function updateJoy(e) {
  const r = joyZone.getBoundingClientRect();
  let dx = e.clientX - (r.left + r.width * 0.5);
  let dy = e.clientY - (r.top + r.height * 0.5);
  const maxR = 44;
  const len = Math.hypot(dx, dy);
  if (len > maxR) { dx = (dx / len) * maxR; dy = (dy / len) * maxR; }
  joyKnob.style.transform = `translate(${dx}px, ${dy}px)`;
  state.input.jx = dx / maxR;
  state.input.jy = -dy / maxR;
}
joyZone.addEventListener("pointerdown", (e) => { joyActive = true; joyZone.setPointerCapture(e.pointerId); updateJoy(e); });
joyZone.addEventListener("pointermove", (e) => { if (joyActive) updateJoy(e); });
const endJoy = () => { joyActive = false; joyKnob.style.transform = "translate(0px,0px)"; state.input.jx = 0; state.input.jy = 0; };
joyZone.addEventListener("pointerup", endJoy);
joyZone.addEventListener("pointercancel", endJoy);

function toggleTruck() {
  state.player.inTruck = !state.player.inTruck;
  playSfx("horn");
  showToast(state.player.inTruck ? "Naik Truk Canter Kebun! Kapasitas 24 TBS + Speed Ngebut!" : "Turun dari Truk Canter — Mode Jalan Kaki Egrek!");
  updateHud();
}

document.getElementById("btnHarvest").addEventListener("click", triggerHarvestAction);
document.getElementById("btnSell").addEventListener("click", triggerSellAction);
document.getElementById("btnTruck").addEventListener("click", toggleTruck);
document.getElementById("btnHorn").addEventListener("click", () => {
  state.player.boostTimer = 3.5;
  playSfx("horn");
  sendNet({ type: "horn" });
  showToast("KLAKSON TELOLET + NITRO OLENG AKTIF! Celeng Hutan Kabur!");
});

function sendChatNow() {
  const inp = document.getElementById("chatInput");
  const txt = inp.value.trim();
  if (!txt) return;
  sendNet({ type: "chat", channel: "global", text: txt });
  inp.value = "";
}
document.getElementById("chatSend").addEventListener("click", sendChatNow);

document.getElementById("qualityRow").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  state.quality = Number(chip.dataset.q);
  document.querySelectorAll("#qualityRow .chip").forEach((c) => c.classList.toggle("active", c === chip));
  showToast(`Preset Grafis: ${QUALITY_PRESETS[state.quality].name}`);
});

// --- Rich Interactive Feature Modals (Avatar 3D, Global Ranking, Weekly Tournament, Daily Streak, Social Login & Share) ---
const modalBackdrop = document.getElementById("modalBackdrop");
const modalTitle = document.getElementById("modalTitle");
const modalBody = document.getElementById("modalBody");
document.getElementById("modalClose").addEventListener("click", () => modalBackdrop.classList.remove("open"));
modalBackdrop.addEventListener("click", (e) => { if (e.target === modalBackdrop) modalBackdrop.classList.remove("open"); });

function openModal(title, html) {
  modalTitle.textContent = title;
  modalBody.innerHTML = html;
  modalBackdrop.classList.add("open");
}

const HAT_ITEMS = [
  { id: "hat_caping", name: "Caping Bambu Pro" },
  { id: "hat_safety", name: "Helm Proyek Mandor" },
  { id: "hat_headband", name: "Ikat Kepala Pendekar" },
  { id: "hat_cowboy", name: "Topi Koboi Juragan" },
  { id: "hat_crown_gold", name: "Mahkota Raja Sawit 24K" },
];
const BACK_ITEMS = [
  { id: "back_basket", name: "Keranjang Rotan TBS" },
  { id: "back_pack", name: "Ransel Radio HT" },
  { id: "back_cape", name: "Jubah Sultan Sawit" },
  { id: "back_wings_gold", name: "Sayap Daun Sawit Emas" },
];
const TOOL_ITEMS = [
  { id: "tool_egrek", name: "Egrek Sabit Panjang" },
  { id: "tool_dodos", name: "Dodos Baja Tempa" },
  { id: "tool_egrek_dragon", name: "Sabit Naga Emas" },
];
const OUTFIT_COLORS = ["#27AE60", "#E67E22", "#EAB308", "#2563EB", "#DC2626", "#9333EA", "#1E222B", "#14B8A6"];

document.getElementById("btnAvatar").addEventListener("click", function renderAvatarModal() {
  const av = state.profile.avatar;
  const renderPills = (list, key, cur) =>
    list.map((it) => `<span class="opt-pill ${cur === it.id ? "selected" : ""}" data-k="${key}" data-v="${it.id}">${it.name}</span>`).join("");

  openModal("KUSTOMISASI AVATAR 3D LIVE", `
    <div class="option-group">
      <label>Nama Pemanen / Juragan</label>
      <input class="field" id="avNameInput" maxlength="20" value="${escapeDom(state.profile.name)}" />
    </div>
    <div class="option-group">
      <label>Penutup Kepala 3D</label>
      <div class="opt-pills">${renderPills(HAT_ITEMS, "hat", av.hat)}</div>
    </div>
    <div class="option-group">
      <label>Aksesoris Punggung 3D</label>
      <div class="opt-pills">${renderPills(BACK_ITEMS, "back", av.back)}</div>
    </div>
    <div class="option-group">
      <label>Alat Panen 3D (Egrek & Dodos)</label>
      <div class="opt-pills">${renderPills(TOOL_ITEMS, "tool", av.tool)}</div>
    </div>
    <div class="option-group">
      <label>Warna Jersey & Cat Truk Canter</label>
      <div class="opt-pills">
        ${OUTFIT_COLORS.map((hex) => `<span class="opt-pill ${av.outfitHex === hex ? "selected" : ""}" data-k="outfitHex" data-v="${hex}" style="border-left:10px solid ${hex}">${hex}</span>`).join("")}
      </div>
    </div>
    <button class="cta-btn" id="avSaveBtn">TERAPKAN AVATAR KE KEBUN LIVE</button>
  `);

  modalBody.querySelectorAll(".opt-pill").forEach((el) => {
    el.addEventListener("click", () => {
      state.profile.avatar[el.dataset.k] = el.dataset.v;
      sendNet({ type: "avatar", name: document.getElementById("avNameInput").value, avatar: state.profile.avatar });
      renderAvatarModal();
    });
  });
  document.getElementById("avSaveBtn").addEventListener("click", () => {
    state.profile.name = document.getElementById("avNameInput").value.trim() || state.profile.name;
    sendNet({ type: "avatar", name: state.profile.name, avatar: state.profile.avatar });
    modalBackdrop.classList.remove("open");
    showToast("Avatar 3D disimpan & disinkronkan ke semua pemain live!");
  });
});

document.getElementById("btnRank").addEventListener("click", () => {
  sendNet({ type: "refresh_boards" });
  const rows = state.globalLeaderboard.map((r) => `
    <tr>
      <td><b>#${r.rank}</b></td>
      <td><b>${escapeDom(r.name)}</b><br/><small style="color:#93a89d">${escapeDom(r.title)} ${r.socialHandle ? "· " + escapeDom(r.socialHandle) : ""}</small></td>
      <td>${Number(r.totalKg).toLocaleString("id-ID")} Kg</td>
      <td style="color:#4ade80;font-weight:700">${Number(r.score).toLocaleString("id-ID")}</td>
    </tr>`).join("");
  openModal("GLOBAL RANKING JURAGAN SAWIT", `
    <p style="margin-top:0;color:#93a89d;font-size:13px">Peringkat global lintas Android APK & Browser disinkronkan real-time dari setiap setoran TBS di Timbangan PKS.</p>
    <table class="lb">
      <thead><tr><th>Rank</th><th>Pemain</th><th>Tonase TBS</th><th>Skor Global</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `);
});

function openTourneyModal() {
  sendNet({ type: "refresh_boards" });
  const t = state.tournament;
  const hrsLeft = Math.max(1, Math.round((t.endsAtMs - Date.now()) / 3600000));
  const tierCards = (t.tiers || []).map((tr) => {
    const claimed = state.profile.claimedTiers?.includes(tr.id);
    const ready = state.profile.weeklyPoints >= tr.minPts;
    return `
      <div class="day-card ${claimed ? "claimed" : (ready ? "today" : "")}">
        <b style="color:#facc15">${escapeDom(tr.label)}</b>
        <div style="font-size:12px;margin:6px 0">+Rp ${Number(tr.coins).toLocaleString("id-ID")} · +${tr.gems} Permata</div>
        <button class="cta-btn ${ready && !claimed ? "gold" : ""}" data-claim-tier="${tr.id}" ${claimed ? "disabled" : ""}>
          ${claimed ? "SUDAH DIKLAIM" : `KLAIM (${state.profile.weeklyPoints}/${tr.minPts} Poin)`}
        </button>
      </div>`;
  }).join("");

  const rows = (t.standings || []).slice(0, 10).map((s) => `
    <tr>
      <td><b>#${s.rank}</b></td>
      <td><b>${escapeDom(s.name)}</b> <small style="color:#5ce092">[${escapeDom(s.title)}]</small></td>
      <td>${Number(s.kgDelivered).toLocaleString("id-ID")} Kg</td>
      <td style="color:#facc15;font-weight:800">${Number(s.points).toLocaleString("id-ID")} Poin</td>
    </tr>`).join("");

  openModal(`TURNAMEN MINGGUAN ${t.weekId}`, `
    <div style="background:#19231e;border:1px solid #eab308;border-radius:12px;padding:12px;margin-bottom:14px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
      <div><b>PIALA JURAGAN SAWIT MINGGUAN</b><br/><small style="color:#93a89d">Reset dalam ${hrsLeft} jam · Poin Kamu: <b style="color:#facc15">${state.profile.weeklyPoints}</b></small></div>
      <span class="chip active">HADIAH MAHKOTA & SAYAP EMAS</span>
    </div>
    <div class="grid-2" style="margin-bottom:16px">${tierCards}</div>
    <table class="lb">
      <thead><tr><th>Pos</th><th>Peserta</th><th>Setoran Minggu Ini</th><th>Poin Turnamen</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `);
  modalBody.querySelectorAll("[data-claim-tier]").forEach((btn) => {
    btn.addEventListener("click", () => sendNet({ type: "tournament_claim", tierId: btn.dataset.claimTier }));
  });
}
document.getElementById("btnTourney").addEventListener("click", openTourneyModal);

function openDailyModal() {
  const cards = (state.dailyRewards.length ? state.dailyRewards : [
    { day: 1, coins: 250000, gems: 15, label: "Modal Hari 1" },
    { day: 2, coins: 400000, gems: 25, label: "Helm Proyek" },
    { day: 3, coins: 650000, gems: 40, label: "Ransel HT" },
    { day: 4, coins: 900000, gems: 60, label: "Topi Koboi" },
    { day: 5, coins: 1250000, gems: 85, label: "Jubah Sultan" },
    { day: 6, coins: 1750000, gems: 120, label: "Dodos Baja" },
    { day: 7, coins: 3000000, gems: 250, label: "Sabit Naga 24K" },
  ]).map((d) => {
    const claimed = d.day <= state.profile.streakDay;
    const isNext = !claimed && d.day === (state.profile.streakDay % 7) + 1 && state.profile.canClaimDaily;
    return `
      <div class="day-card ${claimed ? "claimed" : ""} ${isNext ? "today" : ""}">
        <div style="font-size:11px;color:#93a89d">HARI ${d.day}</div>
        <b style="display:block;margin:5px 0;color:#fff">${escapeDom(d.label)}</b>
        <div style="color:#4ade80;font-size:12px;font-weight:700">Rp ${Number(d.coins).toLocaleString("id-ID")}</div>
        <div style="color:#38bdf8;font-size:11px">+${d.gems} Permata</div>
      </div>`;
  }).join("");

  openModal("REWARD LOGIN HARIAN 7 HARI", `
    <p style="margin-top:0;color:#93a89d;font-size:13px">Streak Login Aktif: <b style="color:#4ade80">${state.profile.streakDay} Hari Berturut-turut</b> (+${state.profile.streakDay * 5}% Bonus Harga Jual TBS di PKS!)</p>
    <div class="streak-grid">${cards}</div>
    <button class="cta-btn gold" id="claimDailyNowBtn" ${state.profile.canClaimDaily ? "" : "disabled"}>
      ${state.profile.canClaimDaily ? "KLAIM HADIAH HARI INI SEKARANG!" : "SUDAH DIKLAIM HARI INI — KEMBALI BESOK!"}
    </button>
  `);
  const btn = document.getElementById("claimDailyNowBtn");
  if (btn) btn.addEventListener("click", () => sendNet({ type: "daily_claim" }));
}
document.getElementById("btnDaily").addEventListener("click", openDailyModal);

function openSocialModal() {
  openModal("LOGIN SOSIAL - BAGIKAN PRESTASI", `
    <div style="background:#18221d;border:1px solid #2b4a3a;border-radius:12px;padding:12px;margin-bottom:14px">
      Status Akun: <b style="color:#4ade80">${state.profile.socialProvider.toUpperCase()}</b>
      ${state.profile.socialHandle ? `(${escapeDom(state.profile.socialHandle)})` : "(Belum ditautkan — Tautkan untuk +30 Permata & Cloud Sync!)"}
    </div>
    <div class="grid-2">
      <div>
        <label style="font-size:11px;color:#93a89d;font-weight:700">TAUTKAN LOGIN SOSIAL (GOOGLE / TIKTOK / IG / X)</label>
        <input class="field" id="socName" placeholder="Nama Tampilan" value="${escapeDom(state.profile.name)}" style="margin-top:6px" />
        <input class="field" id="socHandle" placeholder="@username atau email Google" value="${escapeDom(state.profile.socialHandle)}" />
        <div class="opt-pills" id="socProviders" style="margin-bottom:8px">
          ${["google", "tiktok", "instagram", "x", "whatsapp"].map((p) => `<span class="opt-pill ${state.profile.socialProvider === p ? "selected" : ""}" data-prov="${p}">${p.toUpperCase()}</span>`).join("")}
        </div>
        <button class="cta-btn" id="btnBindSocial">HUBUNGKAN AKUN SOSIAL (+30 PERMATA)</button>
      </div>
      <div>
        <label style="font-size:11px;color:#93a89d;font-weight:700">BAGIKAN KARTU PRESTASI KE SOSMED</label>
        <p style="font-size:12.5px;color:#cbd5d1;line-height:1.45">Buat kartu pencapaian resmi dengan OpenGraph preview untuk dibagikan ke WhatsApp, TikTok, X/Twitter, atau Instagram!</p>
        <button class="cta-btn gold" id="btnCreateShare">BAGIKAN PENCAPAIAN SEKARANG</button>
        <input class="field" id="shareLinkOut" readonly placeholder="Link kartu pencapaian akan muncul di sini..." style="margin-top:10px" />
      </div>
    </div>
  `);

  let chosenProv = state.profile.socialProvider === "guest" ? "google" : state.profile.socialProvider;
  modalBody.querySelectorAll("[data-prov]").forEach((el) => {
    el.addEventListener("click", () => {
      chosenProv = el.dataset.prov;
      modalBody.querySelectorAll("[data-prov]").forEach((x) => x.classList.toggle("selected", x === el));
    });
  });
  document.getElementById("btnBindSocial").addEventListener("click", () => {
    sendNet({
      type: "auth_social",
      provider: chosenProv,
      displayName: document.getElementById("socName").value,
      handle: document.getElementById("socHandle").value,
    });
  });
  document.getElementById("btnCreateShare").addEventListener("click", async () => {
    const resp = await fetch("/api/share", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        playerId: state.profile.id,
        playerName: state.profile.name,
        title: state.profile.avatar.title,
        totalKg: state.profile.totalKg,
        score: state.profile.allTimeScore,
        weeklyPoints: state.profile.weeklyPoints,
        socialHandle: state.profile.socialHandle,
        hat: state.profile.avatar.hat,
      }),
    }).then((r) => r.json());
    if (resp.shareUrl) {
      document.getElementById("shareLinkOut").value = resp.shareUrl;
      if (navigator.share) {
        navigator.share({ title: "Prestasi Nyawit Live 3D", text: resp.shareText, url: resp.shareUrl }).catch(() => {});
      } else if (navigator.clipboard) {
        navigator.clipboard.writeText(resp.shareText).catch(() => {});
        showToast("Link Kartu Pencapaian disalin! Siap tempel ke Sosmed!");
      }
    }
  });
}
document.getElementById("btnSocial").addEventListener("click", openSocialModal);

// Boot Engine!
(async function boot() {
  buildTerrainAndWaterMeshes();
  updateHud();
  requestAnimationFrame(frame);
  await loadNpakGpuArchive();
  connectLiveServer();
})();
