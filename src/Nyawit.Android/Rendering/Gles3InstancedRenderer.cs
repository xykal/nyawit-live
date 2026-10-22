using System;
using System.Collections.Generic;
using System.Diagnostics;
using Android.Content;
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
    Lobby = 0,
    PreparingWorld = 1,
    Gameplay = 2,
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

/// <summary>
/// NyawitEngine v3.0 Watertight OpenGL ES 3.0 Hardware-Instanced PBR Renderer &amp; Full RigidBody Integrator:
///   - Zero mesh holes ("0% bolong-bolong"): GL_CULL_FACE disabled + gl_FrontFacing normal orientation + watertight NPAK v3.0
///   - 3D Main Lobby Showcase Stage + "MENYIAPKAN DUNIA..." Loading Stage + Live Multiplayer Plantation World
///   - Full 11-Part Articulated Human Anatomy Rig (Head/Face/Eyes/Hair + Torso/Belt + UpperArm + Forearm/5-Finger Hand + Thigh + Calf/Boot)
///   - Full Action &amp; Hold Animations: Two-Hand Egrek Grip &amp; Slash, Knee-Squat Ground Pickup, Two-Hand TBS Chest Hold, Parabolic Throw, Angkong Push, Seated Steering
///   - 4-Wheel Spring-Damper Vehicle Suspension + Steered Front Wheels + Rolling Tires + Chassis Pitch/Roll ("Canter Oleng")
/// </summary>
public sealed class Gles3InstancedRenderer : Java.Lang.Object, GLSurfaceView.IRenderer
{
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
out vec4 fragColor;
void main() {
    vec3 d = normalize(vRay);
    float up = clamp(d.y * 1.15 + 0.06, 0.0, 1.0);
    vec3 col = mix(uSkyHorizon, uSkyZenith, pow(up, 0.62));
    float sd = max(dot(d, normalize(uSunDir)), 0.0);
    col += uSunColor * (pow(sd, 12.0) * 0.28 + smoothstep(0.9965, 0.9994, sd) * 1.85);
    col = (col * (2.51 * col + 0.03)) / (col * (2.43 * col + 0.59) + 0.14);
    fragColor = vec4(pow(clamp(col, 0.0, 1.0), vec3(0.4545)), 1.0);
}";

    private const string ShadowVertexSrc = @"#version 300 es
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

    private const string ShadowFragmentSrc = @"#version 300 es
precision highp float;
in float vAlpha;
out vec4 fragColor;
void main() {
    fragColor = vec4(0.02, 0.05, 0.04, clamp(vAlpha * 0.56, 0.0, 0.62));
}";

    private const string VertexShaderSrc = @"#version 300 es
precision highp float;
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec2 aUV;
layout(location = 3) in vec4 aColor;
layout(location = 4) in vec4 iRow0;
layout(location = 5) in vec4 iRow1;
layout(location = 6) in vec4 iRow2;
layout(location = 7) in vec4 iTintAndWind;

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

    float windAmp = iTintAndWind.w;
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
    vNormal = normalize(rotScale * aNormal);
    vWorldPos = worldPos;
    vColor = aColor;
    vTint = iTintAndWind.rgb;
    vUV = aUV;
    gl_Position = uVP * vec4(worldPos, 1.0);
}";

    private const string FragmentShaderSrc = @"#version 300 es
precision highp float;
in vec3 vNormal;
in vec3 vWorldPos;
in vec4 vColor;
in vec3 vTint;
in vec2 vUV;

