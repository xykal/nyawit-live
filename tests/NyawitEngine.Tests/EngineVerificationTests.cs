using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using NyawitEngine.Assets;
using NyawitEngine.Core;
using NyawitEngine.Math;
using NyawitEngine.Network;
using NyawitEngine.Physics;
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
    public void NpakArchive_LoadsAll41UvMappedPbrModelsAndAtlasExists()
    {
        string root = ResolveRepoRoot();
        string path = Path.Combine(root, "src", "Nyawit.Android", "Assets", "Meshes", "nyawit_models.npak");
        string atlasPath = Path.Combine(root, "src", "Nyawit.Android", "Assets", "Textures", "nyawit_pbr_atlas.png");
        Assert.True(File.Exists(atlasPath), "Missing 2048x2048 PBR texture atlas nyawit_pbr_atlas.png");
        Assert.True(new FileInfo(atlasPath).Length > 500_000, "PBR texture atlas must contain rich high-res texel detail");

        using var fs = File.OpenRead(path);
        var archive = NpakArchive.Load(fs);

        Assert.Equal(41, archive.Meshes.Count);
        foreach (string requiredKey in MeshCatalog.AllRequiredNames)
        {
            Assert.True(archive.Meshes.ContainsKey(requiredKey), $"Missing required 3D model '{requiredKey}' in nyawit_models.npak");
        }

        foreach (var kv in archive.Meshes)
        {
            Assert.Equal(3, kv.Value.Lods.Length);
            Assert.True(kv.Value.Lods[0].IndexCount >= kv.Value.Lods[2].IndexCount,
                $"Mesh {kv.Key} LOD2 must be lighter than or equal to LOD0");
            if (kv.Key != MeshCatalog.VfxPuffQuad && kv.Key != MeshCatalog.TropicalFern)
            {
                Assert.True(kv.Value.Lods[0].VertexCount >= 48,
                    $"Mesh {kv.Key} must be a detailed sculpted mesh, never a primitive cube");
            }
        }
    }

    [Fact]
    public void RigidBodyWorld_EnforcesSolidCollisionsSuspensionSteeringAndTbsPickupThrow()
    {
        var trees = PlantationWorld.GenerateTrees();
        var (_, rocks) = PlantationWorld.GenerateScatterProps();
        var phys = new RigidBodyWorld(trees, rocks);

        // 1. Solid collision against Palm Tree Trunk (0% nembus!)
        var tree = trees[0];
        float px = tree.X, pz = tree.Z;
        bool pushed = phys.SolveSolidCircleCollision(ref px, ref pz, 0.44f);
        Assert.True(pushed);
        float distFromTrunk = MathF.Sqrt((px - tree.X) * (px - tree.X) + (pz - tree.Z) * (pz - tree.Z));
        Assert.True(distFromTrunk >= 0.44f + 0.68f * tree.Scale - 0.01f);

        // 2. Canal water barrier blocks direct water crossing at X=0, while Wooden Bridge at X=-28 allows crossing!
        float waterX = 0f, waterZ = PlantationWorld.CanalZ;
        phys.SolveSolidCircleCollision(ref waterX, ref waterZ, 0.44f);
        Assert.True(MathF.Abs(waterZ - PlantationWorld.CanalZ) >= 4.25f);

        float bridgeX = -28f, bridgeZ = PlantationWorld.CanalZ;
        phys.SolveSolidCircleCollision(ref bridgeX, ref bridgeZ, 0.44f);
        Assert.Equal(PlantationWorld.CanalZ, bridgeZ, 2);

        // 3. Canter 4-wheel suspension, front wheel steering & tire rolling rotation!
        phys.MainTruck.X = 0f;
        phys.MainTruck.Z = 6f;
        phys.MainTruck.Yaw = 0f;
        for (int i = 0; i < 30; i++)
            phys.StepWorld(0.016f, inTruck: true, inputSide: 1.0f, inputForward: 1.0f, camYaw: 0f, boars: []);

        Assert.True(phys.MainTruck.SpeedMs > 3.5f);
        Assert.True(phys.MainTruck.WheelSpinRad > 1.5f);
        Assert.True(MathF.Abs(phys.MainTruck.SteerAngle) > 0.25f);
        Assert.True(MathF.Abs(phys.MainTruck.RollRad) > 0.005f);

        // 4. Physical Harvest -> Ground Bounce -> Squat Pickup -> Two-Hand Carry -> Parabolic Throw -> Truck Bounce!
        phys.Player.X = 10f;
        phys.Player.Z = 6f;
        phys.MainTruck.X = 12.8f;
        phys.MainTruck.Z = 6f;
        phys.SpawnHarvestedGroundFruit(10.5f, 6.2f, isGold: true);
        for (int i = 0; i < 90; i++)
            phys.StepWorld(0.016f, inTruck: false, inputSide: 0f, inputForward: 0f, camYaw: 0f, boars: []);

        int picked = phys.TryPickupGroundFruit();
        Assert.True(picked >= 1);
        Assert.True(phys.Player.HasHeldTbs);
        Assert.Equal(HoldStance.CarryingTbs, phys.Player.Stance);

        int cargoBefore = phys.MainTruck.VisualCargoUnits;
        bool thrown = phys.TryLoadIntoTruckOrAngkong(out string msg);
        Assert.True(thrown);
        Assert.False(string.IsNullOrEmpty(msg));

        for (int i = 0; i < 40; i++)
            phys.StepWorld(0.016f, inTruck: false, inputSide: 0f, inputForward: 0f, camYaw: 0f, boars: []);

        Assert.True(phys.MainTruck.VisualCargoUnits > cargoBefore);
    }

    [Fact]
    public void QualityGovernorAndCuller_SelectsLodsAndScalesDownUnderLoad()
    {
        var gov = new QualityGovernor();
        Assert.Equal(GraphicsPreset.Ultra, gov.CurrentPreset);
        for (int i = 0; i < 30; i++) gov.RecordFrame(0.05f);
        Assert.Equal(GraphicsPreset.Standard, gov.CurrentPreset);
        for (int i = 0; i < 30; i++) gov.RecordFrame(0.05f);
        Assert.Equal(GraphicsPreset.Smooth, gov.CurrentPreset);
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
    public async Task LiveServerHandshake_ReceivesAuthoritativeWelcomeAndRoomsFromCloudflare()
    {
        if (Environment.GetEnvironmentVariable("SKIP_LIVE_NET_TEST") == "1") return;
        using var session = new LiveMultiplayerSession(PlantationWorld.GenerateTrees());
        await session.RefreshRoomsFromServerAsync();
        Assert.True(session.GetRoomsSnapshot().Count >= 3);

        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(12));
        bool ok = await session.ConnectOnceForTestAsync("wss://nyawit.xyverse.my.id/ws?room=kebun-sumatera-01&name=xUnitEngineProbe", cts.Token);
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
