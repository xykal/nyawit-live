# NYAWIT LIVE 3D v6.0.0 — Release Candidate Summary (`release/v6.0.0-draft`)

This release candidate integrates the complete `v6.0.0` engine, 57-model asset archive, C11 SIMD 6-plane frustum culler, authentic Canter driving HUD, telescopic Egrek harvest animation, and 100% Real-Player-Only multiplayer server on top of `main` (`c3be8a6`).

## Key Upgrades in `v6.0.0`

- **57 Sculpted PBR 3D Models (`171` LOD Slices in `nyawit_models.npak`)**:
  - Added `palm_sapling`, `tire_track_segment`, `char_face_neutral`, `char_face_strain`, `canter_axle_suspension`, `canter_driveshaft`, `canter_headlight_beam`, `cut_palm_frond`, `spbu_solar`, `warung_kopi`, `gudang_pupuk`, `offroad_arch`, `item_solar_can`, `item_coffee_cup`, `item_npk_sack`, and `item_cuan_crate`, plus upgraded `5.06m` telescopic `tool_egrek` and `tool_egrek_dragon`.
- **Native C11 SIMD 6-Plane Frustum Culler (`native/nyawit_simd.c`)**:
  - Extracts Gribb-Hartmann frustum planes from the column-major `ViewProj` matrix and performs 6-plane sphere culling + 3-tier LOD selection (`arm64-v8a` NEON, `armeabi-v7a`, `x86_64`, plus zero-GC C# fallback).
- **Expanded Plantation Estate (`220` Mature Palms + `96` Juvenile Saplings + Landmarks)**:
  - Synchronized `PlantationWorld.cs` and `server/src/worldSpec.js` on `220` harvestable mature palms (`WorldSeed = 20261022`), `96` decorative inter-row `palm_sapling` instances, solid collision pads for `SPBU Solar`, `Warung Kopi`, `Gudang Pupuk`, and dual-pillar `Gapura Offroad` arches.
- **Authentic Canter Driving Controls & Telescopic Egrek Harvest Animation**:
  - Default driving HUD uses dedicated left/right steering arrows (`[KIRI]` / `[KANAN]`) + vertical `[GAS]` and `[REM]` (air-brake + smooth reverse) pedals with full multi-touch pointer tracking, plus `"JOYSTICK ANALOG"` toggle in `PENGATURAN`.
  - Dynamic persistent `tire_track_segment` decals under rear dual tires, articulated Canter leaf-spring axles, spinning driveshaft, volumetric headlight beams, `0.68s` two-phase telescopic Egrek reach-and-slash animation, `char_face_strain` / `char_face_neutral` facial rigs, and falling `cut_palm_frond` physics.
  - Custom Canvas QWERTY modal (`ActiveModalOverlay.TextInput`) eliminates the last stock Android `EditText` / `LinearLayout` / `TextView` widgets.
- **100% Real-Player-Only Dedicated Server (`server/src/worker.js`)**:
  - Removed all simulated human bots and `seed_*` starter accounts, added idempotent SQLite cleanup of legacy `seed_*` rows, hardened token-verified `/api/share` & `/s/:code` cards, synchronized all WebSocket payload fields with `LiveMultiplayerClient.cs`, and added per-ABI `/download/apk/<abi>` routes.
- **Per-ABI Signed APKs & Automated Android 14 (`API 34`) 6-Stage Verification**:
  - Builds separate `NYAWIT-LIVE-v6-arm64-v8a.apk`, `NYAWIT-LIVE-v6-armeabi-v7a.apk`, and `NYAWIT-LIVE-v6-x86_64.apk` (~21–24 MB each) and verifies all 6 stages inside a real Android 14 (`API 34`) emulator in CI before updating `v6.0.0-draft`.
