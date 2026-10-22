using System;
using System.Collections.Generic;
using Android.Content;
using Android.Graphics;
using Android.Views;
using Nyawit.AndroidClient.Rendering;
using NyawitEngine.Core;
using NyawitEngine.Network;
using NyawitEngine.World;

namespace Nyawit.AndroidClient.UI;

public sealed class HudOverlayView : View
{
    private readonly Gles3InstancedRenderer _renderer;
    private readonly LiveMultiplayerSession _net;
    private readonly Typeface _displayFont;
    private readonly Bitmap? _brandSmallMark;

    private readonly Paint _panelPaint = new(PaintFlags.AntiAlias);
    private readonly Paint _strokePaint = new(PaintFlags.AntiAlias);
    private readonly Paint _textPaint = new(PaintFlags.AntiAlias);
    private readonly Paint _titlePaint = new(PaintFlags.AntiAlias);

    private int _joyPointerId = -1;
    private float _joyOriginX, _joyOriginY, _joyKnobX, _joyKnobY;
    private int _camPointerId = -1;
    private float _camLastX, _camLastY;

    private string _toastText = "";
    private long _toastUntilMs;

    private readonly List<(RectF Rect, Action Tap, string Label, Color Bg)> _hitZones = new(16);

    public event Action? OnOpenChat;
    public event Action? OnOpenRankings;
    public event Action? OnOpenAvatar;
    public event Action? OnOpenDaily;
    public event Action? OnOpenSocialShare;
    public event Action? OnHarvestPressed;
    public event Action? OnSellPressed;
    public event Action? OnTruckTogglePressed;
    public event Action? OnHornPressed;

    public HudOverlayView(
        Context context,
        Gles3InstancedRenderer renderer,
        LiveMultiplayerSession net,
        Typeface displayFont,
        Bitmap? brandSmallMark) : base(context)
    {
        _renderer = renderer;
        _net = net;
        _displayFont = displayFont;
        _brandSmallMark = brandSmallMark;
        SetWillNotDraw(false);

        _strokePaint.SetStyle(Paint.Style.Stroke);
        _titlePaint.SetTypeface(_displayFont);
    }

    public void ShowToast(string msg)
    {
        _toastText = msg;
        _toastUntilMs = Java.Lang.JavaSystem.CurrentTimeMillis() + 3000;
    }

