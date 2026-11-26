r"""
Preview where the SAM2 click lands at the first frame of every chunk, before a long render.

Usage:  python -s -u tools\pointcheck.py jobs\<name>
Writes jobs\<name>\pointcheck_000.png, pointcheck_001.png, ... with the click marked.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import motion


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: pointcheck.py <job folder>")
    job_dir = os.path.abspath(sys.argv[1])
    cfg = motion.read_config(job_dir)

    norm = os.path.join(job_dir, "drive_norm.mp4")
    if not os.path.exists(norm):
        src = motion.find_video(job_dir, "drive")
        if not src:
            raise SystemExit("No driving video in " + job_dir)
        print("Normalizing drive to 16 fps ...", flush=True)
        motion.normalize_drive(src, norm)

    total, start_frame, chunk_len, stride, overlap, starts = motion.plan_chunks(cfg)
    w, h = int(cfg["width"]), int(cfg["height"])
    pts = cfg.get("points") or [[cfg["point_x"], cfg["point_y"]]]
    pts = [(round(max(0.01, min(0.99, float(p[0]))) * w),
            round(max(0.01, min(0.99, float(p[1]))) * h)) for p in pts]
    total_src = motion.probe_frames(norm)

    for i, pos in enumerate(starts):
        frame = min(pos, max(0, total_src - 1))
        out = os.path.join(job_dir, f"pointcheck_{i:03d}.png")
        boxes = []
        for px, py in pts:
            boxes.append(f"drawbox=x={max(0, px - 12)}:y={max(0, py - 12)}:w=24:h=24:color=red@0.9:t=2")
            boxes.append(f"drawbox=x={max(0, px - 3)}:y={max(0, py - 3)}:w=6:h=6:color=lime@1.0:t=1")
        vf = f"select=eq(n\\,{frame}),scale={w}:{h}," + ",".join(boxes)
        motion.ffmpeg(["-i", norm, "-vf", vf, "-frames:v", "1", "-update", "1", out])
        print(f"chunk {i + 1}: source frame {frame} ({frame / motion.FPS:.2f}s) "
              f"points={pts} -> {os.path.basename(out)}")

    print(f"{len(starts)} chunk(s), {total} frames total, overlap {overlap}. "
          f"Red boxes = clicks. Check every box sits on the subject in every image.")


if __name__ == "__main__":
    main()
