using System;
using System.Collections.Generic;

namespace NyawitEngine.Core;

/// <summary>
/// Free Fire-inspired adaptive mobile graphics tier & dynamic frame-time governor.
/// Automatically down-shifts render scale and foliage range on low-end GPUs ("HP Kentang")
/// to keep frame rates silky smooth at 60+ FPS, while unlocking full detail on flagship GPUs.
/// </summary>
public enum GraphicsPreset
{
    Smooth = 0,     // HP Kentang: 0.62x res scale, aggressive LOD0=16m, no undergrowth ferns -> ultra fast 60 FPS!
    Standard = 1,   // Balanced:   0.80x res scale, LOD0=25m, ferns ON
    Ultra = 2,      // High:       1.00x res scale, LOD0=36m, full foliage & particles
    MaxHD = 3       // Flagship:   native 1.00x + extended horizon LOD0=50m, 4x MSAA candidate
}

public sealed class QualityProfile
{
    public GraphicsPreset Preset { get; init; }
    public string Label { get; init; } = "ULTRA";
    public float RenderScale { get; init; }
    public float Lod0Distance { get; init; }
    public float Lod1Distance { get; init; }
    public float MaxDrawDistance { get; init; }
    public bool DrawUndergrowthFerns { get; init; }
    public int MaxFallingFruits { get; init; }

    public static readonly QualityProfile[] All =
    [
        new() { Preset = GraphicsPreset.Smooth,   Label = "SMOOTH", RenderScale = 0.62f, Lod0Distance = 16f, Lod1Distance = 38f, MaxDrawDistance = 98f,  DrawUndergrowthFerns = false, MaxFallingFruits = 10 },
        new() { Preset = GraphicsPreset.Standard, Label = "STD",    RenderScale = 0.80f, Lod0Distance = 25f, Lod1Distance = 56f, MaxDrawDistance = 132f, DrawUndergrowthFerns = true,  MaxFallingFruits = 18 },
        new() { Preset = GraphicsPreset.Ultra,    Label = "ULTRA",  RenderScale = 1.00f, Lod0Distance = 36f, Lod1Distance = 78f, MaxDrawDistance = 168f, DrawUndergrowthFerns = true,  MaxFallingFruits = 28 },
        new() { Preset = GraphicsPreset.MaxHD,    Label = "MAX HD", RenderScale = 1.00f, Lod0Distance = 50f, Lod1Distance = 108f, MaxDrawDistance = 205f, DrawUndergrowthFerns = true, MaxFallingFruits = 40 },
    ];
}

public enum ShadowQualityTier
{
    Off = 0,
    Medium = 1,
    High = 2
}

public enum AtmospherePreset
{
    SemiEnbCold = 0,   // Cool Cinematic Semi-ENB Dingin (Default)
    KarhutlaSmoke = 1, // Sumatra/Riau Kabut Asap Karhutla Peatland Haze
    TropicalSunny = 2  // Classic Equatorial Plantation Sun
}

public enum AnimeOutlineTier
{
    Off = 0,
    Subtle = 1,
    Bold = 2           // Crisp Anime Silhouette + Crease Ink Outlines (Default)
}

public sealed class QualityGovernor
{
    public GraphicsPreset CurrentPreset { get; private set; } = GraphicsPreset.Ultra;
    public bool AutoStepDownEnabled { get; set; } = true;
    public int TargetFps { get; set; } = 60;
    public ShadowQualityTier ShadowTier { get; set; } = ShadowQualityTier.High;
    public AtmospherePreset Atmosphere { get; set; } = AtmospherePreset.SemiEnbCold;
    public AnimeOutlineTier OutlineTier { get; set; } = AnimeOutlineTier.Bold;
    public bool CloudsEnabled { get; set; } = true;
    public bool ParticlesEnabled { get; set; } = true;
    public bool ShowFpsHud { get; set; } = true;
    public float? CustomRenderScale { get; set; }
    public int CurrentFps { get; private set; } = 60;
    public float AvgFrameMs { get; private set; } = 16.6f;

    private float _accumSec;
    private int _frames;
    private int _lowFpsStrikes;

    public QualityProfile Active => QualityProfile.All[(int)CurrentPreset];
    public float EffectiveRenderScale => CustomRenderScale ?? Active.RenderScale;

