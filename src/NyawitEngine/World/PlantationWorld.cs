using System;
using System.Collections.Generic;
using NyawitEngine.Assets;

namespace NyawitEngine.World;

public sealed class PalmTreeNode
{
    public int Id { get; init; }
    public float X { get; init; }
    public float Y { get; init; }
    public float Z { get; init; }
    public float RotationY { get; init; }
    public float Scale { get; init; }
    public int State { get; set; } = 1; // 0 = Regrowing, 1 = Ripe Red TBS, 2 = Golden Sawit Sultan 24K
}

public struct StaticPropInstance
{
    public float X, Y, Z, RotY, Scale;
}

public struct FallingTbs
{
    public bool Active;
    public float X, Y, Z;
    public float Vx, Vy, Vz;
    public float Rot;
    public float GroundY;
    public float Life;
    public bool IsGold;
}

public static class PlantationWorld
{
    public const uint WorldSeed = 20261022u;
    public const float CanalZ = -48.0f;
    public const float PksX = 0.0f, PksZ = -26.0f;
    public const float RamX = 0.0f, RamZ = -14.5f;
    public const float MandorX = -12.5f, MandorZ = -11.0f;

    public static Func<double> CreateMulberry32(uint seed)
    {
        uint a = seed;
        return () =>
        {
            a = unchecked(a + 0x6D2B79F5u);
            uint t = unchecked((a ^ (a >> 15)) * (1u | a));
            t = unchecked((t + unchecked((t ^ (t >> 7)) * (61u | t))) ^ t);
            return ((t ^ (t >> 14)) / 4294967296.0);
        };
    }

    public static float RoadFactor(double x, double z)
    {
        double dNS = System.Math.Abs(x);
        double dEW = System.Math.Abs(z - 14.0);
        double rLoop = System.Math.Abs(System.Math.Sqrt(x * x + (z - 8.0) * (z - 8.0)) - 70.0);
        double dPlaza = System.Math.Max(0.0, System.Math.Sqrt(x * x + (z + 15.0) * (z + 15.0)) - 15.5);
        double dBL = System.Math.Abs(x + 28.0) < 2.4 && System.Math.Abs(z - CanalZ) < 6.5 ? 0.0 : 99.0;
        double dBR = System.Math.Abs(x - 28.0) < 2.4 && System.Math.Abs(z - CanalZ) < 6.5 ? 0.0 : 99.0;
        double dMin = System.Math.Min(System.Math.Min(System.Math.Min(dNS, dEW), System.Math.Min(rLoop, dPlaza)), System.Math.Min(dBL, dBR));
        return (float)System.Math.Clamp(1.0 - (dMin - 2.6) / 2.2, 0.0, 1.0);
    }

    public static float MudFactor(double x, double z)
    {
        double n = System.Math.Sin(x * 0.075 + 1.1) * System.Math.Cos(z * 0.068 - 0.7) + 0.5 * System.Math.Sin((x + z) * 0.11);
        return (float)(System.Math.Clamp((n - 0.28) * 1.35, 0.0, 1.0) * (1.0 - RoadFactor(x, z) * 0.65));
    }

    public static float TerrainHeight(double x, double z)
    {
        double yardDist = System.Math.Sqrt(x * x + (z + 16.0) * (z + 16.0));
        double yardFlat = System.Math.Clamp((yardDist - 18.0) / 10.0, 0.0, 1.0);
        double h = (System.Math.Sin(x * 0.036) * System.Math.Cos(z * 0.032) * 1.45
                  + System.Math.Sin(x * 0.082 + 0.9) * System.Math.Sin(z * 0.076) * 0.42) * yardFlat;

        double edge = System.Math.Max(0.0, (System.Math.Max(System.Math.Abs(x), System.Math.Abs(z)) - 86.0) / 22.0);
        h += edge * edge * 6.5;

        double dCanal = System.Math.Abs(z - CanalZ);
        if (dCanal < 4.6)
        {
            double k = System.Math.Cos((dCanal / 4.6) * System.Math.PI * 0.5);
            h -= k * k * 1.85;
        }
        return (float)h;
    }

