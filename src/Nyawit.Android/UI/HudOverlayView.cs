using System;
using System.Collections.Generic;
using Android.Content;
using Android.Graphics;
using Android.Runtime;
using Android.Views;
using Nyawit.AndroidClient.Audio;
using Nyawit.AndroidClient.Rendering;
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
}

/// <summary>
/// 100% Sharp-Angled Tactical Cyber-Industrial HUD, 3D Main Lobby &amp; "MENYIAPKAN DUNIA" Loading View.
/// Zero bubble circles, zero emojis anywhere — every button &amp; badge renders crisp vector paths!
/// </summary>
public sealed class HudOverlayView : View
{
    private readonly Gles3InstancedRenderer? _renderer;
    private readonly LiveMultiplayerSession? _net;
    private readonly ProceduralSfxPlayer? _sfx;
    private readonly VoiceChatManager? _voice;
    private readonly Typeface _displayFont = Typeface.DefaultBold!;
    private readonly Typeface _uiBoldFont = Typeface.Create("sans-serif-condensed", TypefaceStyle.Bold) ?? Typeface.DefaultBold!;
    private readonly Bitmap? _brandSmallMark;

    private readonly Paint _fillPaint = new(PaintFlags.AntiAlias);
    private readonly Paint _strokePaint = new(PaintFlags.AntiAlias);
    private readonly Paint _iconPaint = new(PaintFlags.AntiAlias);
    private readonly Paint _textPaint = new(PaintFlags.AntiAlias);
    private readonly Paint _titlePaint = new(PaintFlags.AntiAlias);
    private readonly Path _tmpPath = new();
    private readonly Path _iconPath = new();

    private int _joyPointerId = -1;
    private float _joyOriginX, _joyOriginY, _joyKnobX, _joyKnobY;
    private int _camPointerId = -1;
    private float _camLastX, _camLastY;

    private string _toastText = "";
    private long _toastUntilMs;

    private readonly List<(RectF Rect, Action Tap)> _hitZones = new(32);

    // Public screen coordinates exposed for deterministic automated emulator verification too!
    public RectF LastEnterWorldButtonRect { get; private set; } = new();
    public RectF LastPickupOrLoadButtonRect { get; private set; } = new();
    public RectF LastHarvestButtonRect { get; private set; } = new();
    public RectF LastTruckButtonRect { get; private set; } = new();