    protected override void OnDraw(Canvas canvas)
    {
        base.OnDraw(canvas);
        float w = Width, h = Height;
        float dp = Resources?.DisplayMetrics?.Density ?? 2.5f;

        _hitZones.Clear();

        // 1. Projected 3D Player Nameplates & Live Speech Bubbles
        lock (_renderer.HudLock)
        {
            foreach (var lbl in _renderer.ProjectedLabels)
            {
                DrawProjectedNameplate(canvas, lbl, dp);
            }
        }

        // 2. Top-Left XyVerse Live HUD & Economy Bar
        float pad = 12 * dp;
        var card = new RectF(pad, pad, pad + 300 * dp, pad + 76 * dp);
        DrawGlassCard(canvas, card, new Color(11, 13, 16, 205), new Color(255, 255, 255, 42), 14 * dp);

        float textX = card.Left + 12 * dp;
        if (_brandSmallMark != null)
        {
            float ms = 24 * dp;
            canvas.DrawBitmap(_brandSmallMark, null, new RectF(textX, card.Top + 10 * dp, textX + ms, card.Top + 10 * dp + ms), null);
            textX += ms + 8 * dp;
        }

        _titlePaint.TextSize = 13.5f * dp;
        _titlePaint.Color = Color.White;
        canvas.DrawText("NYAWIT LIVE 3D", textX, card.Top + 26 * dp, _titlePaint);

        _textPaint.TextSize = 10.5f * dp;
        _textPaint.FakeBoldText = true;
        _textPaint.Color = _net.IsConnected ? new Color(46, 204, 113) : new Color(245, 176, 65);
        int onlineCount = 1 + _net.RemotePeerCount;
        canvas.DrawText(
            $"{(_net.IsConnected ? "LIVE ONLINE" : "OFFLINE MODE")}  |  {onlineCount} PEMAIN  |  {_renderer.Quality.CurrentFps} FPS  |  {_renderer.LastDrawCalls} DC",
            card.Left + 12 * dp, card.Top + 46 * dp, _textPaint);

        _textPaint.Color = new Color(245, 176, 65);
        int cap = _renderer.InTruck ? 24 : 12;
        canvas.DrawText(
            $"Rp {_net.Profile.Coins:N0}   |   {_net.Profile.Gems} GEM   |   TBS {_net.LocalCargo}/{cap}",
            card.Left + 12 * dp, card.Top + 65 * dp, _textPaint);

        // 3. Top-Center World Event Banner + Graphics Preset Selector
        var evRect = new RectF(w * 0.5f - 125 * dp, pad, w * 0.5f + 125 * dp, pad + 30 * dp);
        DrawGlassCard(canvas, evRect, new Color(245, 176, 65, 45), new Color(245, 176, 65, 160), 15 * dp);
        _titlePaint.TextSize = 10.5f * dp;
        _titlePaint.Color = new Color(245, 176, 65);
        _titlePaint.TextAlign = Paint.Align.Center;
        canvas.DrawText(_net.EventTitle.ToUpperInvariant(), evRect.CenterX(), evRect.CenterY() + 4 * dp, _titlePaint);
        _titlePaint.TextAlign = Paint.Align.Left;

        string[] qNames = ["SMOOTH", "STD", "ULTRA", "MAX"];
        float qW = 54 * dp, qGap = 5 * dp;
        float qStartX = w * 0.5f - (qW * 4 + qGap * 3) * 0.5f;
        for (int i = 0; i < 4; i++)
        {
            var qr = new RectF(qStartX + i * (qW + qGap), pad + 35 * dp, qStartX + i * (qW + qGap) + qW, pad + 59 * dp);
            bool active = (int)_renderer.Quality.CurrentPreset == i;
            DrawGlassCard(canvas, qr, active ? new Color(46, 204, 113, 235) : new Color(11, 13, 16, 185), new Color(255, 255, 255, 50), 8 * dp);
            _textPaint.TextSize = 9.5f * dp;
            _textPaint.Color = active ? Color.Black : Color.White;
            _textPaint.TextAlign = Paint.Align.Center;
            canvas.DrawText(qNames[i], qr.CenterX(), qr.CenterY() + 3.5f * dp, _textPaint);
            _textPaint.TextAlign = Paint.Align.Left;
            int presetIdx = i;
            _hitZones.Add((qr, () => { _renderer.Quality.SetManualPreset((GraphicsPreset)presetIdx); ShowToast($"Grafik: {qNames[presetIdx]}"); }, qNames[i], Color.Transparent));
        }

        // 4. Top-Right Tactical Minimap + Feature Menu Strip
        float mapSize = 104 * dp;
        var mapRect = new RectF(w - pad - mapSize, pad, w - pad, pad + mapSize);
        DrawMinimap(canvas, mapRect, dp);

        (string label, Action act, bool badge)[] menus =
        [
            ("CHAT", () => OnOpenChat?.Invoke(), false),
            ("RANK & TURNAMEN", () => OnOpenRankings?.Invoke(), false),
            ("AVATAR 3D", () => OnOpenAvatar?.Invoke(), false),
            ("REWARD HARIAN", () => OnOpenDaily?.Invoke(), _net.Profile.CanClaimDaily),
            ("LOGIN & SHARE", () => OnOpenSocialShare?.Invoke(), false),
        ];
        float btnW = 112 * dp, btnH = 29 * dp;
        for (int i = 0; i < menus.Length; i++)
        {
            float bx = mapRect.Left - 8 * dp - btnW;
            float by = pad + i * (btnH + 5 * dp);
            var mr = new RectF(bx, by, bx + btnW, by + btnH);
            DrawGlassCard(canvas, mr, menus[i].badge ? new Color(230, 126, 34, 225) : new Color(11, 13, 16, 205), new Color(255, 255, 255, 55), 9 * dp);
            _textPaint.TextSize = 9.8f * dp;
            _textPaint.Color = Color.White;
            _textPaint.TextAlign = Paint.Align.Center;
            canvas.DrawText(menus[i].label, mr.CenterX(), mr.CenterY() + 3.5f * dp, _textPaint);
            _textPaint.TextAlign = Paint.Align.Left;
            _hitZones.Add((mr, menus[i].act, menus[i].label, Color.Transparent));
        }

        // 5. Left Virtual Analog Thumbstick
        float joyR = 54 * dp;
        float baseCx = _joyPointerId != -1 ? _joyOriginX : 96 * dp;
        float baseCy = _joyPointerId != -1 ? _joyOriginY : h - 92 * dp;
        float knobCx = _joyPointerId != -1 ? _joyKnobX : baseCx;
        float knobCy = _joyPointerId != -1 ? _joyKnobY : baseCy;

        _panelPaint.Color = new Color(255, 255, 255, 28);
        canvas.DrawCircle(baseCx, baseCy, joyR, _panelPaint);
        _strokePaint.StrokeWidth = 2 * dp;
        _strokePaint.Color = new Color(255, 255, 255, 95);
        canvas.DrawCircle(baseCx, baseCy, joyR, _strokePaint);

        _panelPaint.Color = new Color(245, 176, 65, 230);
        canvas.DrawCircle(knobCx, knobCy, 23 * dp, _panelPaint);

        // 6. Bottom-Right Ergonomic Free-Fire Action Buttons
        DrawActionCircle(canvas, w - 84 * dp, h - 82 * dp, 44 * dp,
            _renderer.NearestRipeTreeId >= 0 ? new Color(46, 204, 113, 240) : new Color(39, 174, 96, 135),
            "PANEN!", dp, () => OnHarvestPressed?.Invoke());

        DrawActionCircle(canvas, w - 182 * dp, h - 66 * dp, 36 * dp,
            _renderer.NearRamWeighbridge ? new Color(245, 176, 65, 245) : new Color(180, 125, 30, 130),
            "SETOR PKS", dp, () => OnSellPressed?.Invoke());

        DrawActionCircle(canvas, w - 174 * dp, h - 154 * dp, 33 * dp,
            new Color(52, 152, 219, 225),
            _renderer.InTruck ? "TURUN" : "CANTER", dp, () => OnTruckTogglePressed?.Invoke());

        DrawActionCircle(canvas, w - 82 * dp, h - 182 * dp, 31 * dp,
            new Color(230, 126, 34, 225),
            "KLAKSON", dp, () => OnHornPressed?.Invoke());

        // 7. Toast Feedback Pill
        if (!string.IsNullOrEmpty(_toastText) && Java.Lang.JavaSystem.CurrentTimeMillis() < _toastUntilMs)
        {
            var tr = new RectF(w * 0.5f - 175 * dp, h - 54 * dp, w * 0.5f + 175 * dp, h - 20 * dp);
            DrawGlassCard(canvas, tr, new Color(11, 13, 16, 232), new Color(245, 176, 65, 190), 16 * dp);
            _textPaint.TextSize = 11 * dp;
            _textPaint.Color = new Color(245, 176, 65);
            _textPaint.TextAlign = Paint.Align.Center;
            canvas.DrawText(_toastText, tr.CenterX(), tr.CenterY() + 4 * dp, _textPaint);
            _textPaint.TextAlign = Paint.Align.Left;
        }

        PostInvalidateOnAnimation();
    }

