"""
Shot runner for ComfyUI + Wan 2.2 I2V (GGUF) + LatentSync 1.5.

Keeps a character consistent across shots:
  - one project.json holds the character description, style, LoRAs, preset
  - every shot starts from a reference image OR the previous shot's last frame ("chain")
  - fixed seeds; the exact graph used for each shot is saved next to the result,
    so any shot can be re-rendered identically (or drag the *_graph.json into ComfyUI).

Usage (from the repo root; ComfyUI must be running: start_comfyui.bat):
  run_shots.bat projects\\example
  ... --only s01,s02          run only some shots
  ... --preset draft          override preset (draft | realism)
  ... --seeds 4               draft seed sweep: render seed, seed+1, ... seed+3
  ... --no-lipsync            skip LatentSync even if a shot has audio
"""
import argparse, copy, json, mimetypes, os, shutil, sys, time, urllib.error, urllib.request, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root
SERVER = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
COMFY_OUT = os.path.join(ROOT, "ComfyUI_windows_portable", "ComfyUI", "output")

DEFAULT_NEGATIVE = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，"
    "丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，"
    "杂乱的背景，三条腿，背景人很多，倒着走, cartoon, cgi, 3d render, plastic skin, airbrushed, oversaturated"
)

SPEED_LORA_HIGH = "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors"
SPEED_LORA_LOW = "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors"

VIDEO_MODELS = {
    # original Wan 2.2 I2V; quant comes from the preset (Q3_K_M draft / Q4_K_M realism)
    "base": {"high": "Wan2.2-I2V-A14B-HighNoise-{q}.gguf", "low": "Wan2.2-I2V-A14B-LowNoise-{q}.gguf", "distilled": False},
    # Wan 2.2 Remix v3.0 I2V: NSFW-capable finetune, lightx2v speed LoRA already merged (CFG 1, 4-8 steps)
    "uncensored": {"high": "wan22RemixT2VI2V_i2vHighV30-{q}.gguf", "low": "wan22RemixT2VI2V_i2vLowV30-{q}.gguf", "distilled": True},
}

# presets for distilled models (speed LoRA baked in -> never add it again, CFG must stay 1)
DISTILLED_PRESETS = {
    "draft": {"quant": "Q3_K_M",
              "high": {"speed_lora": False, "steps": 4, "end": 2, "cfg": 1.0},
              "low": {"speed_lora": False, "steps": 4, "start": 2, "cfg": 1.0}},
    "realism": {"quant": "Q3_K_M",
                "high": {"speed_lora": False, "steps": 8, "end": 4, "cfg": 1.0},
                "low": {"speed_lora": False, "steps": 8, "start": 4, "cfg": 1.0}},
}

PRESETS = {
    # fast prompt/seed testing (~4-6 min / 5 s clip)
    "draft": {
        "quant": "Q3_K_M",
        "high": {"speed_lora": True, "steps": 4, "end": 2, "cfg": 1.0},
        "low": {"speed_lora": True, "steps": 4, "start": 2, "cfg": 1.0},
    },
    # realism: high-noise (motion/composition) WITHOUT speed LoRA, real CFG;
    # low-noise (detail) with speed LoRA. Both splits sit at 50% of the schedule.
    "realism": {
        "quant": "Q4_K_M",
        "high": {"speed_lora": False, "steps": 16, "end": 8, "cfg": 3.5},
        "low": {"speed_lora": True, "steps": 4, "start": 2, "cfg": 1.0},
    },
}


# ---------------------------------------------------------------- ComfyUI API
def api(path, data=None, raw=None, headers=None):
    req = urllib.request.Request(SERVER + path, data=raw if raw is not None else
                                 (json.dumps(data).encode() if data is not None else None),
                                 headers=headers or ({"Content-Type": "application/json"} if data is not None else {}))
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"{}")


def free():
    """Unload every model and drop cached results before the next big step (16 GB RAM machine)."""
    api("/free", {"unload_models": True, "free_memory": True})
    time.sleep(4)  # the worker applies the flags on its next idle tick


