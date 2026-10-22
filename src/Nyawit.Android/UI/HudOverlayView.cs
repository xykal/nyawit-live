using System;
using System.Collections.Generic;
using Android.Content;
using Android.Graphics;
using Path = global::Android.Graphics.Path;
using Android.Runtime;
using Android.Views;
using Nyawit.AndroidClient.Audio;
using Nyawit.AndroidClient.Rendering;
using NyawitEngine.Assets;
using NyawitEngine.Core;
using NyawitEngine.Network;
using NyawitEngine.Physics;
using NyawitEngine.World;

namespace Nyawit.AndroidClient.UI;

public enum VectorIconKind : byte
{
    None = 0,
    HarvestSickle = 1,
    PickupTbs = 2,
    LoadTruck = 3,
    Angkong = 4,
    CanterTruck = 5,
    SteeringWheel = 6,
    SellPks = 7,
    BasuriHorn = 8,
    MicOn = 9,
    MicMuted = 10,
    ChatBox = 11,
    Trophy = 12,
    AvatarHelm = 13,
    DailyCrate = 14,
    ShareNodes = 15,
    LobbyGrid = 16,
    PlayChevron = 17,
    SettingsGear = 18,
    CloseCross = 19,
}

public enum ActiveModalOverlay : byte
{
    None = 0,
    Settings = 1,      // Pengaturan Sistem, Grafik, Frame Rate (30/60/90/120), Bayangan, Awan, Partikel & Audio!
    Wardrobe = 2,      // Lemari Pakaian & Aksesoris Pemanen Lengkap!
    SocialRoom = 3,    // Server Live, Room Kebun & Quick Chat!
    Ranking = 4,       // Papan Peringkat & Turnamen Mingguan!
    DailyReward = 5,   // Absensi & Bonus Harian!
}

/// <summary>
/// NyawitEngine v4.0 Precision Anti-Lag Custom Game UI &amp; Modal System:
///   - ZERO stock Android widgets / AlertDialogs / ActionBars anywhere
///   - Pre-allocated zero-GC Paint/Path/HitZone buffers + throttled 6 Hz passive UI refresh during gameplay (-> 60-120 FPS!)
///   - Screen 0: Custom XyVerse + Nyawit Live Boot Splash Screen
///   - Screen 1: Dedicated Separate 3D Garage Showroom Lobby UI + 360-deg Touch Orbit
///   - Screen 2: Dedicated Full-Screen "MENYIAPKAN DUNIA" Loading Screen
///   - Screen 3: Uncluttered Precision Gameplay HUD + Full Custom In-Game PENGATURAN Modal
/// </summary>
public sealed class HudOverlayView : View
{
    private struct HitZoneSlot
    {
        public float L, T, R, B;
        public Action? Callback;
    }

    private readonly Gles3InstancedRenderer? _renderer;
    private readonly LiveMultiplayerSession? _net;
    private readonly ProceduralSfxPlayer? _sfx;
    private readonly VoiceChatManager? _voice;
    private readonly Typeface _displayFont = Typeface.DefaultBold!;
    private readonly Typeface _uiBoldFont = Typeface.Create("sans-serif-condensed", TypefaceStyle.Bold) ?? Typeface.DefaultBold!;
    private readonly Bitmap? _brandSmallMark;
    private readonly Bitmap? _brandWideLogo;

    private readonly Paint _fillPaint = new(PaintFlags.AntiAlias);
    private readonly Paint _strokePaint = new(PaintFlags.AntiAlias);
    private readonly Paint _iconPaint = new(PaintFlags.AntiAlias);
    private readonly Paint _textPaint = new(PaintFlags.AntiAlias);
    private readonly Paint _titlePaint = new(PaintFlags.AntiAlias);
    private readonly Path _tmpPath = new();
    private readonly Path _iconPath = new();
    private readonly Rect _srcRect = new();
    private readonly RectF _dstRect = new();

    private readonly HitZoneSlot[] _hitZones = new HitZoneSlot[64];
    private int _hitCount;

    private int _joyPointerId = -1;
    private float _joyOriginX, _joyOriginY, _joyKnobX, _joyKnobY;
    private int _camPointerId = -1;
    private float _camLastX, _camLastY;

    private string _toastText = "";
    private long _toastUntilMs;

    public ActiveModalOverlay ActiveModal { get; private set; } = ActiveModalOverlay.None;
    public int SettingsTabIndex { get; set; } // 0 = GRAFIK & FPS, 1 = VISUAL & BAYANGAN, 2 = AUDIO & KONTROL

    private readonly List<LeaderboardRow> _leaderCache = new(16);
    private readonly List<RoomDescriptor> _roomsCache = new(8);
    private readonly List<RemotePeerState> _peersTmp = new(4);
    private readonly List<BoarNetState> _boarsTmp = new(2);
    private readonly List<ChatMessageEntry> _chatsTmp = new(32);

    // Pre-allocated modal tab actions (zero closure allocation per frame!)
    private Action[] _tabActions = [];

    public RectF LastEnterWorldButtonRect { get; private set; } = new();
    public RectF LastPickupOrLoadButtonRect { get; private set; } = new();
    public RectF LastHarvestButtonRect { get; private set; } = new();
    public RectF LastTruckButtonRect { get; private set; } = new();

    public event Action? OnEnterWorldRequested;
    public event Action? OnReturnLobbyRequested;
    public event Action? OnToggleVoiceMic;
    public event Action<int>? OnTargetFpsSelected;
    public event Action? OnCustomChatInputRequested;
    public event Action? OnRenamePlayerRequested;
    public event Action? OnHarvestPressed;
    public event Action? OnPickupOrLoadPressed;
    public event Action? OnAngkongTogglePressed;
    public event Action? OnSellPressed;
    public event Action? OnTruckTogglePressed;
    public event Action? OnHornPressed;
    public event Action? OnProfileModified;

    private static readonly string[] HatCycle = [MeshCatalog.HatCaping, MeshCatalog.HatSafety, MeshCatalog.HatHeadband, MeshCatalog.HatCowboy, MeshCatalog.HatCrownGold];
    private static readonly string[] HatLabels = ["CAPING BAMBU", "HELM PROYEK", "IKAT KEPALA", "TOPI MANDOR", "MAHKOTA SULTAN"];
    private static readonly string[] BackCycle = [MeshCatalog.BackBasket, MeshCatalog.BackPack, MeshCatalog.BackCape, MeshCatalog.BackWingsGold, "none"];
    private static readonly string[] BackLabels = ["KERANJANG ROTAN", "RANSEL TAKTIS", "JUBAH SAWIT", "SAYAP EMAS", "TANPA TAS"];
    private static readonly string[] ToolCycle = [MeshCatalog.ToolEgrek, MeshCatalog.ToolDodos, MeshCatalog.ToolTojok, MeshCatalog.ToolEgrekDragon];
    private static readonly string[] ToolLabels = ["EGREK BAJA", "DODOS LEBAR", "TOJOK SAWIT", "EGREK NAGA"];
    private static readonly string[] ColorHexCycle = ["#27AE60", "#2563EB", "#DC2626", "#D97706", "#1E293B"];
    private static readonly string[] ColorNameCycle = ["HIJAU KEBUN", "BIRU PROYEK", "MERAH BERANI", "EMAS MANDOR", "HITAM TAKTIS"];

    public HudOverlayView(IntPtr javaReference, JniHandleOwnership transfer)
        : base(javaReference, transfer)
    {
    }

    public HudOverlayView(
        Context context,
        Gles3InstancedRenderer renderer,
        LiveMultiplayerSession net,
        ProceduralSfxPlayer sfx,
        VoiceChatManager voice,
        Typeface displayFont,
        Bitmap? brandSmallMark,
        Bitmap? brandWideLogo = null)
        : base(context)
    {
        _renderer = renderer;
        _net = net;
        _sfx = sfx;
        _voice = voice;
        _displayFont = displayFont;
        _brandSmallMark = brandSmallMark;
        _brandWideLogo = brandWideLogo;

        _strokePaint.SetStyle(Paint.Style.Stroke);
        _iconPaint.SetStyle(Paint.Style.Stroke);
        _iconPaint.StrokeCap = Paint.Cap.Square;
        _iconPaint.StrokeJoin = Paint.Join.Miter;
        _textPaint.SetTypeface(_uiBoldFont);
        _titlePaint.SetTypeface(_displayFont);

        _tabActions =
        [
            () => { _sfx?.Play("ui_click"); SettingsTabIndex = 0; PostInvalidate(); },
            () => { _sfx?.Play("ui_click"); SettingsTabIndex = 1; PostInvalidate(); },
            () => { _sfx?.Play("ui_click"); SettingsTabIndex = 2; PostInvalidate(); },
        ];

        _renderer.OnStageChanged += () => PostInvalidate();
    }

    public void OpenModal(ActiveModalOverlay modal)
    {
        ActiveModal = modal;
        if (modal == ActiveModalOverlay.Ranking && _net != null)
        {
            _net.RefreshBoards();
            var snap = _net.GetBoardsSnapshot();
            lock (_leaderCache)
            {
                _leaderCache.Clear();
                _leaderCache.AddRange(snap.Weekly.Count > 0 ? snap.Weekly : snap.Global);
            }
        }
        else if (modal == ActiveModalOverlay.SocialRoom && _net != null)
        {
            _ = _net.RefreshRoomsFromServerAsync().ContinueWith(_ =>
            {
                lock (_roomsCache) { _roomsCache.Clear(); _roomsCache.AddRange(_net.GetRoomsSnapshot()); }
                PostInvalidate();
            });
        }
        PostInvalidate();
    }

    public void CloseModal()
    {
        if (ActiveModal == ActiveModalOverlay.None) return;
        ActiveModal = ActiveModalOverlay.None;
        PostInvalidate();
    }

    public void ShowToast(string text)
    {
        _toastText = text;
        _toastUntilMs = Java.Lang.JavaSystem.CurrentTimeMillis() + 2600L;
        PostInvalidate();
    }

    private void RegisterHit(float l, float t, float r, float b, Action cb)
    {
        if (_hitCount >= _hitZones.Length) return;
        _hitZones[_hitCount].L = l;
        _hitZones[_hitCount].T = t;
        _hitZones[_hitCount].R = r;
        _hitZones[_hitCount].B = b;
        _hitZones[_hitCount].Callback = cb;
        _hitCount++;
    }

    private float Dp(float v) => v * (Resources?.DisplayMetrics?.Density ?? 2.5f);

