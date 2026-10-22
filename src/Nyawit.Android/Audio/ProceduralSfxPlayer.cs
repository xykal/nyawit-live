using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Android.Media;
using NyawitEngine.Network;

namespace Nyawit.AndroidClient.Audio;

/// <summary>
/// High-response procedural foley &amp; UI sound synthesizer:
///   - Tactile UI switches ("ui_click", "ui_open", "world_ready")
///   - Harvest &amp; physics foley ("chop", "harvest", "thud", "pickup", "throw", "load_truck", "load_angkong")
///   - Vehicle audio ("engine_enter", "bump", "horn", "sell")
/// Zero asset bloat (~96 KB PCM total), zero GC churn!
/// </summary>
public sealed class ProceduralSfxPlayer : IDisposable
{
    private const int SampleRate = 22050;
    private readonly Dictionary<string, short[]> _clips = new(StringComparer.Ordinal);
    private bool _disposed;

    public ProceduralSfxPlayer()
    {
        // Crisp mechanical tactical HUD click (fast transient snap + low thock)
        _clips["ui_click"] = Mix(
            BuildSweep(1820f, 860f, 0.022f, 0.28f, square: false, noiseMix: 0.16f),
            BuildSweep(310f, 150f, 0.028f, 0.24f, square: false));

        _clips["ui_open"] = Concat(
            BuildSweep(660f, 880f, 0.042f, 0.22f, square: false),
            BuildSweep(990f, 1320f, 0.055f, 0.24f, square: false));

        _clips["world_ready"] = Concat(
            BuildSweep(523.25f, 528f, 0.075f, 0.32f, false),
            BuildSweep(659.25f, 664f, 0.075f, 0.34f, false),
            BuildSweep(783.99f, 790f, 0.085f, 0.36f, false),
            BuildSweep(1046.5f, 1054f, 0.22f, 0.40f, false));

        // Egrek steel whoosh + fibrous palm stalk cut
        _clips["chop"] = Concat(
            BuildSweep(240f, 560f, 0.055f, 0.30f, false, noiseMix: 0.45f),
            BuildSweep(480f, 115f, 0.095f, 0.48f, false, noiseMix: 0.28f));

        _clips["harvest"] = Concat(
            BuildSweep(587f, 610f, 0.075f, 0.34f, false),
            BuildSweep(880f, 920f, 0.13f, 0.38f, false));

        // Heavy 30kg spiky TBS bunch hitting plantation ground
        _clips["thud"] = BuildSweep(118f, 42f, 0.11f, 0.44f, false, noiseMix: 0.22f);

        // Knee-squat & two-hand TBS lift
        _clips["pickup"] = Concat(
            BuildSweep(230f, 360f, 0.055f, 0.30f, false, noiseMix: 0.18f),
            BuildSweep(440f, 660f, 0.080f, 0.34f, false));

        // Two-handed heave & toss into Canter / Angkong
        _clips["throw"] = BuildSweep(195f, 470f, 0.11f, 0.34f, false, noiseMix: 0.32f);

        // TBS landing in wooden Canter bed + leaf spring bounce squeak!
        _clips["load_truck"] = Concat(
            BuildSweep(135f, 52f, 0.11f, 0.50f, false, noiseMix: 0.25f),
            BuildSweep(540f, 760f, 0.075f, 0.26f, false));

        // TBS landing in steel Angkong tray
        _clips["load_angkong"] = Mix(
            BuildSweep(295f, 175f, 0.095f, 0.42f, false, noiseMix: 0.15f),
            BuildSweep(620f, 580f, 0.070f, 0.22f, false));

        // Canter 4D34 Turbo Diesel ignition roar
        _clips["engine_enter"] = Concat(
            BuildSweep(95f, 145f, 0.08f, 0.36f, true, noiseMix: 0.20f),
            BuildSweep(125f, 196f, 0.16f, 0.40f, true, noiseMix: 0.15f));

        // Chassis solid collision bump
        _clips["bump"] = BuildSweep(140f, 48f, 0.10f, 0.44f, false, noiseMix: 0.30f);

        // Signature Indonesian 6-note Telolet Basuri V3 airhorn!
        _clips["horn"] = Concat(
            BuildSweep(523f, 523f, 0.085f, 0.42f, true),
            BuildSweep(659f, 659f, 0.085f, 0.42f, true),
            BuildSweep(784f, 784f, 0.085f, 0.44f, true),
            BuildSweep(659f, 659f, 0.080f, 0.42f, true),
            BuildSweep(784f, 784f, 0.090f, 0.44f, true),
            BuildSweep(1047f, 1055f, 0.19f, 0.46f, true));

        _clips["sell"] = Concat(
            BuildSweep(523f, 523f, 0.07f, 0.36f, false),
            BuildSweep(659f, 659f, 0.07f, 0.36f, false),
            BuildSweep(784f, 784f, 0.08f, 0.38f, false),
            BuildSweep(1047f, 1060f, 0.20f, 0.44f, false));
    }

