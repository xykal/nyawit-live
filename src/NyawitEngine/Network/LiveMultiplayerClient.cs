using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using NyawitEngine.World;

namespace NyawitEngine.Network;

public sealed class RoomDescriptor
{
    public string Id { get; set; } = "kebun-sumatera-01";
    public string Label { get; set; } = "SUMATERA BLOK A-01";
    public string Region { get; set; } = "ID-WIB";
    public int Online { get; set; }
    public int Capacity { get; set; } = 32;
}

public sealed class AvatarConfig
{
    public string Hat { get; set; } = "hat_caping";
    public string Back { get; set; } = "back_basket";
    public string Tool { get; set; } = "tool_egrek";
    public string OutfitHex { get; set; } = "#27AE60";
    public string Aura { get; set; } = "leaf";
    public string Title { get; set; } = "Pemanen Kebun";
    public bool Glasses { get; set; } = false;
    public bool WaistParang { get; set; } = true;

    public (float R, float G, float B) GetOutfitRgb()
    {
        string h = (OutfitHex ?? "#27AE60").TrimStart('#');
        if (h.Length == 6 && int.TryParse(h, System.Globalization.NumberStyles.HexNumber, null, out int val))
        {
            return (((val >> 16) & 255) / 255f, ((val >> 8) & 255) / 255f, (val & 255) / 255f);
        }
        return (0.15f, 0.68f, 0.38f);
    }
}

public sealed class PlayerProfile
{
    public string Id { get; set; } = "";
    public string Token { get; set; } = "";
    public string Name { get; set; } = "JuraganSawit";
    public string SocialProvider { get; set; } = "guest";
    public string SocialHandle { get; set; } = "";
    public long Coins { get; set; } = 150000;
    public int Gems { get; set; } = 25;
    public int TotalKg { get; set; }
    public int AllTimeScore { get; set; }
    public int WeeklyPoints { get; set; }
    public int StreakDay { get; set; }
    public bool CanClaimDaily { get; set; } = true;
    public AvatarConfig Avatar { get; set; } = new();
    public List<string> ClaimedTiers { get; set; } = [];
}

public sealed class RemotePeerState
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public float TargetX, TargetY, TargetZ, TargetYaw;
    public float RenderX, RenderY, RenderZ, RenderYaw;
    public float WalkPhase;
    public int AnimState;
    public bool InTruck;
    public bool CarryingTbs;
    public bool PushingAngkong;
    public float SteerAngle;
    public int Cargo;
    public bool SpeakingNow;
    public double VoiceActiveUntilSec;
    public AvatarConfig Avatar { get; set; } = new();
}

public sealed class BoarNetState
{
    public string Id { get; set; } = "";
    public float X, Z, Yaw;
}

public sealed class ChatMessageEntry
{
    public string SenderId { get; set; } = "";
    public string SenderName { get; set; } = "";
    public string Title { get; set; } = "";
    public string Text { get; set; } = "";
    public double ExpiresBubbleAtSec { get; set; }
}

public sealed class LeaderboardRow
{
    public int Rank { get; set; }
    public string Name { get; set; } = "";
    public string Title { get; set; } = "";
    public string SocialHandle { get; set; } = "";
    public int TotalKg { get; set; }
    public int Score { get; set; }
}

public sealed class TournamentTierRow
{
    public string Id { get; set; } = "";
    public int MinPts { get; set; }
    public long Coins { get; set; }
    public int Gems { get; set; }
    public string Label { get; set; } = "";
}

public sealed class LiveMultiplayerSession : IDisposable
{
    public static readonly string[] DefaultWsEndpoints =
    [
        "wss://nyawit.xyverse.my.id/ws"
    ];

    public const string PrimaryApiBase = "https://nyawit.xyverse.my.id";

