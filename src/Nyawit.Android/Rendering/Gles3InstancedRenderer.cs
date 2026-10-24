using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using Android.Content;
using Android.Graphics;
using Android.Opengl;
using Android.Runtime;
using Java.Nio;
using Javax.Microedition.Khronos.Opengles;
using NyawitEngine.Assets;
using NyawitEngine.Core;
using NyawitEngine.Math;
using NyawitEngine.Network;
using NyawitEngine.Physics;
using NyawitEngine.World;
using EGLConfig = Javax.Microedition.Khronos.Egl.EGLConfig;

namespace Nyawit.AndroidClient.Rendering;

public enum AppSceneStage : byte
{
    Splash = 0,          // Custom XyVerse + Nyawit Live boot splash & shader/atlas warm-up
    Lobby = 1,           // Dedicated separate 3D Garage/Workshop Showroom (NOT inside plantation map!)
    PreparingWorld = 2,  // Full-screen "MENYIAPKAN DUNIA" world streaming screen
    Gameplay = 3,        // Live multiplayer plantation open world
}

public sealed class GpuMeshHandle
{
    public int Vao;
    public int IndexCount;
}

public struct ProjectedLabel
{
    public float ScreenX, ScreenY;
    public string Name;
    public string SubTitle;
    public string BubbleText;
    public bool IsSelf;
    public bool IsSpeaking;
}

public struct VfxParticle
{
    public bool Active;
    public float X, Y, Z;
    public float Vx, Vy, Vz;
    public float SizeStart, SizeEnd;
    public float R, G, B, Alpha;
    public float Age, Life;
    public float Spin;
}

public struct SmoothedRigPose
{
    public bool Initialized;
    public float HipOffsetY, TorsoRx;
    public float ThighLRx, KneeLRx, ThighRRx, KneeRRx;
    public float UaLRx, UaLRz, FaLRx, FaLRy;
    public float UaRRx, UaRRz, FaRRx, FaRRy;
}

public struct TireTrackDecal
{
    public bool Active;
    public float X, Y, Z;
    public float Rx, Ry, Rz;
    public float Age, Life;
}

public struct FallingFrond
{
    public bool Active;
    public float X, Y, Z;
    public float Vx, Vy, Vz;
    public float Rx, Ry, Rz;
    public float GroundY;
    public float Age, Life;
}

/// <summary>
/// NyawitEngine v4.0 Photorealistic OpenGL ES 3.0 Hardware-Instanced PBR + Shadow-Mapped Renderer:
///   - 2048x2048 Mipmapped + Anisotropic RGBA8 PBR Texture Atlas + Zero-Seam Alpha Cutout Foliage
///   - Real 1024x1024 Hardware Directional Sun Shadow Map FBO + 4-Tap Rotated Poisson PCF
///   - Multi-Scale Splatmapped Laterite Dirt Road / Lush Plantation Grass / Concrete PKS Yard
///   - Animated Volumetric Cumulus Sky Clouds + Atmospheric Golden Haze + Soft GPU VFX Particle Pool
///   - Separate Dedicated 3D Garage/Workshop Lobby Scene (14 draw calls -> locked 60-120 FPS!)
///   - Spring-Smoothed Fluid Human Kinematics + Complete Accessories + COE Canter Dual Rear Wheels & Live Steering Wheel
/// </summary>
public sealed class Gles3InstancedRenderer : Java.Lang.Object, GLSurfaceView.IRenderer
{
    private const int ShadowMapSize = 1024;

    private const string SkyVertexSrc = @"#version 300 es
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
}";

    private const string SkyFragmentSrc = @"#version 300 es
precision highp float;
in vec3 vRay;
uniform vec3 uSkyZenith;
uniform vec3 uSkyHorizon;
uniform vec3 uSunDir;
uniform vec3 uSunColor;
uniform float uTime;
uniform float uCloudsOn;
out vec4 fragColor;