    private void DrawProjectedNameplate(Canvas canvas, ProjectedLabel lbl, float dp)
    {
        _textPaint.TextAlign = Paint.Align.Center;
        _textPaint.TextSize = 10.5f * dp;
        float tw = System.Math.Max(_textPaint.MeasureText(lbl.Name) + 18 * dp, 74 * dp);
        var nr = new RectF(lbl.ScreenX - tw * 0.5f, lbl.ScreenY - 22 * dp, lbl.ScreenX + tw * 0.5f, lbl.ScreenY + 2 * dp);
        DrawGlassCard(canvas, nr, new Color(8, 10, 14, 185), lbl.IsSelf ? new Color(46, 204, 113, 160) : new Color(255, 255, 255, 45), 7 * dp);
        _textPaint.Color = lbl.IsSelf ? new Color(130, 255, 175) : Color.White;
        canvas.DrawText(lbl.Name, lbl.ScreenX, lbl.ScreenY - 6 * dp, _textPaint);

        if (!string.IsNullOrEmpty(lbl.BubbleText))
        {
            float bw = System.Math.Min(220 * dp, _textPaint.MeasureText(lbl.BubbleText) + 22 * dp);
            var br = new RectF(lbl.ScreenX - bw * 0.5f, lbl.ScreenY - 52 * dp, lbl.ScreenX + bw * 0.5f, lbl.ScreenY - 26 * dp);
            DrawGlassCard(canvas, br, new Color(255, 255, 255, 240), new Color(245, 176, 65, 200), 10 * dp);
            _textPaint.Color = Color.Black;
            canvas.DrawText(lbl.BubbleText, lbl.ScreenX, lbl.ScreenY - 35 * dp, _textPaint);
        }
        _textPaint.TextAlign = Paint.Align.Left;
    }

