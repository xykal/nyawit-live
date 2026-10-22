using System;
using System.Text;
using Android.App;
using Android.Content;
using Android.Content.PM;
using Android.Graphics;
using Android.Opengl;
using Android.OS;
using Android.Views;
using Android.Widget;
using Nyawit.AndroidClient.Audio;
using Nyawit.AndroidClient.Rendering;
using Nyawit.AndroidClient.UI;
using NyawitEngine.Assets;
using NyawitEngine.Network;
using NyawitEngine.World;

namespace Nyawit.AndroidClient;

[Activity(
    Label = "Nyawit Live 3D",
    MainLauncher = true,
    Exported = true,
    ScreenOrientation = ScreenOrientation.SensorLandscape,
    ConfigurationChanges = ConfigChanges.Orientation | ConfigChanges.ScreenSize | ConfigChanges.KeyboardHidden)]
public class MainActivity : Activity
{
    private GLSurfaceView? _glView;
    private Gles3InstancedRenderer? _renderer;
    private HudOverlayView? _hud;
    private LiveMultiplayerSession? _net;
    private ProceduralSfxPlayer? _sfx;
    private ISharedPreferences? _prefs;

    protected override void OnCreate(Bundle? savedInstanceState)
    {
        base.OnCreate(savedInstanceState);
        EnableImmersiveFullscreen();

        _prefs = GetSharedPreferences("nyawit_live_prefs", FileCreationMode.Private);

        // Load sculpted 29-model multi-LOD NPAK archive from APK assets
        NpakArchive archive;
        using (var assetStream = Assets!.Open("Meshes/nyawit_models.npak"))
        {
            archive = NpakArchive.Load(assetStream);
        }

        Typeface displayFont = Typeface.DefaultBold!;
        try { displayFont = Typeface.CreateFromAsset(Assets, "Fonts/XyVerseDisplay-Semibold.otf")!; } catch { }

        Bitmap? smallBrandMark = null;
        try
        {
            using var markStream = Assets.Open("Brand/mark_kecil_transparan_putih.png");
            smallBrandMark = BitmapFactory.DecodeStream(markStream);
        }
        catch { }

        var trees = PlantationWorld.GenerateTrees();
        _net = new LiveMultiplayerSession(trees);
        RestoreLocalProfile(_net.Profile);

        _sfx = new ProceduralSfxPlayer();
        _renderer = new Gles3InstancedRenderer(this, archive, trees, _net);

        _glView = new GLSurfaceView(this);
        _glView.SetEGLContextClientVersion(3);
        _glView.SetEGLConfigChooser(8, 8, 8, 8, 16, 0);
        _glView.PreserveEGLContextOnPause = true;
        _glView.SetRenderer(_renderer);
        _glView.RenderMode = Rendermode.Continuously;

        _hud = new HudOverlayView(this, _renderer, _net, displayFont, smallBrandMark);
        WireGameplayAndModalEvents();

        var root = new FrameLayout(this);
        root.AddView(_glView, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MatchParent, ViewGroup.LayoutParams.MatchParent));
        root.AddView(_hud, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MatchParent, ViewGroup.LayoutParams.MatchParent));
        SetContentView(root);

        _net.StartBackgroundConnect();
        _hud.ShowToast("Selamat datang di Kebun Nyawit Live 3D!");
    }

    private void WireGameplayAndModalEvents()
    {
        if (_hud == null || _renderer == null || _net == null || _sfx == null) return;

        _net.OnToast += msg => RunOnUiThread(() => _hud?.ShowToast(msg));
        _net.OnSoundTrigger += clip => _sfx?.Play(clip);
        _net.OnProfilePersisted += SaveLocalProfile;

        _hud.OnHarvestPressed += () =>
        {
            _renderer.ChopAnim = 1.0f;
            _sfx.Play("chop");
            if (_renderer.NearestRipeTreeId >= 0)
                _net.RequestHarvest(_renderer.NearestRipeTreeId, _renderer.InTruck);
            else
                _hud.ShowToast("Dekati pohon sawit matang dulu bre!");
        };

        _hud.OnSellPressed += () =>
        {
            if (_renderer.NearRamWeighbridge) _net.RequestSell();
            else _hud.ShowToast(_net.LocalCargo > 0 ? "Bawa TBS ke Timbangan RAM PKS di tengah!" : "Panen TBS sawit dulu bre!");
        };

        _hud.OnTruckTogglePressed += () =>
        {
            _renderer.InTruck = !_renderer.InTruck;
            _sfx.Play("horn");
            _hud.ShowToast(_renderer.InTruck ? "Naik Truk Canter Sawit (Muatan 24 TBS)!" : "Turun jalan kaki bawa Egrek!");
        };

        _hud.OnHornPressed += () =>
        {
            _renderer.BoostTimer = 2.6f;
            _sfx.Play("horn");
            _net.SendHorn();
            _hud.ShowToast("TELOLET! Turbo Diesel Aktif!");
        };

        _hud.OnOpenChat += ShowChatDialog;
        _hud.OnOpenRankings += ShowRankingsAndTournamentDialog;
        _hud.OnOpenAvatar += ShowAvatarCustomizerDialog;
        _hud.OnOpenDaily += ShowDailyRewardDialog;
        _hud.OnOpenSocialShare += ShowSocialAndShareDialog;
    }

    private void ShowChatDialog()
    {
        if (_net == null) return;
        var layout = CreateDialogContainer(out int pad);

        var logText = new TextView(this) { TextSize = 12.5f };
        logText.SetTextColor(Color.Argb(255, 225, 232, 240));
        var chats = new System.Collections.Generic.List<ChatMessageEntry>();
        _net.CopyRenderState(new(), new(), chats, 0f);
        var sb = new StringBuilder();
        foreach (var c in chats) sb.AppendLine($"[{c.SenderName}]: {c.Text}");
        if (sb.Length == 0) sb.AppendLine("Belum ada chat. Sapa pemanen lain sekarang!");
        logText.Text = sb.ToString();
        layout.AddView(logText);

        var input = new EditText(this) { Hint = "Ketik pesan ke semua pemain kebun..." };
        input.SetTextColor(Color.White);
        input.SetHintTextColor(Color.Gray);
        layout.AddView(input);

        string[] quick = ["Gas panen blok timur!", "Sawit Emas muncul bre!!", "Antri RAM PKS!", "Truk Canter oleng bos!"];
        foreach (var q in quick)
        {
            string msg = q;
            var b = CreateStyledButton($"Quick: {msg}", false);
            b.Click += (_, _) => { _net.SendChat(msg); _hud?.ShowToast("Chat terkirim!"); };
            layout.AddView(b);
        }

        new AlertDialog.Builder(this)
            .SetTitle("LIVE CHAT KEBUN & QUICK EMOTE")!
            .SetView(WrapScroll(layout))!
            .SetPositiveButton("KIRIM CHAT", (_, _) =>
            {
                string txt = (input.Text ?? "").Trim();
                if (!string.IsNullOrEmpty(txt)) _net.SendChat(txt);
            })!
            .SetNegativeButton("TUTUP", (_, _) => { })!
            .Show();
    }

    private void ShowRankingsAndTournamentDialog()
    {
        if (_net == null) return;
        _net.RefreshBoards();
        var (globalB, weeklyB, tiers) = _net.GetBoardsSnapshot();
        var layout = CreateDialogContainer(out _);

        long remSec = Math.Max(0, (_net.TournamentEndsAtMs - DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()) / 1000);
        var header = new TextView(this)
        {
            Text = $"TURNAMEN MINGGUAN ({_net.TournamentWeekId}) — Reset {remSec / 86400}h {(remSec % 86400) / 3600}j\nPoin Mingguanmu: {_net.Profile.WeeklyPoints:N0} Pts  |  Total Setoran: {_net.Profile.TotalKg:N0} Kg",
            TextSize = 13f
        };
        header.SetTextColor(Color.Argb(255, 245, 176, 65));
        layout.AddView(header);

        foreach (var t in tiers)
        {
            string tid = t.Id;
            bool claimed = _net.Profile.ClaimedTiers.Contains(tid);
            bool ready = _net.Profile.WeeklyPoints >= t.MinPts && !claimed;
            var btn = CreateStyledButton($"{t.Label} {(claimed ? "[DIKLAIM]" : ready ? "[KLAIM SEKARANG!]" : $"[{_net.Profile.WeeklyPoints}/{t.MinPts}]")}", ready);
            btn.Enabled = ready;
            btn.Click += (_, _) => _net.ClaimTournamentTier(tid);
            layout.AddView(btn);
        }

        var sb = new StringBuilder("\n--- TOP GLOBAL RANKING SEPANJANG MASA ---\n");
        foreach (var r in globalB)
            sb.AppendLine($"#{r.Rank}  {r.Name} ({r.Title}) — {r.TotalKg:N0} Kg | {r.Score:N0} Pts");

        sb.AppendLine("\n--- KLASEMEN TURNAMEN MINGGU INI ---");
        foreach (var r in weeklyB)
            sb.AppendLine($"#{r.Rank}  {r.Name} — {r.Score:N0} Poin ({r.TotalKg:N0} Kg)");

        var tv = new TextView(this) { Text = sb.ToString(), TextSize = 12f };
        tv.SetTextColor(Color.White);
        layout.AddView(tv);

        new AlertDialog.Builder(this)
            .SetTitle("GLOBAL RANKING & TURNAMEN MINGGUAN")!
            .SetView(WrapScroll(layout))!
            .SetPositiveButton("TUTUP", (_, _) => { })!
            .Show();
    }

    private void ShowAvatarCustomizerDialog()
    {
        if (_net == null) return;
        var layout = CreateDialogContainer(out _);
        var av = _net.Profile.Avatar;

        var nameEdit = new EditText(this) { Text = _net.Profile.Name, Hint = "Nama Panggilan 3D" };
        nameEdit.SetTextColor(Color.White);
        layout.AddView(nameEdit);

        (string id, string label)[] hats =
        [
            (MeshCatalog.HatCaping, "Topi Caping Bambu"),
            (MeshCatalog.HatSafety, "Helm Proyek Safety"),
            (MeshCatalog.HatHeadband, "Ikat Kepala Pendekar"),
            (MeshCatalog.HatCowboy, "Topi Koboi Juragan"),
            (MeshCatalog.HatCrownGold, "Mahkota Raja Sawit 24K")
        ];
        (string id, string label)[] backs =
        [
            (MeshCatalog.BackBasket, "Keranjang Rotan TBS"),
            (MeshCatalog.BackPack, "Ransel Taktis Lapangan"),
            (MeshCatalog.BackCape, "Jubah Mandor Sultan"),
            (MeshCatalog.BackWingsGold, "Sayap Emas Juara")
        ];
        (string id, string label)[] tools =
        [
            (MeshCatalog.ToolEgrek, "Egrek Galah Panjang"),
            (MeshCatalog.ToolDodos, "Dodos Baja Tajam"),
            (MeshCatalog.ToolEgrekDragon, "Sabit Naga Sawit 24K")
        ];
        string[] colors = ["#27AE60", "#E67E22", "#E74C3C", "#2980B9", "#8E44AD", "#F1C40F", "#16A085", "#ECF0F1"];

        string selHat = av.Hat, selBack = av.Back, selTool = av.Tool, selHex = av.OutfitHex;

        AddOptionGroup(layout, "PILIH TOPI 3D:", hats, id => { selHat = id; ApplyAvatarNow(); });
        AddOptionGroup(layout, "PILIH AKSESORIS PUNGGUNG 3D:", backs, id => { selBack = id; ApplyAvatarNow(); });
        AddOptionGroup(layout, "PILIH ALAT PANEN 3D:", tools, id => { selTool = id; ApplyAvatarNow(); });

        var colorRow = new LinearLayout(this) { Orientation = Orientation.Horizontal };
        foreach (var hex in colors)
        {
            string h = hex;
            var cb = new Button(this) { Text = " " };
            cb.SetBackgroundColor(Color.ParseColor(h));
            cb.Click += (_, _) => { selHex = h; ApplyAvatarNow(); };
            colorRow.AddView(cb, new LinearLayout.LayoutParams(90, 72) { RightMargin = 10 });
        }
        layout.AddView(colorRow);

        void ApplyAvatarNow()
        {
            _net.SaveAvatar((nameEdit.Text ?? _net.Profile.Name).Trim(), new AvatarConfig
            {
                Hat = selHat, Back = selBack, Tool = selTool, OutfitHex = selHex, Aura = av.Aura, Title = av.Title
            });
            _hud?.ShowToast("Avatar 3D langsung terpasang di semua pemain!");
        }

        new AlertDialog.Builder(this)
            .SetTitle("KUSTOMISASI AVATAR 3D LIVE")!
            .SetView(WrapScroll(layout))!
            .SetPositiveButton("SIMPAN AVATAR", (_, _) => ApplyAvatarNow())!
            .SetNegativeButton("TUTUP", (_, _) => { })!
            .Show();
    }

    private void ShowDailyRewardDialog()
    {
        if (_net == null) return;
        var layout = CreateDialogContainer(out _);
        string[] rewards =
        [
            "Hari 1: Rp 150.000 + 10 Permata",
            "Hari 2: Rp 250.000 + 15 Permata + Helm Safety",
            "Hari 3: Rp 400.000 + 25 Permata",
            "Hari 4: Rp 600.000 + 35 Permata + Aura Api",
            "Hari 5: Rp 850.000 + 50 Permata + Jetpack Sawit",
            "Hari 6: Rp 1.200.000 + 75 Permata",
            "Hari 7 JACKPOT: Rp 2.500.000 + 150 Permata + Sabit Emas!"
        ];
        var info = new TextView(this)
        {
            Text = $"Streak Login Saat Ini: {_net.Profile.StreakDay} Hari Berturut-turut!\n\n" + string.Join("\n", rewards),
            TextSize = 13f
        };
        info.SetTextColor(Color.White);
        layout.AddView(info);

        new AlertDialog.Builder(this)
            .SetTitle("REWARD HARIAN 7-HARI")!
            .SetView(WrapScroll(layout))!
            .SetPositiveButton(_net.Profile.CanClaimDaily ? "KLAIM REWARD HARI INI!" : "SUDAH DIKLAIM HARI INI", (_, _) =>
            {
                if (_net.Profile.CanClaimDaily) _net.ClaimDaily();
            })!
            .SetNegativeButton("TUTUP", (_, _) => { })!
            .Show();
    }

    private void ShowSocialAndShareDialog()
    {
        if (_net == null) return;
        var layout = CreateDialogContainer(out _);

        var handleInput = new EditText(this)
        {
            Text = string.IsNullOrEmpty(_net.Profile.SocialHandle) ? $"@{_net.Profile.Name.ToLowerInvariant()}" : _net.Profile.SocialHandle,
            Hint = "@username sosmed / email Google"
        };
        handleInput.SetTextColor(Color.White);
        layout.AddView(handleInput);

        string[] providers = ["google", "tiktok", "instagram", "x", "whatsapp"];
        foreach (var p in providers)
        {
            string prov = p;
            var btn = CreateStyledButton($"Login / Tautkan {prov.ToUpperInvariant()} (+30 Permata)", false);
            btn.Click += (_, _) => _net.LinkSocial(prov, _net.Profile.Name, (handleInput.Text ?? "@juragansawit").Trim());
            layout.AddView(btn);
        }

        var shareBtn = CreateStyledButton("BAGIKAN KARTU PENCAPAIAN KE SOSMED / WA!", true);
        shareBtn.Click += async (_, _) =>
        {
            _hud?.ShowToast("Menyiapkan link kartu pencapaian live...");
            var (url, text) = await _net.CreateShareCardAsync();
            RunOnUiThread(() =>
            {
                var sendIntent = new Intent(Intent.ActionSend);
                sendIntent.SetType("text/plain");
                sendIntent.PutExtra(Intent.ExtraSubject, "Pencapaian Nyawit Live 3D!");
                sendIntent.PutExtra(Intent.ExtraText, text);
                StartActivity(Intent.CreateChooser(sendIntent, "Bagikan Pencapaian Nyawit Live 3D"));
            });
        };
        layout.AddView(shareBtn);

        new AlertDialog.Builder(this)
            .SetTitle("LOGIN SOSIAL & SHARE PENCAPAIAN")!
            .SetView(WrapScroll(layout))!
            .SetPositiveButton("TUTUP", (_, _) => { })!
            .Show();
    }

    private void AddOptionGroup(LinearLayout parent, string heading, (string id, string label)[] items, Action<string> onPick)
    {
        var tv = new TextView(this) { Text = heading, TextSize = 11.5f };
        tv.SetTextColor(Color.Argb(255, 245, 176, 65));
        parent.AddView(tv);
        foreach (var (id, label) in items)
        {
            string captured = id;
            var b = CreateStyledButton(label, false);
            b.Click += (_, _) => onPick(captured);
            parent.AddView(b);
        }
    }

    private LinearLayout CreateDialogContainer(out int pad)
    {
        float dp = Resources?.DisplayMetrics?.Density ?? 2.5f;
        pad = (int)(16 * dp);
        var ll = new LinearLayout(this) { Orientation = Orientation.Vertical };
        ll.SetPadding(pad, pad, pad, pad);
        ll.SetBackgroundColor(Color.Argb(255, 16, 20, 26));
        return ll;
    }

    private ScrollView WrapScroll(View child)
    {
        var sv = new ScrollView(this);
        sv.AddView(child);
        return sv;
    }

    private Button CreateStyledButton(string text, bool highlightGold)
    {
        var b = new Button(this) { Text = text, TextSize = 11.5f };
        b.SetBackgroundColor(highlightGold ? Color.Argb(255, 245, 176, 65) : Color.Argb(255, 32, 42, 54));
        b.SetTextColor(highlightGold ? Color.Black : Color.White);
        var lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MatchParent, ViewGroup.LayoutParams.WrapContent) { TopMargin = 10 };
        b.LayoutParameters = lp;
        return b;
    }

    private void RestoreLocalProfile(PlayerProfile p)
    {
        if (_prefs == null) return;
        p.Id = _prefs.GetString("player_id", "") ?? "";
        p.Token = _prefs.GetString("player_token", "") ?? "";
        p.Name = _prefs.GetString("player_name", $"Juragan{Random.Shared.Next(100, 999)}") ?? "JuraganSawit";
        p.Avatar.Hat = _prefs.GetString("av_hat", "hat_caping") ?? "hat_caping";
        p.Avatar.Back = _prefs.GetString("av_back", "back_basket") ?? "back_basket";
        p.Avatar.Tool = _prefs.GetString("av_tool", "tool_egrek") ?? "tool_egrek";
        p.Avatar.OutfitHex = _prefs.GetString("av_hex", "#27AE60") ?? "#27AE60";
    }

    private void SaveLocalProfile()
    {
        if (_prefs == null || _net == null) return;
        var ed = _prefs.Edit()!;
        ed.PutString("player_id", _net.Profile.Id);
        ed.PutString("player_token", _net.Profile.Token);
        ed.PutString("player_name", _net.Profile.Name);
        ed.PutString("av_hat", _net.Profile.Avatar.Hat);
        ed.PutString("av_back", _net.Profile.Avatar.Back);
        ed.PutString("av_tool", _net.Profile.Avatar.Tool);
        ed.PutString("av_hex", _net.Profile.Avatar.OutfitHex);
        ed.Apply();
    }

    private void EnableImmersiveFullscreen()
    {
        if (Window == null) return;
        Window.AddFlags(WindowManagerFlags.KeepScreenOn);
        if (OperatingSystem.IsAndroidVersionAtLeast(30))
        {
            Window.SetDecorFitsSystemWindows(false);
            var controller = Window.InsetsController;
            if (controller != null)
            {
                controller.Hide(WindowInsets.Type.StatusBars() | WindowInsets.Type.NavigationBars());
                controller.SystemBarsBehavior = (int)WindowInsetsControllerBehavior.ShowTransientBarsBySwipe;
            }
        }
        else
        {
#pragma warning disable CA1422, CS0618
            Window.DecorView.SystemUiVisibility = (StatusBarVisibility)(
                SystemUiFlags.ImmersiveSticky | SystemUiFlags.Fullscreen | SystemUiFlags.HideNavigation | SystemUiFlags.LayoutFullscreen);
#pragma warning restore CA1422, CS0618
        }
    }

    protected override void OnResume()
    {
        base.OnResume();
        EnableImmersiveFullscreen();
        _glView?.OnResume();
    }

    protected override void OnPause()
    {
        _glView?.OnPause();
        base.OnPause();
    }

    protected override void OnDestroy()
    {
        _net?.Dispose();
        _sfx?.Dispose();
        base.OnDestroy();
    }
}