uniform vec3 uSunDir;
uniform vec3 uSunColor;
uniform vec3 uSkyTop;
uniform vec3 uGroundBounce;
uniform vec3 uFogColor;
uniform vec3 uCamPos;
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
    // True double-sided surface shading guarantee: backfaces orient cleanly toward camera!
    vec3 N = normalize(vNormal) * (gl_FrontFacing ? 1.0 : -1.0);
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
        vec3 outEm = mix(hdrEm, uFogColor, fogEm);
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
    vec3 hdr = mix(lit, uFogColor, clamp(fogAmt, 0.0, 0.88));

    vec3 mapped = (hdr * (2.51 * hdr + 0.03)) / (hdr * (2.43 * hdr + 0.59) + 0.14);
    fragColor = vec4(pow(clamp(mapped, 0.0, 1.0), vec3(0.4545)), 1.0);
}";

    private readonly Context? _context;
    private readonly NpakArchive? _archive;
    private readonly List<PalmTreeNode> _trees = [];
    private readonly LiveMultiplayerSession? _net;
    private readonly List<StaticPropInstance> _ferns = [];
    private readonly List<StaticPropInstance> _rocks = [];

    public RigidBodyWorld Physics { get; } = null!;
    public QualityGovernor Quality { get; } = new();
    public AppSceneStage Stage { get; private set; } = AppSceneStage.Lobby;
    public float WorldPrepProgress { get; private set; }
    public string WorldPrepStatus { get; private set; } = "MENYIAPKAN DUNIA...";
    public float LobbyAvatarSpinOffset { get; set; }

    public event Action<float>? OnRenderScaleChanged;
    public event Action? OnWorldReady;

    private readonly Dictionary<string, GpuMeshHandle[]> _gpuMeshes = new(StringComparer.Ordinal);
    private GpuMeshHandle? _terrainGpu;
    private GpuMeshHandle? _waterGpu;
    private GpuMeshHandle? _shadowGpu;
    private int _skyProgram, _skyVao, _uSkyInvVp, _uSkyZenith, _uSkyHorizon, _uSkySunDir, _uSkySunCol;
    private int _shadowProgram, _uShadowVp;
    private int _program;
    private int _instanceVbo;
    private int _uVp, _uTime, _uSunDir, _uSunColor, _uSkyTop, _uGroundBounce, _uFogColor, _uCamPos, _uFogDensity, _uDetailStrength;
    private bool _gpuReady;

    private const int MaxInstancesPerBatch = 1024;
    private readonly float[] _instStaging = new float[MaxInstancesPerBatch * 16];
    private readonly float[] _shadowStaging = new float[MaxInstancesPerBatch * 16];
    private readonly float[][] _treeLodStaging = [new float[256 * 16], new float[256 * 16], new float[256 * 16]];
    private readonly float[] _fruitStaging = new float[256 * 16];
    private readonly float[] _goldStaging = new float[128 * 16];
    private readonly float[] _treePositionsXyz = [];
    private readonly sbyte[] _treeLodResult = [];
    private FloatBuffer? _directFloatBuffer;

    public bool InTruck;
    public float BoostTimer;
    public float JoyX, JoyY;
    public float CamYaw = 0.25f, CamPitch = 0.30f, CamDist = 7.8f;
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

    private int _surfaceWidth = 1280, _surfaceHeight = 720;
    private float _appliedScale = -1f;
    private readonly Stopwatch _clock = Stopwatch.StartNew();
    private double _lastTimeSec;
    private double _nextNetSyncSec;

    private readonly float[] _proj = new float[16];
    private readonly float[] _view = new float[16];
    private readonly float[] _vp = new float[16];
    private readonly float[] _invVp = new float[16];

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
        Physics = new RigidBodyWorld(trees, rocks);

        _treePositionsXyz = new float[_trees.Count * 3];
        _treeLodResult = new sbyte[_trees.Count];
        for (int i = 0; i < _trees.Count; i++)
        {
            _treePositionsXyz[i * 3 + 0] = _trees[i].X;
            _treePositionsXyz[i * 3 + 1] = _trees[i].Y;
            _treePositionsXyz[i * 3 + 2] = _trees[i].Z;
        }

        _net.OnHarvestSpawnFruit += (tx, tz, isGold) =>
        {
            if (InTruck) Physics.LaunchDirectTreeToTruckArc(tx, tz, isGold);
            else Physics.SpawnHarvestedGroundFruit(tx, tz, isGold);
        };
        Physics.OnCargoLandedInVehicle += (units, isGold) =>
        {
            _net.SendLoadTbs(units, isGold ? 1 : 0);
        };
    }

    public List<PalmTreeNode> Trees => _trees;

    public void BeginWorldPreparation()
    {
        if (Stage == AppSceneStage.PreparingWorld) return;
        WorldPrepProgress = 0.02f;
        WorldPrepStatus = "MEMBANGUN TOPOGRAFI KEBUN SAWIT & PARIT...";
        Stage = AppSceneStage.PreparingWorld;
    }

    public void ReturnToLobby()
    {
        InTruck = false;
        JoyX = JoyY = 0f;
        Stage = AppSceneStage.Lobby;
    }

    public void RequestPresetChange(GraphicsPreset preset)
    {
        Quality.SetManualPreset(preset);
        EnsureRenderScaleSynced();
    }

    private void EnsureRenderScaleSynced()
    {
        float target = Quality.Active.RenderScale;
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
            // Bring Canter close in front/beside player if parked far away, or climb straight in!
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
        if (_archive == null) return;

        int byteCap = MaxInstancesPerBatch * 16 * sizeof(float);
        var initByteBuf = ByteBuffer.AllocateDirect(byteCap).Order(ByteOrder.NativeOrder()!);
        _directFloatBuffer = initByteBuf.AsFloatBuffer()!;

        _skyProgram = BuildLinkedProgram(SkyVertexSrc, SkyFragmentSrc);
        _uSkyInvVp = GLES30.GlGetUniformLocation(_skyProgram, "uInvVP");
        _uSkyZenith = GLES30.GlGetUniformLocation(_skyProgram, "uSkyZenith");
        _uSkyHorizon = GLES30.GlGetUniformLocation(_skyProgram, "uSkyHorizon");
        _uSkySunDir = GLES30.GlGetUniformLocation(_skyProgram, "uSunDir");
        _uSkySunCol = GLES30.GlGetUniformLocation(_skyProgram, "uSunColor");

        int[] skyVaos = new int[1];
        GLES30.GlGenVertexArrays(1, skyVaos, 0);
        _skyVao = skyVaos[0];

        _shadowProgram = BuildLinkedProgram(ShadowVertexSrc, ShadowFragmentSrc);
        _uShadowVp = GLES30.GlGetUniformLocation(_shadowProgram, "uVP");

        _program = BuildLinkedProgram(VertexShaderSrc, FragmentShaderSrc);
        _uVp = GLES30.GlGetUniformLocation(_program, "uVP");
        _uTime = GLES30.GlGetUniformLocation(_program, "uTime");
        _uSunDir = GLES30.GlGetUniformLocation(_program, "uSunDir");
        _uSunColor = GLES30.GlGetUniformLocation(_program, "uSunColor");
        _uSkyTop = GLES30.GlGetUniformLocation(_program, "uSkyTop");
        _uGroundBounce = GLES30.GlGetUniformLocation(_program, "uGroundBounce");
        _uFogColor = GLES30.GlGetUniformLocation(_program, "uFogColor");
        _uCamPos = GLES30.GlGetUniformLocation(_program, "uCamPos");
        _uFogDensity = GLES30.GlGetUniformLocation(_program, "uFogDensity");
        _uDetailStrength = GLES30.GlGetUniformLocation(_program, "uDetailStrength");

        int[] bufs = new int[1];
        GLES30.GlGenBuffers(1, bufs, 0);
        _instanceVbo = bufs[0];
        initByteBuf.Position(0);
        GLES30.GlBindBuffer(GLES30.GlArrayBuffer, _instanceVbo);
        GLES30.GlBufferData(GLES30.GlArrayBuffer, byteCap, initByteBuf, GLES30.GlDynamicDraw);

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
        _shadowGpu = UploadMeshToGpu(PlantationWorld.BuildSoftShadowDiscMesh(16));

        GLES30.GlEnable(GLES30.GlDepthTest);
        // Disable backface culling so no open botanical/fabric or mirrored surface ever renders hollow!
        GLES30.GlDisable(0x0B44);
        _gpuReady = true;
        _lastTimeSec = _clock.Elapsed.TotalSeconds;
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

        double now = _clock.Elapsed.TotalSeconds;
        float dt = (float)System.Math.Clamp(now - _lastTimeSec, 0.001, 0.05);
        _lastTimeSec = now;
        Time.TotalTime = (float)now;
        Time.DeltaTime = dt;
        if (Quality.RecordFrame(dt))
            EnsureRenderScaleSynced();

        if (Stage == AppSceneStage.PreparingWorld)
        {
            StepWorldPreparation(dt);
        }
        else if (Stage == AppSceneStage.Gameplay)
        {
            StepGameplayPhysics(dt, now);
        }
        else
        {
            Physics.Player.IdleBreathPhase += dt * 2.2f;
        }

        Render3DWorld((float)now, dt);
    }

    private void StepWorldPreparation(float dt)
    {
        if (!_gpuReady) return;
        float stepDt = System.Math.Max(dt, 0.033f);
        WorldPrepProgress = System.Math.Min(1.0f, WorldPrepProgress + stepDt * 0.44f);

        if (WorldPrepProgress < 0.25f)
            WorldPrepStatus = "MEMBANGUN TOPOGRAFI KEBUN SAWIT & PARIT...";
        else if (WorldPrepProgress < 0.52f)
            WorldPrepStatus = $"MEMUAT FISIKA RIGIDBODY & {Physics.StaticColliders.Count} COLLIDER SOLID...";
        else if (WorldPrepProgress < 0.78f)
            WorldPrepStatus = "MENYIAPKAN SUSPENSI 4 RODA TRUK CANTER & ANGKONG...";
        else if (WorldPrepProgress < 0.96f)
            WorldPrepStatus = $"SINKRONISASI SERVER LIVE ({_net?.CurrentRoomId.ToUpperInvariant()})...";
        else
            WorldPrepStatus = "DUNIA SIAP - SELAMAT MEMANEN!";

        Physics.StepWorld(dt, inTruck: false, inputSide: 0f, inputForward: 0f, camYaw: CamYaw, boars: _boarsSnap);

        if (WorldPrepProgress >= 1.0f)
        {
            Stage = AppSceneStage.Gameplay;
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

        // Smooth camera follow behind Canter when driving!
        if (!LockShowcaseCam && InTruck && MathF.Abs(Physics.MainTruck.SpeedMs) > 0.6f)
        {
            float desiredCamYaw = Physics.MainTruck.Yaw + MathF.PI;
            float diff = desiredCamYaw - CamYaw;
            while (diff > MathF.PI) diff -= MathF.PI * 2f;
            while (diff < -MathF.PI) diff += MathF.PI * 2f;
            CamYaw += diff * MathF.Min(1f, dt * 3.1f);
        }

        // Nearest ripe tree within harvest reach
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

    private void Render3DWorld(float now, float dt)
    {
        if (_net == null) return;
        var q = Quality.Active;
        GLES30.GlViewport(0, 0, _surfaceWidth, _surfaceHeight);

        bool storm = _net.EventKind == "HUJAN_BADAI";
        bool goldRush = _net.EventKind == "DEMAM_SAWIT_EMAS";

        GLES30.GlClearColor(0.24f, 0.56f, 0.86f, 1.0f);
        GLES30.GlClear(GLES30.GlColorBufferBit | GLES30.GlDepthBufferBit);

        float eyeX, eyeY, eyeZ, lookX, lookY, lookZ, fovDeg;
        if (Stage == AppSceneStage.Lobby)
        {
            // Heroic 3D Main Lobby Showroom Stage: close-up full-body view of Avatar + Canter Truck + PKS backdrop!
            float gy = RigidBodyWorld.SurfaceHeightWithStructures(8.0f, 6.0f);
            lookX = 8.35f;
            lookY = gy + 1.18f;
            lookZ = 5.45f;
            float orbit = MathF.Sin(now * 0.42f) * 0.14f;
            eyeX = 8.0f + MathF.Sin(orbit) * 3.55f;
            eyeY = gy + 1.56f;
            eyeZ = 6.0f + MathF.Cos(orbit) * 3.55f;
            fovDeg = 46f;
        }
        else if (Stage == AppSceneStage.PreparingWorld)
        {
            // Cinematic sweeping fly-in camera descending smoothly from panoramic aerial view straight to shoulder!
            float t = WorldPrepProgress;
            float ease = t * t * (3f - 2f * t);
            float dist = (1f - ease) * 34f + ease * CamDist;
            float pitch = (1f - ease) * 0.72f + ease * CamPitch;
            float yaw = CamYaw + (1f - ease) * 1.15f;
            eyeX = PlayerX + MathF.Sin(yaw) * MathF.Cos(pitch) * dist;
            eyeZ = PlayerZ + MathF.Cos(yaw) * MathF.Cos(pitch) * dist;
            eyeY = System.Math.Max(PlantationWorld.TerrainHeight(eyeX, eyeZ) + 1.25f, PlayerY + 1.65f + MathF.Sin(pitch) * dist);
            lookX = PlayerX;
            lookY = PlayerY + 1.45f;
            lookZ = PlayerZ;
            fovDeg = 55f;
        }
        else
        {
            if (LockShowcaseCam && InTruck)
                CamYaw = Physics.MainTruck.Yaw + 0.68f;

            float dist = InTruck ? (LockShowcaseCam ? CamDist : CamDist * 1.22f) : CamDist;
            eyeX = PlayerX + MathF.Sin(CamYaw) * MathF.Cos(CamPitch) * dist;
            eyeZ = PlayerZ + MathF.Cos(CamYaw) * MathF.Cos(CamPitch) * dist;
            float baseEyeH = LockShowcaseCam ? (InTruck ? 1.05f : 1.16f) : 1.62f;
            eyeY = System.Math.Max(PlantationWorld.TerrainHeight(eyeX, eyeZ) + (LockShowcaseCam ? 0.85f : 1.25f), PlayerY + baseEyeH + MathF.Sin(CamPitch) * dist);
            lookX = PlayerX;
            lookY = PlayerY + (LockShowcaseCam ? (InTruck ? 1.18f : 1.20f) : (InTruck ? 1.68f : 1.38f));
            lookZ = PlayerZ;
            fovDeg = LockShowcaseCam ? 47f : 56f;
        }

        Mat4Utils.CreatePerspective(_proj, fovDeg * MathF.PI / 180f, _surfaceWidth / (float)_surfaceHeight, 0.30f, 260f);
        Mat4Utils.CreateLookAt(_view, eyeX, eyeY, eyeZ, lookX, lookY, lookZ);
        Mat4Utils.Multiply(_vp, _proj, _view);
        InvertMatrix4(_vp, _invVp);

        int drawCalls = 0, tris = 0;

        // Pass 0: Atmospheric Sky Gradient + Solar Halo Dome
        GLES30.GlDepthMask(false);
        GLES30.GlDisable(GLES30.GlDepthTest);
        GLES30.GlUseProgram(_skyProgram);
        GLES30.GlUniformMatrix4fv(_uSkyInvVp, 1, false, _invVp, 0);
        GLES30.GlUniform3f(_uSkySunDir, 0.48f, 0.72f, 0.44f);
        if (storm)
        {
            GLES30.GlUniform3f(_uSkyZenith, 0.03f, 0.06f, 0.13f);
            GLES30.GlUniform3f(_uSkyHorizon, 0.11f, 0.16f, 0.24f);
            GLES30.GlUniform3f(_uSkySunCol, 0.28f, 0.34f, 0.48f);
        }
        else if (goldRush)
        {
            GLES30.GlUniform3f(_uSkyZenith, 0.05f, 0.16f, 0.46f);
            GLES30.GlUniform3f(_uSkyHorizon, 0.72f, 0.42f, 0.14f);
            GLES30.GlUniform3f(_uSkySunCol, 1.55f, 0.95f, 0.35f);
        }
        else
        {
            GLES30.GlUniform3f(_uSkyZenith, 0.035f, 0.17f, 0.58f);
            GLES30.GlUniform3f(_uSkyHorizon, 0.34f, 0.62f, 0.88f);
            GLES30.GlUniform3f(_uSkySunCol, 1.45f, 1.25f, 0.86f);
        }
        GLES30.GlBindVertexArray(_skyVao);
        GLES30.GlDrawArrays(GLES30.GlTriangleStrip, 0, 4);
        drawCalls++;
        tris += 2;
        GLES30.GlEnable(GLES30.GlDepthTest);
        GLES30.GlDepthMask(true);

        // Pass 1: Main Double-Sided Watertight PBR Scene
        GLES30.GlUseProgram(_program);
        GLES30.GlUniformMatrix4fv(_uVp, 1, false, _vp, 0);
        GLES30.GlUniform1f(_uTime, now);
        GLES30.GlUniform3f(_uSunDir, 0.48f, 0.72f, 0.44f);
        GLES30.GlUniform3f(_uCamPos, eyeX, eyeY, eyeZ);
        GLES30.GlUniform1f(_uDetailStrength, q.Preset == GraphicsPreset.Smooth ? 0.35f : 1.0f);

        if (storm)
        {
            GLES30.GlUniform3f(_uSunColor, 0.62f, 0.72f, 0.95f);
            GLES30.GlUniform3f(_uSkyTop, 0.14f, 0.20f, 0.32f);
            GLES30.GlUniform3f(_uGroundBounce, 0.05f, 0.07f, 0.05f);
            GLES30.GlUniform3f(_uFogColor, 0.11f, 0.16f, 0.24f);
            GLES30.GlUniform1f(_uFogDensity, 0.0090f);
        }
        else if (goldRush)
        {
            GLES30.GlUniform3f(_uSunColor, 2.35f, 1.55f, 0.72f);
            GLES30.GlUniform3f(_uSkyTop, 0.42f, 0.30f, 0.22f);
            GLES30.GlUniform3f(_uGroundBounce, 0.14f, 0.10f, 0.05f);
            GLES30.GlUniform3f(_uFogColor, 0.62f, 0.38f, 0.14f);
            GLES30.GlUniform1f(_uFogDensity, 0.0040f);
        }
        else
        {
            GLES30.GlUniform3f(_uSunColor, 2.15f, 1.92f, 1.48f);
            GLES30.GlUniform3f(_uSkyTop, 0.26f, 0.46f, 0.76f);
            GLES30.GlUniform3f(_uGroundBounce, 0.09f, 0.14f, 0.06f);
            GLES30.GlUniform3f(_uFogColor, 0.34f, 0.60f, 0.86f);
            GLES30.GlUniform1f(_uFogDensity, 0.0035f);
        }

        // 1. Terrain & Rippling Specular Canal Water
        int c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1);
        DrawGpuHandle(_terrainGpu, _instStaging, c, ref drawCalls, ref tris);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, 0, MathF.Sin(now * 1.4f) * 0.03f, 0, 0, 0, 0, 1, 1, 1);
        DrawGpuHandle(_waterGpu, _instStaging, c, ref drawCalls, ref tris);

        _net.CopyRenderState(_peersSnap, _boarsSnap, _chatSnap, dt);

        float fx = lookX - eyeX, fy = lookY - eyeY, fz = lookZ - eyeZ;
        float fl = MathF.Max(1e-4f, MathF.Sqrt(fx * fx + fy * fy + fz * fz));
        SimdCuller.SelectLodBatch(_treePositionsXyz, _trees.Count, eyeX, eyeY, eyeZ, fx / fl, fy / fl, fz / fl, q.Lod0Distance, q.Lod1Distance, q.MaxDrawDistance, _treeLodResult);

        // 1.5. Hardware-Instanced Soft Canopy, Vehicle & Character Contact Shadows!
        int nSh = 0;
        nSh = Mat4Utils.WriteInstanceTRS(_shadowStaging, nSh, PlantationWorld.PksX, PlantationWorld.TerrainHeight(PlantationWorld.PksX, PlantationWorld.PksZ), PlantationWorld.PksZ, 0, 0, 0, 7.6f, 1f, 6.2f, 0.95f);
        nSh = Mat4Utils.WriteInstanceTRS(_shadowStaging, nSh, PlantationWorld.MandorX, PlantationWorld.TerrainHeight(PlantationWorld.MandorX, PlantationWorld.MandorZ), PlantationWorld.MandorZ, 0, 0, 0, 2.9f, 1f, 2.9f, 0.85f);
        nSh = Mat4Utils.WriteInstanceTRS(_shadowStaging, nSh, Physics.MainTruck.X, Physics.MainTruck.Y, Physics.MainTruck.Z, 0, Physics.MainTruck.Yaw, 0, 1.45f, 1f, 2.95f, 1.0f);
        nSh = Mat4Utils.WriteInstanceTRS(_shadowStaging, nSh, Physics.YardTruck.X, Physics.YardTruck.Y, Physics.YardTruck.Z, 0, Physics.YardTruck.Yaw, 0, 1.45f, 1f, 2.95f, 1.0f);
        if (!InTruck)
            nSh = Mat4Utils.WriteInstanceTRS(_shadowStaging, nSh, PlayerX, Physics.Player.GroundedY, PlayerZ, 0, Physics.Player.Yaw, 0, 0.68f, 1f, 0.68f, 1.0f);

        for (int i = 0; i < Physics.Angkongs.Length; i++)
            nSh = Mat4Utils.WriteInstanceTRS(_shadowStaging, nSh, Physics.Angkongs[i].X, Physics.Angkongs[i].Y, Physics.Angkongs[i].Z, 0, Physics.Angkongs[i].Yaw, 0, 0.68f, 1f, 0.98f, 0.88f);

        for (int i = 0; i < _peersSnap.Count; i++)
        {
            var p = _peersSnap[i];
            nSh = Mat4Utils.WriteInstanceTRS(_shadowStaging, nSh, p.RenderX, p.RenderY, p.RenderZ, 0, p.RenderYaw, 0, p.InTruck ? 1.45f : 0.68f, 1f, p.InTruck ? 2.95f : 0.68f, 1.0f);
        }
        for (int i = 0; i < _boarsSnap.Count; i++)
        {
            var b = _boarsSnap[i];
            nSh = Mat4Utils.WriteInstanceTRS(_shadowStaging, nSh, b.X, PlantationWorld.TerrainHeight(b.X, b.Z), b.Z, 0, b.Yaw, 0, 0.72f, 1f, 0.98f, 0.90f);
        }
        for (int i = 0; i < _trees.Count; i++)
        {
            sbyte tier = _treeLodResult[i];
            if (tier < 0 || tier > (q.Preset == GraphicsPreset.Smooth ? 1 : 2)) continue;
            var t = _trees[i];
            nSh = Mat4Utils.WriteInstanceTRS(_shadowStaging, nSh, t.X + 0.45f, t.Y, t.Z + 0.35f, 0, 0, 0, 3.35f * t.Scale, 1f, 3.35f * t.Scale, tier == 2 ? 0.55f : 0.85f);
        }
        if (nSh > 0)
        {
            GLES30.GlUseProgram(_shadowProgram);
            GLES30.GlUniformMatrix4fv(_uShadowVp, 1, false, _vp, 0);
            GLES30.GlEnable(GLES30.GlBlend);
            GLES30.GlBlendFunc(GLES30.GlSrcAlpha, GLES30.GlOneMinusSrcAlpha);
            GLES30.GlDepthMask(false);
            DrawGpuHandle(_shadowGpu, _shadowStaging, nSh, ref drawCalls, ref tris);
            GLES30.GlDepthMask(true);
            GLES30.GlDisable(GLES30.GlBlend);
            GLES30.GlUseProgram(_program);
        }

        // 2. Living PKS Mill + Spinning Rooftop Turbines + Billowing Boiler Steam + RAM + Bridges + Mandor Post
        float pksGround = PlantationWorld.TerrainHeight(PlantationWorld.PksX, PlantationWorld.PksZ);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, PlantationWorld.PksX, pksGround, PlantationWorld.PksZ, 0, 0, 0, 1, 1, 1);
        DrawNamed(MeshCatalog.PksFactory, 0, _instStaging, c, ref drawCalls, ref tris);

        // Spinning industrial cyclone turbines on PKS rooftop!
        c = 0;
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, PlantationWorld.PksX - 1.5f, pksGround + 8.35f, PlantationWorld.PksZ - 1.6f, 0, now * 5.2f, 0, 1, 1, 1);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, PlantationWorld.PksX + 1.5f, pksGround + 8.35f, PlantationWorld.PksZ + 1.6f, 0, -now * 4.6f, 0, 1, 1, 1);
        DrawNamed(MeshCatalog.PksFan, 0, _instStaging, c, ref drawCalls, ref tris);

        // Rising billowing boiler steam clouds from twin PKS smokestacks + diesel truck exhaust!
        c = 0;
        for (int sp = 0; sp < 6; sp++)
        {
            float cycle = ((now * 0.42f + sp * 0.1666f) % 1.0f);
            float cxChim = sp % 2 == 0 ? (PlantationWorld.PksX - 3.2f) : (PlantationWorld.PksX - 1.0f);
            float sc = 0.85f + cycle * 2.15f;
            c = Mat4Utils.WriteInstanceTRS(
                _instStaging, c,
                cxChim + cycle * 2.2f + MathF.Sin(now + sp) * 0.25f,
                pksGround + 14.2f + cycle * 6.8f,
                PlantationWorld.PksZ - 2.2f + cycle * 1.4f,
                0, now * 0.6f + sp, 0, sc, sc * 0.82f, sc);
        }
        if (InTruck && MathF.Abs(Physics.MainTruck.SpeedMs) > 1.2f)
        {
            float exCycle = (now * 2.4f) % 1.0f;
            float syT = MathF.Sin(Physics.MainTruck.Yaw), cyT = MathF.Cos(Physics.MainTruck.Yaw);
            float exX = Physics.MainTruck.X + 0.85f * cyT + 0.86f * syT;
            float exZ = Physics.MainTruck.Z - 0.85f * syT + 0.86f * cyT;
            float exS = 0.22f + exCycle * 0.45f;
            c = Mat4Utils.WriteInstanceTRS(_instStaging, c, exX, Physics.MainTruck.Y + 2.48f + exCycle * 1.15f, exZ, 0, now * 3f, 0, exS, exS, exS);
        }
        DrawNamed(MeshCatalog.SteamPuff, 0, _instStaging, c, ref drawCalls, ref tris);

        c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, PlantationWorld.RamX, PlantationWorld.TerrainHeight(PlantationWorld.RamX, PlantationWorld.RamZ), PlantationWorld.RamZ, 0, 0, 0, 1, 1, 1);
        DrawNamed(MeshCatalog.WeighbridgeRam, 0, _instStaging, c, ref drawCalls, ref tris);

        c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, PlantationWorld.MandorX, PlantationWorld.TerrainHeight(PlantationWorld.MandorX, PlantationWorld.MandorZ), PlantationWorld.MandorZ, 0, 0.5f, 0, 1, 1, 1);
        DrawNamed(MeshCatalog.MandorPost, 0, _instStaging, c, ref drawCalls, ref tris);

        c = 0;
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, -28f, PlantationWorld.TerrainHeight(-28f, PlantationWorld.CanalZ - 4.7f), PlantationWorld.CanalZ, 0, 0, 0, 1, 1, 1);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, 28f, PlantationWorld.TerrainHeight(28f, PlantationWorld.CanalZ - 4.7f), PlantationWorld.CanalZ, 0, 0, 0, 1, 1, 1);
        DrawNamed(MeshCatalog.WoodenBridge, 0, _instStaging, c, ref drawCalls, ref tris);

        // 2.5. Physical Angkong Wheelbarrows + Independent Spinning Wheels!
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

        // 3. Multi-LOD Oil Palms + Swaying Crowns + Hanging Ripe/Gold TBS
        float windAmp = storm ? 2.1f : 0.85f;
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
                    t.X + (0.30f * cy + 0.24f * sy) * t.Scale,
                    t.Y + 6.18f * t.Scale,
                    t.Z + (-0.30f * sy + 0.24f * cy) * t.Scale,
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
                            t.X + MathF.Sin(ang) * 0.52f * t.Scale,
                            t.Y + 5.82f * t.Scale,
                            t.Z + MathF.Cos(ang) * 0.52f * t.Scale,
                            0, ang, 0, t.Scale, t.Scale, t.Scale,
                            isGold ? 2.35f : 1f, isGold ? 1.80f : 1f, isGold ? 0.45f : 1f, 0.35f);
                    }
                }
            }
            DrawNamed(MeshCatalog.PalmTrunk, tier, _treeLodStaging[0], nTrunk, ref drawCalls, ref tris);
            DrawNamed(MeshCatalog.PalmCrown, tier, _treeLodStaging[1], nCrown, ref drawCalls, ref tris);
            DrawNamed(MeshCatalog.TbsBunch, tier, _fruitStaging, nBunch, ref drawCalls, ref tris);
        }

        // 3.5. Physical Ground Bouncing TBS Bunches + Parabolic Thrown TBS Projectiles!
        int nDynFruit = 0;
        for (int i = 0; i < Physics.GroundFruits.Length; i++)
        {
            if (!Physics.GroundFruits[i].Active) continue;
            ref var gf = ref Physics.GroundFruits[i];
            float pulse = gf.Grounded ? (1.0f + MathF.Sin(now * 5.0f + i) * 0.05f) : 1.0f;
            nDynFruit = Mat4Utils.WriteInstanceTRS(
                _goldStaging, nDynFruit, gf.X, gf.Y, gf.Z, gf.RotX, gf.RotY, 0, pulse, pulse, pulse,
                gf.IsGold ? 2.35f : 1.08f, gf.IsGold ? 1.80f : 1.05f, gf.IsGold ? 0.45f : 1.0f, 0f);
        }
        for (int i = 0; i < Physics.ThrownArcs.Length; i++)
        {
            if (!Physics.ThrownArcs[i].Active) continue;
            ref var ar = ref Physics.ThrownArcs[i];
            nDynFruit = Mat4Utils.WriteInstanceTRS(
                _goldStaging, nDynFruit, ar.CurX, ar.CurY, ar.CurZ, ar.SpinRad, ar.SpinRad * 0.7f, 0, 0.95f, 0.95f, 0.95f,
                ar.IsGold ? 2.35f : 1.08f, ar.IsGold ? 1.80f : 1.05f, ar.IsGold ? 0.45f : 1.0f, 0f);
        }
        if (nDynFruit > 0) DrawNamed(MeshCatalog.TbsBunch, 0, _goldStaging, nDynFruit, ref drawCalls, ref tris);

        // 4. Undergrowth Ferns & Boulders
        if (q.DrawUndergrowthFerns)
        {
            c = 0;
            for (int i = 0; i < _ferns.Count; i++)
            {
                var f = _ferns[i];
                float dx = f.X - eyeX, dz = f.Z - eyeZ;
                if (dx * dx + dz * dz < q.Lod1Distance * q.Lod1Distance)
                    c = Mat4Utils.WriteInstanceTRS(_instStaging, c, f.X, f.Y, f.Z, 0, f.RotY, 0, f.Scale, f.Scale, f.Scale, 1, 1, 1, 0.6f);
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

        // 5. Wild Celeng Boars with 4 Articulated Galloping Legs!
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

        // 6. Render Both Physical Canter Trucks (Main Player Truck + Yard Canter Truck) with 4-Wheel Suspension & Steering!
        if (Stage == AppSceneStage.Lobby)
        {
            // Showroom Canter parked at heroic 3/4 angle right behind avatar with front wheels steered +22 deg!
            float tgy = RigidBodyWorld.SurfaceHeightWithStructures(9.85f, 3.85f);
            Physics.MainTruck.X = 9.85f;
            Physics.MainTruck.Z = 3.85f;
            Physics.MainTruck.Y = tgy;
            Physics.MainTruck.Yaw = -0.62f;
            Physics.MainTruck.SteerAngle = 0.36f;
            for (int w = 0; w < 4; w++) Physics.MainTruck.WheelWorldY[w] = tgy + 0.48f;
        }
        int shownCargo = System.Math.Max(_net.LocalCargo, Physics.MainTruck.VisualCargoUnits);
        DrawCanterVehicleRig(Physics.MainTruck, _net.Profile.Avatar, shownCargo, hasDriver: InTruck && Stage == AppSceneStage.Gameplay, ref drawCalls, ref tris);
        DrawCanterVehicleRig(Physics.YardTruck, new AvatarConfig { OutfitHex = "#E67E22" }, Physics.YardTruck.VisualCargoUnits, hasDriver: false, ref drawCalls, ref tris);

        // 7. Render Local Player's Full 11-Part Detailed Anatomy Rig!
        if (!InTruck || Stage != AppSceneStage.Gameplay)
        {
            float renderYaw = Stage == AppSceneStage.Lobby ? (LobbyAvatarSpinOffset + MathF.Sin(now * 0.7f) * 0.06f) : Physics.Player.Yaw;
            float px = Stage == AppSceneStage.Lobby ? 7.65f : PlayerX;
            float pz = Stage == AppSceneStage.Lobby ? 6.15f : PlayerZ;
            float py = Stage == AppSceneStage.Lobby ? RigidBodyWorld.SurfaceHeightWithStructures(px, pz) : PlayerY;

            DrawDetailedHumanRig(
                px, py, pz, renderYaw,
                walkPhase: Stage == AppSceneStage.Lobby ? 0f : Physics.Player.WalkCycleRad,
                breathPhase: Physics.Player.IdleBreathPhase,
                moving: Stage == AppSceneStage.Gameplay && Physics.Player.MoveSpeedMs > 0.2f,
                stance: Stage == AppSceneStage.Lobby ? HoldStance.TwoHandTool : Physics.Player.Stance,
                slashTimer: Physics.Player.SlashTimer,
                pickupTimer: Physics.Player.PickupTimer,
                throwTimer: Physics.Player.ThrowTimer,
                heldGold: Physics.Player.HeldGoldUnits > 0,
                av: _net.Profile.Avatar,
                ref drawCalls, ref tris);
        }

        // 8. Render Live Remote Multiplayer Peers (Full 11-Part Anatomy or Canter Rig!)
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
                    ref drawCalls, ref tris);
            }
        }

        LastDrawCalls = drawCalls;
        LastTriangles = tris;

        // Publish normalized screen projections for Gameplay Nameplates & Voice Waves
        lock (HudLock)
        {
            ProjectedLabels.Clear();
            MinimapPeers.Clear();

            if (Stage == AppSceneStage.Gameplay)
            {
                string myBubble = FindLatestBubble(_net.Profile.Id, now);
                if (Mat4Utils.ProjectWorldToScreen(_vp, PlayerX, PlayerY + (InTruck ? 2.85f : 2.18f), PlayerZ, 1f, 1f, out float sx, out float sy))
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
                    if (Mat4Utils.ProjectWorldToScreen(_vp, p.RenderX, p.RenderY + (p.InTruck ? 2.85f : 2.18f), p.RenderZ, 1f, 1f, out float px, out float py))
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
    /// Renders Mitsubishi Canter 'Oleng Sawit HD' with:
    ///   - Chassis Pitch + Roll ("Canter Oleng") + Heave
    ///   - 4 Independent Spring-Damper Suspension Wheels
    ///   - Front-Wheel Steering Turn Angle (ry = Yaw + SteerAngle) + Rolling Tire Spin (rx = WheelSpinRad)
    ///   - Seated Visible Driver inside Cab turning with SteerAngle!
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

        // 4 Independent Suspension + Steer + Rolling Wheels!
        float sy = MathF.Sin(v.Yaw), cy = MathF.Cos(v.Yaw);
        ReadOnlySpan<float> lx = [-0.88f, 0.88f, -0.88f, 0.88f];
        ReadOnlySpan<float> lz = [1.55f, 1.55f, -1.25f, -1.25f];
        int nw = 0;
        for (int w = 0; w < 4; w++)
        {
            float wx = v.X + lx[w] * cy + lz[w] * sy;
            float wz = v.Z - lx[w] * sy + lz[w] * cy;
            float wy = v.WheelWorldY[w] > 0.001f ? v.WheelWorldY[w] : (v.Y + 0.48f);
            float wheelYaw = w < 2 ? (v.Yaw + v.SteerAngle) : v.Yaw;
            var hub = Mat4Utils.BoneMat.TRS(wx, wy, wz, ry: wheelYaw).Child(0f, 0f, 0f, rx: v.WheelSpinRad);
            nw = hub.Emit(_instStaging, nw);
        }
        DrawNamed(MeshCatalog.TruckWheel, 0, _instStaging, nw, ref drawCalls, ref tris);

        if (cargoUnits > 0)
        {
            float fill = System.Math.Min(1.12f, 0.45f + cargoUnits * 0.032f);
            int nc = chassis.Child(0f, 0.82f, 0f, sx: 0.96f, sy: fill, sz: 0.96f).Emit(_instStaging, 0);
            DrawNamed(MeshCatalog.TruckCargoHeap, 0, _instStaging, nc, ref drawCalls, ref tris);
        }

        if (hasDriver)
        {
            // Seated detailed driver inside right-hand Indonesian cab turning with steering wheel!
            var drvTorso = chassis.Child(0.42f, 1.16f, 1.62f, sx: 0.86f, sy: 0.86f, sz: 0.86f);
            DrawNamed(MeshCatalog.CharTorsoHead, 0, _instStaging, drvTorso.Emit(_instStaging, 0, cr, cg, cb), ref drawCalls, ref tris);
            var drvHead = drvTorso.Child(0f, 0.56f, 0.01f, ry: v.SteerAngle * 0.55f);
            DrawNamed(MeshCatalog.CharHead, 0, _instStaging, drvHead.Emit(_instStaging, 0), ref drawCalls, ref tris);
            if (!string.IsNullOrEmpty(av.Hat) && av.Hat != "none")
                DrawNamed(av.Hat, 0, _instStaging, drvHead.Child(0f, 0.255f, 0.01f).Emit(_instStaging, 0), ref drawCalls, ref tris);

            int na = 0, nf = 0;
            var armL = drvTorso.Child(-0.24f, 0.46f, 0.02f, rx: -0.95f + v.SteerAngle * 0.45f, rz: -0.18f);
            var armR = drvTorso.Child(0.24f, 0.46f, 0.02f, rx: -0.95f - v.SteerAngle * 0.45f, rz: 0.18f);
            na = armL.Emit(_instStaging, na, cr, cg, cb);
            na = armR.Emit(_instStaging, na, cr, cg, cb);
            nf = armL.Child(0f, -0.27f, 0.01f, rx: -0.45f).Emit(_goldStaging, nf);
            nf = armR.Child(0f, -0.27f, 0.01f, rx: -0.45f).Emit(_goldStaging, nf);
            DrawNamed(MeshCatalog.CharArm, 0, _instStaging, na, ref drawCalls, ref tris);
            DrawNamed(MeshCatalog.CharForearmHand, 0, _goldStaging, nf, ref drawCalls, ref tris);
        }
    }

    /// <summary>
    /// Full 11-Part Hierarchical Human Anatomy &amp; Action Animator:
    ///   - Standing height = exact 1.76m, rubber boots flush on ground y = 0.00m
    ///   - Animations: Idle Breath &amp; Head Scan, Athletic Stride + Knee Flexion, Overhead Egrek Slash,
    ///     Knee-Squat Ground TBS Pickup ("Animasi Mengambil Sawit"), Two-Hand TBS Hold ("Animasi Pegang"),
    ///     Two-Hand Heave &amp; Throw ("Animasi Menaruh ke Truk / Angkong"), and Angkong Handle Push!
    /// </summary>
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
        ref int drawCalls,
        ref int tris)
    {
        var (cr, cg, cb) = av.GetOutfitRgb();
        float breath = MathF.Sin(breathPhase) * 0.014f;

        // 1. Compute Leg Kinematics (Hip -> Thigh -> Knee -> Calf + Rubber Boot)
        float stride = moving ? MathF.Sin(walkPhase) : 0f;
        float bob = moving ? MathF.Abs(MathF.Cos(walkPhase)) * 0.042f : breath * 0.5f;

        float squatK = pickupTimer > 0.001f ? MathF.Sin(System.Math.Clamp(pickupTimer / 0.40f, 0f, 1f) * MathF.PI) : 0f;
        float hipDrop = squatK * 0.34f;
        float torsoLeanX = squatK * 0.56f + (moving ? 0.08f : 0f);

        float thighL_rx = -stride * 0.62f - squatK * 0.92f;
        float thighR_rx = stride * 0.62f - squatK * 0.92f;
        float kneeL_rx = (moving ? MathF.Max(0f, MathF.Cos(walkPhase)) * 0.68f : 0.05f) + squatK * 1.48f;
        float kneeR_rx = (moving ? MathF.Max(0f, -MathF.Cos(walkPhase)) * 0.68f : 0.05f) + squatK * 1.48f;

        var hipRoot = Mat4Utils.BoneMat.TRS(x, y + 0.88f + bob - hipDrop, z, ry: yaw);
        var torsoMat = hipRoot.Child(0f, 0f, 0f, rx: torsoLeanX);
        var headMat = torsoMat.Child(
            0f, 0.56f + breath * 0.4f, 0.01f,
            rx: -torsoLeanX * 0.45f + MathF.Sin(breathPhase * 0.6f) * 0.03f,
            ry: moving ? 0f : MathF.Sin(breathPhase * 0.45f) * 0.09f);

        var thighL = hipRoot.Child(-0.115f, 0f, 0f, rx: thighL_rx);
        var calfL = thighL.Child(0f, -0.43f, 0f, rx: kneeL_rx);
        var thighR = hipRoot.Child(0.115f, 0f, 0f, rx: thighR_rx);
        var calfR = thighR.Child(0f, -0.43f, 0f, rx: kneeR_rx);

        // 2. Compute Arm & 5-Finger Hand Kinematics per Active Hold Stance & Action Timer!
        float uaL_rx, uaL_rz, faL_rx, faL_ry;
        float uaR_rx, uaR_rz, faR_rx, faR_ry;

        if (pickupTimer > 0.001f)
        {
            // Reaching both 5-finger hands down toward the fallen spiky TBS on the ground!
            uaL_rx = -0.35f - squatK * 0.98f; uaL_rz = -0.16f;
            faL_rx = -0.35f - squatK * 0.25f; faL_ry = 0.20f;
            uaR_rx = -0.35f - squatK * 0.98f; uaR_rz = 0.16f;
            faR_rx = -0.35f - squatK * 0.25f; faR_ry = -0.20f;
        }
        else if (throwTimer > 0.001f)
        {
            // Powerful two-handed chest-to-overhead heave into Truck Bed / Angkong!
            float tk = 1f - System.Math.Clamp(throwTimer / 0.48f, 0f, 1f);
            float heave = MathF.Sin(tk * MathF.PI);
            uaL_rx = -0.82f - heave * 1.15f; uaL_rz = -0.18f;
            faL_rx = -0.68f + heave * 0.48f; faL_ry = 0.20f;
            uaR_rx = -0.82f - heave * 1.15f; uaR_rz = 0.18f;
            faR_rx = -0.68f + heave * 0.48f; faR_ry = -0.20f;
        }
        else if (slashTimer > 0.001f)
        {
            // High-energy two-handed Egrek pull-slash!
            float sk = 1f - System.Math.Clamp(slashTimer / 0.46f, 0f, 1f);
            float swing = MathF.Sin(sk * MathF.PI);
            uaL_rx = -0.88f - swing * 1.15f; uaL_rz = -0.30f;
            faL_rx = -0.45f + swing * 0.25f; faL_ry = 0.28f;
            uaR_rx = -0.70f - swing * 1.25f; uaR_rz = 0.22f;
            faR_rx = -0.55f + swing * 0.25f; faR_ry = -0.18f;
        }
        else if (stance == HoldStance.CarryingTbs)
        {
            // Two-handed TBS cradling hold right in front of chest!
            float carryBob = moving ? MathF.Sin(walkPhase * 2f) * 0.05f : breath;
            uaL_rx = -0.78f + carryBob; uaL_rz = -0.22f;
            faL_rx = -0.72f;            faL_ry = 0.26f;
            uaR_rx = -0.78f + carryBob; uaR_rz = 0.22f;
            faR_rx = -0.72f;            faR_ry = -0.26f;
        }
        else if (stance == HoldStance.PushingAngkong)
        {
            // Both hands extended forward gripping the two red rubber Angkong handles!
            uaL_rx = -0.72f; uaL_rz = 0.06f;
            faL_rx = -0.42f; faL_ry = 0.04f;
            uaR_rx = -0.72f; uaR_rz = -0.06f;
            faR_rx = -0.42f; faR_ry = -0.04f;
        }
        else
        {
            // Ready Two-Handed Egrek / Dodos Hold Pose (never empty stiff arms!)
            float sw = moving ? stride * 0.16f : breath;
            uaL_rx = -0.88f + sw; uaL_rz = -0.32f;
            faL_rx = -0.40f;      faL_ry = 0.28f;
            uaR_rx = -0.64f - sw; uaR_rz = 0.24f;
            faR_rx = -0.52f;      faR_ry = -0.18f;
        }

        var upperArmL = torsoMat.Child(-0.245f, 0.485f, 0.01f, rx: uaL_rx, rz: uaL_rz);
        var forearmL = upperArmL.Child(0f, -0.27f, 0.01f, rx: faL_rx, ry: faL_ry);
        var upperArmR = torsoMat.Child(0.245f, 0.485f, 0.01f, rx: uaR_rx, rz: uaR_rz);
        var forearmR = upperArmR.Child(0f, -0.27f, 0.01f, rx: faR_rx, ry: faR_ry);

        // 3. Emit Batched GPU Draw Calls for All 11 Anatomical Segments + Cosmetics + Held Item!
        DrawNamed(MeshCatalog.CharTorsoHead, 0, _instStaging, torsoMat.Emit(_instStaging, 0, cr, cg, cb), ref drawCalls, ref tris);
        DrawNamed(MeshCatalog.CharHead, 0, _instStaging, headMat.Emit(_instStaging, 0), ref drawCalls, ref tris);

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

        if (!string.IsNullOrEmpty(av.Hat) && av.Hat != "none")
        {
            DrawNamed(av.Hat, 0, _instStaging, headMat.Child(0f, 0.255f, 0.01f).Emit(_instStaging, 0), ref drawCalls, ref tris);
        }

        if (!string.IsNullOrEmpty(av.Back) && av.Back != "none")
        {
            float windBack = av.Back == MeshCatalog.BackCape ? 0.65f : 0.20f;
            DrawNamed(av.Back, 0, _instStaging, torsoMat.Child(0f, 0.36f, -0.14f).Emit(_instStaging, 0, 1f, 1f, 1f, windBack), ref drawCalls, ref tris);
        }

        string toolMesh = string.IsNullOrEmpty(av.Tool) ? MeshCatalog.ToolEgrek : av.Tool;
        if (stance == HoldStance.CarryingTbs)
        {
            // Render held spiky TBS bunch directly between both 5-finger hands + sling Egrek diagonally on back!
            var heldFruit = torsoMat.Child(0f, 0.33f, 0.44f, rx: 0.35f, sx: 0.84f, sy: 0.84f, sz: 0.84f);
            DrawNamed(MeshCatalog.TbsBunch, 0, _instStaging,
                heldFruit.Emit(_instStaging, 0, heldGold ? 2.35f : 1.06f, heldGold ? 1.80f : 1.05f, heldGold ? 0.45f : 1f),
                ref drawCalls, ref tris);
            DrawNamed(toolMesh, 0, _instStaging, torsoMat.Child(-0.08f, 0.15f, -0.22f, rx: -0.18f, rz: -0.42f, sx: 0.72f, sy: 0.72f, sz: 0.72f).Emit(_instStaging, 0), ref drawCalls, ref tris);
        }
        else if (stance == HoldStance.PushingAngkong)
        {
            // Sling Egrek neatly across back while gripping Angkong handles!
            DrawNamed(toolMesh, 0, _instStaging, torsoMat.Child(-0.08f, 0.15f, -0.22f, rx: -0.18f, rz: -0.42f, sx: 0.72f, sy: 0.72f, sz: 0.72f).Emit(_instStaging, 0), ref drawCalls, ref tris);
        }
        else
        {
            // Held Egrek / Dodos in both hands with dynamic overhead slash pivot!
            float slashPitch = slashTimer > 0.001f
                ? -0.55f + MathF.Sin((1f - slashTimer / 0.46f) * MathF.PI) * 1.35f
                : 0.14f;
            var toolMat = torsoMat.Child(0.04f, 0.24f, 0.38f, rx: slashPitch, rz: 0.10f);
            DrawNamed(toolMesh, 0, _instStaging, toolMat.Emit(_instStaging, 0), ref drawCalls, ref tris);
        }
    }

    private void DrawNamed(string meshName, int lod, float[] instBuf, int count, ref int drawCalls, ref int tris)
    {
        if (count <= 0 || !_gpuMeshes.TryGetValue(meshName, out var lods)) return;
        int idx = System.Math.Min(lod, lods.Length - 1);
        DrawGpuHandle(lods[idx], instBuf, count, ref drawCalls, ref tris);
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