    private void DrawMinimap(Canvas canvas, RectF r, float dp)
    {
        DrawGlassCard(canvas, r, new Color(14, 34, 20, 225), new Color(255, 255, 255, 65), 12 * dp);
        float scale = r.Width() / 215f;
        float cx = r.CenterX(), cy = r.CenterY();

        // Canal strip
        _panelPaint.Color = new Color(34, 132, 148, 180);
        float cz = cy + PlantationWorld.CanalZ * scale;
        canvas.DrawRect(r.Left + 3 * dp, cz - 2 * dp, r.Right - 3 * dp, cz + 2 * dp, _panelPaint);

        // PKS & RAM markers
        _panelPaint.Color = new Color(245, 176, 65);
        canvas.DrawRect(cx - 4 * dp, cy + PlantationWorld.RamZ * scale - 4 * dp, cx + 4 * dp, cy + PlantationWorld.RamZ * scale + 4 * dp, _panelPaint);

        // Golden Sawit 24K trees on radar
        for (int i = 0; i < _renderer.Trees.Count; i++)
        {
            var t = _renderer.Trees[i];
            if (t.State != 2) continue;
            canvas.DrawCircle(cx + t.X * scale, cy + t.Z * scale, 1.8f * dp, _panelPaint);
        }

        // Live remote peers
        _panelPaint.Color = new Color(86, 204, 242);
        lock (_renderer.HudLock)
        {
            foreach (var p in _renderer.MinimapPeers)
                canvas.DrawCircle(cx + p.X * scale, cy + p.Z * scale, 2.8f * dp, _panelPaint);
        }

        // Self dot
        _panelPaint.Color = new Color(46, 204, 113);
        canvas.DrawCircle(cx + _renderer.PlayerX * scale, cy + _renderer.PlayerZ * scale, 3.6f * dp, _panelPaint);
    }

    private void DrawActionCircle(Canvas canvas, float cx, float cy, float radius, Color fill, string label, float dp, Action onTap)
    {
        _panelPaint.Color = fill;
        canvas.DrawCircle(cx, cy, radius, _panelPaint);
        _strokePaint.StrokeWidth = 2.2f * dp;
        _strokePaint.Color = new Color(255, 255, 255, 125);
        canvas.DrawCircle(cx, cy, radius, _strokePaint);

        _titlePaint.TextSize = 9.5f * dp;
        _titlePaint.Color = Color.White;
        _titlePaint.TextAlign = Paint.Align.Center;
        canvas.DrawText(label, cx, cy + 3.5f * dp, _titlePaint);
        _titlePaint.TextAlign = Paint.Align.Left;

        _hitZones.Add((new RectF(cx - radius, cy - radius, cx + radius, cy + radius), onTap, label, fill));
    }

    private void DrawGlassCard(Canvas canvas, RectF rect, Color bg, Color border, float radius)
    {
        _panelPaint.Color = bg;
        canvas.DrawRoundRect(rect, radius, radius, _panelPaint);
        _strokePaint.StrokeWidth = 1.4f;
        _strokePaint.Color = border;
        canvas.DrawRoundRect(rect, radius, radius, _strokePaint);
    }

    public override bool OnTouchEvent(MotionEvent? e)
    {
        if (e == null) return false;
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
                    PerformHapticFeedback(FeedbackConstants.KeyboardTap);
                    _hitZones[i].Tap();
                    return true;
                }
            }

            if (x < Width * 0.45f && _joyPointerId == -1)
            {
                _joyPointerId = pid;
                _joyOriginX = _joyKnobX = x;
                _joyOriginY = _joyKnobY = y;
                _renderer.JoyX = _renderer.JoyY = 0f;
            }
            else if (_camPointerId == -1)
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
                if (id == _joyPointerId)
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
