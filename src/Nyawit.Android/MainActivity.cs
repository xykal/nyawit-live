using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Android;
using Android.App;
using Android.Content;
using Android.Content.PM;
using Android.Graphics;
using Android.Opengl;
using Android.OS;
using Android.Runtime;
using Android.Views;
using Android.Views.InputMethods;
using Android.Widget;
using Javax.Microedition.Khronos.Egl;
using Nyawit.AndroidClient.Audio;
using Nyawit.AndroidClient.Rendering;
using Nyawit.AndroidClient.UI;
using NyawitEngine.Assets;
using NyawitEngine.Core;
using NyawitEngine.Network;
using NyawitEngine.Physics;
using NyawitEngine.World;
using EGLConfig = Javax.Microedition.Khronos.Egl.EGLConfig;
using EGLDisplay = Javax.Microedition.Khronos.Egl.EGLDisplay;

namespace Nyawit.AndroidClient;

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
    Name = "id.my.xyverse.nyawitlive.MainActivity",
    Label = "Nyawit Live 3D",
    Theme = "@android:style/Theme.Black.NoTitleBar.Fullscreen",
    LaunchMode = LaunchMode.SingleTop,
    MainLauncher = true,
    Exported = true,
    ScreenOrientation = ScreenOrientation.SensorLandscape,
    ConfigurationChanges = ConfigChanges.Orientation | ConfigChanges.ScreenSize | ConfigChanges.SmallestScreenSize | ConfigChanges.ScreenLayout | ConfigChanges.KeyboardHidden | ConfigChanges.Density)]
public class MainActivity : Activity
{
    private const int ReqRecordAudio = 4102;

    private FrameLayout? _rootLayout;
    private LinearLayout? _inlineInputOverlay;
    private GLSurfaceView? _glView;
    private Gles3InstancedRenderer? _renderer;
    private HudOverlayView? _hud;
    private LiveMultiplayerSession? _net;
    private ProceduralSfxPlayer? _sfx;
    private VoiceChatManager? _voice;
    private ISharedPreferences? _prefs;