def upload(path):
    """Upload an image/audio file to ComfyUI's input folder, return its name."""
    boundary = uuid.uuid4().hex
    name = os.path.basename(path)
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
                f"Content-Type: {ctype}\r\n\r\n").encode() + f.read() + \
               (f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue"
                f"\r\n--{boundary}--\r\n").encode()
    res = api("/upload/image", raw=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return (res.get("subfolder", "") + "/" if res.get("subfolder") else "") + res["name"]


def run_graph(graph, label):
    try:
        res = api("/prompt", {"prompt": graph, "client_id": "shots"})
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{label}: ComfyUI rejected the graph:\n{e.read().decode(errors='replace')}")
    if res.get("node_errors"):
        raise RuntimeError(f"{label}: invalid nodes:\n{json.dumps(res['node_errors'], indent=1)}")
    pid = res.get("prompt_id")
    if not pid:
        raise RuntimeError(f"{label}: ComfyUI rejected the graph: {res}")
    t0 = time.time()
    while True:
        time.sleep(3)
        h = api(f"/history/{pid}")
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                msgs = [m for m in st.get("messages", []) if m[0] == "execution_error"]
                raise RuntimeError(f"{label}: {msgs[-1][1].get('exception_message') if msgs else st}")
            if st.get("completed"):
                print(f"  {label} done in {(time.time() - t0) / 60:.1f} min")
                return h[pid]["outputs"]
        print(f"\r  {label} running... {(time.time() - t0) / 60:.1f} min", end="", flush=True)


def out_file(outputs, node_id):
    o = outputs.get(node_id, {})
    for key in ("gifs", "images", "videos", "audio"):
        for item in o.get(key, []):
            if item.get("fullpath"):
                return item["fullpath"]
            return os.path.join(COMFY_OUT, item.get("subfolder", ""), item["filename"])
    raise RuntimeError(f"no output from node {node_id}")


# ---------------------------------------------------------------- graphs
class G:
    def __init__(self):
        self.nodes, self.n = {}, 0

    def add(self, cls, **inputs):
        self.n += 1
        self.nodes[str(self.n)] = {"class_type": cls, "inputs": inputs}
        return str(self.n)


def combine(g, images, prefix, fps, audio=None):
    kw = dict(images=[images, 0], frame_rate=fps, loop_count=0, filename_prefix=prefix,
              format="video/h264-mp4", pix_fmt="yuv420p", crf=17, save_metadata=True,
              trim_to_audio=False, pingpong=False, save_output=True)
    if audio:
        kw["audio"] = audio
    return g.add("VHS_VideoCombine", **kw)


def model_chain(g, unet_file, use_speed, speed_lora, loras, which, shift):
    m = g.add("UnetLoaderGGUF", unet_name=unet_file)
    if use_speed:
        m = g.add("LoraLoaderModelOnly", model=[m, 0], lora_name=speed_lora, strength_model=1.0)
    for l in loras:  # character / realism / style LoRAs from Civitai
        s = l.get(which, l.get("strength", 1.0))
        if s:
            m = g.add("LoraLoaderModelOnly", model=[m, 0], lora_name=l["file"], strength_model=s)
    return g.add("ModelSamplingSD3", model=[m, 0], shift=shift)


def gen_graph(p, preset, positive, negative, image_name, seed, prefix):
    g = G()
    vm = VIDEO_MODELS[p.get("video_model", "base")]
    q = preset["quant"]
    hi, lo = preset["high"], preset["low"]
    mh = model_chain(g, vm["high"].format(q=q), hi["speed_lora"], SPEED_LORA_HIGH, p["loras"], "high", p["shift"])
    ml = model_chain(g, vm["low"].format(q=q), lo["speed_lora"], SPEED_LORA_LOW, p["loras"], "low", p["shift"])
    clip = g.add("CLIPLoaderGGUF", clip_name="umt5-xxl-encoder-Q5_K_M.gguf", type="wan")
    vae = g.add("VAELoader", vae_name="wan_2.1_vae.safetensors")
    pos = g.add("CLIPTextEncode", clip=[clip, 0], text=positive)
    neg = g.add("CLIPTextEncode", clip=[clip, 0], text=negative)
    img = g.add("LoadImage", image=image_name)
    i2v = g.add("WanImageToVideo", positive=[pos, 0], negative=[neg, 0], vae=[vae, 0], start_image=[img, 0],
                width=p["width"], height=p["height"], length=p["frames"], batch_size=1)
    s1 = g.add("KSamplerAdvanced", model=[mh, 0], positive=[i2v, 0], negative=[i2v, 1], latent_image=[i2v, 2],
               add_noise="enable", noise_seed=seed, steps=hi["steps"], cfg=hi["cfg"], sampler_name="euler",
               scheduler="simple", start_at_step=0, end_at_step=hi["end"], return_with_leftover_noise="enable")
    s2 = g.add("KSamplerAdvanced", model=[ml, 0], positive=[i2v, 0], negative=[i2v, 1], latent_image=[s1, 0],
               add_noise="disable", noise_seed=0, steps=lo["steps"], cfg=lo["cfg"], sampler_name="euler",
               scheduler="simple", start_at_step=lo["start"], end_at_step=10000, return_with_leftover_noise="disable")
    dec = g.add("VAEDecodeTiled", samples=[s2, 0], vae=[vae, 0], tile_size=256, overlap=64,
                temporal_size=64, temporal_overlap=8)
    raw = combine(g, dec, prefix + "_raw", p["fps"])
    rife = g.add("RIFE VFI", frames=[dec, 0], ckpt_name="rife49.pth", clear_cache_after_n_frames=10,
                 multiplier=2, fast_mode=True, ensemble=True, scale_factor=1.0,
                 dtype="float16", torch_compile=False, batch_size=1)
    smooth = combine(g, rife, prefix + "_smooth", p["fps"] * 2)
    last = g.add("ImageFromBatch", image=[dec, 0], batch_index=p["frames"] - 1, length=1)
    lastimg = g.add("SaveImage", images=[last, 0], filename_prefix=prefix + "_last")
    return g.nodes, {"raw": raw, "smooth": smooth, "last": lastimg}


def lipsync_graph(video_path, audio_name, seed, prefix, lips=1.5, steps=20):
    g = G()
    v = g.add("VHS_LoadVideoPath", video=video_path, force_rate=25, custom_width=0, custom_height=0,
              frame_load_cap=0, skip_first_frames=0, select_every_nth=1)
    a = g.add("LoadAudio", audio=audio_name)
    adj = g.add("VideoLengthAdjuster", images=[v, 0], audio=[a, 0], mode="pingpong", fps=25.0, silent_padding_sec=0.5)
    ls = g.add("LatentSyncNode", images=[adj, 0], audio=[adj, 1], seed=seed, lips_expression=lips, inference_steps=steps)
    out = combine(g, ls, prefix + "_lipsync", 25, audio=[ls, 1])
    return g.nodes, {"final": out}


def resolve_preset(p, preset_name):
    table = DISTILLED_PRESETS if VIDEO_MODELS[p.get("video_model", "base")]["distilled"] else PRESETS
    preset = copy.deepcopy(table[preset_name])
    for k, v in p.get("preset_overrides", {}).get(preset_name, {}).items():
        preset[k] = {**preset[k], **v} if isinstance(v, dict) else v
    return preset


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--only")
    ap.add_argument("--preset")
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--no-lipsync", action="store_true")
    a = ap.parse_args()

    proj = os.path.abspath(a.project)
    p = json.load(open(os.path.join(proj, "project.json"), encoding="utf-8-sig"))
    p.setdefault("loras", []); p.setdefault("width", 480); p.setdefault("height", 832)
    p.setdefault("frames", 81); p.setdefault("fps", 16); p.setdefault("shift", 5.0)
    preset_name = a.preset or p.get("preset", "draft")
    preset = resolve_preset(p, preset_name)
    negative = p.get("negative") or DEFAULT_NEGATIVE
    name = os.path.basename(proj)
    only = set(a.only.split(",")) if a.only else None

    prev_last = None
    for shot in p["shots"]:
        sid = shot["id"]
        shot_dir = os.path.join(proj, "shots", sid)
        if only and sid not in only:
            cand = os.path.join(shot_dir, "last.png")
            prev_last = cand if os.path.exists(cand) else prev_last
            continue
        os.makedirs(shot_dir, exist_ok=True)

        src = shot.get("image", "chain")
        if src == "chain":
            if not prev_last:
                sys.exit(f"{sid}: 'chain' needs a previous shot with a last frame")
            start = prev_last
        else:
            start = os.path.join(proj, src)
        positive = ". ".join(x for x in (p.get("character", ""), shot["action"], p.get("style", "")) if x)
        base_seed = shot.get("seed", p.get("seed", 42))
        print(f"\n=== {sid} [{preset_name}] start={os.path.basename(start)}\n  prompt: {positive}")
        img_name = upload(start)

        for k in range(a.seeds):
            seed = base_seed + k
            tag = f"{sid}_{preset_name}_s{seed}"
            prefix = f"{name}/{tag}"
            graph, ids = gen_graph(p, preset, positive, negative, img_name, seed, prefix)
            outs = run_graph(graph, f"{tag} video")
            res = {"raw": out_file(outs, ids["raw"]), "smooth": out_file(outs, ids["smooth"]),
                   "last": out_file(outs, ids["last"])}
            for key, f in res.items():
                shutil.copy2(f, os.path.join(shot_dir, f"{tag}_{key}{os.path.splitext(f)[1]}"))
            graphs = {"video": graph}

            audio = shot.get("audio")
            if audio and not a.no_lipsync:
                aname = upload(os.path.join(proj, audio))
                lg, lids = lipsync_graph(res["smooth"], aname, seed, prefix, shot.get("lips_expression", 1.5))
                louts = run_graph(lg, f"{tag} lipsync")
                f = out_file(louts, lids["final"])
                shutil.copy2(f, os.path.join(shot_dir, f"{tag}_final.mp4"))
                graphs["lipsync"] = lg

            json.dump({"shot": shot, "preset": preset_name, "seed": seed, "prompt": positive,
                       "negative": negative, "start_image": start, "graphs": graphs},
                      open(os.path.join(shot_dir, f"{tag}_recipe.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
            json.dump(graph, open(os.path.join(shot_dir, f"{tag}_graph.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
            if k == 0:
                shutil.copy2(res["last"], os.path.join(shot_dir, "last.png"))
        prev_last = os.path.join(shot_dir, "last.png")
    print("\nAll shots finished. Results in", os.path.join(proj, "shots"))


if __name__ == "__main__":
    main()
