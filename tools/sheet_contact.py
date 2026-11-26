r"""
Build a contact sheet from sheet_<view>.png files in a character folder.

Usage:
  python -s -u tools\sheet_contact.py projects\motion_asian_baddie\assets\character
  ... --width 480 --height 832 --cols 3

Order: front, three_quarter, side, back, face, source. Missing views are skipped.
Each panel is labelled; source falls back to source.jpg.
"""
import argparse
import os
import sys

ORDER = ("front", "three_quarter", "side", "back", "face", "source")
LABELS = {"front": "front", "three_quarter": "three-quarter", "side": "side",
          "back": "back", "face": "face", "source": "original"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--width", type=int, default=480)
    ap.add_argument("--height", type=int, default=832)
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--out", default="sheet_contact.jpg")
    a = ap.parse_args()

    folder = os.path.abspath(a.folder)
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps
    except Exception as e:
        raise SystemExit("PIL unavailable: %s" % e)

    files = []
    for name in ORDER:
        p = os.path.join(folder, "sheet_%s.png" % name)
        if name == "source" and not os.path.isfile(p):
            p = os.path.join(folder, "source.jpg")
        if os.path.isfile(p):
            files.append((name, p))
        else:
            print("missing, skipped:", p)
    if not files:
        raise SystemExit("No sheet_<view>.png files in " + folder)

    cell = (a.width, a.height)
    cols = max(1, min(a.cols, len(files)))
    rows = (len(files) + cols - 1) // cols
    pad = 12
    canvas = Image.new("RGBA", (cell[0] * cols + pad * (cols + 1),
                                cell[1] * rows + pad * (rows + 1)), (235, 235, 235, 255))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 22)
    except Exception:
        font = ImageFont.load_default()

    for i, (name, f) in enumerate(files):
        im = Image.open(f).convert("RGB")
        im = ImageOps.fit(im, cell, method=Image.LANCZOS, centering=(0.5, 0.5))
        x = pad + (i % cols) * (cell[0] + pad)
        y = pad + (i // cols) * (cell[1] + pad)
        canvas.paste(im, (x, y))
        label = LABELS.get(name, name)
        box = draw.textbbox((0, 0), label, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        draw.rounded_rectangle([x + 8, y + 8, x + 8 + tw + 16, y + 8 + th + 12],
                               radius=6, fill=(0, 0, 0, 145))
        draw.text((x + 16, y + 13), label, font=font, fill=(255, 255, 255, 240))
        print("panel %d: %s (%s)" % (i + 1, os.path.basename(f), label))
    dst = os.path.join(folder, a.out)
    canvas.convert("RGB").save(dst, quality=90)
    print("saved", dst, canvas.size)


if __name__ == "__main__":
    main()