    private void BuildChamferRectPath(Path p, float l, float t, float r, float b, float cut)
    {
        p.Reset();
        float c = System.Math.Min(cut, System.Math.Min((r - l) * 0.25f, (b - t) * 0.25f));
        p.MoveTo(l + c, t);
        p.LineTo(r - c, t);
        p.LineTo(r, t + c);
        p.LineTo(r, b - c);
        p.LineTo(r - c, b);
        p.LineTo(l + c, b);
        p.LineTo(l, b - c);
        p.LineTo(l, t + c);
        p.Close();
    }

    private void DrawSharpPanel(Canvas canvas, float l, float t, float r, float b, Color fill, Color border, float cutDp = 7f, float strokeDp = 1.5f)
    {
        BuildChamferRectPath(_tmpPath, l, t, r, b, Dp(cutDp));
        _fillPaint.Color = fill;
        canvas.DrawPath(_tmpPath, _fillPaint);
        _strokePaint.Color = border;
        _strokePaint.StrokeWidth = Dp(strokeDp);
        canvas.DrawPath(_tmpPath, _strokePaint);
    }

    private void DrawSharpButton(
        Canvas canvas, float l, float t, float r, float b,
        string label, VectorIconKind icon,
        Color fill, Color border, Color textCol,
        Action onTap, float textSp = 10.5f, float cutDp = 7f)
    {
        DrawSharpPanel(canvas, l, t, r, b, fill, border, cutDp, 1.5f);
        float cx = (l + r) * 0.5f;
        float cy = (t + b) * 0.5f;
        float h = b - t;

        if (icon != VectorIconKind.None && string.IsNullOrEmpty(label))
        {
            DrawVectorIcon(canvas, icon, cx, cy, System.Math.Min(r - l, h) * 0.29f, textCol);
        }
        else if (icon != VectorIconKind.None && h >= Dp(50f))
        {
            DrawVectorIcon(canvas, icon, cx, t + h * 0.37f, System.Math.Min(r - l, h) * 0.21f, textCol);
            _textPaint.Color = textCol;
            _textPaint.TextSize = Dp(textSp);
            _textPaint.TextAlign = Paint.Align.Center;
            canvas.DrawText(label, cx, b - h * 0.16f, _textPaint);
        }
        else if (icon != VectorIconKind.None)
        {
            float iconR = h * 0.25f;
            DrawVectorIcon(canvas, icon, l + Dp(15f) + iconR * 0.45f, cy, iconR, textCol);
            _textPaint.Color = textCol;
            _textPaint.TextSize = Dp(textSp);
            _textPaint.TextAlign = Paint.Align.Left;
            canvas.DrawText(label, l + Dp(24f) + iconR * 1.15f, cy + Dp(textSp * 0.36f), _textPaint);
        }
        else
        {
            _textPaint.Color = textCol;
            _textPaint.TextSize = Dp(textSp);
            _textPaint.TextAlign = Paint.Align.Center;
            canvas.DrawText(label, cx, cy + Dp(textSp * 0.36f), _textPaint);
        }

        RegisterHit(l, t, r, b, onTap);
    }

    private void DrawVectorIcon(Canvas canvas, VectorIconKind kind, float cx, float cy, float r, Color col)
    {
        _iconPaint.Color = col;
        _iconPaint.StrokeWidth = System.Math.Max(Dp(1.75f), r * 0.14f);
        _iconPath.Reset();

        switch (kind)
        {
            case VectorIconKind.HarvestSickle:
                _iconPath.MoveTo(cx - r * 0.7f, cy + r * 0.8f);
                _iconPath.LineTo(cx + r * 0.15f, cy - r * 0.15f);
                _iconPath.QuadTo(cx + r * 0.85f, cy - r * 0.85f, cx - r * 0.1f, cy - r * 0.85f);
                canvas.DrawPath(_iconPath, _iconPaint);
                break;

            case VectorIconKind.PickupTbs:
                _iconPath.MoveTo(cx, cy - r * 0.8f);
                _iconPath.LineTo(cx + r * 0.7f, cy);
                _iconPath.LineTo(cx, cy + r * 0.8f);
                _iconPath.LineTo(cx - r * 0.7f, cy);
                _iconPath.Close();
                canvas.DrawPath(_iconPath, _iconPaint);
                canvas.DrawLine(cx, cy + r * 0.8f, cx, cy - r * 0.25f, _iconPaint);
                break;

            case VectorIconKind.LoadTruck:
                canvas.DrawRect(cx - r * 0.8f, cy + r * 0.15f, cx + r * 0.8f, cy + r * 0.75f, _iconPaint);
                canvas.DrawLine(cx, cy + r * 0.3f, cx, cy - r * 0.75f, _iconPaint);
                canvas.DrawLine(cx - r * 0.42f, cy - r * 0.32f, cx, cy - r * 0.75f, _iconPaint);
                canvas.DrawLine(cx + r * 0.42f, cy - r * 0.32f, cx, cy - r * 0.75f, _iconPaint);
                break;

            case VectorIconKind.Angkong:
                _iconPath.MoveTo(cx - r * 0.8f, cy - r * 0.3f);
                _iconPath.LineTo(cx + r * 0.35f, cy - r * 0.3f);
                _iconPath.LineTo(cx + r * 0.55f, cy + r * 0.25f);
                _iconPath.LineTo(cx - r * 0.5f, cy + r * 0.25f);
                _iconPath.Close();
                canvas.DrawPath(_iconPath, _iconPaint);
                canvas.DrawCircle(cx + r * 0.62f, cy + r * 0.52f, r * 0.24f, _iconPaint);
                canvas.DrawLine(cx - r * 0.5f, cy + r * 0.25f, cx - r * 0.9f, cy + r * 0.6f, _iconPaint);
                break;

            case VectorIconKind.CanterTruck:
                canvas.DrawRect(cx - r * 0.85f, cy - r * 0.35f, cx + r * 0.18f, cy + r * 0.35f, _iconPaint);
                _iconPath.MoveTo(cx + r * 0.18f, cy - r * 0.32f);
                _iconPath.LineTo(cx + r * 0.78f, cy - r * 0.28f);
                _iconPath.LineTo(cx + r * 0.85f, cy + r * 0.35f);
                _iconPath.LineTo(cx + r * 0.18f, cy + r * 0.35f);
                _iconPath.Close();
                canvas.DrawPath(_iconPath, _iconPaint);
                canvas.DrawCircle(cx - r * 0.45f, cy + r * 0.55f, r * 0.22f, _iconPaint);
                canvas.DrawCircle(cx + r * 0.50f, cy + r * 0.55f, r * 0.22f, _iconPaint);
                break;

            case VectorIconKind.SteeringWheel:
                canvas.DrawCircle(cx, cy, r * 0.78f, _iconPaint);
                canvas.DrawCircle(cx, cy, r * 0.22f, _iconPaint);
                canvas.DrawLine(cx - r * 0.75f, cy, cx + r * 0.75f, cy, _iconPaint);
                canvas.DrawLine(cx, cy + r * 0.22f, cx, cy + r * 0.78f, _iconPaint);
                break;

            case VectorIconKind.SellPks:
                _iconPath.MoveTo(cx - r * 0.75f, cy + r * 0.7f);
                _iconPath.LineTo(cx - r * 0.75f, cy - r * 0.15f);
                _iconPath.LineTo(cx - r * 0.15f, cy - r * 0.65f);
                _iconPath.LineTo(cx + r * 0.45f, cy - r * 0.15f);
                _iconPath.LineTo(cx + r * 0.45f, cy + r * 0.7f);
                _iconPath.Close();
                canvas.DrawPath(_iconPath, _iconPaint);
                canvas.DrawLine(cx + r * 0.68f, cy + r * 0.7f, cx + r * 0.68f, cy - r * 0.8f, _iconPaint);
                break;

            case VectorIconKind.BasuriHorn:
                _iconPath.MoveTo(cx - r * 0.75f, cy - r * 0.2f);
                _iconPath.LineTo(cx - r * 0.15f, cy - r * 0.2f);
                _iconPath.LineTo(cx + r * 0.55f, cy - r * 0.65f);
                _iconPath.LineTo(cx + r * 0.55f, cy + r * 0.65f);
                _iconPath.LineTo(cx - r * 0.15f, cy + r * 0.2f);
                _iconPath.LineTo(cx - r * 0.75f, cy + r * 0.2f);
                _iconPath.Close();
                canvas.DrawPath(_iconPath, _iconPaint);
                break;

            case VectorIconKind.MicOn:
            case VectorIconKind.MicMuted:
                canvas.DrawRect(cx - r * 0.28f, cy - r * 0.75f, cx + r * 0.28f, cy + r * 0.12f, _iconPaint);
                canvas.DrawLine(cx - r * 0.58f, cy, cx + r * 0.58f, cy, _iconPaint);
                canvas.DrawLine(cx, cy + r * 0.12f, cx, cy + r * 0.78f, _iconPaint);
                if (kind == VectorIconKind.MicMuted)
                    canvas.DrawLine(cx - r * 0.75f, cy - r * 0.75f, cx + r * 0.75f, cy + r * 0.75f, _iconPaint);
                break;

            case VectorIconKind.ChatBox:
                canvas.DrawRect(cx - r * 0.8f, cy - r * 0.65f, cx + r * 0.8f, cy + r * 0.35f, _iconPaint);
                canvas.DrawLine(cx - r * 0.45f, cy - r * 0.25f, cx + r * 0.45f, cy - r * 0.25f, _iconPaint);
                canvas.DrawLine(cx - r * 0.45f, cy + r * 0.05f, cx + r * 0.2f, cy + r * 0.05f, _iconPaint);
                break;

            case VectorIconKind.Trophy:
                canvas.DrawRect(cx - r * 0.5f, cy - r * 0.7f, cx + r * 0.5f, cy + r * 0.08f, _iconPaint);
                canvas.DrawLine(cx, cy + r * 0.08f, cx, cy + r * 0.68f, _iconPaint);
                canvas.DrawLine(cx - r * 0.48f, cy + r * 0.68f, cx + r * 0.48f, cy + r * 0.68f, _iconPaint);
                break;

            case VectorIconKind.AvatarHelm:
                _iconPath.MoveTo(cx - r * 0.85f, cy + r * 0.35f);
                _iconPath.LineTo(cx, cy - r * 0.65f);
                _iconPath.LineTo(cx + r * 0.85f, cy + r * 0.35f);
                _iconPath.Close();
                canvas.DrawPath(_iconPath, _iconPaint);
                break;

            case VectorIconKind.DailyCrate:
                canvas.DrawRect(cx - r * 0.72f, cy - r * 0.55f, cx + r * 0.72f, cy + r * 0.72f, _iconPaint);
                canvas.DrawLine(cx, cy - r * 0.55f, cx, cy + r * 0.72f, _iconPaint);
                canvas.DrawLine(cx - r * 0.72f, cy, cx + r * 0.72f, cy, _iconPaint);
                break;

            case VectorIconKind.LobbyGrid:
                canvas.DrawRect(cx - r * 0.72f, cy - r * 0.72f, cx - r * 0.1f, cy - r * 0.1f, _iconPaint);
                canvas.DrawRect(cx + r * 0.1f, cy - r * 0.72f, cx + r * 0.72f, cy - r * 0.1f, _iconPaint);
                canvas.DrawRect(cx - r * 0.72f, cy + r * 0.1f, cx - r * 0.1f, cy + r * 0.72f, _iconPaint);
                canvas.DrawRect(cx + r * 0.1f, cy + r * 0.1f, cx + r * 0.72f, cy + r * 0.72f, _iconPaint);
                break;

            case VectorIconKind.PlayChevron:
                _iconPath.MoveTo(cx - r * 0.45f, cy - r * 0.72f);
                _iconPath.LineTo(cx + r * 0.68f, cy);
                _iconPath.LineTo(cx - r * 0.45f, cy + r * 0.72f);
                _iconPath.Close();
                canvas.DrawPath(_iconPath, _iconPaint);
                break;

            case VectorIconKind.SettingsGear:
                canvas.DrawCircle(cx, cy, r * 0.38f, _iconPaint);
                for (int k = 0; k < 8; k++)
                {
                    float a = k * 0.785398f;
                    float ca = MathF.Cos(a), sa = MathF.Sin(a);
                    canvas.DrawLine(cx + ca * r * 0.50f, cy + sa * r * 0.50f, cx + ca * r * 0.86f, cy + sa * r * 0.86f, _iconPaint);
                }
                break;

            case VectorIconKind.CloseCross:
                canvas.DrawLine(cx - r * 0.65f, cy - r * 0.65f, cx + r * 0.65f, cy + r * 0.65f, _iconPaint);
                canvas.DrawLine(cx + r * 0.65f, cy - r * 0.65f, cx - r * 0.65f, cy + r * 0.65f, _iconPaint);
                break;
        }
    }

