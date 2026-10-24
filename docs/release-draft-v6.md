# NYAWIT LIVE 3D v6.0.0 — Official Release Notes

`NYAWIT LIVE 3D v6.0.0` delivers the upgraded **57-Model High-Detail 3D Asset Pack (`60,556` LOD0 triangles)**, **Anime Ink Outline + Hybrid Cel-PBR Renderer**, **`Semi-ENB Dingin` & `Fog Asap Karhutla` Atmosphere Modes**, **C11 SIMD 6-Plane Frustum Culler**, **Authentic Canter Steering Arrows + Gas/Brake Pedals**, and **100% Real-Player-Only Dedicated Multiplayer & Live Voice Server** (`https://nyawit.xyverse.my.id`).

## Key Upgrades in `v6.0.0`

- **57 High-Detail Sculpted 3D Models (`171` LOD Slices, `3.64 MB` `nyawit_models.npak`, `60,556` LOD0 Triangles)**:
  - Re-sculpted hero & estate assets with crisp chamfered silhouettes: **Mitsubishi Fuso Canter FE 74 HD Modif Sumatera** (slatted chrome grille, bumper foglamps, roof rack, cab steps, dual exhausts, rear mudflaps, leaf-spring axles, spinning driveshaft & halogen beams), **7-Lug Deep-Dish Steel Rims (`canter_wheel`)**, **`5.06m` Telescopic `Egrek` & `Egrek Naga`**, **Spiky TBS Sawit (`tbs_bunch`)**, **Angkong Sawit (`angkong_cart`)**, **Pemanen Rig + Expressions (`char_face_neutral` / `char_face_strain`)**, **`SPBU Solar`**, **`Warung Kopi`**, **`Gudang Pupuk`**, **`Pabrik PKS`**, **`Timbangan RAM`**, and **`Gapura Offroad`**.
- **Anime Ink Outline + `Semi-ENB Dingin` & `Fog Asap Karhutla` Graphics (`Gles3InstancedRenderer.cs`)**:
  - Zero-upload inverted-hull (`GL_CULL_FACE` + `GL_FRONT`) silhouette ink outlines (`MATI` / `HALUS` / `ANIME TEGAS`) paired with hybrid cel-shaded ACES-tonemapped PBR lighting.
  - Switchable real-time atmospheres in `PENGATURAN -> VISUAL & BAYANGAN`:
    - **`ENB DINGIN` (`Semi-ENB Dingin`)**: Crisp steel-cyan sky, cool slate shadow lift, high-contrast ACES S-curve, and icy specular rim highlights.
    - **`ASAP KARHUTLA` (`Fog Asap Karhutla`)**: Authentic Sumatra/Kalimantan peatland smoke haze, amber-filtered sunbeams, drifting smoke motes, and automatic Canter halogen headlights.
    - **`TROPIK CERAH`**: Classic warm golden tropical estate lighting.
- **Native C11 SIMD 6-Plane Frustum Culler (`native/nyawit_simd.c`)**:
  - Extracts Gribb-Hartmann frustum planes from the column-major `ViewProj` matrix and performs 6-plane sphere culling + 3-tier LOD selection (`arm64-v8a` NEON, `armeabi-v7a`, `x86_64`, plus zero-GC C# fallback).
- **Expanded Plantation Estate (`220` Mature Palms + `96` Juvenile Saplings + Landmarks)**:
  - Synchronized `PlantationWorld.cs` and `server/src/worldSpec.js` on `220` harvestable mature palms (`WorldSeed = 20261022`), `96` decorative inter-row `palm_sapling` instances, solid collision pads for `SPBU Solar`, `Warung Kopi`, `Gudang Pupuk`, and dual-pillar `Gapura Offroad` arches.
- **Authentic Canter Driving Controls & Telescopic Egrek Harvest Animation**:
  - Default driving HUD uses dedicated left/right steering arrows (`[KIRI]` / `[KANAN]`) + vertical `[GAS]` and `[REM]` (air-brake + smooth reverse) pedals with full multi-touch pointer tracking, plus `"JOYSTICK ANALOG"` toggle in `PENGATURAN`.
  - Dynamic persistent `tire_track_segment` decals under rear dual tires, `0.68s` two-phase telescopic Egrek reach-and-slash animation, and custom Canvas QWERTY modal (`0` stock Android UI widgets, `0` emojis).
- **100% Real-Player-Only Dedicated Server (`server/src/worker.js`)**:
  - Removed all simulated human bots and `seed_*` starter accounts, added idempotent SQLite cleanup of legacy `seed_*` rows, hardened token-verified `/api/share` & `/s/:code` cards, synchronized all WebSocket payload fields with `LiveMultiplayerClient.cs`, and added per-ABI `/download/apk/<abi>` routes.
- **Per-ABI Signed APKs & Automated Android 14 (`API 34`) 7-Stage Verification**:
  - Builds separate `NYAWIT-LIVE-v6-arm64-v8a.apk`, `NYAWIT-LIVE-v6-armeabi-v7a.apk`, and `NYAWIT-LIVE-v6-x86_64.apk` (~22–24 MB each) and verifies all 7 stages (including `Semi-ENB Dingin`, `Fog Asap Karhutla`, and `PENGATURAN`) inside a real Android 14 (`API 34`) emulator in CI.
