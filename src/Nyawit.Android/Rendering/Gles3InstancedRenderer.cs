using System;
using System.Collections.Generic;
using System.Diagnostics;
using Android.Content;
using Android.Opengl;
using Java.Nio;
using Javax.Microedition.Khronos.Opengles;
using NyawitEngine.Assets;
using NyawitEngine.Core;
using NyawitEngine.Math;
using NyawitEngine.Network;
using NyawitEngine.World;
using EGLConfig = Javax.Microedition.Khronos.Egl.EGLConfig;

namespace Nyawit.AndroidClient.Rendering;

public struct ProjectedLabel
{
    public float ScreenX, ScreenY;
    public string Name;
    public string SubTitle;
    public string BubbleText;
    public bool IsSelf;
}

public sealed class Gles3InstancedRenderer : Java.Lang.Object, GLSurfaceView.IRenderer
{
    private const string VertexShaderSrc = @"#version 300 es
precision highp float;
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNorm;
layout(location = 2) in vec2 aUV;
layout(location = 3) in vec4 aColor;
layout(location = 4) in vec4 iRow0;
layout(location = 5) in vec4 iRow1;
layout(location = 6) in vec4 iRow2;
layout(location = 7) in vec4 iColor;

uniform mat4 uVP;
uniform float uTime;

out vec3 vNormal;
out vec3 vWorldPos;
out vec4 vColor;
out vec3 vTint;
out vec2 vUV;

void main() {
  mat4 M = mat4(
    vec4(iRow0.x, iRow1.x, iRow2.x, 0.0),
    vec4(iRow0.y, iRow1.y, iRow2.y, 0.0),
    vec4(iRow0.z, iRow1.z, iRow2.z, 0.0),
    vec4(iRow0.w, iRow1.w, iRow2.w, 1.0)
  );
  vec3 lp = aPos;
  if (iColor.a > 0.001) {
    float hFactor = max(0.0, lp.y - 1.2) * 0.055 * iColor.a;
    lp.x += sin(uTime * 1.9 + iRow0.w * 0.21 + iRow2.w * 0.17) * hFactor;
    lp.z += cos(uTime * 1.5 + iRow2.w * 0.25) * hFactor * 0.8;
  }
  vec4 wp = M * vec4(lp, 1.0);
  vWorldPos = wp.xyz;
  vNormal = normalize(mat3(M) * aNorm);
  vColor = aColor;
  vTint = iColor.rgb;
  vUV = aUV;
  gl_Position = uVP * wp;
}";

    private const string FragmentShaderSrc = @"#version 300 es
precision mediump float;
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

out vec4 outColor;

void main() {
  vec3 N = normalize(vNormal);
  vec3 V = normalize(uCamPos - vWorldPos);
  float ndl = max(dot(N, uSunDir), 0.0);
  vec3 hemi = mix(uGroundBounce, uSkyTop, N.y * 0.5 + 0.5);
  vec3 H = normalize(uSunDir + V);
  float spec = pow(max(dot(N, H), 0.0), 28.0) * 0.20 * vColor.a;
  vec3 effTint = mix(vec3(1.0), vTint, step(0.75, vUV.x));
  vec3 base = vColor.rgb * effTint;
  vec3 lit = base * (hemi * 0.72 + uSunColor * ndl * 0.92) + uSunColor * spec;

  float dist = length(uCamPos - vWorldPos);
  float fogF = 1.0 - exp(-pow(dist * uFogDensity, 2.0));
  vec3 col = mix(lit, uFogColor, clamp(fogF, 0.0, 0.92));
  col = col / (col + vec3(0.85)) * 1.38;
  outColor = vec4(col, 1.0);
}";

    private sealed class GpuMeshHandle
    {
        public int Vao;
        public int IndexCount;
    }

    private readonly Context _context;
    private readonly NpakArchive _archive;
    private readonly List<PalmTreeNode> _trees;
    private readonly List<StaticPropInstance> _ferns;
    private readonly List<StaticPropInstance> _rocks;
    private readonly LiveMultiplayerSession _net;
    public QualityGovernor Quality { get; } = new();

    private readonly Dictionary<string, GpuMeshHandle[]> _gpuMeshes = new(StringComparer.Ordinal);
    private GpuMeshHandle? _terrainGpu;
    private GpuMeshHandle? _waterGpu;
    private int _program;
    private int _instanceVbo;
    private int _uVp, _uTime, _uSunDir, _uSunColor, _uSkyTop, _uGroundBounce, _uFogColor, _uCamPos, _uFogDensity;