    private int GetEffectiveViewportWidth() => Width;

    protected override void OnDraw(Canvas? canvas)
    {
        if (canvas == null) return;
        base.OnDraw(canvas);
        if (_renderer == null || _net == null) return;

        _hitCount = 0;
        int w = GetEffectiveViewportWidth(), h = Height;
        if (w <= 0 || h <= 0) return;

        if (_renderer.Stage == AppSceneStage.Splash)
        {
            DrawBootSplashScreen(canvas, w, h);
            PostInvalidateDelayed(33);
            return;
        }

        if (_renderer.Stage == AppSceneStage.PreparingWorld)
        {
            DrawWorldLoadingScreen(canvas, w, h);
            PostInvalidateDelayed(33);
            return;
        }

        if (_renderer.Stage == AppSceneStage.Lobby)
        {
            DrawSeparateGarageLobbyUi(canvas, w, h);
        }
        else
        {
            DrawGameplayHud(canvas, w, h);
        }

        if (ActiveModal != ActiveModalOverlay.None)
        {
            DrawActiveModalOverlay(canvas, w, h);
        }

        long nowMs = Java.Lang.JavaSystem.CurrentTimeMillis();
        if (nowMs < _toastUntilMs && !string.IsNullOrEmpty(_toastText))
        {
            float tw = System.Math.Min(w * 0.58f, Dp(460f));
            float tl = (w - tw) * 0.5f, tt = Dp(58f);
            DrawSharpPanel(canvas, tl, tt, tl + tw, tt + Dp(34f),
                Color.Argb(232, 10, 20, 18), Color.Argb(245, 74, 222, 128), 6f, 1.5f);
            _textPaint.Color = Color.White;
            _textPaint.TextSize = Dp(10.5f);
            _textPaint.TextAlign = Paint.Align.Center;
            canvas.DrawText(_toastText, w * 0.5f, tt + Dp(21f), _textPaint);
        }

        // Anti-Lag UI Refresh Governor:
        // Active joystick/toast refreshes smoothly at 20 Hz; idle HUD refreshes passively at 6 Hz (zero GPU overdraw choke!)
        long nextDelay = (_joyPointerId != -1 || nowMs < _toastUntilMs) ? 50L : 170L;
        PostInvalidateDelayed(nextDelay);
    }

    private void DrawBootSplashScreen(Canvas canvas, int w, int h)
    {
        _fillPaint.Color = Color.Argb(255, 9, 11, 13);
        canvas.DrawRect(0, 0, w, h, _fillPaint);

        // Crisp subtle architectural border lines
        _strokePaint.Color = Color.Argb(70, 52, 211, 153);
        _strokePaint.StrokeWidth = Dp(1.2f);
        canvas.DrawRect(Dp(20f), Dp(18f), w - Dp(20f), h - Dp(18f), _strokePaint);

        float centerY = h * 0.44f;
        if (_brandWideLogo != null)
        {
            float logoH = Dp(44f);
            float logoW = _brandWideLogo.Width * (logoH / _brandWideLogo.Height);
            _srcRect.Set(0, 0, _brandWideLogo.Width, _brandWideLogo.Height);
            _dstRect.Set((w - logoW) * 0.5f, centerY - Dp(82f), (w + logoW) * 0.5f, centerY - Dp(82f) + logoH);
            canvas.DrawBitmap(_brandWideLogo, _srcRect, _dstRect, null);
        }

        _titlePaint.Color = Color.White;
        _titlePaint.TextSize = Dp(38f);
        _titlePaint.TextAlign = Paint.Align.Center;
        canvas.DrawText("NYAWIT LIVE", w * 0.5f, centerY + Dp(6f), _titlePaint);

        _textPaint.Color = Color.Argb(235, 74, 222, 128);
        _textPaint.TextSize = Dp(11.5f);
        _textPaint.TextAlign = Paint.Align.Center;
        canvas.DrawText("SIMULASI KEBUN SAWIT & TRUK CANTER PBR MULTIPLAYER", w * 0.5f, centerY + Dp(32f), _textPaint);

        // Precision chamfered progress bar
        float barW = System.Math.Min(w * 0.46f, Dp(410f));
        float bl = (w - barW) * 0.5f, bt = h * 0.72f, bb = bt + Dp(12f);
        DrawSharpPanel(canvas, bl, bt, bl + barW, bb, Color.Argb(255, 18, 25, 30), Color.Argb(180, 52, 211, 153), 4f, 1.2f);

        float fillW = System.Math.Max(Dp(12f), (barW - Dp(4f)) * System.Math.Clamp(_renderer!.SplashProgress, 0.04f, 1f));
        _fillPaint.Color = Color.Argb(255, 34, 197, 94);
        canvas.DrawRect(bl + Dp(2f), bt + Dp(2f), bl + Dp(2f) + fillW, bb - Dp(2f), _fillPaint);

        _textPaint.Color = Color.Argb(205, 190, 210, 218);
        _textPaint.TextSize = Dp(10f);
        canvas.DrawText(_renderer.SplashStatus, w * 0.5f, bt + Dp(30f), _textPaint);
    }

