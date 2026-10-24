using System;
using System.Collections.Generic;
using NyawitEngine.Network;
using NyawitEngine.World;

namespace NyawitEngine.Physics;

public enum ColliderKind : byte
{
    Cylinder = 0,
    Box = 1,
}

public struct StaticCollider
{
    public ColliderKind Kind;
    public float X;
    public float Z;
    public float Radius;     // Used for Cylinder
    public float HalfX;      // Used for Box
    public float HalfZ;      // Used for Box
    public float TopY;
    public byte Tag;         // 1=Tree, 2=Rock, 3=Building, 4=Guardrail
}

public enum HoldStance : byte
{
    TwoHandTool = 0,     // Default: gripping Egrek / Dodos with both 5-finger hands
    CarryingTbs = 1,     // Holding harvested spiky TBS bunch in front of chest with both hands
    PushingAngkong = 2,  // Gripping red rubber handles of an Angkong cart
    DrivingCanter = 3,   // Seated inside Canter cab gripping steering wheel
}

public struct GroundTbsBody
{
    public bool Active;
    public bool IsGold;
    public int ValueUnits;
    public float X, Y, Z;
    public float Vx, Vy, Vz;
    public float RotX, RotY, SpinVel;
    public byte BounceCount;
    public bool Grounded;
    public float AgeSec;
}

public struct ThrownTbsArc
{
    public bool Active;
    public bool IsGold;
    public int TargetKind;   // 0 = Main Canter, 1 = Angkong, 2 = Yard Canter
    public int TargetIndex;
    public int ValueUnits;
    public float StartX, StartY, StartZ;
    public float EndX, EndY, EndZ;
    public float ElapsedSec;
    public float DurationSec;
    public float CurX, CurY, CurZ;
    public float SpinRad;
}

public sealed class VehicleRigidBody
{
    public float X;
    public float Y;
    public float Z;
    public float Yaw;

    public float SpeedMs;
    public float SteerAngle;       // Front wheel turn angle in radians (-0.48 .. +0.48)
    public float WheelSpinRad;     // Rolling rotation angle of tires

    // 4-Wheel Spring-Damper Suspension State: [0]=FL, [1]=FR, [2]=RL, [3]=RR
    public readonly float[] WheelWorldY = new float[4];
    public readonly float[] WheelSpringOffset = new float[4];
    public readonly float[] WheelSpringVel = new float[4];

    // Chassis RigidBody Heave, Pitch (squat/dive) & Roll ("Canter Oleng")
    public float HeaveY;
    public float HeaveVelY;
    public float PitchRad;
    public float PitchVel;
    public float RollRad;
    public float RollVel;

    public int VisualCargoUnits;

    public void TriggerCargoDropImpulse(float dropStrength = 1.0f)
    {
        HeaveVelY -= 1.45f * dropStrength;
        PitchVel += 0.55f * dropStrength;
        RollVel += ((WheelSpinRad % 0.2f > 0.1f) ? 1f : -1f) * 0.65f * dropStrength;
    }
}

public sealed class AngkongRigidBody
{
    public float X;
    public float Y;
    public float Z;
    public float Yaw;
    public float PitchRad;
    public float WheelSpinRad;
    public int CargoUnits;
    public int GoldUnits;
    public const int MaxUnits = 8;
}

public sealed class CharacterMotorBody
{
    public float X = 8.0f;
    public float Y;
    public float Z = 6.0f;
    public float VelX;
    public float VelY;
    public float VelZ;
    public float Yaw;
    public float GroundedY;
    public bool IsGrounded = true;

    public float MoveSpeedMs;
    public float WalkCycleRad;
    public float IdleBreathPhase;

    // Action & Hold Animation Timers (0 = inactive, >0 counts down)
    public HoldStance Stance = HoldStance.TwoHandTool;
    public float SlashTimer;        // 0.46s two-handed overhead Egrek slash
    public float PickupTimer;       // 0.40s knee-squat & two-handed grab from ground
    public float ThrowTimer;        // 0.46s heave & parabolic toss into Truck / Angkong

    // Held TBS state (up to 3 bunches carried in arms before loading into Angkong/Canter!)
    public int HeldTbsUnits;
    public int HeldGoldUnits;
    public const int MaxHeldUnits = 6;
    public bool HasHeldTbs => HeldTbsUnits > 0;

    public int ActiveAngkongIndex = -1; // -1 = none, 0..1 = pushing that Angkong
}

/// <summary>
/// Deterministic 60Hz Spatial-Hashed RigidBody, Solid Collision ("0% Nembus"), 4-Wheel Spring-Damper
/// Suspension, Front-Wheel Steering, Rolling Tires, and TBS Pickup/Carry/Throw Physics World.
/// </summary>
public sealed class RigidBodyWorld
{
    private const int GridDim = 24;
    private const float WorldHalfSpan = 120f;
    private const float CellSize = (WorldHalfSpan * 2f) / GridDim; // 10.0m cells

    private readonly List<StaticCollider> _colliders = new(480);
    private readonly List<int>[] _cells = new List<int>[GridDim * GridDim];

    public CharacterMotorBody Player { get; } = new();
    public VehicleRigidBody MainTruck { get; } = new() { X = 14.2f, Z = -2.2f, Yaw = -0.35f, VisualCargoUnits = 2 };
    public VehicleRigidBody YardTruck { get; } = new() { X = 11.5f, Z = -18.5f, Yaw = -2.25f, VisualCargoUnits = 8 };
    public AngkongRigidBody[] Angkongs { get; } =
    [
        new() { X = -7.8f, Z = -6.5f, Yaw = 0.65f, CargoUnits = 0 },
        new() { X = 6.4f, Z = 16.5f, Yaw = -1.15f, CargoUnits = 1 },
    ];

    public readonly GroundTbsBody[] GroundFruits = new GroundTbsBody[48];
    public readonly ThrownTbsArc[] ThrownArcs = new ThrownTbsArc[12];

    public event Action<string>? OnPhysicsSfx;
    public event Action<int, bool>? OnCargoLandedInVehicle; // (units, isGold)

    public IReadOnlyList<StaticCollider> StaticColliders => _colliders;