    private const int MaxInstancesPerBatch = 1024;
    private readonly float[] _instStaging = new float[MaxInstancesPerBatch * 16];
    private readonly float[][] _treeLodStaging = [new float[256 * 16], new float[256 * 16], new float[256 * 16]];
    private readonly float[] _fruitStaging = new float[256 * 16];
    private readonly float[] _goldStaging = new float[128 * 16];
    private readonly float[] _treePositionsXyz;
    private readonly sbyte[] _treeLodResult;
    private FloatBuffer? _directFloatBuffer;

    private readonly FallingTbs[] _fallingPool = new FallingTbs[40];
    private int _fallingCursor;

    // Player & Camera simulation state (staggered plaza spawn so concurrent players never overlap)
    public float PlayerX = (Random.Shared.NextSingle() - 0.5f) * 9.0f;
    public float PlayerY = 0f;
    public float PlayerZ = 3.0f + Random.Shared.NextSingle() * 4.5f;
    public float PlayerYaw = MathF.PI, PlayerSpeed = 0f;
    public bool InTruck;
    public float WalkPhase, ChopAnim, BoostTimer;
    public float JoyX, JoyY;
    public float CamYaw = 0.35f, CamPitch = 0.36f, CamDist = 8.8f;
    public int NearestRipeTreeId = -1;
    public bool NearRamWeighbridge;
    public int LastDrawCalls { get; private set; }
    public int LastTriangles { get; private set; }

    private int _surfaceWidth = 1280, _surfaceHeight = 720;
    private readonly Stopwatch _clock = Stopwatch.StartNew();
    private double _lastTimeSec;
    private double _nextNetSyncSec;

    private readonly float[] _proj = new float[16];
    private readonly float[] _view = new float[16];
    private readonly float[] _vp = new float[16];

    private readonly List<RemotePeerState> _peersSnap = new(24);
    private readonly List<BoarNetState> _boarsSnap = new(4);
    private readonly List<ChatMessageEntry> _chatSnap = new(40);
    public readonly object HudLock = new();
    public readonly List<ProjectedLabel> ProjectedLabels = new(24);
    public readonly List<(float X, float Z, bool InTruck)> MinimapPeers = new(24);

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

        _treePositionsXyz = new float[_trees.Count * 3];
        _treeLodResult = new sbyte[_trees.Count];
        for (int i = 0; i < _trees.Count; i++)
        {
            _treePositionsXyz[i * 3 + 0] = _trees[i].X;
            _treePositionsXyz[i * 3 + 1] = _trees[i].Y;
            _treePositionsXyz[i * 3 + 2] = _trees[i].Z;
        }

