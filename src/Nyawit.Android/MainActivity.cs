using System;
using System.IO;
using System.Text;
using Android;
using Android.App;
using Android.Content;
using Android.Content.PM;
using Android.Graphics;
using Android.Opengl;
using Android.OS;
using Android.Runtime;
using Android.Views;
using Android.Widget;
using Javax.Microedition.Khronos.Egl;
using Nyawit.AndroidClient.Audio;
using Nyawit.AndroidClient.Rendering;
using Nyawit.AndroidClient.UI;
using NyawitEngine.Assets;
using NyawitEngine.Network;
using NyawitEngine.World;
using EGLConfig = Javax.Microedition.Khronos.Egl.EGLConfig;
using EGLDisplay = Javax.Microedition.Khronos.Egl.EGLDisplay;

namespace Nyawit.AndroidClient;

/// <summary>
/// Universal resilient EGL config selector for Qualcomm Adreno, ARM Mali, PowerVR, Xclipse &amp; Virtio/SwiftShader GPUs.
/// </summary>
public sealed class SafeGles3ConfigChooser : Java.Lang.Object, GLSurfaceView.IEGLConfigChooser
{
    private const int EglRenderableType = 0x3040;
    private const int EglOpenGlEs3Bit = 0x0040;
    private const int EglOpenGlEs2Bit = 0x0004;

    public SafeGles3ConfigChooser() { }
    public SafeGles3ConfigChooser(IntPtr handle, JniHandleOwnership transfer) : base(handle, transfer) { }

    public EGLConfig ChooseConfig(IEGL10? egl, EGLDisplay? display)
    {
        if (egl == null || display == null)
            throw new InvalidOperationException("EGL display unavailable");

        int[][] candidates =
        [
            [
                IEGL10.EglRedSize, 8, IEGL10.EglGreenSize, 8, IEGL10.EglBlueSize, 8,
                IEGL10.EglDepthSize, 16,
                IEGL10.EglSampleBuffers, 1, IEGL10.EglSamples, 4,
                EglRenderableType, EglOpenGlEs3Bit,
                IEGL10.EglNone
            ],
            [
                IEGL10.EglRedSize, 8, IEGL10.EglGreenSize, 8, IEGL10.EglBlueSize, 8,
                IEGL10.EglDepthSize, 16,
                EglRenderableType, EglOpenGlEs3Bit,
                IEGL10.EglNone
            ],
            [
                IEGL10.EglRedSize, 5, IEGL10.EglGreenSize, 6, IEGL10.EglBlueSize, 5,
                IEGL10.EglDepthSize, 16,
                EglRenderableType, EglOpenGlEs2Bit,
                IEGL10.EglNone
            ],
        ];

        var configs = new EGLConfig[4];
        int[] num = new int[1];
        foreach (var spec in candidates)
        {
            if (egl.EglChooseConfig(display, spec, configs, configs.Length, num) && num[0] > 0 && configs[0] != null)
                return configs[0];
        }

        int[] fallback = [IEGL10.EglNone];
        if (egl.EglChooseConfig(display, fallback, configs, configs.Length, num) && num[0] > 0 && configs[0] != null)
            return configs[0];

        throw new InvalidOperationException("No compatible EGL config available");
    }
}

[Activity(
    Label = "Nyawit Live 3D",
    MainLauncher = true,
    Exported = true,
    ScreenOrientation = ScreenOrientation.SensorLandscape,
    ConfigurationChanges = ConfigChanges.Orientation | ConfigChanges.ScreenSize | ConfigChanges.SmallestScreenSize | ConfigChanges.ScreenLayout | ConfigChanges.KeyboardHidden | ConfigChanges.Density)]
public class MainActivity : Activity
{
    private const int ReqRecordAudio = 4102;

    private GLSurfaceView? _glView;
    private Gles3InstancedRenderer? _renderer;
    private HudOverlayView? _hud;
    private LiveMultiplayerSession? _net;
    private ProceduralSfxPlayer? _sfx;
    private VoiceChatManager? _voice;
    private ISharedPreferences? _prefs;