    public static float SurfaceHeight(float x, float z)
    {
        if ((MathF.Abs(x + 28f) < 2.2f || MathF.Abs(x - 28f) < 2.2f) && MathF.Abs(z - CanalZ) < 4.3f)
        {
            float dz = z - CanalZ;
            return TerrainHeight(x, CanalZ - 4.7) + 0.52f * (1f - (dz / 4.2f) * (dz / 4.2f)) + 0.32f;
        }
        return TerrainHeight(x, z);
    }

    /// <summary>
    /// Generates the exact same 180 oil palm tree coordinates & orientations as server/src/worldSpec.js!
    /// </summary>
    public static List<PalmTreeNode> GenerateTrees()
    {
        var rng = CreateMulberry32(WorldSeed);
        var trees = new List<PalmTreeNode>(180);
        for (double gx = -94.0; gx <= 94.0 && trees.Count < 180; gx += 11.5)
        {
            for (double gz = -92.0; gz <= 94.0 && trees.Count < 180; gz += 11.5)
            {
                double x = System.Math.Round(gx + (rng() - 0.5) * 3.8, 2);
                double z = System.Math.Round(gz + (rng() - 0.5) * 3.8, 2);
                double rot = System.Math.Round(rng() * System.Math.PI * 2.0, 3);
                double scale = System.Math.Round(0.84 + rng() * 0.34, 3);
                if (System.Math.Sqrt(x * x + (z + 15.0) * (z + 15.0)) < 22.0) continue;
                if (System.Math.Abs(z - CanalZ) < 6.4) continue;
                if (RoadFactor(x, z) > 0.35f) continue;

                float y = (float)System.Math.Round(TerrainHeight(x, z), 2);
                trees.Add(new PalmTreeNode
                {
                    Id = trees.Count,
                    X = (float)x,
                    Y = y,
                    Z = (float)z,
                    RotationY = (float)rot,
                    Scale = (float)scale,
                    State = trees.Count % 13 == 0 ? 2 : 1,
                });
            }
        }
        return trees;
    }

    public static (List<StaticPropInstance> Ferns, List<StaticPropInstance> Rocks) GenerateScatterProps()
    {
        var rng = CreateMulberry32(991177u);
        var ferns = new List<StaticPropInstance>(160);
        var rocks = new List<StaticPropInstance>(42);

        for (int i = 0; i < 160; i++)
        {
            double x = (rng() - 0.5) * 190.0;
            double z = (rng() - 0.5) * 190.0;
            if (RoadFactor(x, z) > 0.3f || System.Math.Sqrt(x * x + (z + 15.0) * (z + 15.0)) < 18.0) continue;
            ferns.Add(new StaticPropInstance { X = (float)x, Y = TerrainHeight(x, z) - 0.05f, Z = (float)z, RotY = (float)(rng() * 6.283), Scale = (float)(0.75 + rng() * 0.55) });
        }
        for (int i = 0; i < 42; i++)
        {
            double x = (rng() - 0.5) * 195.0;
            double z = (rng() - 0.5) * 195.0;
            if (RoadFactor(x, z) > 0.25f || System.Math.Sqrt(x * x + (z + 15.0) * (z + 15.0)) < 20.0) continue;
            rocks.Add(new StaticPropInstance { X = (float)x, Y = TerrainHeight(x, z) - 0.12f, Z = (float)z, RotY = (float)(rng() * 6.283), Scale = (float)(0.70 + rng() * 0.80) });
        }
        return (ferns, rocks);
    }