    private void DrawSeparateGarageLobbyUi(Canvas canvas, int w, int h)
    {
        float pad = Dp(16f);

        // Top-Left: Brand + Dedicated Garage Showroom Title + Player Economy Card
        float topH = Dp(50f);
        float brandW = Dp(248f);
        DrawSharpPanel(canvas, pad, pad, pad + brandW, pad + topH,
            Color.Argb(224, 10, 16, 20), Color.Argb(215, 52, 211, 153), 7f, 1.5f);

        float textX = pad + Dp(14f);
        if (_brandSmallMark != null)
        {
            float ms = Dp(28f);
            _srcRect.Set(0, 0, _brandSmallMark.Width, _brandSmallMark.Height);
            _dstRect.Set(pad + Dp(11f), pad + (topH - ms) * 0.5f, pad + Dp(11f) + ms, pad + (topH + ms) * 0.5f);
            canvas.DrawBitmap(_brandSmallMark, _srcRect, _dstRect, null);
            textX = pad + Dp(48f);
        }
        _titlePaint.Color = Color.White;
        _titlePaint.TextSize = Dp(16.5f);
        _titlePaint.TextAlign = Paint.Align.Left;
        canvas.DrawText("GARASI SAWIT", textX, pad + Dp(24f), _titlePaint);

        _textPaint.Color = Color.Argb(230, 74, 222, 128);
        _textPaint.TextSize = Dp(9.5f);
        _textPaint.TextAlign = Paint.Align.Left;
        canvas.DrawText($"ROOM {_net!.CurrentRoomId.ToUpperInvariant()}  •  {_renderer!.Quality.CurrentFps} FPS", textX, pad + Dp(40f), _textPaint);

        // Player Wallet & Identity Strip (tapping allows renaming player cleanly!)
        float profL = pad + brandW + Dp(10f);
        float profR = profL + Dp(250f);
        DrawSharpButton(
            canvas, profL, pad, profR, pad + topH,
            $"{_net.Profile.Name.ToUpperInvariant()}  |  RP {_net.Profile.Coins:N0}  |  {_net.Profile.Gems} EMAS",
            VectorIconKind.AvatarHelm,
            Color.Argb(220, 14, 22, 28), Color.Argb(190, 245, 196, 66), Color.Argb(255, 250, 232, 175),
            () => { _sfx?.Play("ui_click"); OnRenamePlayerRequested?.Invoke(); }, 9.8f, 7f);

        // Top-Right Utility Bar: ABSEN | SERVER | RANK | PENGATURAN (Gear)
        float btnS = Dp(46f), gap = Dp(8f);
        float rx = w - pad;
        DrawSharpButton(canvas, rx - btnS, pad, rx, pad + topH, "", VectorIconKind.SettingsGear,
            Color.Argb(230, 16, 26, 32), Color.Argb(235, 74, 222, 128), Color.White,
            () => { _sfx?.Play("ui_open"); OpenModal(ActiveModalOverlay.Settings); });
        rx -= btnS + gap;
        DrawSharpButton(canvas, rx - btnS, pad, rx, pad + topH, "", VectorIconKind.Trophy,
            Color.Argb(225, 16, 24, 30), Color.Argb(200, 245, 196, 66), Color.Argb(255, 250, 208, 92),
            () => { _sfx?.Play("ui_open"); OpenModal(ActiveModalOverlay.Ranking); });
        rx -= btnS + gap;
        DrawSharpButton(canvas, rx - btnS, pad, rx, pad + topH, "", VectorIconKind.ChatBox,
            Color.Argb(225, 16, 24, 30), Color.Argb(200, 56, 189, 248), Color.Argb(255, 140, 225, 255),
            () => { _sfx?.Play("ui_open"); OpenModal(ActiveModalOverlay.SocialRoom); });
        rx -= btnS + gap;
        DrawSharpButton(canvas, rx - btnS, pad, rx, pad + topH, "", VectorIconKind.DailyCrate,
            Color.Argb(225, 16, 24, 30), Color.Argb(200, 74, 222, 128), Color.Argb(255, 134, 239, 172),
            () => { _sfx?.Play("ui_open"); OpenModal(ActiveModalOverlay.DailyReward); });

        // Left Showroom Wardrobe & Accessory Rail (instant live 3D preview on the turntable!)
        float railL = pad, railW = Dp(196f), rowH = Dp(36f), rowGap = Dp(6f);
        float ry = pad + topH + Dp(14f);
        var av = _net.Profile.Avatar;

        DrawSharpButton(canvas, railL, ry, railL + railW, ry + rowH,
            $"TOPI: {FindLabel(HatCycle, HatLabels, av.Hat)}", VectorIconKind.None,
            Color.Argb(215, 12, 20, 25), Color.Argb(175, 52, 211, 153), Color.White,
            () => CycleAvatarSlot(HatCycle, av.Hat, v => av.Hat = v), 9.5f, 6f);
        ry += rowH + rowGap;

        DrawSharpButton(canvas, railL, ry, railL + railW, ry + rowH,
            $"KACAMATA: {(av.Glasses ? "AKTIF" : "LEPAS")}", VectorIconKind.None,
            Color.Argb(215, 12, 20, 25), Color.Argb(175, 56, 189, 248), Color.White,
            () => { _sfx?.Play("ui_click"); av.Glasses = !av.Glasses; NotifyProfileUpdated(); }, 9.5f, 6f);
        ry += rowH + rowGap;

        DrawSharpButton(canvas, railL, ry, railL + railW, ry + rowH,
            $"TAS: {FindLabel(BackCycle, BackLabels, av.Back)}", VectorIconKind.None,
            Color.Argb(215, 12, 20, 25), Color.Argb(175, 52, 211, 153), Color.White,
            () => CycleAvatarSlot(BackCycle, av.Back, v => av.Back = v), 9.5f, 6f);
        ry += rowH + rowGap;

        DrawSharpButton(canvas, railL, ry, railL + railW, ry + rowH,
            $"ALAT: {FindLabel(ToolCycle, ToolLabels, av.Tool)}", VectorIconKind.None,
            Color.Argb(215, 12, 20, 25), Color.Argb(175, 245, 196, 66), Color.Argb(255, 253, 230, 138),
            () => CycleAvatarSlot(ToolCycle, av.Tool, v => av.Tool = v), 9.5f, 6f);
        ry += rowH + rowGap;

        DrawSharpButton(canvas, railL, ry, railL + railW, ry + rowH,
            $"BAJU: {FindLabel(ColorHexCycle, ColorNameCycle, av.OutfitHex)}", VectorIconKind.None,
            Color.Argb(215, 12, 20, 25), Color.Argb(175, 52, 211, 153), Color.White,
            () => CycleAvatarSlot(ColorHexCycle, av.OutfitHex, v => av.OutfitHex = v), 9.5f, 6f);
        ry += rowH + rowGap;

        DrawSharpButton(canvas, railL, ry, railL + railW, ry + rowH,
            "KATALOG LENGKAP", VectorIconKind.AvatarHelm,
            Color.Argb(230, 18, 36, 32), Color.Argb(235, 74, 222, 128), Color.Argb(255, 134, 239, 172),
            () => { _sfx?.Play("ui_open"); OpenModal(ActiveModalOverlay.Wardrobe); }, 9.5f, 6f);

        // Subtle Showroom Interactive Orbit Hint at Bottom-Left
        _textPaint.Color = Color.Argb(175, 205, 222, 230);
        _textPaint.TextSize = Dp(9.5f);
        _textPaint.TextAlign = Paint.Align.Left;
        canvas.DrawText("GESER LAYAR UNTUK PUTAR KAMERA GARASI 360°  •  MITSUBISHI CANTER FE 74 HD SIAP", pad, h - pad - Dp(8f), _textPaint);

        // Bottom-Right Heroic CTA: MULAI PANEN (Enters PreparingWorld -> Plantation World!)
        float ctaW = Dp(236f), ctaH = Dp(58f);
        float cl = w - pad - ctaW, ct = h - pad - ctaH;
        LastEnterWorldButtonRect = new RectF(cl, ct, cl + ctaW, ct + ctaH);
        DrawSharpButton(
            canvas, cl, ct, cl + ctaW, ct + ctaH,
            "MULAI PANEN", VectorIconKind.PlayChevron,
            Color.Argb(245, 22, 163, 74), Color.Argb(255, 187, 247, 208), Color.White,
            () => OnEnterWorldRequested?.Invoke(), 14.5f, 9f);
    }

    private void DrawWorldLoadingScreen(Canvas canvas, int w, int h)
    {
        // Clean full-screen tactical slate-obsidian backdrop over warm-up frame
        _fillPaint.Color = Color.Argb(242, 9, 13, 17);
        canvas.DrawRect(0, 0, w, h, _fillPaint);

        _strokePaint.Color = Color.Argb(85, 74, 222, 128);
        _strokePaint.StrokeWidth = Dp(1.3f);
        canvas.DrawRect(Dp(20f), Dp(18f), w - Dp(20f), h - Dp(18f), _strokePaint);

        if (_brandWideLogo != null)
        {
            float logoH = Dp(34f);
            float logoW = _brandWideLogo.Width * (logoH / _brandWideLogo.Height);
            _srcRect.Set(0, 0, _brandWideLogo.Width, _brandWideLogo.Height);
            _dstRect.Set(Dp(38f), Dp(34f), Dp(38f) + logoW, Dp(34f) + logoH);
            canvas.DrawBitmap(_brandWideLogo, _srcRect, _dstRect, null);
        }

        _titlePaint.Color = Color.White;
        _titlePaint.TextSize = Dp(30f);
        _titlePaint.TextAlign = Paint.Align.Center;
        canvas.DrawText("MENYIAPKAN DUNIA", w * 0.5f, h * 0.34f, _titlePaint);

        float prog = System.Math.Clamp(_renderer!.WorldPrepProgress, 0.03f, 1.0f);
        int pct = (int)MathF.Round(prog * 100f);

        // Streaming system checklist card
        float cardW = System.Math.Min(w * 0.62f, Dp(520f));
        float cl = (w - cardW) * 0.5f, ct = h * 0.41f, cb = ct + Dp(122f);
        DrawSharpPanel(canvas, cl, ct, cl + cardW, cb, Color.Argb(235, 13, 21, 26), Color.Argb(180, 52, 211, 153), 7f, 1.4f);

        _textPaint.TextAlign = Paint.Align.Left;
        _textPaint.TextSize = Dp(10.2f);
        DrawCheckStep(canvas, cl + Dp(20f), ct + Dp(26f), prog >= 0.25f, "TOPOGRAFI JALAN TANAH LATERIT, RUMPUT & PARIT KEBUN");
        DrawCheckStep(canvas, cl + Dp(20f), ct + Dp(52f), prog >= 0.52f, "PELEPAH SAWIT ALPHA-CUTOUT & SHADOW MAP 1024x1024 PCF");
        DrawCheckStep(canvas, cl + Dp(20f), ct + Dp(78f), prog >= 0.80f, "FISIKA RIGIDBODY & SUSPENSI BAN DOBEL MITSUBISHI CANTER");
        DrawCheckStep(canvas, cl + Dp(20f), ct + Dp(104f), prog >= 0.96f, $"SINKRONISASI MULTIPLAYER & VOICE ({_net!.CurrentRoomId.ToUpperInvariant()})");

        // Segmented high-precision loading bar
        float bt = cb + Dp(22f), bb = bt + Dp(16f);
        DrawSharpPanel(canvas, cl, bt, cl + cardW, bb, Color.Argb(255, 16, 25, 31), Color.Argb(215, 74, 222, 128), 5f, 1.4f);
        float fw = System.Math.Max(Dp(12f), (cardW - Dp(6f)) * prog);
        _fillPaint.Color = Color.Argb(255, 34, 197, 94);
        canvas.DrawRect(cl + Dp(3f), bt + Dp(3f), cl + Dp(3f) + fw, bb - Dp(3f), _fillPaint);

        _textPaint.Color = Color.Argb(240, 167, 243, 208);
        _textPaint.TextAlign = Paint.Align.Left;
        canvas.DrawText(_renderer.WorldPrepStatus, cl, bb + Dp(20f), _textPaint);

        _textPaint.Color = Color.White;
        _textPaint.TextAlign = Paint.Align.Right;
        canvas.DrawText($"{pct}%", cl + cardW, bb + Dp(20f), _textPaint);
    }

    private void DrawCheckStep(Canvas canvas, float x, float y, bool done, string label)
    {
        _fillPaint.Color = done ? Color.Argb(255, 34, 197, 94) : Color.Argb(255, 245, 196, 66);
        canvas.DrawRect(x, y - Dp(8f), x + Dp(8f), y, _fillPaint);
        _textPaint.Color = done ? Color.White : Color.Argb(205, 190, 208, 216);
        canvas.DrawText(label, x + Dp(16f), y, _textPaint);
    }

