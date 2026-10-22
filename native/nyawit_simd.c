/*
 * nyawit_simd.c — Native C11 / ARM NEON Fast Frustum & Multi-LOD Culler
 * Compiled for arm64-v8a & armeabi-v7a via Android NDK Clang into libnyawit_simd.so
 * Invoked from C# NyawitEngine via [DllImport("nyawit_simd")].
 */

#include <stdint.h>
#include <math.h>

#if defined(__ARM_NEON) || defined(__ARM_NEON__)
#include <arm_neon.h>
#endif

#ifdef _WIN32
#define NYAWIT_API __declspec(dllexport)
#else
#define NYAWIT_API __attribute__((visibility("default")))
#endif

/*
 * Classifies `count` world positions packed as [x0, y0, z0, x1, y1, z1, ...]
 * into `out_lod[i]`:
 *   -1 = culled (beyond max_dist or behind camera frustum cone)
 *    0 = LOD0 (hero close-up detail)
 *    1 = LOD1 (mid-range mesh)
 *    2 = LOD2 (horizon low-poly silhouette)
 * Returns total visible instance count.
 */
NYAWIT_API int32_t nyawit_cull_and_select_lod(
    const float* positions_xyz,
    int32_t count,
    float eye_x,
    float eye_y,
    float eye_z,
    float fwd_x,
    float fwd_y,
    float fwd_z,
    float lod0_dist,
    float lod1_dist,
    float max_dist,
    float min_cos_fov,
    int8_t* out_lod)
{
    const float l0_sq = lod0_dist * lod0_dist;
    const float l1_sq = lod1_dist * lod1_dist;
    const float max_sq = max_dist * max_dist;
    int32_t visible = 0;

    for (int32_t i = 0; i < count; ++i) {
        const float dx = positions_xyz[i * 3 + 0] - eye_x;
        const float dy = (positions_xyz[i * 3 + 1] + 3.0f) - eye_y;
        const float dz = positions_xyz[i * 3 + 2] - eye_z;
        const float d2 = dx * dx + dy * dy + dz * dz;

        if (d2 > max_sq) {
            out_lod[i] = -1;
            continue;
        }
        /* Keep everything within 14m around camera visible regardless of angle (shadows/close trees) */
        if (d2 > 196.0f) {
            const float dot_fwd = dx * fwd_x + dy * fwd_y + dz * fwd_z;
            if (dot_fwd < 0.0f && (dot_fwd * dot_fwd) > (d2 * min_cos_fov * min_cos_fov)) {
                out_lod[i] = -1;
                continue;
            }
        }

        if (d2 < l0_sq) {
            out_lod[i] = 0;
        } else if (d2 < l1_sq) {
            out_lod[i] = 1;
        } else {
            out_lod[i] = 2;
        }
        ++visible;
    }
    return visible;
}
