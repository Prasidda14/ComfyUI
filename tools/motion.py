r"""
Motion control: put a character image into a driving video (Wan 2.2 Animate, Mix / replacement mode).

Usage:  python -s -u tools\motion.py jobs\<name>
Reads jobs\<name>\motion.json, copies the inputs into ComfyUI\input, submits an API workflow,
waits for it, and writes jobs\<name>\motion.mp4 (+ motion_ref.png).

With "chunked": 1 the target length is rendered as several overlapping 77-frame passes. Each pass
re-reads the previous pass's last few frames as continue_motion so the character carries across cuts.
"""
import glob, json, os, shutil, subprocess, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMFY = "http://127.0.0.1:8188"
COMFY_INPUT = os.path.join(ROOT, "ComfyUI_windows_portable", "ComfyUI", "input")
FFMPEG = os.path.join(ROOT, "tools", "bin", "ffmpeg.exe")
FPS = 16

DEFAULTS = {
    "prompt": "the character moves naturally, same camera, same background, natural lighting",
    "negative": "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，"
                 "JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，"
                 "形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走",
    "width": 480, "height": 832, "frames": 49, "steps": 6, "cfg": 1.0, "seed": 1,
    "point_x": 0.5, "point_y": 0.5, "relight": 1,
    "chunked": 0, "start_frame": 0, "chunk_frames": 77,
    "character": "", "drive": "",
}


def log(*a):
    print(*a, flush=True)


def read_config(job_dir):
    path = os.path.join(job_dir, "motion.json")
    cfg = dict(DEFAULTS)
    if os.path.exists(path):
        try:
            cfg.update(json.load(open(path, encoding="utf-8-sig")))
        except Exception as e:
            log("Could not read motion.json:", e)
    return cfg


def post(path, payload):
    req = urllib.request.Request(COMFY + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"ComfyUI rejected the workflow ({e.code}): {e.read().decode('utf-8', 'replace')[:2000]}")


def get(path):
    with urllib.request.urlopen(COMFY + path, timeout=30) as r:
        return json.loads(r.read())


def find_file(folder, stem):
    for d in (folder, os.path.join(folder, "assets")):
        for ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
            p = os.path.join(d, stem + ext)
            if os.path.isfile(p):
                return p
    return None


def find_video(folder, stem):
    for d in (folder, os.path.join(folder, "assets")):
        for ext in (".mp4", ".mov", ".webm", ".mkv", ".avi"):
            p = os.path.join(d, stem + ext)
            if os.path.isfile(p):
                return p
    return None


def find_ffprobe():
    p = shutil.which("ffprobe")
    if p:
        return p
    pat = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet",
                       "Packages", "Gyan.FFmpeg*", "*", "bin", "ffprobe.exe")
    hits = glob.glob(pat)
    return hits[0] if hits else "ffprobe"