    private void DrawGameplayHud(Canvas canvas, int w, int h)
    {
        float pad = Dp(14f);

        // 1. Projected 3D World Nameplates, Voice Waves & Chat Bubbles
        lock (_renderer!.HudLock)
        {
            for (int i = 0; i < _renderer.ProjectedLabels.Count; i++)
            {
                var lbl = _renderer.ProjectedLabels[i];
                float sx = lbl.ScreenX * w, sy = lbl.ScreenY * h;
                if (sx < Dp(40f) || sx > w - Dp(40f) || sy < Dp(24f) || sy > h - Dp(80f)) continue;

                _textPaint.TextSize = Dp(9.5f);
                _textPaint.TextAlign = Paint.Align.Center;
                float tagW = System.Math.Max(Dp(86f), _textPaint.MeasureText(lbl.Name) + Dp(24f));
                DrawSharpPanel(canvas, sx - tagW * 0.5f, sy - Dp(18f), sx + tagW * 0.5f, sy + Dp(4f),
                    Color.Argb(186, 10, 18, 22),
                    lbl.IsSpeaking ? Color.Argb(255, 56, 189, 248) : (lbl.IsSelf ? Color.Argb(215, 74, 222, 128) : Color.Argb(180, 245, 196, 66)),
                    4f, 1.2f);
                _textPaint.Color = Color.White;
                canvas.DrawText(lbl.Name, sx, sy - Dp(3.5f), _textPaint);

                if (!string.IsNullOrEmpty(lbl.BubbleText))
                {
                    float bw = System.Math.Min(Dp(210f), _textPaint.MeasureText(lbl.BubbleText) + Dp(22f));
                    DrawSharpPanel(canvas, sx - bw * 0.5f, sy - Dp(44f), sx + bw * 0.5f, sy - Dp(21f),
                        Color.Argb(230, 15, 26, 34), Color.Argb(235, 56, 189, 248), 5f, 1.2f);
                    _textPaint.Color = Color.Argb(255, 224, 242, 254);
                    canvas.DrawText(lbl.BubbleText, sx, sy - Dp(29f), _textPaint);
                }
            }
        }

        // 2. Top-Left Precision Radar Minimap + Uncluttered Status Card (ZERO overlapping widgets!)
        float mapSize = Dp(106f);
        DrawSharpPanel(canvas, pad, pad, pad + mapSize, pad + mapSize,
            Color.Argb(206, 9, 16, 20), Color.Argb(210, 52, 211, 153), 6f, 1.4f);

        float mcx = pad + mapSize * 0.5f, mcy = pad + mapSize * 0.5f;
        float mScale = (mapSize * 0.45f) / 105f;
        _strokePaint.Color = Color.Argb(75, 74, 222, 128);
        _strokePaint.StrokeWidth = Dp(1f);
        canvas.DrawLine(mcx, pad + Dp(4f), mcx, pad + mapSize - Dp(4f), _strokePaint);
        canvas.DrawLine(pad + Dp(4f), mcy, pad + mapSize - Dp(4f), mcy, _strokePaint);

        // RAM PKS marker (gold square)
        float ramMx = mcx + PlantationWorld.RamX * mScale, ramMz = mcy + PlantationWorld.RamZ * mScale;
        _fillPaint.Color = Color.Argb(255, 245, 196, 66);
        canvas.DrawRect(ramMx - Dp(3.5f), ramMz - Dp(3.5f), ramMx + Dp(3.5f), ramMz + Dp(3.5f), _fillPaint);

        // Main Canter marker (cyan square)
        float trkMx = mcx + _renderer.Physics.MainTruck.X * mScale, trkMz = mcy + _renderer.Physics.MainTruck.Z * mScale;
        _fillPaint.Color = Color.Argb(255, 56, 189, 248);
        canvas.DrawRect(trkMx - Dp(3f), trkMz - Dp(3f), trkMx + Dp(3f), trkMz + Dp(3f), _fillPaint);

        // Player arrow dot (bright green)
        float plMx = System.Math.Clamp(mcx + _renderer.PlayerX * mScale, pad + Dp(6f), pad + mapSize - Dp(6f));
        float plMz = System.Math.Clamp(mcy + _renderer.PlayerZ * mScale, pad + Dp(6f), pad + mapSize - Dp(6f));
        _fillPaint.Color = Color.Argb(255, 74, 222, 128);
        canvas.DrawCircle(plMx, plMz, Dp(4f), _fillPaint);

        // Clean Economy & Cargo Strip beside Minimap
        float statL = pad + mapSize + Dp(10f);
        float statW = Dp(218f), statH = Dp(52f);
        DrawSharpPanel(canvas, statL, pad, statL + statW, pad + statH,
            Color.Argb(204, 10, 17, 22), Color.Argb(185, 52, 211, 153), 6f, 1.3f);

        int cargoUnits = System.Math.Max(_net!.LocalCargo, _renderer.Physics.MainTruck.VisualCargoUnits);
        _textPaint.TextAlign = Paint.Align.Left;
        _textPaint.TextSize = Dp(10.5f);
        _textPaint.Color = Color.Argb(255, 250, 214, 96);
        canvas.DrawText($"RP {_net.Profile.Coins:N0}   •   {_net.Profile.Gems} EMAS", statL + Dp(12f), pad + Dp(21f), _textPaint);

        _textPaint.TextSize = Dp(9.6f);
        _textPaint.Color = Color.Argb(235, 198, 226, 214);
        string holdInfo = _renderer.InTruck
            ? $"CANTER: {MathF.Abs(_renderer.Physics.MainTruck.SpeedMs * 3.6f):0} KM/J  |  BAK {cargoUnits * 25} KG"
            : $"BAK TRUK: {cargoUnits * 25} KG  |  TANGAN: {_renderer.Physics.Player.HeldTbsUnits}";
        canvas.DrawText(holdInfo, statL + Dp(12f), pad + Dp(40f), _textPaint);

        // 3. Top-Right Uncluttered 4-Button Tactical Bar: [VOICE] [SERVER] [RANK] [PENGATURAN GEAR]
        // Notice: ALL graphics/FPS/shadow toggles moved cleanly inside PENGATURAN as requested!
        float btnS = Dp(42f), gap = Dp(7f);
        float rx = w - pad;
        DrawSharpButton(canvas, rx - btnS, pad, rx, pad + btnS, "", VectorIconKind.SettingsGear,
            Color.Argb(218, 12, 20, 26), Color.Argb(225, 74, 222, 128), Color.White,
            () => { _sfx?.Play("ui_open"); OpenModal(ActiveModalOverlay.Settings); });
        rx -= btnS + gap;
        DrawSharpButton(canvas, rx - btnS, pad, rx, pad + btnS, "", VectorIconKind.Trophy,
            Color.Argb(208, 12, 20, 26), Color.Argb(185, 245, 196, 66), Color.Argb(255, 250, 208, 92),
            () => { _sfx?.Play("ui_open"); OpenModal(ActiveModalOverlay.Ranking); });
        rx -= btnS + gap;
        DrawSharpButton(canvas, rx - btnS, pad, rx, pad + btnS, "", VectorIconKind.ChatBox,
            Color.Argb(208, 12, 20, 26), Color.Argb(185, 56, 189, 248), Color.Argb(255, 148, 226, 255),
            () => { _sfx?.Play("ui_open"); OpenModal(ActiveModalOverlay.SocialRoom); });
        rx -= btnS + gap;
        bool micActive = _voice?.MicEnabled == true;
        DrawSharpButton(canvas, rx - btnS, pad, rx, pad + btnS, "",
            micActive ? VectorIconKind.MicOn : VectorIconKind.MicMuted,
            micActive ? Color.Argb(225, 16, 78, 56) : Color.Argb(208, 12, 20, 26),
            micActive ? Color.Argb(255, 74, 222, 128) : Color.Argb(165, 148, 163, 184),
            Color.White,
            () => OnToggleVoiceMic?.Invoke());

        if (_renderer.Quality.ShowFpsHud)
        {
            _textPaint.Color = Color.Argb(185, 167, 243, 208);
            _textPaint.TextSize = Dp(8.8f);
            _textPaint.TextAlign = Paint.Align.Right;
            canvas.DrawText(
                $"{_renderer.Quality.CurrentFps} FPS ({_renderer.Quality.TargetFps}HZ)  •  {_renderer.Quality.Active.Label}  •  {_net.CurrentRoomId.ToUpperInvariant()}",
                w - pad, pad + btnS + Dp(14f), _textPaint);
        }

        // 4. Bottom-Left Precision Analog Joystick
        float baseR = Dp(56f);
        float jcx = _joyPointerId != -1 ? _joyOriginX : pad + baseR + Dp(18f);
        float jcy = _joyPointerId != -1 ? _joyOriginY : h - pad - baseR - Dp(12f);
        float kx = _joyPointerId != -1 ? _joyKnobX : jcx;
        float ky = _joyPointerId != -1 ? _joyKnobY : jcy;

        _fillPaint.Color = Color.Argb(88, 10, 18, 22);
        canvas.DrawCircle(jcx, jcy, baseR, _fillPaint);
        _strokePaint.Color = Color.Argb(175, 74, 222, 128);
        _strokePaint.StrokeWidth = Dp(1.6f);
        canvas.DrawCircle(jcx, jcy, baseR, _strokePaint);

        _fillPaint.Color = Color.Argb(220, 34, 197, 94);
        canvas.DrawCircle(kx, ky, Dp(21f), _fillPaint);

        // 5. Bottom-Right Ergonomic Action Cluster (Clean, Spacious, Zero Clutter!)
        float mainS = Dp(72f);
        float hx = w - pad - mainS, hy = h - pad - mainS;

        if (!_renderer.InTruck)
        {
            // Primary: PANEN EGREK / DODOS / TOJOK
            LastHarvestButtonRect = new RectF(hx, hy, hx + mainS, hy + mainS);
            bool treeReady = _renderer.NearestRipeTreeId >= 0;
            DrawSharpButton(canvas, hx, hy, hx + mainS, hy + mainS, "PANEN", VectorIconKind.HarvestSickle,
                treeReady ? Color.Argb(235, 22, 163, 74) : Color.Argb(205, 16, 28, 34),
                treeReady ? Color.Argb(255, 134, 239, 172) : Color.Argb(170, 74, 222, 128),
                Color.White, () => OnHarvestPressed?.Invoke(), 10f, 10f);

            // Contextual: AMBIL TBS / MUAT TRUK
            float subS = Dp(56f);
            float px = hx - subS - Dp(12f), py = h - pad - subS;
            LastPickupOrLoadButtonRect = new RectF(px, py, px + subS, py + subS);
            bool loadMode = _renderer.CanLoadIntoVehicleOrCart || _renderer.Physics.Player.HasHeldTbs;
            bool glow = loadMode || _renderer.NearbyGroundFruitCount > 0;
            DrawSharpButton(
                canvas, px, py, px + subS, py + subS,
                loadMode ? "MUAT" : "AMBIL",
                loadMode ? VectorIconKind.LoadTruck : VectorIconKind.PickupTbs,
                glow ? Color.Argb(235, 180, 83, 9) : Color.Argb(205, 16, 26, 32),
                glow ? Color.Argb(255, 253, 224, 71) : Color.Argb(160, 148, 163, 184),
                Color.White, () => OnPickupOrLoadPressed?.Invoke(), 8.8f, 8f);

            // Secondary arc: NAIK CANTER + ANGKONG
            float tx = hx, ty = hy - subS - Dp(10f);
            LastTruckButtonRect = new RectF(tx, ty, tx + subS, ty + subS);
            DrawSharpButton(canvas, tx, ty, tx + subS, ty + subS, "TRUK", VectorIconKind.CanterTruck,
                Color.Argb(215, 16, 28, 36), Color.Argb(215, 245, 196, 66), Color.Argb(255, 253, 224, 71),
                () => OnTruckTogglePressed?.Invoke(), 8.5f, 8f);

            float ax = px - subS - Dp(10f), ay = py;
            DrawSharpButton(canvas, ax, ay, ax + subS, ay + subS, "ANGKONG", VectorIconKind.Angkong,
                _renderer.Physics.Player.ActiveAngkongIndex >= 0 ? Color.Argb(230, 21, 128, 61) : Color.Argb(205, 16, 26, 32),
                Color.Argb(185, 74, 222, 128), Color.White,
                () => OnAngkongTogglePressed?.Invoke(), 8.0f, 8f);
        }
        else
        {
            // Driving COE Mitsubishi Canter HUD Cluster: TURBO KLAKSON + TURUN KABIN
            LastHarvestButtonRect = new RectF(hx, hy, hx + mainS, hy + mainS);
            DrawSharpButton(canvas, hx, hy, hx + mainS, hy + mainS, "TURBO", VectorIconKind.BasuriHorn,
                Color.Argb(235, 180, 83, 9), Color.Argb(255, 253, 224, 71), Color.White,
                () => OnHornPressed?.Invoke(), 10f, 10f);

            float subS = Dp(56f);
            float tx = hx - subS - Dp(12f), ty = h - pad - subS;
            LastTruckButtonRect = new RectF(tx, ty, tx + subS, ty + subS);
            DrawSharpButton(canvas, tx, ty, tx + subS, ty + subS, "TURUN", VectorIconKind.SteeringWheel,
                Color.Argb(220, 16, 28, 36), Color.Argb(225, 56, 189, 248), Color.White,
                () => OnTruckTogglePressed?.Invoke(), 8.8f, 8f);
        }

        // Contextual Sell Button when near RAM PKS Weighbridge
        if (_renderer.NearRamWeighbridge)
        {
            float sw = Dp(196f), sh = Dp(46f);
            float sl = (w - sw) * 0.5f, st = h - pad - sh;
            DrawSharpButton(canvas, sl, st, sl + sw, st + sh,
                "JUAL SETOR RAM PKS", VectorIconKind.SellPks,
                Color.Argb(242, 202, 138, 4), Color.Argb(255, 254, 249, 195), Color.White,
                () => OnSellPressed?.Invoke(), 11f, 8f);
        }
    }