    public RigidBodyWorld(
        IReadOnlyList<PalmTreeNode> trees,
        IReadOnlyList<StaticPropInstance> rocks,
        IReadOnlyList<StaticPropInstance>? saplings = null)
    {
        for (int i = 0; i < _cells.Length; i++) _cells[i] = new List<int>(8);
        var saplingList = saplings ?? PlantationWorld.GenerateJuvenileSaplings(trees);
        BuildStaticWorldColliders(trees, rocks, saplingList);
        ResetPosesToTerrain();
    }

    private void AddCollider(StaticCollider col)
    {
        int idx = _colliders.Count;
        _colliders.Add(col);

        float rx = col.Kind == ColliderKind.Cylinder ? col.Radius : col.HalfX;
        float rz = col.Kind == ColliderKind.Cylinder ? col.Radius : col.HalfZ;

        int minCx = System.Math.Clamp((int)MathF.Floor((col.X - rx + WorldHalfSpan) / CellSize), 0, GridDim - 1);
        int maxCx = System.Math.Clamp((int)MathF.Floor((col.X + rx + WorldHalfSpan) / CellSize), 0, GridDim - 1);
        int minCz = System.Math.Clamp((int)MathF.Floor((col.Z - rz + WorldHalfSpan) / CellSize), 0, GridDim - 1);
        int maxCz = System.Math.Clamp((int)MathF.Floor((col.Z + rz + WorldHalfSpan) / CellSize), 0, GridDim - 1);

        for (int cz = minCz; cz <= maxCz; cz++)
            for (int cx = minCx; cx <= maxCx; cx++)
                _cells[cz * GridDim + cx].Add(idx);
    }

    private void BuildStaticWorldColliders(
        IReadOnlyList<PalmTreeNode> trees,
        IReadOnlyList<StaticPropInstance> rocks,
        IReadOnlyList<StaticPropInstance> saplings)
    {
        // 1. All 220 Mature Oil Palm Trunks — solid cylindrical trunks (ZERO nembus!)
        for (int i = 0; i < trees.Count; i++)
        {
            var t = trees[i];
            AddCollider(new StaticCollider
            {
                Kind = ColliderKind.Cylinder,
                X = t.X,
                Z = t.Z,
                Radius = 0.68f * t.Scale,
                TopY = t.Y + 6.4f * t.Scale,
                Tag = 1,
            });
        }

        // 1b. All 96 Juvenile Palm Saplings ("Bibit Sawit TBM") — compact trunk colliders
        for (int i = 0; i < saplings.Count; i++)
        {
            var s = saplings[i];
            AddCollider(new StaticCollider
            {
                Kind = ColliderKind.Cylinder,
                X = s.X,
                Z = s.Z,
                Radius = 0.28f * s.Scale,
                TopY = s.Y + 1.35f * s.Scale,
                Tag = 1,
            });
        }

        // 2. All Granite/Laterite Plantation Boulders — solid colliders!
        for (int i = 0; i < rocks.Count; i++)
        {
            var r = rocks[i];
            AddCollider(new StaticCollider
            {
                Kind = ColliderKind.Cylinder,
                X = r.X,
                Z = r.Z,
                Radius = 0.78f * r.Scale,
                TopY = r.Y + 0.95f * r.Scale,
                Tag = 2,
            });
        }

        // 3. PKS Palm Oil Factory Main Building + 3 Steel CPO Silos
        AddCollider(new StaticCollider
        {
            Kind = ColliderKind.Box,
            X = PlantationWorld.PksX,
            Z = PlantationWorld.PksZ,
            HalfX = 5.65f,
            HalfZ = 4.55f,
            TopY = 9.0f,
            Tag = 3,
        });
        ReadOnlySpan<(float ox, float oz)> silos = [(7.3f, -2.3f), (7.3f, 1.9f), (-7.3f, 0.2f)];
        foreach (var (ox, oz) in silos)
        {
            AddCollider(new StaticCollider
            {
                Kind = ColliderKind.Cylinder,
                X = PlantationWorld.PksX + ox,
                Z = PlantationWorld.PksZ + oz,
                Radius = 1.82f,
                TopY = 6.2f,
                Tag = 3,
            });
        }

        // 4. Weighbridge RAM Left/Right Steel Guardrails & Operator Booth (center deck stays open to drive onto!)
        AddCollider(new StaticCollider { Kind = ColliderKind.Box, X = PlantationWorld.RamX - 2.16f, Z = PlantationWorld.RamZ, HalfX = 0.22f, HalfZ = 3.65f, TopY = 4.5f, Tag = 4 });
        AddCollider(new StaticCollider { Kind = ColliderKind.Box, X = PlantationWorld.RamX + 2.16f, Z = PlantationWorld.RamZ, HalfX = 0.22f, HalfZ = 3.65f, TopY = 4.5f, Tag = 4 });
        AddCollider(new StaticCollider { Kind = ColliderKind.Box, X = PlantationWorld.RamX + 3.35f, Z = PlantationWorld.RamZ, HalfX = 0.92f, HalfZ = 1.02f, TopY = 2.6f, Tag = 3 });

        // 5. Mandor Post Timber Building & Oil Drums
        AddCollider(new StaticCollider { Kind = ColliderKind.Box, X = PlantationWorld.MandorX, Z = PlantationWorld.MandorZ - 0.15f, HalfX = 1.85f, HalfZ = 1.95f, TopY = 4.2f, Tag = 3 });
        AddCollider(new StaticCollider { Kind = ColliderKind.Cylinder, X = PlantationWorld.MandorX - 2.25f, Z = PlantationWorld.MandorZ + 0.8f, Radius = 0.36f, TopY = 1.2f, Tag = 4 });
        AddCollider(new StaticCollider { Kind = ColliderKind.Cylinder, X = PlantationWorld.MandorX - 2.25f, Z = PlantationWorld.MandorZ - 0.2f, Radius = 0.36f, TopY = 1.2f, Tag = 4 });

        // 6. v6.0 Estate Landmarks: SPBU Solar Pump Island, Warung Kopi, Gudang Pupuk & Drive-Through Offroad Arches!
        AddCollider(new StaticCollider { Kind = ColliderKind.Box, X = PlantationWorld.SpbuX, Z = PlantationWorld.SpbuZ, HalfX = 1.95f, HalfZ = 2.85f, TopY = 4.5f, Tag = 3 });
        AddCollider(new StaticCollider { Kind = ColliderKind.Box, X = PlantationWorld.WarungX, Z = PlantationWorld.WarungZ, HalfX = 2.35f, HalfZ = 2.75f, TopY = 3.3f, Tag = 3 });
        AddCollider(new StaticCollider { Kind = ColliderKind.Box, X = PlantationWorld.GudangX, Z = PlantationWorld.GudangZ, HalfX = 3.55f, HalfZ = 4.10f, TopY = 5.3f, Tag = 3 });

        AddCollider(new StaticCollider { Kind = ColliderKind.Cylinder, X = PlantationWorld.ArchNorthX - 3.12f, Z = PlantationWorld.ArchNorthZ, Radius = 0.42f, TopY = 4.3f, Tag = 4 });
        AddCollider(new StaticCollider { Kind = ColliderKind.Cylinder, X = PlantationWorld.ArchNorthX + 3.12f, Z = PlantationWorld.ArchNorthZ, Radius = 0.42f, TopY = 4.3f, Tag = 4 });
        AddCollider(new StaticCollider { Kind = ColliderKind.Cylinder, X = PlantationWorld.ArchBridgeX - 3.12f, Z = PlantationWorld.ArchBridgeZ, Radius = 0.42f, TopY = 4.3f, Tag = 4 });
        AddCollider(new StaticCollider { Kind = ColliderKind.Cylinder, X = PlantationWorld.ArchBridgeX + 3.12f, Z = PlantationWorld.ArchBridgeZ, Radius = 0.42f, TopY = 4.3f, Tag = 4 });
    }

