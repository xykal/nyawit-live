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

    public static void CreateOrthographic(Span<float> outColMajor, float left, float right, float bottom, float top, float near, float far)
    {
        outColMajor.Clear();
        float rl = 1f / (right - left);
        float tb = 1f / (top - bottom);
        float fn = 1f / (far - near);
        outColMajor[0] = 2f * rl;
        outColMajor[5] = 2f * tb;
        outColMajor[10] = -2f * fn;
        outColMajor[12] = -(right + left) * rl;
        outColMajor[13] = -(top + bottom) * tb;
        outColMajor[14] = -(far + near) * fn;
        outColMajor[15] = 1f;
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

    /// <summary>
    /// Zero-allocation 3x4 affine bone matrix struct for multi-joint skeletal hierarchies:
    ///   - Hip -> Torso -> Neck/Head -> Hat
    ///   - Hip -> Shoulder -> UpperArm -> Elbow -> Forearm+5FingerHand -> Tool
    ///   - Hip -> Thigh -> Knee -> Calf+RubberBoot
    ///   - Chassis -> WheelHub -> Steer -> RollingTire
    /// </summary>
    public struct BoneMat
    {
        public float M00, M01, M02, M03;
        public float M10, M11, M12, M13;
        public float M20, M21, M22, M23;

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public static BoneMat TRS(float tx, float ty, float tz, float rx = 0f, float ry = 0f, float rz = 0f, float sx = 1f, float sy = 1f, float sz = 1f)
        {
            float cx = MathF.Cos(rx), sxn = MathF.Sin(rx);
            float cy = MathF.Cos(ry), syn = MathF.Sin(ry);
            float cz = MathF.Cos(rz), szn = MathF.Sin(rz);
            return new BoneMat
            {
                M00 = (cy * cz + syn * sxn * szn) * sx, M01 = (-cy * szn + syn * sxn * cz) * sy, M02 = (syn * cx) * sz, M03 = tx,
                M10 = (cx * szn) * sx,                  M11 = (cx * cz) * sy,                    M12 = (-sxn) * sz,     M13 = ty,
                M20 = (-syn * cz + cy * sxn * szn) * sx, M21 = (syn * szn + cy * sxn * cz) * sy, M22 = (cy * cx) * sz,  M23 = tz,
            };
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public readonly BoneMat Child(float tx, float ty, float tz, float rx = 0f, float ry = 0f, float rz = 0f, float sx = 1f, float sy = 1f, float sz = 1f)
        {
            BoneMat b = TRS(tx, ty, tz, rx, ry, rz, sx, sy, sz);
            return new BoneMat
            {
                M00 = M00 * b.M00 + M01 * b.M10 + M02 * b.M20,
                M01 = M00 * b.M01 + M01 * b.M11 + M02 * b.M21,
                M02 = M00 * b.M02 + M01 * b.M12 + M02 * b.M22,
                M03 = M00 * b.M03 + M01 * b.M13 + M02 * b.M23 + M03,

                M10 = M10 * b.M00 + M11 * b.M10 + M12 * b.M20,
                M11 = M10 * b.M01 + M11 * b.M11 + M12 * b.M21,
                M12 = M10 * b.M02 + M11 * b.M12 + M12 * b.M22,
                M13 = M10 * b.M03 + M11 * b.M13 + M12 * b.M23 + M13,

                M20 = M20 * b.M00 + M21 * b.M10 + M22 * b.M20,
                M21 = M20 * b.M01 + M21 * b.M11 + M22 * b.M21,
                M22 = M20 * b.M02 + M21 * b.M12 + M22 * b.M22,
                M23 = M20 * b.M03 + M21 * b.M13 + M22 * b.M23 + M23,
            };
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        public readonly int Emit(float[] buffer, int cursor, float cr = 1f, float cg = 1f, float cb = 1f, float wind = 0f)
        {
            if ((uint)cursor >= (uint)(buffer.Length / 16)) return cursor;
            int o = cursor * 16;
            buffer[o + 0] = M00; buffer[o + 1] = M01; buffer[o + 2] = M02; buffer[o + 3] = M03;
            buffer[o + 4] = M10; buffer[o + 5] = M11; buffer[o + 6] = M12; buffer[o + 7] = M13;
            buffer[o + 8] = M20; buffer[o + 9] = M21; buffer[o + 10] = M22; buffer[o + 11] = M23;
            buffer[o + 12] = cr; buffer[o + 13] = cg; buffer[o + 14] = cb; buffer[o + 15] = wind;
            return cursor + 1;
        }
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
    private static bool _native6PlaneChecked;
    private static bool _native6PlaneAvailable;

    [DllImport("nyawit_simd", CallingConvention = CallingConvention.Cdecl)]
    private static extern unsafe void nyawit_extract_frustum_planes(
        float* vpColMajor,
        float* outPlanes24);

    [DllImport("nyawit_simd", CallingConvention = CallingConvention.Cdecl)]
    private static extern unsafe int nyawit_cull_frustum_6plane(
        float* positionsXyz,
        int count,
        float* planes24,
        float eyeX, float eyeY, float eyeZ,
        float centerYOffset,
        float boundRadius,
        float lod0Dist, float lod1Dist, float renderDist,
        sbyte* outLod);

    [DllImport("nyawit_simd", CallingConvention = CallingConvention.Cdecl)]
    private static extern unsafe int nyawit_cull_and_select_lod(
        float* positionsXyz,
        int count,
        float eyeX, float eyeY, float eyeZ,
        float fwdX, float fwdY, float fwdZ,
        float lod0Dist, float lod1Dist, float maxDist,
        float minCosFov,
        sbyte* outLod);

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    private static void NormalizePlane(float a, float b, float c, float d, Span<float> dst4)
    {
        float len2 = a * a + b * b + c * c;
        float inv = len2 > 1e-12f ? (1f / MathF.Sqrt(len2)) : 1f;
        dst4[0] = a * inv;
        dst4[1] = b * inv;
        dst4[2] = c * inv;
        dst4[3] = d * inv;
    }

    public static unsafe void ExtractFrustumPlanes(float[] vpColMajor16, float[] outPlanes24)
    {
        EnsureNative6PlaneProbed();
        if (_native6PlaneAvailable)
        {
            fixed (float* vp = vpColMajor16)
            fixed (float* pl = outPlanes24)
            {
                nyawit_extract_frustum_planes(vp, pl);
                return;
            }
        }
        ExtractFrustumPlanesManaged(vpColMajor16, outPlanes24);
    }

    public static void ExtractFrustumPlanesManaged(ReadOnlySpan<float> vp, Span<float> outPlanes24)
    {
        float r0x = vp[0], r0y = vp[4], r0z = vp[8],  r0w = vp[12];
        float r1x = vp[1], r1y = vp[5], r1z = vp[9],  r1w = vp[13];
        float r2x = vp[2], r2y = vp[6], r2z = vp[10], r2w = vp[14];
        float r3x = vp[3], r3y = vp[7], r3z = vp[11], r3w = vp[15];

        NormalizePlane(r3x + r0x, r3y + r0y, r3z + r0z, r3w + r0w, outPlanes24.Slice(0, 4));
        NormalizePlane(r3x - r0x, r3y - r0y, r3z - r0z, r3w - r0w, outPlanes24.Slice(4, 4));
        NormalizePlane(r3x + r1x, r3y + r1y, r3z + r1z, r3w + r1w, outPlanes24.Slice(8, 4));
        NormalizePlane(r3x - r1x, r3y - r1y, r3z - r1z, r3w - r1w, outPlanes24.Slice(12, 4));
        NormalizePlane(r3x + r2x, r3y + r2y, r3z + r2z, r3w + r2w, outPlanes24.Slice(16, 4));
        NormalizePlane(r3x - r2x, r3y - r2y, r3z - r2z, r3w - r2w, outPlanes24.Slice(20, 4));
    }

    private static unsafe void EnsureNative6PlaneProbed()
    {
        if (_native6PlaneChecked) return;
        _native6PlaneChecked = true;
        try
        {
            float* vp = stackalloc float[16];
            float* pl = stackalloc float[24];
            sbyte* lo = stackalloc sbyte[1];
            vp[0] = vp[5] = vp[10] = vp[15] = 1f;
            nyawit_extract_frustum_planes(vp, pl);
            nyawit_cull_frustum_6plane(vp, 0, pl, 0f, 0f, 0f, 0f, 1f, 10f, 20f, 50f, lo);
            _native6PlaneAvailable = true;
        }
        catch
        {
            _native6PlaneAvailable = false;
        }
    }

    public static unsafe int CullFrustum6Plane(
        float[] positionsXyz,
        int count,
        float[] planes24,
        float eyeX, float eyeY, float eyeZ,
        float centerYOffset,
        float boundRadius,
        float lod0Dist, float lod1Dist, float renderDist,
        sbyte[] outLod)
    {
        EnsureNative6PlaneProbed();
        if (_native6PlaneAvailable)
        {
            fixed (float* pos = positionsXyz)
            fixed (float* pl = planes24)
            fixed (sbyte* ol = outLod)
            {
                return nyawit_cull_frustum_6plane(
                    pos, count, pl, eyeX, eyeY, eyeZ,
                    centerYOffset, boundRadius, lod0Dist, lod1Dist, renderDist, ol);
            }
        }
        return CullFrustum6PlaneManaged(
            positionsXyz, count, planes24, eyeX, eyeY, eyeZ,
            centerYOffset, boundRadius, lod0Dist, lod1Dist, renderDist, outLod);
    }

    public static int CullFrustum6PlaneManaged(
        ReadOnlySpan<float> positionsXyz,
        int count,
        ReadOnlySpan<float> planes24,
        float eyeX, float eyeY, float eyeZ,
        float centerYOffset,
        float boundRadius,
        float lod0Dist, float lod1Dist, float renderDist,
        Span<sbyte> outLod)
    {
        float l0Sq = lod0Dist * lod0Dist;
        float l1Sq = lod1Dist * lod1Dist;
        float maxSq = renderDist * renderDist;
        float negR = -boundRadius;
        int visible = 0;

        for (int i = 0; i < count; i++)
        {
            float px = positionsXyz[i * 3 + 0];
            float py = positionsXyz[i * 3 + 1] + centerYOffset;
            float pz = positionsXyz[i * 3 + 2];

            float dx = px - eyeX;
            float dy = py - eyeY;
            float dz = pz - eyeZ;
            float d2 = dx * dx + dy * dy + dz * dz;

            if (d2 > maxSq)
            {
                outLod[i] = -1;
                continue;
            }

            bool outside = false;
            for (int p = 0; p < 24; p += 4)
            {
                if (planes24[p + 0] * px + planes24[p + 1] * py + planes24[p + 2] * pz + planes24[p + 3] < negR)
                {
                    outside = true;
                    break;
                }
            }
            if (outside)
            {
                outLod[i] = -1;
                continue;
            }

            outLod[i] = d2 < l0Sq ? (sbyte)0 : (d2 < l1Sq ? (sbyte)1 : (sbyte)2);
            visible++;
        }
        return visible;
    }

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
