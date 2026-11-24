"""
Video Studio - a small local web UI around make.py.   Start with studio.bat -> http://127.0.0.1:8190
Each "job" is a folder in jobs/ holding job.txt (the prompts/settings) and its results.
"""
import json, mimetypes, os, re, shutil, subprocess, sys, threading, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS = os.path.join(ROOT, "jobs")
VOICES = os.path.join(ROOT, "voices")
IMAGES = os.path.join(ROOT, "images")
UPSCALE_MODELS = os.path.join(ROOT, "models", "upscale_models")
PY = os.path.join(ROOT, "ComfyUI_windows_portable", "python_embeded", "python.exe")
MAKE = os.path.join(ROOT, "tools", "make.py")
MOTION = os.path.join(ROOT, "tools", "motion.py")
PORT = 8190
COMFY = "http://127.0.0.1:8188"
FFMPEG = os.path.join(ROOT, "tools", "bin", "ffmpeg.exe")
if not os.path.exists(FFMPEG):
    FFMPEG = "ffmpeg"

FIELDS = ["image", "video", "speech", "sound", "voice", "lipsync", "preset", "seed", "seconds", "size",
          "image_model", "video_model", "video_quant", "voice_emotion", "sound_volume"]
DEFAULTS = {"image": "", "video": "", "speech": "", "sound": "auto", "voice": "female", "lipsync": "infinitetalk",
            "preset": "realism", "seed": "1", "seconds": "5", "size": "portrait", "image_model": "uncensored",
            "video_model": "uncensored", "video_quant": "Q3_K_M", "voice_emotion": "0.6", "sound_volume": "-10"}
MODES = {"image": ["--image-only"], "video": [], "audio": ["--reuse-video"], "motion": []}
RESULT_FILES = ["ref.png", "final.mp4", "video_talk.mp4", "video_smooth.mp4", "video_lipsync.mp4", "speech.flac", "sfx.flac",
                "motion.mp4", "motion_720p.mp4", "motion_ref.png", "character.png", "character.jpg", "character.jpeg", "character.webp",
                "drive.mp4", "drive.mov", "drive.webm", "drive.mkv", "drive.avi"]

MOTION_FIELDS = ["prompt", "negative", "width", "height", "frames", "steps", "cfg", "seed",
                 "point_x", "point_y", "relight", "chunked", "start_frame", "chunk_frames"]
MOTION_DEFAULTS = {
    "prompt": "the character moves naturally, same camera, same background, natural lighting",
    "negative": "static, blurry, low quality, deformed hands, deformed face, extra fingers, distorted limbs, "
                "messy background, text, watermark, subtitles",
    "width": "480", "height": "832", "frames": "49", "steps": "6", "cfg": "1", "seed": "1",
    "point_x": "0.5", "point_y": "0.5", "relight": "1",
    "chunked": "0", "start_frame": "0", "chunk_frames": "77",
}

run = {"proc": None, "job": None, "mode": None, "start": 0.0}
lock = threading.Lock()

# live progress + preview frames from ComfyUI's websocket (make.py submits as client "shots")
live = {"value": 0, "max": 0, "preview": None, "ptype": "image/jpeg", "pts": 0}


def watch_comfy():
    import asyncio, struct
    import aiohttp  # ships with ComfyUI's python

    async def loop():
        while True:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.ws_connect("ws://127.0.0.1:8188/ws?clientId=shots", heartbeat=30) as ws:
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                m = json.loads(msg.data)
                                if m.get("type") == "progress":
                                    live.update(value=m["data"]["value"], max=m["data"]["max"])
                                elif m.get("type") == "execution_start":
                                    live.update(value=0, max=0)
                            elif msg.type == aiohttp.WSMsgType.BINARY and len(msg.data) > 8:
                                event = struct.unpack(">I", msg.data[:4])[0]
                                if event == 1:  # PREVIEW_IMAGE: type(4) + image
                                    itype, img = struct.unpack(">I", msg.data[4:8])[0], msg.data[8:]
                                    live.update(preview=img, ptype="image/png" if itype == 2 else "image/jpeg", pts=time.time())
                                elif event == 4:  # PREVIEW_IMAGE_WITH_METADATA: len(4) + json + image
                                    n = struct.unpack(">I", msg.data[4:8])[0]
                                    meta = json.loads(msg.data[8:8 + n])
                                    live.update(preview=msg.data[8 + n:], ptype=meta.get("image_type", "image/jpeg"), pts=time.time())
            except Exception:
                pass
            await asyncio.sleep(3)

    asyncio.run(loop())


