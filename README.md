# NYAWIT LIVE 3D — `v4.0.0` (PBR Edition, Real-Time Shadows, 3D Garage Lobby & 60–120 FPS Engine)

**Custom Native C# OpenGL ES 3.0 Instanced PBR 3D Engine · Real-Time `1024x1024` Directional Shadow Map · Volumetric Cumulus Clouds · Separate 3D Garage Showroom Lobby · Reference-Accurate Mitsubishi Fuso Canter FE 74 HD (COE) · Multi-Room Dedicated Server & Live Push-to-Talk Voice**

- **Live Dedicated Multiplayer, Global Chat & Voice Server Portal**: <https://nyawit.xyverse.my.id>
- **Direct Signed Universal Android APK (`v4.0.0`, `arm64-v8a` + `armeabi-v7a` + `x86_64`)**: <https://nyawit.xyverse.my.id/download/apk>
- **Official GitHub Releases**: <https://github.com/xykal/nyawit-live/releases/latest>

![Nyawit Live 3D v4.0.0 Banner](docs/screenshots/og_banner.png)

---

## Verified Live Hardware Android 14 (`API 34`) Captures (`2400x1080` Fullscreen Immersive)

Every build of **Nyawit Live 3D `v4.0.0`** boots head-on inside a real KVM-accelerated **Android 14 (`API 34`)** device environment in CI with **zero stock Android chrome/bars/dialogs** and verifies all **6 distinct engine stages** in one uninterrupted process PID:

### 1. Custom `XYVERSE TECH` Boot Splash & Shader/Atlas Warm-Up
![Android 14 Boot Splash](docs/screenshots/android_v4_splash_hd.png)

### 2. Dedicated Separate 3D Garage / Workshop Showroom Lobby (`GARASI SAWIT`)
Completely separate from the open plantation map — features `360°` touch turntable camera, full harvester outfit & accessory selector (`Caping Bambu`, `Helm Proyek`, `Topi Koboi`, `Mahkota Emas`, `Kacamata Hitam`, `Keranjang Rotan`, `Tas Ransel`, `Egrek Baja`, `Dodos Lebar`, `Tojok Besi`, `Sarung Parang`), and the **Mitsubishi Fuso Canter FE 74 HD Bak Kayu**.
![Android 14 Separate 3D Garage Showroom Lobby](docs/screenshots/android_v4_lobby_garage_hd.png)

### 3. Full-Screen `"MENYIAPKAN DUNIA"` World Streaming Stage
![Android 14 World Loading Screen](docs/screenshots/android_v4_loading_hd.png)

### 4. Photorealistic Plantation On-Foot Gameplay — PBR Atlas, Alpha-Cutout Palms, Real Shadows & Spiky TBS Hold
![Android 14 On-Foot PBR Plantation](docs/screenshots/android_v4_onfoot_hold_hd.png)

### 5. Flat-Nose COE Mitsubishi Fuso Canter FE 74 HD Bak Kayu — 4-Wheel Suspension, Dual Rear Tires, Dust & Exhaust VFX
![Android 14 COE Canter FE 74 HD Driving](docs/screenshots/android_v4_canter_drive_hd.png)

### 6. Clean Uncluttered HUD & Custom In-Game `PENGATURAN` Panel (`30 / 60 / 90 / 120 FPS`, Render Scale, Anti-Lag)
![Android 14 Custom In-Game Settings Modal](docs/screenshots/android_v4_settings_hd.png)

### Sculpted UV-Mapped PBR Asset Showcase (`41` Models × `3` LODs = `123` Watertight Meshes)
![v4.0.0 PBR Sculpted Models Showcase](docs/screenshots/models_showcase.png)

---

## Key Engineering Highlights in `v4.0.0`

