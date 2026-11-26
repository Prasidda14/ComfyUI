r"""
Generate character views with Z-Image Turbo from a project's character.json.

Z-Image follows identity and outfit well at cfg 1, but ignores side/back camera prompts.
Use tools\turntable.py (Wan 2.2 I2V) for a real turnaround, then tools\sheet_contact.py.

Usage:
  python -s -u tools\sheet.py projects\motion_asian_baddie
  python -s -u tools\sheet.py projects\motion_asian_baddie --views front,face --seed 501
  python -s -u tools\sheet.py projects\motion_asian_baddie --views three_quarter --seed 201 --overwrite

Reads  <project>\assets\character\character.json
Writes <project>\assets\character\sheet_<view>.png (+ _recipe.json)
       <project>\assets\character\sheet_contact.jpg when enough views exist.
"""
import argparse
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from image import zimage_graph  # noqa: E402
from shots import run_graph, out_file  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTACT_ORDER = ("front", "three_quarter", "side", "back")


def clean_prompt(parts):
    text = ". ".join(p.strip().strip(".") for p in parts if p and p.strip())
    while ".." in text:
        text = text.replace("..", ".")
    return text


def make_contact(char_dir, names):
    files = [os.path.join(char_dir, "sheet_%s.png" % n) for n in CONTACT_ORDER]
    files = [f for f in files if os.path.isfile(f)]
    if len(files) < 2:
        return None
    try:
        from PIL import Image
    except Exception as e:
        print("  contact sheet skipped (PIL unavailable):", e)
        return None
    imgs = [Image.open(f).convert("RGB") for f in files]
    w, h = imgs[0].size
    cols = 2
    rows = (len(imgs) + cols - 1) // cols
    pad = 12
    canvas = Image.new("RGB", (w * cols + pad * (cols + 1), h * rows + pad * (rows + 1)), (235, 235, 235))
    for i, im in enumerate(imgs):
        if im.size != (w, h):
            im = im.resize((w, h))
        x = pad + (i % cols) * (w + pad)
        y = pad + (i // cols) * (h + pad)
        canvas.paste(im, (x, y))
    dst = os.path.join(char_dir, "sheet_contact.jpg")
    canvas.save(dst, quality=90)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--views", default="", help="comma list, default: all views in character.json")
    ap.add_argument("--seed", type=int, default=100)
    ap.add_argument("--steps", type=int, default=9)
    ap.add_argument("--width", type=int, default=768)
    ap.add_argument("--height", type=int, default=1344)
    ap.add_argument("--model", default="base", choices=["base", "uncensored"])
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--no-contact", action="store_true")
    a = ap.parse_args()

    proj = os.path.abspath(a.project)
    if not os.path.isdir(proj):
        raise SystemExit("Project not found: " + proj)
    char_dir = os.path.join(proj, "assets", "character")
    spec_path = os.path.join(char_dir, "character.json")
    if not os.path.isfile(spec_path):
        raise SystemExit("Missing " + spec_path)
    spec = json.load(open(spec_path, encoding="utf-8-sig"))
    views = [v.strip() for v in a.views.split(",") if v.strip()] or list(spec["views"])

    print("project:", proj)
    print("model:", a.model, "| size:", a.width, "x", a.height, "| steps:", a.steps)
    print("views:", ", ".join(views))

    for i, view in enumerate(views):
        if view not in spec["views"]:
            raise SystemExit("Unknown view '%s'. Available: %s" % (view, ", ".join(spec["views"])))
        dst = os.path.join(char_dir, "sheet_%s.png" % view)
        if os.path.isfile(dst) and not a.overwrite:
            print("  skip existing", dst, "(use --overwrite)")
            continue
        seed = a.seed + i * 17
        prompt = clean_prompt([spec.get("identity"), spec.get("outfit"), spec["views"][view], spec.get("style")])
        graph, out = zimage_graph(prompt, seed, a.width, a.height, a.steps,
                                  "motion_asian_baddie/sheet_%s" % view, a.model)
        t0 = time.time()
        f = out_file(run_graph(graph, "sheet_%s_s%d" % (view, seed)), out)
        shutil.copy2(f, dst)
        json.dump({
            "model": a.model, "view": view, "prompt": prompt, "seed": seed,
            "width": a.width, "height": a.height, "steps": a.steps,
            "graph": graph,
        }, open(os.path.join(char_dir, "sheet_%s_recipe.json" % view), "w", encoding="utf-8"),
            indent=1, ensure_ascii=False)
        print("  saved %s  (%.1f min)" % (dst, (time.time() - t0) / 60))

    if not a.no_contact:
        contact = make_contact(char_dir, views)
        if contact:
            print("contact sheet:", contact)


if __name__ == "__main__":
    main()