    public static float SurfaceHeightWithStructures(float x, float z)
    {
        float h = PlantationWorld.SurfaceHeight(x, z);

        // Elevated Steel Weighbridge RAM Deck & Front/Back Yellow Steel Ramps!
        float dxRam = MathF.Abs(x - PlantationWorld.RamX);
        float dzRam = MathF.Abs(z - PlantationWorld.RamZ);
        if (dxRam < 2.02f && dzRam < 5.55f)
        {
            float baseH = PlantationWorld.TerrainHeight(PlantationWorld.RamX, PlantationWorld.RamZ);
            float rampK = dzRam <= 3.75f ? 1.0f : System.Math.Clamp(1.0f - (dzRam - 3.75f) / 1.80f, 0f, 1f);
            float deckH = baseH + 0.30f * rampK;
            if (deckH > h) h = deckH;
        }
        return h;
    }

    private void ResetPosesToTerrain()
    {
        Player.Y = SurfaceHeightWithStructures(Player.X, Player.Z);
        Player.GroundedY = Player.Y;
        StepVehicleSuspension(MainTruck, 0.1f);
        StepVehicleSuspension(YardTruck, 0.1f);
        for (int i = 0; i < Angkongs.Length; i++)
        {
            Angkongs[i].Y = SurfaceHeightWithStructures(Angkongs[i].X, Angkongs[i].Z);
        }
    }

    /// <summary>
    /// Enforces 100% solid collision against:
    ///   - All spatial-hashed static cylinders & boxes (180 palms, 42 rocks, PKS, Silos, RAM rails, Mandor Post)
    ///   - Deep drainage canal banks (strictly passable ONLY via the two wooden bridges at X=-28 and X=+28, with solid bridge side rails!)
    ///   - World perimeter bounds
    ///   - Dynamic vehicles & angkongs
    /// Returns true if a hard impact occurred.
    /// </summary>
    public bool SolveSolidCircleCollision(
        ref float x,
        ref float z,
        float radius,
        VehicleRigidBody? skipVehicle = null,
        int skipAngkong = -1)
    {
        bool hitHard = false;

        for (int iter = 0; iter < 3; iter++)
        {
            // A. Outer world boundary
            float lim = 95.0f - radius;
            if (x < -lim) { x = -lim; hitHard = true; }
            else if (x > lim) { x = lim; hitHard = true; }
            if (z < -lim) { z = -lim; hitHard = true; }
            else if (z > lim) { z = lim; hitHard = true; }

            // B. Drainage Canal Water Barrier & Bridge Handrails!
            bool alignedLeftBridge = MathF.Abs(x + 28f) <= (1.88f - radius * 0.45f);
            bool alignedRightBridge = MathF.Abs(x - 28f) <= (1.88f - radius * 0.45f);
            float dCanal = z - PlantationWorld.CanalZ;

            if (MathF.Abs(dCanal) < (3.85f + radius))
            {
                if (alignedLeftBridge || alignedRightBridge)
                {
                    // Inside wooden bridge span: enforce left & right timber railings so nothing falls sideways off the bridge!
                    float bx = alignedLeftBridge ? -28f : 28f;
                    float maxBridgeHalfW = MathF.Max(0.42f, 1.82f - radius * 0.55f);
                    if (x < bx - maxBridgeHalfW) x = bx - maxBridgeHalfW;
                    else if (x > bx + maxBridgeHalfW) x = bx + maxBridgeHalfW;
                }
                else
                {
                    // Push smoothly back onto the north or south canal bank — NEVER walk or drive into deep water!
                    z = dCanal >= 0f ? (PlantationWorld.CanalZ + 3.85f + radius) : (PlantationWorld.CanalZ - 3.85f - radius);
                    hitHard = true;
                }
            }

            // C. Spatial-hashed static world colliders
            int minCx = System.Math.Clamp((int)MathF.Floor((x - radius - 2.0f + WorldHalfSpan) / CellSize), 0, GridDim - 1);
            int maxCx = System.Math.Clamp((int)MathF.Floor((x + radius + 2.0f + WorldHalfSpan) / CellSize), 0, GridDim - 1);
            int minCz = System.Math.Clamp((int)MathF.Floor((z - radius - 2.0f + WorldHalfSpan) / CellSize), 0, GridDim - 1);
            int maxCz = System.Math.Clamp((int)MathF.Floor((z + radius + 2.0f + WorldHalfSpan) / CellSize), 0, GridDim - 1);

            for (int cz = minCz; cz <= maxCz; cz++)
            {
                for (int cx = minCx; cx <= maxCx; cx++)
                {
                    var bucket = _cells[cz * GridDim + cx];
                    for (int bi = 0; bi < bucket.Count; bi++)
                    {
                        var col = _colliders[bucket[bi]];
                        if (col.Kind == ColliderKind.Cylinder)
                        {
                            float dx = x - col.X;
                            float dz = z - col.Z;
                            float minDist = radius + col.Radius;
                            float d2 = dx * dx + dz * dz;
                            if (d2 < minDist * minDist)
                            {
                                float d = MathF.Sqrt(d2);
                                if (d < 1e-4f) { dx = 1f; dz = 0f; d = 1f; }
                                float push = minDist - d;
                                x += (dx / d) * push;
                                z += (dz / d) * push;
                                hitHard = true;
                            }
                        }
                        else
                        {
                            float dx = x - col.X;
                            float dz = z - col.Z;
                            float clampedX = System.Math.Clamp(dx, -col.HalfX, col.HalfX);
                            float clampedZ = System.Math.Clamp(dz, -col.HalfZ, col.HalfZ);
                            float px = dx - clampedX;
                            float pz = dz - clampedZ;
                            float d2 = px * px + pz * pz;
                            if (d2 < radius * radius)
                            {
                                if (d2 > 1e-6f)
                                {
                                    float d = MathF.Sqrt(d2);
                                    float push = radius - d;
                                    x += (px / d) * push;
                                    z += (pz / d) * push;
                                }
                                else
                                {
                                    float penX = col.HalfX + radius - MathF.Abs(dx);
                                    float penZ = col.HalfZ + radius - MathF.Abs(dz);
                                    if (penX < penZ) x += (dx >= 0f ? penX : -penX);
                                    else z += (dz >= 0f ? penZ : -penZ);
                                }
                                hitHard = true;
                            }
                        }
                    }
                }
            }

            // D. Solid Dynamic Vehicles (Oriented Box 2D Push-Out -> 0% walking/driving through trucks!)
            if (skipVehicle != MainTruck) hitHard |= PushOutOrientedBox(ref x, ref z, radius, MainTruck.X, MainTruck.Z, MainTruck.Yaw, 1.06f, 2.58f);
            if (skipVehicle != YardTruck) hitHard |= PushOutOrientedBox(ref x, ref z, radius, YardTruck.X, YardTruck.Z, YardTruck.Yaw, 1.06f, 2.58f);

            // E. Solid Dynamic Angkongs
            for (int ai = 0; ai < Angkongs.Length; ai++)
            {
                if (ai == skipAngkong) continue;
                float dx = x - Angkongs[ai].X, dz = z - Angkongs[ai].Z;
                float md = radius + 0.58f;
                float d2 = dx * dx + dz * dz;
                if (d2 < md * md)
                {
                    float d = MathF.Max(1e-4f, MathF.Sqrt(d2));
                    x += (dx / d) * (md - d);
                    z += (dz / d) * (md - d);
                    hitHard = true;
                }
            }
        }
        return hitHard;
    }