    private void DrawActiveModalOverlay(Canvas canvas, int w, int h)
    {
        // Full-screen dim backdrop (blocks accidental touches behind modal)
        _fillPaint.Color = Color.Argb(204, 5, 9, 12);
        canvas.DrawRect(0, 0, w, h, _fillPaint);

        float mw = System.Math.Min(w - Dp(44f), Dp(650f));
        float mh = System.Math.Min(h - Dp(30f), Dp(368f));
        float ml = (w - mw) * 0.5f, mt = (h - mh) * 0.5f;
        float mr = ml + mw, mb = mt + mh;

        DrawSharpPanel(canvas, ml, mt, mr, mb, Color.Argb(248, 11, 18, 23), Color.Argb(235, 74, 222, 128), 9f, 1.8f);

        string title = ActiveModal switch
        {
            ActiveModalOverlay.Settings => "PENGATURAN",
            ActiveModalOverlay.Wardrobe => "LEMARI AKSESORIS",
            ActiveModalOverlay.SocialRoom => "SERVER DAN CHAT",
            ActiveModalOverlay.Ranking => "PERINGKAT PKS",
            ActiveModalOverlay.DailyReward => "HADIAH HARIAN",
            _ => "MENU",
        };

        _titlePaint.Color = Color.White;
        _titlePaint.TextSize = Dp(19f);
        _titlePaint.TextAlign = Paint.Align.Left;
        canvas.DrawText(title, ml + Dp(22f), mt + Dp(33f), _titlePaint);

        // Close [X] button top-right of modal
        DrawSharpButton(canvas, mr - Dp(50f), mt + Dp(10f), mr - Dp(12f), mt + Dp(44f), "", VectorIconKind.CloseCross,
            Color.Argb(235, 127, 29, 29), Color.Argb(235, 248, 113, 113), Color.White,
            () => { _sfx?.Play("ui_click"); CloseModal(); }, 10f, 6f);

        _strokePaint.Color = Color.Argb(90, 74, 222, 128);
        _strokePaint.StrokeWidth = Dp(1f);
        canvas.DrawLine(ml + Dp(18f), mt + Dp(52f), mr - Dp(18f), mt + Dp(52f), _strokePaint);

        switch (ActiveModal)
        {
            case ActiveModalOverlay.Settings:
                DrawSettingsModalBody(canvas, ml, mt + Dp(60f), mr, mb);
                break;
            case ActiveModalOverlay.Wardrobe:
                DrawWardrobeModalBody(canvas, ml, mt + Dp(60f), mr, mb);
                break;
            case ActiveModalOverlay.SocialRoom:
                DrawSocialRoomModalBody(canvas, ml, mt + Dp(60f), mr, mb);
                break;
            case ActiveModalOverlay.Ranking:
                DrawRankingModalBody(canvas, ml, mt + Dp(60f), mr, mb);
                break;
            case ActiveModalOverlay.DailyReward:
                DrawDailyModalBody(canvas, ml, mt + Dp(60f), mr, mb);
                break;
        }
    }

    private void DrawSettingsModalBody(Canvas canvas, float ml, float bodyTop, float mr, float mb)
    {
        var q = _renderer!.Quality;
        float innerL = ml + Dp(20f), innerR = mr - Dp(20f);
        float tabW = (innerR - innerL - Dp(16f)) / 3f;
        string[] tabs = ["GRAFIK & FPS", "VISUAL & BAYANGAN", "AUDIO & SISTEM"];
        for (int i = 0; i < 3; i++)
        {
            float tl = innerL + i * (tabW + Dp(8f));
            bool sel = SettingsTabIndex == i;
            DrawSharpButton(canvas, tl, bodyTop, tl + tabW, bodyTop + Dp(34f), tabs[i], VectorIconKind.None,
                sel ? Color.Argb(240, 22, 163, 74) : Color.Argb(220, 18, 28, 35),
                sel ? Color.Argb(255, 187, 247, 208) : Color.Argb(150, 71, 85, 105),
                Color.White, _tabActions[i], 9.8f, 5f);
        }

        float y = bodyTop + Dp(48f);
        float rowH = Dp(42f), rowStep = Dp(52f);

        if (SettingsTabIndex == 0)
        {
            // Row 1: Graphics Quality Preset
            DrawSettingLabel(canvas, innerL, y, "KUALITAS GRAFIK", q.Active.Label);
            DrawOptionStrip(canvas, innerL + Dp(185f), y, innerR, rowH,
                ["SMOOTH", "STD", "ULTRA", "MAX HD"],
                (int)q.CurrentPreset,
                idx =>
                {
                    _sfx?.Play("ui_click");
                    _renderer.RequestPresetChange((GraphicsPreset)idx);
                    PostInvalidate();
                });
            y += rowStep;

            // Row 2: Target Frame Rate (30 / 60 / 90 / 120 FPS + Hardware Display Mode!)
            int fpsIdx = q.TargetFps >= 115 ? 3 : (q.TargetFps >= 85 ? 2 : (q.TargetFps >= 55 ? 1 : 0));
            DrawSettingLabel(canvas, innerL, y, "TARGET FRAME RATE", $"{q.TargetFps} FPS");
            DrawOptionStrip(canvas, innerL + Dp(185f), y, innerR, rowH,
                ["30 FPS", "60 FPS", "90 FPS", "120 FPS"],
                fpsIdx,
                idx =>
                {
                    int[] rates = [30, 60, 90, 120];
                    _sfx?.Play("ui_click");
                    q.TargetFps = rates[idx];
                    OnTargetFpsSelected?.Invoke(rates[idx]);
                    PostInvalidate();
                });
            y += rowStep;

            // Row 3: 3D Render Scale
            float sc = q.EffectiveRenderScale;
            int scIdx = sc < 0.68f ? 0 : (sc < 0.82f ? 1 : (sc < 0.95f ? 2 : 3));
            DrawSettingLabel(canvas, innerL, y, "RESOLUSI RENDER 3D", $"{(int)MathF.Round(sc * 100f)}%");
            DrawOptionStrip(canvas, innerL + Dp(185f), y, innerR, rowH,
                ["60%", "75%", "88%", "100% HD"],
                scIdx,
                idx =>
                {
                    float[] scales = [0.60f, 0.75f, 0.88f, 1.00f];
                    _sfx?.Play("ui_click");
                    q.CustomRenderScale = scales[idx];
                    _renderer.SyncRenderScaleNow();
                    PostInvalidate();
                });
            y += rowStep;

            // Row 4: Adaptive Anti-Lag Governor
            DrawSettingLabel(canvas, innerL, y, "OPTIMASI ANTI-LAG OTOMATIS", q.AutoStepDownEnabled ? "AKTIF" : "MANUAL");
            DrawOptionStrip(canvas, innerL + Dp(185f), y, innerR, rowH,
                ["MATI (MANUAL)", "AKTIF (STABIL FPS)"],
                q.AutoStepDownEnabled ? 1 : 0,
                idx => { _sfx?.Play("ui_click"); q.AutoStepDownEnabled = idx == 1; PostInvalidate(); });
        }
        else if (SettingsTabIndex == 1)
        {
            // Row 1: Real-Time Sun Shadow Map Quality
            DrawSettingLabel(canvas, innerL, y, "BAYANGAN MATAHARI REAL-TIME", q.ShadowTier.ToString().ToUpperInvariant());
            DrawOptionStrip(canvas, innerL + Dp(185f), y, innerR, rowH,
                ["MATI", "SEDANG", "TINGGI PCF"],
                (int)q.ShadowTier,
                idx => { _sfx?.Play("ui_click"); q.ShadowTier = (ShadowQualityTier)idx; PostInvalidate(); });
            y += rowStep;

            // Row 2: Volumetric Cumulus Clouds & Atmospheric Lighting
            DrawSettingLabel(canvas, innerL, y, "AWAN VOLUMETRIK & KABUT", q.CloudsEnabled ? "AKTIF" : "MATI");
            DrawOptionStrip(canvas, innerL + Dp(185f), y, innerR, rowH,
                ["MATI", "AKTIF"],
                q.CloudsEnabled ? 1 : 0,
                idx => { _sfx?.Play("ui_click"); q.CloudsEnabled = idx == 1; PostInvalidate(); });
            y += rowStep;

            // Row 3: Tire Dust, Diesel Smoke & Harvest VFX
            DrawSettingLabel(canvas, innerL, y, "EFEK DEBU BAN & ASAP DIESEL", q.ParticlesEnabled ? "AKTIF" : "MATI");
            DrawOptionStrip(canvas, innerL + Dp(185f), y, innerR, rowH,
                ["MATI", "AKTIF"],
                q.ParticlesEnabled ? 1 : 0,
                idx => { _sfx?.Play("ui_click"); q.ParticlesEnabled = idx == 1; PostInvalidate(); });
            y += rowStep;

            // Row 4: Live FPS & Frame Telemetry Indicator
            DrawSettingLabel(canvas, innerL, y, "INDIKATOR FPS DI LAYAR", q.ShowFpsHud ? "TAMPIL" : "SEMBUNYI");
            DrawOptionStrip(canvas, innerL + Dp(185f), y, innerR, rowH,
                ["SEMBUNYI", "TAMPIL FPS"],
                q.ShowFpsHud ? 1 : 0,
                idx => { _sfx?.Play("ui_click"); q.ShowFpsHud = idx == 1; PostInvalidate(); });
        }
        else
        {
            bool sfxOn = _sfx?.Muted == false;
            DrawSettingLabel(canvas, innerL, y, "EFEK SUARA MESIN & PANEN", sfxOn ? "AKTIF" : "BISU");
            DrawOptionStrip(canvas, innerL + Dp(185f), y, innerR, rowH,
                ["BISU", "SUARA AKTIF"],
                sfxOn ? 1 : 0,
                idx => { if (_sfx != null) _sfx.Muted = idx == 0; _sfx?.Play("ui_click"); PostInvalidate(); });
            y += rowStep;

            int sensIdx = _renderer.CameraSensitivity < 0.85f ? 0 : (_renderer.CameraSensitivity > 1.25f ? 2 : 1);
            DrawSettingLabel(canvas, innerL, y, "SENSITIVITAS KAMERA 3D", sensIdx == 0 ? "RENDAH" : (sensIdx == 2 ? "CEPAT" : "NORMAL"));
            DrawOptionStrip(canvas, innerL + Dp(185f), y, innerR, rowH,
                ["RENDAH", "NORMAL", "CEPAT"],
                sensIdx,
                idx => { float[] sv = [0.68f, 1.0f, 1.45f]; _renderer.CameraSensitivity = sv[idx]; _sfx?.Play("ui_click"); PostInvalidate(); });
            y += rowStep + Dp(8f);

            if (_renderer.Stage == AppSceneStage.Gameplay)
            {
                DrawSharpButton(canvas, innerL, y, innerR, y + Dp(46f),
                    "KEMBALI KE GARASI SHOWROOM LOBBY", VectorIconKind.LobbyGrid,
                    Color.Argb(235, 30, 58, 138), Color.Argb(235, 96, 165, 250), Color.White,
                    () => { CloseModal(); OnReturnLobbyRequested?.Invoke(); }, 10.5f, 7f);
            }
        }
    }