def safe_name(name):
    name = re.sub(r"[^A-Za-z0-9_\-]+", "_", (name or "").strip())[:60].strip("_")
    return name or "untitled"


def read_job(name):
    data = dict(DEFAULTS)
    path = os.path.join(JOBS, name, "job.txt")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8-sig"):
            line = line.strip()
            if line and not line.startswith("#") and ":" in line:
                k, v = line.split(":", 1)
                if k.strip().lower() in FIELDS:
                    data[k.strip().lower()] = v.strip()
    return data


def write_job(name, fields):
    os.makedirs(os.path.join(JOBS, name), exist_ok=True)
    lines = ["# written by Video Studio - you can also edit this file by hand"]
    for k in FIELDS:
        v = " ".join(str(fields.get(k, DEFAULTS[k])).split())  # one line per key
        lines.append(f"{k}: {v}")
    open(os.path.join(JOBS, name, "job.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")


def read_motion(name):
    data = dict(MOTION_DEFAULTS)
    path = os.path.join(JOBS, name, "motion.json")
    if os.path.exists(path):
        try:
            for k, v in json.load(open(path, encoding="utf-8-sig")).items():
                if k in MOTION_FIELDS:
                    data[k] = v
        except Exception:
            pass
    return {k: str(v) for k, v in data.items()}


def write_motion(name, fields):
    os.makedirs(os.path.join(JOBS, name), exist_ok=True)
    data = {k: (float(fields.get(k, MOTION_DEFAULTS[k])) if k in ("cfg", "point_x", "point_y")
                else int(fields.get(k, MOTION_DEFAULTS[k])) if k in ("width", "height", "frames", "steps", "seed", "relight", "chunked", "start_frame", "chunk_frames")
                else str(fields.get(k, MOTION_DEFAULTS[k])))
            for k in MOTION_FIELDS}
    json.dump(data, open(os.path.join(JOBS, name, "motion.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def motion_inputs(name):
    d = os.path.join(JOBS, name)
    if not os.path.isdir(d):
        return {}, {}
    imgs = {f for f in os.listdir(d) if os.path.splitext(f)[0] == "character"}
    vids = {f for f in os.listdir(d) if os.path.splitext(f)[0] == "drive"}
    return imgs, vids


def input_file(name, kind):
    """A user-supplied picture.* / video.* in the job folder, else None."""
    d = os.path.join(JOBS, name)
    if not os.path.isdir(d):
        return None
    return next((f for f in sorted(os.listdir(d)) if os.path.splitext(f)[0] == kind), None)


def upscale_picture(name, src):
    """Upscale the chosen picture with ComfyUI's ESRGAN model (keeps the original as picture_orig.*)."""
    model = next((f for f in sorted(os.listdir(UPSCALE_MODELS))
                  if f.lower().endswith((".pth", ".safetensors"))), None) if os.path.isdir(UPSCALE_MODELS) else None
    if not model:
        raise RuntimeError("no upscale model in models/upscale_models (e.g. 4x-UltraSharp.pth)")
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from shots import G, upload, run_graph, out_file, free
    g = G()
    img = g.add("LoadImage", image=upload(os.path.join(JOBS, name, src)))
    up = g.add("UpscaleModelLoader", model_name=model)
    scaled = g.add("ImageUpscaleWithModel", upscale_model=[up, 0], image=[img, 0])
    out = g.add("SaveImage", images=[scaled, 0], filename_prefix=f"{name}/upscale")
    d = os.path.join(JOBS, name)
    if not any(os.path.splitext(f)[0] == "picture_orig" for f in os.listdir(d)):
        shutil.copy2(os.path.join(d, src), os.path.join(d, "picture_orig" + os.path.splitext(src)[1]))
    free()
    f = out_file(run_graph(g.nodes, "upscale"), out)
    dest = os.path.join(d, "picture.png")
    shutil.copy2(f, dest)
    if src != "picture.png":
        os.remove(os.path.join(d, src))
    os.makedirs(IMAGES, exist_ok=True)
    saved = os.path.join(IMAGES, name + "_upscaled.png")
    if os.path.exists(saved):
        os.remove(saved)
    try:
        os.link(dest, saved)  # one file on disk, visible in both images\ and the job folder
    except OSError:
        shutil.copy2(dest, saved)
    return os.path.getsize(f)


def is_running():
    return run["proc"] is not None and run["proc"].poll() is None


def log_tail(name, n=40):
    path = os.path.join(JOBS, name, "studio_log.txt")
    if not os.path.exists(path):
        return ""
    text = open(path, encoding="utf-8", errors="replace").read()
    out = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        parts = [p for p in raw.split("\r") if p.strip()]
        if parts:
            out.append(parts[-1].rstrip())
    return "\n".join(out[-n:])


def comfy_up():
    try:
        urllib.request.urlopen(COMFY + "/system_stats", timeout=2)
        return True
    except Exception:
        return False


OUTPUT_NAMES = ("motion_720p.mp4", "motion.mp4", "final.mp4", "video_lipsync.mp4", "video_talk.mp4",
                "video_smooth.mp4", "ref.png", "character.jpg", "character.png")


def output_files(name):
    d = os.path.join(JOBS, name)
    return [f for f in OUTPUT_NAMES if os.path.exists(os.path.join(d, f))]


def job_kind(name):
    return "motion" if os.path.exists(os.path.join(JOBS, name, "motion.json")) else "video"


def done_minutes(name):
    m = re.findall(r"DONE in ([\d.]+) min", log_tail(name, 600))
    return round(float(m[-1]), 1) if m else None


def progress_fraction(name, log, live_p):
    """0..1 estimate across the whole job, not just the current ComfyUI node."""
    total = 1
    m = re.findall(r"\[chunk \d+/(\d+)\]", log)
    if m:
        total = max(1, int(m[-1]))
    cur = (live_p["value"] / live_p["max"]) if live_p.get("max") else 0.0
    if total > 1:
        done = len(re.findall(r"chunk \d+: saved in", log))
        return min(0.999, (done + cur) / total)
    stages = [int(x) for x in re.findall(r"\[(\d)/5\]", log)]
    stage = max(stages) if stages else 1
    return min(0.999, (stage - 1 + cur) / 5)


def job_info(name):
    d = os.path.join(JOBS, name)
    files = {f: int(os.path.getmtime(os.path.join(d, f))) for f in RESULT_FILES if os.path.exists(os.path.join(d, f))}
    for kind in ("picture", "video"):
        f = input_file(name, kind)
        if f:
            files[f] = int(os.path.getmtime(os.path.join(d, f)))
    running = is_running() and run["job"] == name
    log = log_tail(name)
    last = log.splitlines()[-1] if log else ""
    order = [q for q in queue if q[1] == "image"] + [q for q in queue if q[1] != "image"]  # run order
    waiting = [i for i, q in enumerate(order) if q[0] == name]
    if running:
        status = "running"
    elif waiting:
        status = "queued"
        log = f"Waiting for the GPU - number {waiting[0] + 1} in line (now running: {run['job']})"
    elif "DONE in" in last:
        status = "done"
    elif log:
        status = "error"  # finished without the DONE line (crash or stopped)
    else:
        # finished outside the queue (e.g. run from the command line): a final video means done
        status = "done" if ("final.mp4" in files or "motion.mp4" in files) else "idle"
    stage = next((l.strip() for l in reversed(log.splitlines()) if re.match(r"\s*\[\d/5\]|final mix|\s*\[chunk \d+/", l)), "")
    outputs = output_files(name)
    elapsed = round(time.time() - run["start"]) if running else 0
    frac = progress_fraction(name, log, live) if running else 0.0
    eta = round(elapsed * (1 - frac) / frac) if running and frac > 0.02 else None
    finished = int(max(os.path.getmtime(os.path.join(d, f)) for f in outputs)) if outputs else None
    fields = read_motion(name) if os.path.exists(os.path.join(d, "motion.json")) else read_job(name)
    return {"name": name, "fields": fields, "files": files, "status": status,
            "kind": job_kind(name), "outputs": outputs, "finished": finished,
            "picture_file": input_file(name, "picture"), "video_file": input_file(name, "video"),
            "duration_min": done_minutes(name), "percent": round(frac * 100, 1), "eta": eta,
            "queue_pos": waiting[0] + 1 if waiting else None,
            "mode": run["mode"] if running else None,
            "elapsed": elapsed, "log": log, "stage": stage,
            "progress": {"value": live["value"], "max": live["max"]} if running else None,
            "preview_ts": live["pts"] if running and live["pts"] > run["start"] else 0}


queue = []  # [(job, mode)] waiting for the GPU; one job runs at a time


def enqueue(name, mode):
    """Run now if the GPU is free, otherwise wait in line (picked up by queue_worker)."""
    with lock:
        if not comfy_up():
            return "ComfyUI is not running - start it with start_comfyui.bat (or studio.bat)"
        if (run["job"] == name and is_running()) or any(q[0] == name for q in queue):
            return f"'{name}' is already running or waiting"
        queue.append((name, mode))
    return None


def queue_worker():
    while True:
        time.sleep(1.5)
        with lock:
            if queue and not is_running():
                # pictures (~1 min) jump ahead of waiting videos so you are never stuck behind a long render
                i = next((k for k, q in enumerate(queue) if q[1] == "image"), 0)
                name, mode = queue.pop(i)
                launch(name, mode)


def launch(name, mode):
    log = open(os.path.join(JOBS, name, "studio_log.txt"), "w", encoding="utf-8")
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    script, extra = (MOTION, []) if mode == "motion" else (MAKE, MODES[mode])
    run.update(proc=subprocess.Popen([PY, "-s", "-u", script, os.path.join(JOBS, name)] + extra,
                                     stdout=log, stderr=subprocess.STDOUT, env=env, cwd=ROOT,
                                     creationflags=subprocess.CREATE_NO_WINDOW),
               job=name, mode=mode, start=time.time())


def stop(name):
    """Stop a job: drop it from the queue, or kill it if it is the one running."""
    with lock:
        queue[:] = [q for q in queue if q[0] != name]
    if is_running() and run["job"] == name:
        run["proc"].kill()
        try:
            urllib.request.urlopen(urllib.request.Request(COMFY + "/interrupt", data=b"", method="POST"), timeout=3)
            urllib.request.urlopen(urllib.request.Request(COMFY + "/queue", data=b'{"clear": true}',
                                                          headers={"Content-Type": "application/json"}), timeout=3)
        except Exception:
            pass


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        if not isinstance(body, bytes):
            body = (json.dumps(body) if ctype == "application/json" else body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def body_json(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if u.path == "/":
            return self.send(200, open(os.path.join(ROOT, "tools", "studio.html"), "rb").read(), "text/html; charset=utf-8")
        if u.path == "/motion":
            return self.send(200, open(os.path.join(ROOT, "tools", "motion.html"), "rb").read(), "text/html; charset=utf-8")
        if u.path in ("/jobs", "/history", "/dashboard"):
            return self.send(200, open(os.path.join(ROOT, "tools", "library.html"), "rb").read(), "text/html; charset=utf-8")
        if u.path == "/graph":
            return self.send(200, open(os.path.join(ROOT, "tools", "graph.html"), "rb").read(), "text/html; charset=utf-8")
        if u.path == "/api/graph":
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location("graphify", os.path.join(ROOT, "tools", "graphify.py"))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return self.send(200, mod.build_dict())
            except Exception as e:
                return self.send(500, {"error": str(e)})
        if u.path == "/api/library":
            names = sorted((x for x in os.listdir(JOBS) if os.path.isdir(os.path.join(JOBS, x)) and not x.startswith("_")),
                           key=lambda x: -os.path.getmtime(os.path.join(JOBS, x)))
            active, history, idle = [], [], []
            for n in names:
                info = job_info(n)
                info.pop("log", None)
                info.pop("fields", None)
                if info["status"] in ("running", "queued"):
                    active.append(info)
                elif info["status"] in ("done", "error"):
                    history.append(info)
                else:
                    idle.append(n)
            active.sort(key=lambda i: 0 if i["status"] == "running" else 1)
            history.sort(key=lambda i: -(i["finished"] or 0))
            import collections, datetime
            days = collections.OrderedDict()
            today = datetime.date.today()
            for i in range(6, -1, -1):
                days[(today - datetime.timedelta(days=i)).isoformat()] = 0
            for h in history:
                if h.get("finished"):
                    k = datetime.date.fromtimestamp(h["finished"]).isoformat()
                    if k in days:
                        days[k] += 1
            du = 0
            for root, _, fs in os.walk(JOBS):
                for f in fs:
                    try:
                        du += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
            week = int(time.time()) - 7 * 86400
            return self.send(200, {
                "comfy": comfy_up(), "running": run["job"] if is_running() else None,
                "active": active, "history": history, "idle": idle,
                "stats": {"renders": len(history),
                          "videos": sum(1 for h in history if any(f.endswith(".mp4") for f in h.get("outputs", []))),
                          "minutes": round(sum(h.get("duration_min") or 0 for h in history), 1),
                          "week": sum(1 for h in history if (h.get("finished") or 0) >= week),
                          "errors": sum(1 for h in history if h["status"] == "error"),
                          "disk_mb": round(du / 2**20, 1)},
                "days": days})
        if u.path == "/api/thumb":
            name = safe_name(q.get("name"))
            d = os.path.join(JOBS, name)
            srcs = [os.path.join(d, f) for f in ("motion_720p.mp4", "motion.mp4", "final.mp4", "video_lipsync.mp4",
                                                 "video_talk.mp4", "video_smooth.mp4") if os.path.exists(os.path.join(d, f))]
            if not srcs:
                img = next((os.path.join(d, f) for f in ("character.jpg", "character.png", "ref.png")
                            if os.path.exists(os.path.join(d, f))), None)
                return self.send_file(img) if img else self.send(404, {"error": "no thumb"})
            cached = os.path.join(d, "thumb.jpg")
            src = srcs[0]
            try:
                if not os.path.exists(cached) or os.path.getmtime(cached) < os.path.getmtime(src):
                    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", "1", "-i", src, "-frames:v", "1",
                                    "-vf", "scale=480:-2", "-q:v", "3", cached], timeout=40)
            except Exception:
                pass
            return self.send_file(cached) if os.path.exists(cached) else self.send(404, {"error": "thumb failed"})
        if u.path == "/api/motion/job":
            name = safe_name(q.get("name"))
            info = job_info(name)
            imgs, vids = motion_inputs(name)
            info["character"] = sorted(imgs)[0] if imgs else None
            info["drive"] = sorted(vids)[0] if vids else None
            info["fields"] = read_motion(name)
            info["mode"] = "motion" if info["status"] == "running" and run["mode"] == "motion" else info["mode"]
            return self.send(200, info)
        if u.path == "/api/jobs":
            names = sorted((d for d in os.listdir(JOBS) if os.path.isdir(os.path.join(JOBS, d)) and not d.startswith("_")),
                           key=lambda d: -os.path.getmtime(os.path.join(JOBS, d)))
            return self.send(200, {"jobs": names, "running": run["job"] if is_running() else None, "comfy": comfy_up(),
                                   "queue": [f"{q[0]} ({q[1]})" for q in queue]})
        if u.path == "/api/job":
            return self.send(200, job_info(safe_name(q.get("name"))))
        if u.path == "/api/preview":
            if not live["preview"]:
                return self.send(404, {"error": "no preview"})
            return self.send(200, live["preview"], live["ptype"])
        if u.path == "/api/voices":
            vs = sorted(os.path.splitext(f)[0] for f in os.listdir(VOICES) if f.lower().endswith((".wav", ".mp3", ".flac")))
            return self.send(200, {"voices": ["male"] + vs})
        if u.path.startswith("/files/"):
            _, _, job, fname = u.path.split("/", 3)
            path = os.path.join(JOBS, safe_name(urllib.parse.unquote(job)), os.path.basename(urllib.parse.unquote(fname)))
            if not os.path.isfile(path):
                return self.send(404, {"error": "not found"})
            return self.send_file(path)
        self.send(404, {"error": "not found"})

    def send_file(self, path):
        size = os.path.getsize(path)
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        rng = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        start, end = 0, size - 1
        if rng and (rng.group(1) or rng.group(2)):
            start = int(rng.group(1) or 0)
            end = int(rng.group(2)) if rng.group(2) else size - 1
        with open(path, "rb") as f:
            f.seek(start)
            data = f.read(end - start + 1)
        self.send_response(206 if rng else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(data)))
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/run":
            d = self.body_json()
            name, mode = safe_name(d.get("name")), d.get("mode")
            if mode not in MODES:
                return self.send(400, {"error": "bad mode"})
            fields = {k: d.get("fields", {}).get(k, DEFAULTS[k]) for k in FIELDS}
            if not fields["image"].strip() and not input_file(name, "picture"):
                return self.send(400, {"error": "Write an image prompt first (or choose your own picture)."})
            if mode != "image" and not fields["video"].strip() and not input_file(name, "video"):
                return self.send(400, {"error": "Write a video prompt first (or choose your own video)."})
            if mode == "audio" and not any(os.path.exists(os.path.join(JOBS, name, f)) for f in ("video_talk.mp4", "video_smooth.mp4")):
                return self.send(400, {"error": "There is no video yet - use 'Make video' first."})
            write_job(name, fields)
            err = enqueue(name, mode)
            return self.send(409 if err else 200, {"error": err} if err else {"ok": True, "name": name})
        if u.path == "/api/new":  # create the job folder + job.txt right away (visible in VS Code)
            name = safe_name(self.body_json().get("name"))
            if not os.path.exists(os.path.join(JOBS, name, "job.txt")):
                write_job(name, {})
            return self.send(200, {"ok": True, "name": name, "path": os.path.join(JOBS, name)})
        if u.path == "/api/motion/run":
            d = self.body_json()
            name = safe_name(d.get("name"))
            os.makedirs(os.path.join(JOBS, name), exist_ok=True)
            imgs, vids = motion_inputs(name)
            if not imgs:
                return self.send(400, {"error": "Upload a character image first."})
            if not vids:
                return self.send(400, {"error": "Upload a driving video first."})
            write_motion(name, d.get("fields", {}))
            err = enqueue(name, "motion")
            return self.send(409 if err else 200, {"error": err} if err else {"ok": True, "name": name})
        if u.path == "/api/motion/upload":
            name = safe_name(urllib.parse.unquote(self.headers.get("X-Job", "")))
            kind = self.headers.get("X-Kind", "")
            if kind not in ("character", "drive"):
                return self.send(400, {"error": "bad kind"})
            fname = os.path.basename(urllib.parse.unquote(self.headers.get("X-Filename", "")))
            ext = os.path.splitext(fname)[1].lower()
            allowed = (".png", ".jpg", ".jpeg", ".webp") if kind == "character" else (".mp4", ".mov", ".webm", ".mkv", ".avi")
            if ext not in allowed:
                return self.send(400, {"error": "unsupported file type: " + (ext or "none")})
            n = int(self.headers.get("Content-Length", 0))
            if n > (300 if kind == "drive" else 30) * 2**20:
                return self.send(400, {"error": "file too large"})
            d = os.path.join(JOBS, name)
            os.makedirs(d, exist_ok=True)
            for f in os.listdir(d):
                if os.path.splitext(f)[0] == kind:
                    os.remove(os.path.join(d, f))
            open(os.path.join(d, kind + ext), "wb").write(self.rfile.read(n))
            return self.send(200, {"ok": True, "file": kind + ext})
        if u.path == "/api/upload_input":  # your own picture / video for steps 1-2
            name = safe_name(urllib.parse.unquote(self.headers.get("X-Job", "")))
            kind = self.headers.get("X-Kind", "")
            if kind not in ("picture", "video"):
                return self.send(400, {"error": "bad kind"})
            fname = os.path.basename(urllib.parse.unquote(self.headers.get("X-Filename", "")))
            ext = os.path.splitext(fname)[1].lower()
            allowed = (".png", ".jpg", ".jpeg", ".webp") if kind == "picture" else (".mp4", ".mov", ".webm", ".mkv", ".avi")
            if ext not in allowed:
                return self.send(400, {"error": "unsupported file type: " + (ext or "none")})
            n = int(self.headers.get("Content-Length", 0))
            if n > (300 if kind == "video" else 30) * 2**20:
                return self.send(400, {"error": "file too large"})
            d = os.path.join(JOBS, name)
            os.makedirs(d, exist_ok=True)
            for f in os.listdir(d):
                if os.path.splitext(f)[0] in (kind, kind + "_orig"):
                    os.remove(os.path.join(d, f))
            open(os.path.join(d, kind + ext), "wb").write(self.rfile.read(n))
            return self.send(200, {"ok": True, "file": kind + ext})
        if u.path == "/api/upscale":
            name = safe_name(self.body_json().get("name"))
            if not input_file(name, "picture"):
                return self.send(400, {"error": "Choose a picture first."})
            if is_running() or queue:
                return self.send(409, {"error": "GPU busy - wait for the current job to finish."})
            if not comfy_up():
                return self.send(409, {"error": "ComfyUI is not running - start it with start_comfyui.bat"})
            try:
                size = upscale_picture(name, input_file(name, "picture"))
            except Exception as e:
                return self.send(500, {"error": str(e).splitlines()[0][:300]})
            return self.send(200, {"ok": True, "file": "picture.png", "bytes": size})
        if u.path == "/api/clear_input":
            d = self.body_json()
            name, kind = safe_name(d.get("name")), d.get("kind")
            if kind not in ("picture", "video"):
                return self.send(400, {"error": "bad kind"})
            jd = os.path.join(JOBS, name)
            for f in (input_file(name, kind), input_file(name, kind + "_orig")):
                if f:
                    os.remove(os.path.join(jd, f))
            return self.send(200, {"ok": True})
        if u.path == "/api/stop":
            stop(safe_name(self.body_json().get("name")))
            return self.send(200, {"ok": True})
        if u.path == "/api/upload_voice":
            fname = os.path.basename(urllib.parse.unquote(self.headers.get("X-Filename", "voice.wav")))
            base, ext = os.path.splitext(fname)
            if ext.lower() not in (".wav", ".mp3", ".flac"):
                return self.send(400, {"error": "use a .wav, .mp3 or .flac file"})
            n = int(self.headers.get("Content-Length", 0))
            if n > 30 * 2**20:
                return self.send(400, {"error": "file too large (max 30 MB)"})
            name = safe_name(base)
            open(os.path.join(VOICES, name + ext.lower()), "wb").write(self.rfile.read(n))
            return self.send(200, {"ok": True, "voice": name})
        self.send(404, {"error": "not found"})


if __name__ == "__main__":
    os.makedirs(JOBS, exist_ok=True)
    os.makedirs(VOICES, exist_ok=True)
    os.makedirs(IMAGES, exist_ok=True)
    threading.Thread(target=watch_comfy, daemon=True).start()
    threading.Thread(target=queue_worker, daemon=True).start()
    print(f"Video Studio running at http://127.0.0.1:{PORT}  (keep this window open, close it to stop)")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