    private static bool PushOutOrientedBox(ref float wx, ref float wz, float radius, float bx, float bz, float yaw, float halfX, float halfZ)
    {
        float c = MathF.Cos(-yaw), s = MathF.Sin(-yaw);
        float rx = wx - bx, rz = wz - bz;
        float lx = rx * c + rz * s;
        float lz = -rx * s + rz * c;

        float cx = System.Math.Clamp(lx, -halfX, halfX);
        float cz = System.Math.Clamp(lz, -halfZ, halfZ);
        float dx = lx - cx, dz = lz - cz;
        float d2 = dx * dx + dz * dz;
        if (d2 >= radius * radius) return false;

        if (d2 > 1e-6f)
        {
            float d = MathF.Sqrt(d2);
            lx += (dx / d) * (radius - d);
            lz += (dz / d) * (radius - d);
        }
        else
        {
            float px = halfX + radius - MathF.Abs(lx);
            float pz = halfZ + radius - MathF.Abs(lz);
            if (px < pz) lx = lx >= 0f ? (halfX + radius) : -(halfX + radius);
            else lz = lz >= 0f ? (halfZ + radius) : -(halfZ + radius);
        }

        float cw = MathF.Cos(yaw), sw = MathF.Sin(yaw);
        wx = bx + lx * cw + lz * sw;
        wz = bz - lx * sw + lz * cw;
        return true;
    }

    private void StepVehicleSuspension(VehicleRigidBody v, float dt)
    {
        float sy = MathF.Sin(v.Yaw), cy = MathF.Cos(v.Yaw);
        // Wheel local anchors: FL(-0.88, +1.55), FR(+0.88, +1.55), RL(-0.88, -1.25), RR(+0.88, -1.25)
        ReadOnlySpan<float> lx = [-0.88f, 0.88f, -0.88f, 0.88f];
        ReadOnlySpan<float> lz = [1.55f, 1.55f, -1.25f, -1.25f];

        float sumGround = 0f;
        for (int w = 0; w < 4; w++)
        {
            float wx = v.X + lx[w] * cy + lz[w] * sy;
            float wz = v.Z - lx[w] * sy + lz[w] * cy;
            float groundH = SurfaceHeightWithStructures(wx, wz);
            float targetY = groundH + 0.48f;

            // Spring-damper integration per tire so every bump visibly compresses that corner's suspension!
            if (v.WheelWorldY[w] == 0f) v.WheelWorldY[w] = targetY;
            float err = targetY - v.WheelWorldY[w];
            v.WheelSpringVel[w] = (v.WheelSpringVel[w] + err * 145f * dt) * MathF.Exp(-11.5f * dt);
            v.WheelWorldY[w] += v.WheelSpringVel[w] * dt;
            if (v.WheelWorldY[w] < targetY - 0.16f) v.WheelWorldY[w] = targetY - 0.16f;
            if (v.WheelWorldY[w] > targetY + 0.22f) v.WheelWorldY[w] = targetY + 0.22f;
            v.WheelSpringOffset[w] = v.WheelWorldY[w] - targetY;
            sumGround += v.WheelWorldY[w] - 0.48f;
        }

        float avgGround = sumGround * 0.25f;
        v.HeaveVelY = (v.HeaveVelY - v.HeaveY * 58f * dt) * MathF.Exp(-6.8f * dt);
        v.HeaveY = System.Math.Clamp(v.HeaveY + v.HeaveVelY * dt, -0.18f, 0.22f);
        v.Y = avgGround + v.HeaveY;

        float frontY = (v.WheelWorldY[0] + v.WheelWorldY[1]) * 0.5f;
        float rearY = (v.WheelWorldY[2] + v.WheelWorldY[3]) * 0.5f;
        float leftY = (v.WheelWorldY[0] + v.WheelWorldY[2]) * 0.5f;
        float rightY = (v.WheelWorldY[1] + v.WheelWorldY[3]) * 0.5f;

        float terrainPitch = -MathF.Atan2(frontY - rearY, 2.80f);
        float terrainRoll = MathF.Atan2(leftY - rightY, 1.76f);

        // Signature "Canter Oleng" suspension lean on steering + accel/brake pitch!
        float targetRoll = terrainRoll + System.Math.Clamp(v.SteerAngle * (v.SpeedMs / 13.5f) * 0.28f, -0.16f, 0.16f);
        v.RollVel = (v.RollVel + (targetRoll - v.RollRad) * 44f * dt) * MathF.Exp(-6.2f * dt);
        v.RollRad = System.Math.Clamp(v.RollRad + v.RollVel * dt, -0.24f, 0.24f);

        v.PitchVel = (v.PitchVel + (terrainPitch - v.PitchRad) * 46f * dt) * MathF.Exp(-7.0f * dt);
        v.PitchRad = System.Math.Clamp(v.PitchRad + v.PitchVel * dt, -0.26f, 0.26f);
    }