    private void DrawWardrobeModalBody(Canvas canvas, float ml, float bodyTop, float mr, float mb)
    {
        var av = _net!.Profile.Avatar;
        float innerL = ml + Dp(20f), innerR = mr - Dp(20f);
        float y = bodyTop + Dp(4f), rowH = Dp(42f), step = Dp(54f);

        DrawSettingLabel(canvas, innerL, y, "PENUTUP KEPALA", FindLabel(HatCycle, HatLabels, av.Hat));
        DrawOptionStrip(canvas, innerL + Dp(165f), y, innerR, rowH,
            ["CAPING", "HELM", "IKAT", "MANDOR", "SULTAN"],
            System.Math.Max(0, Array.IndexOf(HatCycle, av.Hat)),
            idx => { av.Hat = HatCycle[idx]; _sfx?.Play("ui_click"); NotifyProfileUpdated(); });
        y += step;

        DrawSettingLabel(canvas, innerL, y, "TAS & GENDONGAN", FindLabel(BackCycle, BackLabels, av.Back));
        DrawOptionStrip(canvas, innerL + Dp(165f), y, innerR, rowH,
            ["ROTAN", "RANSEL", "JUBAH", "SAYAP", "LEPAS"],
            System.Math.Max(0, Array.IndexOf(BackCycle, av.Back)),
            idx => { av.Back = BackCycle[idx]; _sfx?.Play("ui_click"); NotifyProfileUpdated(); });
        y += step;

        DrawSettingLabel(canvas, innerL, y, "ALAT PANEN UTAMA", FindLabel(ToolCycle, ToolLabels, av.Tool));
        DrawOptionStrip(canvas, innerL + Dp(165f), y, innerR, rowH,
            ["EGREK", "DODOS", "TOJOK", "NAGA"],
            System.Math.Max(0, Array.IndexOf(ToolCycle, av.Tool)),
            idx => { av.Tool = ToolCycle[idx]; _sfx?.Play("ui_click"); NotifyProfileUpdated(); });
        y += step;

        DrawSettingLabel(canvas, innerL, y, "WARNA SERAGAM", FindLabel(ColorHexCycle, ColorNameCycle, av.OutfitHex));
        DrawOptionStrip(canvas, innerL + Dp(165f), y, innerR, rowH,
            ["HIJAU", "BIRU", "MERAH", "EMAS", "HITAM"],
            System.Math.Max(0, Array.IndexOf(ColorHexCycle, av.OutfitHex)),
            idx => { av.OutfitHex = ColorHexCycle[idx]; _sfx?.Play("ui_click"); NotifyProfileUpdated(); });
        y += step;

        float halfW = (innerR - innerL - Dp(12f)) * 0.5f;
        DrawSharpButton(canvas, innerL, y, innerL + halfW, y + Dp(40f),
            $"KACAMATA HITAM: {(av.Glasses ? "AKTIF" : "LEPAS")}", VectorIconKind.None,
            av.Glasses ? Color.Argb(235, 22, 163, 74) : Color.Argb(220, 18, 28, 35),
            Color.Argb(200, 74, 222, 128), Color.White,
            () => { av.Glasses = !av.Glasses; _sfx?.Play("ui_click"); NotifyProfileUpdated(); }, 9.5f, 6f);

        DrawSharpButton(canvas, innerL + halfW + Dp(12f), y, innerR, y + Dp(40f),
            $"SARUNG PARANG PINGGANG: {(av.WaistParang ? "AKTIF" : "LEPAS")}", VectorIconKind.None,
            av.WaistParang ? Color.Argb(235, 22, 163, 74) : Color.Argb(220, 18, 28, 35),
            Color.Argb(200, 74, 222, 128), Color.White,
            () => { av.WaistParang = !av.WaistParang; _sfx?.Play("ui_click"); NotifyProfileUpdated(); }, 9.5f, 6f);
    }

    private void DrawSocialRoomModalBody(Canvas canvas, float ml, float bodyTop, float mr, float mb)
    {
        float innerL = ml + Dp(20f), innerR = mr - Dp(20f);
        string[] rooms = ["kebun-sumatera-01", "kebun-riau-02", "kebun-kalimantan-03", "kebun-sultan-vip"];
        DrawSettingLabel(canvas, innerL, bodyTop + Dp(4f), "PILIH ROOM SERVER LIVE", _net!.CurrentRoomId.ToUpperInvariant());
        DrawOptionStrip(canvas, innerL + Dp(175f), bodyTop + Dp(4f), innerR, Dp(40f),
            ["SUMATERA", "RIAU", "KALIMANTAN", "SULTAN"],
            System.Math.Max(0, Array.IndexOf(rooms, _net.CurrentRoomId)),
            idx => { _sfx?.Play("ui_click"); _net.SelectRoom(rooms[idx]); ShowToast($"PINDAH KE SERVER {rooms[idx].ToUpperInvariant()}"); PostInvalidate(); });

        float y = bodyTop + Dp(58f);
        string[] quickMsgs = ["SIAP SETOR RAM!", "ADA SAWIT EMAS!", "BANTU MUAT TRUK!", "CANTER OLENG GAS!"];
        float qw = (innerR - innerL - Dp(18f)) / 4f;
        for (int i = 0; i < quickMsgs.Length; i++)
        {
            string msg = quickMsgs[i];
            float ql = innerL + i * (qw + Dp(6f));
            DrawSharpButton(canvas, ql, y, ql + qw, y + Dp(36f), msg, VectorIconKind.None,
                Color.Argb(225, 16, 32, 42), Color.Argb(185, 56, 189, 248), Color.White,
                () => { _sfx?.Play("ui_click"); _net.SendChat(msg); ShowToast($"TERKIRIM: {msg}"); PostInvalidate(); }, 8.3f, 5f);
        }

        // Recent live chat feed box + custom keyboard chat button
        float feedTop = y + Dp(46f), feedBot = mb - Dp(56f);
        DrawSharpPanel(canvas, innerL, feedTop, innerR, feedBot, Color.Argb(230, 8, 13, 17), Color.Argb(130, 56, 189, 248), 6f, 1.1f);
        _net.CopyRenderState(_peersTmp, _boarsTmp, _chatsTmp, 0f);
        _textPaint.TextAlign = Paint.Align.Left;
        _textPaint.TextSize = Dp(9.6f);
        int start = System.Math.Max(0, _chatsTmp.Count - 4);
        float cy = feedTop + Dp(22f);
        if (_chatsTmp.Count == 0)
        {
            _textPaint.Color = Color.Argb(175, 148, 163, 184);
            canvas.DrawText("SERVER CHAT GLOBAL AKTIF — PILIH PESAN CEPAT ATAU KETIK PESAN BARU.", innerL + Dp(14f), cy, _textPaint);
        }
        else
        {
            for (int i = start; i < _chatsTmp.Count; i++)
            {
                _textPaint.Color = Color.Argb(255, 167, 243, 208);
                canvas.DrawText($"[{_chatsTmp[i].SenderName}]  {_chatsTmp[i].Text}", innerL + Dp(14f), cy, _textPaint);
                cy += Dp(22f);
            }
        }

        float halfW = (innerR - innerL - Dp(12f)) * 0.5f;
        DrawSharpButton(canvas, innerL, mb - Dp(46f), innerL + halfW, mb - Dp(10f),
            "KETIK PESAN CHAT...", VectorIconKind.ChatBox,
            Color.Argb(235, 14, 116, 144), Color.Argb(235, 125, 211, 252), Color.White,
            () => { _sfx?.Play("ui_click"); OnCustomChatInputRequested?.Invoke(); }, 9.8f, 6f);

        bool micOn = _voice?.MicEnabled == true;
        DrawSharpButton(canvas, innerL + halfW + Dp(12f), mb - Dp(46f), innerR, mb - Dp(10f),
            micOn ? "VOICE CHAT: AKTIF (MATIKAN)" : "VOICE CHAT: AKTIFKAN MIC",
            micOn ? VectorIconKind.MicOn : VectorIconKind.MicMuted,
            micOn ? Color.Argb(235, 22, 163, 74) : Color.Argb(225, 30, 41, 59),
            Color.Argb(220, 74, 222, 128), Color.White,
            () => { OnToggleVoiceMic?.Invoke(); PostInvalidate(); }, 9.8f, 6f);
    }

