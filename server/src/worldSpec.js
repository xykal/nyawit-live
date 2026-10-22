// Shared Deterministic World & Economy Specification (Identical to NyawitEngine C# PlantationLayout.cs!)

export const WORLD_SEED = 20261022;
export const WORLD_HALF = 108.0;

// Landmark Coordinates (Meters)
export const PKS_POS = { x: 0.0, z: -26.0 };
export const RAM_POS = { x: 0.0, z: -14.5 };      // Drive-through Jembatan Timbang PKS sell zone!
export const MANDOR_POS = { x: -12.5, z: -11.0 };
export const SPAWN_CENTER = { x: 0.0, z: 3.0 };
export const CANAL_Z = -48.0;
export const BRIDGE_XS = [-28.0, 28.0];

export function mulberry32(seed) {
  let a = seed >>> 0;
  return function next() {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function roadFactor(x, z) {
  // North-South main haul road (x = 0) + East-West collector (z = 14) + Outer estate loop (r = 72)
  const dNS = Math.abs(x);
  const dEW = Math.abs(z - 14.0);
  const rLoop = Math.abs(Math.hypot(x, z - 8.0) - 70.0);
  const dPlaza = Math.hypot(x, z + 15.0) - 15.5;
  const dBridgeL = Math.abs(x + 28.0) < 2.4 && Math.abs(z - CANAL_Z) < 6.5 ? 0.0 : 99.0;
  const dBridgeR = Math.abs(x - 28.0) < 2.4 && Math.abs(z - CANAL_Z) < 6.5 ? 0.0 : 99.0;
  const dMin = Math.min(dNS, dEW, rLoop, Math.max(0.0, dPlaza), dBridgeL, dBridgeR);
  return Math.max(0.0, Math.min(1.0, 1.0 - (dMin - 2.6) / 2.2));
}

export function mudFactor(x, z) {
  const n = Math.sin(x * 0.075 + 1.1) * Math.cos(z * 0.068 - 0.7) + 0.5 * Math.sin((x + z) * 0.11);
  return Math.max(0.0, Math.min(1.0, (n - 0.28) * 1.35)) * (1.0 - roadFactor(x, z) * 0.65);
}

export function terrainHeight(x, z) {
  // Flat compacted central PKS yard & Timbangan RAM
  const yardDist = Math.hypot(x, z + 16.0);
  const yardFlat = Math.max(0.0, Math.min(1.0, (yardDist - 18.0) / 10.0));

  let h = (
    Math.sin(x * 0.036) * Math.cos(z * 0.032) * 1.45 +
    Math.sin(x * 0.082 + 0.9) * Math.sin(z * 0.076) * 0.42
  ) * yardFlat;

  // Perimeter scenic Sumatra volcanic foothills
  const edge = Math.max(0.0, (Math.max(Math.abs(x), Math.abs(z)) - 86.0) / 22.0);
  h += edge * edge * 6.5;

  // Flowing tropical drainage canal at z = -48 (carved smoothly except at bridges? No — wooden bridges arch OVER the canal!)
  const dCanal = Math.abs(z - CANAL_Z);
  if (dCanal < 4.6) {
    const k = Math.cos((dCanal / 4.6) * Math.PI * 0.5);
    h -= k * k * 1.85;
  }
  return h;
}

export function generatePlantationTrees() {
  const rng = mulberry32(WORLD_SEED);
  const trees = [];
  // 180 trees on realistic estate grid with organic jitter avoiding roads, canal & PKS yard
  for (let gx = -94; gx <= 94 && trees.length < 180; gx += 11.5) {
    for (let gz = -92; gz <= 94 && trees.length < 180; gz += 11.5) {
      const x = +(gx + (rng() - 0.5) * 3.8).toFixed(2);
      const z = +(gz + (rng() - 0.5) * 3.8).toFixed(2);
      const rot = +(rng() * Math.PI * 2.0).toFixed(3);
      const scale = +(0.84 + rng() * 0.34).toFixed(3);
      if (Math.hypot(x, z + 15.0) < 22.0) continue;           // Clear PKS & RAM yard
      if (Math.abs(z - CANAL_Z) < 6.4) continue;              // Clear canal banks
      if (roadFactor(x, z) > 0.35) continue;                  // Clear haul roads
      const y = +terrainHeight(x, z).toFixed(2);
      const isNorthSultanZone = z > 42.0;
      trees.push({
        id: trees.length,
        x,
        y,
        z,
        rot,
        scale,
        sultanBias: isNorthSultanZone ? 0.24 : 0.08,
      });
    }
  }
  return trees;
}

export const DAILY_REWARDS = [
  { day: 1, coins: 250000, gems: 15, unlock: null, label: "Modal Panen Hari 1" },
  { day: 2, coins: 400000, gems: 25, unlock: "hat_safety", label: "Helm Proyek Mandor" },
  { day: 3, coins: 650000, gems: 40, unlock: "back_pack", label: "Ransel Radio HT" },
  { day: 4, coins: 900000, gems: 60, unlock: "hat_cowboy", label: "Topi Koboi Juragan" },
  { day: 5, coins: 1250000, gems: 85, unlock: "back_cape", label: "Jubah Sultan Sawit" },
  { day: 6, coins: 1750000, gems: 120, unlock: "tool_dodos", label: "Dodos Baja Tempa" },
  { day: 7, coins: 3000000, gems: 250, unlock: "tool_egrek_dragon", label: "Sabit Naga Emas 24K" },
];

export const WEEKLY_TOURNAMENT_TIERS = [
  { id: "tier_bronze", minPts: 250, coins: 500000, gems: 35, unlock: "hat_headband", title: "Pendekar Kebun", label: "250 Poin: Ikat Kepala Pendekar" },
  { id: "tier_silver", minPts: 800, coins: 1200000, gems: 80, unlock: "tool_egrek_dragon", title: "Mandor Utama", label: "800 Poin: Sabit Naga Sawit" },
  { id: "tier_gold", minPts: 1800, coins: 2500000, gems: 160, unlock: "back_wings_gold", title: "Sayap Emas PKS", label: "1.800 Poin: Sayap Daun Sawit Emas" },
  { id: "tier_champion", minPts: 3200, coins: 5000000, gems: 350, unlock: "hat_crown_gold", title: "RAJA SAWIT NUSANTARA", label: "3.200 Poin / Top 3: Mahkota Raja Sawit" },
];