    public event Action? OnEnterWorldRequested;
    public event Action? OnReturnLobbyRequested;
    public event Action? OnToggleVoiceMic;
    public event Action? OnOpenChat;
    public event Action? OnOpenRankings;
    public event Action? OnOpenAvatar;
    public event Action? OnOpenDaily;
    public event Action? OnOpenSocialShare;
    public event Action? OnHarvestPressed;
    public event Action? OnPickupOrLoadPressed;
    public event Action? OnAngkongTogglePressed;
    public event Action? OnSellPressed;
    public event Action? OnTruckTogglePressed;
    public event Action? OnHornPressed;

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
        Bitmap? brandSmallMark) : base(context)
    {
        _renderer = renderer;
        _net = net;
        _sfx = sfx;
        _voice = voice;
        _displayFont = displayFont ?? Typeface.DefaultBold!;
        _brandSmallMark = brandSmallMark;
        SetWillNotDraw(false);

        _strokePaint.SetStyle(Paint.Style.Stroke);
        _iconPaint.SetStyle(Paint.Style.Stroke);
        _iconPaint.StrokeCap = Paint.Cap.Square;
        _iconPaint.StrokeJoin = Paint.Join.Miter;

        // XyVerse Brand Rule: XyVerseDisplay strictly for pure A-Z uppercase display headlines;
        // _uiBoldFont handles numbers, stats, percentages & labels cleanly with zero missing glyphs!
        _titlePaint.SetTypeface(_displayFont);
        _textPaint.SetTypeface(_uiBoldFont);
    }

    public void ShowToast(string msg)
    {
        _toastText = msg.ToUpperInvariant();
        _toastUntilMs = Java.Lang.JavaSystem.CurrentTimeMillis() + 3100;
    }

    protected override void OnDraw(Canvas canvas)
    {
        base.OnDraw(canvas);
        if (_renderer == null || _net == null) return;

        float w = Width, h = Height;
        if (w <= 1f || h <= 1f) return;
        float dp = Resources?.DisplayMetrics?.Density ?? 2.5f;

        _hitZones.Clear();

        float pad = 12 * dp;
        float cutoutLeft = 0f;
        if (OperatingSystem.IsAndroidVersionAtLeast(28))
            cutoutLeft = RootWindowInsets?.DisplayCutout?.SafeInsetLeft ?? 0f;
        float leftPad = System.Math.Max(pad, cutoutLeft + 8 * dp);

        if (_renderer.Stage == AppSceneStage.Lobby)
        {
            DrawMainLobbyOverlay(canvas, w, h, leftPad, pad, dp);
        }
        else if (_renderer.Stage == AppSceneStage.PreparingWorld)
        {
            DrawPreparingWorldScreen(canvas, w, h, leftPad, pad, dp);
        }
        else
        {
            DrawGameplayHud(canvas, w, h, leftPad, pad, dp);
        }

        DrawToastBanner(canvas, w, h, dp);
        PostInvalidateOnAnimation();
    }

    // =========================================================================
    //  SCREEN 1: INTERACTIVE 3D MAIN LOBBY SHOWCASE SCREEN
    // =========================================================================
    private void DrawMainLobbyOverlay(Canvas canvas, float w, float h, float leftPad, float pad, float dp)
    {
        if (_renderer == null || _net == null) return;

        // Subtle left & right tactical gradient vignette while keeping center 3D Avatar + Canter crystal clear!
        _fillPaint.Color = new Color(7, 11, 13, 128);
        canvas.DrawRect(0, 0, leftPad + 272 * dp, h, _fillPaint);
        canvas.DrawRect(w - pad - 248 * dp, 0, w, h, _fillPaint);

        // 1. Left Column: Brand Header + Player Profile Card + Multi-Room Server Selector
        var hdr = new RectF(leftPad, pad, leftPad + 258 * dp, pad + 78 * dp);
        DrawChamferedPanel(canvas, hdr, new Color(11, 15, 18, 232), new Color(48, 232, 138, 225), 9 * dp, accentLeft: true);

        float tx = hdr.Left + 12 * dp;
        if (_brandSmallMark != null && !_brandSmallMark.IsRecycled)
        {
            float ms = 26 * dp;
            canvas.DrawBitmap(_brandSmallMark, null, new RectF(tx, hdr.Top + 11 * dp, tx + ms, hdr.Top + 11 * dp + ms), null);
            tx += ms + 9 * dp;
        }
        _titlePaint.TextSize = 14.5f * dp;
        _titlePaint.Color = Color.White;
        canvas.DrawText("NYAWIT LIVE", tx, hdr.Top + 27 * dp, _titlePaint);

        _textPaint.TextSize = 9.5f * dp;
        _textPaint.Color = new Color(48, 232, 138);
        canvas.DrawText($"SERVER API: {(_net.IsConnected ? "ONLINE TERHUBUNG" : "MENGHUBUNGKAN...")}  //  {_net.PingMs} MS", hdr.Left + 12 * dp, hdr.Top + 47 * dp, _textPaint);

        _textPaint.Color = new Color(246, 195, 56);
        canvas.DrawText($"RP {_net.Profile.Coins:N0}   //   {_net.Profile.Gems} GEM   //   {_net.Profile.TotalKg:N0} KG", hdr.Left + 12 * dp, hdr.Top + 66 * dp, _textPaint);

        // Player Call-Sign Card
        var profRect = new RectF(leftPad, hdr.Bottom + 8 * dp, leftPad + 258 * dp, hdr.Bottom + 54 * dp);
        DrawChamferedPanel(canvas, profRect, new Color(14, 21, 24, 226), new Color(255, 255, 255, 68), 7 * dp);
        DrawVectorIcon(canvas, VectorIconKind.AvatarHelm, profRect.Left + 22 * dp, profRect.CenterY(), 11 * dp, new Color(48, 232, 138), dp);
        _textPaint.TextSize = 11.2f * dp;
        _textPaint.Color = Color.White;
        canvas.DrawText(_net.Profile.Name.ToUpperInvariant(), profRect.Left + 40 * dp, profRect.Top + 20 * dp, _textPaint);
        _textPaint.TextSize = 9.2f * dp;
        _textPaint.Color = new Color(168, 196, 184);
        canvas.DrawText($"{_net.Profile.Avatar.Title.ToUpperInvariant()}  //  SKOR {_net.Profile.AllTimeScore:N0}", profRect.Left + 40 * dp, profRect.Top + 37 * dp, _textPaint);

        // Multi-Room Server Selector
        _textPaint.TextSize = 9.5f * dp;
        _textPaint.Color = new Color(152, 178, 168);
        canvas.DrawText("PILIH SERVER KEBUN MULTIPLAYER", leftPad + 2 * dp, profRect.Bottom + 18 * dp, _textPaint);

        var rooms = _net.GetRoomsSnapshot();
        float ry = profRect.Bottom + 24 * dp;
        float rh = 38 * dp;
        for (int i = 0; i < rooms.Count && i < 3; i++)
        {
            var rm = rooms[i];
            bool selected = rm.Id == _net.CurrentRoomId;
            var rr = new RectF(leftPad, ry, leftPad + 258 * dp, ry + rh);
            DrawChamferedPanel(
                canvas, rr,
                selected ? new Color(22, 68, 46, 238) : new Color(12, 17, 20, 216),
                selected ? new Color(48, 232, 138, 245) : new Color(255, 255, 255, 52),
                6 * dp, accentLeft: selected);

            _fillPaint.Color = selected ? new Color(48, 232, 138) : new Color(246, 195, 56);
            canvas.DrawRect(rr.Left + 11 * dp, rr.CenterY() - 3 * dp, rr.Left + 17 * dp, rr.CenterY() + 3 * dp, _fillPaint);

            _textPaint.TextSize = 10.0f * dp;
            _textPaint.Color = Color.White;
            canvas.DrawText(rm.Label, rr.Left + 25 * dp, rr.Top + 16 * dp, _textPaint);
            _textPaint.TextSize = 8.6f * dp;
            _textPaint.Color = selected ? new Color(138, 250, 192) : new Color(160, 175, 170);
            int liveCount = selected ? System.Math.Max(rm.Online, 1 + _net.RemotePeerCount) : rm.Online;
            canvas.DrawText($"{rm.Region}  //  {liveCount}/{rm.Capacity} AKTIF", rr.Left + 25 * dp, rr.Top + 31 * dp, _textPaint);

            string capturedRoom = rm.Id;
            string capturedLabel = rm.Label;
            RegisterButton(rr, () =>
            {
                _net.SelectRoom(capturedRoom);
                ShowToast($"TERHUBUNG KE ROOM {capturedLabel}");
            });
            ry += rh + 6 * dp;
        }

        // Center Showcase Hint Badge
        var rotHint = new RectF(w * 0.5f - 118 * dp, h - pad - 28 * dp, w * 0.5f + 118 * dp, h - pad);
        DrawChamferedPanel(canvas, rotHint, new Color(10, 14, 16, 196), new Color(255, 255, 255, 64), 5 * dp);
        _textPaint.TextAlign = Paint.Align.Center;
        _textPaint.TextSize = 9.0f * dp;
        _textPaint.Color = new Color(210, 228, 220);
        canvas.DrawText("GESER LAYAR TENGAH: PUTAR 3D AVATAR & CANTER", rotHint.CenterX(), rotHint.CenterY() + 3.2f * dp, _textPaint);
        _textPaint.TextAlign = Paint.Align.Left;

        // 2. Right Column: Sharp Tactical Feature Modules + Quality Preset Bar + Giant "MASUK KEBUN" Launch Button
        float rx0 = w - pad - 232 * dp;
        float rw = 232 * dp;
        (string label, VectorIconKind icon, Action act, bool highlight)[] lobbyMenus =
        [
            ("KUSTOMISASI AVATAR 3D", VectorIconKind.AvatarHelm, () => OnOpenAvatar?.Invoke(), false),
            ("RANKING & TURNAMEN", VectorIconKind.Trophy, () => OnOpenRankings?.Invoke(), false),
            ("REWARD HARIAN 7-HARI", VectorIconKind.DailyCrate, () => OnOpenDaily?.Invoke(), _net.Profile.CanClaimDaily),
            ("GLOBAL CHAT & SUARA", VectorIconKind.ChatBox, () => OnOpenChat?.Invoke(), false),
            ("AKUN SOSMED & SHARE", VectorIconKind.ShareNodes, () => OnOpenSocialShare?.Invoke(), false),
        ];

        float my = pad;
        float mh = 33 * dp;
        for (int i = 0; i < lobbyMenus.Length; i++)
        {
            var mr = new RectF(rx0, my, rx0 + rw, my + mh);
            bool hi = lobbyMenus[i].highlight;
            DrawChamferedPanel(
                canvas, mr,
                hi ? new Color(84, 52, 12, 232) : new Color(12, 17, 21, 224),
                hi ? new Color(246, 195, 56, 235) : new Color(255, 255, 255, 68),
                6 * dp);
            DrawVectorIcon(canvas, lobbyMenus[i].icon, mr.Left + 18 * dp, mr.CenterY(), 8.5f * dp, hi ? new Color(246, 195, 56) : new Color(48, 232, 138), dp);
            _textPaint.TextSize = 9.8f * dp;
            _textPaint.Color = Color.White;
            canvas.DrawText(lobbyMenus[i].label, mr.Left + 34 * dp, mr.CenterY() + 3.5f * dp, _textPaint);
            RegisterButton(mr, lobbyMenus[i].act);
            my += mh + 5 * dp;
        }

        // Graphics Preset Strip in Lobby
        string[] qNames = ["SMOOTH", "STD", "ULTRA", "MAX HD"];
        float qw = (rw - 12 * dp) / 4f;
        for (int i = 0; i < 4; i++)
        {
            var qr = new RectF(rx0 + i * (qw + 4 * dp), my + 2 * dp, rx0 + i * (qw + 4 * dp) + qw, my + 26 * dp);
            bool active = (int)_renderer.Quality.CurrentPreset == i;
            DrawChamferedPanel(canvas, qr, active ? new Color(48, 232, 138, 240) : new Color(12, 17, 21, 215), new Color(255, 255, 255, 65), 4 * dp);
            _textPaint.TextAlign = Paint.Align.Center;
            _textPaint.TextSize = 8.4f * dp;
            _textPaint.Color = active ? Color.Black : Color.White;
            canvas.DrawText(qNames[i], qr.CenterX(), qr.CenterY() + 3 * dp, _textPaint);
            _textPaint.TextAlign = Paint.Align.Left;
            int qi = i;
            RegisterButton(qr, () =>
            {
                _renderer.RequestPresetChange((GraphicsPreset)qi);
                ShowToast($"GRAFIK {qNames[qi]} AKTIF");
            });
        }

        // Primary Sharp Chamfered Launch Button: "MASUK KEBUN"
        var playRect = new RectF(rx0, h - pad - 62 * dp, rx0 + rw, h - pad);
        LastEnterWorldButtonRect = playRect;
        DrawChamferedPanel(canvas, playRect, new Color(38, 206, 118, 248), new Color(246, 214, 88, 255), 11 * dp, accentLeft: true);
        DrawVectorIcon(canvas, VectorIconKind.PlayChevron, playRect.Left + 26 * dp, playRect.CenterY(), 13 * dp, new Color(8, 14, 12), dp);
        _titlePaint.TextSize = 15.5f * dp;
        _titlePaint.Color = new Color(8, 14, 12);
        canvas.DrawText("MASUK KEBUN", playRect.Left + 46 * dp, playRect.Top + 31 * dp, _titlePaint);
        _textPaint.TextSize = 8.8f * dp;
        _textPaint.Color = new Color(10, 32, 22);
        canvas.DrawText("MULAI PANEN & TRUK CANTER LIVE", playRect.Left + 46 * dp, playRect.Top + 49 * dp, _textPaint);
        RegisterButton(playRect, () => OnEnterWorldRequested?.Invoke());
    }

    // =========================================================================
    //  SCREEN 2: "MENYIAPKAN DUNIA..." TACTICAL WORLD PREPARATION LOADING SCREEN
    // =========================================================================
    private void DrawPreparingWorldScreen(Canvas canvas, float w, float h, float leftPad, float pad, float dp)
    {
        if (_renderer == null || _net == null) return;

        // Atmospheric dark tactical letterbox bars so the live 3D aerial plantation fly-in shines!
        _fillPaint.Color = new Color(6, 10, 12, 168);
        canvas.DrawRect(0, 0, w, 62 * dp, _fillPaint);
        canvas.DrawRect(0, h - 134 * dp, w, h, _fillPaint);

        // Top Bar Brand Stamp
        float tx = leftPad;
        if (_brandSmallMark != null && !_brandSmallMark.IsRecycled)
        {
            float ms = 24 * dp;
            canvas.DrawBitmap(_brandSmallMark, null, new RectF(tx, 18 * dp, tx + ms, 18 * dp + ms), null);
            tx += ms + 10 * dp;
        }
        _titlePaint.TextSize = 14 * dp;
        _titlePaint.Color = Color.White;
        canvas.DrawText("NYAWIT LIVE", tx, 36 * dp, _titlePaint);

        _textPaint.TextAlign = Paint.Align.Right;
        _textPaint.TextSize = 9.8f * dp;
        _textPaint.Color = new Color(48, 232, 138);
        canvas.DrawText($"ROOM AKTIF: {_net.CurrentRoomId.ToUpperInvariant()}  //  FISIKA 60HZ", w - pad, 35 * dp, _textPaint);
        _textPaint.TextAlign = Paint.Align.Left;

        // Bottom Sharp Loading Telemetry Frame
        var box = new RectF(leftPad + 36 * dp, h - 118 * dp, w - pad - 36 * dp, h - 22 * dp);
        DrawChamferedPanel(canvas, box, new Color(10, 15, 18, 240), new Color(48, 232, 138, 235), 10 * dp, accentLeft: true);

        _titlePaint.TextSize = 16.5f * dp;
        _titlePaint.Color = Color.White;
        canvas.DrawText("MENYIAPKAN DUNIA", box.Left + 18 * dp, box.Top + 28 * dp, _titlePaint);

        int pct = System.Math.Clamp((int)MathF.Round(_renderer.WorldPrepProgress * 100f), 0, 100);
        _textPaint.TextAlign = Paint.Align.Right;
        _textPaint.TextSize = 15.0f * dp;
        _textPaint.Color = new Color(246, 195, 56);
        canvas.DrawText($"{pct}%", box.Right - 18 * dp, box.Top + 28 * dp, _textPaint);
        _textPaint.TextAlign = Paint.Align.Left;

        _textPaint.TextSize = 9.8f * dp;
        _textPaint.Color = new Color(148, 240, 192);
        canvas.DrawText(_renderer.WorldPrepStatus, box.Left + 18 * dp, box.Top + 47 * dp, _textPaint);

        // Sharp Segmented Progress Bar
        var barBg = new RectF(box.Left + 18 * dp, box.Top + 56 * dp, box.Right - 18 * dp, box.Top + 70 * dp);
        _fillPaint.Color = new Color(26, 38, 42, 255);
        canvas.DrawRect(barBg, _fillPaint);
        _strokePaint.StrokeWidth = 1.2f * dp;
        _strokePaint.Color = new Color(255, 255, 255, 65);
        canvas.DrawRect(barBg, _strokePaint);

        float fillW = (barBg.Width() - 4 * dp) * System.Math.Clamp(_renderer.WorldPrepProgress, 0f, 1f);
        if (fillW > 1f)
        {
            _fillPaint.Color = new Color(48, 232, 138, 255);
            canvas.DrawRect(barBg.Left + 2 * dp, barBg.Top + 2 * dp, barBg.Left + 2 * dp + fillW, barBg.Bottom - 2 * dp, _fillPaint);
        }

        _textPaint.TextSize = 8.6f * dp;
        _textPaint.Color = new Color(178, 196, 190);
        canvas.DrawText("PANDUAN: TEBANG SAWIT -> AMBIL TBS DI TANAH -> MUAT KE BAK TRUK CANTER / ANGKONG -> SETOR DI RAM PKS", box.Left + 18 * dp, box.Top + 86 * dp, _textPaint);
    }

    // =========================================================================
    //  SCREEN 3: SHARP-ANGLED TACTICAL GAMEPLAY HUD + VECTOR ICONS + VOICE + PHYSICS TELEMETRY
    // =========================================================================
    private void DrawGameplayHud(Canvas canvas, float w, float h, float leftPad, float pad, float dp)
    {
        if (_renderer == null || _net == null) return;
        var player = _renderer.Physics.Player;
        var truck = _renderer.Physics.MainTruck;

        // 1. Projected 3D Player Nameplates, Voice Indicators & Sharp Speech Boxes
        lock (_renderer.HudLock)
        {
            foreach (var lbl in _renderer.ProjectedLabels)
            {
                DrawProjectedNameplate(canvas, lbl.ScreenX * w, lbl.ScreenY * h, lbl.Name, lbl.BubbleText, lbl.IsSelf, lbl.IsSpeaking, dp);
            }
        }

        // 2. Top-Left Sharp Tactical Status & Economy Card
        var card = new RectF(leftPad, pad, leftPad + 306 * dp, pad + 76 * dp);
        DrawChamferedPanel(canvas, card, new Color(10, 14, 17, 224), new Color(48, 232, 138, 185), 8 * dp, accentLeft: true);

        float textX = card.Left + 11 * dp;
        if (_brandSmallMark != null && !_brandSmallMark.IsRecycled)
        {
            float ms = 22 * dp;
            canvas.DrawBitmap(_brandSmallMark, null, new RectF(textX, card.Top + 9 * dp, textX + ms, card.Top + 9 * dp + ms), null);
            textX += ms + 8 * dp;
        }

        _titlePaint.TextSize = 13.0f * dp;
        _titlePaint.Color = Color.White;
        canvas.DrawText("NYAWIT LIVE", textX, card.Top + 24 * dp, _titlePaint);

        _textPaint.TextSize = 9.4f * dp;
        _textPaint.Color = _net.IsConnected ? new Color(48, 232, 138) : new Color(246, 195, 56);
        int onlineCount = 1 + _net.RemotePeerCount;
        canvas.DrawText(
            $"{(_net.IsConnected ? "ONLINE" : "OFFLINE")}  //  {onlineCount} PEMAIN  //  {_renderer.Quality.CurrentFps} FPS  //  {_renderer.LastDrawCalls} DC",
            card.Left + 11 * dp, card.Top + 44 * dp, _textPaint);

        int shownTruckCargo = System.Math.Max(_net.LocalCargo, truck.VisualCargoUnits);
        _textPaint.Color = new Color(246, 195, 56);
        canvas.DrawText(
            $"RP {_net.Profile.Coins:N0}  //  TANGAN {player.HeldTbsUnits}/6  //  BAK {shownTruckCargo}/24",
            card.Left + 11 * dp, card.Top + 63 * dp, _textPaint);

        // 3. Top-Center Event Banner + Graphics Bar + Live Canter Speed / Suspension Telemetry
        var evRect = new RectF(w * 0.5f - 126 * dp, pad, w * 0.5f + 126 * dp, pad + 26 * dp);
        DrawChamferedPanel(canvas, evRect, new Color(18, 26, 22, 218), new Color(246, 195, 56, 200), 6 * dp);
        _textPaint.TextSize = 9.6f * dp;
        _textPaint.Color = new Color(246, 195, 56);
        _textPaint.TextAlign = Paint.Align.Center;
        canvas.DrawText(_net.EventTitle.ToUpperInvariant(), evRect.CenterX(), evRect.CenterY() + 3.5f * dp, _textPaint);

        string[] qNames = ["SMOOTH", "STD", "ULTRA", "MAX HD"];
        float qW = 55 * dp, qGap = 4 * dp;
        float qStartX = w * 0.5f - (qW * 4 + qGap * 3) * 0.5f;
        for (int i = 0; i < 4; i++)
        {
            var qr = new RectF(qStartX + i * (qW + qGap), pad + 30 * dp, qStartX + i * (qW + qGap) + qW, pad + 52 * dp);
            bool active = (int)_renderer.Quality.CurrentPreset == i;
            DrawChamferedPanel(canvas, qr, active ? new Color(48, 232, 138, 240) : new Color(10, 14, 17, 204), new Color(255, 255, 255, 62), 4 * dp);
            _textPaint.TextSize = 8.6f * dp;
            _textPaint.Color = active ? Color.Black : Color.White;
            canvas.DrawText(qNames[i], qr.CenterX(), qr.CenterY() + 3.2f * dp, _textPaint);
            int presetIdx = i;
            RegisterButton(qr, () =>
            {
                _renderer.RequestPresetChange((GraphicsPreset)presetIdx);
                ShowToast($"GRAFIK {qNames[presetIdx]} AKTIF");
            });
        }

        if (_renderer.InTruck)
        {
            int kmh = (int)MathF.Round(MathF.Abs(truck.SpeedMs) * 3.6f);
            int steerDeg = (int)MathF.Round(truck.SteerAngle * 180f / MathF.PI);
            int rollDeg = (int)MathF.Round(truck.RollRad * 180f / MathF.PI);
            var telRect = new RectF(w * 0.5f - 126 * dp, pad + 56 * dp, w * 0.5f + 126 * dp, pad + 79 * dp);
            DrawChamferedPanel(canvas, telRect, new Color(10, 18, 26, 224), new Color(44, 196, 248, 200), 5 * dp);
            _textPaint.TextSize = 9.0f * dp;
            _textPaint.Color = new Color(118, 224, 255);
            canvas.DrawText($"{kmh} KM/J  //  BELOK {steerDeg} DEG  //  OLENG {rollDeg} DEG", telRect.CenterX(), telRect.CenterY() + 3.2f * dp, _textPaint);
        }
        _textPaint.TextAlign = Paint.Align.Left;

        // 4. Top-Right Sharp Square Tactical Minimap + Vector-Icon Menu Strip
        float mapSize = 104 * dp;
        var mapRect = new RectF(w - pad - mapSize, pad, w - pad, pad + mapSize);
        DrawSharpMinimap(canvas, mapRect, dp);

        bool micOn = _voice?.IsMicTransmitting == true;
        (string label, VectorIconKind icon, Action act, bool accent)[] menus =
        [
            ("LOBBY", VectorIconKind.LobbyGrid, () => OnReturnLobbyRequested?.Invoke(), false),
            (micOn ? "MIC AKTIF" : "VOICE OFF", micOn ? VectorIconKind.MicOn : VectorIconKind.MicMuted, () => OnToggleVoiceMic?.Invoke(), micOn),
            ("CHAT", VectorIconKind.ChatBox, () => OnOpenChat?.Invoke(), false),
            ("RANKING", VectorIconKind.Trophy, () => OnOpenRankings?.Invoke(), false),
            ("AVATAR", VectorIconKind.AvatarHelm, () => OnOpenAvatar?.Invoke(), false),
            ("REWARD", VectorIconKind.DailyCrate, () => OnOpenDaily?.Invoke(), _net.Profile.CanClaimDaily),
        ];
        float btnW = 102 * dp, btnH = 26 * dp;
        for (int i = 0; i < menus.Length; i++)
        {
            float bx = mapRect.Left - 7 * dp - btnW;
            float by = pad + i * (btnH + 4 * dp);
            var mr = new RectF(bx, by, bx + btnW, by + btnH);
            bool hi = menus[i].accent;
            DrawChamferedPanel(
                canvas, mr,
                hi ? new Color(24, 92, 62, 236) : new Color(10, 14, 17, 214),
                hi ? new Color(48, 232, 138, 240) : new Color(255, 255, 255, 62),
                5 * dp);
            DrawVectorIcon(canvas, menus[i].icon, mr.Left + 14 * dp, mr.CenterY(), 7.2f * dp, hi ? new Color(110, 255, 180) : new Color(246, 195, 56), dp);
            _textPaint.TextSize = 8.8f * dp;
            _textPaint.Color = Color.White;
            canvas.DrawText(menus[i].label, mr.Left + 27 * dp, mr.CenterY() + 3.2f * dp, _textPaint);
            RegisterButton(mr, menus[i].act);
        }

        // 5. Bottom-Left Sharp Octagonal Tactical Analog Pad (ZERO circular bubbles!)
        float joyR = 52 * dp;
        float baseCx = _joyPointerId != -1 ? _joyOriginX : 96 * dp;
        float baseCy = _joyPointerId != -1 ? _joyOriginY : h - 90 * dp;
        float knobCx = _joyPointerId != -1 ? _joyKnobX : baseCx;
        float knobCy = _joyPointerId != -1 ? _joyKnobY : baseCy;

        DrawOctagonPad(canvas, baseCx, baseCy, joyR, knobCx, knobCy, dp);

        // 6. Bottom-Right Sharp Chamfered Tactical Action Pad with Custom Vector Icons!
        // Primary Action [PANEN]
        var harvestRect = new RectF(w - pad - 102 * dp, h - pad - 92 * dp, w - pad, h - pad);
        LastHarvestButtonRect = harvestRect;
        DrawTacticalButton(
            canvas, harvestRect,
            active: _renderer.NearestRipeTreeId >= 0,
            fillActive: new Color(36, 198, 112, 244),
            fillIdle: new Color(18, 48, 34, 212),
            border: new Color(88, 250, 162, 240),
            icon: VectorIconKind.HarvestSickle,
            label: "PANEN",
            sub: _renderer.NearestRipeTreeId >= 0 ? "SIAP TEBANG" : "CARI POHON",
            dp: dp,
            onTap: () => OnHarvestPressed?.Invoke());

        // Dynamic Pickup / Carry / Load Button [AMBIL TBS / MUAT TRUK / ISI ANGKONG]
        string pickLabel = "AMBIL TBS";
        string pickSub = _renderer.NearbyGroundFruitCount > 0 ? $"ADA {_renderer.NearbyGroundFruitCount} TBS" : "DEKATI TBS";
        VectorIconKind pickIcon = VectorIconKind.PickupTbs;
        bool pickReady = _renderer.NearbyGroundFruitCount > 0;
        Color pickFill = new Color(36, 152, 224, 240);

        if (_renderer.CanLoadIntoVehicleOrCart)
        {
            bool toTruck = _renderer.Physics.IsNearMainTruck(5.6f);
            pickLabel = toTruck ? "MUAT TRUK" : "ISI ANGKONG";
            pickSub = toTruck ? "LEMPAR KE BAK" : "TARUH GEROBAK";
            pickIcon = VectorIconKind.LoadTruck;
            pickReady = true;
            pickFill = new Color(242, 168, 30, 246);
        }
        else if (player.HasHeldTbs && _renderer.NearbyGroundFruitCount == 0)
        {
            pickLabel = "PEGANG TBS";
            pickSub = $"BAWA {player.HeldTbsUnits} KE TRUK";
            pickIcon = VectorIconKind.LoadTruck;
            pickReady = true;
            pickFill = new Color(36, 152, 224, 232);
        }

        var pickupRect = new RectF(harvestRect.Left - 8 * dp - 100 * dp, h - pad - 76 * dp, harvestRect.Left - 8 * dp, h - pad);
        LastPickupOrLoadButtonRect = pickupRect;
        DrawTacticalButton(
            canvas, pickupRect,
            active: pickReady,
            fillActive: pickFill,
            fillIdle: new Color(16, 28, 38, 212),
            border: new Color(96, 214, 255, 225),
            icon: pickIcon,
            label: pickLabel,
            sub: pickSub,
            dp: dp,
            onTap: () => OnPickupOrLoadPressed?.Invoke());

        // [SETOR PKS] Button
        var sellRect = new RectF(pickupRect.Left - 8 * dp - 92 * dp, h - pad - 68 * dp, pickupRect.Left - 8 * dp, h - pad);
        DrawTacticalButton(
            canvas, sellRect,
            active: _renderer.NearRamWeighbridge,
            fillActive: new Color(244, 184, 34, 248),
            fillIdle: new Color(46, 36, 16, 206),
            border: new Color(250, 208, 78, 225),
            icon: VectorIconKind.SellPks,
            label: "SETOR PKS",
            sub: _renderer.NearRamWeighbridge ? "JUAL SEKARANG" : "KE RAM PKS",
            dp: dp,
            onTap: () => OnSellPressed?.Invoke());

        // Upper Row Action Buttons: [ANGKONG] + [NAIK CANTER / TURUN] + [BASURI]
        var hornRect = new RectF(w - pad - 92 * dp, harvestRect.Top - 8 * dp - 58 * dp, w - pad, harvestRect.Top - 8 * dp);
        DrawTacticalButton(
            canvas, hornRect,
            active: true,
            fillActive: new Color(214, 96, 28, 232),
            fillIdle: new Color(214, 96, 28, 232),
            border: new Color(255, 166, 78, 220),
            icon: VectorIconKind.BasuriHorn,
            label: "BASURI",
            sub: "KLAKSON + GAS",
            dp: dp,
            onTap: () => OnHornPressed?.Invoke());

        var truckRect = new RectF(hornRect.Left - 8 * dp - 96 * dp, pickupRect.Top - 8 * dp - 58 * dp, hornRect.Left - 8 * dp, pickupRect.Top - 8 * dp);
        LastTruckButtonRect = truckRect;
        DrawTacticalButton(
            canvas, truckRect,
            active: true,
            fillActive: _renderer.InTruck ? new Color(206, 58, 62, 236) : new Color(28, 128, 198, 236),
            fillIdle: new Color(28, 128, 198, 236),
            border: new Color(118, 216, 255, 225),
            icon: _renderer.InTruck ? VectorIconKind.SteeringWheel : VectorIconKind.CanterTruck,
            label: _renderer.InTruck ? "TURUN" : "CANTER",
            sub: _renderer.InTruck ? "JALAN KAKI" : "KEMUDI TRUK",
            dp: dp,
            onTap: () => OnTruckTogglePressed?.Invoke());

        bool pushingCart = player.ActiveAngkongIndex >= 0;
        if (!_renderer.InTruck && (_renderer.NearbyAngkongId >= 0 || pushingCart))
        {
            var cartRect = new RectF(truckRect.Left - 8 * dp - 92 * dp, sellRect.Top - 8 * dp - 58 * dp, truckRect.Left - 8 * dp, sellRect.Top - 8 * dp);
            DrawTacticalButton(
                canvas, cartRect,
                active: true,
                fillActive: pushingCart ? new Color(206, 58, 62, 236) : new Color(24, 152, 168, 236),
                fillIdle: new Color(24, 152, 168, 236),
                border: new Color(96, 238, 245, 225),
                icon: VectorIconKind.Angkong,
                label: pushingCart ? "LEPAS" : "ANGKONG",
                sub: pushingCart ? "PARKIR" : "DORONG",
                dp: dp,
                onTap: () => OnAngkongTogglePressed?.Invoke());
        }
    }

    private void DrawToastBanner(Canvas canvas, float w, float h, float dp)
    {
        if (string.IsNullOrEmpty(_toastText) || Java.Lang.JavaSystem.CurrentTimeMillis() >= _toastUntilMs) return;
        float tw = System.Math.Clamp(_textPaint.MeasureText(_toastText) + 42 * dp, 220 * dp, 430 * dp);
        var tr = new RectF(w * 0.5f - tw * 0.5f, 88 * dp, w * 0.5f + tw * 0.5f, 118 * dp);
        DrawChamferedPanel(canvas, tr, new Color(8, 13, 16, 238), new Color(246, 195, 56, 235), 6 * dp, accentLeft: true);
        _textPaint.TextSize = 9.8f * dp;
        _textPaint.Color = new Color(248, 206, 82);
        _textPaint.TextAlign = Paint.Align.Center;
        canvas.DrawText(_toastText, tr.CenterX(), tr.CenterY() + 3.5f * dp, _textPaint);
        _textPaint.TextAlign = Paint.Align.Left;
    }

    private void DrawProjectedNameplate(Canvas canvas, float sx, float sy, string name, string bubble, bool isSelf, bool speaking, float dp)
    {
        _textPaint.TextAlign = Paint.Align.Center;
        _textPaint.TextSize = 9.8f * dp;
        string tag = speaking ? $"[SUARA] {name.ToUpperInvariant()}" : name.ToUpperInvariant();
        float tw = System.Math.Max(_textPaint.MeasureText(tag) + 20 * dp, 74 * dp);
        var nr = new RectF(sx - tw * 0.5f, sy - 21 * dp, sx + tw * 0.5f, sy + 2 * dp);
        DrawChamferedPanel(
            canvas, nr,
            new Color(8, 12, 16, 196),
            speaking ? new Color(48, 255, 152, 245) : (isSelf ? new Color(48, 232, 138, 190) : new Color(255, 255, 255, 70)),
            4 * dp);
        _textPaint.Color = isSelf ? new Color(136, 255, 188) : Color.White;
        canvas.DrawText(tag, sx, sy - 5.5f * dp, _textPaint);

        if (!string.IsNullOrEmpty(bubble))
        {
            float bw = System.Math.Min(230 * dp, _textPaint.MeasureText(bubble) + 22 * dp);
            var br = new RectF(sx - bw * 0.5f, sy - 49 * dp, sx + bw * 0.5f, sy - 25 * dp);
            DrawChamferedPanel(canvas, br, new Color(246, 248, 250, 245), new Color(246, 195, 56, 230), 5 * dp);
            _textPaint.Color = new Color(12, 16, 20);
            canvas.DrawText(bubble, sx, sy - 33.5f * dp, _textPaint);
        }
        _textPaint.TextAlign = Paint.Align.Left;
    }

    private void DrawSharpMinimap(Canvas canvas, RectF r, float dp)
    {
        if (_renderer == null) return;
        DrawChamferedPanel(canvas, r, new Color(11, 26, 18, 234), new Color(48, 232, 138, 155), 7 * dp);
        float scale = r.Width() / 215f;
        float cx = r.CenterX(), cy = r.CenterY();

        // Crosshair tactical grid lines
        _strokePaint.StrokeWidth = 1f;
        _strokePaint.Color = new Color(255, 255, 255, 24);
        canvas.DrawLine(cx, r.Top + 4 * dp, cx, r.Bottom - 4 * dp, _strokePaint);
        canvas.DrawLine(r.Left + 4 * dp, cy, r.Right - 4 * dp, cy, _strokePaint);

        // Canal + 2 Wooden Bridges
        _fillPaint.Color = new Color(34, 146, 168, 205);
        float cz = cy + PlantationWorld.CanalZ * scale;
        canvas.DrawRect(r.Left + 3 * dp, cz - 2 * dp, r.Right - 3 * dp, cz + 2 * dp, _fillPaint);
        _fillPaint.Color = new Color(214, 154, 78);
        canvas.DrawRect(cx - 28f * scale - 2.5f * dp, cz - 3.5f * dp, cx - 28f * scale + 2.5f * dp, cz + 3.5f * dp, _fillPaint);
        canvas.DrawRect(cx + 28f * scale - 2.5f * dp, cz - 3.5f * dp, cx + 28f * scale + 2.5f * dp, cz + 3.5f * dp, _fillPaint);

        // RAM Weighbridge Square
        _fillPaint.Color = new Color(246, 195, 56);
        canvas.DrawRect(cx - 4 * dp, cy + PlantationWorld.RamZ * scale - 4 * dp, cx + 4 * dp, cy + PlantationWorld.RamZ * scale + 4 * dp, _fillPaint);

        // Golden Trees
        for (int i = 0; i < _renderer.Trees.Count; i++)
        {
            var t = _renderer.Trees[i];
            if (t.State != 2) continue;
            float gx = cx + t.X * scale, gz = cy + t.Z * scale;
            canvas.DrawRect(gx - 1.5f * dp, gz - 1.5f * dp, gx + 1.5f * dp, gz + 1.5f * dp, _fillPaint);
        }

        // Main Canter Marker (Amber Square)
        _fillPaint.Color = new Color(255, 196, 36);
        float txm = cx + _renderer.Physics.MainTruck.X * scale, tzm = cy + _renderer.Physics.MainTruck.Z * scale;
        canvas.DrawRect(txm - 3 * dp, tzm - 3 * dp, txm + 3 * dp, tzm + 3 * dp, _fillPaint);

        // Remote Peers (Cyan Diamonds)
        _fillPaint.Color = new Color(76, 214, 255);
        lock (_renderer.HudLock)
        {
            foreach (var p in _renderer.MinimapPeers)
            {
                float px = cx + p.X * scale, pz = cy + p.Z * scale;
                canvas.DrawRect(px - 2.5f * dp, pz - 2.5f * dp, px + 2.5f * dp, pz + 2.5f * dp, _fillPaint);
            }
        }

        // Local Player Marker (Bright Emerald Diamond)
        _fillPaint.Color = new Color(48, 255, 148);
        float lx = cx + _renderer.PlayerX * scale, lz = cy + _renderer.PlayerZ * scale;
        _tmpPath.Reset();
        _tmpPath.MoveTo(lx, lz - 4.5f * dp);
        _tmpPath.LineTo(lx + 4.5f * dp, lz);
        _tmpPath.LineTo(lx, lz + 4.5f * dp);
        _tmpPath.LineTo(lx - 4.5f * dp, lz);
        _tmpPath.Close();
        canvas.DrawPath(_tmpPath, _fillPaint);
    }

    private void DrawOctagonPad(Canvas canvas, float cx, float cy, float r, float kx, float ky, float dp)
    {
        BuildOctagonPath(_tmpPath, cx, cy, r);
        _fillPaint.Color = new Color(10, 16, 20, 164);
        canvas.DrawPath(_tmpPath, _fillPaint);
        _strokePaint.StrokeWidth = 2.0f * dp;
        _strokePaint.Color = new Color(48, 232, 138, 165);
        canvas.DrawPath(_tmpPath, _strokePaint);

        // Tactical crosshair ticks inside joystick pad
        _strokePaint.StrokeWidth = 1.2f * dp;
        _strokePaint.Color = new Color(255, 255, 255, 65);
        canvas.DrawLine(cx - r * 0.72f, cy, cx + r * 0.72f, cy, _strokePaint);
        canvas.DrawLine(cx, cy - r * 0.72f, cx, cy + r * 0.72f, _strokePaint);

        // Sharp Beveled Octagon Thumb Knob
        BuildOctagonPath(_tmpPath, kx, ky, 21 * dp);
        _fillPaint.Color = new Color(246, 195, 56, 238);
        canvas.DrawPath(_tmpPath, _fillPaint);
        _strokePaint.StrokeWidth = 1.8f * dp;
        _strokePaint.Color = Color.White;
        canvas.DrawPath(_tmpPath, _strokePaint);
    }

    private static void BuildOctagonPath(Path p, float cx, float cy, float r)
    {
        p.Reset();
        float k = r * 0.4142f;
        p.MoveTo(cx - k, cy - r);
        p.LineTo(cx + k, cy - r);
        p.LineTo(cx + r, cy - k);
        p.LineTo(cx + r, cy + k);
        p.LineTo(cx + k, cy + r);
        p.LineTo(cx - k, cy + r);
        p.LineTo(cx - r, cy + k);
        p.LineTo(cx - r, cy - k);
        p.Close();
    }

    private void DrawTacticalButton(
        Canvas canvas,
        RectF rect,
        bool active,
        Color fillActive,
        Color fillIdle,
        Color border,
        VectorIconKind icon,
        string label,
        string sub,
        float dp,
        Action onTap)
    {
        DrawChamferedPanel(canvas, rect, active ? fillActive : fillIdle, active ? border : new Color(255, 255, 255, 72), 7 * dp);

        bool darkInk = active && (fillActive.R > 210 && fillActive.G > 165);
        Color fg = darkInk ? new Color(10, 14, 16) : Color.White;
        Color subCol = darkInk ? new Color(24, 34, 28) : new Color(210, 232, 224);

        DrawVectorIcon(canvas, icon, rect.CenterX(), rect.Top + rect.Height() * 0.34f, 10.5f * dp, fg, dp);

        _textPaint.TextAlign = Paint.Align.Center;
        _textPaint.TextSize = 9.8f * dp;
        _textPaint.Color = fg;
        canvas.DrawText(label, rect.CenterX(), rect.Bottom - 17 * dp, _textPaint);

        _textPaint.TextSize = 7.4f * dp;
        _textPaint.Color = subCol;
        canvas.DrawText(sub, rect.CenterX(), rect.Bottom - 6.5f * dp, _textPaint);
        _textPaint.TextAlign = Paint.Align.Left;

        RegisterButton(rect, onTap);
    }

    /// <summary>
    /// Draws a sharp chamfered polygon card with 45-degree diagonal cut corners (0 rounded bubble radius!).
    /// </summary>
    private void DrawChamferedPanel(Canvas canvas, RectF r, Color bg, Color border, float cut, bool accentLeft = false)
    {
        float c = System.Math.Min(cut, System.Math.Min(r.Width(), r.Height()) * 0.28f);
        _tmpPath.Reset();
        _tmpPath.MoveTo(r.Left + c, r.Top);
        _tmpPath.LineTo(r.Right, r.Top);
        _tmpPath.LineTo(r.Right, r.Bottom - c);
        _tmpPath.LineTo(r.Right - c, r.Bottom);
        _tmpPath.LineTo(r.Left, r.Bottom);
        _tmpPath.LineTo(r.Left, r.Top + c);
        _tmpPath.Close();

        _fillPaint.Color = bg;
        canvas.DrawPath(_tmpPath, _fillPaint);
        _strokePaint.StrokeWidth = 1.6f;
        _strokePaint.Color = border;
        canvas.DrawPath(_tmpPath, _strokePaint);

        if (accentLeft)
        {
            _fillPaint.Color = border;
            canvas.DrawRect(r.Left, r.Top + c, r.Left + 3.5f, r.Bottom, _fillPaint);
        }
    }

    /// <summary>
    /// Pure procedural geometric vector icon renderer — ZERO emojis anywhere!
    /// </summary>
    private void DrawVectorIcon(Canvas canvas, VectorIconKind kind, float cx, float cy, float s, Color col, float dp)
    {
        _iconPaint.Color = col;
        _iconPaint.StrokeWidth = System.Math.Max(2.0f, 1.85f * dp);
        _iconPath.Reset();

        switch (kind)
        {
            case VectorIconKind.HarvestSickle:
                // Angled pole + curved steel Egrek sickle blade
                canvas.DrawLine(cx - s * 0.65f, cy + s * 0.75f, cx + s * 0.15f, cy - s * 0.25f, _iconPaint);
                _iconPath.MoveTo(cx + s * 0.15f, cy - s * 0.25f);
                _iconPath.LineTo(cx + s * 0.72f, cy - s * 0.72f);
                _iconPath.LineTo(cx + s * 0.15f, cy - s * 0.82f);
                _iconPath.LineTo(cx - s * 0.35f, cy - s * 0.45f);
                canvas.DrawPath(_iconPath, _iconPaint);
                break;

            case VectorIconKind.PickupTbs:
                // Spiky diamond TBS + upward grab arrows
                _iconPath.MoveTo(cx, cy - s * 0.25f);
                _iconPath.LineTo(cx + s * 0.55f, cy + s * 0.28f);
                _iconPath.LineTo(cx, cy + s * 0.78f);
                _iconPath.LineTo(cx - s * 0.55f, cy + s * 0.28f);
                _iconPath.Close();
                canvas.DrawPath(_iconPath, _iconPaint);
                canvas.DrawLine(cx, cy - s * 0.85f, cx, cy - s * 0.32f, _iconPaint);
                canvas.DrawLine(cx - s * 0.32f, cy - s * 0.56f, cx, cy - s * 0.85f, _iconPaint);
                canvas.DrawLine(cx + s * 0.32f, cy - s * 0.56f, cx, cy - s * 0.85f, _iconPaint);
                break;

            case VectorIconKind.LoadTruck:
                // Open truck bed box + curved throw arrow landing inside!
                canvas.DrawLine(cx - s * 0.75f, cy + s * 0.15f, cx - s * 0.75f, cy + s * 0.70f, _iconPaint);
                canvas.DrawLine(cx - s * 0.75f, cy + s * 0.70f, cx + s * 0.75f, cy + s * 0.70f, _iconPaint);
                canvas.DrawLine(cx + s * 0.75f, cy + s * 0.70f, cx + s * 0.75f, cy + s * 0.15f, _iconPaint);
                _iconPath.MoveTo(cx - s * 0.65f, cy - s * 0.20f);
                _iconPath.QuadTo(cx, cy - s * 0.95f, cx + s * 0.28f, cy + s * 0.22f);
                canvas.DrawPath(_iconPath, _iconPaint);
                break;

            case VectorIconKind.Angkong:
                // Wheelbarrow hopper + front wheel + handle
                _iconPath.MoveTo(cx - s * 0.75f, cy - s * 0.25f);
                _iconPath.LineTo(cx + s * 0.45f, cy - s * 0.25f);
                _iconPath.LineTo(cx + s * 0.22f, cy + s * 0.30f);
                _iconPath.LineTo(cx - s * 0.45f, cy + s * 0.30f);
                _iconPath.Close();
                canvas.DrawPath(_iconPath, _iconPaint);
                canvas.DrawLine(cx - s * 0.85f, cy - s * 0.45f, cx - s * 0.45f, cy + s * 0.30f, _iconPaint);
                canvas.DrawRect(cx + s * 0.32f, cy + s * 0.25f, cx + s * 0.72f, cy + s * 0.65f, _iconPaint);
                break;

            case VectorIconKind.CanterTruck:
                // Sharp Canter cab + cargo bed + 2 wheels
                canvas.DrawRect(cx - s * 0.82f, cy - s * 0.32f, cx + s * 0.15f, cy + s * 0.38f, _iconPaint);
                _iconPath.MoveTo(cx + s * 0.15f, cy - s * 0.15f);
                _iconPath.LineTo(cx + s * 0.62f, cy - s * 0.15f);
                _iconPath.LineTo(cx + s * 0.80f, cy + s * 0.38f);
                _iconPath.LineTo(cx + s * 0.15f, cy + s * 0.38f);
                canvas.DrawPath(_iconPath, _iconPaint);
                canvas.DrawRect(cx - s * 0.58f, cy + s * 0.38f, cx - s * 0.28f, cy + s * 0.68f, _iconPaint);
                canvas.DrawRect(cx + s * 0.32f, cy + s * 0.38f, cx + s * 0.62f, cy + s * 0.68f, _iconPaint);
                break;

            case VectorIconKind.SteeringWheel:
                BuildOctagonPath(_iconPath, cx, cy, s * 0.72f);
                canvas.DrawPath(_iconPath, _iconPaint);
                canvas.DrawLine(cx - s * 0.65f, cy, cx + s * 0.65f, cy, _iconPaint);
                canvas.DrawLine(cx, cy, cx, cy + s * 0.68f, _iconPaint);
                break;

            case VectorIconKind.SellPks:
                // Factory sawtooth roof + chimney + upward value arrow
                _iconPath.MoveTo(cx - s * 0.75f, cy + s * 0.70f);
                _iconPath.LineTo(cx - s * 0.75f, cy - s * 0.10f);
                _iconPath.LineTo(cx - s * 0.25f, cy - s * 0.45f);
                _iconPath.LineTo(cx - s * 0.25f, cy - s * 0.10f);
                _iconPath.LineTo(cx + s * 0.25f, cy - s * 0.45f);
                _iconPath.LineTo(cx + s * 0.25f, cy + s * 0.70f);
                _iconPath.Close();
                canvas.DrawPath(_iconPath, _iconPaint);
                canvas.DrawLine(cx + s * 0.62f, cy + s * 0.65f, cx + s * 0.62f, cy - s * 0.65f, _iconPaint);
                canvas.DrawLine(cx + s * 0.38f, cy - s * 0.35f, cx + s * 0.62f, cy - s * 0.65f, _iconPaint);
                break;

            case VectorIconKind.BasuriHorn:
                _iconPath.MoveTo(cx - s * 0.70f, cy - s * 0.20f);
                _iconPath.LineTo(cx - s * 0.15f, cy - s * 0.20f);
                _iconPath.LineTo(cx + s * 0.42f, cy - s * 0.65f);
                _iconPath.LineTo(cx + s * 0.42f, cy + s * 0.65f);
                _iconPath.LineTo(cx - s * 0.15f, cy + s * 0.20f);
                _iconPath.LineTo(cx - s * 0.70f, cy + s * 0.20f);
                _iconPath.Close();
                canvas.DrawPath(_iconPath, _iconPaint);
                canvas.DrawLine(cx + s * 0.72f, cy - s * 0.42f, cx + s * 0.72f, cy + s * 0.42f, _iconPaint);
                break;

            case VectorIconKind.MicOn:
            case VectorIconKind.MicMuted:
                canvas.DrawRect(cx - s * 0.32f, cy - s * 0.72f, cx + s * 0.32f, cy + s * 0.12f, _iconPaint);
                canvas.DrawLine(cx - s * 0.58f, cy + s * 0.35f, cx + s * 0.58f, cy + s * 0.35f, _iconPaint);
                canvas.DrawLine(cx, cy + s * 0.35f, cx, cy + s * 0.75f, _iconPaint);
                if (kind == VectorIconKind.MicMuted)
                    canvas.DrawLine(cx - s * 0.75f, cy - s * 0.75f, cx + s * 0.75f, cy + s * 0.75f, _iconPaint);
                break;

            case VectorIconKind.ChatBox:
                _iconPath.MoveTo(cx - s * 0.72f, cy - s * 0.58f);
                _iconPath.LineTo(cx + s * 0.72f, cy - s * 0.58f);
                _iconPath.LineTo(cx + s * 0.72f, cy + s * 0.32f);
                _iconPath.LineTo(cx - s * 0.12f, cy + s * 0.32f);
                _iconPath.LineTo(cx - s * 0.48f, cy + s * 0.72f);
                _iconPath.LineTo(cx - s * 0.48f, cy + s * 0.32f);
                _iconPath.LineTo(cx - s * 0.72f, cy + s * 0.32f);
                _iconPath.Close();
                canvas.DrawPath(_iconPath, _iconPaint);
                break;

            case VectorIconKind.Trophy:
                _iconPath.MoveTo(cx - s * 0.55f, cy - s * 0.68f);
                _iconPath.LineTo(cx + s * 0.55f, cy - s * 0.68f);
                _iconPath.LineTo(cx + s * 0.32f, cy + s * 0.12f);
                _iconPath.LineTo(cx - s * 0.32f, cy + s * 0.12f);
                _iconPath.Close();
                canvas.DrawPath(_iconPath, _iconPaint);
                canvas.DrawLine(cx, cy + s * 0.12f, cx, cy + s * 0.68f, _iconPaint);
                canvas.DrawLine(cx - s * 0.45f, cy + s * 0.68f, cx + s * 0.45f, cy + s * 0.68f, _iconPaint);
                break;

            case VectorIconKind.AvatarHelm:
                _iconPath.MoveTo(cx, cy - s * 0.75f);
                _iconPath.LineTo(cx + s * 0.65f, cy - s * 0.25f);
                _iconPath.LineTo(cx + s * 0.50f, cy + s * 0.68f);
                _iconPath.LineTo(cx - s * 0.50f, cy + s * 0.68f);
                _iconPath.LineTo(cx - s * 0.65f, cy - s * 0.25f);
                _iconPath.Close();
                canvas.DrawPath(_iconPath, _iconPaint);
                canvas.DrawLine(cx - s * 0.38f, cy - s * 0.05f, cx + s * 0.38f, cy - s * 0.05f, _iconPaint);
                break;

            case VectorIconKind.DailyCrate:
                canvas.DrawRect(cx - s * 0.65f, cy - s * 0.52f, cx + s * 0.65f, cy + s * 0.68f, _iconPaint);
                canvas.DrawLine(cx, cy - s * 0.52f, cx, cy + s * 0.68f, _iconPaint);
                canvas.DrawLine(cx - s * 0.65f, cy + s * 0.05f, cx + s * 0.65f, cy + s * 0.05f, _iconPaint);
                break;

            case VectorIconKind.ShareNodes:
                canvas.DrawLine(cx + s * 0.52f, cy - s * 0.55f, cx - s * 0.52f, cy, _iconPaint);
                canvas.DrawLine(cx - s * 0.52f, cy, cx + s * 0.52f, cy + s * 0.55f, _iconPaint);
                canvas.DrawRect(cx + s * 0.35f, cy - s * 0.72f, cx + s * 0.70f, cy - s * 0.38f, _iconPaint);
                canvas.DrawRect(cx - s * 0.70f, cy - s * 0.18f, cx - s * 0.35f, cy + s * 0.18f, _iconPaint);
                canvas.DrawRect(cx + s * 0.35f, cy + s * 0.38f, cx + s * 0.70f, cy + s * 0.72f, _iconPaint);
                break;

            case VectorIconKind.LobbyGrid:
                canvas.DrawRect(cx - s * 0.65f, cy - s * 0.65f, cx - s * 0.12f, cy - s * 0.12f, _iconPaint);
                canvas.DrawRect(cx + s * 0.12f, cy - s * 0.65f, cx + s * 0.65f, cy - s * 0.12f, _iconPaint);
                canvas.DrawRect(cx - s * 0.65f, cy + s * 0.12f, cx - s * 0.12f, cy + s * 0.65f, _iconPaint);
                canvas.DrawRect(cx + s * 0.12f, cy + s * 0.12f, cx + s * 0.65f, cy + s * 0.65f, _iconPaint);
                break;

            case VectorIconKind.PlayChevron:
                _fillPaint.Color = col;
                _iconPath.MoveTo(cx - s * 0.55f, cy - s * 0.75f);
                _iconPath.LineTo(cx + s * 0.72f, cy);
                _iconPath.LineTo(cx - s * 0.55f, cy + s * 0.75f);
                _iconPath.Close();
                canvas.DrawPath(_iconPath, _fillPaint);
                break;
        }
    }

    private void RegisterButton(RectF rect, Action onTap)
    {
        _hitZones.Add((rect, onTap));
    }

    public override bool OnTouchEvent(MotionEvent? e)
    {
        if (e == null || _renderer == null) return false;
        int action = (int)e.ActionMasked;
        int idx = e.ActionIndex;
        int pid = e.GetPointerId(idx);
        float x = e.GetX(idx), y = e.GetY(idx);
        float maxR = 52f * (Resources?.DisplayMetrics?.Density ?? 2.5f);

        if (action == (int)MotionEventActions.Down || action == (int)MotionEventActions.PointerDown)
        {
            for (int i = _hitZones.Count - 1; i >= 0; i--)
            {
                if (_hitZones[i].Rect.Contains(x, y))
                {
                    _sfx?.Play("ui_click");
                    try { PerformHapticFeedback(FeedbackConstants.KeyboardTap); } catch { }
                    _hitZones[i].Tap();
                    return true;
                }
            }

            if (_renderer.Stage == AppSceneStage.Lobby)
            {
                _camPointerId = pid;
                _camLastX = x;
                _camLastY = y;
                return true;
            }
            if (_renderer.Stage != AppSceneStage.Gameplay)
            {
                return true;
            }

            if (x < Width * 0.44f && _joyPointerId == -1)
            {
                _joyPointerId = pid;
                _joyOriginX = _joyKnobX = x;
                _joyOriginY = _joyKnobY = y;
                _renderer.JoyX = _renderer.JoyY = 0f;
            }
            else if (pid != _joyPointerId && _camPointerId == -1)
            {
                _camPointerId = pid;
                _camLastX = x;
                _camLastY = y;
            }
            return true;
        }

        if (action == (int)MotionEventActions.Move)
        {
            for (int p = 0; p < e.PointerCount; p++)
            {
                int id = e.GetPointerId(p);
                float px = e.GetX(p), py = e.GetY(p);
                if (_renderer.Stage == AppSceneStage.Lobby && id == _camPointerId)
                {
                    _renderer.LobbyAvatarSpinOffset += (px - _camLastX) * 0.012f;
                    _camLastX = px;
                    _camLastY = py;
                }
                else if (id == _joyPointerId)
                {
                    float dx = px - _joyOriginX, dy = py - _joyOriginY;
                    float dist = MathF.Sqrt(dx * dx + dy * dy);
                    if (dist > maxR) { dx = dx / dist * maxR; dy = dy / dist * maxR; }
                    _joyKnobX = _joyOriginX + dx;
                    _joyKnobY = _joyOriginY + dy;
                    _renderer.JoyX = dx / maxR;
                    _renderer.JoyY = dy / maxR;
                }
                else if (id == _camPointerId)
                {
                    _renderer.CamYaw -= (px - _camLastX) * 0.0065f;
                    _renderer.CamPitch = System.Math.Clamp(_renderer.CamPitch + (py - _camLastY) * 0.005f, 0.10f, 1.08f);
                    _camLastX = px;
                    _camLastY = py;
                }
            }
            return true;
        }

        if (action == (int)MotionEventActions.Up || action == (int)MotionEventActions.PointerUp || action == (int)MotionEventActions.Cancel)
        {
            if (pid == _joyPointerId || action == (int)MotionEventActions.Cancel)
            {
                _joyPointerId = -1;
                _renderer.JoyX = _renderer.JoyY = 0f;
            }
            if (pid == _camPointerId || action == (int)MotionEventActions.Cancel)
            {
                _camPointerId = -1;
            }
            return true;
        }
        return true;
    }
}