    private readonly object _sync = new();
    private readonly List<PalmTreeNode> _trees;
    private readonly Dictionary<string, RemotePeerState> _peers = new();
    private readonly List<BoarNetState> _boars =
    [
        new() { Id = "boar_1", X = -24f, Z = 54f, Yaw = 0.4f },
        new() { Id = "boar_2", X = 30f, Z = 62f, Yaw = -1.2f }
    ];
    private readonly List<RoomDescriptor> _rooms =
    [
        new() { Id = "kebun-sumatera-01", Label = "SUMATERA BLOK A-01", Region = "ID-WIB", Online = 1, Capacity = 32 },
        new() { Id = "kebun-riau-02", Label = "RIAU GAMBUT B-02", Region = "ID-WIB", Online = 0, Capacity = 32 },
        new() { Id = "kebun-kalimantan-03", Label = "KALIMANTAN SAWIT C-03", Region = "ID-WITA", Online = 0, Capacity = 32 },
    ];
    private readonly List<ChatMessageEntry> _chat = new(40);
    private readonly List<LeaderboardRow> _globalBoard = new(24);
    private readonly List<LeaderboardRow> _weeklyBoard = new(24);
    private readonly List<TournamentTierRow> _tiers =
    [
        new() { Id = "tier_bronze", MinPts = 250, Coins = 500000, Gems = 35, Label = "250 POIN: IKAT KEPALA PENDEKAR" },
        new() { Id = "tier_silver", MinPts = 800, Coins = 1200000, Gems = 80, Label = "800 POIN: SABIT NAGA SAWIT" },
        new() { Id = "tier_gold", MinPts = 1800, Coins = 2500000, Gems = 160, Label = "1800 POIN: SAYAP DAUN SAWIT EMAS" },
        new() { Id = "tier_champion", MinPts = 3200, Coins = 5000000, Gems = 350, Label = "3200 POIN / TOP 3: MAHKOTA RAJA SAWIT" },
    ];

    private CancellationTokenSource? _cts;
    private ClientWebSocket? _ws;
    private readonly SemaphoreSlim _sendLock = new(1, 1);

    public PlayerProfile Profile { get; } = new();
    public string CurrentRoomId { get; private set; } = "kebun-sumatera-01";
    public bool IsConnected { get; private set; }
    public int PingMs { get; private set; } = 24;
    public string EventTitle { get; private set; } = "PANEN RAYA CERAH";
    public string EventKind { get; private set; } = "CERAH_PANEN";
    public string TournamentWeekId { get; private set; } = "2026-W43";
    public long TournamentEndsAtMs { get; private set; } = DateTimeOffset.UtcNow.AddDays(4).ToUnixTimeMilliseconds();

    public int LocalCargo { get; set; }
    public int LocalGoldCargo { get; set; }

    public event Action<string>? OnToast;
    public event Action<float, float, bool>? OnHarvestSpawnFruit;
    public event Action<string>? OnSoundTrigger;
    public event Action? OnProfilePersisted;
    public event Action<string, string, byte[]>? OnVoiceFrameReceived;

    public LiveMultiplayerSession(List<PalmTreeNode> trees)
    {
        _trees = trees;
    }

    public List<RoomDescriptor> GetRoomsSnapshot()
    {
        lock (_sync) return new List<RoomDescriptor>(_rooms);
    }

    public void SelectRoom(string roomId)
    {
        if (string.IsNullOrWhiteSpace(roomId) || roomId == CurrentRoomId) return;
        CurrentRoomId = roomId;
        lock (_sync) _peers.Clear();
        StartBackgroundConnect();
    }