    public bool Muted { get; set; }

    public void Play(string name)
    {
        if (_disposed || Muted || !_clips.TryGetValue(name, out var pcm)) return;
        _ = Task.Run(async () =>
        {
            try
            {
                int byteLen = pcm.Length * sizeof(short);
                var attrs = new AudioAttributes.Builder()
                    .SetUsage(AudioUsageKind.Game)!
                    .SetContentType(AudioContentType.Sonification)!
                    .Build()!;
                var fmt = new AudioFormat.Builder()
                    .SetEncoding(Encoding.Pcm16bit)!
                    .SetSampleRate(SampleRate)!
                    .SetChannelMask(ChannelOut.Mono)!
                    .Build()!;
                using var track = new AudioTrack(attrs, fmt, byteLen, AudioTrackMode.Static, 0);
                track.Write(pcm, 0, pcm.Length);
                track.Play();
                await Task.Delay((int)(pcm.Length * 1000.0 / SampleRate) + 45).ConfigureAwait(false);
                track.Stop();
            }
            catch { }
        });
    }

    private static short[] BuildSweep(float fStart, float fEnd, float sec, float amp, bool square, float noiseMix = 0f)
    {
        int n = System.Math.Max(96, (int)(SampleRate * sec));
        short[] data = new short[n];
        double phase = 0.0;
        uint lfsr = 0xACE1u;
        for (int i = 0; i < n; i++)
        {
            float t = i / (float)n;
            float freq = fStart + (fEnd - fStart) * t;
            phase += 2.0 * System.Math.PI * freq / SampleRate;
            float env = (1f - t) * System.Math.Min(1f, i / 48f);
            double wave = System.Math.Sin(phase);
            if (square) wave = wave >= 0 ? 0.65 : -0.65;
            if (noiseMix > 0.001f)
            {
                lfsr = (lfsr >> 1) ^ (uint)(-(lfsr & 1u) & 0xB400u);
                double nz = ((lfsr & 0xFFFFu) / 32768.0) - 1.0;
                wave = wave * (1.0 - noiseMix) + nz * noiseMix;
            }
            data[i] = (short)System.Math.Clamp(wave * amp * env * 32000.0, -32767.0, 32767.0);
        }
        return data;
    }

    private static short[] Mix(short[] a, short[] b)
    {
        int n = System.Math.Max(a.Length, b.Length);
        short[] res = new short[n];
        for (int i = 0; i < n; i++)
        {
            int va = i < a.Length ? a[i] : 0;
            int vb = i < b.Length ? b[i] : 0;
            res[i] = (short)System.Math.Clamp(va + vb, -32767, 32767);
        }
        return res;
    }

    private static short[] Concat(params short[][] parts)
    {
        int total = 0;
        foreach (var p in parts) total += p.Length;
        short[] res = new short[total];
        int off = 0;
        foreach (var p in parts)
        {
            Array.Copy(p, 0, res, off, p.Length);
            off += p.Length;
        }
        return res;
    }

    public void Dispose() => _disposed = true;
}

/// <summary>
/// Real-time 8kHz ITU-T G.711 mu-law Voice Chat transceiver over wss://nyawit.xyverse.my.id/ws!
/// Safely handles devices/emulators without microphones without throwing exceptions.
/// </summary>
public sealed class VoiceChatManager : IDisposable
{
    private const int VoiceRate = 8000;
    private readonly LiveMultiplayerSession _net;
    private AudioTrack? _playTrack;
    private CancellationTokenSource? _micCts;
    private bool _disposed;

    public bool IsMicTransmitting { get; private set; }
    public string LastSpeakerName { get; private set; } = "";
    public long LastVoiceRxMs { get; private set; }
    public float LocalMicLevel { get; private set; }

    public VoiceChatManager(LiveMultiplayerSession net)
    {
        _net = net;
        _net.OnVoiceFrameReceived += HandleIncomingVoiceFrame;
    }

