#!/usr/bin/env python3
"""
Zero-dependency Android 14 (API 34) emulator verification harness for NYAWIT LIVE v6.0.0.
Uses frame-acknowledged loopback TCP sync (adb forward tcp:18765 tcp:18765) to capture all 6 live
stages (splash, separate 3D garage lobby, loading, on-foot plantation, Canter driving with arrow+pedal
HUD, and custom PENGATURAN modal) in one uninterrupted Android process PID.
"""
import os
import re
import struct
import subprocess
import sys
import time
import urllib.request

ACTIVITY = "id.my.xyverse.nyawitlive/id.my.xyverse.nyawitlive.MainActivity"
APK_PATH = os.environ.get("NYAWIT_APK_PATH", "dist-apk/NYAWIT-LIVE-v6-x86_64.apk")
SCREENSHOT_PREFIX = os.environ.get("NYAWIT_SCREENSHOT_PREFIX", "android_v6")


def log_msg(msg: str):
    print(msg, flush=True)


def inspect_png_stdlib(path: str, min_kb: float = 12.0):
    with open(path, "rb") as f:
        data = f.read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path}: invalid PNG signature"
    pos = 8
    width = height = 0
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            width, height = struct.unpack(">II", chunk[:8])
        elif ctype == b"IEND":
            break
    compressed_kb = len(data) / 1024.0
    log_msg(f"  [ANDROID 14 v6 FRAME] {path}: size=({width}, {height}), pngSize={compressed_kb:.1f} KB")
    assert width > height, f"Expected landscape frame, got {width}x{height}"
    assert compressed_kb > min_kb, f"Frame appears blank/incomplete ({compressed_kb:.1f} KB < {min_kb} KB)"


def run(cmd, check=True, binary=False):
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if check and res.returncode != 0:
        out = res.stdout.decode("utf-8", errors="replace")
        raise RuntimeError(f"Command {cmd} failed ({res.returncode}):\n{out}")
    return res.stdout if binary else res.stdout.decode("utf-8", errors="replace")


def sync_stage(stage_name: str):
    deadline = time.time() + 50.0
    last_err = None
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:18765/stage?s={stage_name}", timeout=18.0) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                log_msg(f"  -> Frame-Synced Stage '{stage_name}' (attempt {attempt}): {body}")
                return
        except Exception as ex:
            last_err = ex
            pid_now = run(["adb", "shell", "pidof", "id.my.xyverse.nyawitlive"], check=False).strip()
            log_msg(f"  [retry stage={stage_name} attempt={attempt} pid='{pid_now}'] {ex}")
            run(["adb", "forward", "tcp:18765", "tcp:18765"], check=False)
            time.sleep(0.6)
    raise RuntimeError(f"Timed out waiting for stage server '{stage_name}': {last_err}")


def capture_screen(out_path: str):
    png = subprocess.check_output(["adb", "exec-out", "screencap", "-p"])
    with open(out_path, "wb") as f:
        f.write(png)
    log_msg(f"Captured {out_path} ({len(png):,} bytes)")


def dump_diagnostics(tag: str):
    log = run(["adb", "logcat", "-d"], check=False)
    os.makedirs("dist-apk", exist_ok=True)
    with open("dist-apk/android_logcat.txt", "w", encoding="utf-8") as f:
        f.write(log)
    log_msg(f"\n=== DIAGNOSTIC LOGCAT TAIL ({tag}) ===")
    interesting = [
        ln for ln in log.splitlines()
        if re.search(r"AndroidRuntime|mono-rt|Nyawit|FATAL|Exception|EGL|GLES|ANR", ln, re.I)
    ]
    for ln in interesting[-90:]:
        log_msg(ln)
    return log


