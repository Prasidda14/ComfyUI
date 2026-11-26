r"""
Turn a still into a turn-around clip with Wan 2.2 I2V, then export view frames.

Usage:
  python -s -u tools\turntable.py projects\motion_asian_baddie\assets\character\sheet_front.png
  ... --seed 7 --frames 81 --views 0,20,40,60,80,100

The still anchors identity in frame 1. The prompt asks for a slow camera orbit, so later
frames show the side and back. Output: turntable.mp4 and turn_<pct>.png next to the still.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shots import DEFAULT_NEGATIVE, gen_graph, resolve_preset, run_graph, out_file, upload, free  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FFMPEG = os.path.join(ROOT, "tools", "bin", "ffmpeg.exe")

PROMPT = ("the camera slowly orbits around the woman to the right in a smooth steady move, "
          "revealing her side profile and then her back, the woman stands still with her arms "
          "relaxed at her sides, full body in frame, plain light grey studio background, "
          "photorealistic, realistic skin texture, 35mm")


def frame_at(video, n, dst):
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", video,
                    "-vf", "select=eq(n\\,%d)" % n, "-frames:v", "1", dst],
                   check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--outdir", default="")
    ap.add_argument("--frames", type=int, default=81)
    ap.add_argument("--fps", type=int, default=16)
    ap.add_argument("--width", type=int, default=480)
    ap.add_argument("--height", type=int, default=832)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--preset", default="draft", choices=["draft", "realism"])
    ap.add_argument("--prompt", default=PROMPT)
    ap.add_argument("--negative", default=DEFAULT_NEGATIVE)
    ap.add_argument("--views", default="0,20,40,60,80,100")
    ap.add_argument("--no-rife", action="store_true", help="unused, kept for clarity")
    ap.add_argument("--extract-only", action="store_true", help="reuse an existing turntable.mp4")
    a = ap.parse_args()

    image = os.path.abspath(a.image)
    if not os.path.isfile(image):
        raise SystemExit("Image not found: " + image)
    if (a.frames - 1) % 4:
        raise SystemExit("frames must be 1 + 4k, got %d" % a.frames)
    outdir = os.path.abspath(a.outdir) if a.outdir else os.path.dirname(image)
    os.makedirs(outdir, exist_ok=True)

    p = {
        "video_model": "base",
        "width": a.width,
        "height": a.height,
        "frames": a.frames,
        "fps": a.fps,
        "shift": 5.0,
        "loras": [],
        "preset_overrides": {},
    }
    preset = resolve_preset(p, a.preset)

    video_dst = os.path.join(outdir, "turntable.mp4")
    if a.extract_only:
        if not os.path.isfile(video_dst):
            raise SystemExit("No existing turntable.mp4 in " + outdir)
        print("extract only:", video_dst)
    else:
        print("image:", image)
        print("graph: Wan 2.2 I2V base %s, %dx%d, %d frames, %d fps, preset %s"
              % (preset["quant"], a.width, a.height, a.frames, a.fps, a.preset))
        name = upload(image)
        print("uploaded:", name)

        free()
        graph, outs = gen_graph(p, preset, a.prompt, a.negative, name, a.seed, "turntable")
        result = run_graph(graph, "turntable")

        video_src = out_file(result, outs["raw"])
        shutil.copy2(video_src, video_dst)
        print("video:", video_dst)

    stills = []
    for pct in [float(x) for x in a.views.split(",") if x.strip()]:
        n = int(round((a.frames - 1) * pct / 100.0))
        dst = os.path.join(outdir, "turn_%03d.png" % int(pct))
        frame_at(video_dst, n, dst)
        stills.append(dst)
        print("frame %3d%% -> %s" % (int(pct), dst))

    json.dump({"image": image, "prompt": a.prompt, "seed": a.seed, "frames": a.frames,
               "fps": a.fps, "width": a.width, "height": a.height, "preset": a.preset,
               "stills": stills, "video": video_dst},
              open(os.path.join(outdir, "turntable_recipe.json"), "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