    private void EnsurePlayTrack()
    {
        if (_playTrack != null) return;
        try
        {
            int minBuf = System.Math.Max(3200, AudioTrack.GetMinBufferSize(VoiceRate, ChannelOut.Mono, Encoding.Pcm16bit));
            var attrs = new AudioAttributes.Builder()
                .SetUsage(AudioUsageKind.VoiceCommunication)!
                .SetContentType(AudioContentType.Speech)!
                .Build()!;
            var fmt = new AudioFormat.Builder()
                .SetEncoding(Encoding.Pcm16bit)!
                .SetSampleRate(VoiceRate)!
                .SetChannelMask(ChannelOut.Mono)!
                .Build()!;
            _playTrack = new AudioTrack(attrs, fmt, minBuf * 2, AudioTrackMode.Stream, 0);
            _playTrack.Play();
        }
        catch
        {
            _playTrack = null;
        }
    }

    private void HandleIncomingVoiceFrame(string senderId, string senderName, byte[] ulaw)
    {
        if (_disposed || ulaw.Length == 0) return;
        LastSpeakerName = senderName;
        LastVoiceRxMs = Java.Lang.JavaSystem.CurrentTimeMillis();
        _ = Task.Run(() =>
        {
            try
            {
                EnsurePlayTrack();
                if (_playTrack == null) return;
                short[] pcm = new short[ulaw.Length];
                for (int i = 0; i < ulaw.Length; i++) pcm[i] = DecodeMuLaw(ulaw[i]);
                _playTrack.Write(pcm, 0, pcm.Length);
            }
            catch { }
        });
    }

    public bool MicEnabled => IsMicTransmitting;

    public bool SetMicEnabled(bool enable)
    {
        if (!enable)
        {
            IsMicTransmitting = false;
            LocalMicLevel = 0f;
            _micCts?.Cancel();
            _micCts = null;
            return false;
        }
        if (IsMicTransmitting) return true;

        _micCts?.Cancel();
        var cts = new CancellationTokenSource();
        _micCts = cts;
        IsMicTransmitting = true;

        _ = Task.Run(() => CaptureLoop(cts.Token));
        return true;
    }

    private void CaptureLoop(CancellationToken ct)
    {
        AudioRecord? rec = null;
        try
        {
            int minBuf = System.Math.Max(1600, AudioRecord.GetMinBufferSize(VoiceRate, ChannelIn.Mono, Encoding.Pcm16bit));
            rec = new AudioRecord(AudioSource.VoiceCommunication, VoiceRate, ChannelIn.Mono, Encoding.Pcm16bit, minBuf * 2);
            if (rec.State != State.Initialized)
            {
                IsMicTransmitting = false;
                return;
            }
            rec.StartRecording();
            short[] pcmBuf = new short[1000]; // 125ms voice packet @ 8kHz = 1.0 KB mu-law!
            byte[] ulawBuf = new byte[1000];

            while (!ct.IsCancellationRequested && IsMicTransmitting)
            {
                int read = rec.Read(pcmBuf, 0, pcmBuf.Length);
                if (read <= 0)
                {
                    Thread.Sleep(25);
                    continue;
                }
                long energy = 0;
                for (int i = 0; i < read; i++)
                {
                    energy += System.Math.Abs((int)pcmBuf[i]);
                    ulawBuf[i] = EncodeMuLaw(pcmBuf[i]);
                }
                float avg = (energy / (float)read) / 8000f;
                LocalMicLevel = System.Math.Clamp(avg, 0f, 1f);
                if (avg > 0.015f)
                    _net.SendVoiceFrame(ulawBuf, read);
            }
        }
        catch
        {
            IsMicTransmitting = false;
        }
        finally
        {
            try { rec?.Stop(); } catch { }
            try { rec?.Release(); } catch { }
            rec?.Dispose();
            LocalMicLevel = 0f;
        }
    }

    private static byte EncodeMuLaw(short pcmVal)
    {
        const int BIAS = 0x84;
        const int CLIP = 32635;
        int sign = (pcmVal >> 8) & 0x80;
        int sample = pcmVal < 0 ? -pcmVal : pcmVal;
        if (sample > CLIP) sample = CLIP;
        sample += BIAS;
        int exponent = 7;
        for (int expMask = 0x4000; (sample & expMask) == 0 && exponent > 0; exponent--, expMask >>= 1) { }
        int mantissa = (sample >> (exponent + 3)) & 0x0F;
        return (byte)(~(sign | (exponent << 4) | mantissa));
    }

    private static short DecodeMuLaw(byte ulaw)
    {
        ulaw = (byte)~ulaw;
        int sign = ulaw & 0x80;
        int exponent = (ulaw >> 4) & 0x07;
        int mantissa = ulaw & 0x0F;
        int t = ((mantissa << 3) + 0x84) << exponent;
        t -= 0x84;
        return (short)(sign != 0 ? -t : t);
    }

    public void Dispose()
    {
        _disposed = true;
        SetMicEnabled(false);
        try { _playTrack?.Stop(); } catch { }
        _playTrack?.Dispose();
    }
}
