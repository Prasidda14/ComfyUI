r"""
Scaffold a new video idea folder inside a motion project.

Usage:
  python -s -u tools\new_idea.py motion_asian_baddie "Bar mirror selfie"
  python -s -u tools\new_idea.py motion_asian_baddie "Bar mirror selfie" --slug 02_bar_mirror --url https://...

Creates <project>\videos\<NN_slug>\ with README.md, research.md, todo.md, how_to_work.md
and an empty assets\ folder, using videos\_template as the source.
"""
import argparse
import datetime
import os
import re
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def slugify(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")[:40]


def next_prefix(videos_dir):
    nums = []
    for name in os.listdir(videos_dir):
        m = re.match(r"^(\d{2})_", name)
        if m and os.path.isdir(os.path.join(videos_dir, name)):
            nums.append(int(m.group(1)))
    return "%02d" % (max(nums) + 1 if nums else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("title")
    ap.add_argument("--slug", default="", help="folder name, default: NN_<title>")
    ap.add_argument("--url", default="", help="source URL")
    ap.add_argument("--source", default="unknown", help="short source label")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    proj = a.project if os.path.isabs(a.project) else os.path.join(ROOT, "projects", a.project)
    proj = os.path.abspath(proj)
    videos = os.path.join(proj, "videos")
    template = os.path.join(videos, "_template")
    if not os.path.isdir(videos):
        raise SystemExit("Not a motion project (no videos folder): " + proj)
    if not os.path.isdir(template):
        raise SystemExit("Missing template: " + template)

    slug = a.slug.strip() or (next_prefix(videos) + "_" + slugify(a.title))
    slug = slugify(slug) if not re.match(r"^\d", slug) else re.sub(r"[^A-Za-z0-9_]+", "_", slug)
    dst = os.path.join(videos, slug)
    if os.path.exists(dst) and not a.force:
        raise SystemExit("Already exists: " + dst + " (use --force)")
    os.makedirs(os.path.join(dst, "assets"), exist_ok=True)

    values = {
        "{{TITLE}}": a.title,
        "{{SLUG}}": slug,
        "{{DATE}}": datetime.date.today().isoformat(),
        "{{PROJECT}}": os.path.basename(proj),
        "{{URL}}": a.url or "(add source URL)",
        "{{SOURCE}}": a.source,
    }
    for name in ("README.md", "research.md", "todo.md", "how_to_work.md"):
        src = os.path.join(template, name)
        if not os.path.isfile(src):
            print("  template missing, skipped:", name)
            continue
        text = open(src, encoding="utf-8-sig").read()
        for k, v in values.items():
            text = text.replace(k, v)
        open(os.path.join(dst, name), "w", encoding="utf-8").write(text)

    print("created", dst)
    print("next: put drive_original.mp4 and character.png in", os.path.join(dst, "assets"))


if __name__ == "__main__":
    main()