float hash21(vec2 p) {
    p = fract(p * vec2(127.1, 311.7));
    p += dot(p, p + 34.23);
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
float fbmCloud(vec2 p) {
    float s = 0.0, a = 0.52;
    mat2 m = mat2(1.6, 1.2, -1.2, 1.6);
    for (int i = 0; i < 5; i++) {
        s += a * vnoise(p);
        p = m * p;
        a *= 0.5;
    }
    return s;
}

void main() {
    vec3 d = normalize(vRay);
    vec3 L = normalize(uSunDir);
    float up = clamp(d.y * 1.15 + 0.04, 0.0, 1.0);
    vec3 col = mix(uSkyHorizon, uSkyZenith, pow(up, 0.58));

    // Volumetric Tropical Cumulus Cloud Deck + Sunlit Silver-Gold Lining!
    if (uCloudsOn > 0.5 && d.y > 0.015) {
        vec2 uvC = d.xz / (d.y + 0.14);
        vec2 drift = vec2(uTime * 0.022, uTime * 0.011);
        float dens = fbmCloud(uvC * 0.95 + drift);
        float detail = fbmCloud(uvC * 2.65 - drift * 1.4);
        float cloud = smoothstep(0.46, 0.63, dens * 0.78 + detail * 0.26);
        // Directional derivative toward sun for realistic self-shadowed cloud bellies!
        float densSun = fbmCloud((uvC + L.xz * 0.14) * 0.95 + drift);
        float lit = clamp(0.45 + (dens - densSun) * 4.2, 0.10, 1.12);
        float sd = max(dot(d, L), 0.0);
        vec3 cloudDark = uSkyHorizon * 0.34;
        vec3 cloudBright = mix(uSkyHorizon * 1.72, vec3(0.92, 0.95, 0.98), 0.56) + uSunColor * pow(sd, 5.0) * 0.28;
        vec3 cCol = mix(cloudDark, cloudBright, lit);
        float horizonFade = smoothstep(0.012, 0.20, d.y);
        col = mix(col, cCol, cloud * 0.94 * horizonFade);
    }

    float sd = max(dot(d, L), 0.0);
    col += uSunColor * (pow(sd, 10.0) * 0.14 + pow(sd, 96.0) * 0.42 + smoothstep(0.9972, 0.9996, sd) * 1.45);
    // Atmospheric horizon mist scatter
    col = mix(col, uSkyHorizon * 1.02, pow(1.0 - clamp(abs(d.y) * 2.5, 0.0, 1.0), 4.0) * 0.52);
    col = (col * (2.51 * col + 0.03)) / (col * (2.43 * col + 0.59) + 0.14);
    fragColor = vec4(pow(clamp(col, 0.0, 1.0), vec3(0.4545)), 1.0);
}";

    // Hardware Depth-Only Sun Shadow Caster Program (supports wind animation + alpha-cutout palm fronds!)
    private const string DepthShadowVertexSrc = @"#version 300 es
precision highp float;
layout(location = 0) in vec3 aPos;
layout(location = 2) in vec2 aUV;
layout(location = 4) in vec4 iRow0;
layout(location = 5) in vec4 iRow1;
layout(location = 6) in vec4 iRow2;
layout(location = 7) in vec4 iTintAndWind;
uniform mat4 uLightVP;
uniform float uTime;
out vec2 vUV;
void main() {
    vec4 localPos = vec4(aPos, 1.0);
    vec3 worldPos = vec3(dot(iRow0, localPos), dot(iRow1, localPos), dot(iRow2, localPos));
    float windAmp = iTintAndWind.w;
    if (windAmp > 0.001) {
        float h = max(0.0, aPos.y + length(aPos.xz) * 0.42);
        float gust = sin(uTime * 2.05 + iRow0.w * 0.14 + iRow2.w * 0.11);
        float flutter = cos(uTime * 3.90 + aPos.x * 2.2 + iRow2.w * 0.17);
        worldPos.x += gust * 0.048 * h * windAmp;
        worldPos.z += flutter * 0.026 * h * windAmp;
        worldPos.y -= abs(gust) * 0.010 * h * windAmp;
    }
    float isDye = step(1.5, aUV.x);
    vUV = vec2(aUV.x - isDye * 2.0, aUV.y);
    gl_Position = uLightVP * vec4(worldPos, 1.0);
}";

    private const string DepthShadowFragmentSrc = @"#version 300 es
precision mediump float;
in vec2 vUV;
uniform sampler2D uAtlas;
void main() {
    if (texture(uAtlas, vUV).a < 0.44) discard;
}";

    private const string ContactShadowVertexSrc = @"#version 300 es
precision highp float;
layout(location = 0) in vec3 aPos;
layout(location = 3) in vec4 aColor;
layout(location = 4) in vec4 iRow0;
layout(location = 5) in vec4 iRow1;
layout(location = 6) in vec4 iRow2;
layout(location = 7) in vec4 iTintAndWind;
uniform mat4 uVP;
out float vAlpha;
void main() {
    vec4 p = vec4(aPos, 1.0);
    vec3 wp = vec3(dot(iRow0, p), dot(iRow1, p), dot(iRow2, p));
    vAlpha = aColor.a * iTintAndWind.r;
    gl_Position = uVP * vec4(wp, 1.0);
}";

    private const string ContactShadowFragmentSrc = @"#version 300 es
precision mediump float;
in float vAlpha;
out vec4 fragColor;
void main() {
    fragColor = vec4(0.015, 0.035, 0.025, clamp(vAlpha * 0.48, 0.0, 0.56));
}";

    private const string VertexShaderSrc = @"#version 300 es
precision highp float;
precision highp int;
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec2 aUV;
layout(location = 3) in vec4 aColor;
layout(location = 4) in vec4 iRow0;
layout(location = 5) in vec4 iRow1;
layout(location = 6) in vec4 iRow2;
layout(location = 7) in vec4 iTintAndWind;

uniform mat4 uVP;
uniform mat4 uLightVP;
uniform vec3 uCamPos;
uniform float uTime;
uniform int uRenderMode;
uniform float uOutlineWidth;

out vec3 vNormal;
out vec3 vWorldPos;
out vec4 vColor;
out vec4 vTintWind;
out vec2 vUV;
out vec4 vShadowCoord;

void main() {
    vec4 localPos = vec4(aPos, 1.0);
    vec3 worldPos = vec3(dot(iRow0, localPos), dot(iRow1, localPos), dot(iRow2, localPos));

    float windAmp = iTintAndWind.w;
    if (windAmp > 0.001 && aColor.a < 0.99 && uRenderMode != 3) {
        float h = max(0.0, aPos.y + length(aPos.xz) * 0.42);
        float gust = sin(uTime * 2.05 + iRow0.w * 0.14 + iRow2.w * 0.11);
        float flutter = cos(uTime * 3.90 + aPos.x * 2.2 + iRow2.w * 0.17);
        worldPos.x += gust * 0.048 * h * windAmp;
        worldPos.z += flutter * 0.026 * h * windAmp;
        worldPos.y -= abs(gust) * 0.010 * h * windAmp;
    }

    mat3 rotScale = mat3(
        iRow0.x, iRow1.x, iRow2.x,
        iRow0.y, iRow1.y, iRow2.y,
        iRow0.z, iRow1.z, iRow2.z
    );
    vec3 wNrm = normalize(rotScale * aNormal);
    vNormal = wNrm;
    vColor = aColor;
    vTintWind = iTintAndWind;
    vUV = aUV;

    // Mode 3: Inverted-Hull Geometric Anime Silhouette Pass (GL_FRONT culled, radial-blended zero-split corners)
    if (uRenderMode == 3) {
        // Keep double-sided cab glass panes open so 3D cabin interior stays crystal clear!
        if (aColor.a > 0.80 && aColor.a < 0.92 && aUV.y > 0.50 && aUV.y < 0.63) {
            gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
            vWorldPos = worldPos;
            vShadowCoord = vec4(0.0);
            return;
        }
        float distO = length(uCamPos - worldPos);
        if (distO > 44.0 || uOutlineWidth <= 0.0001) {
            gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
            vWorldPos = worldPos;
            vShadowCoord = vec4(0.0);
            return;
        }
        vec3 radLocal = length(aPos) > 0.001 ? normalize(aPos) : aNormal;
        vec3 extDir = normalize(mix(wNrm, normalize(rotScale * radLocal), 0.36));
        float thick = uOutlineWidth * clamp(0.65 + distO * 0.024, 0.65, 1.85);
        worldPos += extDir * thick;
        vWorldPos = worldPos;
        vShadowCoord = vec4(0.0);
        vec4 clipO = uVP * vec4(worldPos, 1.0);
        clipO.z += 0.00075 * clipO.w;
        gl_Position = clipO;
        return;
    }

    vWorldPos = worldPos;
    vShadowCoord = uLightVP * vec4(worldPos, 1.0);
    gl_Position = uVP * vec4(worldPos, 1.0);
}";

    private const string FragmentShaderSrc = @"#version 300 es
precision highp float;
precision highp int;
in vec3 vNormal;
in vec3 vWorldPos;
in vec4 vColor;
in vec4 vTintWind;
in vec2 vUV;
in vec4 vShadowCoord;

uniform sampler2D uAtlas;
uniform sampler2D uShadowMap;
uniform vec3 uSunDir;
uniform vec3 uSunColor;
uniform vec3 uSkyTop;
uniform vec3 uGroundBounce;
uniform vec3 uFogColor;
uniform vec3 uCamPos;
uniform float uFogDensity;
uniform float uTime;
uniform int uRenderMode;   // 0 = Semi-ENB PBR Mesh, 1 = Wet Mud Splatmapped Terrain, 2 = Soft VFX Puff, 3 = Thin Ink Outline
uniform int uShadowMode;   // 0 = Off, 1 = Single-Tap Fast Shadow, 2 = 4-Tap Soft PCF Shadow
uniform float uCloudsOn;
uniform float uOutlineStrength;
uniform int uAtmoPreset;   // 0 = Semi-ENB Dingin Sumatera, 1 = Fog Asap Karhutla Riau, 2 = Tropik Cerah

out vec4 fragColor;

vec2 tileUv(vec2 w, vec2 cellOrigin) {
    vec2 f = clamp(fract(w), vec2(0.018), vec2(0.982));
    return cellOrigin + f * 0.25;
}

float computeAtmosphereFog(float dist, float worldY) {
    if (uAtmoPreset == 1) {
        // Riau / Sumatera Peatland Fire Haze ('Kabut Asap Karhutla'): thick whitish-ash smoke veil + low ground peat fog!
        float baseHaze = smoothstep(5.5, 62.0, dist) * 0.92;
        float peatGround = exp(-max(0.0, worldY - 0.10) * 0.38) * smoothstep(3.0, 28.0, dist) * 0.28;
        return clamp(baseHaze + peatGround, 0.0, 0.94);
    }
    if (uAtmoPreset == 0) {
        // Bussid / GTA SA Mod ENB Dingin Sumatera: cool overcast morning plantation mist
        float mist = smoothstep(26.0, 148.0, dist) * (0.78 + uFogDensity * 6.0);
        float lowMist = exp(-max(0.0, worldY) * 0.22) * smoothstep(18.0, 88.0, dist) * 0.16;
        return clamp(mist + lowMist, 0.0, 0.88);
    }
    return clamp(smoothstep(56.0, 208.0, dist) * (0.74 + uFogDensity * 10.0), 0.0, 0.84);
}

vec3 applySemiEnbGrade(vec3 hdr) {
    vec3 mapped = (hdr * (2.51 * hdr + 0.03)) / (hdr * (2.43 * hdr + 0.59) + 0.14);
    vec3 srgbOut = pow(clamp(mapped, 0.0, 1.0), vec3(0.4545));
    // Cinematic ENB S-curve contrast (deep grounded blacks, controlled crisp highlights)
    vec3 scurve = srgbOut * srgbOut * (3.0 - 2.0 * srgbOut);
    srgbOut = mix(srgbOut, scurve, 0.34);
    float luma = dot(srgbOut, vec3(0.2126, 0.7152, 0.0722));
    if (uAtmoPreset == 0) {
        // Bussid / GTA SA Mod ENB Dingin Sumatera: desaturated moody cool steel-slate shadows, zero neon saturation!
        srgbOut = mix(vec3(luma), srgbOut, 0.90);
        srgbOut.r *= 0.955;
        srgbOut.g *= 0.985;
        srgbOut.b = clamp(srgbOut.b * 1.045 + (1.0 - luma) * 0.022, 0.0, 1.0);
    } else if (uAtmoPreset == 1) {
        // Riau Peatland Karhutla Ash-Smoke: desaturated smoky ash-taupe haze
        srgbOut = mix(vec3(luma), srgbOut, 0.78);
        srgbOut.r = clamp(srgbOut.r * 1.025 + 0.008, 0.0, 1.0);
        srgbOut.b *= 0.955;
    } else {
        srgbOut = clamp(mix(vec3(luma), srgbOut, 1.02), 0.0, 1.0);
    }
    return clamp(srgbOut, 0.0, 1.0);
}

float computeSunShadow(vec3 N, vec3 L, float camDist) {
    if (uShadowMode <= 0 || camDist > 38.0) return 1.0;
    vec3 sc = vShadowCoord.xyz / max(vShadowCoord.w, 1e-4);
    sc = sc * 0.5 + 0.5;
    if (sc.x < 0.01 || sc.x > 0.99 || sc.y < 0.01 || sc.y > 0.99 || sc.z > 0.998) return 1.0;

    float bias = max(0.0020 * (1.0 - max(dot(N, L), 0.0)), 0.00075);
    float fade = 1.0 - smoothstep(26.0, 37.5, camDist);

    if (uShadowMode == 1) {
        float d = texture(uShadowMap, sc.xy).r;
        float lit = sc.z - bias <= d ? 1.0 : 0.14;
        return mix(1.0, lit, fade);
    }

    const vec2 kPoisson[4] = vec2[4](
        vec2(-0.9420, -0.3990),
        vec2( 0.9455, -0.7689),
        vec2(-0.0941, -0.9293),
        vec2( 0.3449,  0.2938)
    );
    float vis = 0.0;
    float spread = 1.35 / 1024.0;
    for (int i = 0; i < 4; i++) {
        float d = texture(uShadowMap, sc.xy + kPoisson[i] * spread).r;
        vis += (sc.z - bias <= d) ? 1.0 : 0.12;
    }
    return mix(1.0, vis * 0.25, fade);
}

void main() {
    float dist = length(uCamPos - vWorldPos);

    // Mode 3: Clean Thin Geometric Silhouette Ink Outline (faded smoothly into haze)
    if (uRenderMode == 3) {
        float isDyeO = step(1.5, vUV.x);
        vec2 uvO = vec2(vUV.x - isDyeO * 2.0, vUV.y);
        if (texture(uAtlas, uvO).a < 0.44) discard;
        vec3 inkHdr = (uAtmoPreset == 1) ? vec3(0.022, 0.019, 0.016) : vec3(0.005, 0.007, 0.012);
        float fogO = computeAtmosphereFog(dist, vWorldPos.y);
        float farFade = smoothstep(28.0, 44.0, dist);
        vec3 outO = mix(inkHdr, uFogColor, clamp(max(fogO, farFade), 0.0, 0.98));
        fragColor = vec4(applySemiEnbGrade(outO), 1.0);
        return;
    }

    // Mode 2: Soft Volumetric Alpha Particle Puff (Tire Mud Spray, Diesel Soot, Karhutla Smoke, Steam)
    if (uRenderMode == 2) {
        float isDyeP = step(1.5, vUV.x);
        vec2 puv = vec2(vUV.x - isDyeP * 2.0, vUV.y);
        vec4 ptex = texture(uAtlas, puv);
        float alpha = ptex.a * clamp(vTintWind.w, 0.0, 1.0);
        if (alpha < 0.02) discard;
        vec3 pcol = pow(max(ptex.rgb, vec3(0.01)), vec3(2.2)) * vTintWind.rgb;
        fragColor = vec4(applySemiEnbGrade(pcol), alpha);
        return;
    }

    vec3 N = normalize(vNormal) * (gl_FrontFacing ? 1.0 : -1.0);
    vec3 L = normalize(uSunDir);
    vec3 V = normalize(uCamPos - vWorldPos);

    // Dark Sumatran Peat-Tea Drainage Canal Water ('Parit Gambut Sawit') reflecting moody ENB sky
    if (uRenderMode == 0 && vUV.y > 0.903 && vUV.y < 0.907 && vColor.a > 0.98) {
        float w1 = sin(vWorldPos.x * 1.45 + uTime * 1.85 + sin(vWorldPos.z * 1.7) * 0.8);
        float w2 = cos(vWorldPos.z * 2.45 - uTime * 1.45 + vWorldPos.x * 0.7);
        N = normalize(vec3(w1 * 0.10, 1.0, w2 * 0.12));
        float fres = pow(1.0 - max(dot(N, V), 0.0), 3.6);
        vec3 deepPeatWater = (uAtmoPreset == 0) ? vec3(0.012, 0.018, 0.022) : vec3(0.024, 0.022, 0.016);
        vec3 waterAlb = mix(deepPeatWater, uFogColor * 0.88, clamp(fres * 0.82 + 0.10, 0.0, 0.92));
        vec3 Hw = normalize(L + V);
        waterAlb += uSunColor * smoothstep(0.97, 0.996, max(dot(N, Hw), 0.0)) * 0.55;
        float fogW = computeAtmosphereFog(dist, vWorldPos.y);
        fragColor = vec4(applySemiEnbGrade(mix(waterAlb, uFogColor, fogW)), 1.0);
        return;
    }

    vec3 base;
    float gloss = vColor.a;
    float puddleMask = 0.0;

    if (uRenderMode == 1) {
        // Multi-scale splatmapped Sumatran plantation ground: Dark Undergrowth + Wet Rutted Mud Road + RAM Concrete
        float roadW = clamp(vUV.x, 0.0, 1.0);
        float mudW  = clamp(vUV.y, 0.0, 1.0);
        float yardW = clamp(1.0 - (length(vWorldPos.xz - vec2(0.0, -17.5)) - 11.5) / 4.5, 0.0, 1.0);

        vec3 gNear = texture(uAtlas, tileUv(vWorldPos.xz * 0.28, vec2(0.00, 0.00))).rgb;
        vec3 gFar  = texture(uAtlas, tileUv(vWorldPos.xz * 0.058 + 0.37, vec2(0.00, 0.00))).rgb;
        vec3 grass = mix(gNear, gFar, 0.40);

        vec3 dNear = texture(uAtlas, tileUv(vWorldPos.xz * 0.24, vec2(0.25, 0.00))).rgb;
        vec3 dFar  = texture(uAtlas, tileUv(vWorldPos.xz * 0.064 + 0.19, vec2(0.25, 0.00))).rgb;
        vec3 dirt  = mix(dNear, dFar, 0.36);

        vec3 conc  = texture(uAtlas, tileUv(vWorldPos.xz * 0.22, vec2(0.25, 0.75))).rgb;

        float dirtMix = smoothstep(0.14, 0.72, max(roadW, mudW * 0.68));
        vec3 srgbTex = mix(grass, dirt, dirtMix);
        srgbTex = mix(srgbTex, conc, yardW * 0.90);
        base = pow(max(srgbTex * vColor.rgb, vec3(0.001)), vec3(2.2));

        // Signature Bussid / GTA SA ENB Wet Rain-Slicked Sumatran Mud Road & Irregular Rainwater Puddles!
        float pWave = sin(vWorldPos.x * 0.57 + cos(vWorldPos.z * 0.49) * 2.1) * 0.36
                    + cos(vWorldPos.z * 0.83 - sin(vWorldPos.x * 0.41) * 1.7) * 0.32
                    + sin((vWorldPos.x + vWorldPos.z) * 1.15) * 0.18 + 0.46;
        puddleMask = smoothstep(0.64, 0.88, pWave + mudW * 0.16) * smoothstep(0.62, 0.92, roadW) * (1.0 - yardW * 0.85);
        float wetSoil = clamp(roadW * 0.58 + mudW * 0.34 + puddleMask * 0.48, 0.0, 1.0);
        // Wet soil absorbs diffuse light & shifts rich dark peat-chocolate!
        base *= mix(1.0, 0.46, wetSoil);

        if (dist < 32.0) {
            float lum = dot(srgbTex, vec3(0.333));
            float bumpFade = (1.0 - smoothstep(16.0, 32.0, dist)) * (1.0 - puddleMask * 0.85);
            N = normalize(N - vec3(dFdx(lum), 0.0, dFdy(lum)) * 2.3 * bumpFade);
        }
        N = normalize(mix(N, vec3(0.0, 1.0, 0.0), puddleMask * 0.88));
        gloss = clamp(0.05 + wetSoil * 0.36 + puddleMask * 0.52, 0.04, 0.94);
    } else {
        float isDyeable = step(1.5, vUV.x);
        vec2 atlasUV = vec2(vUV.x - isDyeable * 2.0, vUV.y);
        vec4 texel = texture(uAtlas, atlasUV);
        if (texel.a < 0.44) discard;
        vec3 effTint = mix(vec3(1.0), vTintWind.rgb, isDyeable);
        effTint *= mix(vec3(1.0), vTintWind.rgb, step(1.12, max(vTintWind.r, vTintWind.g)) * (1.0 - isDyeable));
        base = pow(max(texel.rgb * vColor.rgb, vec3(0.001)), vec3(2.2)) * pow(max(effTint, vec3(0.002)), vec3(1.65));
    }

    // Self-illuminated lamps / LED signs / crystal headlamps
    if (gloss > 0.965) {
        fragColor = vec4(applySemiEnbGrade(base * 2.25), 1.0);
        return;
    }

    vec3 H = normalize(L + V);
    float ndlSigned = dot(N, L);
    // Grounded Semi-ENB PBR + Soft Stylized Diffuse Ramp (crisp light/shadow separation without flat cartoon banding)
    float halfLam = pow(clamp(ndlSigned * 0.5 + 0.5, 0.0, 1.0), 1.75);
    float softCel = 0.16 + 0.48 * smoothstep(-0.04, 0.16, ndlSigned) + 0.36 * smoothstep(0.38, 0.62, ndlSigned);
    float diff = (uRenderMode == 1) ? mix(halfLam, max(ndlSigned, 0.0), 0.55) : mix(halfLam, softCel, 0.55);

    // Subsurface botanical translucency for oil palm fronds & ferns
    float isBotanical = step(0.75, 1.0 - abs(fract(vUV.x) - 0.125)) * step(0.25, vUV.y) * (1.0 - step(0.50, vUV.y));
    float sss = (uRenderMode == 0 ? 1.0 : 0.0) * isBotanical * pow(clamp(dot(-V, L) * 0.5 + 0.5, 0.0, 1.0), 2.4) * 0.36;

    float shadow = computeSunShadow(N, L, dist);
    if (uCloudsOn > 0.5) {
        float cWave = sin(vWorldPos.x * 0.038 + uTime * 0.26) * cos(vWorldPos.z * 0.034 + uTime * 0.18);
        shadow *= mix(0.80, 1.04, cWave * 0.5 + 0.5);
    }

    vec3 hemi = mix(uGroundBounce, uSkyTop, clamp(N.y * 0.5 + 0.5, 0.0, 1.0));
    float shininess = mix(14.0, 112.0, clamp(gloss, 0.0, 1.0));
    float spec = pow(max(dot(N, H), 0.0), shininess) * gloss * shadow;

    // Automotive clearcoat Fresnel reflection ONLY on glossy painted/metal meshes (zero cyan bleed onto grass/mud!)
    float fresnelObj = (uRenderMode == 0 ? 1.0 : 0.0) * (1.0 - isBotanical) * pow(1.0 - max(dot(N, V), 0.0), 3.6) * gloss * gloss;

    vec3 lit = base * (hemi + uSunColor * (mix(0.12, 1.0, shadow) * diff + sss))
             + uSunColor * spec * 0.48
             + uSkyTop * fresnelObj * 0.42;

    // ENB Wet Mud Road Puddle Sky & Canopy Reflection (dark glossy rainwater pools, zero white edge glare!)
    if (puddleMask > 0.01) {
        float pFres = clamp(0.14 + 0.56 * pow(1.0 - max(dot(N, V), 0.0), 3.6), 0.0, 0.68);
        vec3 puddleSky = mix(vec3(0.032, 0.026, 0.022), uSkyTop * 0.68, pFres) * mix(0.38, 1.0, shadow);
        lit = mix(lit, puddleSky + uSunColor * spec * 0.72, puddleMask * 0.58);
    }

    float fogAmt = computeAtmosphereFog(dist, vWorldPos.y);
    vec3 hdr = mix(lit, uFogColor, fogAmt);
    fragColor = vec4(applySemiEnbGrade(hdr), 1.0);
}";

    private readonly Context? _context;
    private readonly NpakArchive? _archive;
    private readonly List<PalmTreeNode> _trees = [];
    private readonly LiveMultiplayerSession? _net;
    private readonly List<StaticPropInstance> _ferns = [];
    private readonly List<StaticPropInstance> _rocks = [];
    private readonly List<StaticPropInstance> _saplings = [];

    public RigidBodyWorld Physics { get; } = null!;
    public QualityGovernor Quality { get; } = new();
    public AppSceneStage Stage { get; private set; } = AppSceneStage.Splash;
    public float SplashProgress { get; private set; }
    public string SplashStatus { get; private set; } = "MEMUAT ENGINE 3D & TEKSTUR PBR...";
    public float WorldPrepProgress { get; private set; }
    public string WorldPrepStatus { get; private set; } = "MENYIAPKAN DUNIA...";
    public float LobbyAvatarSpinOffset { get; set; }
    public float LobbyOrbitYaw { get; set; } = 0.06f;

    public event Action<float>? OnRenderScaleChanged;
    public event Action? OnWorldReady;
    public event Action? OnStageChanged;

    private readonly Dictionary<string, GpuMeshHandle[]> _gpuMeshes = new(StringComparer.Ordinal);
    private GpuMeshHandle? _terrainGpu;
    private GpuMeshHandle? _waterGpu;
    private GpuMeshHandle? _shadowDiscGpu;

    private int _atlasTexId;
    private int _shadowMapFbo, _shadowMapDepthTex;
    private int _depthShadowProgram, _uDepthLightVp, _uDepthTime, _uDepthAtlas;
    private int _skyProgram, _skyVao, _uSkyInvVp, _uSkyZenith, _uSkyHorizon, _uSkySunDir, _uSkySunCol, _uSkyTime, _uSkyClouds;
    private int _contactShadowProgram, _uContactVp;
    private int _program;
    private int _instanceVbo;
    private int _uVp, _uLightVp, _uTime, _uAtlas, _uShadowMap, _uSunDir, _uSunColor, _uSkyTop, _uGroundBounce, _uFogColor, _uCamPos, _uFogDensity, _uRenderMode, _uShadowMode, _uCloudsOn;
    private int _uOutlineWidth, _uOutlineStrength, _uAtmoPreset;
    private bool _allowOutlinePass;
    private float _karhutlaHazeAccum;
    private bool _gpuReady;

    private const int MaxInstancesPerBatch = 1024;
    private readonly float[] _instStaging = new float[MaxInstancesPerBatch * 16];
    private readonly float[] _shadowStaging = new float[MaxInstancesPerBatch * 16];
    private readonly float[][] _treeLodStaging = [new float[320 * 16], new float[320 * 16], new float[320 * 16]];
    private readonly float[] _fruitStaging = new float[MaxInstancesPerBatch * 16];
    private readonly float[] _goldStaging = new float[320 * 16];
    private readonly float[] _frustumPlanes24 = new float[24];
    private readonly float[] _treePositionsXyz = [];
    private readonly sbyte[] _treeLodResult = [];
    private readonly float[] _saplingPositionsXyz = [];
    private readonly sbyte[] _saplingLodResult = [];
    private FloatBuffer? _directFloatBuffer;

    // Pre-allocated zero-GC VFX particle pool, terrain-conforming tire tracks, falling fronds & spring rig!
    private readonly VfxParticle[] _vfxPool = new VfxParticle[96];
    private int _vfxCursor;
    private readonly TireTrackDecal[] _tireTracks = new TireTrackDecal[128];
    private int _tireTrackCursor;
    private float _lastTrackX = float.NaN, _lastTrackZ = float.NaN;
    private readonly FallingFrond[] _fallingFronds = new FallingFrond[16];
    private int _frondCursor;
    private float _dustEmitAccum;
    private float _exhaustEmitAccum;
    private SmoothedRigPose _localRigPose;
    public bool NearSpbuSolar;
    public bool NearWarungKopi;

    public bool InTruck;
    public float BoostTimer;
    public float JoyX, JoyY;
    public float CamYaw = 0.25f, CamPitch = 0.28f, CamDist = 7.4f;
    public float CameraSensitivity = 1.0f;
    public bool LockShowcaseCam;
    public int NearestRipeTreeId = -1;
    public bool NearRamWeighbridge;
    public int NearbyGroundFruitCount;
    public bool CanLoadIntoVehicleOrCart;
    public int NearbyAngkongId = -1;
    public bool LocalMicSpeaking;

    public float PlayerX => Physics.Player.X;
    public float PlayerY => Physics.Player.Y;
    public float PlayerZ => Physics.Player.Z;

    public int LastDrawCalls { get; private set; }
    public int LastTriangles { get; private set; }
    public int SurfaceWidth => _surfaceWidth;
    public int SurfaceHeight => _surfaceHeight;
    public bool IsGpuReady => _gpuReady;

    private int _surfaceWidth = 1280, _surfaceHeight = 720;
    private float _appliedScale = -1f;
    private readonly Stopwatch _clock = Stopwatch.StartNew();
    private double _lastTimeSec;
    private double _nextNetSyncSec;

    private readonly float[] _proj = new float[16];
    private readonly float[] _view = new float[16];
    private readonly float[] _vp = new float[16];
    private readonly float[] _invVp = new float[16];
    private readonly float[] _lightProj = new float[16];
    private readonly float[] _lightView = new float[16];
    private readonly float[] _lightVp = new float[16];

    private readonly List<RemotePeerState> _peersSnap = new(24);
    private readonly List<BoarNetState> _boarsSnap = new(4);
    private readonly List<ChatMessageEntry> _chatSnap = new(40);
    public readonly object HudLock = new();
    public readonly List<ProjectedLabel> ProjectedLabels = new(24);
    public readonly List<(float X, float Z, bool InTruck)> MinimapPeers = new(24);

    public Gles3InstancedRenderer(IntPtr javaReference, JniHandleOwnership transfer)
        : base(javaReference, transfer)
    {
    }

    public Gles3InstancedRenderer(
        Context context,
        NpakArchive archive,
        List<PalmTreeNode> trees,
        LiveMultiplayerSession net)
    {
        _context = context;
        _archive = archive;
        _trees = trees;
        _net = net;
        var (ferns, rocks) = PlantationWorld.GenerateScatterProps();
        _ferns = ferns;
        _rocks = rocks;
        _saplings = PlantationWorld.GenerateJuvenileSaplings(trees);
        Physics = new RigidBodyWorld(trees, rocks, _saplings);

        _treePositionsXyz = new float[_trees.Count * 3];
        _treeLodResult = new sbyte[_trees.Count];
        for (int i = 0; i < _trees.Count; i++)
        {
            _treePositionsXyz[i * 3 + 0] = _trees[i].X;
            _treePositionsXyz[i * 3 + 1] = _trees[i].Y;
            _treePositionsXyz[i * 3 + 2] = _trees[i].Z;
        }

        _saplingPositionsXyz = new float[_saplings.Count * 3];
        _saplingLodResult = new sbyte[_saplings.Count];
        for (int i = 0; i < _saplings.Count; i++)
        {
            _saplingPositionsXyz[i * 3 + 0] = _saplings[i].X;
            _saplingPositionsXyz[i * 3 + 1] = _saplings[i].Y;
            _saplingPositionsXyz[i * 3 + 2] = _saplings[i].Z;
        }

        _net.OnHarvestSpawnFruit += (tx, tz, isGold) =>
        {
            float gy = PlantationWorld.TerrainHeight(tx, tz);
            EmitHarvestBurstVfx(tx, gy + 5.6f, tz, isGold);
            EmitDustBurstVfx(tx + 0.6f, gy + 0.25f, tz + 0.6f, 6);
            SpawnFallingFrond(tx, gy + 5.75f, tz);
            if (InTruck) Physics.LaunchDirectTreeToTruckArc(tx, tz, isGold);
            else Physics.SpawnHarvestedGroundFruit(tx, tz, isGold);
        };
        Physics.OnCargoLandedInVehicle += (units, isGold) =>
        {
            EmitDustBurstVfx(Physics.MainTruck.X, Physics.MainTruck.Y + 1.45f, Physics.MainTruck.Z, 5);
            _net.SendLoadTbs(units, isGold ? 1 : 0);
        };
    }

    public List<PalmTreeNode> Trees => _trees;

    public void EmitHarvestBurstVfx(float wx, float wy, float wz, bool isGold)
    {
        if (!Quality.ParticlesEnabled) return;
        for (int i = 0; i < 8; i++)
        {
            float ang = i * 0.785f;
            SpawnParticle(
                wx + MathF.Cos(ang) * 0.35f, wy, wz + MathF.Sin(ang) * 0.35f,
                MathF.Cos(ang) * 1.9f, 0.8f - (i % 3) * 0.5f, MathF.Sin(ang) * 1.9f,
                0.24f, 0.62f,
                isGold ? 0.95f : 0.24f, isGold ? 0.78f : 0.42f, 0.14f, 0.78f, 0.85f);
        }
    }

    public void EmitDustBurstVfx(float wx, float wy, float wz, int count = 5)
    {
        if (!Quality.ParticlesEnabled) return;
        for (int i = 0; i < count; i++)
        {
            float ang = i * (6.283f / System.Math.Max(1, count));
            SpawnParticle(
                wx + MathF.Cos(ang) * 0.28f, wy, wz + MathF.Sin(ang) * 0.28f,
                MathF.Cos(ang) * 1.15f, 0.75f + (i % 2) * 0.35f, MathF.Sin(ang) * 1.15f,
                0.30f, 1.05f, 0.42f, 0.31f, 0.21f, 0.48f, 0.78f);
        }
    }

    private void SpawnParticle(
        float x, float y, float z,
        float vx, float vy, float vz,
        float sizeStart, float sizeEnd,
        float r, float g, float b, float alpha, float life)
    {
        ref var p = ref _vfxPool[_vfxCursor];
        _vfxCursor = (_vfxCursor + 1) % _vfxPool.Length;
        p.Active = true;
        p.X = x; p.Y = y; p.Z = z;
        p.Vx = vx; p.Vy = vy; p.Vz = vz;
        p.SizeStart = sizeStart; p.SizeEnd = sizeEnd;
        p.R = r; p.G = g; p.B = b; p.Alpha = alpha;
        p.Age = 0f; p.Life = life;
        p.Spin = (_vfxCursor % 7) * 0.8f;
    }

    public void SpawnFallingFrond(float tx, float startY, float tz)
    {
        ref var f = ref _fallingFronds[_frondCursor];
        float ang = (_frondCursor * 1.85f) + tx * 0.25f;
        _frondCursor = (_frondCursor + 1) % _fallingFronds.Length;
        float gx = tx + MathF.Cos(ang) * 1.15f;
        float gz = tz + MathF.Sin(ang) * 1.15f;
        f.Active = true;
        f.X = gx;
        f.Y = startY;
        f.Z = gz;
        f.Vx = MathF.Cos(ang) * 1.35f;
        f.Vy = -0.6f;
        f.Vz = MathF.Sin(ang) * 1.35f;
        f.Rx = 0.25f;
        f.Ry = ang;
        f.Rz = 0.15f;
        f.GroundY = RigidBodyWorld.SurfaceHeightWithStructures(gx, gz) + 0.05f;
        f.Age = 0f;
        f.Life = 22.0f;
    }

    public void EmitTireTrackAt(float wx, float wz, float yaw)
    {
        float h = RigidBodyWorld.SurfaceHeightWithStructures(wx, wz);
        // Never stamp tire tracks onto open canal water!
        bool onBridge = (MathF.Abs(wx + 28f) < 2.2f || MathF.Abs(wx - 28f) < 2.2f) && MathF.Abs(wz - PlantationWorld.CanalZ) < 4.3f;
        if (!onBridge && MathF.Abs(wz - PlantationWorld.CanalZ) < 4.1f) return;

        float sy = MathF.Sin(yaw), cy = MathF.Cos(yaw);
        float hFront = RigidBodyWorld.SurfaceHeightWithStructures(wx + sy * 0.35f, wz + cy * 0.35f);
        float hBack = RigidBodyWorld.SurfaceHeightWithStructures(wx - sy * 0.35f, wz - cy * 0.35f);
        float hRight = RigidBodyWorld.SurfaceHeightWithStructures(wx + cy * 0.22f, wz - sy * 0.22f);
        float hLeft = RigidBodyWorld.SurfaceHeightWithStructures(wx - cy * 0.22f, wz + sy * 0.22f);

        ref var tr = ref _tireTracks[_tireTrackCursor];
        _tireTrackCursor = (_tireTrackCursor + 1) % _tireTracks.Length;
        tr.Active = true;
        tr.X = wx;
        tr.Y = h + 0.008f;
        tr.Z = wz;
        tr.Rx = -MathF.Atan2(hFront - hBack, 0.70f);
        tr.Ry = yaw;
        tr.Rz = MathF.Atan2(hLeft - hRight, 0.44f);
        tr.Age = 0f;
        tr.Life = 36.0f;
    }

    public void SeedShowcaseTireTracks()
    {
        for (int i = 0; i < _tireTracks.Length; i++) _tireTracks[i].Active = false;
        _tireTrackCursor = 0;
        var v = Physics.MainTruck;
        for (int step = 1; step <= 10; step++)
        {
            float distBack = 1.35f + step * 0.68f;
            float curveYaw = v.Yaw - step * 0.032f;
            float sy = MathF.Sin(curveYaw), cy = MathF.Cos(curveYaw);
            float cx = v.X - sy * distBack;
            float cz = v.Z - cy * distBack;
            EmitTireTrackAt(cx - 0.84f * cy, cz + 0.84f * sy, curveYaw);
            EmitTireTrackAt(cx + 0.84f * cy, cz - 0.84f * sy, curveYaw);
        }
        _lastTrackX = v.X;
        _lastTrackZ = v.Z;
    }

    private void StepVfxParticles(float dt)
    {
        for (int i = 0; i < _vfxPool.Length; i++)
        {
            if (!_vfxPool[i].Active) continue;
            ref var p = ref _vfxPool[i];
            p.Age += dt;
            if (p.Age >= p.Life) { p.Active = false; continue; }
            p.X += p.Vx * dt;
            p.Y += p.Vy * dt;
            p.Z += p.Vz * dt;
            p.Vx *= (1f - dt * 1.8f);
            p.Vz *= (1f - dt * 1.8f);
            p.Vy -= 1.25f * dt;
        }

        for (int i = 0; i < _tireTracks.Length; i++)
        {
            if (!_tireTracks[i].Active) continue;
            _tireTracks[i].Age += dt;
            if (_tireTracks[i].Age >= _tireTracks[i].Life) _tireTracks[i].Active = false;
        }

        for (int i = 0; i < _fallingFronds.Length; i++)
        {
            if (!_fallingFronds[i].Active) continue;
            ref var f = ref _fallingFronds[i];
            f.Age += dt;
            if (f.Age >= f.Life) { f.Active = false; continue; }
            if (f.Y > f.GroundY)
            {
                f.Vy -= 8.2f * dt;
                f.X += f.Vx * dt;
                f.Y += f.Vy * dt;
                f.Z += f.Vz * dt;
                f.Rx += 1.6f * dt;
                f.Ry += 0.9f * dt;
                f.Rz = MathF.Sin(f.Age * 5.5f) * 0.35f;
                if (f.Y <= f.GroundY)
                {
                    f.Y = f.GroundY;
                    f.Rx = 0f;
                    f.Rz = 0f;
                }
            }
        }
    }

    public void SkipSplashToLobby()
    {
        if (!_gpuReady) return;
        SplashProgress = 1.0f;
        SetStage(AppSceneStage.Lobby);
    }

    public void BeginWorldPreparation()
    {
        if (Stage == AppSceneStage.PreparingWorld) return;
        // Park Canter cleanly in the PKS/Spawn plaza ready to drive or walk!
        Physics.MainTruck.X = 5.4f;
        Physics.MainTruck.Z = 4.2f;
        Physics.MainTruck.Yaw = -0.35f;
        Physics.MainTruck.SteerAngle = 0f;
        Physics.MainTruck.Y = RigidBodyWorld.SurfaceHeightWithStructures(5.4f, 4.2f);
        WorldPrepProgress = 0.02f;
        WorldPrepStatus = "MEMBANGUN TOPOGRAFI KEBUN SAWIT & PARIT...";
        SetStage(AppSceneStage.PreparingWorld);
    }

    public void ReturnToLobby()
    {
        InTruck = false;
        JoyX = JoyY = 0f;
        SetStage(AppSceneStage.Lobby);
    }

    private double _stageEnterSec;
    public bool HoldStageProgress { get; set; }

    private int _presentedFrameCount;
    public int PresentedFrameCount => System.Threading.Volatile.Read(ref _presentedFrameCount);

    public void ForceStageAndProgress(AppSceneStage stage, float progress = 0.58f, bool hold = false)
    {
        HoldStageProgress = hold;
        _stageEnterSec = _clock.Elapsed.TotalSeconds - progress * 2.2;
        if (stage == AppSceneStage.Splash) SplashProgress = progress;
        else if (stage == AppSceneStage.PreparingWorld) WorldPrepProgress = progress;
        Stage = stage;
        OnStageChanged?.Invoke();
    }

    private void SetStage(AppSceneStage next)
    {
        if (Stage == next) return;
        Stage = next;
        _stageEnterSec = _clock.Elapsed.TotalSeconds;
        OnStageChanged?.Invoke();
    }

    public void RequestPresetChange(GraphicsPreset preset)
    {
        Quality.SetManualPreset(preset);
        SyncRenderScaleNow();
    }

    public void SyncRenderScaleNow()
    {
        float target = Quality.EffectiveRenderScale;
        if (MathF.Abs(target - _appliedScale) > 0.01f)
        {
            _appliedScale = target;
            OnRenderScaleChanged?.Invoke(target);
        }
    }

    public void ToggleVehicleEnterExit()
    {
        if (!InTruck)
        {
            if (!Physics.IsNearMainTruck(9.5f))
            {
                float sx = PlayerX + MathF.Sin(Physics.Player.Yaw) * 3.6f;
                float sz = PlayerZ + MathF.Cos(Physics.Player.Yaw) * 3.6f;
                Physics.SolveSolidCircleCollision(ref sx, ref sz, 1.15f, skipVehicle: Physics.MainTruck);
                Physics.MainTruck.X = sx;
                Physics.MainTruck.Z = sz;
                Physics.MainTruck.Yaw = Physics.Player.Yaw;
            }
            InTruck = true;
            Physics.MainTruck.TriggerCargoDropImpulse(0.45f);
        }
        else
        {
            InTruck = false;
            float exitX = Physics.MainTruck.X - MathF.Cos(Physics.MainTruck.Yaw) * 1.95f;
            float exitZ = Physics.MainTruck.Z + MathF.Sin(Physics.MainTruck.Yaw) * 1.95f;
            Physics.SolveSolidCircleCollision(ref exitX, ref exitZ, 0.45f);
            Physics.Player.X = exitX;
            Physics.Player.Z = exitZ;
            Physics.Player.Y = RigidBodyWorld.SurfaceHeightWithStructures(exitX, exitZ);
            Physics.Player.VelX = Physics.Player.VelZ = 0f;
        }
    }

    public void OnSurfaceCreated(IGL10? gl, EGLConfig? config)
    {
        if (_archive == null || _context == null) return;

        int byteCap = MaxInstancesPerBatch * 16 * sizeof(float);
        var initByteBuf = ByteBuffer.AllocateDirect(byteCap).Order(ByteOrder.NativeOrder()!);
        _directFloatBuffer = initByteBuf.AsFloatBuffer()!;

        _skyProgram = BuildLinkedProgram(SkyVertexSrc, SkyFragmentSrc);
        _uSkyInvVp = GLES30.GlGetUniformLocation(_skyProgram, "uInvVP");
        _uSkyZenith = GLES30.GlGetUniformLocation(_skyProgram, "uSkyZenith");
        _uSkyHorizon = GLES30.GlGetUniformLocation(_skyProgram, "uSkyHorizon");
        _uSkySunDir = GLES30.GlGetUniformLocation(_skyProgram, "uSunDir");
        _uSkySunCol = GLES30.GlGetUniformLocation(_skyProgram, "uSunColor");
        _uSkyTime = GLES30.GlGetUniformLocation(_skyProgram, "uTime");
        _uSkyClouds = GLES30.GlGetUniformLocation(_skyProgram, "uCloudsOn");

        int[] skyVaos = new int[1];
        GLES30.GlGenVertexArrays(1, skyVaos, 0);
        _skyVao = skyVaos[0];

        _depthShadowProgram = BuildLinkedProgram(DepthShadowVertexSrc, DepthShadowFragmentSrc);
        _uDepthLightVp = GLES30.GlGetUniformLocation(_depthShadowProgram, "uLightVP");
        _uDepthTime = GLES30.GlGetUniformLocation(_depthShadowProgram, "uTime");
        _uDepthAtlas = GLES30.GlGetUniformLocation(_depthShadowProgram, "uAtlas");

        _contactShadowProgram = BuildLinkedProgram(ContactShadowVertexSrc, ContactShadowFragmentSrc);
        _uContactVp = GLES30.GlGetUniformLocation(_contactShadowProgram, "uVP");

        _program = BuildLinkedProgram(VertexShaderSrc, FragmentShaderSrc);
        _uVp = GLES30.GlGetUniformLocation(_program, "uVP");
        _uLightVp = GLES30.GlGetUniformLocation(_program, "uLightVP");
        _uTime = GLES30.GlGetUniformLocation(_program, "uTime");
        _uAtlas = GLES30.GlGetUniformLocation(_program, "uAtlas");
        _uShadowMap = GLES30.GlGetUniformLocation(_program, "uShadowMap");
        _uSunDir = GLES30.GlGetUniformLocation(_program, "uSunDir");
        _uSunColor = GLES30.GlGetUniformLocation(_program, "uSunColor");
        _uSkyTop = GLES30.GlGetUniformLocation(_program, "uSkyTop");
        _uGroundBounce = GLES30.GlGetUniformLocation(_program, "uGroundBounce");
        _uFogColor = GLES30.GlGetUniformLocation(_program, "uFogColor");
        _uCamPos = GLES30.GlGetUniformLocation(_program, "uCamPos");
        _uFogDensity = GLES30.GlGetUniformLocation(_program, "uFogDensity");
        _uRenderMode = GLES30.GlGetUniformLocation(_program, "uRenderMode");
        _uShadowMode = GLES30.GlGetUniformLocation(_program, "uShadowMode");
        _uCloudsOn = GLES30.GlGetUniformLocation(_program, "uCloudsOn");
        _uOutlineWidth = GLES30.GlGetUniformLocation(_program, "uOutlineWidth");
        _uOutlineStrength = GLES30.GlGetUniformLocation(_program, "uOutlineStrength");
        _uAtmoPreset = GLES30.GlGetUniformLocation(_program, "uAtmoPreset");

        int[] bufs = new int[1];
        GLES30.GlGenBuffers(1, bufs, 0);
        _instanceVbo = bufs[0];
        initByteBuf.Position(0);
        GLES30.GlBindBuffer(GLES30.GlArrayBuffer, _instanceVbo);
        GLES30.GlBufferData(GLES30.GlArrayBuffer, byteCap, initByteBuf, GLES30.GlDynamicDraw);

        _atlasTexId = UploadPbrAtlasTexture();
        CreateHardwareShadowMapFbo();

        _gpuMeshes.Clear();
        foreach (var kv in _archive.Meshes)
        {
            var lodHandles = new GpuMeshHandle[kv.Value.Lods.Length];
            for (int l = 0; l < kv.Value.Lods.Length; l++)
                lodHandles[l] = UploadMeshToGpu(kv.Value.Lods[l]);
            _gpuMeshes[kv.Key] = lodHandles;
        }
        _terrainGpu = UploadMeshToGpu(PlantationWorld.BuildSplattedTerrainMesh(136, 224f));
        _waterGpu = UploadMeshToGpu(PlantationWorld.BuildCanalWaterMesh(64));
        _shadowDiscGpu = UploadMeshToGpu(PlantationWorld.BuildSoftShadowDiscMesh(16));

        GLES30.GlEnable(GLES30.GlDepthTest);
        GLES30.GlDisable(0x0B44);

        string gpuRenderer = GLES30.GlGetString(GLES30.GlRenderer) ?? "";
        if (gpuRenderer.Contains("SwiftShader", StringComparison.OrdinalIgnoreCase) ||
            gpuRenderer.Contains("llvmpipe", StringComparison.OrdinalIgnoreCase))
        {
            // Software CPU rasterizer detected: optimize render scale & single-tap shadow filter for high FPS!
            Quality.CustomRenderScale ??= 0.72f;
            if (Quality.ShadowTier == ShadowQualityTier.High)
                Quality.ShadowTier = ShadowQualityTier.Medium;
            SyncRenderScaleNow();
        }

        _gpuReady = true;
        _lastTimeSec = _clock.Elapsed.TotalSeconds;
        _stageEnterSec = _lastTimeSec;
    }

    private int UploadPbrAtlasTexture()
    {
        int[] tex = new int[1];
        GLES30.GlGenTextures(1, tex, 0);
        GLES30.GlBindTexture(GLES30.GlTexture2d, tex[0]);

        var opts = new BitmapFactory.Options
        {
            InScaled = false,
            InPremultiplied = false,
            InPreferredConfig = Bitmap.Config.Argb8888,
        };
        using var stream = _context!.Assets!.Open("Textures/nyawit_pbr_atlas.png");
        using var bmp = BitmapFactory.DecodeStream(stream, null, opts);
        if (bmp != null)
        {
            GLUtils.TexImage2D(GLES30.GlTexture2d, 0, bmp, 0);
            GLES30.GlGenerateMipmap(GLES30.GlTexture2d);
        }

        GLES30.GlTexParameteri(GLES30.GlTexture2d, GLES30.GlTextureMinFilter, GLES30.GlLinearMipmapLinear);
        GLES30.GlTexParameteri(GLES30.GlTexture2d, GLES30.GlTextureMagFilter, GLES30.GlLinear);
        GLES30.GlTexParameteri(GLES30.GlTexture2d, GLES30.GlTextureWrapS, GLES30.GlRepeat);
        GLES30.GlTexParameteri(GLES30.GlTexture2d, GLES30.GlTextureWrapT, GLES30.GlRepeat);
        // Hardware anisotropic filtering (GL_TEXTURE_MAX_ANISOTROPY_EXT = 0x84FE) for razor-sharp roads at grazing angles!
        try { GLES30.GlTexParameterf(GLES30.GlTexture2d, 0x84FE, 8.0f); } catch { }
        return tex[0];
    }

    private void CreateHardwareShadowMapFbo()
    {
        int[] tex = new int[1];
        GLES30.GlGenTextures(1, tex, 0);
        _shadowMapDepthTex = tex[0];
        GLES30.GlBindTexture(GLES30.GlTexture2d, _shadowMapDepthTex);
        GLES30.GlTexImage2D(
            GLES30.GlTexture2d, 0, GLES30.GlDepthComponent16,
            ShadowMapSize, ShadowMapSize, 0,
            GLES30.GlDepthComponent, GLES30.GlUnsignedShort, null);
        GLES30.GlTexParameteri(GLES30.GlTexture2d, GLES30.GlTextureMinFilter, GLES30.GlNearest);
        GLES30.GlTexParameteri(GLES30.GlTexture2d, GLES30.GlTextureMagFilter, GLES30.GlNearest);
        GLES30.GlTexParameteri(GLES30.GlTexture2d, GLES30.GlTextureWrapS, GLES30.GlClampToEdge);
        GLES30.GlTexParameteri(GLES30.GlTexture2d, GLES30.GlTextureWrapT, GLES30.GlClampToEdge);

        int[] fbo = new int[1];
        GLES30.GlGenFramebuffers(1, fbo, 0);
        _shadowMapFbo = fbo[0];
        GLES30.GlBindFramebuffer(GLES30.GlFramebuffer, _shadowMapFbo);
        GLES30.GlFramebufferTexture2D(
            GLES30.GlFramebuffer, GLES30.GlDepthAttachment,
            GLES30.GlTexture2d, _shadowMapDepthTex, 0);
        GLES30.GlDrawBuffers(1, new int[] { GLES30.GlNone }, 0);
        GLES30.GlReadBuffer(GLES30.GlNone);
        if (GLES30.GlCheckFramebufferStatus(GLES30.GlFramebuffer) != GLES30.GlFramebufferComplete)
        {
            _shadowMapFbo = 0;
        }
        GLES30.GlBindFramebuffer(GLES30.GlFramebuffer, 0);
    }

    public void OnSurfaceChanged(IGL10? gl, int width, int height)
    {
        _surfaceWidth = System.Math.Max(1, width);
        _surfaceHeight = System.Math.Max(1, height);
        GLES30.GlViewport(0, 0, _surfaceWidth, _surfaceHeight);
    }

    public void OnDrawFrame(IGL10? gl)
    {
        if (_net == null || _program == 0) return;

        // Precision frame limiter when user selects battery-saving 30 FPS in Pengaturan!
        int targetFps = Quality.TargetFps;
        if (targetFps > 0 && targetFps <= 45)
        {
            double minFrameSec = 1.0 / targetFps;
            double elapsed = _clock.Elapsed.TotalSeconds - _lastTimeSec;
            if (elapsed < minFrameSec - 0.002)
            {
                int sleepMs = (int)((minFrameSec - elapsed) * 1000.0);
                if (sleepMs > 1) Thread.Sleep(System.Math.Min(sleepMs, 24));
            }
        }

        double now = _clock.Elapsed.TotalSeconds;
        float dt = (float)System.Math.Clamp(now - _lastTimeSec, 0.001, 0.05);
        _lastTimeSec = now;
        Time.TotalTime = (float)now;
        Time.DeltaTime = dt;
        if (Quality.RecordFrame(dt))
            SyncRenderScaleNow();
        System.Threading.Interlocked.Increment(ref _presentedFrameCount);

        if (Stage == AppSceneStage.Splash)
        {
            StepBootSplash(dt);
            GLES30.GlViewport(0, 0, _surfaceWidth, _surfaceHeight);
            GLES30.GlClearColor(0.035f, 0.045f, 0.052f, 1.0f);
            GLES30.GlClear(GLES30.GlColorBufferBit | GLES30.GlDepthBufferBit);
            return;
        }

        if (Stage == AppSceneStage.Lobby)
        {
            Physics.Player.IdleBreathPhase += dt * 2.15f;
            RenderDedicatedGarageShowroom((float)now, dt);
            return;
        }

        if (Stage == AppSceneStage.PreparingWorld)
        {
            StepWorldPreparation(dt);
        }
        else
        {
            StepGameplayPhysics(dt, now);
            StepVfxParticles(dt);
        }

        RenderPlantationWorld((float)now, dt);
    }

    private void StepBootSplash(float dt)
    {
        if (!_gpuReady) return;
        if (!HoldStageProgress)
        {
            if (_stageEnterSec <= 0.001) _stageEnterSec = _clock.Elapsed.TotalSeconds;
            float elapsed = (float)(_clock.Elapsed.TotalSeconds - _stageEnterSec);
            SplashProgress = System.Math.Clamp(elapsed / 2.2f, 0.05f, 1.0f);
        }
        if (SplashProgress < 0.35f)
            SplashStatus = "INISIALISASI SHADER PBR & 6-PLANE FRUSTUM CULLER...";
        else if (SplashProgress < 0.72f)
            SplashStatus = "MEMUAT ATLAS TEKSTUR 2048x2048 & 57 MODEL 3D...";
        else
            SplashStatus = "MEMBUKA GARASI SHOWROOM SAWIT...";

        if (!HoldStageProgress && SplashProgress >= 1.0f)
            SetStage(AppSceneStage.Lobby);
    }

    private void StepWorldPreparation(float dt)
    {
        if (!_gpuReady) return;
        if (!HoldStageProgress)
        {
            float elapsed = (float)(_clock.Elapsed.TotalSeconds - _stageEnterSec);
            WorldPrepProgress = System.Math.Clamp(elapsed / 2.2f, 0.05f, 1.0f);
        }

        if (WorldPrepProgress < 0.28f)
            WorldPrepStatus = "MEMBANGUN TOPOGRAFI JALAN TANAH MERAH & PARIT...";
        else if (WorldPrepProgress < 0.56f)
            WorldPrepStatus = $"MEMUAT {Physics.StaticColliders.Count} COLLIDER FISIKA SOLID & BAYANGAN POHON...";
        else if (WorldPrepProgress < 0.84f)
            WorldPrepStatus = "MENYIAPKAN SUSPENSI BAN DOBEL MITSUBISHI CANTER...";
        else
            WorldPrepStatus = $"SINKRONISASI SERVER LIVE ({_net?.CurrentRoomId.ToUpperInvariant()})...";

        Physics.StepWorld(dt, inTruck: false, inputSide: 0f, inputForward: 0f, camYaw: CamYaw, boars: _boarsSnap);

        if (!HoldStageProgress && WorldPrepProgress >= 1.0f)
        {
            SetStage(AppSceneStage.Gameplay);
            OnWorldReady?.Invoke();
        }
    }

    private void StepGameplayPhysics(float dt, double now)
    {
        if (_net == null) return;
        if (BoostTimer > 0f) BoostTimer -= dt;
        float boostScale = BoostTimer > 0f ? 1.38f : 1.0f;

        Physics.StepWorld(
            dt,
            inTruck: InTruck,
            inputSide: JoyX,
            inputForward: (-JoyY) * boostScale,
            camYaw: CamYaw,
            boars: _boarsSnap);

        // Emit terrain-conforming herringbone tire tracks behind Canter dual rear wheels!
        float speedAbs = MathF.Abs(Physics.MainTruck.SpeedMs);
        if (speedAbs > 0.65f)
        {
            if (float.IsNaN(_lastTrackX))
            {
                _lastTrackX = Physics.MainTruck.X;
                _lastTrackZ = Physics.MainTruck.Z;
            }
            float tdx = Physics.MainTruck.X - _lastTrackX;
            float tdz = Physics.MainTruck.Z - _lastTrackZ;
            if (tdx * tdx + tdz * tdz >= 0.72f * 0.72f)
            {
                _lastTrackX = Physics.MainTruck.X;
                _lastTrackZ = Physics.MainTruck.Z;
                float sy = MathF.Sin(Physics.MainTruck.Yaw), cy = MathF.Cos(Physics.MainTruck.Yaw);
                float rearAxleX = Physics.MainTruck.X - 1.25f * sy;
                float rearAxleZ = Physics.MainTruck.Z - 1.25f * cy;
                EmitTireTrackAt(rearAxleX - 0.84f * cy, rearAxleZ + 0.84f * sy, Physics.MainTruck.Yaw);
                EmitTireTrackAt(rearAxleX + 0.84f * cy, rearAxleZ - 0.84f * sy, Physics.MainTruck.Yaw);
            }
        }

        // Emit realistic tire dust behind Canter dual rear wheels + diesel exhaust smoke!
        if (InTruck && Quality.ParticlesEnabled && speedAbs > 1.8f)
        {
            _dustEmitAccum += dt * (4.0f + speedAbs * 0.85f);
            while (_dustEmitAccum >= 1f)
            {
                _dustEmitAccum -= 1f;
                float sy = MathF.Sin(Physics.MainTruck.Yaw), cy = MathF.Cos(Physics.MainTruck.Yaw);
                float side = (_vfxCursor % 2 == 0) ? -0.92f : 0.92f;
                float wx = Physics.MainTruck.X + side * cy - 1.35f * sy;
                float wz = Physics.MainTruck.Z - side * sy - 1.35f * cy;
                SpawnParticle(
                    wx, Physics.MainTruck.Y + 0.26f, wz,
                    -sy * 0.8f + side * 0.25f, 0.55f, -cy * 0.8f,
                    0.35f, 1.35f, 0.44f, 0.33f, 0.22f, 0.42f, 0.85f);
            }

            _exhaustEmitAccum += dt * 6.5f;
            while (_exhaustEmitAccum >= 1f)
            {
                _exhaustEmitAccum -= 1f;
                float sy = MathF.Sin(Physics.MainTruck.Yaw), cy = MathF.Cos(Physics.MainTruck.Yaw);
                float exX = Physics.MainTruck.X + 0.86f * cy + 0.62f * sy;
                float exZ = Physics.MainTruck.Z - 0.86f * sy + 0.62f * cy;
                SpawnParticle(
                    exX, Physics.MainTruck.Y + 2.30f, exZ,
                    -sy * 0.5f, 1.35f, -cy * 0.5f,
                    0.18f, 0.72f, 0.14f, 0.15f, 0.16f, 0.36f, 0.75f);
            }
        }

        if (!LockShowcaseCam && InTruck && speedAbs > 0.6f)
        {
            float desiredCamYaw = Physics.MainTruck.Yaw + MathF.PI;
            float diff = desiredCamYaw - CamYaw;
            while (diff > MathF.PI) diff -= MathF.PI * 2f;
            while (diff < -MathF.PI) diff += MathF.PI * 2f;
            CamYaw += diff * MathF.Min(1f, dt * 3.1f);
        }

        float bestD2 = InTruck ? 56.0f : 38.5f;
        int bestId = -1;
        for (int i = 0; i < _trees.Count; i++)
        {
            var t = _trees[i];
            if (t.State == 0) continue;
            float dx = t.X - PlayerX, dz = t.Z - PlayerZ;
            float d2 = dx * dx + dz * dz;
            if (d2 < bestD2) { bestD2 = d2; bestId = i; }
        }
        NearestRipeTreeId = bestId;

        NearbyGroundFruitCount = InTruck ? 0 : Physics.CountNearbyGroundFruits(3.8f);
        NearbyAngkongId = InTruck ? -1 : Physics.FindNearbyAngkong(3.2f);
        CanLoadIntoVehicleOrCart = !InTruck && (
            (Physics.Player.HasHeldTbs && (Physics.IsNearMainTruck(5.6f) || NearbyAngkongId >= 0)) ||
            (Physics.IsNearMainTruck(5.6f) && NearbyAngkongId >= 0 && Physics.Angkongs[NearbyAngkongId].CargoUnits > 0));

        int totalSellableCargo = _net.LocalCargo
            + Physics.Player.HeldTbsUnits
            + (NearbyAngkongId >= 0 ? Physics.Angkongs[NearbyAngkongId].CargoUnits : 0);
        float rdx = PlayerX - PlantationWorld.RamX, rdz = PlayerZ - PlantationWorld.RamZ;
        NearRamWeighbridge = totalSellableCargo > 0 && MathF.Sqrt(rdx * rdx + rdz * rdz) < 11.5f;

        float sdx = PlayerX - PlantationWorld.SpbuX, sdz = PlayerZ - PlantationWorld.SpbuZ;
        NearSpbuSolar = (sdx * sdx + sdz * sdz) < 8.5f * 8.5f;

        float wdx = PlayerX - PlantationWorld.WarungX, wdz = PlayerZ - PlantationWorld.WarungZ;
        NearWarungKopi = !InTruck && (wdx * wdx + wdz * wdz) < 6.5f * 6.5f;

        // Ambient drifting Riau peatland ash-smoke wisps when Sumatra Karhutla Haze mode is active!
        if (Quality.Atmosphere == AtmospherePreset.KarhutlaSmoke && Quality.ParticlesEnabled)
        {
            _karhutlaHazeAccum += dt * 9.0f;
            while (_karhutlaHazeAccum >= 1f)
            {
                _karhutlaHazeAccum -= 1f;
                float ang = (_vfxCursor * 2.39996f) + (float)now * 0.35f;
                float rad = 4.0f + (_vfxCursor % 7) * 2.5f;
                float sx = PlayerX + MathF.Cos(ang) * rad;
                float sz = PlayerZ + MathF.Sin(ang) * rad;
                float sy = PlantationWorld.TerrainHeight(sx, sz) + 0.55f + (_vfxCursor % 5) * 0.42f;
                SpawnParticle(
                    sx, sy, sz,
                    0.48f, 0.22f, 0.28f,
                    1.35f, 3.25f, 0.66f, 0.64f, 0.60f, 0.26f, 2.6f);
            }
        }

        if (now >= _nextNetSyncSec)
        {
            _nextNetSyncSec = now + 0.085;
            int anim = Physics.Player.SlashTimer > 0.05f ? 2 : (Physics.Player.MoveSpeedMs > 0.4f ? 1 : 0);
            _net.SendPlayerState(
                PlayerX, PlayerY, PlayerZ, Physics.Player.Yaw,
                anim, InTruck,
                carryingTbs: Physics.Player.HasHeldTbs,
                pushingAngkong: Physics.Player.ActiveAngkongIndex >= 0,
                steerAngle: InTruck ? Physics.MainTruck.SteerAngle : 0f);
        }
    }

    /// <summary>
    /// Dedicated Separate 3D Garage/Workshop Lobby Scene!
    /// Completely isolated from the 180-tree plantation map -> < 15 draw calls -> locked 60-120 FPS!
    /// </summary>
    private void RenderDedicatedGarageShowroom(float now, float dt)
    {
        if (_net == null) return;
        GLES30.GlBindFramebuffer(GLES30.GlFramebuffer, 0);
        GLES30.GlViewport(0, 0, _surfaceWidth, _surfaceHeight);
        GLES30.GlClearColor(0.06f, 0.09f, 0.13f, 1.0f);
        GLES30.GlClear(GLES30.GlColorBufferBit | GLES30.GlDepthBufferBit);

        float orbit = LobbyOrbitYaw + MathF.Sin(now * 0.45f) * 0.045f;
        float lookX = -0.35f, lookY = 1.36f, lookZ = -0.25f;
        float eyeX = lookX + MathF.Sin(orbit) * 6.95f;
        float eyeY = 2.08f;
        float eyeZ = lookZ + MathF.Cos(orbit) * 6.95f;

        Mat4Utils.CreatePerspective(_proj, 42f * MathF.PI / 180f, _surfaceWidth / (float)_surfaceHeight, 0.25f, 120f);
        Mat4Utils.CreateLookAt(_view, eyeX, eyeY, eyeZ, lookX, lookY, lookZ);
        Mat4Utils.Multiply(_vp, _proj, _view);
        InvertMatrix4(_vp, _invVp);
        Array.Clear(_lightVp, 0, 16);
        _lightVp[0] = _lightVp[5] = _lightVp[10] = _lightVp[15] = 1f;

        int drawCalls = 0, tris = 0;

        // Open-front garage sky glimpse through workshop entrance
        GLES30.GlDepthMask(false);
        GLES30.GlDisable(GLES30.GlDepthTest);
        GLES30.GlUseProgram(_skyProgram);
        GLES30.GlUniformMatrix4fv(_uSkyInvVp, 1, false, _invVp, 0);
        GLES30.GlUniform3f(_uSkySunDir, 0.35f, 0.65f, 0.66f);
        if (Quality.Atmosphere == AtmospherePreset.KarhutlaSmoke)
        {
            GLES30.GlUniform3f(_uSkyZenith, 0.16f, 0.15f, 0.13f);
            GLES30.GlUniform3f(_uSkyHorizon, 0.36f, 0.34f, 0.30f);
            GLES30.GlUniform3f(_uSkySunCol, 0.88f, 0.48f, 0.20f);
        }
        else
        {
            GLES30.GlUniform3f(_uSkyZenith, 0.042f, 0.088f, 0.185f);
            GLES30.GlUniform3f(_uSkyHorizon, 0.26f, 0.34f, 0.44f);
            GLES30.GlUniform3f(_uSkySunCol, 0.96f, 1.04f, 1.16f);
        }
        GLES30.GlUniform1f(_uSkyTime, now);
        GLES30.GlUniform1f(_uSkyClouds, Quality.CloudsEnabled ? 1f : 0f);
        GLES30.GlBindVertexArray(_skyVao);
        GLES30.GlDrawArrays(GLES30.GlTriangleStrip, 0, 4);
        drawCalls++;
        tris += 2;
        GLES30.GlEnable(GLES30.GlDepthTest);
        GLES30.GlDepthMask(true);

        BindAtlasAndShadowTextures();
        GLES30.GlUseProgram(_program);
        GLES30.GlUniformMatrix4fv(_uVp, 1, false, _vp, 0);
        GLES30.GlUniformMatrix4fv(_uLightVp, 1, false, _lightVp, 0);
        GLES30.GlUniform1f(_uTime, now);
        GLES30.GlUniform1i(_uAtlas, 0);
        GLES30.GlUniform1i(_uShadowMap, 1);
        GLES30.GlUniform3f(_uSunDir, 0.28f, 0.80f, 0.53f);
        if (Quality.Atmosphere == AtmospherePreset.KarhutlaSmoke)
        {
            GLES30.GlUniform3f(_uSunColor, 1.25f, 1.02f, 0.78f);
            GLES30.GlUniform3f(_uSkyTop, 0.22f, 0.20f, 0.18f);
            GLES30.GlUniform3f(_uGroundBounce, 0.06f, 0.055f, 0.045f);
            GLES30.GlUniform3f(_uFogColor, 0.36f, 0.34f, 0.30f);
        }
        else
        {
            GLES30.GlUniform3f(_uSunColor, 1.56f, 1.64f, 1.76f);
            GLES30.GlUniform3f(_uSkyTop, 0.18f, 0.25f, 0.35f);
            GLES30.GlUniform3f(_uGroundBounce, 0.055f, 0.068f, 0.082f);
            GLES30.GlUniform3f(_uFogColor, 0.12f, 0.16f, 0.22f);
        }
        GLES30.GlUniform3f(_uCamPos, eyeX, eyeY, eyeZ);
        GLES30.GlUniform1f(_uFogDensity, 0.001f);
        GLES30.GlUniform1i(_uRenderMode, 0);
        GLES30.GlUniform1i(_uShadowMode, 0);
        GLES30.GlUniform1f(_uCloudsOn, 0f);
        GLES30.GlUniform1i(_uAtmoPreset, (int)Quality.Atmosphere);
        ConfigureAnimeOutlineUniforms();

        // 1. Workshop Garage Interior + Turntable + Workbench + Spare Tires + Oil Drums
        _allowOutlinePass = false;
        int c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, 0f, 0f, 0f, 0f, 0f, 0f, 1f, 1f, 1f);
        DrawNamed(MeshCatalog.GarageShowroom, 0, _instStaging, c, ref drawCalls, ref tris);

        // Soft showroom contact shadows on the turntable
        int nSh = 0;
        nSh = Mat4Utils.WriteInstanceTRS(_shadowStaging, nSh, 1.15f, 0.085f, -0.55f, 0f, -0.56f, 0f, 1.48f, 1f, 2.95f, 1.0f);
        nSh = Mat4Utils.WriteInstanceTRS(_shadowStaging, nSh, -1.35f, 0.085f, 1.25f, 0f, 0f, 0f, 0.65f, 1f, 0.65f, 1.0f);
        nSh = Mat4Utils.WriteInstanceTRS(_shadowStaging, nSh, -3.55f, 0.085f, -1.65f, 0f, 0.52f, 0f, 0.68f, 1f, 0.96f, 0.9f);
        GLES30.GlUseProgram(_contactShadowProgram);
        GLES30.GlUniformMatrix4fv(_uContactVp, 1, false, _vp, 0);
        GLES30.GlEnable(GLES30.GlBlend);
        GLES30.GlBlendFunc(GLES30.GlSrcAlpha, GLES30.GlOneMinusSrcAlpha);
        GLES30.GlDepthMask(false);
        DrawGpuHandle(_shadowDiscGpu, _shadowStaging, nSh, ref drawCalls, ref tris);
        GLES30.GlDepthMask(true);
        GLES30.GlDisable(GLES30.GlBlend);
        GLES30.GlUseProgram(_program);
        _allowOutlinePass = true;

        // 2. Workshop Angkong Cart beside tool bench
        var lobbyCart = Mat4Utils.BoneMat.TRS(-3.55f, 0.08f, -1.65f, 0f, 0.52f, 0f);
        DrawNamed(MeshCatalog.AngkongCart, 0, _instStaging, lobbyCart.Emit(_instStaging, 0), ref drawCalls, ref tris);
        DrawNamed(MeshCatalog.TruckWheel, 0, _goldStaging,
            lobbyCart.Child(0f, 0.29f, 0.80f, sx: 0.45f, sy: 0.59f, sz: 0.59f).Emit(_goldStaging, 0),
            ref drawCalls, ref tris);

        // 3. Heroic Showroom Mitsubishi Canter COE Bak Kayu with full TBS cargo & steered front wheels!
        var showroomTruck = new VehicleRigidBody
        {
            X = 1.15f,
            Y = 0.08f,
            Z = -0.55f,
            Yaw = -0.56f,
            SteerAngle = 0.36f,
        };
        for (int w = 0; w < 4; w++) showroomTruck.WheelWorldY[w] = 0.08f + 0.48f;
        DrawCanterVehicleRig(showroomTruck, _net.Profile.Avatar, System.Math.Max(14, _net.LocalCargo), hasDriver: false, ref drawCalls, ref tris);

        // 4. Local Harvester Character on Turntable Foreground with full live outfit/accessories!
        DrawDetailedHumanRig(
            -1.35f, 0.08f, 1.25f, 0.28f + LobbyAvatarSpinOffset,
            walkPhase: 0f,
            breathPhase: Physics.Player.IdleBreathPhase,
            moving: false,
            stance: HoldStance.TwoHandTool,
            slashTimer: 0f,
            pickupTimer: 0f,
            throwTimer: 0f,
            heldGold: false,
            av: _net.Profile.Avatar,
            dt: dt,
            useSmoothState: true,
            ref drawCalls, ref tris);

        LastDrawCalls = drawCalls;
        LastTriangles = tris;
        lock (HudLock)
        {
            ProjectedLabels.Clear();
            MinimapPeers.Clear();
        }
    }

    private void RenderPlantationWorld(float now, float dt)
    {
        if (_net == null) return;
        var q = Quality.Active;
        bool storm = _net.EventKind == "HUJAN_BADAI";
        bool goldRush = _net.EventKind == "DEMAM_SAWIT_EMAS";

        float eyeX, eyeY, eyeZ, lookX, lookY, lookZ, fovDeg;
        if (Stage == AppSceneStage.PreparingWorld)
        {
            float t = WorldPrepProgress;
            float ease = t * t * (3f - 2f * t);
            float dist = (1f - ease) * 32f + ease * CamDist;
            float pitch = (1f - ease) * 0.68f + ease * CamPitch;
            float yaw = CamYaw + (1f - ease) * 1.05f;
            eyeX = PlayerX + MathF.Sin(yaw) * MathF.Cos(pitch) * dist;
            eyeZ = PlayerZ + MathF.Cos(yaw) * MathF.Cos(pitch) * dist;
            eyeY = System.Math.Max(PlantationWorld.TerrainHeight(eyeX, eyeZ) + 1.25f, PlayerY + 1.60f + MathF.Sin(pitch) * dist);
            lookX = PlayerX;
            lookY = PlayerY + 1.42f;
            lookZ = PlayerZ;
            fovDeg = 54f;
        }
        else
        {
            if (LockShowcaseCam && InTruck)
                CamYaw = Physics.MainTruck.Yaw + 0.68f;

            float dist = InTruck ? (LockShowcaseCam ? CamDist : CamDist * 1.22f) : CamDist;
            eyeX = PlayerX + MathF.Sin(CamYaw) * MathF.Cos(CamPitch) * dist;
            eyeZ = PlayerZ + MathF.Cos(CamYaw) * MathF.Cos(CamPitch) * dist;
            float baseEyeH = LockShowcaseCam ? (InTruck ? 1.05f : 1.16f) : 1.60f;
            eyeY = System.Math.Max(PlantationWorld.TerrainHeight(eyeX, eyeZ) + (LockShowcaseCam ? 0.85f : 1.25f), PlayerY + baseEyeH + MathF.Sin(CamPitch) * dist);
            lookX = PlayerX;
            lookY = PlayerY + (LockShowcaseCam ? (InTruck ? 1.18f : 1.20f) : (InTruck ? 1.66f : 1.38f));
            lookZ = PlayerZ;
            fovDeg = LockShowcaseCam ? 47f : 56f;
        }

        _net.CopyRenderState(_peersSnap, _boarsSnap, _chatSnap, dt);

        Mat4Utils.CreatePerspective(_proj, fovDeg * MathF.PI / 180f, _surfaceWidth / (float)_surfaceHeight, 0.30f, 260f);
        Mat4Utils.CreateLookAt(_view, eyeX, eyeY, eyeZ, lookX, lookY, lookZ);
        Mat4Utils.Multiply(_vp, _proj, _view);
        InvertMatrix4(_vp, _invVp);

        SimdCuller.ExtractFrustumPlanes(_vp, _frustumPlanes24);
        SimdCuller.CullFrustum6Plane(
            _treePositionsXyz, _trees.Count, _frustumPlanes24,
            eyeX, eyeY, eyeZ, centerYOffset: 4.5f, boundRadius: 5.5f,
            q.Lod0Distance, q.Lod1Distance, q.MaxDrawDistance, _treeLodResult);
        SimdCuller.CullFrustum6Plane(
            _saplingPositionsXyz, _saplings.Count, _frustumPlanes24,
            eyeX, eyeY, eyeZ, centerYOffset: 0.7f, boundRadius: 1.65f,
            q.Lod0Distance, q.Lod1Distance, q.MaxDrawDistance, _saplingLodResult);

        int drawCalls = 0, tris = 0;
        float windAmp = storm ? 2.0f : 0.82f;
        _allowOutlinePass = false;

        // Pass A: Hardware 1024x1024 Directional Sun Shadow Map Pass!
        int activeShadowMode = (_shadowMapFbo != 0 && Quality.ShadowTier != ShadowQualityTier.Off)
            ? (int)Quality.ShadowTier
            : 0;
        if (activeShadowMode > 0)
        {
            UpdateSunShadowMatrix(PlayerX, PlayerY, PlayerZ);
            GLES30.GlBindFramebuffer(GLES30.GlFramebuffer, _shadowMapFbo);
            GLES30.GlViewport(0, 0, ShadowMapSize, ShadowMapSize);
            GLES30.GlClear(GLES30.GlDepthBufferBit);
            GLES30.GlColorMask(false, false, false, false);

            GLES30.GlActiveTexture(GLES30.GlTexture0);
            GLES30.GlBindTexture(GLES30.GlTexture2d, _atlasTexId);
            GLES30.GlUseProgram(_depthShadowProgram);
            GLES30.GlUniformMatrix4fv(_uDepthLightVp, 1, false, _lightVp, 0);
            GLES30.GlUniform1f(_uDepthTime, now);
            GLES30.GlUniform1i(_uDepthAtlas, 0);

            RenderShadowCasters(windAmp, ref drawCalls, ref tris);

            GLES30.GlColorMask(true, true, true, true);
            GLES30.GlBindFramebuffer(GLES30.GlFramebuffer, 0);
        }

        // Pass B: Main Color + Depth Framebuffer Pass
        GLES30.GlViewport(0, 0, _surfaceWidth, _surfaceHeight);
        if (Quality.Atmosphere == AtmospherePreset.KarhutlaSmoke)
            GLES30.GlClearColor(0.36f, 0.34f, 0.30f, 1.0f);
        else
            GLES30.GlClearColor(0.16f, 0.24f, 0.34f, 1.0f);
        GLES30.GlClear(GLES30.GlColorBufferBit | GLES30.GlDepthBufferBit);

        // Volumetric Cumulus Sky Dome
        GLES30.GlDepthMask(false);
        GLES30.GlDisable(GLES30.GlDepthTest);
        GLES30.GlUseProgram(_skyProgram);
        GLES30.GlUniformMatrix4fv(_uSkyInvVp, 1, false, _invVp, 0);
        GLES30.GlUniform3f(_uSkySunDir, 0.48f, 0.72f, 0.44f);
        GLES30.GlUniform1f(_uSkyTime, now);
        GLES30.GlUniform1f(_uSkyClouds, Quality.CloudsEnabled ? 1f : 0f);
        if (storm)
        {
            GLES30.GlUniform3f(_uSkyZenith, 0.03f, 0.06f, 0.12f);
            GLES30.GlUniform3f(_uSkyHorizon, 0.14f, 0.19f, 0.26f);
            GLES30.GlUniform3f(_uSkySunCol, 0.32f, 0.38f, 0.50f);
        }
        else if (goldRush)
        {
            GLES30.GlUniform3f(_uSkyZenith, 0.06f, 0.18f, 0.44f);
            GLES30.GlUniform3f(_uSkyHorizon, 0.56f, 0.40f, 0.22f);
            GLES30.GlUniform3f(_uSkySunCol, 1.45f, 1.02f, 0.46f);
        }
        else if (Quality.Atmosphere == AtmospherePreset.KarhutlaSmoke)
        {
            // Riau / Sumatera Dense Peatland Fire Smoke Canopy: choked ash-gray sky + dim blood-amber sun disc
            GLES30.GlUniform3f(_uSkyZenith, 0.17f, 0.16f, 0.14f);
            GLES30.GlUniform3f(_uSkyHorizon, 0.38f, 0.36f, 0.32f);
            GLES30.GlUniform3f(_uSkySunCol, 0.92f, 0.48f, 0.20f);
        }
        else if (Quality.Atmosphere == AtmospherePreset.SemiEnbCold)
        {
            // Bussid / GTA SA Mod ENB Dingin Sumatera: moody cool overcast steel-slate sky + dark-bellied rain clouds!
            GLES30.GlUniform3f(_uSkyZenith, 0.042f, 0.088f, 0.185f);
            GLES30.GlUniform3f(_uSkyHorizon, 0.27f, 0.35f, 0.45f);
            GLES30.GlUniform3f(_uSkySunCol, 1.02f, 1.12f, 1.26f);
        }
        else
        {
            GLES30.GlUniform3f(_uSkyZenith, 0.055f, 0.20f, 0.54f);
            GLES30.GlUniform3f(_uSkyHorizon, 0.42f, 0.58f, 0.74f);
            GLES30.GlUniform3f(_uSkySunCol, 1.38f, 1.24f, 0.96f);
        }
        GLES30.GlBindVertexArray(_skyVao);
        GLES30.GlDrawArrays(GLES30.GlTriangleStrip, 0, 4);
        drawCalls++;
        tris += 2;
        GLES30.GlEnable(GLES30.GlDepthTest);
        GLES30.GlDepthMask(true);

        BindAtlasAndShadowTextures();
        GLES30.GlUseProgram(_program);
        GLES30.GlUniformMatrix4fv(_uVp, 1, false, _vp, 0);
        GLES30.GlUniformMatrix4fv(_uLightVp, 1, false, _lightVp, 0);
        GLES30.GlUniform1f(_uTime, now);
        GLES30.GlUniform1i(_uAtlas, 0);
        GLES30.GlUniform1i(_uShadowMap, 1);
        GLES30.GlUniform3f(_uSunDir, 0.48f, 0.72f, 0.44f);
        GLES30.GlUniform3f(_uCamPos, eyeX, eyeY, eyeZ);
        GLES30.GlUniform1i(_uShadowMode, activeShadowMode);
        GLES30.GlUniform1f(_uCloudsOn, Quality.CloudsEnabled ? 1f : 0f);
        GLES30.GlUniform1i(_uAtmoPreset, storm || goldRush ? 2 : (int)Quality.Atmosphere);
        ConfigureAnimeOutlineUniforms();

        if (storm)
        {
            GLES30.GlUniform3f(_uSunColor, 0.72f, 0.82f, 0.98f);
            GLES30.GlUniform3f(_uSkyTop, 0.14f, 0.19f, 0.28f);
            GLES30.GlUniform3f(_uGroundBounce, 0.04f, 0.05f, 0.05f);
            GLES30.GlUniform3f(_uFogColor, 0.14f, 0.19f, 0.26f);
            GLES30.GlUniform1f(_uFogDensity, 0.009f);
        }
        else if (goldRush)
        {
            GLES30.GlUniform3f(_uSunColor, 1.85f, 1.42f, 0.85f);
            GLES30.GlUniform3f(_uSkyTop, 0.28f, 0.24f, 0.20f);
            GLES30.GlUniform3f(_uGroundBounce, 0.08f, 0.06f, 0.04f);
            GLES30.GlUniform3f(_uFogColor, 0.48f, 0.36f, 0.22f);
            GLES30.GlUniform1f(_uFogDensity, 0.004f);
        }
        else if (Quality.Atmosphere == AtmospherePreset.KarhutlaSmoke)
        {
            // Authentic Riau / Jambi Peatland Karhutla Smoke: diffused dimmed sun + thick whitish-ash-gray haze
            GLES30.GlUniform3f(_uSunColor, 1.18f, 0.96f, 0.74f);
            GLES30.GlUniform3f(_uSkyTop, 0.22f, 0.21f, 0.19f);
            GLES30.GlUniform3f(_uGroundBounce, 0.065f, 0.060f, 0.052f);
            GLES30.GlUniform3f(_uFogColor, 0.38f, 0.36f, 0.32f);
            GLES30.GlUniform1f(_uFogDensity, 0.015f);
        }
        else if (Quality.Atmosphere == AtmospherePreset.SemiEnbCold)
        {
            // Bussid / GTA SA Mod ENB Dingin Sumatera: crisp cool key light + deep steel-slate shadows + morning mist
            GLES30.GlUniform3f(_uSunColor, 1.58f, 1.66f, 1.78f);
            GLES30.GlUniform3f(_uSkyTop, 0.16f, 0.22f, 0.31f);
            GLES30.GlUniform3f(_uGroundBounce, 0.045f, 0.056f, 0.062f);
            GLES30.GlUniform3f(_uFogColor, 0.25f, 0.32f, 0.41f);
            GLES30.GlUniform1f(_uFogDensity, 0.0045f);
        }
        else
        {
            GLES30.GlUniform3f(_uSunColor, 1.78f, 1.66f, 1.38f);
            GLES30.GlUniform3f(_uSkyTop, 0.22f, 0.32f, 0.46f);
            GLES30.GlUniform3f(_uGroundBounce, 0.068f, 0.082f, 0.058f);
            GLES30.GlUniform3f(_uFogColor, 0.38f, 0.52f, 0.68f);
            GLES30.GlUniform1f(_uFogDensity, 0.0030f);
        }

        // 1. Multi-Scale Splatmapped Terrain (Mode 1) & Canal Water (Mode 0)
        GLES30.GlUniform1i(_uRenderMode, 1);
        int c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1);
        DrawGpuHandle(_terrainGpu, _instStaging, c, ref drawCalls, ref tris);

        GLES30.GlUniform1i(_uRenderMode, 0);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, 0, MathF.Sin(now * 1.4f) * 0.03f, 0, 0, 0, 0, 1, 1, 1);
        DrawGpuHandle(_waterGpu, _instStaging, c, ref drawCalls, ref tris);

        // Soft grounding contact AO discs (plus distant tree canopy discs beyond the 34m shadow map!)
        int nSh = 0;
        nSh = Mat4Utils.WriteInstanceTRS(_shadowStaging, nSh, Physics.MainTruck.X, Physics.MainTruck.Y, Physics.MainTruck.Z, 0, Physics.MainTruck.Yaw, 0, 1.45f, 1f, 2.95f, 0.72f);
        nSh = Mat4Utils.WriteInstanceTRS(_shadowStaging, nSh, Physics.YardTruck.X, Physics.YardTruck.Y, Physics.YardTruck.Z, 0, Physics.YardTruck.Yaw, 0, 1.45f, 1f, 2.95f, 0.72f);
        if (!InTruck)
            nSh = Mat4Utils.WriteInstanceTRS(_shadowStaging, nSh, PlayerX, Physics.Player.GroundedY, PlayerZ, 0, Physics.Player.Yaw, 0, 0.62f, 1f, 0.62f, 0.78f);

        for (int i = 0; i < _trees.Count; i++)
        {
            sbyte tier = _treeLodResult[i];
            if (tier < 0) continue;
            var t = _trees[i];
            float d2 = (t.X - PlayerX) * (t.X - PlayerX) + (t.Z - PlayerZ) * (t.Z - PlayerZ);
            if (activeShadowMode > 0 && d2 < 26f * 26f) continue; // Real 1024x1024 shadow map handles nearby trees!
            nSh = Mat4Utils.WriteInstanceTRS(_shadowStaging, nSh, t.X + 0.55f, t.Y, t.Z + 0.45f, 0, 0, 0, 3.25f * t.Scale, 1f, 3.25f * t.Scale, tier == 2 ? 0.52f : 0.78f);
        }
        if (nSh > 0)
        {
            GLES30.GlUseProgram(_contactShadowProgram);
            GLES30.GlUniformMatrix4fv(_uContactVp, 1, false, _vp, 0);
            GLES30.GlEnable(GLES30.GlBlend);
            GLES30.GlBlendFunc(GLES30.GlSrcAlpha, GLES30.GlOneMinusSrcAlpha);
            GLES30.GlDepthMask(false);
            DrawGpuHandle(_shadowDiscGpu, _shadowStaging, nSh, ref drawCalls, ref tris);
            GLES30.GlDepthMask(true);
            GLES30.GlDisable(GLES30.GlBlend);
            GLES30.GlUseProgram(_program);
        }

        _allowOutlinePass = true;

        // 2. PKS Mill + Turbines + Weighbridge RAM + Mandor Post + Wooden Bridges
        float pksGround = PlantationWorld.TerrainHeight(PlantationWorld.PksX, PlantationWorld.PksZ);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, PlantationWorld.PksX, pksGround, PlantationWorld.PksZ, 0, 0, 0, 1, 1, 1);
        DrawNamed(MeshCatalog.PksFactory, 0, _instStaging, c, ref drawCalls, ref tris);

        c = 0;
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, PlantationWorld.PksX - 1.5f, pksGround + 8.35f, PlantationWorld.PksZ - 1.6f, 0, now * 5.2f, 0, 1, 1, 1);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, PlantationWorld.PksX + 1.5f, pksGround + 8.35f, PlantationWorld.PksZ + 1.6f, 0, -now * 4.6f, 0, 1, 1, 1);
        DrawNamed(MeshCatalog.PksFan, 0, _instStaging, c, ref drawCalls, ref tris);

        c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, PlantationWorld.RamX, PlantationWorld.TerrainHeight(PlantationWorld.RamX, PlantationWorld.RamZ), PlantationWorld.RamZ, 0, 0, 0, 1, 1, 1);
        DrawNamed(MeshCatalog.WeighbridgeRam, 0, _instStaging, c, ref drawCalls, ref tris);

        c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, PlantationWorld.MandorX, PlantationWorld.TerrainHeight(PlantationWorld.MandorX, PlantationWorld.MandorZ), PlantationWorld.MandorZ, 0, 0.5f, 0, 1, 1, 1);
        DrawNamed(MeshCatalog.MandorPost, 0, _instStaging, c, ref drawCalls, ref tris);

        c = 0;
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, -28f, PlantationWorld.TerrainHeight(-28f, PlantationWorld.CanalZ - 4.7f), PlantationWorld.CanalZ, 0, 0, 0, 1, 1, 1);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, 28f, PlantationWorld.TerrainHeight(28f, PlantationWorld.CanalZ - 4.7f), PlantationWorld.CanalZ, 0, 0, 0, 1, 1, 1);
        DrawNamed(MeshCatalog.WoodenBridge, 0, _instStaging, c, ref drawCalls, ref tris);

        // 2.2. v6.0 Expanded Estate Landmarks & Interactive Field Props (SPBU Solar, Warung Kopi, Gudang Pupuk, Gapura Offroad)
        float spbuY = PlantationWorld.TerrainHeight(PlantationWorld.SpbuX, PlantationWorld.SpbuZ);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, PlantationWorld.SpbuX, spbuY, PlantationWorld.SpbuZ, 0f, PlantationWorld.SpbuRotY, 0f, 1f, 1f, 1f);
        DrawNamed(MeshCatalog.SpbuSolar, 0, _instStaging, c, ref drawCalls, ref tris);

        c = 0;
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, PlantationWorld.SpbuX - 2.35f, spbuY, PlantationWorld.SpbuZ - 1.35f, 0f, 0.35f, 0f, 1f, 1f, 1f);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, PlantationWorld.SpbuX - 2.35f, spbuY, PlantationWorld.SpbuZ - 0.85f, 0f, -0.22f, 0f, 1f, 1f, 1f);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, PlantationWorld.SpbuX - 2.10f, spbuY, PlantationWorld.SpbuZ + 1.55f, 0f, 0.78f, 0f, 1f, 1f, 1f);
        DrawNamed(MeshCatalog.ItemSolarCan, 0, _instStaging, c, ref drawCalls, ref tris);

        float warungY = PlantationWorld.TerrainHeight(PlantationWorld.WarungX, PlantationWorld.WarungZ);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, PlantationWorld.WarungX, warungY, PlantationWorld.WarungZ, 0f, PlantationWorld.WarungRotY, 0f, 1f, 1f, 1f);
        DrawNamed(MeshCatalog.WarungKopi, 0, _instStaging, c, ref drawCalls, ref tris);

        c = 0;
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, PlantationWorld.WarungX + 1.85f, warungY + 0.88f, PlantationWorld.WarungZ - 0.55f, 0f, 0.4f, 0f, 0.9f, 0.9f, 0.9f);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, PlantationWorld.WarungX + 1.85f, warungY + 0.88f, PlantationWorld.WarungZ + 0.35f, 0f, -0.6f, 0f, 0.9f, 0.9f, 0.9f);
        DrawNamed(MeshCatalog.ItemCoffeeCup, 0, _instStaging, c, ref drawCalls, ref tris);

        c = 0;
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, PlantationWorld.WarungX + 2.45f, warungY, PlantationWorld.WarungZ + 1.85f, 0f, 0.25f, 0f, 1f, 1f, 1f);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, PlantationWorld.WarungX + 2.45f, warungY + 0.46f, PlantationWorld.WarungZ + 1.85f, 0f, 0.55f, 0f, 0.95f, 0.95f, 0.95f);
        DrawNamed(MeshCatalog.ItemCuanCrate, 0, _instStaging, c, ref drawCalls, ref tris);

        float gudangY = PlantationWorld.TerrainHeight(PlantationWorld.GudangX, PlantationWorld.GudangZ);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, PlantationWorld.GudangX, gudangY, PlantationWorld.GudangZ, 0f, PlantationWorld.GudangRotY, 0f, 1f, 1f, 1f);
        DrawNamed(MeshCatalog.GudangPupuk, 0, _instStaging, c, ref drawCalls, ref tris);

        c = 0;
        for (int sk = 0; sk < 6; sk++)
        {
            float rowX = PlantationWorld.GudangX + 3.95f + (sk % 2) * 0.62f;
            float rowZ = PlantationWorld.GudangZ - 1.25f + (sk / 2) * 0.95f;
            c = Mat4Utils.WriteInstanceTRS(_instStaging, c, rowX, PlantationWorld.TerrainHeight(rowX, rowZ), rowZ, 0f, sk * 0.45f, 0f, 1f, 1f, 1f);
        }
        DrawNamed(MeshCatalog.ItemNpkSack, 0, _instStaging, c, ref drawCalls, ref tris);

        c = 0;
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, PlantationWorld.ArchNorthX, PlantationWorld.TerrainHeight(PlantationWorld.ArchNorthX, PlantationWorld.ArchNorthZ), PlantationWorld.ArchNorthZ, 0f, 0f, 0f, 1f, 1f, 1f);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, PlantationWorld.ArchBridgeX, PlantationWorld.TerrainHeight(PlantationWorld.ArchBridgeX, PlantationWorld.ArchBridgeZ), PlantationWorld.ArchBridgeZ, 0f, 0f, 0f, 1f, 1f, 1f);
        DrawNamed(MeshCatalog.OffroadArch, 0, _instStaging, c, ref drawCalls, ref tris);

        // 2.3. Terrain-Conforming Canter Herringbone Tire Tracks (1 instanced draw call, zero floating over water!)
        int nTracks = 0;
        for (int i = 0; i < _tireTracks.Length; i++)
        {
            if (!_tireTracks[i].Active) continue;
            ref var tr = ref _tireTracks[i];
            float fade = 1f - System.Math.Clamp((tr.Age - 20f) / 16f, 0f, 0.72f);
            nTracks = Mat4Utils.WriteInstanceTRS(_instStaging, nTracks, tr.X, tr.Y, tr.Z, tr.Rx, tr.Ry, tr.Rz, 1.08f * fade, 1f, 1.04f, 0.76f, 0.70f, 0.64f, 0f);
        }
        if (nTracks > 0) DrawNamed(MeshCatalog.TireTrackSegment, 0, _instStaging, nTracks, ref drawCalls, ref tris);

        // 2.5. Angkong Wheelbarrows
        int nCart = 0, nCartWheel = 0, nCartExtraFruit = 0;
        for (int i = 0; i < Physics.Angkongs.Length; i++)
        {
            var ak = Physics.Angkongs[i];
            var cartMat = Mat4Utils.BoneMat.TRS(ak.X, ak.Y, ak.Z, ak.PitchRad, ak.Yaw, 0f);
            nCart = cartMat.Emit(_instStaging, nCart);
            nCartWheel = cartMat.Child(0f, 0.29f, 0.80f, rx: ak.WheelSpinRad, sx: 0.45f, sy: 0.59f, sz: 0.59f)
                .Emit(_goldStaging, nCartWheel);
            if (ak.CargoUnits > 2)
            {
                float stackScale = 0.85f + ak.CargoUnits * 0.05f;
                nCartExtraFruit = cartMat.Child(0f, 1.02f, 0.14f, sx: stackScale, sy: stackScale, sz: stackScale)
                    .Emit(_fruitStaging, nCartExtraFruit, ak.GoldUnits > 0 ? 2.2f : 1f, ak.GoldUnits > 0 ? 1.7f : 1f, ak.GoldUnits > 0 ? 0.5f : 1f);
            }
        }
        DrawNamed(MeshCatalog.AngkongCart, 0, _instStaging, nCart, ref drawCalls, ref tris);
        DrawNamed(MeshCatalog.TruckWheel, 0, _goldStaging, nCartWheel, ref drawCalls, ref tris);
        if (nCartExtraFruit > 0) DrawNamed(MeshCatalog.TbsBunch, 0, _fruitStaging, nCartExtraFruit, ref drawCalls, ref tris);

        // 3. Multi-LOD Tenera Oil Palms + Alpha-Cutout Pinnate Crowns + Glossy Spiky TBS Clusters!
        for (int tier = 0; tier < 3; tier++)
        {
            int nTrunk = 0, nCrown = 0, nBunch = 0;
            for (int i = 0; i < _trees.Count; i++)
            {
                if (_treeLodResult[i] != tier) continue;
                var t = _trees[i];
                float highlight = i == NearestRipeTreeId ? 1.24f : 1.0f;
                float cy = MathF.Cos(t.RotationY), sy = MathF.Sin(t.RotationY);

                nTrunk = Mat4Utils.WriteInstanceTRS(_treeLodStaging[0], nTrunk, t.X, t.Y - 0.12f, t.Z, 0, t.RotationY, 0, t.Scale, t.Scale, t.Scale, highlight, highlight, 1f, 0f);
                nCrown = Mat4Utils.WriteInstanceTRS(
                    _treeLodStaging[1], nCrown,
                    t.X + (0.28f * cy + 0.20f * sy) * t.Scale,
                    t.Y + 6.32f * t.Scale,
                    t.Z + (-0.28f * sy + 0.20f * cy) * t.Scale,
                    0, t.RotationY, 0, t.Scale, t.Scale, t.Scale, 1f, 1f, 1f, tier < 2 ? windAmp : 0f);

                if (t.State > 0 && tier <= 1)
                {
                    bool isGold = t.State == 2;
                    int perTree = tier == 0 ? 5 : 2;
                    for (int b = 0; b < perTree; b++)
                    {
                        float ang = t.RotationY + b * 1.256f;
                        nBunch = Mat4Utils.WriteInstanceTRS(
                            _fruitStaging, nBunch,
                            t.X + (0.28f * cy + 0.20f * sy + MathF.Sin(ang) * 0.42f) * t.Scale,
                            t.Y + (5.96f - (b % 2) * 0.18f) * t.Scale,
                            t.Z + (-0.28f * sy + 0.20f * cy + MathF.Cos(ang) * 0.42f) * t.Scale,
                            0, ang, 0, t.Scale, t.Scale, t.Scale,
                            isGold ? 2.35f : 1f, isGold ? 1.80f : 1f, isGold ? 0.45f : 1f, 0.30f);
                    }
                }
            }
            DrawNamed(MeshCatalog.PalmTrunk, tier, _treeLodStaging[0], nTrunk, ref drawCalls, ref tris);
            DrawNamed(MeshCatalog.PalmCrown, tier, _treeLodStaging[1], nCrown, ref drawCalls, ref tris);
            DrawNamed(MeshCatalog.TbsBunch, tier, _fruitStaging, nBunch, ref drawCalls, ref tris);

            int nSapling = 0;
            for (int i = 0; i < _saplings.Count; i++)
            {
                if (_saplingLodResult[i] != tier) continue;
                var sp = _saplings[i];
                nSapling = Mat4Utils.WriteInstanceTRS(
                    _treeLodStaging[2], nSapling,
                    sp.X, sp.Y, sp.Z, 0f, sp.RotY, 0f,
                    sp.Scale, sp.Scale, sp.Scale, 1f, 1f, 1f, tier < 2 ? windAmp * 0.72f : 0f);
            }
            if (nSapling > 0) DrawNamed(MeshCatalog.PalmSapling, tier, _treeLodStaging[2], nSapling, ref drawCalls, ref tris);
        }

        // 3.5. Fallen Ground TBS, Thrown Arcs & Severed Cut Palm Fronds ("Pelepah Sawit Jatuh")
        int nDynFruit = 0;
        for (int i = 0; i < Physics.GroundFruits.Length; i++)
        {
            if (!Physics.GroundFruits[i].Active) continue;
            ref var gf = ref Physics.GroundFruits[i];
            float pulse = gf.Grounded ? (1.0f + MathF.Sin(now * 4.5f + i) * 0.04f) : 1.0f;
            nDynFruit = Mat4Utils.WriteInstanceTRS(
                _goldStaging, nDynFruit, gf.X, gf.Y, gf.Z, gf.RotX, gf.RotY, 0, pulse, pulse, pulse,
                gf.IsGold ? 2.35f : 1.04f, gf.IsGold ? 1.80f : 1.02f, gf.IsGold ? 0.45f : 1.0f, 0f);
        }
        for (int i = 0; i < Physics.ThrownArcs.Length; i++)
        {
            if (!Physics.ThrownArcs[i].Active) continue;
            ref var ar = ref Physics.ThrownArcs[i];
            nDynFruit = Mat4Utils.WriteInstanceTRS(
                _goldStaging, nDynFruit, ar.CurX, ar.CurY, ar.CurZ, ar.SpinRad, ar.SpinRad * 0.7f, 0, 0.95f, 0.95f, 0.95f,
                ar.IsGold ? 2.35f : 1.04f, ar.IsGold ? 1.80f : 1.02f, ar.IsGold ? 0.45f : 1.0f, 0f);
        }
        if (nDynFruit > 0) DrawNamed(MeshCatalog.TbsBunch, 0, _goldStaging, nDynFruit, ref drawCalls, ref tris);

        int nFronds = 0;
        for (int i = 0; i < _fallingFronds.Length; i++)
        {
            if (!_fallingFronds[i].Active) continue;
            ref var fr = ref _fallingFronds[i];
            nFronds = Mat4Utils.WriteInstanceTRS(_instStaging, nFronds, fr.X, fr.Y, fr.Z, fr.Rx, fr.Ry, fr.Rz, 1f, 1f, 1f, 1f, 1f, 1f, 0.25f);
        }
        if (nFronds > 0) DrawNamed(MeshCatalog.CutPalmFrond, 0, _instStaging, nFronds, ref drawCalls, ref tris);

        // 4. Undergrowth Alpha-Cutout Ferns & Granite Boulders
        if (q.DrawUndergrowthFerns)
        {
            c = 0;
            for (int i = 0; i < _ferns.Count; i++)
            {
                var f = _ferns[i];
                float dx = f.X - eyeX, dz = f.Z - eyeZ;
                if (dx * dx + dz * dz < q.Lod1Distance * q.Lod1Distance)
                    c = Mat4Utils.WriteInstanceTRS(_instStaging, c, f.X, f.Y, f.Z, 0, f.RotY, 0, f.Scale, f.Scale, f.Scale, 1, 1, 1, 0.55f);
            }
            DrawNamed(MeshCatalog.TropicalFern, q.Preset == GraphicsPreset.Standard ? 1 : 0, _instStaging, c, ref drawCalls, ref tris);
        }

        c = 0;
        for (int i = 0; i < _rocks.Count; i++)
        {
            var r = _rocks[i];
            float dx = r.X - eyeX, dz = r.Z - eyeZ;
            if (dx * dx + dz * dz < q.MaxDrawDistance * q.MaxDrawDistance)
                c = Mat4Utils.WriteInstanceTRS(_instStaging, c, r.X, r.Y, r.Z, 0, r.RotY, 0, r.Scale, r.Scale, r.Scale);
        }
        DrawNamed(MeshCatalog.RockBoulder, 1, _instStaging, c, ref drawCalls, ref tris);

        // 5. Wild Celeng Boars
        int nBoar = 0, nBoarLeg = 0;
        for (int i = 0; i < _boarsSnap.Count; i++)
        {
            var b = _boarsSnap[i];
            float gallop = now * 10.5f + i * 1.9f;
            float by = PlantationWorld.TerrainHeight(b.X, b.Z) + MathF.Abs(MathF.Sin(gallop)) * 0.08f;
            var boarM = Mat4Utils.BoneMat.TRS(b.X, by, b.Z, rx: MathF.Sin(gallop) * 0.06f, ry: b.Yaw, sx: 1.05f, sy: 1.05f, sz: 1.05f);
            nBoar = boarM.Emit(_instStaging, nBoar);
            float sw = MathF.Sin(gallop) * 0.58f;
            nBoarLeg = boarM.Child(-0.20f, 0.50f, 0.44f, rx: sw).Emit(_goldStaging, nBoarLeg);
            nBoarLeg = boarM.Child(0.20f, 0.50f, 0.44f, rx: -sw).Emit(_goldStaging, nBoarLeg);
            nBoarLeg = boarM.Child(-0.19f, 0.50f, -0.44f, rx: -sw).Emit(_goldStaging, nBoarLeg);
            nBoarLeg = boarM.Child(0.19f, 0.50f, -0.44f, rx: sw).Emit(_goldStaging, nBoarLeg);
        }
        DrawNamed(MeshCatalog.CelengBoar, 0, _instStaging, nBoar, ref drawCalls, ref tris);
        DrawNamed(MeshCatalog.BoarLeg, 0, _goldStaging, nBoarLeg, ref drawCalls, ref tris);

        // 6. Physical Mitsubishi Fuso Canter COE Bak Kayu Trucks!
        int shownCargo = System.Math.Max(_net.LocalCargo, Physics.MainTruck.VisualCargoUnits);
        DrawCanterVehicleRig(Physics.MainTruck, _net.Profile.Avatar, shownCargo, hasDriver: InTruck, ref drawCalls, ref tris);
        DrawCanterVehicleRig(Physics.YardTruck, new AvatarConfig { OutfitHex = "#E67E22" }, Physics.YardTruck.VisualCargoUnits, hasDriver: false, ref drawCalls, ref tris);

        // 7. Local Player Harvester (Fluid Spring-Smoothed Kinematics + Full Accessories!)
        if (!InTruck)
        {
            DrawDetailedHumanRig(
                PlayerX, PlayerY, PlayerZ, Physics.Player.Yaw,
                walkPhase: Physics.Player.WalkCycleRad,
                breathPhase: Physics.Player.IdleBreathPhase,
                moving: Physics.Player.MoveSpeedMs > 0.2f,
                stance: Physics.Player.Stance,
                slashTimer: Physics.Player.SlashTimer,
                pickupTimer: Physics.Player.PickupTimer,
                throwTimer: Physics.Player.ThrowTimer,
                heldGold: Physics.Player.HeldGoldUnits > 0,
                av: _net.Profile.Avatar,
                dt: dt,
                useSmoothState: true,
                ref drawCalls, ref tris);
        }

        // 8. Live Remote Multiplayer Peers
        for (int i = 0; i < _peersSnap.Count; i++)
        {
            var p = _peersSnap[i];
            if (p.InTruck)
            {
                var remoteTruck = new VehicleRigidBody
                {
                    X = p.RenderX,
                    Y = p.RenderY,
                    Z = p.RenderZ,
                    Yaw = p.RenderYaw,
                    SteerAngle = p.SteerAngle,
                    WheelSpinRad = p.WalkPhase,
                    RollRad = p.AnimState == 1 ? MathF.Sin(p.WalkPhase * 0.45f) * 0.05f : 0f,
                };
                for (int w = 0; w < 4; w++) remoteTruck.WheelWorldY[w] = p.RenderY + 0.48f;
                DrawCanterVehicleRig(remoteTruck, p.Avatar, p.Cargo, hasDriver: true, ref drawCalls, ref tris);
            }
            else
            {
                var peerStance = p.PushingAngkong ? HoldStance.PushingAngkong : (p.CarryingTbs ? HoldStance.CarryingTbs : HoldStance.TwoHandTool);
                DrawDetailedHumanRig(
                    p.RenderX, p.RenderY, p.RenderZ, p.RenderYaw,
                    walkPhase: p.WalkPhase,
                    breathPhase: now * 2.1f + i,
                    moving: p.AnimState == 1,
                    stance: peerStance,
                    slashTimer: p.AnimState == 2 ? 0.25f : 0f,
                    pickupTimer: 0f,
                    throwTimer: 0f,
                    heldGold: false,
                    av: p.Avatar,
                    dt: dt,
                    useSmoothState: false,
                    ref drawCalls, ref tris);
            }
        }

        // 9. Soft Volumetric Billboards: PKS Boiler Steam + Tire Dust + Diesel Exhaust + Harvest Chaff (Mode 2)!
        _allowOutlinePass = false;
        if (Quality.ParticlesEnabled)
        {
            float billboardYaw = MathF.Atan2(eyeX - lookX, eyeZ - lookZ);
            int nPuff = 0;

            // PKS Boiler Steam Plumes
            for (int sp = 0; sp < 8; sp++)
            {
                float cycle = (now * 0.36f + sp * 0.125f) % 1.0f;
                float cxChim = sp % 2 == 0 ? (PlantationWorld.PksX - 3.2f) : (PlantationWorld.PksX - 1.0f);
                float sc = 1.25f + cycle * 3.4f;
                float alpha = MathF.Sin(cycle * MathF.PI) * 0.44f;
                nPuff = Mat4Utils.WriteInstanceTRS(
                    _instStaging, nPuff,
                    cxChim + cycle * 2.8f + MathF.Sin(now + sp) * 0.22f,
                    pksGround + 14.3f + cycle * 7.2f,
                    PlantationWorld.PksZ - 2.2f + cycle * 1.5f,
                    0f, billboardYaw, cycle * 1.6f, sc, sc, sc,
                    0.95f, 0.96f, 0.98f, alpha);
            }

            // Dynamic Tire Dust, Diesel Exhaust & Harvest Burst Particles!
            for (int i = 0; i < _vfxPool.Length; i++)
            {
                if (!_vfxPool[i].Active) continue;
                ref var p = ref _vfxPool[i];
                float t = System.Math.Clamp(p.Age / p.Life, 0f, 1f);
                float sz = p.SizeStart + (p.SizeEnd - p.SizeStart) * t;
                float alpha = p.Alpha * (1f - t * t);
                nPuff = Mat4Utils.WriteInstanceTRS(
                    _instStaging, nPuff,
                    p.X, p.Y, p.Z,
                    0f, billboardYaw, p.Spin + t * 1.4f, sz, sz, sz,
                    p.R, p.G, p.B, alpha);
            }

            if (nPuff > 0)
            {
                GLES30.GlUniform1i(_uRenderMode, 2);
                GLES30.GlEnable(GLES30.GlBlend);
                GLES30.GlBlendFunc(GLES30.GlSrcAlpha, GLES30.GlOneMinusSrcAlpha);
                GLES30.GlDepthMask(false);
                DrawNamed(MeshCatalog.VfxPuffQuad, 0, _instStaging, nPuff, ref drawCalls, ref tris);
                GLES30.GlDepthMask(true);
                GLES30.GlDisable(GLES30.GlBlend);
                GLES30.GlUniform1i(_uRenderMode, 0);
            }
        }

        LastDrawCalls = drawCalls;
        LastTriangles = tris;

        lock (HudLock)
        {
            ProjectedLabels.Clear();
            MinimapPeers.Clear();

            if (Stage == AppSceneStage.Gameplay)
            {
                string myBubble = FindLatestBubble(_net.Profile.Id, now);
                if (Mat4Utils.ProjectWorldToScreen(_vp, PlayerX, PlayerY + (InTruck ? 2.75f : 2.15f), PlayerZ, 1f, 1f, out float sx, out float sy))
                {
                    ProjectedLabels.Add(new ProjectedLabel
                    {
                        ScreenX = sx,
                        ScreenY = sy,
                        Name = _net.Profile.Name,
                        SubTitle = _net.Profile.Avatar.Title,
                        BubbleText = myBubble,
                        IsSelf = true,
                        IsSpeaking = LocalMicSpeaking,
                    });
                }

                for (int i = 0; i < _peersSnap.Count; i++)
                {
                    var p = _peersSnap[i];
                    MinimapPeers.Add((p.RenderX, p.RenderZ, p.InTruck));
                    if (Mat4Utils.ProjectWorldToScreen(_vp, p.RenderX, p.RenderY + (p.InTruck ? 2.75f : 2.15f), p.RenderZ, 1f, 1f, out float px, out float py))
                    {
                        ProjectedLabels.Add(new ProjectedLabel
                        {
                            ScreenX = px,
                            ScreenY = py,
                            Name = p.Name,
                            SubTitle = p.Avatar.Title,
                            BubbleText = FindLatestBubble(p.Id, now),
                            IsSelf = false,
                            IsSpeaking = p.SpeakingNow,
                        });
                    }
                }
            }
        }
    }

    private void UpdateSunShadowMatrix(float focusX, float focusY, float focusZ)
    {
        // Snap shadow frustum center to 0.5m world grid to eliminate shadow edge swimming completely!
        float sx = MathF.Round(focusX * 2f) * 0.5f;
        float sz = MathF.Round(focusZ * 2f) * 0.5f;
        float halfExt = 27.0f;
        Mat4Utils.CreateOrthographic(_lightProj, -halfExt, halfExt, -halfExt, halfExt, 1.0f, 96.0f);
        Mat4Utils.CreateLookAt(
            _lightView,
            sx + 0.48f * 46f, focusY + 0.72f * 46f, sz + 0.44f * 46f,
            sx, focusY, sz);
        Mat4Utils.Multiply(_lightVp, _lightProj, _lightView);
    }

    private void RenderShadowCasters(float windAmp, ref int drawCalls, ref int tris)
    {
        float focusX = PlayerX, focusZ = PlayerZ;
        int nTrunk = 0, nCrown = 0;
        for (int i = 0; i < _trees.Count; i++)
        {
            var t = _trees[i];
            float dx = t.X - focusX, dz = t.Z - focusZ;
            if (dx * dx + dz * dz > 33f * 33f) continue;
            float cy = MathF.Cos(t.RotationY), sy = MathF.Sin(t.RotationY);
            nTrunk = Mat4Utils.WriteInstanceTRS(_treeLodStaging[0], nTrunk, t.X, t.Y - 0.12f, t.Z, 0, t.RotationY, 0, t.Scale, t.Scale, t.Scale);
            nCrown = Mat4Utils.WriteInstanceTRS(
                _treeLodStaging[1], nCrown,
                t.X + (0.28f * cy + 0.20f * sy) * t.Scale,
                t.Y + 6.32f * t.Scale,
                t.Z + (-0.28f * sy + 0.20f * cy) * t.Scale,
                0, t.RotationY, 0, t.Scale, t.Scale, t.Scale, 1f, 1f, 1f, windAmp);
        }
        DrawNamed(MeshCatalog.PalmTrunk, 1, _treeLodStaging[0], nTrunk, ref drawCalls, ref tris);
        DrawNamed(MeshCatalog.PalmCrown, 1, _treeLodStaging[1], nCrown, ref drawCalls, ref tris);

        // Shadow casters for Canter Trucks + PKS Factory + Player!
        int c = 0;
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, Physics.MainTruck.X, Physics.MainTruck.Y, Physics.MainTruck.Z, Physics.MainTruck.PitchRad, Physics.MainTruck.Yaw, Physics.MainTruck.RollRad, 1, 1, 1);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, Physics.YardTruck.X, Physics.YardTruck.Y, Physics.YardTruck.Z, Physics.YardTruck.PitchRad, Physics.YardTruck.Yaw, Physics.YardTruck.RollRad, 1, 1, 1);
        DrawNamed(MeshCatalog.CanterTruckBody, 2, _instStaging, c, ref drawCalls, ref tris);

        float pksGround = PlantationWorld.TerrainHeight(PlantationWorld.PksX, PlantationWorld.PksZ);
        if ((PlantationWorld.PksX - focusX) * (PlantationWorld.PksX - focusX) + (PlantationWorld.PksZ - focusZ) * (PlantationWorld.PksZ - focusZ) < 42f * 42f)
        {
            c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, PlantationWorld.PksX, pksGround, PlantationWorld.PksZ, 0, 0, 0, 1, 1, 1);
            DrawNamed(MeshCatalog.PksFactory, 2, _instStaging, c, ref drawCalls, ref tris);
        }

        if ((PlantationWorld.SpbuX - focusX) * (PlantationWorld.SpbuX - focusX) + (PlantationWorld.SpbuZ - focusZ) * (PlantationWorld.SpbuZ - focusZ) < 38f * 38f)
        {
            c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, PlantationWorld.SpbuX, PlantationWorld.TerrainHeight(PlantationWorld.SpbuX, PlantationWorld.SpbuZ), PlantationWorld.SpbuZ, 0f, PlantationWorld.SpbuRotY, 0f, 1f, 1f, 1f);
            DrawNamed(MeshCatalog.SpbuSolar, 2, _instStaging, c, ref drawCalls, ref tris);
        }
        if ((PlantationWorld.WarungX - focusX) * (PlantationWorld.WarungX - focusX) + (PlantationWorld.WarungZ - focusZ) * (PlantationWorld.WarungZ - focusZ) < 36f * 36f)
        {
            c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, PlantationWorld.WarungX, PlantationWorld.TerrainHeight(PlantationWorld.WarungX, PlantationWorld.WarungZ), PlantationWorld.WarungZ, 0f, PlantationWorld.WarungRotY, 0f, 1f, 1f, 1f);
            DrawNamed(MeshCatalog.WarungKopi, 2, _instStaging, c, ref drawCalls, ref tris);
        }
        c = 0;
        if ((PlantationWorld.ArchNorthX - focusX) * (PlantationWorld.ArchNorthX - focusX) + (PlantationWorld.ArchNorthZ - focusZ) * (PlantationWorld.ArchNorthZ - focusZ) < 36f * 36f)
            c = Mat4Utils.WriteInstanceTRS(_instStaging, c, PlantationWorld.ArchNorthX, PlantationWorld.TerrainHeight(PlantationWorld.ArchNorthX, PlantationWorld.ArchNorthZ), PlantationWorld.ArchNorthZ, 0f, 0f, 0f, 1f, 1f, 1f);
        if ((PlantationWorld.ArchBridgeX - focusX) * (PlantationWorld.ArchBridgeX - focusX) + (PlantationWorld.ArchBridgeZ - focusZ) * (PlantationWorld.ArchBridgeZ - focusZ) < 36f * 36f)
            c = Mat4Utils.WriteInstanceTRS(_instStaging, c, PlantationWorld.ArchBridgeX, PlantationWorld.TerrainHeight(PlantationWorld.ArchBridgeX, PlantationWorld.ArchBridgeZ), PlantationWorld.ArchBridgeZ, 0f, 0f, 0f, 1f, 1f, 1f);
        if (c > 0) DrawNamed(MeshCatalog.OffroadArch, 2, _instStaging, c, ref drawCalls, ref tris);

        if (!InTruck)
        {
            c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, PlayerX, PlayerY + 0.88f, PlayerZ, 0, Physics.Player.Yaw, 0, 1, 1, 1);
            DrawNamed(MeshCatalog.CharTorsoHead, 2, _instStaging, c, ref drawCalls, ref tris);
        }
    }

    private void BindAtlasAndShadowTextures()
    {
        GLES30.GlActiveTexture(GLES30.GlTexture0);
        GLES30.GlBindTexture(GLES30.GlTexture2d, _atlasTexId);
        GLES30.GlActiveTexture(GLES30.GlTexture1);
        GLES30.GlBindTexture(GLES30.GlTexture2d, _shadowMapDepthTex);
        GLES30.GlActiveTexture(GLES30.GlTexture0);
    }

    private string FindLatestBubble(string senderId, float now)
    {
        for (int i = _chatSnap.Count - 1; i >= 0; i--)
        {
            var c = _chatSnap[i];
            if (c.SenderId == senderId && c.ExpiresBubbleAtSec > now) return c.Text;
        }
        return "";
    }

    /// <summary>
    /// Renders authentic Indonesian COE Mitsubishi Fuso Canter FE 74 HD Bak Kayu:
    ///   - Chassis Pitch + Roll ("Canter Oleng") + Heave
    ///   - 2 Single Front Steered Suspension Wheels + 4 DUAL Rear Axle Heavy Radial Wheels (6 wheels total!)
    ///   - Live-Rotating 3D Cabin Steering Wheel (canter_steering_wheel) + Seated Driver turning with SteerAngle!
    /// </summary>
    private void DrawCanterVehicleRig(
        VehicleRigidBody v,
        AvatarConfig av,
        int cargoUnits,
        bool hasDriver,
        ref int drawCalls,
        ref int tris)
    {
        var (cr, cg, cb) = av.GetOutfitRgb();
        var chassis = Mat4Utils.BoneMat.TRS(v.X, v.Y, v.Z, rx: v.PitchRad, ry: v.Yaw, rz: v.RollRad);

        int n = chassis.Emit(_instStaging, 0, 1.0f, 1.0f, 1.0f);
        DrawNamed(MeshCatalog.CanterTruckBody, 0, _instStaging, n, ref drawCalls, ref tris);

        // Live-rotating Canter steering wheel visible right through the wide COE windshield!
        var steerMat = chassis.Child(0.42f, 1.44f, 1.86f, rx: 0.62f, rz: -v.SteerAngle * 2.2f);
        DrawNamed(MeshCatalog.CanterSteeringWheel, 0, _instStaging, steerMat.Emit(_instStaging, 0), ref drawCalls, ref tris);

        // 2 Front Steered Single Wheels + 4 Dual Rear Heavy Canter Wheels (6 wheels in ONE single instanced draw call!)
        float sy = MathF.Sin(v.Yaw), cy = MathF.Cos(v.Yaw);
        int nw = 0;
        float frontAxleYSum = 0f, rearAxleYSum = 0f;
        for (int s = 0; s < 2; s++)
        {
            float sign = s == 0 ? -1f : 1f;
            float wyFront = v.WheelWorldY[s] > 0.001f ? v.WheelWorldY[s] : (v.Y + 0.48f);
            frontAxleYSum += wyFront;
            float fxW = v.X + (sign * 0.88f) * cy + 1.55f * sy;
            float fzW = v.Z - (sign * 0.88f) * sy + 1.55f * cy;
            nw = Mat4Utils.BoneMat.TRS(fxW, wyFront, fzW, ry: v.Yaw + v.SteerAngle)
                .Child(0f, 0f, 0f, rx: v.WheelSpinRad)
                .Emit(_instStaging, nw);

            float wyRear = v.WheelWorldY[2 + s] > 0.001f ? v.WheelWorldY[2 + s] : (v.Y + 0.48f);
            rearAxleYSum += wyRear;
            float innerX = sign * 0.74f, outerX = sign * 0.95f;
            nw = Mat4Utils.BoneMat.TRS(v.X + innerX * cy - 1.25f * sy, wyRear, v.Z - innerX * sy - 1.25f * cy, ry: v.Yaw)
                .Child(0f, 0f, 0f, rx: v.WheelSpinRad)
                .Emit(_instStaging, nw);
            nw = Mat4Utils.BoneMat.TRS(v.X + outerX * cy - 1.25f * sy, wyRear, v.Z - outerX * sy - 1.25f * cy, ry: v.Yaw)
                .Child(0f, 0f, 0f, rx: v.WheelSpinRad)
                .Emit(_instStaging, nw);
        }
        DrawNamed(MeshCatalog.TruckWheel, 0, _instStaging, nw, ref drawCalls, ref tris);

        // Live Heavy-Duty Leaf-Spring Solid Axles ("Gardan & Per Daun Baja") + Spinning Propeller Driveshaft ("Kopel")!
        float fAxleY = frontAxleYSum * 0.5f;
        float rAxleY = rearAxleYSum * 0.5f;
        int nAxle = 0;
        nAxle = Mat4Utils.BoneMat.TRS(v.X + 1.55f * sy, fAxleY, v.Z + 1.55f * cy, ry: v.Yaw + MathF.PI, rz: v.RollRad * 0.35f)
            .Emit(_instStaging, nAxle);
        nAxle = Mat4Utils.BoneMat.TRS(v.X - 1.25f * sy, rAxleY, v.Z - 1.25f * cy, ry: v.Yaw, rz: v.RollRad * 0.35f)
            .Emit(_instStaging, nAxle);
        DrawNamed(MeshCatalog.CanterAxleSuspension, 0, _instStaging, nAxle, ref drawCalls, ref tris);

        var shaftMat = chassis.Child(0f, 0.50f, -1.08f, rz: v.WheelSpinRad * 2.8f, sx: 1f, sy: 1f, sz: 1.48f);
        DrawNamed(MeshCatalog.CanterDriveshaft, 0, _instStaging, shaftMat.Emit(_instStaging, 0), ref drawCalls, ref tris);

        // Warm Halogen Headlight Beams during storm ("HUJAN_BADAI"), Karhutla Haze, or Turbo Solar Boost!
        bool beamsOn = (_net?.EventKind == "HUJAN_BADAI") || (Quality.Atmosphere == AtmospherePreset.KarhutlaSmoke) || (hasDriver && BoostTimer > 0.05f);
        if (beamsOn && Stage == AppSceneStage.Gameplay)
        {
            int nb = 0;
            nb = chassis.Child(-0.72f, 0.94f, 2.30f).Emit(_instStaging, nb, 1.15f, 1.04f, 0.78f, 0.48f);
            nb = chassis.Child(0.72f, 0.94f, 2.30f).Emit(_instStaging, nb, 1.15f, 1.04f, 0.78f, 0.48f);
            GLES30.GlUniform1i(_uRenderMode, 2);
            GLES30.GlEnable(GLES30.GlBlend);
            GLES30.GlBlendFunc(GLES30.GlSrcAlpha, GLES30.GlOne);
            GLES30.GlDepthMask(false);
            DrawNamed(MeshCatalog.CanterHeadlightBeam, 0, _instStaging, nb, ref drawCalls, ref tris);
            GLES30.GlDepthMask(true);
            GLES30.GlBlendFunc(GLES30.GlSrcAlpha, GLES30.GlOneMinusSrcAlpha);
            GLES30.GlDisable(GLES30.GlBlend);
            GLES30.GlUniform1i(_uRenderMode, 0);
        }

        if (cargoUnits > 0)
        {
            float fill = System.Math.Min(1.08f, 0.48f + cargoUnits * 0.030f);
            int nc = chassis.Child(0f, 0.80f, 0f, sx: 0.96f, sy: fill, sz: 0.96f).Emit(_instStaging, 0);
            DrawNamed(MeshCatalog.TruckCargoHeap, 0, _instStaging, nc, ref drawCalls, ref tris);
        }

        if (hasDriver)
        {
            var drvTorso = chassis.Child(0.42f, 1.15f, 1.56f, sx: 0.86f, sy: 0.86f, sz: 0.86f);
            DrawNamed(MeshCatalog.CharTorsoHead, 0, _instStaging, drvTorso.Emit(_instStaging, 0, cr, cg, cb), ref drawCalls, ref tris);
            var drvHead = drvTorso.Child(0f, 0.58f, 0.01f, ry: v.SteerAngle * 0.55f);
            DrawNamed(MeshCatalog.CharHead, 0, _instStaging, drvHead.Emit(_instStaging, 0), ref drawCalls, ref tris);
            DrawNamed(MeshCatalog.CharFaceNeutral, 0, _instStaging, drvHead.Emit(_instStaging, 0), ref drawCalls, ref tris);
            if (av.Glasses)
                DrawNamed(MeshCatalog.AccGlasses, 0, _instStaging, drvHead.Emit(_instStaging, 0), ref drawCalls, ref tris);
            if (!string.IsNullOrEmpty(av.Hat) && av.Hat != "none")
                DrawNamed(av.Hat, 0, _instStaging, drvHead.Child(0f, 0.21f, 0f).Emit(_instStaging, 0, cr, cg, cb), ref drawCalls, ref tris);

            int na = 0, nf = 0;
            var armL = drvTorso.Child(-0.215f, 0.46f, 0.02f, rx: -0.92f + v.SteerAngle * 0.48f, rz: -0.16f);
            var armR = drvTorso.Child(0.215f, 0.46f, 0.02f, rx: -0.92f - v.SteerAngle * 0.48f, rz: 0.16f);
            na = armL.Emit(_instStaging, na, cr, cg, cb);
            na = armR.Emit(_instStaging, na, cr, cg, cb);
            nf = armL.Child(0f, -0.27f, 0.01f, rx: -0.45f).Emit(_goldStaging, nf);
            nf = armR.Child(0f, -0.27f, 0.01f, rx: -0.45f).Emit(_goldStaging, nf);
            DrawNamed(MeshCatalog.CharArm, 0, _instStaging, na, ref drawCalls, ref tris);
            DrawNamed(MeshCatalog.CharForearmHand, 0, _goldStaging, nf, ref drawCalls, ref tris);
        }
    }

    private static float SmoothDampValue(float current, float target, float k) => current + (target - current) * k;

    private void DrawDetailedHumanRig(
        float x, float y, float z, float yaw,
        float walkPhase,
        float breathPhase,
        bool moving,
        HoldStance stance,
        float slashTimer,
        float pickupTimer,
        float throwTimer,
        bool heldGold,
        AvatarConfig av,
        float dt,
        bool useSmoothState,
        ref int drawCalls,
        ref int tris)
    {
        var (cr, cg, cb) = av.GetOutfitRgb();
        float breath = MathF.Sin(breathPhase) * 0.016f;

        float stride = moving ? MathF.Sin(walkPhase) : 0f;
        float bob = moving ? MathF.Abs(MathF.Cos(walkPhase)) * 0.046f : breath * 0.5f;

        float squatK = pickupTimer > 0.001f ? MathF.Sin(System.Math.Clamp(pickupTimer / 0.40f, 0f, 1f) * MathF.PI) : 0f;
        float carryBrace = stance == HoldStance.CarryingTbs ? 1.0f : 0f;
        float tgtHipOffset = 0.88f + bob - squatK * 0.34f - carryBrace * 0.032f;
        float tgtTorsoRx = squatK * 0.54f + carryBrace * 0.078f + (moving ? 0.09f : 0.015f + breath * 0.6f);

        float tgtThighL = -stride * 0.60f - squatK * 0.90f - carryBrace * 0.06f;
        float tgtThighR = stride * 0.60f - squatK * 0.90f - carryBrace * 0.06f;
        float tgtKneeL = (moving ? MathF.Max(0f, MathF.Cos(walkPhase)) * 0.66f : 0.05f) + squatK * 1.45f + carryBrace * 0.11f;
        float tgtKneeR = (moving ? MathF.Max(0f, -MathF.Cos(walkPhase)) * 0.66f : 0.05f) + squatK * 1.45f + carryBrace * 0.11f;

        float tgtUaLRx, tgtUaLRz, tgtFaLRx, tgtFaLRy;
        float tgtUaRRx, tgtUaRRz, tgtFaRRx, tgtFaRRy;
        float slashLookUpRx = 0f;

        if (pickupTimer > 0.001f)
        {
            tgtUaLRx = -0.35f - squatK * 0.96f; tgtUaLRz = -0.15f;
            tgtFaLRx = -0.34f - squatK * 0.24f; tgtFaLRy = 0.20f;
            tgtUaRRx = -0.35f - squatK * 0.96f; tgtUaRRz = 0.15f;
            tgtFaRRx = -0.34f - squatK * 0.24f; tgtFaRRy = -0.20f;
        }
        else if (throwTimer > 0.001f)
        {
            float tk = 1f - System.Math.Clamp(throwTimer / 0.48f, 0f, 1f);
            float heave = MathF.Sin(tk * MathF.PI);
            tgtUaLRx = -0.80f - heave * 1.12f; tgtUaLRz = -0.18f;
            tgtFaLRx = -0.68f + heave * 0.48f; tgtFaLRy = 0.22f;
            tgtUaRRx = -0.80f - heave * 1.12f; tgtUaRRz = 0.18f;
            tgtFaRRx = -0.68f + heave * 0.48f; tgtFaRRy = -0.22f;
        }
        else if (slashTimer > 0.001f)
        {
            // Two-Phase 5.05m Telescopic SBL Egrek Cut-and-Lift:
            //   Phase 1 (0.00..0.44): High overhead reach & hook into tall palm crown
            //   Phase 2 (0.44..1.00): Powerful downward pull-slice ("Tarik Egrek")
            float sk = 1f - System.Math.Clamp(slashTimer / 0.68f, 0f, 1f);
            float reach = sk < 0.44f ? MathF.Sin((sk / 0.44f) * (MathF.PI * 0.5f)) : MathF.Cos(((sk - 0.44f) / 0.56f) * (MathF.PI * 0.5f));
            float pull = sk >= 0.44f ? MathF.Sin(((sk - 0.44f) / 0.56f) * MathF.PI) : 0f;
            tgtTorsoRx -= reach * 0.18f - pull * 0.14f;
            slashLookUpRx = -reach * 0.34f;
            tgtUaLRx = -0.90f - reach * 1.18f + pull * 0.62f; tgtUaLRz = -0.24f;
            tgtFaLRx = -0.48f + reach * 0.32f - pull * 0.22f; tgtFaLRy = 0.26f;
            tgtUaRRx = -0.78f - reach * 1.24f + pull * 0.68f; tgtUaRRz = 0.18f;
            tgtFaRRx = -0.56f + reach * 0.34f - pull * 0.24f; tgtFaRRy = -0.18f;
        }
        else if (stance == HoldStance.CarryingTbs)
        {
            float carryBob = moving ? MathF.Sin(walkPhase * 2f) * 0.055f : breath;
            tgtUaLRx = -0.82f + carryBob; tgtUaLRz = -0.22f;
            tgtFaLRx = -0.82f;            tgtFaLRy = 0.30f;
            tgtUaRRx = -0.82f + carryBob; tgtUaRRz = 0.22f;
            tgtFaRRx = -0.82f;            tgtFaRRy = -0.30f;
        }
        else if (stance == HoldStance.PushingAngkong)
        {
            tgtUaLRx = -0.70f; tgtUaLRz = 0.05f;
            tgtFaLRx = -0.42f; tgtFaLRy = 0.04f;
            tgtUaRRx = -0.70f; tgtUaRRz = -0.05f;
            tgtFaRRx = -0.42f; tgtFaRRy = -0.04f;
        }
        else
        {
            float sw = moving ? stride * 0.18f : breath * 1.4f;
            tgtUaLRx = -0.80f + sw; tgtUaLRz = -0.26f;
            tgtFaLRx = -0.42f;      tgtFaLRy = 0.26f;
            tgtUaRRx = -0.56f - sw; tgtUaRRz = 0.22f;
            tgtFaRRx = -0.54f;      tgtFaRRy = -0.18f;
        }

        // Exponential spring-damping eliminates 100% of rigid state-snap pops ("0% kaku")!
        if (useSmoothState)
        {
            float k = (!_localRigPose.Initialized) ? 1f : (1f - MathF.Exp(-dt * 15.5f));
            _localRigPose.Initialized = true;
            _localRigPose.HipOffsetY = SmoothDampValue(_localRigPose.HipOffsetY, tgtHipOffset, k);
            _localRigPose.TorsoRx = SmoothDampValue(_localRigPose.TorsoRx, tgtTorsoRx, k);
            _localRigPose.ThighLRx = SmoothDampValue(_localRigPose.ThighLRx, tgtThighL, k);
            _localRigPose.KneeLRx = SmoothDampValue(_localRigPose.KneeLRx, tgtKneeL, k);
            _localRigPose.ThighRRx = SmoothDampValue(_localRigPose.ThighRRx, tgtThighR, k);
            _localRigPose.KneeRRx = SmoothDampValue(_localRigPose.KneeRRx, tgtKneeR, k);
            _localRigPose.UaLRx = SmoothDampValue(_localRigPose.UaLRx, tgtUaLRx, k);
            _localRigPose.UaLRz = SmoothDampValue(_localRigPose.UaLRz, tgtUaLRz, k);
            _localRigPose.FaLRx = SmoothDampValue(_localRigPose.FaLRx, tgtFaLRx, k);
            _localRigPose.FaLRy = SmoothDampValue(_localRigPose.FaLRy, tgtFaLRy, k);
            _localRigPose.UaRRx = SmoothDampValue(_localRigPose.UaRRx, tgtUaRRx, k);
            _localRigPose.UaRRz = SmoothDampValue(_localRigPose.UaRRz, tgtUaRRz, k);
            _localRigPose.FaRRx = SmoothDampValue(_localRigPose.FaRRx, tgtFaRRx, k);
            _localRigPose.FaRRy = SmoothDampValue(_localRigPose.FaRRy, tgtFaRRy, k);

            tgtHipOffset = _localRigPose.HipOffsetY;
            tgtTorsoRx = _localRigPose.TorsoRx;
            tgtThighL = _localRigPose.ThighLRx;
            tgtKneeL = _localRigPose.KneeLRx;
            tgtThighR = _localRigPose.ThighRRx;
            tgtKneeR = _localRigPose.KneeRRx;
            tgtUaLRx = _localRigPose.UaLRx;
            tgtUaLRz = _localRigPose.UaLRz;
            tgtFaLRx = _localRigPose.FaLRx;
            tgtFaLRy = _localRigPose.FaLRy;
            tgtUaRRx = _localRigPose.UaRRx;
            tgtUaRRz = _localRigPose.UaRRz;
            tgtFaRRx = _localRigPose.FaRRx;
            tgtFaRRy = _localRigPose.FaRRy;
        }

        float hipSwayRz = moving ? -stride * 0.045f : MathF.Sin(breathPhase * 0.5f) * 0.012f;
        var hipRoot = Mat4Utils.BoneMat.TRS(x, y + tgtHipOffset, z, ry: yaw, rz: hipSwayRz);
        var torsoMat = hipRoot.Child(0f, 0f, 0f, rx: tgtTorsoRx, ry: moving ? stride * 0.07f : 0f);
        var headMat = torsoMat.Child(
            0f, 0.58f + breath * 0.35f, 0.01f,
            rx: -tgtTorsoRx * 0.45f + slashLookUpRx + MathF.Sin(breathPhase * 0.6f) * 0.028f,
            ry: moving ? -stride * 0.05f : MathF.Sin(breathPhase * 0.42f) * 0.095f);

        var thighL = hipRoot.Child(-0.105f, 0f, 0f, rx: tgtThighL, rz: -0.025f);
        var calfL = thighL.Child(0f, -0.43f, 0f, rx: tgtKneeL);
        var thighR = hipRoot.Child(0.105f, 0f, 0f, rx: tgtThighR, rz: 0.025f);
        var calfR = thighR.Child(0f, -0.43f, 0f, rx: tgtKneeR);

        var upperArmL = torsoMat.Child(-0.215f, 0.46f, 0.01f, rx: tgtUaLRx, rz: tgtUaLRz);
        var forearmL = upperArmL.Child(0f, -0.27f, 0.01f, rx: tgtFaLRx, ry: tgtFaLRy);
        var upperArmR = torsoMat.Child(0.215f, 0.46f, 0.01f, rx: tgtUaRRx, rz: tgtUaRRz);
        var forearmR = upperArmR.Child(0f, -0.27f, 0.01f, rx: tgtFaRRx, ry: tgtFaRRy);

        DrawNamed(MeshCatalog.CharTorsoHead, 0, _instStaging, torsoMat.Emit(_instStaging, 0, cr, cg, cb), ref drawCalls, ref tris);
        DrawNamed(MeshCatalog.CharHead, 0, _instStaging, headMat.Emit(_instStaging, 0), ref drawCalls, ref tris);
        bool strainedFace = slashTimer > 0.001f || pickupTimer > 0.001f || throwTimer > 0.001f;
        DrawNamed(strainedFace ? MeshCatalog.CharFaceStrain : MeshCatalog.CharFaceNeutral, 0, _instStaging, headMat.Emit(_instStaging, 0), ref drawCalls, ref tris);

        int nThigh = 0;
        nThigh = thighL.Emit(_instStaging, nThigh);
        nThigh = thighR.Emit(_instStaging, nThigh);
        DrawNamed(MeshCatalog.CharLeg, 0, _instStaging, nThigh, ref drawCalls, ref tris);

        int nBoot = 0;
        nBoot = calfL.Emit(_instStaging, nBoot);
        nBoot = calfR.Emit(_instStaging, nBoot);
        DrawNamed(MeshCatalog.CharCalfBoot, 0, _instStaging, nBoot, ref drawCalls, ref tris);

        int nArm = 0;
        nArm = upperArmL.Emit(_instStaging, nArm, cr, cg, cb);
        nArm = upperArmR.Emit(_instStaging, nArm, cr, cg, cb);
        DrawNamed(MeshCatalog.CharArm, 0, _instStaging, nArm, ref drawCalls, ref tris);

        int nHand = 0;
        nHand = forearmL.Emit(_instStaging, nHand);
        nHand = forearmR.Emit(_instStaging, nHand);
        DrawNamed(MeshCatalog.CharForearmHand, 0, _instStaging, nHand, ref drawCalls, ref tris);

        // Complete Indonesian Harvester Accessories: Sunglasses, Waist Parang Sheath, Hats, Backpacks/Baskets & Tools!
        if (av.Glasses)
        {
            DrawNamed(MeshCatalog.AccGlasses, 0, _instStaging, headMat.Emit(_instStaging, 0), ref drawCalls, ref tris);
        }
        if (av.WaistParang)
        {
            DrawNamed(MeshCatalog.AccParangWaist, 0, _instStaging, torsoMat.Child(0.175f, 0.10f, -0.02f).Emit(_instStaging, 0), ref drawCalls, ref tris);
        }
        if (!string.IsNullOrEmpty(av.Hat) && av.Hat != "none")
        {
            DrawNamed(av.Hat, 0, _instStaging, headMat.Child(0f, 0.21f, 0f).Emit(_instStaging, 0, cr, cg, cb), ref drawCalls, ref tris);
        }
        if (!string.IsNullOrEmpty(av.Back) && av.Back != "none")
        {
            float windBack = av.Back == MeshCatalog.BackCape ? 0.65f : 0.18f;
            DrawNamed(av.Back, 0, _instStaging, torsoMat.Child(0f, 0.34f, -0.14f).Emit(_instStaging, 0, cr, cg, cb, windBack), ref drawCalls, ref tris);
        }

        string toolMesh = string.IsNullOrEmpty(av.Tool) ? MeshCatalog.ToolEgrek : av.Tool;
        if (stance == HoldStance.CarryingTbs)
        {
            var heldFruit = torsoMat.Child(0f, 0.31f, 0.39f, rx: 0.35f, sx: 0.86f, sy: 0.86f, sz: 0.86f);
            DrawNamed(MeshCatalog.TbsBunch, 0, _instStaging,
                heldFruit.Emit(_instStaging, 0, heldGold ? 2.35f : 1.04f, heldGold ? 1.80f : 1.02f, heldGold ? 0.45f : 1f),
                ref drawCalls, ref tris);
            DrawNamed(toolMesh, 0, _instStaging, torsoMat.Child(-0.08f, 0.15f, -0.22f, rx: -0.18f, rz: -0.42f, sx: 0.72f, sy: 0.72f, sz: 0.72f).Emit(_instStaging, 0), ref drawCalls, ref tris);
        }
        else if (stance == HoldStance.PushingAngkong)
        {
            DrawNamed(toolMesh, 0, _instStaging, torsoMat.Child(-0.08f, 0.15f, -0.22f, rx: -0.18f, rz: -0.42f, sx: 0.72f, sy: 0.72f, sz: 0.72f).Emit(_instStaging, 0), ref drawCalls, ref tris);
        }
        else
        {
            float slashPitch = 0.14f;
            float slashLiftY = 0.22f;
            if (slashTimer > 0.001f)
            {
                float sk = 1f - System.Math.Clamp(slashTimer / 0.68f, 0f, 1f);
                float reach = sk < 0.44f ? MathF.Sin((sk / 0.44f) * (MathF.PI * 0.5f)) : MathF.Cos(((sk - 0.44f) / 0.56f) * (MathF.PI * 0.5f));
                float pull = sk >= 0.44f ? MathF.Sin(((sk - 0.44f) / 0.56f) * MathF.PI) : 0f;
                slashPitch = 0.14f - reach * 0.46f + pull * 0.88f;
                slashLiftY = 0.22f + reach * 0.58f - pull * 0.26f;
            }
            var toolMat = torsoMat.Child(0.03f, slashLiftY, 0.34f, rx: slashPitch, rz: 0.08f);
            DrawNamed(toolMesh, 0, _instStaging, toolMat.Emit(_instStaging, 0), ref drawCalls, ref tris);
        }
    }

    private void ConfigureAnimeOutlineUniforms()
    {
        switch (Quality.OutlineTier)
        {
            case AnimeOutlineTier.Bold:
                GLES30.GlUniform1f(_uOutlineWidth, 0.0052f);
                GLES30.GlUniform1f(_uOutlineStrength, 0.85f);
                break;
            case AnimeOutlineTier.Subtle:
                GLES30.GlUniform1f(_uOutlineWidth, 0.0032f);
                GLES30.GlUniform1f(_uOutlineStrength, 0.45f);
                break;
            default:
                GLES30.GlUniform1f(_uOutlineWidth, 0.0f);
                GLES30.GlUniform1f(_uOutlineStrength, 0.0f);
                break;
        }
    }

    private static bool AllowsSilhouetteOutline(string meshName) =>
        meshName != MeshCatalog.PalmCrown &&
        meshName != MeshCatalog.PalmSapling &&
        meshName != MeshCatalog.TropicalFern &&
        meshName != MeshCatalog.CutPalmFrond &&
        meshName != MeshCatalog.TireTrackSegment &&
        meshName != MeshCatalog.CanterHeadlightBeam &&
        meshName != MeshCatalog.VfxPuffQuad &&
        meshName != MeshCatalog.SteamPuff &&
        meshName != MeshCatalog.CharFaceNeutral &&
        meshName != MeshCatalog.CharFaceStrain &&
        meshName != MeshCatalog.GarageShowroom &&
        meshName != MeshCatalog.BackCape;

    private void DrawNamed(string meshName, int lod, float[] instBuf, int count, ref int drawCalls, ref int tris)
    {
        if (count <= 0 || !_gpuMeshes.TryGetValue(meshName, out var lods)) return;
        int idx = System.Math.Min(lod, lods.Length - 1);
        var handle = lods[idx];
        DrawGpuHandle(handle, instBuf, count, ref drawCalls, ref tris);

        // Zero-upload Inverted-Hull Geometric Anime Silhouette Pass (reuses already-bound VAO + _instanceVbo!)
        if (_allowOutlinePass && Quality.OutlineTier != AnimeOutlineTier.Off && lod <= 1 && AllowsSilhouetteOutline(meshName))
        {
            int clamped = System.Math.Min(count, MaxInstancesPerBatch);
            GLES30.GlEnable(0x0B44);   // GL_CULL_FACE
            GLES30.GlCullFace(0x0404); // GL_FRONT -> renders extruded backfaces along vertex normal
            GLES30.GlUniform1i(_uRenderMode, 3);
            GLES30.GlDrawElementsInstanced(GLES30.GlTriangles, handle.IndexCount, GLES30.GlUnsignedShort, 0, clamped);
            GLES30.GlUniform1i(_uRenderMode, 0);
            GLES30.GlDisable(0x0B44);
            drawCalls++;
        }
    }

    private void DrawGpuHandle(GpuMeshHandle? handle, float[] instBuf, int count, ref int drawCalls, ref int tris)
    {
        if (handle == null || count <= 0 || _directFloatBuffer == null) return;
        int clamped = System.Math.Min(count, MaxInstancesPerBatch);

        _directFloatBuffer.Clear();
        _directFloatBuffer.Put(instBuf, 0, clamped * 16);
        _directFloatBuffer.Position(0);

        GLES30.GlBindVertexArray(handle.Vao);
        GLES30.GlBindBuffer(GLES30.GlArrayBuffer, _instanceVbo);
        GLES30.GlBufferSubData(GLES30.GlArrayBuffer, 0, clamped * 64, _directFloatBuffer);
        GLES30.GlDrawElementsInstanced(GLES30.GlTriangles, handle.IndexCount, GLES30.GlUnsignedShort, 0, clamped);
        drawCalls++;
        tris += (handle.IndexCount / 3) * clamped;
    }

    private GpuMeshHandle UploadMeshToGpu(MeshLodSlice slice)
    {
        int[] vaos = new int[1];
        GLES30.GlGenVertexArrays(1, vaos, 0);
        int vao = vaos[0];
        GLES30.GlBindVertexArray(vao);

        int[] bufs = new int[2];
        GLES30.GlGenBuffers(2, bufs, 0);

        using var vDirect = ByteBuffer.AllocateDirect(slice.VertexStream.Length).Order(ByteOrder.NativeOrder()!);
        vDirect.Put(slice.VertexStream);
        vDirect.Position(0);
        GLES30.GlBindBuffer(GLES30.GlArrayBuffer, bufs[0]);
        GLES30.GlBufferData(GLES30.GlArrayBuffer, slice.VertexStream.Length, vDirect, GLES30.GlStaticDraw);

        GLES30.GlEnableVertexAttribArray(0);
        GLES30.GlVertexAttribPointer(0, 3, GLES30.GlFloat, false, 36, 0);
        GLES30.GlEnableVertexAttribArray(1);
        GLES30.GlVertexAttribPointer(1, 3, GLES30.GlFloat, false, 36, 12);
        GLES30.GlEnableVertexAttribArray(2);
        GLES30.GlVertexAttribPointer(2, 2, GLES30.GlFloat, false, 36, 24);
        GLES30.GlEnableVertexAttribArray(3);
        GLES30.GlVertexAttribPointer(3, 4, GLES30.GlUnsignedByte, true, 36, 32);

        using var iDirect = ByteBuffer.AllocateDirect(slice.IndexStream.Length).Order(ByteOrder.NativeOrder()!);
        iDirect.Put(slice.IndexStream);
        iDirect.Position(0);
        GLES30.GlBindBuffer(GLES30.GlElementArrayBuffer, bufs[1]);
        GLES30.GlBufferData(GLES30.GlElementArrayBuffer, slice.IndexStream.Length, iDirect, GLES30.GlStaticDraw);

        GLES30.GlBindBuffer(GLES30.GlArrayBuffer, _instanceVbo);
        for (int k = 0; k < 4; k++)
        {
            int loc = 4 + k;
            GLES30.GlEnableVertexAttribArray(loc);
            GLES30.GlVertexAttribPointer(loc, 4, GLES30.GlFloat, false, 64, k * 16);
            GLES30.GlVertexAttribDivisor(loc, 1);
        }

        GLES30.GlBindVertexArray(0);
        return new GpuMeshHandle { Vao = vao, IndexCount = slice.IndexCount };
    }

    private static int BuildLinkedProgram(string vsSrc, string fsSrc)
    {
        int vs = CompileShader(GLES30.GlVertexShader, vsSrc);
        int fs = CompileShader(GLES30.GlFragmentShader, fsSrc);
        int prog = GLES30.GlCreateProgram();
        GLES30.GlAttachShader(prog, vs);
        GLES30.GlAttachShader(prog, fs);
        GLES30.GlLinkProgram(prog);
        GLES30.GlDeleteShader(vs);
        GLES30.GlDeleteShader(fs);

        int[] ok = new int[1];
        GLES30.GlGetProgramiv(prog, GLES30.GlLinkStatus, ok, 0);
        if (ok[0] == 0)
        {
            string log = GLES30.GlGetProgramInfoLog(prog) ?? "unknown link error";
            throw new InvalidOperationException($"GLSL ES 3.0 program link failed: {log}");
        }
        return prog;
    }

    private static int CompileShader(int type, string src)
    {
        int sh = GLES30.GlCreateShader(type);
        GLES30.GlShaderSource(sh, src);
        GLES30.GlCompileShader(sh);
        int[] ok = new int[1];
        GLES30.GlGetShaderiv(sh, GLES30.GlCompileStatus, ok, 0);
        if (ok[0] == 0)
        {
            string log = GLES30.GlGetShaderInfoLog(sh) ?? "unknown shader error";
            throw new InvalidOperationException($"GLSL ES 3.0 compile failed: {log}");
        }
        return sh;
    }

    private static void InvertMatrix4(ReadOnlySpan<float> m, Span<float> invOut)
    {
        Span<float> inv = stackalloc float[16];
        inv[0] = m[5] * m[10] * m[15] - m[5] * m[11] * m[14] - m[9] * m[6] * m[15] + m[9] * m[7] * m[14] + m[13] * m[6] * m[11] - m[13] * m[7] * m[10];
        inv[4] = -m[4] * m[10] * m[15] + m[4] * m[11] * m[14] + m[8] * m[6] * m[15] - m[8] * m[7] * m[14] - m[12] * m[6] * m[11] + m[12] * m[7] * m[10];
        inv[8] = m[4] * m[9] * m[15] - m[4] * m[11] * m[13] - m[8] * m[5] * m[15] + m[8] * m[7] * m[13] + m[12] * m[5] * m[11] - m[12] * m[7] * m[9];
        inv[12] = -m[4] * m[9] * m[14] + m[4] * m[10] * m[13] + m[8] * m[5] * m[14] - m[8] * m[6] * m[13] - m[12] * m[5] * m[10] + m[12] * m[6] * m[9];
        inv[1] = -m[1] * m[10] * m[15] + m[1] * m[11] * m[14] + m[9] * m[2] * m[15] - m[9] * m[3] * m[14] - m[13] * m[2] * m[11] + m[13] * m[3] * m[10];
        inv[5] = m[0] * m[10] * m[15] - m[0] * m[11] * m[14] - m[8] * m[2] * m[15] + m[8] * m[3] * m[14] + m[12] * m[2] * m[11] - m[12] * m[3] * m[10];
        inv[9] = -m[0] * m[9] * m[15] + m[0] * m[11] * m[13] + m[8] * m[1] * m[15] - m[8] * m[3] * m[13] - m[12] * m[1] * m[11] + m[12] * m[3] * m[9];
        inv[13] = m[0] * m[9] * m[14] - m[0] * m[10] * m[13] - m[8] * m[1] * m[14] + m[8] * m[2] * m[13] + m[12] * m[1] * m[10] - m[12] * m[2] * m[9];
        inv[2] = m[1] * m[6] * m[15] - m[1] * m[7] * m[14] - m[5] * m[2] * m[15] + m[5] * m[3] * m[14] + m[13] * m[2] * m[7] - m[13] * m[3] * m[6];
        inv[6] = -m[0] * m[6] * m[15] + m[0] * m[7] * m[14] + m[4] * m[2] * m[15] - m[4] * m[3] * m[14] - m[12] * m[2] * m[7] + m[12] * m[3] * m[6];
        inv[10] = m[0] * m[5] * m[15] - m[0] * m[7] * m[13] - m[4] * m[1] * m[15] + m[4] * m[3] * m[13] + m[12] * m[1] * m[7] - m[12] * m[3] * m[5];
        inv[14] = -m[0] * m[5] * m[14] + m[0] * m[6] * m[13] + m[4] * m[1] * m[14] + -m[4] * m[2] * m[13] - m[12] * m[1] * m[6] + m[12] * m[2] * m[5];
        inv[3] = -m[1] * m[6] * m[11] + m[1] * m[7] * m[10] + m[5] * m[2] * m[11] - m[5] * m[3] * m[10] - m[9] * m[2] * m[7] + m[9] * m[3] * m[6];
        inv[7] = m[0] * m[6] * m[11] - m[0] * m[7] * m[10] - m[4] * m[2] * m[11] + m[4] * m[3] * m[10] + m[8] * m[2] * m[7] - m[8] * m[3] * m[6];
        inv[11] = -m[0] * m[5] * m[11] + m[0] * m[7] * m[10] + m[4] * m[1] * m[11] - m[4] * m[3] * m[10] - m[8] * m[1] * m[7] + m[8] * m[3] * m[5];
        inv[15] = m[0] * m[5] * m[10] - m[0] * m[6] * m[9] - m[4] * m[1] * m[10] + m[4] * m[2] * m[9] + m[8] * m[1] * m[6] - m[8] * m[2] * m[5];

        float det = m[0] * inv[0] + m[1] * inv[4] + m[2] * inv[8] + m[3] * inv[12];
        if (MathF.Abs(det) < 1e-8f)
        {
            invOut.Clear();
            invOut[0] = invOut[5] = invOut[10] = invOut[15] = 1f;
            return;
        }
        float invDet = 1f / det;
        for (int i = 0; i < 16; i++) invOut[i] = inv[i] * invDet;
    }
}