    protected override void OnCreate(Bundle? savedInstanceState)
    {
        base.OnCreate(savedInstanceState);

        try
        {
            _prefs = GetSharedPreferences("nyawit_live_prefs", FileCreationMode.Private);

            NpakArchive archive;
            using (var assetStream = Assets!.Open("Meshes/nyawit_models.npak"))
            using (var mem = new MemoryStream(8 * 1024 * 1024))
            {
                assetStream.CopyTo(mem);
                mem.Position = 0;
                archive = NpakArchive.Load(mem);
            }

            Typeface displayFont = Typeface.DefaultBold!;
            try { displayFont = Typeface.CreateFromAsset(Assets, "Fonts/XyVerseDisplay-Semibold.otf") ?? Typeface.DefaultBold!; } catch { }

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
            _voice = new VoiceChatManager(_net);
            _renderer = new Gles3InstancedRenderer(this, archive, trees, _net);

            _glView = new GLSurfaceView(this);
            _glView.SetEGLContextClientVersion(3);
            _glView.SetEGLConfigChooser(new SafeGles3ConfigChooser());
            _glView.PreserveEGLContextOnPause = true;
            _glView.SetRenderer(_renderer);
            _glView.RenderMode = Rendermode.Continuously;

            _renderer.OnRenderScaleChanged += scale => RunOnUiThread(() => ApplyHardwareRenderScale(scale));
            _renderer.OnWorldReady += () =>
            {
                _sfx?.Play("world_ready");
                RunOnUiThread(() => _hud?.ShowToast("DUNIA KEBUN SIAP - SELAMAT MEMANEN!"));
            };

            _hud = new HudOverlayView(this, _renderer, _net, _sfx, _voice, displayFont, smallBrandMark);
            WireGameplayAndModalEvents();

            var root = new FrameLayout(this);
            root.SetBackgroundColor(Color.Rgb(9, 13, 16));
            root.AddView(_glView, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MatchParent, ViewGroup.LayoutParams.MatchParent));
            root.AddView(_hud, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MatchParent, ViewGroup.LayoutParams.MatchParent));

            SetContentView(root);
            ScheduleImmersiveFullscreen();

