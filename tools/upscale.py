r"""
720p second pass: upscale a finished clip with a high quality lanczos resample + light sharpen.

Usage:  python -s -u tools\upscale.py jobs\<name>
Reads jobs\<name>\motion.mp4 and writes jobs\<name>\motion_720p.mp4 (audio kept).
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import motion


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: upscale.py <job folder>")
    job_dir = os.path.abspath(sys.argv[1])
    cfg = motion.read_config(job_dir)
    src = os.path.join(job_dir, "motion.mp4")
    if not os.path.exists(src):
        raise SystemExit("No motion.mp4 in " + job_dir)

    w, h = int(cfg["width"]), int(cfg["height"])
    factor = 720 / min(w, h)
    tw = int(round(w * factor / 2)) * 2
    th = int(round(h * factor / 2)) * 2
    dst = os.path.join(job_dir, "motion_720p.mp4")

    args = ["-i", src, "-vf", f"scale={tw}:{th}:flags=lanczos,unsharp=5:5:0.5:5:5:0.0",
            "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p"]
    if motion.has_audio(src):
        args += ["-c:a", "copy"]
    motion.ffmpeg(args + [dst])
    print(f"Saved {dst} ({tw}x{th})")


if __name__ == "__main__":
    main()