    public void StepWorld(
        float rawDt,
        bool inTruck,
        float inputSide,     // -1 left .. +1 right (joystick X / steer)
        float inputForward,  // -1 back/brake .. +1 forward/throttle
        float camYaw,
        IReadOnlyList<BoarNetState> boars)
    {
        float dt = System.Math.Clamp(rawDt, 0.001f, 0.05f);
        Player.IdleBreathPhase += dt * 2.2f;
        if (Player.SlashTimer > 0f) Player.SlashTimer = MathF.Max(0f, Player.SlashTimer - dt);
        if (Player.PickupTimer > 0f) Player.PickupTimer = MathF.Max(0f, Player.PickupTimer - dt);
        if (Player.ThrowTimer > 0f) Player.ThrowTimer = MathF.Max(0f, Player.ThrowTimer - dt);

        if (inTruck)
        {
            Player.ActiveAngkongIndex = -1;
            Player.Stance = HoldStance.DrivingCanter;

            // 1. Steer front wheels smoothly (-27.5 deg .. +27.5 deg)
            float desiredSteer = -inputSide * 0.48f;
            MainTruck.SteerAngle += (desiredSteer - MainTruck.SteerAngle) * MathF.Min(1f, dt * 8.5f);

            // 2. Engine Torque, Braking, Reverse & Road/Mud Rolling Resistance
            float mudDrag = 1f - 0.22f * PlantationWorld.MudFactor(MainTruck.X, MainTruck.Z);
            float prevSpeed = MainTruck.SpeedMs;
            if (inputForward > 0.05f)
            {
                MainTruck.SpeedMs += inputForward * 14.5f * mudDrag * dt;
            }
            else if (inputForward < -0.05f)
            {
                if (MainTruck.SpeedMs > 0.5f) MainTruck.SpeedMs += inputForward * 24.0f * dt; // Strong air-brakes!
                else MainTruck.SpeedMs += inputForward * 7.5f * mudDrag * dt;                // Smooth reverse gear!
            }
            else
            {
                MainTruck.SpeedMs *= MathF.Exp(-2.6f * dt);
                if (MathF.Abs(MainTruck.SpeedMs) < 0.04f) MainTruck.SpeedMs = 0f;
            }
            MainTruck.SpeedMs = System.Math.Clamp(MainTruck.SpeedMs, -6.2f, 15.8f * mudDrag);

            // Pitch squat on acceleration / dive on braking!
            float accel = (MainTruck.SpeedMs - prevSpeed) / dt;
            MainTruck.PitchVel -= System.Math.Clamp(accel * 0.032f, -0.9f, 0.9f) * dt * 12f;

            // Bicycle-ackermann yaw rate proportional to front wheel steerAngle & longitudinal speed
            if (MathF.Abs(MainTruck.SpeedMs) > 0.08f)
            {
                float turnFactor = MathF.Sign(MainTruck.SpeedMs) * MathF.Min(1f, MathF.Abs(MainTruck.SpeedMs) / 3.8f);
                MainTruck.Yaw += MainTruck.SteerAngle * 2.55f * turnFactor * dt;
            }

            // Advance front & rear multi-point solid chassis collision (Front Cab + Center + Rear Bed -> 0% Nembus!)
            float nx = MainTruck.X + MathF.Sin(MainTruck.Yaw) * MainTruck.SpeedMs * dt;
            float nz = MainTruck.Z + MathF.Cos(MainTruck.Yaw) * MainTruck.SpeedMs * dt;

            float sy = MathF.Sin(MainTruck.Yaw), cy = MathF.Cos(MainTruck.Yaw);
            float fx = nx + sy * 1.45f, fz = nz + cy * 1.45f;
            float rx = nx - sy * 1.45f, rz = nz - cy * 1.45f;
            bool hitFront = SolveSolidCircleCollision(ref fx, ref fz, 1.05f, skipVehicle: MainTruck);
            bool hitRear = SolveSolidCircleCollision(ref rx, ref rz, 1.05f, skipVehicle: MainTruck);
            nx = (fx + rx) * 0.5f;
            nz = (fz + rz) * 0.5f;
            bool hitCenter = SolveSolidCircleCollision(ref nx, ref nz, 1.08f, skipVehicle: MainTruck);

            if ((hitFront || hitRear || hitCenter) && MathF.Abs(MainTruck.SpeedMs) > 2.4f)
            {
                MainTruck.HeaveVelY -= 0.85f;
                MainTruck.PitchVel += MathF.Sign(MainTruck.SpeedMs) * 0.8f;
                MainTruck.SpeedMs *= 0.35f;
                OnPhysicsSfx?.Invoke("bump");
            }
            MainTruck.X = nx;
            MainTruck.Z = nz;

            // Real rolling tire rotation matching ground speed!
            MainTruck.WheelSpinRad += (MainTruck.SpeedMs / 0.48f) * dt;
            StepVehicleSuspension(MainTruck, dt);
            StepVehicleSuspension(YardTruck, dt);

            Player.X = MainTruck.X;
            Player.Y = MainTruck.Y;
            Player.Z = MainTruck.Z;
            Player.Yaw = MainTruck.Yaw;
            Player.MoveSpeedMs = MathF.Abs(MainTruck.SpeedMs);
        }
        else
        {
            // Parked vehicles still settle smoothly on their springs (including when cargo lands in the bed!)
            MainTruck.SpeedMs *= MathF.Exp(-5.0f * dt);
            MainTruck.SteerAngle *= MathF.Exp(-4.0f * dt);
            MainTruck.WheelSpinRad += (MainTruck.SpeedMs / 0.48f) * dt;
            StepVehicleSuspension(MainTruck, dt);
            StepVehicleSuspension(YardTruck, dt);

            // On-Foot RigidBody Character Motor + Solid Collisions + Gravity
            float mag = MathF.Sqrt(inputSide * inputSide + inputForward * inputForward);
            if (mag > 0.05f)
            {
                float n = MathF.Min(1f, mag);
                float fwdX = -MathF.Sin(camYaw), fwdZ = -MathF.Cos(camYaw);
                float rgtX = MathF.Cos(camYaw), rgtZ = -MathF.Sin(camYaw);
                float wx = fwdX * inputForward + rgtX * inputSide;
                float wz = fwdZ * inputForward + rgtZ * inputSide;
                float wl = MathF.Max(1e-4f, MathF.Sqrt(wx * wx + wz * wz));
                wx /= wl; wz /= wl;

                float mud = PlantationWorld.MudFactor(Player.X, Player.Z);
                float carryFactor = Player.ActiveAngkongIndex >= 0 ? 0.82f : (Player.HasHeldTbs ? 0.90f : 1.0f);
                float topSpeed = 8.4f * (1f - 0.16f * mud) * carryFactor * n;

                Player.VelX += (wx * topSpeed - Player.VelX) * MathF.Min(1f, dt * 14f);
                Player.VelZ += (wz * topSpeed - Player.VelZ) * MathF.Min(1f, dt * 14f);

                float targetYaw = MathF.Atan2(wx, wz);
                float dyaw = targetYaw - Player.Yaw;
                while (dyaw > MathF.PI) dyaw -= MathF.PI * 2f;
                while (dyaw < -MathF.PI) dyaw += MathF.PI * 2f;
                Player.Yaw += dyaw * MathF.Min(1f, dt * 13f);
            }
            else
            {
                Player.VelX *= MathF.Exp(-14f * dt);
                Player.VelZ *= MathF.Exp(-14f * dt);
            }

            // Wild Boar dynamic solid collision & knockback impulse!
            for (int bi = 0; bi < boars.Count; bi++)
            {
                float bdx = Player.X - boars[bi].X, bdz = Player.Z - boars[bi].Z;
                float bd2 = bdx * bdx + bdz * bdz;
                if (bd2 < 1.35f * 1.35f)
                {
                    float bd = MathF.Max(0.05f, MathF.Sqrt(bd2));
                    Player.X += (bdx / bd) * (1.35f - bd);
                    Player.Z += (bdz / bd) * (1.35f - bd);
                    Player.VelX = (bdx / bd) * 7.2f;
                    Player.VelZ = (bdz / bd) * 7.2f;
                    Player.VelY = MathF.Max(Player.VelY, 2.8f);
                    Player.IsGrounded = false;
                }
            }

            float px = Player.X + Player.VelX * dt;
            float pz = Player.Z + Player.VelZ * dt;
            SolveSolidCircleCollision(ref px, ref pz, 0.44f, skipAngkong: Player.ActiveAngkongIndex);
            Player.X = px;
            Player.Z = pz;

            Player.MoveSpeedMs = MathF.Sqrt(Player.VelX * Player.VelX + Player.VelZ * Player.VelZ);
            if (Player.MoveSpeedMs > 0.15f)
                Player.WalkCycleRad += dt * (2.2f + Player.MoveSpeedMs * 1.18f);

            // Vertical RigidBody Gravity & Terrain Snap
            float groundH = SurfaceHeightWithStructures(Player.X, Player.Z);
            Player.GroundedY = groundH;
            if (!Player.IsGrounded || Player.Y > groundH + 0.04f)
            {
                Player.VelY -= 18.5f * dt;
                Player.Y += Player.VelY * dt;
                if (Player.Y <= groundH)
                {
                    Player.Y = groundH;
                    Player.VelY = 0f;
                    Player.IsGrounded = true;
                }
            }
            else
            {
                Player.Y = groundH;
                Player.VelY = 0f;
            }

            // Update Hold Stance
            if (Player.ActiveAngkongIndex >= 0)
            {
                Player.Stance = HoldStance.PushingAngkong;
                var ak = Angkongs[Player.ActiveAngkongIndex];
                float targetAx = Player.X + MathF.Sin(Player.Yaw) * 1.18f;
                float targetAz = Player.Z + MathF.Cos(Player.Yaw) * 1.18f;
                SolveSolidCircleCollision(ref targetAx, ref targetAz, 0.56f, skipAngkong: Player.ActiveAngkongIndex);
                float moved = MathF.Sqrt((targetAx - ak.X) * (targetAx - ak.X) + (targetAz - ak.Z) * (targetAz - ak.Z));
                ak.X = targetAx;
                ak.Z = targetAz;
                ak.Yaw = Player.Yaw;
                ak.Y = SurfaceHeightWithStructures(ak.X, ak.Z);
                ak.WheelSpinRad += (moved / 0.28f); // Real spinning Angkong wheel!
                float frontH = SurfaceHeightWithStructures(ak.X + MathF.Sin(ak.Yaw) * 0.8f, ak.Z + MathF.Cos(ak.Yaw) * 0.8f);
                ak.PitchRad = -MathF.Atan2(frontH - ak.Y, 0.8f);
            }
            else
            {
                Player.Stance = Player.HasHeldTbs ? HoldStance.CarryingTbs : HoldStance.TwoHandTool;
            }
        }

        // Keep idle Angkongs grounded cleanly
        for (int i = 0; i < Angkongs.Length; i++)
        {
            if (i == Player.ActiveAngkongIndex) continue;
            Angkongs[i].Y = SurfaceHeightWithStructures(Angkongs[i].X, Angkongs[i].Z);
        }

        StepGroundFruitsAndThrows(dt);
    }