    public static MeshLodSlice BuildSplattedTerrainMesh(int grid = 128, float span = 224f)
    {
        byte[] vbuf = new byte[grid * grid * NpakArchive.VertexStrideBytes];
        using (var ms = new System.IO.MemoryStream(vbuf))
        using (var bw = new System.IO.BinaryWriter(ms))
        {
            for (int zi = 0; zi < grid; zi++)
            {
                float z = -span * 0.5f + (zi / (float)(grid - 1)) * span;
                for (int xi = 0; xi < grid; xi++)
                {
                    float x = -span * 0.5f + (xi / (float)(grid - 1)) * span;
                    float h = TerrainHeight(x, z);
                    float hx = TerrainHeight(x + 1.2f, z) - TerrainHeight(x - 1.2f, z);
                    float hz = TerrainHeight(x, z + 1.2f) - TerrainHeight(x, z - 1.2f);
                    float nx = -hx, ny = 2.4f, nz = -hz;
                    float nl = MathF.Sqrt(nx * nx + ny * ny + nz * nz);
                    nx /= nl; ny /= nl; nz /= nl;

                    float rd = RoadFactor(x, z);
                    float md = MudFactor(x, z);
                    float yard = System.Math.Clamp(1f - (MathF.Sqrt(x * x + (z + 15f) * (z + 15f)) - 14f) / 5f, 0f, 1f);
                    float checker = (((int)MathF.Floor(x * 0.25f) + (int)MathF.Floor(z * 0.25f)) & 1) * 0.06f;

                    float r = 56f + checker * 180f, g = 118f + checker * 160f, b = 46f + checker * 80f;
                    r = r * (1f - md) + 92f * md; g = g * (1f - md) + 64f * md; b = b * (1f - md) + 42f * md;
                    r = r * (1f - rd) + 168f * rd; g = g * (1f - rd) + 114f * rd; b = b * (1f - rd) + 74f * rd;
                    r = r * (1f - yard) + 132f * yard; g = g * (1f - yard) + 138f * yard; b = b * (1f - yard) + 142f * yard;

                    bw.Write(x); bw.Write(h); bw.Write(z);
                    bw.Write(nx); bw.Write(ny); bw.Write(nz);
                    bw.Write(0.1f); bw.Write(0.1f);
                    bw.Write((byte)System.Math.Clamp((int)r, 0, 255));
                    bw.Write((byte)System.Math.Clamp((int)g, 0, 255));
                    bw.Write((byte)System.Math.Clamp((int)b, 0, 255));
                    bw.Write((byte)245);
                }
            }
        }

        int triCount = (grid - 1) * (grid - 1) * 6;
        byte[] ibuf = new byte[triCount * sizeof(ushort)];
        using (var ims = new System.IO.MemoryStream(ibuf))
        using (var ibw = new System.IO.BinaryWriter(ims))
        {
            for (int zi = 0; zi < grid - 1; zi++)
            {
                for (int xi = 0; xi < grid - 1; xi++)
                {
                    ushort i0 = (ushort)(zi * grid + xi);
                    ushort i1 = (ushort)(i0 + 1);
                    ushort i2 = (ushort)(i0 + grid);
                    ushort i3 = (ushort)(i2 + 1);
                    ibw.Write(i0); ibw.Write(i2); ibw.Write(i1);
                    ibw.Write(i1); ibw.Write(i2); ibw.Write(i3);
                }
            }
        }
        return new MeshLodSlice { VertexCount = grid * grid, IndexCount = triCount, VertexStream = vbuf, IndexStream = ibuf };
    }

    public static MeshLodSlice BuildCanalWaterMesh()
    {
        byte[] vbuf = new byte[4 * NpakArchive.VertexStrideBytes];
        (float x, float z)[] pts = [(-112f, CanalZ - 4.4f), (112f, CanalZ - 4.4f), (-112f, CanalZ + 4.4f), (112f, CanalZ + 4.4f)];
        using (var ms = new System.IO.MemoryStream(vbuf))
        using (var bw = new System.IO.BinaryWriter(ms))
        {
            foreach (var (x, z) in pts)
            {
                bw.Write(x); bw.Write(-0.82f); bw.Write(z);
                bw.Write(0f); bw.Write(1f); bw.Write(0f);
                bw.Write(0.1f); bw.Write(0.1f);
                bw.Write((byte)34); bw.Write((byte)132); bw.Write((byte)148); bw.Write((byte)255);
            }
        }
        byte[] ibuf = new byte[6 * sizeof(ushort)];
        Buffer.BlockCopy(new ushort[] { 0, 2, 1, 1, 2, 3 }, 0, ibuf, 0, ibuf.Length);
        return new MeshLodSlice { VertexCount = 4, IndexCount = 6, VertexStream = vbuf, IndexStream = ibuf };
    }
}
