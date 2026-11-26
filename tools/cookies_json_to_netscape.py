r"""
Convert a browser cookie JSON export into a Netscape cookies.txt for yt-dlp.

Usage:
  python tools\cookies_json_to_netscape.py "%USERPROFILE%\Downloads\www.instagram.com_16-11-2026.json" cookies.txt

Accepts {"cookies": [...]} or a bare list. Prints cookie names and writes the file.
"""
import argparse
import json
import os
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    a = ap.parse_args()

    data = json.load(open(os.path.abspath(a.src), encoding="utf-8-sig"))
    cookies = data.get("cookies", data) if isinstance(data, dict) else data
    if not isinstance(cookies, list):
        raise SystemExit("Unsupported JSON: expected {'cookies': [...]} or a list")

    lines = ["# Netscape HTTP Cookie File",
             "# Generated from %s on %s" % (os.path.basename(a.src), time.strftime("%Y-%m-%d %H:%M:%S")),
             ""]
    names = []
    for c in cookies:
        name = str(c.get("name", ""))
        value = str(c.get("value", "")).replace("\r", "").replace("\n", "").replace("\t", " ")
        domain = str(c.get("domain", ""))
        if not name or not domain:
            continue
        include_sub = "TRUE" if domain.startswith(".") else "FALSE"
        path = str(c.get("path", "/") or "/")
        secure = "TRUE" if c.get("secure") else "FALSE"
        exp = 0 if c.get("session") else int(float(c.get("expirationDate") or 0))
        prefix = "#HttpOnly_" if c.get("httpOnly") else ""
        lines.append("\t".join([prefix + domain, include_sub, path, secure, str(exp), name, value]))
        names.append(name)

    open(os.path.abspath(a.dst), "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    print("wrote", os.path.abspath(a.dst))
    print("cookies:", ", ".join(names))
    for must in ("sessionid", "ds_user_id", "csrftoken"):
        print("%-12s %s" % (must, "present" if must in names else "MISSING"))


if __name__ == "__main__":
    main()