def ffmpeg(args):
    r = subprocess.run([FFMPEG, "-y"] + args, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("ffmpeg failed: " + (r.stderr or "")[-1500:])
    return r


def has_audio(path):
    r = subprocess.run([find_ffprobe(), "-v", "error", "-select_streams", "a",
                        "-show_entries", "stream=index", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


def normalize_drive(src, dst):
    ffmpeg(["-i", src, "-an", "-vf", f"fps={FPS}", "-c:v", "libx264", "-crf", "18",
            "-pix_fmt", "yuv420p", dst])


def cut_chunk(norm, dst, start_frame, length):
    end = start_frame + length
    vf = (f"fps={FPS},trim=start_frame={start_frame}:end_frame={end},"
          f"tpad=stop_mode=clone:stop_duration=3,setpts=PTS-STARTPTS")
    ffmpeg(["-i", norm, "-an", "-vf", vf, "-frames:v", str(length),
            "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", dst])


def copy_inputs(job_dir, cfg, drive_path=None):
    """Copy the character image and driving video into ComfyUI's input folder under stable names."""
    os.makedirs(COMFY_INPUT, exist_ok=True)
    tag = os.path.basename(job_dir.rstrip("\\/"))
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tag)

    char = find_file(job_dir, "character")
    if not char:
        raise SystemExit("No character image in " + job_dir + " (upload one on the Motion Control page).")
    char_name = "motion_" + safe + "_character" + os.path.splitext(char)[1].lower()
    shutil.copyfile(char, os.path.join(COMFY_INPUT, char_name))

    drive = drive_path or find_video(job_dir, "drive")
    if not drive:
        raise SystemExit("No driving video in " + job_dir + " (upload one on the Motion Control page).")
    drive_name = "motion_" + safe + "_drive" + os.path.splitext(drive)[1].lower()
    shutil.copyfile(drive, os.path.join(COMFY_INPUT, drive_name))

    return char_name, drive_name, char, safe


def build_workflow(cfg, char_name, drive_name, job_name, seed, continue_video=None,
                   continue_frames=5, with_audio=True):
    w, h = int(cfg["width"]), int(cfg["height"])
    frames = max(5, int(cfg["frames"]))
    frames = (frames - 1) // 4 * 4 + 1
    pts = cfg.get("points") or [[cfg["point_x"], cfg["point_y"]]]
    coords = json.dumps([{"x": round(max(0.01, min(0.99, float(p[0]))) * w),
                          "y": round(max(0.01, min(0.99, float(p[1]))) * h)} for p in pts])
    steps = int(cfg["steps"])
    cfg_scale = float(cfg["cfg"])

    nodes = {
        "unet": {"class_type": "UnetLoaderGGUF",
                 "inputs": {"unet_name": "Wan2.2-Animate-14B-Q3_K_S.gguf"}},
        "lora_speed": {"class_type": "LoraLoaderModelOnly",
                       "inputs": {"model": ["unet", 0],
                                  "lora_name": "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",
                                  "strength_model": 1.0}},
        "sampling": {"class_type": "ModelSamplingSD3",
                     "inputs": {"model": ["lora_speed", 0], "shift": 8.0}},
        "clip": {"class_type": "CLIPLoaderGGUF",
                 "inputs": {"clip_name": "umt5-xxl-encoder-Q5_K_M.gguf", "type": "wan"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
        "clipvision": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": "clip_vision_h.safetensors"}},
        "positive": {"class_type": "CLIPTextEncode",
                     "inputs": {"clip": ["clip", 0], "text": cfg["prompt"]}},
        "negative": {"class_type": "CLIPTextEncode",
                     "inputs": {"clip": ["clip", 0], "text": cfg["negative"]}},
        "reference": {"class_type": "LoadImage", "inputs": {"image": char_name}},
        "cvenc": {"class_type": "CLIPVisionEncode",
                  "inputs": {"clip_vision": ["clipvision", 0], "image": ["reference", 0], "crop": "none"}},
        "drive": {"class_type": "LoadVideo", "inputs": {"file": drive_name}},
        "components": {"class_type": "GetVideoComponents", "inputs": {"video": ["drive", 0]}},
        "frames": {"class_type": "ImageFromBatch",
                   "inputs": {"image": ["components", 0], "batch_index": 0, "length": frames}},
        "scale": {"class_type": "ImageScale",
                  "inputs": {"image": ["frames", 0], "upscale_method": "lanczos",
                             "width": w, "height": h, "crop": "disabled"}},
        "pixel": {"class_type": "PixelPerfectResolution",
                  "inputs": {"original_image": ["frames", 0], "image_gen_width": w,
                             "image_gen_height": h, "resize_mode": "Just Resize"}},
        "face": {"class_type": "DWPreprocessor",
                 "inputs": {"image": ["scale", 0], "detect_hand": "disable", "detect_body": "disable",
                            "detect_face": "enable", "resolution": ["pixel", 0],
                            "bbox_detector": "yolox_l.onnx",
                            "pose_estimator": "dw-ll_ucoco_384_bs5.torchscript.pt",
                            "scale_stick_for_xinsr_cn": "disable"}},
        "pose": {"class_type": "DWPreprocessor",
                 "inputs": {"image": ["scale", 0], "detect_hand": "enable", "detect_body": "enable",
                            "detect_face": "disable", "resolution": ["pixel", 0],
                            "bbox_detector": "yolox_l.onnx",
                            "pose_estimator": "dw-ll_ucoco_384_bs5.torchscript.pt",
                            "scale_stick_for_xinsr_cn": "disable"}},
        "sam2": {"class_type": "DownloadAndLoadSAM2Model",
                 "inputs": {"model": "sam2_hiera_base_plus.safetensors", "segmentor": "video",
                            "device": "cuda", "precision": "fp16"}},
        "coords": {"class_type": "PrimitiveString", "inputs": {"value": coords}},
        "seg": {"class_type": "Sam2Segmentation",
                "inputs": {"sam2_model": ["sam2", 0], "image": ["scale", 0],
                           "coordinates_positive": ["coords", 0],
                           "keep_model_loaded": True, "individual_objects": False}},
        "grow": {"class_type": "GrowMask",
                 "inputs": {"mask": ["seg", 0], "expand": 10, "tapered_corners": True}},
        "block": {"class_type": "BlockifyMask", "inputs": {"masks": ["grow", 0], "block_size": 32}},
        "background": {"class_type": "DrawMaskOnImage",
                       "inputs": {"image": ["scale", 0], "mask": ["block", 0], "color": "0, 0, 0"}},
        "animate": {"class_type": "WanAnimateToVideo",
                    "inputs": {"positive": ["positive", 0], "negative": ["negative", 0],
                               "vae": ["vae", 0], "width": w, "height": h, "length": frames,
                               "batch_size": 1, "clip_vision_output": ["cvenc", 0],
                               "reference_image": ["reference", 0], "face_video": ["face", 0],
                               "pose_video": ["pose", 0], "background_video": ["background", 0],
                               "character_mask": ["block", 0], "continue_motion_max_frames": 5,
                               "video_frame_offset": 0}},
        "sampler": {"class_type": "KSampler",
                    "inputs": {"model": ["sampling", 0], "positive": ["animate", 0],
                               "negative": ["animate", 1], "latent_image": ["animate", 2],
                               "seed": seed, "steps": steps, "cfg": cfg_scale,
                               "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "trim": {"class_type": "TrimVideoLatent",
                 "inputs": {"samples": ["sampler", 0], "trim_amount": ["animate", 3]}},
        "decode": {"class_type": "VAEDecode", "inputs": {"samples": ["trim", 0], "vae": ["vae", 0]}},
        "take": {"class_type": "ImageFromBatch",
                 "inputs": {"image": ["decode", 0], "batch_index": ["animate", 4], "length": 4096}},
        "video": {"class_type": "CreateVideo",
                  "inputs": {"images": ["take", 0], "fps": float(FPS)}},
        "save": {"class_type": "SaveVideo",
                 "inputs": {"video": ["video", 0], "filename_prefix": "motion/" + job_name,
                            "format": "mp4", "codec": "h264"}},
    }

    if continue_video:
        nodes["cont"] = {"class_type": "LoadVideo", "inputs": {"file": continue_video}}
        nodes["cont_frames"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["cont", 0]}}
        nodes["animate"]["inputs"]["continue_motion"] = ["cont_frames", 0]
        nodes["animate"]["inputs"]["continue_motion_max_frames"] = int(continue_frames)

    if with_audio:
        nodes["video"]["inputs"]["audio"] = ["components", 1]

    if int(cfg.get("relight", 1)):
        nodes["lora_relight"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {"model": ["lora_speed", 0],
                       "lora_name": "wan2.2_animate_14B_relight_lora_bf16.safetensors",
                       "strength_model": 1.0},
        }
        nodes["sampling"]["inputs"]["model"] = ["lora_relight", 0]

    return nodes


def find_outputs(obj, acc):
    if isinstance(obj, dict):
        if "filename" in obj and isinstance(obj["filename"], str):
            acc.append(obj)
        for v in obj.values():
            find_outputs(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            find_outputs(v, acc)


def render(cfg, char_name, drive_name, job_name, seed, dst, label, continue_video=None,
           continue_frames=5, with_audio=True):
    workflow = build_workflow(cfg, char_name, drive_name, job_name, seed,
                              continue_video=continue_video, continue_frames=continue_frames,
                              with_audio=with_audio)
    res = post("/prompt", {"prompt": workflow, "client_id": "shots"})
    pid = res.get("prompt_id")
    if not pid:
        raise SystemExit("ComfyUI rejected the workflow: " + json.dumps(res)[:800])
    log(f"      {label}: prompt id {pid}")

    last = 0
    t0 = time.time()
    while True:
        time.sleep(4)
        try:
            hist = get("/history/" + urllib.parse.quote(pid))
        except Exception:
            continue
        if pid in hist:
            entry = hist[pid]
            status = entry.get("status", {})
            if status.get("completed") or status.get("status_str") in ("success", "error"):
                if status.get("status_str") == "error":
                    msgs = [m for m in status.get("messages", []) if m and m[0] == "execution_error"]
                    raise SystemExit("ComfyUI error: " + json.dumps(msgs)[-1500:])
                break
        mins = (time.time() - t0) / 60
        if mins - last >= 2:
            last = mins
            log(f"      {label}: still rendering ... {mins:.0f} min")

    out = []
    find_outputs(hist[pid].get("outputs", {}), out)
    videos = [o for o in out if o["filename"].lower().endswith((".mp4", ".webm", ".mov", ".mkv"))]
    if not videos:
        raise SystemExit("Render finished but no video was returned: " + json.dumps(hist[pid].get("outputs", {}))[:800])

    v = videos[-1]
    q = urllib.parse.urlencode({"filename": v["filename"], "subfolder": v.get("subfolder", ""),
                                "type": v.get("type", "output")})
    with urllib.request.urlopen(COMFY + "/view?" + q, timeout=180) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f)
    log(f"      {label}: saved in {(time.time() - t0) / 60:.1f} min")


def assemble(chunk_files, audio_src, start_frame, total_frames, dst):
    inputs = []
    filters = []
    for i, f in enumerate(chunk_files):
        inputs += ["-i", f]
        filters.append(f"[{i}:v]setpts=PTS-STARTPTS[v{i}]")
    n = len(chunk_files)
    filters.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[cat]")
    filters.append(f"[cat]trim=end_frame={total_frames},setpts=PTS-STARTPTS[out]")
    silent = os.path.splitext(dst)[0] + "_silent.mp4"
    ffmpeg(inputs + ["-filter_complex", ";".join(filters), "-map", "[out]",
                     "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", silent])
    if audio_src and has_audio(audio_src):
        start_time = start_frame / FPS
        ffmpeg(["-i", silent, "-ss", f"{start_time:.4f}", "-t", f"{total_frames / FPS:.4f}",
                "-i", audio_src, "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac", "-af", "apad", "-shortest", dst])
        os.remove(silent)
    else:
        shutil.move(silent, dst)


def plan_chunks(cfg):
    """Return (total_frames, start_frame, chunk_len, stride, overlap, starts).

    Each pass after the first re-reads the previous pass's last `overlap` frames (as a short
    video) so the generated character carries across the cut. Stride is chunk_len - overlap.
    """
    total_frames = max(5, min(int(cfg["frames"]), 4096))
    start_frame = max(0, int(cfg.get("start_frame", 0)))
    chunk_len = max(5, int(cfg.get("chunk_frames", 77)))
    chunk_len = (chunk_len - 1) // 4 * 4 + 1
    overlap = 5 if chunk_len >= 9 else 1
    stride = chunk_len - overlap
    starts = list(range(start_frame, start_frame + total_frames, stride))
    return total_frames, start_frame, chunk_len, stride, overlap, starts


def probe_frames(path):
    r = subprocess.run([find_ffprobe(), "-v", "error", "-select_streams", "v",
                        "-show_entries", "stream=nb_frames", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        n = int(r.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        n = 0
    if n:
        return n
    r = subprocess.run([find_ffprobe(), "-v", "error", "-select_streams", "v", "-count_frames",
                        "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return int(r.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        return 0


def tail_clip(video, dst, n):
    total = probe_frames(video)
    start = max(0, total - n)
    ffmpeg(["-i", video, "-an",
            "-vf", f"select=gte(n\\,{start}),setpts=PTS-STARTPTS",
            "-frames:v", str(n), "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", dst])


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: motion.py <job folder>")
    job_dir = os.path.abspath(sys.argv[1])
    job_name = os.path.basename(job_dir.rstrip("\\/"))
    started = time.time()

    cfg = read_config(job_dir)
    char_name, drive_name, char_path, safe = copy_inputs(job_dir, cfg)
    shutil.copyfile(char_path, os.path.join(job_dir, "motion_ref.png"))
    seed = int(cfg.get("seed", 1))

    if not int(cfg.get("chunked", 0)):
        log(f"[1/3] Submitting Wan 2.2 Animate ({cfg['width']}x{cfg['height']}, {cfg['frames']} frames, "
            f"{cfg['steps']} steps) ...")
        dst = os.path.join(job_dir, "motion.mp4")
        render(cfg, char_name, drive_name, job_name, seed, dst, "render")
        log(f"[3/3] Saved jobs\\{job_name}\\motion.mp4 - DONE in {(time.time() - started) / 60:.1f} min")
        return

    source = find_video(job_dir, "drive")
    if not source:
        raise SystemExit("No driving video for chunked render.")
    norm = os.path.join(job_dir, "drive_norm.mp4")
    if not os.path.exists(norm):
        log("[0/n] Normalizing drive to 16 fps ...")
        normalize_drive(source, norm)

    total_frames, start_frame, chunk_len, stride, overlap, starts = plan_chunks(cfg)

    chunk_cfg = dict(cfg)
    chunk_cfg["frames"] = chunk_len
    chunk_files = []
    continue_video = None
    for idx, pos in enumerate(starts):
        local = os.path.join(job_dir, f"drive_chunk_{idx:03d}.mp4")
        cut_chunk(norm, local, pos, chunk_len)
        _, cdrive, _, _ = copy_inputs(job_dir, chunk_cfg, drive_path=local)

        out_file = os.path.join(job_dir, f"chunk_{idx:03d}.mp4")
        log(f"[chunk {idx + 1}/{len(starts)}] source frame {pos}, {chunk_len} frames"
            + (f" (continuing {overlap})" if continue_video else ""))
        render(chunk_cfg, char_name, cdrive, job_name, seed, out_file,
               f"chunk {idx + 1}", continue_video=continue_video,
               continue_frames=overlap, with_audio=False)
        chunk_files.append(out_file)

        cont_mp4 = os.path.join(job_dir, f"chunk_{idx:03d}_tail.mp4")
        tail_clip(out_file, cont_mp4, overlap)
        continue_video = "motion_" + safe + "_cont.mp4"
        shutil.copyfile(cont_mp4, os.path.join(COMFY_INPUT, continue_video))

    log(f"[n/n] Assembling {len(chunk_files)} chunks, trimming to {total_frames} frames ...")
    dst = os.path.join(job_dir, "motion.mp4")
    assemble(chunk_files, source, start_frame, total_frames, dst)
    log(f"      Saved jobs\\{job_name}\\motion.mp4 - DONE in {(time.time() - started) / 60:.1f} min")


if __name__ == "__main__":
    main()
