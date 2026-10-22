using System;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace NyawitEngine.Math;

public static class Mat4Utils
{
    public static void CreatePerspective(Span<float> outColMajor, float fovRadians, float aspect, float near, float far)
    {
        outColMajor.Clear();
        float f = 1f / MathF.Tan(fovRadians * 0.5f);
        float nf = 1f / (near - far);
        outColMajor[0] = f / aspect;
        outColMajor[5] = f;
        outColMajor[10] = (far + near) * nf;
        outColMajor[11] = -1f;
        outColMajor[14] = 2f * far * near * nf;
    }

    public static void CreateLookAt(Span<float> outColMajor, float ex, float ey, float ez, float tx, float ty, float tz)
    {
        float zx = ex - tx, zy = ey - ty, zz = ez - tz;
        float zl = MathF.Sqrt(zx * zx + zy * zy + zz * zz);
        if (zl < 1e-6f) zl = 1f;
        zx /= zl; zy /= zl; zz /= zl;

        // Cross(Up(0,1,0), Z)
        float xx = zz, xy = 0f, xz = -zx;
        float xl = MathF.Sqrt(xx * xx + xz * xz);
        if (xl < 1e-6f) { xx = 1f; xz = 0f; xl = 1f; }
        xx /= xl; xz /= xl;

        float yx = zy * xz - zz * xy;
        float yy = zz * xx - zx * xz;
        float yz = zx * xy - zy * xx;

        outColMajor[0] = xx; outColMajor[1] = yx; outColMajor[2] = zx; outColMajor[3] = 0f;
        outColMajor[4] = xy; outColMajor[5] = yy; outColMajor[6] = zy; outColMajor[7] = 0f;
        outColMajor[8] = xz; outColMajor[9] = yz; outColMajor[10] = zz; outColMajor[11] = 0f;
        outColMajor[12] = -(xx * ex + xy * ey + xz * ez);
        outColMajor[13] = -(yx * ex + yy * ey + yz * ez);
        outColMajor[14] = -(zx * ex + zy * ey + zz * ez);
        outColMajor[15] = 1f;
    }

    public static void Multiply(Span<float> dst, ReadOnlySpan<float> a, ReadOnlySpan<float> b)
    {
        for (int c = 0; c < 4; c++)
        {
            float b0 = b[c * 4], b1 = b[c * 4 + 1], b2 = b[c * 4 + 2], b3 = b[c * 4 + 3];
            dst[c * 4 + 0] = a[0] * b0 + a[4] * b1 + a[8] * b2 + a[12] * b3;
            dst[c * 4 + 1] = a[1] * b0 + a[5] * b1 + a[9] * b2 + a[13] * b3;
            dst[c * 4 + 2] = a[2] * b0 + a[6] * b1 + a[10] * b2 + a[14] * b3;
            dst[c * 4 + 3] = a[3] * b0 + a[7] * b1 + a[11] * b2 + a[15] * b3;
        }
    }

    /// <summary>
    /// Writes a 16-float hardware instance record [row0(4), row1(4), row2(4), tintAndWind(4)] directly
    /// into a pre-allocated float buffer with ZERO heap allocations.
    /// </summary>
    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static int WriteInstanceTRS(
        float[] buffer,
        int cursor,
        float tx, float ty, float tz,
        float rx, float ry, float rz,
        float sx, float sy, float sz,
        float cr = 1f, float cg = 1f, float cb = 1f, float wind = 0f)
    {
        if ((uint)cursor >= (uint)(buffer.Length / 16)) return cursor;

        float cx = MathF.Cos(rx), sxn = MathF.Sin(rx);
        float cy = MathF.Cos(ry), syn = MathF.Sin(ry);
        float cz = MathF.Cos(rz), szn = MathF.Sin(rz);

        int o = cursor * 16;
        buffer[o + 0] = (cy * cz + syn * sxn * szn) * sx;
        buffer[o + 1] = (-cy * szn + syn * sxn * cz) * sy;
        buffer[o + 2] = (syn * cx) * sz;
        buffer[o + 3] = tx;

        buffer[o + 4] = (cx * szn) * sx;
        buffer[o + 5] = (cx * cz) * sy;
        buffer[o + 6] = (-sxn) * sz;
        buffer[o + 7] = ty;

        buffer[o + 8] = (-syn * cz + cy * sxn * szn) * sx;
        buffer[o + 9] = (syn * szn + cy * sxn * cz) * sy;
        buffer[o + 10] = (cy * cx) * sz;
        buffer[o + 11] = tz;

        buffer[o + 12] = cr;
        buffer[o + 13] = cg;
        buffer[o + 14] = cb;
        buffer[o + 15] = wind;
        return cursor + 1;
    }

