"""
Quality checks + self-healing helpers for make.py.

  ensure_comfy()                       start ComfyUI if it is not running, wait until it answers
  check(path, speech_seconds, ...)     inspect a finished video, return (problems, warnings, info)

Hard problems (trigger an automatic re-render): missing/tiny file, no video stream, no audio when
speech was expected, silent speech, too short (speech cut off), black or frozen picture, lip sync step failed.
Warnings (reported, never retried): speech/mouth-motion correlation is weak or out of sync. That
metric is only a heuristic (motion in the upper-centre of the frame vs. the speech loudness).
"""
import math, os, re, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FFMPEG = os.path.join(ROOT, "tools", "bin", "ffmpeg.exe")
SERVER = "http://127.0.0.1:8188"


def comfy_up():
    try:
        urllib.request.urlopen(SERVER + "/system_stats", timeout=3).read()
        return True
    except Exception:
        return False


def ensure_comfy(wait=240):
    """Make sure ComfyUI answers; start it in its own window if it died."""
    if comfy_up():
        return
    print("  ComfyUI is not responding -> starting it ...")
    subprocess.Popen(["cmd", "/c", "start", "ComfyUI", os.path.join(ROOT, "start_comfyui.bat")],
                     cwd=ROOT, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    t0 = time.time()
    while time.time() - t0 < wait:
        time.sleep(5)
        if comfy_up():
            print(f"  ComfyUI is back after {time.time() - t0:.0f} s")
            return
    raise RuntimeError("ComfyUI did not come back within %d s" % wait)


def _ffmpeg(args, capture="stderr"):
    p = subprocess.run([FFMPEG, "-hide_banner", "-nostdin"] + args, capture_output=True)
    return p.stderr.decode(errors="replace") if capture == "stderr" else p.stdout


def _probe(path):
    txt = _ffmpeg(["-i", path])
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", txt)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    return {"duration": dur, "video": "Video:" in txt, "audio": "Audio:" in txt}


def _mean_volume(path):
    txt = _ffmpeg(["-i", path, "-vn", "-af", "volumedetect", "-f", "null", "-"])
    m = re.search(r"mean_volume: (-?[\d.]+) dB", txt)
    return float(m.group(1)) if m else -91.0


def _lip_sync_score(path, fps=25):
    """Return (best correlation, lag in frames) between speech loudness and picture motion, or None."""
    try:
        import numpy as np
    except Exception:
        return None
    W, H = 48, 84
    raw = _ffmpeg(["-i", path, "-vf", f"fps={fps},scale={W}:{H},format=gray", "-f", "rawvideo", "-"], "stdout")
    n = len(raw) // (W * H)
    if n < 20:
        return None
    vid = np.frombuffer(raw[: n * W * H], np.uint8).reshape(n, H, W).astype(np.float32)
    face = vid[:, 8:50, 10:38]  # upper-centre: face of a close-up / medium shot
    motion = np.abs(np.diff(face, axis=0)).mean(axis=(1, 2))
    aud = np.frombuffer(_ffmpeg(["-i", path, "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], "stdout"),
                        np.int16).astype(np.float32)
    spf = 8000 // fps
    k = min(len(aud) // spf, len(motion) + 1)
    if k < 20:
        return None
    env = np.sqrt((aud[: k * spf].reshape(k, spf) ** 2).mean(axis=1))[1:]
    motion = motion[: len(env)]
    env = env[: len(motion)]
    if env.std() < 1e-3 or motion.std() < 1e-3:
        return None
    best = (-1.0, 0)
    for lag in range(-6, 7):  # positive lag = picture moves after the sound
        a, b = (env[: len(env) - lag], motion[lag:]) if lag >= 0 else (env[-lag:], motion[: len(motion) + lag])
        if len(a) > 10 and a.std() > 0 and b.std() > 0:
            c = float(np.corrcoef(a, b)[0, 1])
            if c > best[0]:
                best = (c, lag)
    return best


def check(path, speech_seconds=0.0, seconds=5.0, lipsync_ok=True):
    problems, warnings, info = [], [], {}
    if not os.path.isfile(path) or os.path.getsize(path) < 50_000:
        return ["final video is missing or almost empty"], [], info
    p = _probe(path)
    info.update(p)
    if not p["video"]:
        problems.append("no video stream")
    if speech_seconds:
        if not p["audio"]:
            problems.append("speech expected but there is no audio track")
        else:
            vol = _mean_volume(path)
            info["mean_volume_db"] = vol
            if vol < -45:
                problems.append(f"audio is almost silent ({vol:.0f} dB)")
        if p["duration"] < speech_seconds - 0.3:
            problems.append(f"video ({p['duration']:.1f}s) is shorter than the speech ({speech_seconds:.1f}s): speech cut off")
        if not lipsync_ok:
            problems.append("lip sync step failed (voice was added without mouth sync)")
    elif p["duration"] < 0.7 * seconds:
        problems.append(f"video is only {p['duration']:.1f}s, expected about {seconds:.0f}s")
    # black / frozen picture
    txt = _ffmpeg(["-i", path, "-an", "-vf", "blackdetect=d=0.5:pix_th=0.10,freezedetect=n=-60dB:d=1.0",
                   "-f", "null", "-"])
    black = sum(float(x) for x in re.findall(r"black_duration:([\d.]+)", txt))
    frozen = sum(float(x) for x in re.findall(r"freeze_duration: ([\d.]+)", txt))
    info["black_s"], info["frozen_s"] = black, frozen
    if p["duration"] and black > 0.5 * p["duration"]:
        problems.append(f"picture is black for {black:.1f}s")
    if p["duration"] and frozen > 0.5 * p["duration"]:
        problems.append(f"picture is frozen for {frozen:.1f}s")
    # lip sync heuristic (warning only)
    if speech_seconds and p["audio"] and not problems:
        s = _lip_sync_score(path)
        if s:
            info["lipsync_corr"], info["lipsync_lag_frames"] = round(s[0], 2), s[1]
            if s[0] < 0.10:
                warnings.append(f"mouth motion barely follows the speech (correlation {s[0]:.2f}); "
                                "check the face is large, frontal and visible")
            elif abs(s[1]) > 3:
                warnings.append(f"mouth looks out of sync by about {abs(s[1]) * 40} ms")
    return problems, warnings, info


if __name__ == "__main__":  # python tools\qa.py final.mp4 [speech_seconds]
    pr, wa, inf = check(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 0.0)
    print("info:", inf)
    print("PROBLEMS:", pr or "none")
    print("warnings:", wa or "none")
    sys.exit(1 if pr else 0)