    public void SetManualPreset(GraphicsPreset preset, bool disableAuto = true)
    {
        CurrentPreset = preset;
        CustomRenderScale = null;
        ShadowTier = preset switch
        {
            GraphicsPreset.Smooth => ShadowQualityTier.Off,
            GraphicsPreset.Standard => ShadowQualityTier.Medium,
            _ => ShadowQualityTier.High,
        };
        OutlineTier = preset == GraphicsPreset.Smooth ? AnimeOutlineTier.Subtle : AnimeOutlineTier.Bold;
        CloudsEnabled = preset != GraphicsPreset.Smooth;
        ParticlesEnabled = preset != GraphicsPreset.Smooth;
        if (disableAuto) AutoStepDownEnabled = false;
        _lowFpsStrikes = 0;
    }

    public bool RecordFrame(float dtSeconds)
    {
        _accumSec += dtSeconds;
        _frames++;
        if (_accumSec < 0.5f) return false;

        CurrentFps = (int)System.Math.Round(_frames / _accumSec);
        AvgFrameMs = (_accumSec / _frames) * 1000f;
        _accumSec = 0f;
        _frames = 0;

        if (AutoStepDownEnabled && CurrentFps < 34 && CurrentPreset > GraphicsPreset.Smooth)
        {
            _lowFpsStrikes++;
            if (_lowFpsStrikes >= 3)
            {
                CurrentPreset = (GraphicsPreset)((int)CurrentPreset - 1);
                if (ShadowTier > ShadowQualityTier.Medium)
                    ShadowTier = ShadowQualityTier.Medium;
                _lowFpsStrikes = 0;
                return true;
            }
        }
        else
        {
            _lowFpsStrikes = 0;
        }
        return false;
    }
}

public static class Time
{
    public static float DeltaTime { get; set; } = 0.016f;
    public static float TotalTime { get; set; }
    public static long FrameCount { get; set; }
}

public sealed class Transform
{
    public float PosX, PosY, PosZ;
    public float RotX, RotY, RotZ;
    public float ScaleX = 1f, ScaleY = 1f, ScaleZ = 1f;

    public void SetPosition(float x, float y, float z) { PosX = x; PosY = y; PosZ = z; }
    public void SetUniformScale(float s) { ScaleX = s; ScaleY = s; ScaleZ = s; }
}

public abstract class Component
{
    public GameObject GameObject { get; internal set; } = null!;
    public Transform Transform => GameObject.Transform;
    public bool Enabled { get; set; } = true;
}

/// <summary>
/// Unity-inspired C# Gameplay Scripting base class (`Awake`, `Start`, `Update`, `LateUpdate`).
/// Zero reflection overhead — virtual dispatch on a pre-allocated component list.
/// </summary>
public abstract class MonoBehaviour : Component
{
    internal bool Started;
    public virtual void Awake() { }
    public virtual void Start() { }
    public virtual void Update(float dt) { }
    public virtual void LateUpdate(float dt) { }
}

public sealed class GameObject
{
    public string Name { get; set; }
    public string Tag { get; set; } = "Untagged";
    public bool ActiveSelf { get; set; } = true;
    public Transform Transform { get; } = new();
    private readonly List<Component> _components = new(4);

    public GameObject(string name) => Name = name;

    public T AddComponent<T>() where T : Component, new()
    {
        var c = new T { GameObject = this };
        _components.Add(c);
        if (c is MonoBehaviour mb) mb.Awake();
        return c;
    }

    public T? GetComponent<T>() where T : Component
    {
        for (int i = 0; i < _components.Count; i++)
            if (_components[i] is T match) return match;
        return null;
    }

    internal void TickBehaviours(float dt, bool late)
    {
        if (!ActiveSelf) return;
        for (int i = 0; i < _components.Count; i++)
        {
            if (_components[i] is MonoBehaviour mb && mb.Enabled)
            {
                if (!mb.Started) { mb.Started = true; mb.Start(); }
                if (late) mb.LateUpdate(dt);
                else mb.Update(dt);
            }
        }
    }
}

public sealed class Scene
{
    public string Name { get; }
    private readonly List<GameObject> _objects = new(64);

    public Scene(string name) => Name = name;
    public IReadOnlyList<GameObject> Objects => _objects;

    public GameObject CreateGameObject(string name)
    {
        var go = new GameObject(name);
        _objects.Add(go);
        return go;
    }

    public void StepFrame(float rawDtSeconds)
    {
        float dt = System.Math.Clamp(rawDtSeconds, 0.0005f, 0.05f);
        Time.DeltaTime = dt;
        Time.TotalTime += dt;
        Time.FrameCount++;

        for (int i = 0; i < _objects.Count; i++) _objects[i].TickBehaviours(dt, late: false);
        for (int i = 0; i < _objects.Count; i++) _objects[i].TickBehaviours(dt, late: true);
    }
}