    protected override void OnCreate(Bundle? savedInstanceState)
    {
        RequestWindowFeature(WindowFeatures.NoTitle);
        base.OnCreate(savedInstanceState);
        ScheduleImmersiveFullscreen();

        try
        {
            _prefs = GetSharedPreferences("nyawit_live_prefs_v4", FileCreationMode.Private);

            NpakArchive archive;
            using (var assetStream = Assets!.Open("Meshes/nyawit_models.npak"))
            using (var mem = new MemoryStream(2 * 1024 * 1024))
            {
                assetStream.CopyTo(mem);
                mem.Position = 0;
                archive = NpakArchive.Load(mem);
            }

            Typeface displayFont = Typeface.DefaultBold!;
            try { displayFont = Typeface.CreateFromAsset(Assets, "Fonts/XyVerseDisplay-Semibold.otf") ?? Typeface.DefaultBold!; } catch { }

            var bmpOpts = new BitmapFactory.Options { InScaled = false };
            Bitmap? smallBrandMark = null;
            Bitmap? wideBrandLogo = null;
            try
            {
                using var markStream = Assets.Open("Brand/mark_kecil_transparan_putih.png");
                smallBrandMark = BitmapFactory.DecodeStream(markStream, null, bmpOpts);
            }
            catch { }
            try
            {
                using var wideStream = Assets.Open("Brand/logo_utama_horizontal_transparan_putih.png");
                wideBrandLogo = BitmapFactory.DecodeStream(wideStream, null, bmpOpts);
            }
            catch { }

            var trees = PlantationWorld.GenerateTrees();
            _net = new LiveMultiplayerSession(trees);
            RestoreLocalProfile(_net.Profile);

            _sfx = new ProceduralSfxPlayer();
            _voice = new VoiceChatManager(_net);
            _renderer = new Gles3InstancedRenderer(this, archive, trees, _net);
            RestoreGraphicsSettings();

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
                RunOnUiThread(() => _hud?.ShowToast("DUNIA KEBUN SAWIT SIAP — SELAMAT MEMANEN!"));
            };

            _hud = new HudOverlayView(this, _renderer, _net, _sfx, _voice, displayFont, smallBrandMark, wideBrandLogo);
            WireGameplayEvents();

            _rootLayout = new FrameLayout(this);
            _rootLayout.SetBackgroundColor(Color.Rgb(9, 11, 13));
            _rootLayout.AddView(_glView, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MatchParent, ViewGroup.LayoutParams.MatchParent));
            _rootLayout.AddView(_hud, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MatchParent, ViewGroup.LayoutParams.MatchParent));

            SetContentView(_rootLayout);
            ApplyHardwareDisplayRefreshRate(_renderer.Quality.TargetFps);
            StartLocalStageControlServer();

            _net.StartBackgroundConnect();
            if (!string.IsNullOrWhiteSpace(Intent?.GetStringExtra("stage")))
                ApplyStageByName(Intent.GetStringExtra("stage")!);
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

    private void ApplyHardwareDisplayRefreshRate(int targetFps)
    {
        var win = Window;
        if (win == null || !OperatingSystem.IsAndroidVersionAtLeast(23)) return;
        try
        {
#pragma warning disable CA1422
            var display = WindowManager?.DefaultDisplay;
#pragma warning restore CA1422
            var modes = display?.GetSupportedModes();
            if (modes == null || modes.Length == 0) return;

            Display.Mode? best = null;
            float bestDiff = float.MaxValue;
            foreach (var m in modes)
            {
                float diff = System.Math.Abs(m.RefreshRate - targetFps);
                if (diff < bestDiff)
                {
                    bestDiff = diff;
                    best = m;
                }
            }

            if (best != null && win.Attributes != null)
            {
                var lp = win.Attributes;
                lp.PreferredDisplayModeId = best.ModeId;
                win.Attributes = lp;
            }
            SaveGraphicsSettings();
        }
        catch { }
    }

    private void ApplyHardwareRenderScale(float scale)
    {
        if (_glView?.Holder == null) return;
        try
        {
            int fullW = _glView.Width;
            int fullH = _glView.Height;
            if (fullW <= 64 || fullH <= 64) return;
            int maxH = scale < 0.70f ? 540 : (scale < 0.88f ? 760 : 1080);
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
            SaveGraphicsSettings();
        }
        catch { }
    }

    private void WireGameplayEvents()
    {
        if (_hud == null || _renderer == null || _net == null || _sfx == null || _voice == null) return;

        _net.OnToast += msg => RunOnUiThread(() => _hud?.ShowToast(msg));
        _net.OnSoundTrigger += clip => _sfx?.Play(clip);
        _net.OnProfilePersisted += SaveLocalProfile;
        _renderer.Physics.OnPhysicsSfx += clip => _sfx?.Play(clip);

        _hud.OnProfileModified += SaveLocalProfile;
        _hud.OnTargetFpsSelected += fps =>
        {
            ApplyHardwareDisplayRefreshRate(fps);
            _hud.ShowToast($"TARGET FRAME RATE DIATUR KE {fps} FPS");
        };

        _hud.OnEnterWorldRequested += () =>
        {
            _sfx.Play("ui_open");
            _renderer.BeginWorldPreparation();
        };

        _hud.OnReturnLobbyRequested += () =>
        {
            _sfx.Play("ui_open");
            _renderer.ReturnToLobby();
            _hud.ShowToast("GARASI SHOWROOM AKTIF");
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
                _hud.ShowToast("BAWA MUATAN KE TIMBANGAN RAM PKS");
            }
        };

        _hud.OnTruckTogglePressed += () =>
        {
            _renderer.ToggleVehicleEnterExit();
            _sfx.Play(_renderer.InTruck ? "engine_enter" : "ui_open");
            _hud.ShowToast(_renderer.InTruck
                ? "KABIN MITSUBISHI CANTER AKTIF — SUSPENSI BAN DOBEL SIAP"
                : "TURUN DARI KABIN CANTER");
        };

        _hud.OnHornPressed += () =>
        {
            _renderer.BoostTimer = 2.6f;
            _sfx.Play("horn");
            _net.SendHorn();
            _hud.ShowToast("TURBO DIESEL CANTER AKTIF");
        };

        _hud.OnCustomChatInputRequested += () => ShowInlineTextPrompt("KETIK PESAN SERVER LIVE...", "", txt =>
        {
            if (!string.IsNullOrWhiteSpace(txt))
            {
                _net.SendChat(txt.Trim());
                _hud.ShowToast("PESAN TERKIRIM");
            }
        });

        _hud.OnRenamePlayerRequested += () => ShowInlineTextPrompt("NAMA PEMANEN / JURAGAN BARU", _net.Profile.Name, txt =>
        {
            string clean = txt.Trim();
            if (clean.Length >= 2)
            {
                _net.Profile.Name = clean.Length > 18 ? clean[..18] : clean;
                _net.SaveAvatar(_net.Profile.Name, _net.Profile.Avatar);
                SaveLocalProfile();
                _hud.ShowToast($"NAMA DIUBAH: {_net.Profile.Name}");
                _hud.PostInvalidate();
            }
        });
    }

    private void ShowInlineTextPrompt(string hint, string initial, Action<string> onSubmit)
    {
        if (_rootLayout == null) return;
        DismissInlineTextPrompt();

        var bar = new LinearLayout(this) { Orientation = Orientation.Horizontal };
        bar.SetBackgroundColor(Color.Argb(248, 12, 20, 26));
        int p = (int)(12 * (Resources?.DisplayMetrics?.Density ?? 2.5f));
        bar.SetPadding(p, p, p, p);

        var input = new EditText(this)
        {
            Text = initial,
            Hint = hint,
            TextSize = 13f,
        };
        input.SetSingleLine(true);
        input.SetTextColor(Color.White);
        input.SetHintTextColor(Color.Rgb(148, 163, 184));
        input.SetBackgroundColor(Color.Rgb(20, 32, 40));
        input.SetPadding(p, p / 2, p, p / 2);

        var sendBtn = new TextView(this)
        {
            Text = "SIMPAN",
            TextSize = 12f,
            Gravity = GravityFlags.Center,
        };
        sendBtn.SetTypeface(Typeface.DefaultBold, TypefaceStyle.Bold);
        sendBtn.SetTextColor(Color.White);
        sendBtn.SetBackgroundColor(Color.Rgb(22, 163, 74));
        sendBtn.SetPadding(p * 2, p / 2, p * 2, p / 2);
        sendBtn.Click += (_, _) =>
        {
            string val = input.Text ?? "";
            DismissInlineTextPrompt();
            onSubmit(val);
            ScheduleImmersiveFullscreen();
        };

        var cancelBtn = new TextView(this)
        {
            Text = "BATAL",
            TextSize = 12f,
            Gravity = GravityFlags.Center,
        };
        cancelBtn.SetTypeface(Typeface.DefaultBold, TypefaceStyle.Bold);
        cancelBtn.SetTextColor(Color.White);
        cancelBtn.SetBackgroundColor(Color.Rgb(127, 29, 29));
        cancelBtn.SetPadding(p, p / 2, p, p / 2);
        cancelBtn.Click += (_, _) =>
        {
            DismissInlineTextPrompt();
            ScheduleImmersiveFullscreen();
        };

        bar.AddView(input, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WrapContent, 1f));
        bar.AddView(sendBtn, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WrapContent, ViewGroup.LayoutParams.MatchParent) { LeftMargin = p / 2 });
        bar.AddView(cancelBtn, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WrapContent, ViewGroup.LayoutParams.MatchParent) { LeftMargin = p / 2 });

        var lp = new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MatchParent, ViewGroup.LayoutParams.WrapContent, GravityFlags.Top);
        _inlineInputOverlay = bar;
        _rootLayout.AddView(bar, lp);
        input.RequestFocus();
        var imm = GetSystemService(InputMethodService) as InputMethodManager;
        imm?.ShowSoftInput(input, ShowFlags.Implicit);
    }

    private void DismissInlineTextPrompt()
    {
        if (_inlineInputOverlay != null && _rootLayout != null)
        {
            var imm = GetSystemService(InputMethodService) as InputMethodManager;
            imm?.HideSoftInputFromWindow(_inlineInputOverlay.WindowToken, HideSoftInputFlags.None);
            _rootLayout.RemoveView(_inlineInputOverlay);
            _inlineInputOverlay = null;
        }
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
            _hud.ShowToast($"DIAMBIL {picked} JANJANG TBS — MUAT KE TRUK CANTER ATAU ANGKONG");
        }
        else if (_renderer.Physics.Player.HasHeldTbs)
        {
            _hud.ShowToast("DEKATI BAK TRUK CANTER ATAU ANGKONG UNTUK MEMUAT");
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
            _hud.ShowToast("MENDORONG ANGKONG SAWIT");
        }
        else
        {
            _hud.ShowToast("DEKATI ANGKONG MERAH DI KEBUN");
        }
    }

    private void ToggleVoiceChatWithPermission()
    {
        if (_voice == null || _renderer == null || _hud == null) return;
        if (OperatingSystem.IsAndroidVersionAtLeast(23) &&
            CheckSelfPermission(Manifest.Permission.RecordAudio) != Permission.Granted)
        {
            RequestPermissions([Manifest.Permission.RecordAudio], ReqRecordAudio);
            return;
        }
        bool nowOn = !_voice.MicEnabled;
        bool ok = _voice.SetMicEnabled(nowOn);
        _renderer.LocalMicSpeaking = ok && nowOn;
        _hud.ShowToast(ok && nowOn ? "VOICE CHAT LIVE AKTIF" : "VOICE CHAT DIMATIKAN");
        _hud.PostInvalidate();
    }

    public override void OnRequestPermissionsResult(int requestCode, string[] permissions, [GeneratedEnum] Permission[] grantResults)
    {
        base.OnRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == ReqRecordAudio && grantResults.Length > 0 && grantResults[0] == Permission.Granted)
            ToggleVoiceChatWithPermission();
    }

    private TcpListener? _stageControlServer;

    private void StartLocalStageControlServer()
    {
        try
        {
            _stageControlServer = new TcpListener(IPAddress.Loopback, 18765);
            _stageControlServer.Start();
            _ = Task.Run(async () =>
            {
                while (_stageControlServer != null)
                {
                    TcpClient? client = null;
                    try
                    {
                        client = await _stageControlServer.AcceptTcpClientAsync();
                        using (client)
                        using (var stream = client.GetStream())
                        using (var reader = new StreamReader(stream, Encoding.UTF8, false, 1024, leaveOpen: true))
                        {
                            string reqLine = await reader.ReadLineAsync() ?? "";
                            string stage = "";
                            int qIdx = reqLine.IndexOf("?s=", StringComparison.Ordinal);
                            if (qIdx >= 0)
                            {
                                string rest = reqLine[(qIdx + 3)..];
                                int sp = rest.IndexOfAny(new[] { ' ', '&' });
                                stage = (sp >= 0 ? rest[..sp] : rest).Trim();
                            }

                            if (!string.IsNullOrEmpty(stage))
                            {
                                var tcs = new TaskCompletionSource<bool>();
                                RunOnUiThread(() =>
                                {
                                    try { ApplyStageByName(stage); }
                                    finally { tcs.TrySetResult(true); }
                                });
                                await tcs.Task;

                                int targetFrame = (_renderer?.PresentedFrameCount ?? 0) + 8;
                                var sw = System.Diagnostics.Stopwatch.StartNew();
                                while ((_renderer?.PresentedFrameCount ?? 0) < targetFrame && sw.ElapsedMilliseconds < 6000)
                                {
                                    _hud?.PostInvalidate();
                                    await Task.Delay(60);
                                }
                                _hud?.PostInvalidate();
                                await Task.Delay(180);
                            }

                            string body = $"{{\"ok\":true,\"stage\":\"{stage}\",\"frames\":{_renderer?.PresentedFrameCount ?? 0}}}";
                            byte[] bodyBytes = Encoding.UTF8.GetBytes(body);
                            string hdr = $"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {bodyBytes.Length}\r\nConnection: close\r\n\r\n";
                            byte[] hdrBytes = Encoding.ASCII.GetBytes(hdr);
                            await stream.WriteAsync(hdrBytes);
                            await stream.WriteAsync(bodyBytes);
                            await stream.FlushAsync();
                        }
                    }
                    catch { await Task.Delay(50); }
                }
            });
        }
        catch { }
    }

    protected override void OnNewIntent(Intent? intent)
    {
        base.OnNewIntent(intent);
        ScheduleImmersiveFullscreen();
        if (!string.IsNullOrWhiteSpace(intent?.GetStringExtra("stage")))
            ApplyStageByName(intent.GetStringExtra("stage")!);
    }

    private void ApplyStageByName(string stage)
    {
        if (string.IsNullOrWhiteSpace(stage) || _renderer == null || _hud == null || _net == null) return;

        switch (stage.Trim().ToLowerInvariant())
        {
            case "splash":
                _hud.CloseModal();
                _renderer.ForceStageAndProgress(AppSceneStage.Splash, 0.58f, hold: true);
                _hud.Invalidate();
                break;

            case "garage":
                _hud.CloseModal();
                _renderer.HoldStageProgress = false;
                _renderer.ForceStageAndProgress(AppSceneStage.Lobby, 1.0f, hold: false);
                _renderer.LobbyOrbitYaw = 0.06f;
                _hud.Invalidate();
                break;

            case "loading":
                _hud.CloseModal();
                _renderer.BeginWorldPreparation();
                _renderer.ForceStageAndProgress(AppSceneStage.PreparingWorld, 0.64f, hold: true);
                _hud.Invalidate();
                break;

            case "onfoot":
                _renderer.HoldStageProgress = false;
                _renderer.ForceStageAndProgress(AppSceneStage.Gameplay, 1.0f, hold: false);
                ExecuteKeyShowcase(Keycode.F);
                _hud.Invalidate();
                break;

            case "canter":
                _renderer.HoldStageProgress = false;
                _renderer.ForceStageAndProgress(AppSceneStage.Gameplay, 1.0f, hold: false);
                ExecuteKeyShowcase(Keycode.T);
                _hud.Invalidate();
                break;

            case "settings":
                _renderer.HoldStageProgress = false;
                ExecuteKeyShowcase(Keycode.P);
                _hud.Invalidate();
                break;
        }
    }

    private void ExecuteKeyShowcase(Keycode keyCode)
    {
        if (_renderer == null || _hud == null || _net == null) return;
        if (keyCode == Keycode.P)
        {
            _hud.SettingsTabIndex = 0;
            _hud.OpenModal(ActiveModalOverlay.Settings);
            _hud.PostInvalidate();
            return;
        }
        if (keyCode == Keycode.F)
        {
            _hud.CloseModal();
            _renderer.InTruck = false;
            _renderer.LockShowcaseCam = true;
            _renderer.JoyX = 0f;
            _renderer.JoyY = 0f;
            _renderer.Physics.Player.X = -5.6f;
            _renderer.Physics.Player.Z = 14.0f;
            _renderer.Physics.Player.Y = RigidBodyWorld.SurfaceHeightWithStructures(-5.6f, 14.0f);
            _renderer.Physics.Player.Yaw = 0.22f;
            _renderer.Physics.Player.HeldTbsUnits = 3;
            _renderer.Physics.Player.HeldGoldUnits = 0;
            _renderer.Physics.Player.Stance = HoldStance.CarryingTbs;
            _net.Profile.Avatar.Hat = MeshCatalog.HatCaping;
            _net.Profile.Avatar.Back = MeshCatalog.BackBasket;
            _net.Profile.Avatar.Tool = MeshCatalog.ToolEgrek;
            _net.Profile.Avatar.Glasses = true;
            _net.Profile.Avatar.WaistParang = true;

            _renderer.Physics.MainTruck.X = -2.2f;
            _renderer.Physics.MainTruck.Z = 10.4f;
            _renderer.Physics.MainTruck.Y = RigidBodyWorld.SurfaceHeightWithStructures(-2.2f, 10.4f);
            _renderer.Physics.MainTruck.Yaw = -0.62f;
            _renderer.Physics.MainTruck.SpeedMs = 0f;
            _renderer.Physics.MainTruck.SteerAngle = 0.34f;
            _renderer.Physics.MainTruck.VisualCargoUnits = 16;

            _renderer.CamYaw = 0.14f;
            _renderer.CamPitch = 0.10f;
            _renderer.CamDist = 3.35f;
            _hud.PostInvalidate();
            return;
        }
        if (keyCode == Keycode.T)
        {
            _hud.CloseModal();
            _renderer.InTruck = true;
            _renderer.LockShowcaseCam = true;
            _renderer.JoyX = -0.78f;
            _renderer.JoyY = 0f;
            _renderer.Physics.MainTruck.X = 0.0f;
            _renderer.Physics.MainTruck.Z = 14.0f;
            _renderer.Physics.MainTruck.Y = RigidBodyWorld.SurfaceHeightWithStructures(0.0f, 14.0f);
            _renderer.Physics.MainTruck.Yaw = -0.52f;
            _renderer.Physics.MainTruck.SpeedMs = 0f;
            _renderer.Physics.MainTruck.SteerAngle = 0.36f;
            _renderer.Physics.MainTruck.VisualCargoUnits = 18;
            _renderer.CamYaw = 0.14f;
            _renderer.CamDist = 5.9f;
            _renderer.CamPitch = 0.16f;
            _hud.PostInvalidate();
        }
    }

    public override bool OnKeyDown([GeneratedEnum] Keycode keyCode, KeyEvent? e)
    {
        if (_renderer != null && _hud != null && _net != null)
        {
            if (keyCode == Keycode.Back && _hud.ActiveModal != ActiveModalOverlay.None)
            {
                _hud.CloseModal();
                return true;
            }
            if (keyCode == Keycode.G)
            {
                _hud.CloseModal();
                _renderer.SkipSplashToLobby();
                _renderer.ReturnToLobby();
                return true;
            }
            if (keyCode == Keycode.Enter)
            {
                _hud.CloseModal();
                _renderer.BeginWorldPreparation();
                return true;
            }
            if (keyCode == Keycode.P)
            {
                _hud.SettingsTabIndex = 0;
                _hud.OpenModal(ActiveModalOverlay.Settings);
                return true;
            }
            if (keyCode == Keycode.F)
            {
                // Hero On-Foot Plantation Showcase: MaxHD + PCF Shadows + Clouds + Spiky TBS Held + COE Canter Parked Nearby!
                _hud.CloseModal();
                _renderer.RequestPresetChange(GraphicsPreset.MaxHD);
                _renderer.Quality.ShadowTier = ShadowQualityTier.High;
                _renderer.Quality.CloudsEnabled = true;
                _renderer.InTruck = false;
                _renderer.LockShowcaseCam = true;
                _renderer.Physics.Player.X = -6.2f;
                _renderer.Physics.Player.Z = 14.0f;
                _renderer.Physics.Player.Y = RigidBodyWorld.SurfaceHeightWithStructures(-6.2f, 14.0f);
                _renderer.Physics.Player.Yaw = 0.25f;
                _renderer.Physics.Player.HeldTbsUnits = 3;
                _renderer.Physics.Player.HeldGoldUnits = 0;
                _renderer.Physics.Player.Stance = HoldStance.CarryingTbs;
                _net.Profile.Avatar.Hat = MeshCatalog.HatCaping;
                _net.Profile.Avatar.Back = MeshCatalog.BackBasket;
                _net.Profile.Avatar.Tool = MeshCatalog.ToolEgrek;
                _net.Profile.Avatar.Glasses = true;
                _net.Profile.Avatar.WaistParang = true;

                _renderer.Physics.MainTruck.X = -3.1f;
                _renderer.Physics.MainTruck.Z = 11.2f;
                _renderer.Physics.MainTruck.Y = RigidBodyWorld.SurfaceHeightWithStructures(-3.1f, 11.2f);
                _renderer.Physics.MainTruck.Yaw = -0.62f;
                _renderer.Physics.MainTruck.SteerAngle = 0.34f;
                _renderer.Physics.MainTruck.VisualCargoUnits = 16;

                _renderer.CamYaw = 0.14f;
                _renderer.CamPitch = 0.11f;
                _renderer.CamDist = 3.65f;
                _hud.PostInvalidate();
                return true;
            }
            if (keyCode == Keycode.L)
            {
                TriggerPickupOrLoadAction();
                return true;
            }
            if (keyCode == Keycode.T)
            {
                // Hero COE Canter Driving Showcase: 3/4 Front-Side View of Flat-Nose Canter + Dual Rear Tires + Tire Dust + Shadows!
                _hud.CloseModal();
                _renderer.InTruck = true;
                _renderer.LockShowcaseCam = true;
                _renderer.Physics.MainTruck.X = 0.0f;
                _renderer.Physics.MainTruck.Z = 14.0f;
                _renderer.Physics.MainTruck.Y = RigidBodyWorld.SurfaceHeightWithStructures(0.0f, 14.0f);
                _renderer.Physics.MainTruck.Yaw = 0.0f;
                _renderer.Physics.MainTruck.VisualCargoUnits = 18;
                _renderer.CamDist = 6.2f;
                _renderer.CamPitch = 0.19f;
                _renderer.JoyX = -0.78f;
                _renderer.JoyY = -0.52f;
                _hud.PostInvalidate();
                return true;
            }
        }
        return base.OnKeyDown(keyCode, e);
    }

    private void RestoreGraphicsSettings()
    {
        if (_prefs == null || _renderer == null) return;
        int preset = _prefs.GetInt("gfx_preset", (int)GraphicsPreset.Ultra);
        _renderer.Quality.SetManualPreset((GraphicsPreset)System.Math.Clamp(preset, 0, 3), disableAuto: false);
        _renderer.Quality.TargetFps = _prefs.GetInt("gfx_fps", 60);
        _renderer.Quality.ShadowTier = (ShadowQualityTier)System.Math.Clamp(_prefs.GetInt("gfx_shadow", 2), 0, 2);
        _renderer.Quality.CloudsEnabled = _prefs.GetBoolean("gfx_clouds", true);
        _renderer.Quality.ParticlesEnabled = _prefs.GetBoolean("gfx_particles", true);
        _renderer.Quality.ShowFpsHud = _prefs.GetBoolean("gfx_show_fps", true);
    }

    private void SaveGraphicsSettings()
    {
        if (_prefs == null || _renderer == null) return;
        var ed = _prefs.Edit()!;
        ed.PutInt("gfx_preset", (int)_renderer.Quality.CurrentPreset);
        ed.PutInt("gfx_fps", _renderer.Quality.TargetFps);
        ed.PutInt("gfx_shadow", (int)_renderer.Quality.ShadowTier);
        ed.PutBoolean("gfx_clouds", _renderer.Quality.CloudsEnabled);
        ed.PutBoolean("gfx_particles", _renderer.Quality.ParticlesEnabled);
        ed.PutBoolean("gfx_show_fps", _renderer.Quality.ShowFpsHud);
        ed.Apply();
    }

    private void RestoreLocalProfile(PlayerProfile p)
    {
        if (_prefs == null) return;
        p.Id = _prefs.GetString("player_id", "") ?? "";
        p.Token = _prefs.GetString("player_token", "") ?? "";
        p.Name = _prefs.GetString("player_name", $"Juragan{Random.Shared.Next(100, 999)}") ?? "JuraganSawit";
        p.Avatar.Hat = _prefs.GetString("av_hat", MeshCatalog.HatCaping) ?? MeshCatalog.HatCaping;
        p.Avatar.Back = _prefs.GetString("av_back", MeshCatalog.BackBasket) ?? MeshCatalog.BackBasket;
        p.Avatar.Tool = _prefs.GetString("av_tool", MeshCatalog.ToolEgrek) ?? MeshCatalog.ToolEgrek;
        p.Avatar.OutfitHex = _prefs.GetString("av_hex", "#27AE60") ?? "#27AE60";
        p.Avatar.Glasses = _prefs.GetBoolean("av_glasses", false);
        p.Avatar.WaistParang = _prefs.GetBoolean("av_parang", true);
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
        ed.PutBoolean("av_glasses", _net.Profile.Avatar.Glasses);
        ed.PutBoolean("av_parang", _net.Profile.Avatar.WaistParang);
        ed.Apply();
    }

    private void ScheduleImmersiveFullscreen()
    {
        var win = Window;
        var decor = win?.DecorView;
        if (win == null || decor == null) return;

        try
        {
            win.AddFlags(WindowManagerFlags.KeepScreenOn | WindowManagerFlags.Fullscreen);
            if (OperatingSystem.IsAndroidVersionAtLeast(28) && win.Attributes != null)
            {
                var lp = win.Attributes;
                lp.LayoutInDisplayCutoutMode = OperatingSystem.IsAndroidVersionAtLeast(30)
                    ? LayoutInDisplayCutoutMode.Always
                    : LayoutInDisplayCutoutMode.ShortEdges;
                win.Attributes = lp;
            }
            if (OperatingSystem.IsAndroidVersionAtLeast(30))
            {
#pragma warning disable CA1422
                win.SetDecorFitsSystemWindows(false);
#pragma warning restore CA1422
            }
        }
        catch { }

        ApplyImmersiveBarsHide();
        decor.Post(ApplyImmersiveBarsHide);
    }

    private void ApplyImmersiveBarsHide()
    {
        var win = Window;
        var decor = win?.DecorView;
        if (win == null || decor == null) return;
        try
        {
            if (OperatingSystem.IsAndroidVersionAtLeast(30))
            {
                var controller = win.InsetsController;
                if (controller != null)
                {
                    controller.Hide(WindowInsets.Type.StatusBars() | WindowInsets.Type.NavigationBars() | WindowInsets.Type.SystemBars());
                    controller.SystemBarsBehavior = (int)WindowInsetsControllerBehavior.ShowTransientBarsBySwipe;
                }
            }
#pragma warning disable CA1422, CS0618
            decor.SystemUiVisibility = (StatusBarVisibility)(
                SystemUiFlags.ImmersiveSticky | SystemUiFlags.Fullscreen | SystemUiFlags.HideNavigation |
                SystemUiFlags.LayoutFullscreen | SystemUiFlags.LayoutHideNavigation | SystemUiFlags.LayoutStable);
#pragma warning restore CA1422, CS0618
        }
        catch { }
    }

    public override void OnWindowFocusChanged(bool hasFocus)
    {
        base.OnWindowFocusChanged(hasFocus);
        if (hasFocus) ApplyImmersiveBarsHide();
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
