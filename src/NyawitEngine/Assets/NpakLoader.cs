using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace NyawitEngine.Assets;

public static class MeshCatalog
{
    public const string PalmTrunk = "palm_trunk";
    public const string PalmCrown = "palm_crown";
    public const string TbsBunch = "tbs_bunch";
    public const string TropicalFern = "tropical_fern";
    public const string RockBoulder = "rock_boulder";
    public const string CanterTruckBody = "canter_truck_body";
    public const string CanterSteeringWheel = "canter_steering_wheel";
    public const string TruckWheel = "truck_wheel";
    public const string TruckCargoHeap = "truck_cargo_heap";
    public const string AngkongCart = "angkong_cart";
    public const string PksFactory = "pks_factory";
    public const string PksFan = "pks_fan";
    public const string SteamPuff = "steam_puff";
    public const string WeighbridgeRam = "weighbridge_ram";
    public const string MandorPost = "mandor_post";
    public const string WoodenBridge = "wooden_bridge";
    public const string GarageShowroom = "garage_showroom";
    public const string VfxPuffQuad = "vfx_puff_quad";
    public const string CelengBoar = "celeng_boar";
    public const string BoarLeg = "boar_leg";
    public const string CharTorsoHead = "char_torso_head";
    public const string CharHead = "char_head";
    public const string CharArm = "char_arm";
    public const string CharForearmHand = "char_forearm_hand";
    public const string CharLeg = "char_leg";
    public const string CharCalfBoot = "char_calf_boot";

    public const string HatCaping = "hat_caping";
    public const string HatSafety = "hat_safety";
    public const string HatHeadband = "hat_headband";
    public const string HatCowboy = "hat_cowboy";
    public const string HatCrownGold = "hat_crown_gold";

    public const string AccGlasses = "acc_glasses";
    public const string AccParangWaist = "acc_parang_waist";

    public const string BackBasket = "back_basket";
    public const string BackPack = "back_pack";
    public const string BackCape = "back_cape";
    public const string BackWingsGold = "back_wings_gold";

    public const string ToolEgrek = "tool_egrek";
    public const string ToolDodos = "tool_dodos";
    public const string ToolTojok = "tool_tojok";
    public const string ToolEgrekDragon = "tool_egrek_dragon";

    public static readonly string[] AllRequiredNames =
    [
        PalmTrunk, PalmCrown, TbsBunch, TropicalFern, RockBoulder,
        CanterTruckBody, CanterSteeringWheel, TruckWheel, TruckCargoHeap, AngkongCart,
        PksFactory, PksFan, SteamPuff, WeighbridgeRam, MandorPost, WoodenBridge,
        GarageShowroom, VfxPuffQuad, CelengBoar, BoarLeg,
        CharTorsoHead, CharHead, CharArm, CharForearmHand, CharLeg, CharCalfBoot,
        HatCaping, HatSafety, HatHeadband, HatCowboy, HatCrownGold,
        AccGlasses, AccParangWaist,
        BackBasket, BackPack, BackCape, BackWingsGold,
        ToolEgrek, ToolDodos, ToolTojok, ToolEgrekDragon
    ];
}

public sealed class MeshLodSlice
{
    public int VertexCount { get; init; }
    public int IndexCount { get; init; }
    public byte[] VertexStream { get; init; } = [];
    public byte[] IndexStream { get; init; } = [];
}

public sealed class NpakMeshAsset
{
    public string Name { get; init; } = "";
    public float BoundingRadius { get; init; }
    public MeshLodSlice[] Lods { get; init; } = [];
}

public sealed class NpakArchive
{
    public const int VertexStrideBytes = 36;
    private readonly Dictionary<string, NpakMeshAsset> _meshes = new(StringComparer.Ordinal);
    public IReadOnlyDictionary<string, NpakMeshAsset> Meshes => _meshes;

    public static NpakArchive Load(Stream stream)
    {
        using var br = new BinaryReader(stream, Encoding.UTF8, leaveOpen: true);
        string magic = Encoding.ASCII.GetString(br.ReadBytes(4));
        if (magic != "NPAK") throw new InvalidDataException($"Invalid NPAK header: {magic}");
        uint version = br.ReadUInt32();
        if (version != 1) throw new InvalidDataException($"Unsupported NPAK version: {version}");
        uint count = br.ReadUInt32();

        var archive = new NpakArchive();
        for (uint i = 0; i < count; i++)
        {
            byte nameLen = br.ReadByte();
            float radius = br.ReadSingle();
            _ = br.ReadSingle(); _ = br.ReadSingle(); _ = br.ReadSingle();
            _ = br.ReadSingle(); _ = br.ReadSingle(); _ = br.ReadSingle();
            byte lodCount = br.ReadByte();
            string name = Encoding.UTF8.GetString(br.ReadBytes(nameLen));

            var lods = new MeshLodSlice[lodCount];
            for (int l = 0; l < lodCount; l++)
            {
                int vcnt = (int)br.ReadUInt32();
                int icnt = (int)br.ReadUInt32();
                byte[] vBytes = br.ReadBytes(vcnt * VertexStrideBytes);
                byte[] iBytes = br.ReadBytes(icnt * sizeof(ushort));
                lods[l] = new MeshLodSlice
                {
                    VertexCount = vcnt,
                    IndexCount = icnt,
                    VertexStream = vBytes,
                    IndexStream = iBytes,
                };
            }
            archive._meshes[name] = new NpakMeshAsset { Name = name, BoundingRadius = radius, Lods = lods };
        }
        return archive;
    }
}