| Subsystem | Implementation Details |
| :--- | :--- |
| **True `60–120 FPS` Anti-Lag Architecture** | UI `Canvas` decoupled onto a dirty-driven 15 Hz telemetry invalidator (`0 B/frame` zero-GC render path); hardware-accelerated OpenGL ES 3.0 GPU instancing (`glDrawElementsInstanced`) batches hundreds of oil palms, TBS bunches, cargo logs, and VFX particles in `< 35` draw calls/frame; single `2048x2048` trilinear-mipmapped PBR texture atlas eliminates texture state thrashing; dynamic frustum + distance culling + `3` LOD tiers (`LOD0`, `LOD1`, `LOD2`) + configurable internal render scale (`50%–100% HD`) + native Android `Display.Mode` hardware refresh rate switching (`30 / 60 / 90 / 120 Hz`). |
| **Reference-Accurate 3D Models & Accessories (`nyawit_models.npak`)** | `41` high-detail procedural Blender-grade models (`123` LOD meshes, `24-byte` vertex stride with quantized octahedral normals and `uint16` atlas UVs): COE flat-nose **Mitsubishi Fuso Canter FE 74 HD** with laminated glass windshield, wipers, stepped Mitsubishi side doors, recessed handles, twin side mirrors, chrome 3-diamond grille, multi-reflector headlamps + amber turn signals, `"BM 8899 XY"` plate, dual rear tires (`6` wheels), Meranti wooden `Bak Kayu` with reflective safety tape, `7.5-head` seamless human anatomy, `Angkong` wheelbarrow, diamond-bark oil palms with epiphytic trunk ferns & feathery alpha-cutout fronds, compact spiky dark-crimson-orange **TBS** clusters, and industrial **PKS** mill & **RAM** weighbridge. |
| **PBR Lighting, `1024x1024` Shadow Map, Sky Clouds & VFX** | Depth FBO directional sun shadow pass with `2x2` PCF filtering (`ShadowTier`), energy-conserving hemisphere + tropical sun PBR shader, terrain splat blending (laterite dirt road + grass + drainage ditch moisture), procedural sunlit cumulus cloud dome, atmospheric horizon fog, and ring-buffered instanced `VfxSystem` (`tire dust`, `diesel exhaust`, `falling loose fruitlets`, `water splash`). |
| **Zero Stock Android UI & Clean Stage Separation** | Immersive full-screen `LayoutInDisplayCutoutMode.Always` across `Splash` -> separate `3D Garage Lobby` -> `"MENYIAPKAN DUNIA"` -> `Open Kebun Gameplay`, custom vector icon renderer (`0` emojis anywhere in client or server), custom inline keyboard bar, and full `PENGATURAN` modal (`Grafik & FPS`, `Audio`, `Kontrol & Akun`). |
| **Dedicated Multiplayer, Global Chat & Voice Relay (`nyawit.xyverse.my.id`)** | Cloudflare Workers + Durable Objects (`PlantationRoomDO`, `GlobalLeaderboardDO`) handling real-time 20 Hz room state sync, live `8 kHz` PCM push-to-talk voice chat relay, cross-room global chat, RAM/PKS commodity pricing, and direct `/download/apk` distribution. |

---

## Repository Structure

```text
nyawit-live/
├── src/
│   ├── NyawitEngine/                  # Pure C# 3D engine core (PBR NPAK v2 loader, RigidBodyWorld, AnimationRig, QualityScaler, VfxSystem, Network)
│   └── Nyawit.Android/                # Native .NET 8 Android client (GLES 3.0 shadow+PBR instanced renderer, separated 4-stage UI, PCM voice/SFX)
├── server/                            # Cloudflare Worker + Durable Objects dedicated multiplayer, chat & voice server (nyawit.xyverse.my.id)
├── tools/
│   ├── generate_pbr_atlas.py          # Generates 2048x2048 procedural PBR material texture atlas
│   ├── sculpt_pipeline.py             # Generates 41 UV-mapped 3D models x 3 LODs -> nyawit_models.npak
│   ├── render_showcase.py             # Renders 6-panel PBR textured model showcase sheet
│   └── verify_android_emulator.py     # Automated 8-gate real Android 14 (API 34) hardware verification harness
├── tests/NyawitEngine.Tests/          # xUnit physics, suspension, hold-stance, PBR atlas & 41-mesh NPAK verification suite
└── .github/workflows/build-apk.yml    # End-to-end build, signing, Android 14 6-screen live test & GitHub Release pipeline
```