    public static bool ProjectWorldToScreen(
        ReadOnlySpan<float> vp,
        float wx, float wy, float wz,
        float screenW, float screenH,
        out float sx, out float sy)
    {
        float x = vp[0] * wx + vp[4] * wy + vp[8] * wz + vp[12];
        float y = vp[1] * wx + vp[5] * wy + vp[9] * wz + vp[13];
        float w = vp[3] * wx + vp[7] * wy + vp[11] * wz + vp[15];
        if (w <= 0.12f) { sx = sy = 0f; return false; }
        sx = (x / w * 0.5f + 0.5f) * screenW;
        sy = (0.5f - y / w * 0.5f) * screenH;
        return sx >= -120f && sx <= screenW + 120f && sy >= -80f && sy <= screenH + 80f;
    }
}

public static class SimdCuller
{
    private static bool _nativeChecked;
    private static bool _nativeAvailable;

    [DllImport("nyawit_simd", CallingConvention = CallingConvention.Cdecl)]
    private static extern unsafe int nyawit_cull_and_select_lod(
        float* positionsXyz,
        int count,
        float eyeX, float eyeY, float eyeZ,
        float fwdX, float fwdY, float fwdZ,
        float lod0Dist, float lod1Dist, float maxDist,
        float minCosFov,
        sbyte* outLod);

    public static unsafe int SelectLodBatch(
        float[] positionsXyz,
        int count,
        float eyeX, float eyeY, float eyeZ,
        float fwdX, float fwdY, float fwdZ,
        float lod0Dist, float lod1Dist, float maxDist,
        sbyte[] outLod)
    {
        if (!_nativeChecked)
        {
            _nativeChecked = true;
            try
            {
                fixed (float* p = positionsXyz)
                fixed (sbyte* o = outLod)
                {
                    nyawit_cull_and_select_lod(p, 0, 0, 0, 0, 0, 0, 1, 10, 20, 50, 0.35f, o);
                    _nativeAvailable = true;
                }
            }
            catch
            {
                _nativeAvailable = false;
            }
        }

        if (_nativeAvailable)
        {
            fixed (float* p = positionsXyz)
            fixed (sbyte* o = outLod)
            {
                return nyawit_cull_and_select_lod(p, count, eyeX, eyeY, eyeZ, fwdX, fwdY, fwdZ, lod0Dist, lod1Dist, maxDist, 0.32f, o);
            }
        }

        // Pure managed C# fast fallback (identical behavior on x64 unit tests & emulators)
        float l0Sq = lod0Dist * lod0Dist;
        float l1Sq = lod1Dist * lod1Dist;
        float maxSq = maxDist * maxDist;
        int visible = 0;

        for (int i = 0; i < count; i++)
        {
            float dx = positionsXyz[i * 3 + 0] - eyeX;
            float dy = (positionsXyz[i * 3 + 1] + 3f) - eyeY;
            float dz = positionsXyz[i * 3 + 2] - eyeZ;
            float d2 = dx * dx + dy * dy + dz * dz;
            if (d2 > maxSq) { outLod[i] = -1; continue; }
            if (d2 > 196f)
            {
                float dot = dx * fwdX + dy * fwdY + dz * fwdZ;
                if (dot < 0f && (dot * dot) > (d2 * 0.1024f)) { outLod[i] = -1; continue; }
            }
            outLod[i] = d2 < l0Sq ? (sbyte)0 : (d2 < l1Sq ? (sbyte)1 : (sbyte)2);
            visible++;
        }
        return visible;
    }
}
