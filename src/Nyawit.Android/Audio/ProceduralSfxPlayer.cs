using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Android.Media;

namespace Nyawit.AndroidClient.Audio;

/// <summary>
/// Zero-asset procedural PCM audio synthesizer for instant tactile harvesting, truck airhorn & cash SFX.
/// Generates lightweight 16-bit mono buffers once at startup (~48 KB RAM total).
/// </summary>
public sealed class ProceduralSfxPlayer : IDisposable
{
    private const int SampleRate = 22050;
    private readonly Dictionary<string, short[]> _clips = new();
    private bool _disposed;

    public ProceduralSfxPlayer()
    {
        _clips["chop"] = BuildSweep(340f, 95f, 0.10f, 0.45f, square: false);
        _clips["harvest"] = Concat(
            BuildSweep(523f, 540f, 0.09f, 0.35f, false),
            BuildSweep(784f, 820f, 0.14f, 0.40f, false));
        _clips["horn"] = Concat(
            BuildSweep(392f, 392f, 0.11f, 0.45f, true),
            BuildSweep(494f, 494f, 0.11f, 0.45f, true),
            BuildSweep(587f, 600f, 0.18f, 0.45f, true));
        _clips["sell"] = Concat(
            BuildSweep(523f, 523f, 0.08f, 0.36f, false),
            BuildSweep(659f, 659f, 0.08f, 0.36f, false),
            BuildSweep(784f, 784f, 0.09f, 0.38f, false),
            BuildSweep(1047f, 1060f, 0.20f, 0.42f, false));
    }

    public void Play(string name)
    {
        if (_disposed || !_clips.TryGetValue(name, out var pcm)) return;
        _ = Task.Run(() =>
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
                Task.Delay((int)(pcm.Length * 1000.0 / SampleRate) + 60).Wait();
                track.Stop();
            }
            catch { }
        });
    }

    private static short[] BuildSweep(float fStart, float fEnd, float sec, float amp, bool square)
    {
        int n = System.Math.Max(128, (int)(SampleRate * sec));
        short[] data = new short[n];
        double phase = 0.0;
        for (int i = 0; i < n; i++)
        {
            float t = i / (float)n;
            float freq = fStart + (fEnd - fStart) * t;
            phase += 2.0 * System.Math.PI * freq / SampleRate;
            float env = (1f - t) * System.Math.Min(1f, i / 120f);
            double wave = System.Math.Sin(phase);
            if (square) wave = wave >= 0 ? 0.65 : -0.65;
            data[i] = (short)System.Math.Clamp(wave * amp * env * 32000.0, -32767.0, 32767.0);
        }
        return data;
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