    public async Task RefreshRoomsFromServerAsync()
    {
        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
            string raw = await http.GetStringAsync($"{PrimaryApiBase}/api/rooms");
            using var doc = JsonDocument.Parse(raw);
            if (!doc.RootElement.TryGetProperty("rooms", out var arr) || arr.ValueKind != JsonValueKind.Array) return;
            var fresh = new List<RoomDescriptor>();
            foreach (var r in arr.EnumerateArray())
            {
                fresh.Add(new RoomDescriptor
                {
                    Id = r.GetProperty("id").GetString() ?? "kebun-sumatera-01",
                    Label = (r.GetProperty("label").GetString() ?? "KEBUN LIVE").ToUpperInvariant(),
                    Region = r.TryGetProperty("region", out var reg) ? reg.GetString() ?? "ID" : "ID",
                    Online = r.TryGetProperty("online", out var onl) ? onl.GetInt32() : 0,
                    Capacity = r.TryGetProperty("capacity", out var cap) ? cap.GetInt32() : 32,
                });
            }
            if (fresh.Count > 0)
            {
                lock (_sync)
                {
                    _rooms.Clear();
                    _rooms.AddRange(fresh);
                }
            }
        }
        catch { }
    }

    private static byte[] BuildJsonBytes(Action<Utf8JsonWriter> writeBody)
    {
        using var ms = new MemoryStream(256);
        using (var writer = new Utf8JsonWriter(ms))
        {
            writer.WriteStartObject();
            writeBody(writer);
            writer.WriteEndObject();
        }
        return ms.ToArray();
    }

    public void StartBackgroundConnect()
    {
        _cts?.Cancel();
        _cts = new CancellationTokenSource();
        _ = Task.Run(() => RefreshRoomsFromServerAsync());
        _ = Task.Run(() => ConnectLoopAsync(_cts.Token));
    }

    public async Task<bool> ConnectOnceForTestAsync(string wsUrl, CancellationToken ct)
    {
        using var ws = new ClientWebSocket();
        await ws.ConnectAsync(new Uri(wsUrl), ct);
        byte[] hello = BuildJsonBytes(w =>
        {
            w.WriteString("type", "hello");
            w.WriteString("roomId", CurrentRoomId);
            w.WriteString("playerId", Profile.Id);
            w.WriteString("token", Profile.Token);
            w.WriteString("name", Profile.Name);
        });
        await ws.SendAsync(hello, WebSocketMessageType.Text, true, ct);

        byte[] buf = new byte[65536];
        using var ms = new MemoryStream();
        while (string.IsNullOrEmpty(Profile.Id) && !ct.IsCancellationRequested)
        {
            ms.SetLength(0);
            WebSocketReceiveResult res;
            do
            {
                res = await ws.ReceiveAsync(buf, ct);
                ms.Write(buf, 0, res.Count);
            } while (!res.EndOfMessage);

            ProcessServerMessage(Encoding.UTF8.GetString(ms.ToArray()), 0.0);
        }
        try { await ws.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "ok", ct); } catch { }
        return !string.IsNullOrEmpty(Profile.Id);
    }

    private async Task ConnectLoopAsync(CancellationToken ct)
    {
        int epIndex = 0;
        byte[] recvBuf = new byte[65536];

        while (!ct.IsCancellationRequested)
        {
            string baseEp = DefaultWsEndpoints[epIndex % DefaultWsEndpoints.Length];
            epIndex++;
            try
            {
                using var ws = new ClientWebSocket();
                ws.Options.KeepAliveInterval = TimeSpan.FromSeconds(15);
                string fullUrl = $"{baseEp}?room={Uri.EscapeDataString(CurrentRoomId)}&pid={Uri.EscapeDataString(Profile.Id)}&tok={Uri.EscapeDataString(Profile.Token)}&name={Uri.EscapeDataString(Profile.Name)}";
                await ws.ConnectAsync(new Uri(fullUrl), ct);

                _ws = ws;
                IsConnected = true;
                await SendRawBytesAsync(BuildJsonBytes(w =>
                {
                    w.WriteString("type", "hello");
                    w.WriteString("roomId", CurrentRoomId);
                    w.WriteString("playerId", Profile.Id);
                    w.WriteString("token", Profile.Token);
                    w.WriteString("name", Profile.Name);
                }), ct);

                _ = Task.Run(async () =>
                {
                    while (!ct.IsCancellationRequested && ws.State == WebSocketState.Open)
                    {
                        await Task.Delay(5000, ct);
                        long ts = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
                        await SendRawBytesAsync(BuildJsonBytes(w =>
                        {
                            w.WriteString("type", "ping");
                            w.WriteNumber("ts", ts);
                        }), ct);
                    }
                }, ct);

                using var ms = new MemoryStream();
                while (!ct.IsCancellationRequested && ws.State == WebSocketState.Open)
                {
                    ms.SetLength(0);
                    WebSocketReceiveResult result;
                    do
                    {
                        result = await ws.ReceiveAsync(recvBuf, ct);
                        if (result.MessageType == WebSocketMessageType.Close) break;
                        ms.Write(recvBuf, 0, result.Count);
                    } while (!result.EndOfMessage);

                    if (result.MessageType == WebSocketMessageType.Close) break;
                    string json = Encoding.UTF8.GetString(ms.ToArray());
                    ProcessServerMessage(json, NyawitEngine.Core.Time.TotalTime);
                }
            }
            catch
            {
                // Seamless retry / offline tolerance
            }
            finally
            {
                IsConnected = false;
                _ws = null;
            }

            try { await Task.Delay(2200, ct); } catch { break; }
        }
    }

    private async Task SendRawBytesAsync(byte[] payload, CancellationToken ct = default)
    {
        var ws = _ws;
        if (ws == null || ws.State != WebSocketState.Open) return;
        await _sendLock.WaitAsync(ct);
        try
        {
            if (ws.State == WebSocketState.Open)
                await ws.SendAsync(payload, WebSocketMessageType.Text, true, ct);
        }
        catch { }
        finally
        {
            _sendLock.Release();
        }
    }

    public void SendPlayerState(float x, float y, float z, float yaw, int anim, bool inTruck, bool carryingTbs = false, bool pushingAngkong = false, float steerAngle = 0f)
    {
        _ = SendRawBytesAsync(BuildJsonBytes(w =>
        {
            w.WriteString("type", "state");
            w.WriteNumber("x", System.Math.Round(x, 2));
            w.WriteNumber("y", System.Math.Round(y, 2));
            w.WriteNumber("z", System.Math.Round(z, 2));
            w.WriteNumber("yaw", System.Math.Round(yaw, 3));
            w.WriteNumber("anim", anim);
            w.WriteBoolean("inTruck", inTruck);
            w.WriteBoolean("heldTbs", carryingTbs);
            w.WriteBoolean("pushingAngkong", pushingAngkong);
            w.WriteNumber("steerAngle", System.Math.Round(steerAngle, 3));
        }));
    }

    public void SendLoadTbs(int units, int goldUnits)
    {
        LocalCargo = System.Math.Min(24, LocalCargo + units);
        LocalGoldCargo = System.Math.Min(24, LocalGoldCargo + goldUnits);
        if (IsConnected)
        {
            _ = SendRawBytesAsync(BuildJsonBytes(w =>
            {
                w.WriteString("type", "load_tbs");
                w.WriteNumber("units", units);
                w.WriteNumber("goldUnits", goldUnits);
            }));
        }
    }

    public void SendVoiceFrame(byte[] ulawBuffer, int length)
    {
        if (!IsConnected || length <= 0 || length > 4096) return;
        string b64 = Convert.ToBase64String(ulawBuffer, 0, length);
        _ = SendRawBytesAsync(BuildJsonBytes(w =>
        {
            w.WriteString("type", "voice");
            w.WriteString("pcm", b64);
        }));
    }

    public void RequestHarvest(int treeId, bool inTruck)
    {
        if (IsConnected)
        {
            _ = SendRawBytesAsync(BuildJsonBytes(w =>
            {
                w.WriteString("type", "harvest");
                w.WriteNumber("treeId", treeId);
            }));
            return;
        }
        if (treeId >= 0 && treeId < _trees.Count && _trees[treeId].State > 0)
        {
            var t = _trees[treeId];
            bool gold = t.State == 2;
            t.State = 0;
            if (inTruck)
            {
                LocalCargo = System.Math.Min(24, LocalCargo + (gold ? 3 : 2));
                if (gold) LocalGoldCargo++;
                OnToast?.Invoke($"PANEN CANTER! MUATAN {LocalCargo}/24");
            }
            else
            {
                OnToast?.Invoke(gold ? "SAWIT EMAS 24K JATUH! AMBIL DAN MUAT KE TRUK/ANGKONG" : "TBS JATUH KE TANAH! AMBIL DAN MUAT KE TRUK/ANGKONG");
            }
            OnHarvestSpawnFruit?.Invoke(t.X, t.Z, gold);
            OnSoundTrigger?.Invoke("harvest");
        }
    }

    public void RequestSell()
    {
        if (IsConnected)
        {
            _ = SendRawBytesAsync(Encoding.UTF8.GetBytes("{\"type\":\"sell\"}"));
            return;
        }
        int kg = LocalCargo * 28 + LocalGoldCargo * 65;
        long earned = kg * 3200L;
        LocalCargo = 0;
        LocalGoldCargo = 0;
        Profile.Coins += earned;
        Profile.TotalKg += kg;
        Profile.AllTimeScore += kg * 12;
        Profile.WeeklyPoints += kg;
        OnSoundTrigger?.Invoke("sell");
        OnToast?.Invoke($"SETOR PKS +{kg} KG (+RP {earned:N0})");
        OnProfilePersisted?.Invoke();
    }

    public void SendHorn() => _ = SendRawBytesAsync(Encoding.UTF8.GetBytes("{\"type\":\"horn\"}"));

    public void SendChat(string text, string channel = "global") => _ = SendRawBytesAsync(BuildJsonBytes(w =>
    {
        w.WriteString("type", "chat");
        w.WriteString("channel", channel);
        w.WriteString("text", text);
    }));

    public void ClaimDaily() => _ = SendRawBytesAsync(Encoding.UTF8.GetBytes("{\"type\":\"daily_claim\"}"));

    public void ClaimTournamentTier(string tierId) => _ = SendRawBytesAsync(BuildJsonBytes(w =>
    {
        w.WriteString("type", "tournament_claim");
        w.WriteString("tierId", tierId);
    }));

    public void RefreshBoards() => _ = SendRawBytesAsync(Encoding.UTF8.GetBytes("{\"type\":\"refresh_boards\"}"));

    public void SaveAvatar(string name, AvatarConfig av)
    {
        Profile.Name = name;
        Profile.Avatar = av;
        OnProfilePersisted?.Invoke();
        _ = SendRawBytesAsync(BuildJsonBytes(w =>
        {
            w.WriteString("type", "avatar");
            w.WriteString("name", name);
            w.WriteStartObject("avatar");
            w.WriteString("hat", av.Hat);
            w.WriteString("back", av.Back);
            w.WriteString("tool", av.Tool);
            w.WriteString("outfitHex", av.OutfitHex);
            w.WriteString("aura", av.Aura);
            w.WriteString("title", av.Title);
            w.WriteEndObject();
        }));
    }

    public void LinkSocial(string provider, string displayName, string handle, string? googleIdToken = null)
    {
        _ = SendRawBytesAsync(BuildJsonBytes(w =>
        {
            w.WriteString("type", "auth_social");
            w.WriteString("provider", provider);
            w.WriteString("displayName", displayName);
            w.WriteString("handle", handle);
            if (!string.IsNullOrEmpty(googleIdToken)) w.WriteString("googleIdToken", googleIdToken);
        }));
    }

    public async Task<(string ShareUrl, string ShareText)> CreateShareCardAsync()
    {
        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(8) };
            byte[] body = BuildJsonBytes(w =>
            {
                w.WriteString("playerId", Profile.Id);
                w.WriteString("playerName", Profile.Name);
                w.WriteString("title", Profile.Avatar.Title);
                w.WriteNumber("totalKg", Profile.TotalKg);
                w.WriteNumber("score", Profile.AllTimeScore);
                w.WriteNumber("weeklyPoints", Profile.WeeklyPoints);
                w.WriteString("socialHandle", Profile.SocialHandle);
                w.WriteString("hat", Profile.Avatar.Hat);
            });
            using var content = new ByteArrayContent(body);
            content.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("application/json");
            using var resp = await http.PostAsync($"{PrimaryApiBase}/api/share", content);
            string raw = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(raw);
            string url = doc.RootElement.GetProperty("shareUrl").GetString() ?? PrimaryApiBase;
            string txt = doc.RootElement.GetProperty("shareText").GetString() ?? url;
            return (url, txt);
        }
        catch
        {
            string fallback = $"NYAWIT LIVE 3D - {Profile.Name} [{Profile.Avatar.Title}] SETORAN {Profile.TotalKg:N0} KG TBS DI {PrimaryApiBase}";
            return (PrimaryApiBase, fallback);
        }
    }

    public void CopyRenderState(
        List<RemotePeerState> dstPeers,
        List<BoarNetState> dstBoars,
        List<ChatMessageEntry> dstChat,
        float dt)
    {
        double now = NyawitEngine.Core.Time.TotalTime;
        lock (_sync)
        {
            dstPeers.Clear();
            float k = System.Math.Min(1f, dt * 9.5f);
            foreach (var p in _peers.Values)
            {
                float dx = p.TargetX - p.RenderX, dz = p.TargetZ - p.RenderZ;
                p.RenderX += dx * k;
                p.RenderZ += dz * k;
                p.RenderY = PlantationWorld.SurfaceHeight(p.RenderX, p.RenderZ);
                float dyaw = p.TargetYaw - p.RenderYaw;
                while (dyaw > MathF.PI) dyaw -= MathF.PI * 2f;
                while (dyaw < -MathF.PI) dyaw += MathF.PI * 2f;
                p.RenderYaw += dyaw * k;
                if (dx * dx + dz * dz > 0.001f) p.WalkPhase += dt * 9f;
                p.SpeakingNow = p.VoiceActiveUntilSec > now;
                dstPeers.Add(p);
            }
            dstBoars.Clear();
            dstBoars.AddRange(_boars);
            dstChat.Clear();
            dstChat.AddRange(_chat);
        }
    }

    public (List<LeaderboardRow> Global, List<LeaderboardRow> Weekly, List<TournamentTierRow> Tiers) GetBoardsSnapshot()
    {
        lock (_sync)
        {
            return (new List<LeaderboardRow>(_globalBoard), new List<LeaderboardRow>(_weeklyBoard), new List<TournamentTierRow>(_tiers));
        }
    }

    private void ProcessServerMessage(string json, double nowEngineSec)
    {
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;
        if (!root.TryGetProperty("type", out var typeProp)) return;
        string type = typeProp.GetString() ?? "";

        switch (type)
        {
            case "welcome":
                if (root.TryGetProperty("roomId", out var rmEl) && rmEl.GetString() is string rid && !string.IsNullOrEmpty(rid))
                    CurrentRoomId = rid;
                if (root.TryGetProperty("profile", out var profEl)) ParseProfile(profEl);
                if (root.TryGetProperty("trees", out var treesEl) && treesEl.ValueKind == JsonValueKind.Array)
                {
                    int i = 0;
                    foreach (var st in treesEl.EnumerateArray())
                        if (i < _trees.Count) _trees[i++].State = st.GetInt32();
                }
                if (root.TryGetProperty("event", out var evEl)) ParseEvent(evEl);
                lock (_sync)
                {
                    if (root.TryGetProperty("globalLeaderboard", out var lbEl)) ParseBoard(lbEl, _globalBoard, isWeekly: false);
                    if (root.TryGetProperty("tournament", out var trEl)) ParseTournament(trEl);
                    if (root.TryGetProperty("chatHistory", out var chEl) && chEl.ValueKind == JsonValueKind.Array)
                    {
                        _chat.Clear();
                        foreach (var c in chEl.EnumerateArray()) AppendChatLocked(c, nowEngineSec);
                    }
                }
                OnProfilePersisted?.Invoke();
                break;

            case "world":
                lock (_sync)
                {
                    if (root.TryGetProperty("peers", out var peersEl) && peersEl.ValueKind == JsonValueKind.Array)
                    {
                        var seen = new HashSet<string>();
                        foreach (var pe in peersEl.EnumerateArray())
                        {
                            string id = pe.GetProperty("id").GetString() ?? "";
                            if (string.IsNullOrEmpty(id) || id == Profile.Id) continue;
                            seen.Add(id);
                            float px = pe.GetProperty("x").GetSingle();
                            float py = pe.GetProperty("y").GetSingle();
                            float pz = pe.GetProperty("z").GetSingle();
                            float pyaw = pe.GetProperty("yaw").GetSingle();
                            if (!_peers.TryGetValue(id, out var peer))
                            {
                                peer = new RemotePeerState { Id = id, RenderX = px, RenderY = py, RenderZ = pz, RenderYaw = pyaw };
                                _peers[id] = peer;
                            }
                            peer.Name = pe.GetProperty("n").GetString() ?? "Pemanen";
                            peer.TargetX = px; peer.TargetY = py; peer.TargetZ = pz; peer.TargetYaw = pyaw;
                            peer.AnimState = pe.GetProperty("a").GetInt32();
                            peer.InTruck = pe.GetProperty("tr").GetInt32() != 0;
                            peer.Cargo = pe.GetProperty("cg").GetInt32();
                            peer.CarryingTbs = pe.TryGetProperty("carry", out var cr) && cr.GetInt32() != 0;
                            peer.PushingAngkong = pe.TryGetProperty("cart", out var crt) && crt.GetInt32() != 0;
                            peer.SteerAngle = pe.TryGetProperty("steer", out var st) ? st.GetSingle() : 0f;
                            if (pe.TryGetProperty("av", out var avEl)) peer.Avatar = ParseAvatar(avEl);
                        }
                        var toRemove = new List<string>();
                        foreach (var k in _peers.Keys) if (!seen.Contains(k)) toRemove.Add(k);
                        foreach (var k in toRemove) _peers.Remove(k);
                    }
                    if (root.TryGetProperty("boars", out var bEl) && bEl.ValueKind == JsonValueKind.Array)
                    {
                        _boars.Clear();
                        foreach (var item in bEl.EnumerateArray())
                        {
                            _boars.Add(new BoarNetState
                            {
                                Id = item.GetProperty("id").GetString() ?? "boar",
                                X = item.GetProperty("x").GetSingle(),
                                Z = item.GetProperty("z").GetSingle(),
                                Yaw = item.GetProperty("yaw").GetSingle()
                            });
                        }
                    }
                }
                break;

            case "voice":
                string vSenderId = root.TryGetProperty("senderId", out var vsid) ? vsid.GetString() ?? "" : "";
                string vSenderName = root.TryGetProperty("senderName", out var vsn) ? vsn.GetString() ?? "Pemain" : "Pemain";
                string b64Pcm = root.TryGetProperty("pcm", out var vpcm) ? vpcm.GetString() ?? "" : "";
                if (!string.IsNullOrEmpty(b64Pcm))
                {
                    try
                    {
                        byte[] raw = Convert.FromBase64String(b64Pcm);
                        lock (_sync)
                        {
                            if (_peers.TryGetValue(vSenderId, out var spPeer))
                                spPeer.VoiceActiveUntilSec = nowEngineSec + 0.55;
                        }
                        OnVoiceFrameReceived?.Invoke(vSenderId, vSenderName, raw);
                    }
                    catch { }
                }
                break;

            case "trees_delta":
                if (root.TryGetProperty("changes", out var chg))
                {
                    foreach (var pair in chg.EnumerateArray())
                    {
                        int idx = pair[0].GetInt32();
                        int st = pair[1].GetInt32();
                        if ((uint)idx < (uint)_trees.Count) _trees[idx].State = st;
                    }
                }
                break;

            case "harvest_fx":
                int tid = root.GetProperty("treeId").GetInt32();
                if ((uint)tid < (uint)_trees.Count) _trees[tid].State = 0;
                OnHarvestSpawnFruit?.Invoke(root.GetProperty("x").GetSingle(), root.GetProperty("z").GetSingle(), root.GetProperty("isGold").GetBoolean());
                break;

            case "cargo_sync":
                LocalCargo = root.GetProperty("cargo").GetInt32();
                LocalGoldCargo = root.GetProperty("goldCargo").GetInt32();
                int maxCap = root.GetProperty("maxCap").GetInt32();
                int combo = root.GetProperty("combo").GetInt32();
                bool isG = root.GetProperty("isGold").GetBoolean();
                OnSoundTrigger?.Invoke("harvest");
                OnToast?.Invoke(isG ? $"SAWIT EMAS 24K! COMBO X{combo} [{LocalCargo}/{maxCap}]" : $"PANEN TBS! COMBO X{combo} [{LocalCargo}/{maxCap}]");
                break;

            case "sell_receipt":
                LocalCargo = 0;
                LocalGoldCargo = 0;
                long rp = root.GetProperty("rupiahEarned").GetInt64();
                int tpts = root.GetProperty("tourneyPts").GetInt32();
                if (root.TryGetProperty("profile", out var sp)) ParseProfile(sp);
                lock (_sync)
                {
                    if (root.TryGetProperty("globalLeaderboard", out var glb)) ParseBoard(glb, _globalBoard, isWeekly: false);
                    if (root.TryGetProperty("tournament", out var trn)) ParseTournament(trn);
                }
                OnSoundTrigger?.Invoke("sell");
                OnProfilePersisted?.Invoke();
                OnToast?.Invoke($"SETOR PKS SUKSES! +RP {rp:N0} | +{tpts} POIN TURNAMEN");
                break;

            case "chat":
                lock (_sync) AppendChatLocked(root, nowEngineSec);
                break;

            case "system_notice":
                lock (_sync)
                {
                    _chat.Add(new ChatMessageEntry
                    {
                        SenderId = "sys",
                        SenderName = "MANDOR PKS",
                        Title = "LIVE",
                        Text = root.GetProperty("text").GetString() ?? "",
                        ExpiresBubbleAtSec = 0
                    });
                    if (_chat.Count > 36) _chat.RemoveAt(0);
                }
                break;

            case "event":
                if (root.TryGetProperty("event", out var ev2)) ParseEvent(ev2);
                OnToast?.Invoke($"EVENT DUNIA: {EventTitle}");
                break;

            case "daily_claimed":
                if (root.TryGetProperty("profile", out var dp)) ParseProfile(dp);
                OnSoundTrigger?.Invoke("sell");
                OnProfilePersisted?.Invoke();
                OnToast?.Invoke($"REWARD HARI {root.GetProperty("day").GetInt32()} DIKLAIM!");
                break;

            case "tournament_claimed":
                if (root.TryGetProperty("profile", out var tp)) ParseProfile(tp);
                lock (_sync) { if (root.TryGetProperty("tournament", out var tr3)) ParseTournament(tr3); }
                OnSoundTrigger?.Invoke("sell");
                OnProfilePersisted?.Invoke();
                OnToast?.Invoke("HADIAH EKSKLUSIF TURNAMEN MINGGUAN BERHASIL DIKLAIM!");
                break;

            case "social_linked":
                if (root.TryGetProperty("profile", out var socp)) ParseProfile(socp);
                OnSoundTrigger?.Invoke("sell");
                OnProfilePersisted?.Invoke();
                OnToast?.Invoke($"AKUN {Profile.SocialProvider.ToUpperInvariant()} TERHUBUNG! +30 PERMATA!");
                break;

            case "profile_sync":
                if (root.TryGetProperty("profile", out var ps)) ParseProfile(ps);
                OnProfilePersisted?.Invoke();
                break;

            case "boards":
                lock (_sync)
                {
                    if (root.TryGetProperty("globalLeaderboard", out var b1)) ParseBoard(b1, _globalBoard, isWeekly: false);
                    if (root.TryGetProperty("tournament", out var b2)) ParseTournament(b2);
                }
                break;

            case "pong":
                long sent = root.GetProperty("clientTs").GetInt64();
                PingMs = (int)System.Math.Clamp(DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() - sent, 8, 999);
                break;

            case "toast":
                OnToast?.Invoke(root.GetProperty("text").GetString() ?? "");
                break;
        }
    }

    private void ParseProfile(JsonElement el)
    {
        Profile.Id = el.GetProperty("id").GetString() ?? Profile.Id;
        Profile.Token = el.GetProperty("token").GetString() ?? Profile.Token;
        Profile.Name = el.GetProperty("name").GetString() ?? Profile.Name;
        Profile.SocialProvider = el.GetProperty("socialProvider").GetString() ?? "guest";
        Profile.SocialHandle = el.TryGetProperty("socialHandle", out var sh) ? sh.GetString() ?? "" : "";
        Profile.Coins = el.GetProperty("coins").GetInt64();
        Profile.Gems = el.GetProperty("gems").GetInt32();
        Profile.TotalKg = el.GetProperty("totalKg").GetInt32();
        Profile.AllTimeScore = el.GetProperty("allTimeScore").GetInt32();
        Profile.WeeklyPoints = el.GetProperty("weeklyPoints").GetInt32();
        Profile.StreakDay = el.GetProperty("streakDay").GetInt32();
        Profile.CanClaimDaily = el.GetProperty("canClaimDaily").GetBoolean();
        if (el.TryGetProperty("avatar", out var av)) Profile.Avatar = ParseAvatar(av);
        if (el.TryGetProperty("claimedTiers", out var ct) && ct.ValueKind == JsonValueKind.Array)
        {
            Profile.ClaimedTiers.Clear();
            foreach (var item in ct.EnumerateArray())
                if (item.GetString() is string s) Profile.ClaimedTiers.Add(s);
        }
    }

    private static AvatarConfig ParseAvatar(JsonElement av) => new()
    {
        Hat = av.TryGetProperty("hat", out var h) ? h.GetString() ?? "hat_caping" : "hat_caping",
        Back = av.TryGetProperty("back", out var b) ? b.GetString() ?? "back_basket" : "back_basket",
        Tool = av.TryGetProperty("tool", out var t) ? t.GetString() ?? "tool_egrek" : "tool_egrek",
        OutfitHex = av.TryGetProperty("outfitHex", out var o) ? o.GetString() ?? "#27AE60" : "#27AE60",
        Aura = av.TryGetProperty("aura", out var a) ? a.GetString() ?? "leaf" : "leaf",
        Title = av.TryGetProperty("title", out var tl) ? tl.GetString() ?? "Pemanen Kebun" : "Pemanen Kebun",
    };

    private void ParseEvent(JsonElement ev)
    {
        EventKind = ev.GetProperty("kind").GetString() ?? "CERAH_PANEN";
        EventTitle = ev.GetProperty("title").GetString() ?? "PANEN RAYA CERAH";
    }

    private static void ParseBoard(JsonElement arr, List<LeaderboardRow> target, bool isWeekly)
    {
        target.Clear();
        if (arr.ValueKind != JsonValueKind.Array) return;
        foreach (var r in arr.EnumerateArray())
        {
            target.Add(new LeaderboardRow
            {
                Rank = r.GetProperty("rank").GetInt32(),
                Name = r.GetProperty("name").GetString() ?? "",
                Title = r.TryGetProperty("title", out var t) ? t.GetString() ?? "" : "",
                SocialHandle = r.TryGetProperty("socialHandle", out var sh) ? sh.GetString() ?? "" : "",
                TotalKg = r.TryGetProperty(isWeekly ? "kgDelivered" : "totalKg", out var kg) ? kg.GetInt32() : 0,
                Score = r.TryGetProperty(isWeekly ? "points" : "score", out var sc) ? sc.GetInt32() : 0,
            });
        }
    }

    private void ParseTournament(JsonElement tr)
    {
        TournamentWeekId = tr.GetProperty("weekId").GetString() ?? TournamentWeekId;
        TournamentEndsAtMs = tr.GetProperty("endsAtMs").GetInt64();
        if (tr.TryGetProperty("standings", out var st)) ParseBoard(st, _weeklyBoard, isWeekly: true);
    }

    private void AppendChatLocked(JsonElement c, double nowEngineSec)
    {
        _chat.Add(new ChatMessageEntry
        {
            SenderId = c.GetProperty("senderId").GetString() ?? "",
            SenderName = c.GetProperty("senderName").GetString() ?? "Pemain",
            Title = c.TryGetProperty("title", out var tl) ? tl.GetString() ?? "" : "",
            Text = c.GetProperty("text").GetString() ?? "",
            ExpiresBubbleAtSec = nowEngineSec + 7.5
        });
        if (_chat.Count > 36) _chat.RemoveAt(0);
    }

    public int RemotePeerCount
    {
        get { lock (_sync) return _peers.Count; }
    }

    public void Dispose()
    {
        _cts?.Cancel();
        _ws?.Dispose();
    }
}