            _net.StartBackgroundConnect();
        }
        catch (Exception ex)
        {
            global::Android.Util.Log.Error("NyawitLive3D", $"Startup exception: {ex}");
            var errView = new TextView(this)
            {
                Text = $"Nyawit Live 3D Diagnostic:\n{ex}",
                TextSize = 12f
            };
            errView.SetTextColor(Color.White);
            errView.SetBackgroundColor(Color.Black);
            errView.SetPadding(32, 32, 32, 32);
            SetContentView(errView);
        }
    }

    private void ApplyHardwareRenderScale(float scale)
    {
        if (_glView?.Holder == null) return;
        try
        {
            int fullW = _glView.Width;
            int fullH = _glView.Height;
            if (fullW <= 64 || fullH <= 64) return;
            int maxH = scale < 0.70f ? 540 : (scale < 0.88f ? 720 : 1080);
            float effScale = System.Math.Min(scale, System.Math.Min(1f, maxH / (float)fullH));
            if (effScale >= 0.99f)
            {
                _glView.Holder.SetSizeFromLayout();
            }
            else
            {
                int sw = System.Math.Max(320, (int)(fullW * effScale) & ~1);
                int sh = System.Math.Max(180, (int)(fullH * effScale) & ~1);
                _glView.Holder.SetFixedSize(sw, sh);
            }
        }
        catch { }
    }

    private void WireGameplayAndModalEvents()
    {
        if (_hud == null || _renderer == null || _net == null || _sfx == null || _voice == null) return;

        _net.OnToast += msg => RunOnUiThread(() => _hud?.ShowToast(msg));
        _net.OnSoundTrigger += clip => _sfx?.Play(clip);
        _net.OnProfilePersisted += SaveLocalProfile;
        _renderer.Physics.OnPhysicsSfx += clip => _sfx?.Play(clip);

        _hud.OnEnterWorldRequested += () =>
        {
            _sfx.Play("ui_open");
            _renderer.BeginWorldPreparation();
        };

        _hud.OnReturnLobbyRequested += () =>
        {
            _sfx.Play("ui_open");
            _renderer.ReturnToLobby();
            _hud.ShowToast("KEMBALI KE LOBBY UTAMA 3D");
        };

        _hud.OnToggleVoiceMic += ToggleVoiceChatWithPermission;
        _hud.OnHarvestPressed += TriggerHarvestAction;
        _hud.OnPickupOrLoadPressed += TriggerPickupOrLoadAction;
        _hud.OnAngkongTogglePressed += TriggerAngkongAction;

        _hud.OnSellPressed += () =>
        {
            if (_renderer.NearRamWeighbridge)
            {
                int extraUnits = _renderer.Physics.Player.HeldTbsUnits;
                int extraGold = _renderer.Physics.Player.HeldGoldUnits;
                _renderer.Physics.Player.HeldTbsUnits = 0;
                _renderer.Physics.Player.HeldGoldUnits = 0;
                if (_renderer.NearbyAngkongId >= 0)
                {
                    extraUnits += _renderer.Physics.Angkongs[_renderer.NearbyAngkongId].CargoUnits;
                    extraGold += _renderer.Physics.Angkongs[_renderer.NearbyAngkongId].GoldUnits;
                    _renderer.Physics.Angkongs[_renderer.NearbyAngkongId].CargoUnits = 0;
                    _renderer.Physics.Angkongs[_renderer.NearbyAngkongId].GoldUnits = 0;
                }
                if (extraUnits > 0) _net.SendLoadTbs(extraUnits, extraGold);
                _renderer.Physics.MainTruck.VisualCargoUnits = 0;
                _net.RequestSell();
            }
            else
            {
                _hud.ShowToast("BAWA MUATAN TRUK / ANGKONG KE TIMBANGAN RAM PKS");
            }
        };

        _hud.OnTruckTogglePressed += () =>
        {
            _renderer.ToggleVehicleEnterExit();
            _sfx.Play(_renderer.InTruck ? "engine_enter" : "ui_open");
            _hud.ShowToast(_renderer.InTruck
                ? "KEMUDI CANTER OLENG AKTIF - SUSPENSI 4 RODA SIAP"
                : "TURUN DARI KABIN CANTER - SIAP MEMANEN");
        };

        _hud.OnHornPressed += () =>
        {
            _renderer.BoostTimer = 2.6f;
            _sfx.Play("horn");
            _net.SendHorn();
            _hud.ShowToast("TELOLET BASURI AKTIF - TURBO DIESEL BOOST");
        };

        _hud.OnOpenChat += () => { _sfx.Play("ui_open"); ShowChatDialog(); };
        _hud.OnOpenRankings += () => { _sfx.Play("ui_open"); ShowRankingsAndTournamentDialog(); };
        _hud.OnOpenAvatar += () => { _sfx.Play("ui_open"); ShowAvatarCustomizerDialog(); };
        _hud.OnOpenDaily += () => { _sfx.Play("ui_open"); ShowDailyRewardDialog(); };
        _hud.OnOpenSocialShare += () => { _sfx.Play("ui_open"); ShowSocialAndShareDialog(); };
    }

    private void TriggerHarvestAction()
    {
        if (_renderer == null || _net == null || _sfx == null || _hud == null) return;
        _renderer.Physics.Player.SlashTimer = 0.46f;
        _sfx.Play("chop");
        if (_renderer.NearestRipeTreeId >= 0)
        {
            _net.RequestHarvest(_renderer.NearestRipeTreeId, _renderer.InTruck);
        }
        else
        {
            _hud.ShowToast("DEKATI POHON SAWIT MATANG DULU");
        }
    }

    private void TriggerPickupOrLoadAction()
    {
        if (_renderer == null || _hud == null) return;
        if (_renderer.Physics.TryLoadIntoTruckOrAngkong(out string msg))
        {
            _hud.ShowToast(msg);
            return;
        }
        int picked = _renderer.Physics.TryPickupGroundFruit();
        if (picked > 0)
        {
            _hud.ShowToast($"DIAMBIL {picked} JANJANG TBS - BAWA KE TRUK CANTER ATAU ANGKONG");
        }
        else if (_renderer.Physics.Player.HasHeldTbs)
        {
            _hud.ShowToast("DEKATI BAK TRUK CANTER ATAU ANGKONG UNTUK MEMUAT TBS");
        }
        else
        {
            _hud.ShowToast("TEBANG POHON DULU LALU AMBIL TBS YANG JATUH");
        }
    }

    private void TriggerAngkongAction()
    {
        if (_renderer == null || _hud == null || _sfx == null) return;
        if (_renderer.Physics.Player.ActiveAngkongIndex >= 0)
        {
            _renderer.Physics.Player.ActiveAngkongIndex = -1;
            _sfx.Play("ui_click");
            _hud.ShowToast("ANGKONG DIPARKIR");
        }
        else if (_renderer.NearbyAngkongId >= 0)
        {
            _renderer.Physics.Player.ActiveAngkongIndex = _renderer.NearbyAngkongId;
            _sfx.Play("pickup");
            _hud.ShowToast("MENDORONG ANGKONG SAWIT - RODA AKTIF");
        }
    }

    private void ToggleVoiceChatWithPermission()
    {
        if (_voice == null || _renderer == null || _hud == null || _sfx == null) return;
        if (_voice.IsMicTransmitting)
        {
            _voice.SetMicEnabled(false);
            _renderer.LocalMicSpeaking = false;
            _sfx.Play("ui_click");
            _hud.ShowToast("VOICE CHAT NONAKTIF");
            return;
        }

        if (OperatingSystem.IsAndroidVersionAtLeast(23) && CheckSelfPermission(Manifest.Permission.RecordAudio) != Permission.Granted)
        {
            RequestPermissions([Manifest.Permission.RecordAudio], ReqRecordAudio);
            return;
        }

        bool started = _voice.SetMicEnabled(true);
        _renderer.LocalMicSpeaking = started;
        _sfx.Play("ui_open");
        _hud.ShowToast(started ? "VOICE CHAT LIVE 8KHZ AKTIF" : "MIKROFON TIDAK TERSEDIA DI PERANGKAT INI");
    }

    public override void OnRequestPermissionsResult(int requestCode, string[] permissions, [GeneratedEnum] Permission[] grantResults)
    {
        base.OnRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == ReqRecordAudio && grantResults.Length > 0 && grantResults[0] == Permission.Granted)
        {
            bool ok = _voice?.SetMicEnabled(true) ?? false;
            if (_renderer != null) _renderer.LocalMicSpeaking = ok;
            _hud?.ShowToast(ok ? "VOICE CHAT LIVE 8KHZ AKTIF" : "MIKROFON TIDAK TERSEDIA");
        }
    }

    public override bool OnKeyDown([GeneratedEnum] Keycode keyCode, KeyEvent? e)
    {
        // Supports full physical gamepad / keyboard play + deterministic Android 14 hardware verification!
        if (_renderer != null && _hud != null)
        {
            switch (keyCode)
            {
                case Keycode.Enter:
                case Keycode.ButtonStart:
                    _renderer.Quality.SetManualPreset((NyawitEngine.Core.GraphicsPreset)3, disableAuto: true);
                    if (_renderer.Stage == AppSceneStage.Lobby)
                    {
                        _sfx?.Play("ui_open");
                        _renderer.BeginWorldPreparation();
                    }
                    return true;
                case Keycode.H:
                case Keycode.Space:
                    TriggerHarvestAction();
                    return true;
                case Keycode.F:
                    _glView?.QueueEvent(() =>
                    {
                        _renderer.Quality.SetManualPreset((NyawitEngine.Core.GraphicsPreset)3, disableAuto: true);
                        if (_renderer.InTruck) _renderer.ToggleVehicleEnterExit();
                        _renderer.JoyX = 0f;
                        _renderer.JoyY = 0f;
                        // Step clearly into open sunlit clearing beside Canter & Palm Grove for unobstructed close-up!
                        _renderer.Physics.Player.X = 5.10f;
                        _renderer.Physics.Player.Z = 9.80f;
                        _renderer.Physics.Player.Y = NyawitEngine.Physics.RigidBodyWorld.SurfaceHeightWithStructures(5.10f, 9.80f);
                        _renderer.Physics.Player.Yaw = 0.24f;
                        _renderer.Physics.SpawnHarvestedGroundFruit(5.55f, 10.25f, isGold: false);
                        for (int i = 0; i < 90; i++) _renderer.Physics.StepWorld(0.016f, false, 0f, 0f, _renderer.CamYaw, []);
                        _renderer.Physics.TryPickupGroundFruit();
                        _renderer.Physics.Player.HeldTbsUnits = System.Math.Max(1, _renderer.Physics.Player.HeldTbsUnits);
                        RunOnUiThread(() => _hud?.ShowToast("DIAMBIL 1 JANJANG TBS - ANIMASI PEGANG AKTIF"));
                        _renderer.LockShowcaseCam = true;
                        _renderer.CamDist = 2.65f;
                        _renderer.CamPitch = 0.04f;
                        _renderer.CamYaw = _renderer.Physics.Player.Yaw + 0.26f;
                    });
                    return true;
                case Keycode.L:
                    TriggerPickupOrLoadAction();
                    return true;
                case Keycode.T:
                    _glView?.QueueEvent(() =>
                    {
                        _renderer.Quality.SetManualPreset((NyawitEngine.Core.GraphicsPreset)3, disableAuto: true);
                        _renderer.Physics.MainTruck.VisualCargoUnits = System.Math.Max(_renderer.Physics.MainTruck.VisualCargoUnits, 8);
                        if (!_renderer.InTruck) _renderer.ToggleVehicleEnterExit();
                        _renderer.JoyX = -0.86f;
                        _renderer.JoyY = -0.46f;
                        _renderer.LockShowcaseCam = true;
                        _renderer.CamDist = 4.65f;
                        _renderer.CamPitch = 0.08f;
                        _renderer.CamYaw = _renderer.Physics.MainTruck.Yaw + 0.68f;
                    });
                    return true;
            }
        }
        return base.OnKeyDown(keyCode, e);
    }

    private void ShowChatDialog()
    {
        if (_net == null) return;
        var layout = CreateDialogContainer(out _);

        var logText = new TextView(this) { TextSize = 12.5f };
        logText.SetTextColor(Color.Argb(255, 225, 232, 240));
        var chats = new System.Collections.Generic.List<ChatMessageEntry>();
        _net.CopyRenderState(new(), new(), chats, 0f);
        var sb = new StringBuilder();
        foreach (var c in chats) sb.AppendLine($"[{c.SenderName}]: {c.Text}");
        if (sb.Length == 0) sb.AppendLine("BELUM ADA CHAT. SAPA PEMANEN LAIN SEKARANG!");
        logText.Text = sb.ToString();
        layout.AddView(logText);

        var input = new EditText(this) { Hint = "Ketik pesan ke Global Chat..." };
        input.SetTextColor(Color.White);
        input.SetHintTextColor(Color.Gray);
        layout.AddView(input);

        string[] quick = ["GAS PANEN BLOK TIMUR!", "SAWIT EMAS MUNCUL!", "ANTRI TIMBANGAN RAM PKS!", "CANTER OLENG BOS!"];
        foreach (var q in quick)
        {
            string msg = q;
            var b = CreateStyledButton($" PESAN CEPAT: {msg}", false);
            b.Click += (_, _) => { _sfx?.Play("ui_click"); _net.SendChat(msg); _hud?.ShowToast("CHAT TERKIRIM KE GLOBAL SERVER"); };
            layout.AddView(b);
        }

        new AlertDialog.Builder(this)
            .SetTitle("GLOBAL CHAT & ROOM SERVER")!
            .SetView(WrapScroll(layout))!
            .SetPositiveButton("KIRIM PESAN", (_, _) =>
            {
                _sfx?.Play("ui_click");
                string txt = (input.Text ?? "").Trim();
                if (!string.IsNullOrEmpty(txt)) _net.SendChat(txt);
            })!
            .SetNegativeButton("TUTUP", (_, _) => _sfx?.Play("ui_click"))!
            .Show();
    }

    private void ShowRankingsAndTournamentDialog()
    {
        if (_net == null) return;
        _net.RefreshBoards();
        var (globalB, weeklyB, tiers) = _net.GetBoardsSnapshot();
        var layout = CreateDialogContainer(out _);

        long remSec = System.Math.Max(0, (_net.TournamentEndsAtMs - DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()) / 1000);
        var header = new TextView(this)
        {
            Text = $"TURNAMEN MINGGUAN ({_net.TournamentWeekId}) - RESET {remSec / 86400}H {(remSec % 86400) / 3600}J\nPOIN MINGGUAN: {_net.Profile.WeeklyPoints:N0} PTS  //  SETORAN: {_net.Profile.TotalKg:N0} KG",
            TextSize = 13f
        };
        header.SetTextColor(Color.Argb(255, 245, 195, 56));
        layout.AddView(header);

        foreach (var t in tiers)
        {
            string tid = t.Id;
            bool claimed = _net.Profile.ClaimedTiers.Contains(tid);
            bool ready = _net.Profile.WeeklyPoints >= t.MinPts && !claimed;
            var btn = CreateStyledButton($"{t.Label} {(claimed ? "[DIKLAIM]" : ready ? "[KLAIM]" : $"[{_net.Profile.WeeklyPoints}/{t.MinPts}]")}", ready);
            btn.Enabled = ready;
            btn.Click += (_, _) => { _sfx?.Play("ui_click"); _net.ClaimTournamentTier(tid); };
            layout.AddView(btn);
        }

        var sb = new StringBuilder("\n[ TOP GLOBAL RANKING SEPANJANG MASA ]\n");
        foreach (var r in globalB)
            sb.AppendLine($"#{r.Rank}  {r.Name} [{r.Title}] - {r.TotalKg:N0} KG // {r.Score:N0} PTS");

        sb.AppendLine("\n[ KLASEMEN TURNAMEN MINGGU INI ]");
        foreach (var r in weeklyB)
            sb.AppendLine($"#{r.Rank}  {r.Name} - {r.Score:N0} POIN ({r.TotalKg:N0} KG)");

        var tv = new TextView(this) { Text = sb.ToString(), TextSize = 12f };
        tv.SetTextColor(Color.White);
        layout.AddView(tv);

        new AlertDialog.Builder(this)
            .SetTitle("GLOBAL RANKING & TURNAMEN MINGGUAN")!
            .SetView(WrapScroll(layout))!
            .SetPositiveButton("TUTUP", (_, _) => _sfx?.Play("ui_click"))!
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
            (MeshCatalog.HatCaping, "TOPI CAPING BAMBU"),
            (MeshCatalog.HatSafety, "HELM PROYEK SAFETY"),
            (MeshCatalog.HatHeadband, "IKAT KEPALA PENDEKAR"),
            (MeshCatalog.HatCowboy, "TOPI KOBOI JURAGAN"),
            (MeshCatalog.HatCrownGold, "MAHKOTA RAJA SAWIT 24K")
        ];
        (string id, string label)[] backs =
        [
            (MeshCatalog.BackBasket, "KERANJANG ROTAN TBS"),
            (MeshCatalog.BackPack, "RANSEL TAKTIS LAPANGAN"),
            (MeshCatalog.BackCape, "JUBAH MANDOR SULTAN"),
            (MeshCatalog.BackWingsGold, "SAYAP PHOENIX EMAS JUARA")
        ];
        (string id, string label)[] tools =
        [
            (MeshCatalog.ToolEgrek, "EGREK GALAH PANJANG"),
            (MeshCatalog.ToolDodos, "DODOS BAJA TAJAM"),
            (MeshCatalog.ToolEgrekDragon, "SABIT NAGA SAWIT 24K")
        ];
        string[] colors = ["#27AE60", "#E67E22", "#E74C3C", "#2980B9", "#8E44AD", "#F1C40F", "#16A085", "#ECF0F1"];

        string selHat = av.Hat, selBack = av.Back, selTool = av.Tool, selHex = av.OutfitHex;

        AddOptionGroup(layout, "PILIH PENUTUP KEPALA 3D:", hats, id => { selHat = id; ApplyAvatarNow(); });
        AddOptionGroup(layout, "PILIH AKSESORIS PUNGGUNG 3D:", backs, id => { selBack = id; ApplyAvatarNow(); });
        AddOptionGroup(layout, "PILIH ALAT PANEN 3D:", tools, id => { selTool = id; ApplyAvatarNow(); });

        var colorRow = new LinearLayout(this) { Orientation = Orientation.Horizontal };
        foreach (var hex in colors)
        {
            string h = hex;
            var cb = new Button(this) { Text = " " };
            cb.SetBackgroundColor(Color.ParseColor(h));
            cb.Click += (_, _) => { _sfx?.Play("ui_click"); selHex = h; ApplyAvatarNow(); };
            colorRow.AddView(cb, new LinearLayout.LayoutParams(90, 72) { RightMargin = 10 });
        }
        layout.AddView(colorRow);

        void ApplyAvatarNow()
        {
            _net.SaveAvatar((nameEdit.Text ?? _net.Profile.Name).Trim(), new AvatarConfig
            {
                Hat = selHat, Back = selBack, Tool = selTool, OutfitHex = selHex, Aura = av.Aura, Title = av.Title
            });
            _hud?.ShowToast("AVATAR 3D & WARNA TRUK TERSIMPAN");
        }

        new AlertDialog.Builder(this)
            .SetTitle("KUSTOMISASI AVATAR 3D & WARNA CANTER")!
            .SetView(WrapScroll(layout))!
            .SetPositiveButton("SIMPAN AVATAR", (_, _) => { _sfx?.Play("ui_click"); ApplyAvatarNow(); })!
            .SetNegativeButton("TUTUP", (_, _) => _sfx?.Play("ui_click"))!
            .Show();
    }

    private void ShowDailyRewardDialog()
    {
        if (_net == null) return;
        var layout = CreateDialogContainer(out _);
        string[] rewards =
        [
            "HARI 1: RP 150.000 + 10 PERMATA",
            "HARI 2: RP 250.000 + 15 PERMATA + HELM SAFETY",
            "HARI 3: RP 400.000 + 25 PERMATA",
            "HARI 4: RP 600.000 + 35 PERMATA + AURA API",
            "HARI 5: RP 850.000 + 50 PERMATA + RANSEL TAKTIS",
            "HARI 6: RP 1.200.000 + 75 PERMATA",
            "HARI 7 JACKPOT: RP 2.500.000 + 150 PERMATA + SABIT EMAS"
        ];
        var info = new TextView(this)
        {
            Text = $"STREAK LOGIN AKTIF: {_net.Profile.StreakDay} HARI BERTURUT-TURUT\n\n" + string.Join("\n", rewards),
            TextSize = 13f
        };
        info.SetTextColor(Color.White);
        layout.AddView(info);

        new AlertDialog.Builder(this)
            .SetTitle("REWARD HARIAN 7-HARI")!
            .SetView(WrapScroll(layout))!
            .SetPositiveButton(_net.Profile.CanClaimDaily ? "KLAIM REWARD HARI INI" : "SUDAH DIKLAIM HARI INI", (_, _) =>
            {
                _sfx?.Play("ui_click");
                if (_net.Profile.CanClaimDaily) _net.ClaimDaily();
            })!
            .SetNegativeButton("TUTUP", (_, _) => _sfx?.Play("ui_click"))!
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
            var btn = CreateStyledButton($"TAUTKAN AKUN {prov.ToUpperInvariant()} (+30 PERMATA)", false);
            btn.Click += (_, _) => { _sfx?.Play("ui_click"); _net.LinkSocial(prov, _net.Profile.Name, (handleInput.Text ?? "@juragansawit").Trim()); };
            layout.AddView(btn);
        }

        var shareBtn = CreateStyledButton("BAGIKAN KARTU PENCAPAIAN RESMI", true);
        shareBtn.Click += async (_, _) =>
        {
            _sfx?.Play("ui_click");
            _hud?.ShowToast("MENYIAPKAN LINK KARTU PENCAPAIAN LIVE...");
            var (_, text) = await _net.CreateShareCardAsync();
            RunOnUiThread(() =>
            {
                var sendIntent = new Intent(Intent.ActionSend);
                sendIntent.SetType("text/plain");
                sendIntent.PutExtra(Intent.ExtraSubject, "Pencapaian Nyawit Live 3D");
                sendIntent.PutExtra(Intent.ExtraText, text);
                StartActivity(Intent.CreateChooser(sendIntent, "Bagikan Pencapaian Nyawit Live 3D"));
            });
        };
        layout.AddView(shareBtn);

        new AlertDialog.Builder(this)
            .SetTitle("TAUTKAN SOSMED & SHARE PENCAPAIAN")!
            .SetView(WrapScroll(layout))!
            .SetPositiveButton("TUTUP", (_, _) => _sfx?.Play("ui_click"))!
            .Show();
    }

    private void AddOptionGroup(LinearLayout parent, string heading, (string id, string label)[] items, Action<string> onPick)
    {
        var tv = new TextView(this) { Text = heading, TextSize = 11.5f };
        tv.SetTextColor(Color.Argb(255, 245, 195, 56));
        parent.AddView(tv);
        foreach (var (id, label) in items)
        {
            string captured = id;
            var b = CreateStyledButton(label, false);
            b.Click += (_, _) => { _sfx?.Play("ui_click"); onPick(captured); };
            parent.AddView(b);
        }
    }

    private LinearLayout CreateDialogContainer(out int pad)
    {
        float dp = Resources?.DisplayMetrics?.Density ?? 2.5f;
        pad = (int)(16 * dp);
        var ll = new LinearLayout(this) { Orientation = Orientation.Vertical };
        ll.SetPadding(pad, pad, pad, pad);
        ll.SetBackgroundColor(Color.Argb(255, 12, 17, 21));
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
        b.SetBackgroundColor(highlightGold ? Color.Argb(255, 246, 195, 56) : Color.Argb(255, 22, 34, 42));
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

    private void ScheduleImmersiveFullscreen()
    {
        var win = Window;
        var decor = win?.DecorView;
        if (win == null || decor == null) return;

        try
        {
            win.AddFlags(WindowManagerFlags.KeepScreenOn);
            if (OperatingSystem.IsAndroidVersionAtLeast(28) && win.Attributes != null)
            {
                var lp = win.Attributes;
                lp.LayoutInDisplayCutoutMode = LayoutInDisplayCutoutMode.ShortEdges;
                win.Attributes = lp;
            }
        }
        catch { }

        decor.Post(() =>
        {
            try
            {
                if (OperatingSystem.IsAndroidVersionAtLeast(30))
                {
#pragma warning disable CA1422
                    win.SetDecorFitsSystemWindows(false);
#pragma warning restore CA1422
                    var controller = win.InsetsController;
                    if (controller != null)
                    {
                        controller.Hide(WindowInsets.Type.StatusBars() | WindowInsets.Type.NavigationBars());
                        controller.SystemBarsBehavior = (int)WindowInsetsControllerBehavior.ShowTransientBarsBySwipe;
                    }
                }
                else
                {
#pragma warning disable CA1422, CS0618
                    decor.SystemUiVisibility = (StatusBarVisibility)(
                        SystemUiFlags.ImmersiveSticky | SystemUiFlags.Fullscreen | SystemUiFlags.HideNavigation | SystemUiFlags.LayoutFullscreen);
#pragma warning restore CA1422, CS0618
                }
            }
            catch { }
        });
    }

    protected override void OnResume()
    {
        base.OnResume();
        ScheduleImmersiveFullscreen();
        _glView?.OnResume();
    }

    protected override void OnPause()
    {
        _glView?.OnPause();
        base.OnPause();
    }

    protected override void OnDestroy()
    {
        _voice?.Dispose();
        _net?.Dispose();
        _sfx?.Dispose();
        base.OnDestroy();
    }
}