    private void DrawRankingModalBody(Canvas canvas, float ml, float bodyTop, float mr, float mb)
    {
        float innerL = ml + Dp(20f), innerR = mr - Dp(20f);
        DrawSharpPanel(canvas, innerL, bodyTop + Dp(2f), innerR, mb - Dp(14f),
            Color.Argb(228, 8, 14, 18), Color.Argb(150, 245, 196, 66), 6f, 1.2f);

        _textPaint.TextSize = Dp(10f);
        float y = bodyTop + Dp(26f);
        lock (_leaderCache)
        {
            if (_leaderCache.Count == 0)
            {
                _textPaint.Color = Color.Argb(225, 250, 214, 96);
                _textPaint.TextAlign = Paint.Align.Left;
                canvas.DrawText($"#1  {_net!.Profile.Name.ToUpperInvariant()}   —   {_net.Profile.TotalKg} KG TBS DISERAHKAN KE PKS", innerL + Dp(18f), y, _textPaint);
            }
            else
            {
                int limit = System.Math.Min(7, _leaderCache.Count);
                for (int i = 0; i < limit; i++)
                {
                    var r = _leaderCache[i];
                    _textPaint.Color = i == 0 ? Color.Argb(255, 253, 224, 71) : Color.White;
                    _textPaint.TextAlign = Paint.Align.Left;
                    canvas.DrawText($"#{r.Rank}   {r.Name}", innerL + Dp(18f), y, _textPaint);
                    _textPaint.TextAlign = Paint.Align.Right;
                    canvas.DrawText($"{r.TotalKg:N0} KG  •  {r.Score:N0} PTS", innerR - Dp(18f), y, _textPaint);
                    y += Dp(34f);
                }
            }
        }
    }

    private void DrawDailyModalBody(Canvas canvas, float ml, float bodyTop, float mr, float mb)
    {
        float innerL = ml + Dp(20f), innerR = mr - Dp(20f);
        float cardW = (innerR - innerL - Dp(36f)) / 7f;
        int streak = System.Math.Clamp(_net!.Profile.StreakDay, 0, 7);
        for (int d = 0; d < 7; d++)
        {
            float cl = innerL + d * (cardW + Dp(6f));
            bool claimed = d < streak;
            DrawSharpPanel(canvas, cl, bodyTop + Dp(12f), cl + cardW, bodyTop + Dp(132f),
                claimed ? Color.Argb(230, 20, 83, 45) : Color.Argb(220, 16, 25, 32),
                d == streak ? Color.Argb(255, 253, 224, 71) : Color.Argb(165, 74, 222, 128), 6f, 1.3f);
            _textPaint.TextAlign = Paint.Align.Center;
            _textPaint.TextSize = Dp(9.2f);
            _textPaint.Color = Color.Argb(230, 167, 243, 208);
            canvas.DrawText($"HARI {d + 1}", cl + cardW * 0.5f, bodyTop + Dp(38f), _textPaint);
            _textPaint.Color = Color.Argb(255, 253, 224, 71);
            canvas.DrawText($"+{(d + 1) * 25}K", cl + cardW * 0.5f, bodyTop + Dp(78f), _textPaint);
            _textPaint.Color = Color.White;
            canvas.DrawText(claimed ? "SELESAI" : "BONUS", cl + cardW * 0.5f, bodyTop + Dp(110f), _textPaint);
        }

        DrawSharpButton(canvas, innerL, mb - Dp(62f), innerR, mb - Dp(14f),
            "KLAIM BONUS KEHADIRAN HARIAN", VectorIconKind.DailyCrate,
            Color.Argb(242, 22, 163, 74), Color.Argb(255, 187, 247, 208), Color.White,
            () =>
            {
                _sfx?.Play("sell");
                _net.ClaimDaily();
                ShowToast("BONUS HARIAN DIKLAIM!");
                CloseModal();
            }, 11.5f, 7f);
    }

    private void DrawSettingLabel(Canvas canvas, float x, float y, string title, string currentVal)
    {
        _textPaint.TextAlign = Paint.Align.Left;
        _textPaint.TextSize = Dp(9.6f);
        _textPaint.Color = Color.White;
        canvas.DrawText(title, x, y + Dp(17f), _textPaint);
        _textPaint.TextSize = Dp(8.8f);
        _textPaint.Color = Color.Argb(235, 74, 222, 128);
        canvas.DrawText(currentVal, x, y + Dp(33f), _textPaint);
    }

    private void DrawOptionStrip(Canvas canvas, float l, float t, float r, float h, string[] labels, int activeIdx, Action<int> onPick)
    {
        float gap = Dp(6f);
        float bw = (r - l - gap * (labels.Length - 1)) / labels.Length;
        for (int i = 0; i < labels.Length; i++)
        {
            int captured = i;
            float bl = l + i * (bw + gap);
            bool sel = i == activeIdx;
            DrawSharpButton(
                canvas, bl, t, bl + bw, t + h,
                labels[i], VectorIconKind.None,
                sel ? Color.Argb(242, 22, 163, 74) : Color.Argb(220, 17, 26, 33),
                sel ? Color.Argb(255, 187, 247, 208) : Color.Argb(150, 71, 85, 105),
                Color.White,
                () => onPick(captured), 9.0f, 5f);
        }
    }

    private void CycleAvatarSlot(string[] values, string current, Action<string> setter)
    {
        _sfx?.Play("ui_click");
        int idx = Array.IndexOf(values, current);
        setter(values[(idx + 1 + values.Length) % values.Length]);
        NotifyProfileUpdated();
    }

    private static string FindLabel(string[] keys, string[] labels, string val)
    {
        int i = Array.IndexOf(keys, val);
        return i >= 0 && i < labels.Length ? labels[i] : labels[0];
    }

    private void NotifyProfileUpdated()
    {
        if (_net != null) _net.SaveAvatar(_net.Profile.Name, _net.Profile.Avatar);
        OnProfileModified?.Invoke();
        PostInvalidate();
    }

    public override bool OnTouchEvent(MotionEvent? e)
    {
        if (e == null || _renderer == null) return false;
        var action = e.ActionMasked;
        int idx = e.ActionIndex;
        int pid = e.GetPointerId(idx);
        float x = e.GetX(idx), y = e.GetY(idx);

        if (action == MotionEventActions.Down || action == MotionEventActions.PointerDown)
        {
            // Tap anywhere during Splash once GPU is warm skips cleanly straight into Garage Lobby!
            if (_renderer.Stage == AppSceneStage.Splash)
            {
                _renderer.SkipSplashToLobby();
                PostInvalidate();
                return true;
            }

            // 1. Check crisp registered UI hit zones first (LIFO so modal buttons always win!)
            for (int i = _hitCount - 1; i >= 0; i--)
            {
                ref var hz = ref _hitZones[i];
                if (x >= hz.L && x <= hz.R && y >= hz.T && y <= hz.B && hz.Callback != null)
                {
                    hz.Callback.Invoke();
                    return true;
                }
            }

            if (ActiveModal != ActiveModalOverlay.None) return true;

            // 2. Left-half analog movement stick in Gameplay!
            if (_renderer.Stage == AppSceneStage.Gameplay && _joyPointerId == -1 && x < Width * 0.44f && y > Height * 0.30f)
            {
                _joyPointerId = pid;
                _joyOriginX = x;
                _joyOriginY = y;
                _joyKnobX = x;
                _joyKnobY = y;
                _renderer.JoyX = 0f;
                _renderer.JoyY = 0f;
                PostInvalidate();
                return true;
            }

            // 3. Free 360-deg Camera Orbit (both in Separate Garage Lobby AND in Gameplay!)
            if (_camPointerId == -1)
            {
                _camPointerId = pid;
                _camLastX = x;
                _camLastY = y;
                return true;
            }
        }
        else if (action == MotionEventActions.Move)
        {
            float maxR = Dp(56f);
            for (int p = 0; p < e.PointerCount; p++)
            {
                int id = e.GetPointerId(p);
                float px = e.GetX(p), py = e.GetY(p);
                if (id == _joyPointerId)
                {
                    float dx = px - _joyOriginX, dy = py - _joyOriginY;
                    float len = MathF.Sqrt(dx * dx + dy * dy);
                    if (len > maxR) { dx = dx / len * maxR; dy = dy / len * maxR; }
                    _joyKnobX = _joyOriginX + dx;
                    _joyKnobY = _joyOriginY + dy;
                    _renderer.JoyX = dx / maxR;
                    _renderer.JoyY = dy / maxR;
                    PostInvalidate();
                }
                else if (id == _camPointerId)
                {
                    float dx = px - _camLastX, dy = py - _camLastY;
                    _camLastX = px;
                    _camLastY = py;
                    float sens = 0.0052f * _renderer.CameraSensitivity;
                    if (_renderer.Stage == AppSceneStage.Lobby)
                    {
                        _renderer.LobbyOrbitYaw = System.Math.Clamp(_renderer.LobbyOrbitYaw - dx * sens * 0.85f, -0.85f, 0.85f);
                        _renderer.LobbyAvatarSpinOffset += dx * sens * 0.65f;
                    }
                    else
                    {
                        _renderer.CamYaw -= dx * sens;
                        _renderer.CamPitch = System.Math.Clamp(_renderer.CamPitch + dy * sens * 0.72f, 0.06f, 0.88f);
                    }
                }
            }
            return true;
        }
        else if (action == MotionEventActions.Up || action == MotionEventActions.PointerUp || action == MotionEventActions.Cancel)
        {
            if (action == MotionEventActions.Cancel || pid == _joyPointerId)
            {
                _joyPointerId = -1;
                _renderer.JoyX = 0f;
                _renderer.JoyY = 0f;
                PostInvalidate();
            }
            if (action == MotionEventActions.Cancel || pid == _camPointerId)
            {
                _camPointerId = -1;
            }
            return true;
        }
        return true;
    }
}