def main():
    os.makedirs("dist-apk", exist_ok=True)
    try:
        log_msg(f"=== [1/8] Configuring immersive mode and installing {APK_PATH} ===")
        run(["adb", "shell", "cmd", "overlay", "enable", "com.android.internal.systemui.navbar.gestural"], check=False)
        run(["adb", "shell", "settings", "put", "global", "policy_control", "immersive.full=*"], check=False)
        run(["adb", "shell", "settings", "put", "secure", "immersive_mode_confirmations", "confirmed"], check=False)
        run(["adb", "shell", "settings", "put", "system", "screen_brightness_mode", "0"], check=False)
        run(["adb", "shell", "settings", "put", "system", "screen_brightness", "255"], check=False)
        run(["adb", "shell", "wm", "dismiss-keyguard"], check=False)
        run(["adb", "shell", "input", "keyevent", "82"], check=False)
        run(["adb", "shell", "am", "broadcast", "-a", "android.intent.action.CLOSE_SYSTEM_DIALOGS"], check=False)
        time.sleep(1.0)

        install_out = run(["adb", "install", "-r", APK_PATH])
        log_msg(install_out.strip())
        run(["adb", "logcat", "-c"], check=False)
        run(["adb", "forward", "tcp:18765", "tcp:18765"])

        log_msg("=== [2/8] Cold-Launching App & Frame-Syncing Stage 1: Boot Splash ===")
        run(["adb", "shell", "am", "start", "-W", "-n", ACTIVITY, "--es", "stage", "splash"])
        sync_stage("splash")

        pid1 = run(["adb", "shell", "pidof", "id.my.xyverse.nyawitlive"], check=False).strip()
        log_msg(f"Live Android Process PID: '{pid1}'")
        if not pid1:
            dump_diagnostics("COLD_LAUNCH_EXIT")
            sys.exit(1)
        capture_screen(f"dist-apk/{SCREENSHOT_PREFIX}_splash_hd.png")

        log_msg("=== [3/8] Frame-Syncing Stage 2: Dedicated Separate 3D Garage Showroom Lobby ===")
        sync_stage("garage")
        capture_screen(f"dist-apk/{SCREENSHOT_PREFIX}_lobby_garage_hd.png")

        log_msg("=== [4/8] Frame-Syncing Stage 3: Full-Screen 'MENYIAPKAN DUNIA' World Streaming ===")
        sync_stage("loading")
        capture_screen(f"dist-apk/{SCREENSHOT_PREFIX}_loading_hd.png")

        log_msg("=== [5/8] Frame-Syncing Stage 4: v6.0 Plantation (220 Mature Palms, 96 Saplings, Landmarks & TBS Hold) ===")
        sync_stage("onfoot")
        capture_screen(f"dist-apk/{SCREENSHOT_PREFIX}_onfoot_hold_hd.png")

        log_msg("=== [6/9] Frame-Syncing Stage 5: Canter FE 74 HD + Anime Outline + Semi-ENB Dingin + Arrow/Pedals HUD ===")
        sync_stage("canter")
        capture_screen(f"dist-apk/{SCREENSHOT_PREFIX}_canter_drive_hd.png")

        log_msg("=== [7/9] Frame-Syncing Stage 6: Fog Asap Karhutla Sumatra + Anime Outline + Canter Headlights ===")
        sync_stage("karhutla")
        capture_screen(f"dist-apk/{SCREENSHOT_PREFIX}_karhutla_hd.png")

        log_msg("=== [8/9] Frame-Syncing Stage 7: Custom In-Game 'PENGATURAN' Panel (ENB Dingin / Asap Karhutla & Anime Outline) ===")
        sync_stage("settings")
        capture_screen(f"dist-apk/{SCREENSHOT_PREFIX}_settings_hd.png")

        pid2 = run(["adb", "shell", "pidof", "id.my.xyverse.nyawitlive"], check=False).strip()
        log_msg(f"Live Android Process PID after all 7 frame-synced stages: '{pid2}'")
        if not pid2 or pid2 != pid1:
            dump_diagnostics("GAMEPLAY_CRASH_OR_RESTART")
            sys.exit(1)

        log_msg("=== [9/9] Auditing Full Android 14 Logcat & Validating All 7 Full-HD Hardware Frames ===")
        log = dump_diagnostics("HEALTHY_RUN_SUMMARY")
        if "FATAL EXCEPTION" in log or "Startup exception:" in log:
            log_msg("ERROR: Detected unhandled exception in logcat!")
            sys.exit(1)

        inspect_png_stdlib(f"dist-apk/{SCREENSHOT_PREFIX}_splash_hd.png", min_kb=10.0)
        inspect_png_stdlib(f"dist-apk/{SCREENSHOT_PREFIX}_lobby_garage_hd.png", min_kb=80.0)
        inspect_png_stdlib(f"dist-apk/{SCREENSHOT_PREFIX}_loading_hd.png", min_kb=10.0)
        inspect_png_stdlib(f"dist-apk/{SCREENSHOT_PREFIX}_onfoot_hold_hd.png", min_kb=80.0)
        inspect_png_stdlib(f"dist-apk/{SCREENSHOT_PREFIX}_canter_drive_hd.png", min_kb=80.0)
        inspect_png_stdlib(f"dist-apk/{SCREENSHOT_PREFIX}_karhutla_hd.png", min_kb=60.0)
        inspect_png_stdlib(f"dist-apk/{SCREENSHOT_PREFIX}_settings_hd.png", min_kb=80.0)

        log_msg("=== Android 14 v6.0.0 verification PASSED across all 7 stages in a single uninterrupted PID! ===")
    except Exception:
        dump_diagnostics("STAGE_FAILURE")
        raise


if __name__ == "__main__":
    main()
