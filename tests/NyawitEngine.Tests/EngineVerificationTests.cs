using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using NyawitEngine.Assets;
using NyawitEngine.Core;
using NyawitEngine.Math;
using NyawitEngine.Network;
using NyawitEngine.World;
using Xunit;

namespace NyawitEngine.Tests;

public sealed class EngineVerificationTests
{
    private static string ResolveRepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null && !File.Exists(Path.Combine(dir.FullName, "src", "Nyawit.Android", "Assets", "Meshes", "nyawit_models.npak")))
            dir = dir.Parent;
        return dir?.FullName ?? throw new FileNotFoundException("Could not locate repository root");
    }

    [Fact]
    public void NpakArchive_LoadsAll29SculptedModelsAndMatchesEveryMeshCatalogKey()
    {
        string path = Path.Combine(ResolveRepoRoot(), "src", "Nyawit.Android", "Assets", "Meshes", "nyawit_models.npak");
        using var fs = File.OpenRead(path);
        var archive = NpakArchive.Load(fs);

        Assert.Equal(29, archive.Meshes.Count);
        foreach (string requiredKey in MeshCatalog.AllRequiredNames)
        {
            Assert.True(archive.Meshes.ContainsKey(requiredKey), $"Missing required 3D model '{requiredKey}' in nyawit_models.npak");
        }

        foreach (var kv in archive.Meshes)
        {
            Assert.Equal(3, kv.Value.Lods.Length);
            Assert.True(kv.Value.Lods[0].IndexCount >= kv.Value.Lods[2].IndexCount,
                $"Mesh {kv.Key} LOD2 must be lighter than or equal to LOD0");
            Assert.True(kv.Value.Lods[0].VertexCount >= 70,
                $"Mesh {kv.Key} must be a detailed sculpted mesh, never a primitive cube");
        }
    }

    [Fact]
    public void PlantationWorld_GeneratesDeterministic180TreesAndTerrainMesh()
    {
        var treesA = PlantationWorld.GenerateTrees();
        var treesB = PlantationWorld.GenerateTrees();
        Assert.Equal(180, treesA.Count);
        for (int i = 0; i < treesA.Count; i++)
        {
            Assert.Equal(treesA[i].X, treesB[i].X);
            Assert.Equal(treesA[i].Z, treesB[i].Z);
            Assert.Equal(treesA[i].RotationY, treesB[i].RotationY);
        }

        var terrain = PlantationWorld.BuildSplattedTerrainMesh(64, 224f);
        Assert.Equal(64 * 64, terrain.VertexCount);
        Assert.Equal(63 * 63 * 6, terrain.IndexCount);
    }

    [Fact]
    public void QualityGovernorAndCuller_SelectsLodsAndScalesDownUnderLoad()
    {
        var gov = new QualityGovernor();
        Assert.Equal(GraphicsPreset.Ultra, gov.CurrentPreset);

        // 30 x 0.05s = 1.5s = 3 half-second low-FPS strikes -> steps down Ultra -> Standard
        for (int i = 0; i < 30; i++) gov.RecordFrame(0.05f);
        Assert.Equal(GraphicsPreset.Standard, gov.CurrentPreset);

        // Another 30 x 0.05s -> steps down Standard -> Smooth (HP Kentang mode!)
        for (int i = 0; i < 30; i++) gov.RecordFrame(0.05f);
        Assert.Equal(GraphicsPreset.Smooth, gov.CurrentPreset);

        float[] pos = [0f, 0f, 5f, 0f, 0f, 45f, 0f, 0f, 95f, 0f, 0f, 260f];
        sbyte[] lods = new sbyte[4];
        int vis = SimdCuller.SelectLodBatch(pos, 4, 0, 2, 0, 0, 0, 1, 20f, 65f, 150f, lods);
        Assert.Equal(3, vis);
        Assert.Equal(0, lods[0]);
        Assert.Equal(1, lods[1]);
        Assert.Equal(2, lods[2]);
        Assert.Equal(-1, lods[3]);
    }

    [Fact]
    public void SceneGraphMonoBehaviourLifecycle_RunsAwakeStartUpdateLateUpdate()
    {
        var scene = new Scene("KebunTest");
        var go = scene.CreateGameObject("Player");
        var probe = go.AddComponent<TestBehaviour>();
        Assert.Equal(1, probe.AwakeCalls);
        scene.StepFrame(0.016f);
        scene.StepFrame(0.016f);
        Assert.Equal(1, probe.StartCalls);
        Assert.Equal(2, probe.UpdateCalls);
        Assert.Equal(2, probe.LateCalls);
    }

    [Fact]
    public async Task LiveServerHandshake_ReceivesAuthoritativeWelcomeFromCloudflare()
    {
        if (Environment.GetEnvironmentVariable("SKIP_LIVE_NET_TEST") == "1") return;
        using var session = new LiveMultiplayerSession(PlantationWorld.GenerateTrees());
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(12));
        bool ok = await session.ConnectOnceForTestAsync("wss://nyawit.xyverse.my.id/ws?name=xUnitEngineProbe", cts.Token);
        Assert.True(ok);
        Assert.StartsWith("p_", session.Profile.Id);
    }

    private sealed class TestBehaviour : MonoBehaviour
    {
        public int AwakeCalls, StartCalls, UpdateCalls, LateCalls;
        public override void Awake() => AwakeCalls++;
        public override void Start() => StartCalls++;
        public override void Update(float dt) => UpdateCalls++;
        public override void LateUpdate(float dt) => LateCalls++;
    }
}