    public void SpawnHarvestedGroundFruit(float treeX, float treeZ, bool isGold)
    {
        int count = isGold ? 3 : 2;
        int unitVal = 1;
        for (int k = 0; k < count; k++)
        {
            int slot = FindFreeFruitSlot();
            float ang = (k * 2.15f) + (treeX * 0.37f);
            float dist = 1.05f + 0.35f * k;
            float sx = treeX + MathF.Cos(ang) * dist;
            float sz = treeZ + MathF.Sin(ang) * dist;
            SolveSolidCircleCollision(ref sx, ref sz, 0.32f);

            GroundFruits[slot] = new GroundTbsBody
            {
                Active = true,
                IsGold = isGold && k == 0,
                ValueUnits = isGold && k == 0 ? 2 : unitVal,
                X = sx,
                Y = SurfaceHeightWithStructures(treeX, treeZ) + 5.3f + 0.35f * k,
                Z = sz,
                Vx = MathF.Cos(ang) * 1.45f,
                Vy = 0.8f,
                Vz = MathF.Sin(ang) * 1.45f,
                RotY = ang,
                SpinVel = 4.2f,
                BounceCount = 0,
                Grounded = false,
                AgeSec = 0f,
            };
        }
    }

    private int FindFreeFruitSlot()
    {
        int oldestIdx = 0;
        float oldestAge = -1f;
        for (int i = 0; i < GroundFruits.Length; i++)
        {
            if (!GroundFruits[i].Active) return i;
            if (GroundFruits[i].AgeSec > oldestAge) { oldestAge = GroundFruits[i].AgeSec; oldestIdx = i; }
        }
        return oldestIdx;
    }