        _net.OnHarvestSpawnFruit += SpawnFallingFruits;
    }

    public List<PalmTreeNode> Trees => _trees;

    public void SpawnFallingFruits(float tx, float tz, bool isGold)
    {
        float gy = PlantationWorld.TerrainHeight(tx, tz);
        int count = isGold ? 3 : 2;
        for (int i = 0; i < count; i++)
        {
            float ang = i * 2.1f + (float)_lastTimeSec;
            _fallingPool[_fallingCursor % _fallingPool.Length] = new FallingTbs
            {
                Active = true,
                X = tx + MathF.Cos(ang) * 0.85f,
                Y = gy + 4.9f,
                Z = tz + MathF.Sin(ang) * 0.85f,
                Vx = MathF.Cos(ang) * 1.45f,
                Vy = 1.6f,
                Vz = MathF.Sin(ang) * 1.45f,
                GroundY = gy + 0.34f,
                Life = 3.2f,
                IsGold = isGold
            };
            _fallingCursor++;
        }
    }

    public void OnSurfaceCreated(IGL10? gl, EGLConfig? config)
    {
        _directFloatBuffer = ByteBuffer
            .AllocateDirect(MaxInstancesPerBatch * 16 * sizeof(float))
            .Order(ByteOrder.NativeOrder()!)
            .AsFloatBuffer()!;

        int vs = CompileShader(GLES30.GlVertexShader, VertexShaderSrc);
        int fs = CompileShader(GLES30.GlFragmentShader, FragmentShaderSrc);
        _program = GLES30.GlCreateProgram();
        GLES30.GlAttachShader(_program, vs);
        GLES30.GlAttachShader(_program, fs);
        GLES30.GlLinkProgram(_program);

        _uVp = GLES30.GlGetUniformLocation(_program, "uVP");
        _uTime = GLES30.GlGetUniformLocation(_program, "uTime");
        _uSunDir = GLES30.GlGetUniformLocation(_program, "uSunDir");
        _uSunColor = GLES30.GlGetUniformLocation(_program, "uSunColor");
        _uSkyTop = GLES30.GlGetUniformLocation(_program, "uSkyTop");
        _uGroundBounce = GLES30.GlGetUniformLocation(_program, "uGroundBounce");
        _uFogColor = GLES30.GlGetUniformLocation(_program, "uFogColor");
        _uCamPos = GLES30.GlGetUniformLocation(_program, "uCamPos");
        _uFogDensity = GLES30.GlGetUniformLocation(_program, "uFogDensity");

        int[] bufs = new int[1];
        GLES30.GlGenBuffers(1, bufs, 0);
        _instanceVbo = bufs[0];
        GLES30.GlBindBuffer(GLES30.GlArrayBuffer, _instanceVbo);
        GLES30.GlBufferData(GLES30.GlArrayBuffer, MaxInstancesPerBatch * 64, null, GLES30.GlStreamDraw);

        _gpuMeshes.Clear();
        foreach (var kv in _archive.Meshes)
        {
            var lodHandles = new GpuMeshHandle[kv.Value.Lods.Length];
            for (int l = 0; l < kv.Value.Lods.Length; l++)
                lodHandles[l] = UploadMeshToGpu(kv.Value.Lods[l]);
            _gpuMeshes[kv.Key] = lodHandles;
        }
        _terrainGpu = UploadMeshToGpu(PlantationWorld.BuildSplattedTerrainMesh(128, 224f));
        _waterGpu = UploadMeshToGpu(PlantationWorld.BuildCanalWaterMesh());

        GLES30.GlEnable(GLES30.GlDepthTest);
        GLES30.GlEnable(0x0B44); // GL_CULL_FACE
        GLES30.GlCullFace(0x0405); // GL_BACK
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
        double now = _clock.Elapsed.TotalSeconds;
        float dt = (float)System.Math.Clamp(now - _lastTimeSec, 0.001, 0.05);
        _lastTimeSec = now;
        Time.TotalTime = (float)now;
        Time.DeltaTime = dt;
        Quality.RecordFrame(dt);

        StepGameplayPhysics(dt, now);
        Render3DWorld((float)now, dt);
    }

    private void StepGameplayPhysics(float dt, double now)
    {
        float mud = PlantationWorld.MudFactor(PlayerX, PlayerZ);
        float road = PlantationWorld.RoadFactor(PlayerX, PlayerZ);
        float boostMul = BoostTimer > 0f ? 1.55f : 1.0f;
        if (BoostTimer > 0f) BoostTimer -= dt;

        float baseSpeed = InTruck ? (14.6f + road * 4.4f - mud * 4.6f) : (7.5f - mud * 1.6f);
        float maxSpeed = baseSpeed * boostMul;

        float jMag = MathF.Sqrt(JoyX * JoyX + JoyY * JoyY);
        if (jMag > 0.05f)
        {
            float nx = JoyX / System.Math.Max(1f, jMag);
            float ny = JoyY / System.Math.Max(1f, jMag);
            float fwdX = -MathF.Sin(CamYaw), fwdZ = -MathF.Cos(CamYaw);
            float rgtX = MathF.Cos(CamYaw), rgtZ = -MathF.Sin(CamYaw);
            float wx = rgtX * nx + fwdX * (-ny);
            float wz = rgtZ * nx + fwdZ * (-ny);
            float targetYaw = MathF.Atan2(wx, wz);
            float diff = targetYaw - PlayerYaw;
            while (diff > MathF.PI) diff -= MathF.PI * 2f;
            while (diff < -MathF.PI) diff += MathF.PI * 2f;
            PlayerYaw += diff * System.Math.Min(1f, dt * (InTruck ? 5.6f : 12.0f));
            PlayerSpeed = System.Math.Min(maxSpeed, PlayerSpeed + dt * 26f) * System.Math.Min(1f, jMag);
            WalkPhase += dt * (InTruck ? 14f : 10.5f);
        }
        else
        {
            PlayerSpeed = System.Math.Max(0f, PlayerSpeed - dt * 24f);
        }

        if (PlayerSpeed > 0.02f)
        {
            float nx = System.Math.Clamp(PlayerX + MathF.Sin(PlayerYaw) * PlayerSpeed * dt, -96f, 96f);
            float nz = System.Math.Clamp(PlayerZ + MathF.Cos(PlayerYaw) * PlayerSpeed * dt, -96f, 96f);
            bool onBridge = MathF.Abs(nx + 28f) < 2.2f || MathF.Abs(nx - 28f) < 2.2f;
            if (MathF.Abs(nz - PlantationWorld.CanalZ) < 3.6f && !onBridge)
            {
                nz = PlayerZ < PlantationWorld.CanalZ ? PlantationWorld.CanalZ - 3.65f : PlantationWorld.CanalZ + 3.65f;
            }
            PlayerX = nx;
            PlayerZ = nz;
        }
        PlayerY = PlantationWorld.SurfaceHeight(PlayerX, PlayerZ);
        if (ChopAnim > 0f) ChopAnim = System.Math.Max(0f, ChopAnim - dt * 2.8f);

        // Find nearest ripe palm & RAM weighbridge
        float bestD2 = 38.5f;
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

        float rdx = PlayerX - PlantationWorld.RamX, rdz = PlayerZ - PlantationWorld.RamZ;
        NearRamWeighbridge = _net.LocalCargo > 0 && MathF.Sqrt(rdx * rdx + rdz * rdz) < 11.5f;

        // Falling TBS fruit bounce physics
        for (int i = 0; i < _fallingPool.Length; i++)
        {
            if (!_fallingPool[i].Active) continue;
            ref var f = ref _fallingPool[i];
            f.Vy -= 15.5f * dt;
            f.X += f.Vx * dt;
            f.Y += f.Vy * dt;
            f.Z += f.Vz * dt;
            f.Rot += 5.5f * dt;
            if (f.Y < f.GroundY)
            {
                f.Y = f.GroundY;
                f.Vy = MathF.Abs(f.Vy) * 0.34f;
                f.Vx *= 0.6f;
                f.Vz *= 0.6f;
            }
            f.Life -= dt;
            if (f.Life <= 0f) f.Active = false;
        }

        if (now >= _nextNetSyncSec)
        {
            _nextNetSyncSec = now + 0.085;
            int anim = ChopAnim > 0.1f ? 2 : (PlayerSpeed > 0.4f ? 1 : 0);
            _net.SendPlayerState(PlayerX, PlayerY, PlayerZ, PlayerYaw, anim, InTruck);
        }
    }

    private void Render3DWorld(float now, float dt)
    {
        var q = Quality.Active;
        GLES30.GlViewport(0, 0, _surfaceWidth, _surfaceHeight);

        bool storm = _net.EventKind == "HUJAN_BADAI";
        bool goldRush = _net.EventKind == "DEMAM_SAWIT_EMAS";

        if (storm) GLES30.GlClearColor(0.18f, 0.24f, 0.31f, 1.0f);
        else if (goldRush) GLES30.GlClearColor(0.55f, 0.42f, 0.24f, 1.0f);
        else GLES30.GlClearColor(0.42f, 0.68f, 0.90f, 1.0f);

        GLES30.GlClear(GLES30.GlColorBufferBit | GLES30.GlDepthBufferBit);
        GLES30.GlUseProgram(_program);

        float dist = InTruck ? CamDist * 1.28f : CamDist;
        float eyeX = PlayerX + MathF.Sin(CamYaw) * MathF.Cos(CamPitch) * dist;
        float eyeZ = PlayerZ + MathF.Cos(CamYaw) * MathF.Cos(CamPitch) * dist;
        float eyeY = System.Math.Max(PlantationWorld.TerrainHeight(eyeX, eyeZ) + 1.2f, PlayerY + 1.9f + MathF.Sin(CamPitch) * dist);
        float lookY = PlayerY + (InTruck ? 1.85f : 1.55f);

        Mat4Utils.CreatePerspective(_proj, 58f * MathF.PI / 180f, _surfaceWidth / (float)_surfaceHeight, 0.35f, 250f);
        Mat4Utils.CreateLookAt(_view, eyeX, eyeY, eyeZ, PlayerX, lookY, PlayerZ);
        Mat4Utils.Multiply(_vp, _proj, _view);

        GLES30.GlUniformMatrix4fv(_uVp, 1, false, _vp, 0);
        GLES30.GlUniform1f(_uTime, now);
        GLES30.GlUniform3f(_uSunDir, 0.48f, 0.78f, 0.39f);
        GLES30.GlUniform3f(_uCamPos, eyeX, eyeY, eyeZ);

        if (storm)
        {
            GLES30.GlUniform3f(_uSunColor, 0.58f, 0.64f, 0.78f);
            GLES30.GlUniform3f(_uSkyTop, 0.26f, 0.34f, 0.46f);
            GLES30.GlUniform3f(_uGroundBounce, 0.14f, 0.17f, 0.13f);
            GLES30.GlUniform3f(_uFogColor, 0.20f, 0.26f, 0.33f);
            GLES30.GlUniform1f(_uFogDensity, 0.0105f);
        }
        else if (goldRush)
        {
            GLES30.GlUniform3f(_uSunColor, 1.32f, 1.02f, 0.62f);
            GLES30.GlUniform3f(_uSkyTop, 0.72f, 0.56f, 0.36f);
            GLES30.GlUniform3f(_uGroundBounce, 0.30f, 0.24f, 0.14f);
            GLES30.GlUniform3f(_uFogColor, 0.62f, 0.48f, 0.28f);
            GLES30.GlUniform1f(_uFogDensity, 0.0068f);
        }
        else
        {
            GLES30.GlUniform3f(_uSunColor, 1.24f, 1.16f, 0.98f);
            GLES30.GlUniform3f(_uSkyTop, 0.46f, 0.72f, 0.96f);
            GLES30.GlUniform3f(_uGroundBounce, 0.26f, 0.30f, 0.18f);
            GLES30.GlUniform3f(_uFogColor, 0.52f, 0.75f, 0.92f);
            GLES30.GlUniform1f(_uFogDensity, 0.0062f);
        }

        int drawCalls = 0, tris = 0;

        // 1. Terrain & Canal Water (2 draw calls)
        int c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1);
        DrawGpuHandle(_terrainGpu, _instStaging, c, ref drawCalls, ref tris);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, 0, MathF.Sin(now * 1.4f) * 0.04f, 0, 0, 0, 0, 1, 1, 1);
        DrawGpuHandle(_waterGpu, _instStaging, c, ref drawCalls, ref tris);

        // 2. PKS Mill, RAM Weighbridge, Bridges, Mandor Hut, Parked Wheelbarrows
        c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, PlantationWorld.PksX, PlantationWorld.TerrainHeight(PlantationWorld.PksX, PlantationWorld.PksZ), PlantationWorld.PksZ, 0, 0, 0, 1, 1, 1);
        DrawNamed(MeshCatalog.PksFactory, 0, _instStaging, c, ref drawCalls, ref tris);

        c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, PlantationWorld.RamX, PlantationWorld.TerrainHeight(PlantationWorld.RamX, PlantationWorld.RamZ), PlantationWorld.RamZ, 0, 0, 0, 1, 1, 1);
        DrawNamed(MeshCatalog.WeighbridgeRam, 0, _instStaging, c, ref drawCalls, ref tris);

        c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, PlantationWorld.MandorX, PlantationWorld.TerrainHeight(PlantationWorld.MandorX, PlantationWorld.MandorZ), PlantationWorld.MandorZ, 0, 0.5f, 0, 1, 1, 1);
        DrawNamed(MeshCatalog.MandorPost, 0, _instStaging, c, ref drawCalls, ref tris);

        c = 0;
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, -28f, PlantationWorld.TerrainHeight(-28f, PlantationWorld.CanalZ - 4.7f), PlantationWorld.CanalZ, 0, 0, 0, 1, 1, 1);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, 28f, PlantationWorld.TerrainHeight(28f, PlantationWorld.CanalZ - 4.7f), PlantationWorld.CanalZ, 0, 0, 0, 1, 1, 1);
        DrawNamed(MeshCatalog.WoodenBridge, 0, _instStaging, c, ref drawCalls, ref tris);

        c = 0;
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, -6.5f, PlantationWorld.TerrainHeight(-6.5f, -13f), -13f, 0, 0.8f, 0, 1, 1, 1);
        c = Mat4Utils.WriteInstanceTRS(_instStaging, c, 7.2f, PlantationWorld.TerrainHeight(7.2f, -12.5f), -12.5f, 0, -1.1f, 0, 1, 1, 1);
        DrawNamed(MeshCatalog.AngkongCart, 0, _instStaging, c, ref drawCalls, ref tris);

        // 3. Native SIMD / Multi-LOD Frustum Culling & Batching for 180 Oil Palms + Hanging Ripe/Gold TBS!
        float fx = PlayerX - eyeX, fy = lookY - eyeY, fz = PlayerZ - eyeZ;
        float fl = MathF.Sqrt(fx * fx + fy * fy + fz * fz);
        SimdCuller.SelectLodBatch(_treePositionsXyz, _trees.Count, eyeX, eyeY, eyeZ, fx / fl, fy / fl, fz / fl, q.Lod0Distance, q.Lod1Distance, q.MaxDrawDistance, _treeLodResult);

        float windAmp = storm ? 2.1f : 0.85f;
        for (int tier = 0; tier < 3; tier++)
        {
            int nTrunk = 0, nCrown = 0, nBunch = 0;
            for (int i = 0; i < _trees.Count; i++)
            {
                if (_treeLodResult[i] != tier) continue;
                var t = _trees[i];
                float highlight = i == NearestRipeTreeId ? 1.18f : 1.0f;
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
                    int perTree = tier == 0 ? 4 : 2;
                    for (int b = 0; b < perTree; b++)
                    {
                        float ang = t.RotationY + b * 1.57f;
                        nBunch = Mat4Utils.WriteInstanceTRS(
                            _fruitStaging, nBunch,
                            t.X + MathF.Sin(ang) * 0.52f * t.Scale,
                            t.Y + 5.82f * t.Scale,
                            t.Z + MathF.Cos(ang) * 0.52f * t.Scale,
                            0, ang, 0, t.Scale, t.Scale, t.Scale,
                            isGold ? 2.25f : 1f, isGold ? 1.75f : 1f, isGold ? 0.50f : 1f, 0.35f);
                    }
                }
            }
            DrawNamed(MeshCatalog.PalmTrunk, tier, _treeLodStaging[0], nTrunk, ref drawCalls, ref tris);
            DrawNamed(MeshCatalog.PalmCrown, tier, _treeLodStaging[1], nCrown, ref drawCalls, ref tris);
            DrawNamed(MeshCatalog.TbsBunch, tier, _fruitStaging, nBunch, ref drawCalls, ref tris);
        }

        // Falling fruits physics instances
        int nFall = 0;
        for (int i = 0; i < _fallingPool.Length; i++)
        {
            if (!_fallingPool[i].Active) continue;
            ref var f = ref _fallingPool[i];
            nFall = Mat4Utils.WriteInstanceTRS(
                _goldStaging, nFall, f.X, f.Y, f.Z, f.Rot, f.Rot * 0.7f, 0, 1.0f, 1.0f, 1.0f,
                f.IsGold ? 2.25f : 1f, f.IsGold ? 1.75f : 1f, f.IsGold ? 0.50f : 1f, 0f);
        }
        DrawNamed(MeshCatalog.TbsBunch, 0, _goldStaging, nFall, ref drawCalls, ref tris);

        // 4. Undergrowth Ferns (disabled on SMOOTH preset!) & Rocks
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

        // 5. Local Player + Live Remote Players + Celeng Boars
        _net.CopyRenderState(_peersSnap, _boarsSnap, _chatSnap, dt);

        c = 0;
        for (int i = 0; i < _boarsSnap.Count; i++)
        {
            var b = _boarsSnap[i];
            c = Mat4Utils.WriteInstanceTRS(_instStaging, c, b.X, PlantationWorld.TerrainHeight(b.X, b.Z) + MathF.Abs(MathF.Sin(now * 9f + i)) * 0.08f, b.Z, 0, b.Yaw, 0, 1.05f, 1.05f, 1.05f);
        }
        DrawNamed(MeshCatalog.CelengBoar, 0, _instStaging, c, ref drawCalls, ref tris);

        DrawCharacterOrTruck(PlayerX, PlayerY, PlayerZ, PlayerYaw, InTruck, _net.LocalCargo, WalkPhase, ChopAnim, PlayerSpeed > 0.3f, _net.Profile.Avatar, ref drawCalls, ref tris);
        for (int i = 0; i < _peersSnap.Count; i++)
        {
            var p = _peersSnap[i];
            DrawCharacterOrTruck(p.RenderX, p.RenderY, p.RenderZ, p.RenderYaw, p.InTruck, p.Cargo, p.WalkPhase, p.AnimState == 2 ? 0.8f : 0f, p.AnimState == 1, p.Avatar, ref drawCalls, ref tris);
        }

        LastDrawCalls = drawCalls;
        LastTriangles = tris;

        // Publish 2D screen projections for Nameplates, Floating Chat Bubbles & Minimap!
        lock (HudLock)
        {
            ProjectedLabels.Clear();
            MinimapPeers.Clear();

            string myBubble = FindLatestBubble(_net.Profile.Id, now);
            if (Mat4Utils.ProjectWorldToScreen(_vp, PlayerX, PlayerY + (InTruck ? 2.85f : 2.35f), PlayerZ, _surfaceWidth, _surfaceHeight, out float sx, out float sy))
            {
                ProjectedLabels.Add(new ProjectedLabel { ScreenX = sx, ScreenY = sy, Name = _net.Profile.Name, SubTitle = _net.Profile.Avatar.Title, BubbleText = myBubble, IsSelf = true });
            }

            for (int i = 0; i < _peersSnap.Count; i++)
            {
                var p = _peersSnap[i];
                MinimapPeers.Add((p.RenderX, p.RenderZ, p.InTruck));
                if (Mat4Utils.ProjectWorldToScreen(_vp, p.RenderX, p.RenderY + (p.InTruck ? 2.85f : 2.35f), p.RenderZ, _surfaceWidth, _surfaceHeight, out float px, out float py))
                {
                    ProjectedLabels.Add(new ProjectedLabel
                    {
                        ScreenX = px,
                        ScreenY = py,
                        Name = p.Name,
                        SubTitle = p.Avatar.Title,
                        BubbleText = FindLatestBubble(p.Id, now),
                        IsSelf = false
                    });
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

    private void DrawCharacterOrTruck(
        float x, float y, float z, float yaw,
        bool inTruck, int cargo, float walkPhase, float chopAnim, bool moving,
        AvatarConfig av,
        ref int drawCalls, ref int tris)
    {
        var (cr, cg, cb) = av.GetOutfitRgb();
        float cosY = MathF.Cos(yaw), sinY = MathF.Sin(yaw);

        if (inTruck)
        {
            int c = Mat4Utils.WriteInstanceTRS(_instStaging, 0, x, y, z, 0, yaw, 0, 1, 1, 1, cr, cg, cb);
            DrawNamed(MeshCatalog.CanterTruckBody, 0, _instStaging, c, ref drawCalls, ref tris);

            c = 0;
            (float wx, float wz)[] wheels = [(-0.90f, 1.62f), (0.90f, 1.62f), (-0.90f, -1.18f), (0.90f, -1.18f)];
            foreach (var (ox, oz) in wheels)
            {
                float worldX = x + cosY * ox + sinY * oz;
                float worldZ = z - sinY * ox + cosY * oz;
                c = Mat4Utils.WriteInstanceTRS(_instStaging, c, worldX, y + 0.50f, worldZ, walkPhase, yaw, 0, 1, 1, 1);
            }
            DrawNamed(MeshCatalog.TruckWheel, 0, _instStaging, c, ref drawCalls, ref tris);

            if (cargo > 0)
            {
                float heapScale = 0.55f + System.Math.Min(1f, cargo / 20f) * 0.50f;
                int ch = Mat4Utils.WriteInstanceTRS(_instStaging, 0, x, y + 0.84f, z, 0, yaw, 0, heapScale, heapScale, heapScale);
                DrawNamed(MeshCatalog.TruckCargoHeap, 0, _instStaging, ch, ref drawCalls, ref tris);
            }

            int drv = Mat4Utils.WriteInstanceTRS(_instStaging, 0, x - 0.35f * cosY + 1.55f * sinY, y + 0.92f, z + 0.35f * sinY + 1.55f * cosY, 0, yaw, 0, 0.88f, 0.88f, 0.88f, cr, cg, cb);
            DrawNamed(MeshCatalog.CharTorsoHead, 0, _instStaging, drv, ref drawCalls, ref tris);
            return;
        }

        float stride = moving ? MathF.Sin(walkPhase) * 0.55f : 0f;
        float bob = moving ? MathF.Abs(MathF.Cos(walkPhase)) * 0.045f : 0f;
        (float Wx, float Wy, float Wz) LocalToWorld(float lx, float ly, float lz) =>
            (x + lx * cosY + lz * sinY, y + ly + bob, z - lx * sinY + lz * cosY);

        var (tx, ty, tz) = LocalToWorld(0f, 0.92f, 0f);
        int n = Mat4Utils.WriteInstanceTRS(_instStaging, 0, tx, ty, tz, 0, yaw, 0, 1, 1, 1, cr, cg, cb);
        DrawNamed(MeshCatalog.CharTorsoHead, 0, _instStaging, n, ref drawCalls, ref tris);

        var (llx, lly, llz) = LocalToWorld(-0.11f, 0.92f, 0f);
        var (rlx, rly, rlz) = LocalToWorld(0.11f, 0.92f, 0f);
        int lg1 = Mat4Utils.WriteInstanceTRS(_instStaging, 0, llx, lly, llz, stride, yaw, 0, 1, 1, 1);
        DrawNamed(MeshCatalog.CharLeg, 0, _instStaging, lg1, ref drawCalls, ref tris);
        int lg2 = Mat4Utils.WriteInstanceTRS(_instStaging, 0, rlx, rly, rlz, -stride, yaw, 0, 1, 1, 1);
        DrawNamed(MeshCatalog.CharLeg, 0, _instStaging, lg2, ref drawCalls, ref tris);

        float armSwingR = chopAnim > 0.01f ? -1.45f + MathF.Sin((1f - chopAnim) * MathF.PI) * 1.9f : -stride * 0.7f - 0.35f;
        var (lax, lay, laz) = LocalToWorld(-0.26f, 1.40f, 0f);
        var (rax, ray, raz) = LocalToWorld(0.26f, 1.40f, 0f);
        int nL = Mat4Utils.WriteInstanceTRS(_instStaging, 0, lax, lay, laz, stride * 0.7f - 0.25f, yaw, 0, 1, 1, 1, cr, cg, cb);
        DrawNamed(MeshCatalog.CharArm, 0, _instStaging, nL, ref drawCalls, ref tris);
        int nR = Mat4Utils.WriteInstanceTRS(_instStaging, 0, rax, ray, raz, armSwingR, yaw, 0, 1, 1, 1, cr, cg, cb);
        DrawNamed(MeshCatalog.CharArm, 0, _instStaging, nR, ref drawCalls, ref tris);

        if (!string.IsNullOrEmpty(av.Hat) && av.Hat != "none")
        {
            var (hx, hy, hz) = LocalToWorld(0f, 1.85f, 0.02f);
            int nh = Mat4Utils.WriteInstanceTRS(_instStaging, 0, hx, hy, hz, 0, yaw, 0, 1, 1, 1);
            DrawNamed(av.Hat, 0, _instStaging, nh, ref drawCalls, ref tris);
        }

        if (!string.IsNullOrEmpty(av.Back) && av.Back != "none")
        {
            var (bx, by, bz) = LocalToWorld(0f, 1.28f, -0.14f);
            int nb = Mat4Utils.WriteInstanceTRS(_instStaging, 0, bx, by, bz, 0, yaw, 0, 1, 1, 1, 1, 1, 1, av.Back == MeshCatalog.BackCape ? 0.6f : 0.2f);
            DrawNamed(av.Back, 0, _instStaging, nb, ref drawCalls, ref tris);
        }

        string toolMesh = string.IsNullOrEmpty(av.Tool) ? MeshCatalog.ToolEgrek : av.Tool;
        var (twx, twy, twz) = LocalToWorld(0.30f, 1.08f, 0.28f);
        int nT = Mat4Utils.WriteInstanceTRS(_instStaging, 0, twx, twy, twz, 0.28f + (chopAnim > 0.01f ? MathF.Sin(chopAnim * MathF.PI) * 1.15f : 0f), yaw, 0, 1, 1, 1);
        DrawNamed(toolMesh, 0, _instStaging, nT, ref drawCalls, ref tris);
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
}