    public int FindNearestGroundFruit(float maxDist = 3.2f)
    {
        int best = -1;
        float bestD2 = maxDist * maxDist;
        for (int i = 0; i < GroundFruits.Length; i++)
        {
            if (!GroundFruits[i].Active || GroundFruits[i].Y > SurfaceHeightWithStructures(GroundFruits[i].X, GroundFruits[i].Z) + 1.8f)
                continue;
            float dx = GroundFruits[i].X - Player.X, dz = GroundFruits[i].Z - Player.Z;
            float d2 = dx * dx + dz * dz;
            if (d2 < bestD2) { bestD2 = d2; best = i; }
        }
        return best;
    }

    public int CountNearbyGroundFruits(float maxDist = 4.2f)
    {
        int cnt = 0;
        float maxD2 = maxDist * maxDist;
        for (int i = 0; i < GroundFruits.Length; i++)
        {
            if (!GroundFruits[i].Active) continue;
            float dx = GroundFruits[i].X - Player.X, dz = GroundFruits[i].Z - Player.Z;
            if (dx * dx + dz * dz <= maxD2) cnt++;
        }
        return cnt;
    }

    /// <summary>
    /// Plays knee-squat pickup animation ("Animasi Mengambil Sawit") and lifts nearby fallen TBS into hands!
    /// </summary>
    public int TryPickupGroundFruit()
    {
        int picked = 0;
        for (int pass = 0; pass < 3 && Player.HeldTbsUnits < CharacterMotorBody.MaxHeldUnits; pass++)
        {
            int idx = FindNearestGroundFruit(3.6f);
            if (idx < 0) break;
            ref var f = ref GroundFruits[idx];
            Player.HeldTbsUnits += f.ValueUnits;
            if (f.IsGold) Player.HeldGoldUnits++;
            f.Active = false;
            picked++;
            Player.Yaw = MathF.Atan2(f.X - Player.X, f.Z - Player.Z);
        }
        if (picked > 0)
        {
            Player.PickupTimer = 0.40f;
            Player.Stance = HoldStance.CarryingTbs;
            OnPhysicsSfx?.Invoke("pickup");
        }
        return picked;
    }

    public int FindNearbyAngkong(float maxDist = 2.9f)
    {
        for (int i = 0; i < Angkongs.Length; i++)
        {
            float dx = Angkongs[i].X - Player.X, dz = Angkongs[i].Z - Player.Z;
            if (dx * dx + dz * dz <= maxDist * maxDist) return i;
        }
        return -1;
    }

    public bool IsNearMainTruck(float maxDist = 5.4f)
    {
        float dx = MainTruck.X - Player.X, dz = MainTruck.Z - Player.Z;
        return dx * dx + dz * dz <= maxDist * maxDist;
    }

    /// <summary>
    /// Launches held TBS or Angkong TBS along a real 3D parabolic ballistic arc straight into the Canter bed
    /// or Angkong tray ("Animasi Menaruh Sawit ke Truk / Angkong") and bounces the suspension on impact!
    /// </summary>
    public bool TryLoadIntoTruckOrAngkong(out string actionFeedback)
    {
        actionFeedback = "";
        bool nearTruck = IsNearMainTruck(5.6f);
        int nearAngkong = FindNearbyAngkong(3.4f);

        // Priority 1: If pushing/near an Angkong WITH cargo AND right beside the Canter Truck -> transfer Angkong -> Canter!
        if (nearTruck && nearAngkong >= 0 && Angkongs[nearAngkong].CargoUnits > 0 && !Player.HasHeldTbs)
        {
            var ak = Angkongs[nearAngkong];
            int units = ak.CargoUnits;
            bool gold = ak.GoldUnits > 0;
            ak.CargoUnits = 0;
            ak.GoldUnits = 0;
            Player.ThrowTimer = 0.48f;
            Player.Yaw = MathF.Atan2(MainTruck.X - Player.X, MainTruck.Z - Player.Z);
            LaunchParabolicArc(ak.X, ak.Y + 0.9f, ak.Z, MainTruck.X - MathF.Sin(MainTruck.Yaw) * 0.9f, MainTruck.Y + 1.55f, MainTruck.Z - MathF.Cos(MainTruck.Yaw) * 0.9f, 0, 0, units, gold);
            OnPhysicsSfx?.Invoke("throw");
            actionFeedback = $"Muat {units} TBS dari Angkong ke Bak Truk Canter!";
            return true;
        }

        // Priority 2: Holding TBS in both hands -> heave into Canter Truck bed!
        if (Player.HasHeldTbs && nearTruck)
        {
            int units = Player.HeldTbsUnits;
            bool gold = Player.HeldGoldUnits > 0;
            Player.HeldTbsUnits = 0;
            Player.HeldGoldUnits = 0;
            Player.ThrowTimer = 0.48f;
            Player.Yaw = MathF.Atan2(MainTruck.X - Player.X, MainTruck.Z - Player.Z);
            LaunchParabolicArc(
                Player.X + MathF.Sin(Player.Yaw) * 0.45f, Player.Y + 1.25f, Player.Z + MathF.Cos(Player.Yaw) * 0.45f,
                MainTruck.X - MathF.Sin(MainTruck.Yaw) * 0.85f, MainTruck.Y + 1.55f, MainTruck.Z - MathF.Cos(MainTruck.Yaw) * 0.85f,
                targetKind: 0, targetIdx: 0, units: units, isGold: gold);
            OnPhysicsSfx?.Invoke("throw");
            actionFeedback = $"Lempar {units} Janjang TBS Masuk Bak Canter!";
            return true;
        }

        // Priority 3: Holding TBS in both hands -> place into Angkong cart!
        if (Player.HasHeldTbs && nearAngkong >= 0 && Angkongs[nearAngkong].CargoUnits < AngkongRigidBody.MaxUnits)
        {
            var ak = Angkongs[nearAngkong];
            int space = AngkongRigidBody.MaxUnits - ak.CargoUnits;
            int move = System.Math.Min(space, Player.HeldTbsUnits);
            bool gold = Player.HeldGoldUnits > 0;
            Player.HeldTbsUnits -= move;
            if (Player.HeldTbsUnits == 0) Player.HeldGoldUnits = 0;
            Player.ThrowTimer = 0.42f;
            Player.Yaw = MathF.Atan2(ak.X - Player.X, ak.Z - Player.Z);
            LaunchParabolicArc(
                Player.X + MathF.Sin(Player.Yaw) * 0.42f, Player.Y + 1.22f, Player.Z + MathF.Cos(Player.Yaw) * 0.42f,
                ak.X, ak.Y + 0.88f, ak.Z,
                targetKind: 1, targetIdx: nearAngkong, units: move, isGold: gold);
            OnPhysicsSfx?.Invoke("throw");
            actionFeedback = $"Taruh TBS ke Angkong ({ak.CargoUnits + move}/{AngkongRigidBody.MaxUnits})!";
            return true;
        }

        return false;
    }

    public void LaunchDirectTreeToTruckArc(float treeX, float treeZ, bool isGold)
    {
        LaunchParabolicArc(
            treeX, SurfaceHeightWithStructures(treeX, treeZ) + 4.8f, treeZ,
            MainTruck.X - MathF.Sin(MainTruck.Yaw) * 0.85f, MainTruck.Y + 1.55f, MainTruck.Z - MathF.Cos(MainTruck.Yaw) * 0.85f,
            targetKind: 0, targetIdx: 0, units: isGold ? 3 : 2, isGold: isGold);
    }

    private void LaunchParabolicArc(float sx, float sy, float sz, float ex, float ey, float ez, int targetKind, int targetIdx, int units, bool isGold)
    {
        for (int i = 0; i < ThrownArcs.Length; i++)
        {
            if (ThrownArcs[i].Active) continue;
            ThrownArcs[i] = new ThrownTbsArc
            {
                Active = true,
                IsGold = isGold,
                TargetKind = targetKind,
                TargetIndex = targetIdx,
                ValueUnits = units,
                StartX = sx, StartY = sy, StartZ = sz,
                EndX = ex, EndY = ey, EndZ = ez,
                CurX = sx, CurY = sy, CurZ = sz,
                ElapsedSec = 0f,
                DurationSec = 0.46f,
            };
            return;
        }
    }

    private void StepGroundFruitsAndThrows(float dt)
    {
        for (int i = 0; i < GroundFruits.Length; i++)
        {
            if (!GroundFruits[i].Active) continue;
            ref var f = ref GroundFruits[i];
            f.AgeSec += dt;
            if (f.AgeSec > 55f) { f.Active = false; continue; }

            if (!f.Grounded)
            {
                f.Vy -= 16.5f * dt;
                f.X += f.Vx * dt;
                f.Y += f.Vy * dt;
                f.Z += f.Vz * dt;
                f.RotX += f.SpinVel * dt;
                f.RotY += f.SpinVel * 0.55f * dt;
                SolveSolidCircleCollision(ref f.X, ref f.Z, 0.30f);

                float gh = SurfaceHeightWithStructures(f.X, f.Z) + 0.24f;
                if (f.Y <= gh)
                {
                    f.Y = gh;
                    if (f.BounceCount < 2 && MathF.Abs(f.Vy) > 1.8f)
                    {
                        f.Vy = -f.Vy * 0.36f;
                        f.Vx *= 0.58f;
                        f.Vz *= 0.58f;
                        f.SpinVel *= 0.55f;
                        f.BounceCount++;
                        if (f.BounceCount == 1) OnPhysicsSfx?.Invoke("thud");
                    }
                    else
                    {
                        f.Grounded = true;
                        f.Vx = f.Vy = f.Vz = 0f;
                    }
                }
            }
        }

        for (int i = 0; i < ThrownArcs.Length; i++)
        {
            if (!ThrownArcs[i].Active) continue;
            ref var a = ref ThrownArcs[i];
            a.ElapsedSec += dt;
            float t = System.Math.Clamp(a.ElapsedSec / a.DurationSec, 0f, 1f);
            if (a.TargetKind == 0)
            {
                a.EndX = MainTruck.X - MathF.Sin(MainTruck.Yaw) * 0.85f;
                a.EndY = MainTruck.Y + 1.55f;
                a.EndZ = MainTruck.Z - MathF.Cos(MainTruck.Yaw) * 0.85f;
            }
            float arcLift = 1.45f * 4f * t * (1f - t);
            a.CurX = a.StartX + (a.EndX - a.StartX) * t;
            a.CurY = a.StartY + (a.EndY - a.StartY) * t + arcLift;
            a.CurZ = a.StartZ + (a.EndZ - a.StartZ) * t;
            a.SpinRad += dt * 9.5f;

            if (t >= 1f)
            {
                a.Active = false;
                if (a.TargetKind == 0)
                {
                    MainTruck.VisualCargoUnits = System.Math.Min(24, MainTruck.VisualCargoUnits + a.ValueUnits);
                    MainTruck.TriggerCargoDropImpulse(1.0f);
                    OnPhysicsSfx?.Invoke("load_truck");
                    OnCargoLandedInVehicle?.Invoke(a.ValueUnits, a.IsGold);
                }
                else if (a.TargetKind == 1 && (uint)a.TargetIndex < (uint)Angkongs.Length)
                {
                    Angkongs[a.TargetIndex].CargoUnits = System.Math.Min(AngkongRigidBody.MaxUnits, Angkongs[a.TargetIndex].CargoUnits + a.ValueUnits);
                    if (a.IsGold) Angkongs[a.TargetIndex].GoldUnits++;
                    OnPhysicsSfx?.Invoke("load_angkong");
                }
            }
        }
    }
}
