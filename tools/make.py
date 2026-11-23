"""
One-command pipeline:  prompt -> reference image -> video -> voice + lip sync -> sound effects -> final.mp4

  make.bat jobs\\my_job            (folder containing job.txt)

job.txt is plain text, one "key: value" per line ('#' = comment). Only image/video are required:

  image:  what the reference picture shows (person, outfit, place, framing)
  video:  what happens in the clip (motion, camera)
  speech: words the character says        (empty = no voice)
  sound:  auto | none | your sound description (effects/ambience/music)

Optional:  preset (draft|realism), seed, seconds (1-5), size (portrait|landscape|square),
           image_model / video_model (uncensored|base), voice (path to a 5-15 s wav to clone),
           voice_emotion (0.25-2.0, default 0.5), sound_volume (dB for effects under speech, default -10)

Re-running reuses the reference image if `image`, `seed`, `size` and `image_model` did not change,
so you can iterate on the video prompt without regenerating the picture.
"""
import argparse, json, math, os, shutil, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shots import (G, api, free, upload, run_graph, out_file, combine, gen_graph, lipsync_graph,  # noqa: E402
                   resolve_preset, DEFAULT_NEGATIVE)
from image import zimage_graph  # noqa: E402
import qa  # noqa: E402

SIZES = {  # (image w, h), (video w, h)
    "portrait": ((768, 1344), (480, 832)),
    "landscape": ((1344, 768), (832, 480)),
    "square": ((1024, 1024), (640, 640)),
}
SFX_NEGATIVE_WITH_SPEECH = "speech, talking, voice, singing, vocals"
VOICES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "voices")


def provided(job_dir, kind):
    """A user-supplied picture.* / video.* in the job folder (chosen in the Studio UI), else None."""
    return next((os.path.join(job_dir, f) for f in sorted(os.listdir(job_dir))
                 if os.path.splitext(f)[0] == kind), None)


def read_job(path):
    job = {}
    for line in open(path, encoding="utf-8-sig"):
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        job[k.strip().lower()] = v.strip()
    if not job.get("image") and not provided(os.path.dirname(os.path.abspath(path)), "picture"):
        sys.exit("job.txt needs an 'image:' line (or choose your own picture in the Studio UI)")
    return job


def continue_from(other, job_dir):
    """`image: from:<job name>` - use the last frame of another job's video as this job's start picture.
    Copies it to <this job>/start.png (so the exact picture is kept) and returns 'start.png'."""
    src_dir = os.path.join(os.path.dirname(job_dir), other)
    if not os.path.isdir(src_dir):
        sys.exit(f"image: from:{other} - no job folder named '{other}' next to this one")
    dest = os.path.join(job_dir, "start.png")
    last = os.path.join(src_dir, "video_last.png")
    if os.path.isfile(last):
        shutil.copy2(last, dest)
    else:  # talking jobs have no video_last.png: take the final frame of final.mp4
        video = os.path.join(src_dir, "final.mp4")
        if not os.path.isfile(video):
            sys.exit(f"job '{other}' has no video yet (no video_last.png / final.mp4) - render it first")
        subprocess.run([qa.FFMPEG, "-y", "-loglevel", "error", "-sseof", "-0.2", "-i", video,
                        "-update", "1", "-frames:v", "1", dest], check=True)
    print(f"  continuing from the last frame of job '{other}' -> start.png")
    return "start.png"


_object_info = {}


def defaults(cls):
    """All widget defaults of a node, so we only override what we need."""
    if cls not in _object_info:
        _object_info.update(api(f"/object_info/{cls.replace(' ', '%20')}"))
    out = {}
    for name, spec in _object_info[cls]["input"].get("required", {}).items():
        if len(spec) > 1 and isinstance(spec[1], dict) and "default" in spec[1]:
            out[name] = spec[1]["default"]
        elif spec[0] == "COMBO" and spec[1].get("options"):
            out[name] = spec[1]["options"][0]
        elif isinstance(spec[0], list) and spec[0]:
            out[name] = spec[0][0]
    return out


def step(graph, label, tries=3):
    """Run one ComfyUI graph. Transient failures (crash, out of memory, ComfyUI died) are retried
    after restarting/freeing ComfyUI; a graph ComfyUI rejects as invalid is a bug and is not retried."""
    for i in range(1, tries + 1):
        try:
            qa.ensure_comfy()
            free()
            return run_graph(graph, label)
        except (RuntimeError, OSError) as e:
            msg = str(e)
            if "rejected the graph" in msg or "invalid nodes" in msg or i == tries:
                raise
            print(f"  {label} failed ({msg.splitlines()[0][:160]}) -> retry {i}/{tries - 1} in 20 s")
            time.sleep(20)


def audio_seconds(path):
    import soundfile  # available in ComfyUI's python
    info = soundfile.info(path)
    return info.frames / info.samplerate


def tts_graph(text, prefix, seed, emotion, voice_name=None):
    g = G()
    kw = defaults("ChatterboxTTS")
    kw.update(model_pack_name="chatterbox", text=text, seed=seed, exaggeration=emotion)
    if voice_name:
        v = g.add("LoadAudio", audio=voice_name)
        kw["audio_prompt"] = [v, 0]
    t = g.add("ChatterboxTTS", **kw)
    out = g.add("SaveAudio", audio=[t, 0], filename_prefix=prefix)
    g.add("ChatterboxUnloadAll", after=[t, 0])  # Chatterbox otherwise keeps ~800 MB on the GPU
    return g.nodes, out


def load_video(g, path, frame_cap=0):
    return g.add("VHS_LoadVideoPath", video=path, force_rate=25, custom_width=0, custom_height=0,
                 frame_load_cap=frame_cap, skip_first_frames=0, select_every_nth=1)


TALK_CHUNK = 81  # frames per InfiniteTalk chunk at 25 fps (3.24 s)


def talk_graph(image_name, speech_name, prompt, width, height, seed, chunks, prefix):
    """InfiniteTalk (Wan 2.1 I2V 14B + audio patch): the whole clip is generated from the reference
    image while following the speech, so the face stays the same person (no mouth pasting)."""
    g = G()
    m = g.add("UnetLoaderGGUF", unet_name="wan2.1-i2v-14b-480p-Q3_K_M.gguf")
    m = g.add("LoraLoaderModelOnly", model=[m, 0], lora_name="lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",
              strength_model=1.0)
    patch = g.add("ModelPatchLoader", name="wan2.1_infiniteTalk_single_fp16.safetensors")
    clip = g.add("CLIPLoaderGGUF", clip_name="umt5-xxl-encoder-Q5_K_M.gguf", type="wan")
    vae = g.add("VAELoader", vae_name="wan_2.1_vae.safetensors")
    pos = g.add("CLIPTextEncode", clip=[clip, 0], text=prompt)
    neg = g.add("ConditioningZeroOut", conditioning=[pos, 0])
    enc = g.add("AudioEncoderLoader", audio_encoder_name="wav2vec2-chinese-base_fp16.safetensors")
    speech = g.add("LoadAudio", audio=speech_name)
    audio_feat = g.add("AudioEncoderEncode", audio_encoder=[enc, 0], audio=[speech, 0])
    img = g.add("LoadImage", image=image_name)
    frames, prev = None, None
    for i in range(chunks):
        kw = dict(mode="single_speaker", model=[m, 0], model_patch=[patch, 0], positive=[pos, 0], negative=[neg, 0],
                  vae=[vae, 0], width=width, height=height, length=TALK_CHUNK, audio_encoder_output_1=[audio_feat, 0],
                  motion_frame_count=9, audio_scale=1.0, start_image=[img, 0])
        if prev:
            kw["previous_frames"] = [prev, 0]
        it = g.add("WanInfiniteTalkToVideo", **kw)
        noise = g.add("RandomNoise", noise_seed=seed + i)
        guider = g.add("CFGGuider", model=[it, 0], positive=[it, 1], negative=[it, 2], cfg=1.0)
        sampler = g.add("KSamplerSelect", sampler_name="euler")
        sigmas = g.add("BasicScheduler", model=[it, 0], scheduler="normal", steps=6, denoise=1.0)
        lat = g.add("SamplerCustomAdvanced", noise=[noise, 0], guider=[guider, 0], sampler=[sampler, 0],
                    sigmas=[sigmas, 0], latent_image=[it, 3])
        dec = g.add("VAEDecodeTiled", samples=[lat, 0], vae=[vae, 0], tile_size=256, overlap=64,
                    temporal_size=64, temporal_overlap=8)
        frames = dec if frames is None else g.add("ImageBatch", image1=[frames, 0], image2=[dec, 0])
        prev = dec
    out = combine(g, frames, prefix, 25, audio=[speech, 0])
    return g.nodes, out


def mix_graph(video_path, speech_name, sfx_name, sfx_db, prefix, frame_cap=0):
    """Final mux at 25 fps: speech (if any) + sound effects (if any) under it."""
    g = G()
    v = load_video(g, video_path, frame_cap)
    tracks = []
    if speech_name:
        tracks.append([g.add("LoadAudio", audio=speech_name), 0])
    if sfx_name:
        s = g.add("LoadAudio", audio=sfx_name)
        tracks.append([g.add("AudioAdjustVolume", audio=[s, 0], volume=sfx_db), 0] if sfx_db else [s, 0])
    audio = tracks[0] if tracks else None
    if len(tracks) == 2:
        audio = [g.add("AudioMerge", audio1=tracks[0], audio2=tracks[1], merge_method="add"), 0]
    return g.nodes, combine(g, v, prefix, 25, audio=audio)


def sfx_graph(video_path, prompt, negative, seed, prefix):
    """MMAudio: sound effects / ambience generated from the video frames + prompt (audio only)."""
    g = G()
    v = load_video(g, video_path)
    m = g.add("MMAudioModelLoader", mmaudio_model="mmaudio_large_44k_v2_fp16.safetensors", base_precision="fp16")
    fu = g.add("MMAudioFeatureUtilsLoader", vae_model="mmaudio_vae_44k_fp16.safetensors",
               synchformer_model="mmaudio_synchformer_fp16.safetensors",
               clip_model="apple_DFN5B-CLIP-ViT-H-14-384_fp16.safetensors", mode="44k", precision="fp16")
    s = g.add("MMAudioSampler", mmaudio_model=[m, 0], feature_utils=[fu, 0], images=[v, 0], duration=10.0,
              steps=25, cfg=4.5, seed=seed, prompt=prompt, negative_prompt=negative,
              mask_away_clip=False, force_offload=True)
    return g.nodes, g.add("SaveAudio", audio=[s, 0], filename_prefix=prefix)


def parse():
    ap = argparse.ArgumentParser()
    ap.add_argument("job", help="job folder (with job.txt) or path to a job .txt file")
    ap.add_argument("--reuse-video", action="store_true",
                    help="keep the existing video; only redo voice, lip sync and sound")
    ap.add_argument("--image-only", action="store_true", help="stop after the reference image")
    return ap.parse_args()


def build(a, bump=0, lipsync_mode=None, preset=None):
    """One full pass of the pipeline. bump changes the video/voice seeds (the picture keeps its seed).
    Returns (final path, speech seconds, lip sync ok)."""
    job_file = a.job if a.job.lower().endswith(".txt") else os.path.join(a.job, "job.txt")
    job_dir = os.path.dirname(os.path.abspath(job_file))
    job = read_job(job_file)
    name = os.path.basename(job_dir)
    t_start = time.time()
    own_picture = provided(job_dir, "picture")
    own_video = provided(job_dir, "video")
    if job["image"].lower().startswith("from:"):  # image: from:other_job -> start from that job's last frame
        job["image"] = continue_from(job["image"][5:].strip(), job_dir)
        own_picture = None

    preset_name = preset or job.get("preset", "realism")
    seed = int(job.get("seed", 1))
    vseed = seed + bump
    size = job.get("size", "portrait")
    (iw, ih), (vw, vh) = SIZES[size]
    image_model = job.get("image_model", "uncensored")
    video_model = job.get("video_model", "uncensored")
    seconds = max(1.0, min(5.0, float(job.get("seconds", 5))))
    frames = 4 * round(seconds * 16 / 4) + 1
    speech = job.get("speech", "")
    sound = job.get("sound", "auto")
    recipe = {"job": job, "steps": {}}

    # 1) reference image ------------------------------------------------------------------
    ref = os.path.join(job_dir, "ref.png")
    ref_key = {"image": job["image"], "seed": seed, "size": size, "image_model": image_model}
    ref_recipe = os.path.join(job_dir, "ref_recipe.json")
    if own_picture:
        if os.path.abspath(own_picture).lower() != os.path.abspath(ref).lower():
            shutil.copy2(own_picture, ref)
        print("[1/5] using your picture", os.path.basename(own_picture))
    elif os.path.isfile(os.path.join(job_dir, job["image"])):
        if os.path.abspath(os.path.join(job_dir, job["image"])).lower() != os.path.abspath(ref).lower():
            shutil.copy2(os.path.join(job_dir, job["image"]), ref)  # (image: ref.png is already the reference)
        print("[1/5] using your image", job["image"])
    elif os.path.exists(ref) and os.path.exists(ref_recipe) and \
            json.load(open(ref_recipe, encoding="utf-8")).get("key") == ref_key:
        print("[1/5] reference image unchanged -> reusing ref.png")
    else:
        print(f"[1/5] reference image ({image_model})")
        graph, out = zimage_graph(job["image"], seed, iw, ih, 9, f"{name}/ref", image_model)
        shutil.copy2(out_file(step(graph, "image"), out), ref)
        json.dump({"key": ref_key, "graph": graph}, open(ref_recipe, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    if a.image_only:
        print(f"\nDONE in {(time.time() - t_start) / 60:.1f} min -> {ref}")
        return
    if not job.get("video") and not own_video:
        sys.exit("Write a video prompt ('video:' line) to make the video.")

    # 2) voice ----------------------------------------------------------------------------
    speech_file = None
    dur = 0.0
    if speech:
        print("[2/5] voice")
        voice_name = None
        v = job.get("voice", "").strip()
        if v and v.lower() != "male":  # empty / male = Chatterbox's built-in (male) voice
            cands = [os.path.join(job_dir, v), os.path.join(VOICES_DIR, v), os.path.join(VOICES_DIR, v + ".wav")]
            path = next((c for c in cands if os.path.isfile(c)), None)
            if not path:
                sys.exit(f"voice '{v}' not found (looked in the job folder and {VOICES_DIR})")
            voice_name = upload(path)
            print("  cloning voice from", path)
        graph, out = tts_graph(speech, f"{name}/speech", vseed, float(job.get("voice_emotion", 0.5)), voice_name)
        f = out_file(step(graph, "voice"), out)
        speech_file = os.path.join(job_dir, "speech" + os.path.splitext(f)[1])
        shutil.copy2(f, speech_file)
        dur = audio_seconds(speech_file)
        print(f"  speech is {dur:.1f} s")
    else:
        print("[2/5] voice: none")

    # 3) video ----------------------------------------------------------------------------
    talk = bool(speech_file) and (lipsync_mode or job.get("lipsync", "infinitetalk")).lower() == "infinitetalk"
    if own_video:  # your own clip: speech is lip-synced onto it instead of generating a video
        talk = False
    current = os.path.join(job_dir, "video_talk.mp4" if talk else "video_smooth.mp4")
    if own_video and not a.reuse_video:
        shutil.copy2(own_video, current)
        print(f"[3/5] video: using your video {os.path.basename(own_video)}")
    elif a.reuse_video and os.path.exists(current):
        print(f"[3/5] video: reusing {os.path.basename(current)}")
    elif talk:
        chunks = 1 if dur <= 3.0 else 2 if dur <= 6.0 else 3
        print(f"[3/5] talking video (InfiniteTalk, {chunks} x {TALK_CHUNK} frames @25fps) - face stays consistent")
        graph, out = talk_graph(upload(ref), upload(speech_file), job["video"], vw, vh, vseed, chunks, f"{name}/talk")
        shutil.copy2(out_file(step(graph, "talking video"), out), current)
        recipe["steps"]["video"] = graph
    else:
        print(f"[3/5] video ({video_model}, {preset_name}, {frames} frames)")
        p = {"loras": [], "width": vw, "height": vh, "frames": frames, "fps": 16, "shift": 5.0, "video_model": video_model}
        preset = resolve_preset(p, preset_name)
        if job.get("video_quant"):
            preset["quant"] = job["video_quant"]  # Q3_K_M (16 GB RAM) | Q4_K_M (32 GB+ RAM)
        graph, ids = gen_graph(p, preset, job["video"], job.get("negative", DEFAULT_NEGATIVE), upload(ref), vseed, f"{name}/video")
        outs = step(graph, "video")
        for key in ("raw", "smooth", "last"):
            f = out_file(outs, ids[key])
            shutil.copy2(f, os.path.join(job_dir, f"video_{key}{os.path.splitext(f)[1]}"))
        recipe["steps"]["video"] = graph

    # 4) sound effects (runs first, on a clean GPU) ----------------------------------------
    sfx_file = None
    if sound.lower() != "none":
        sfx_prompt = job["video"] if sound.lower() == "auto" else sound
        print(f"[4/5] sound effects: {sfx_prompt[:80]}")
        negative = SFX_NEGATIVE_WITH_SPEECH if speech_file else ""
        try:
            graph, out = sfx_graph(current, sfx_prompt, negative, vseed, f"{name}/sfx")
            f = out_file(step(graph, "sound"), out)
            sfx_file = os.path.join(job_dir, "sfx" + os.path.splitext(f)[1])
            shutil.copy2(f, sfx_file)
            recipe["steps"]["sound"] = graph
        except RuntimeError as e:
            print(f"  sound effects failed ({str(e).splitlines()[0][:200]}) -> continuing without them")
    else:
        print("[4/5] sound effects: none")

    lipsync_ok = True
    # 5) lip sync -------------------------------------------------------------------------
    if talk:
        print("[5/5] lip sync: done by InfiniteTalk")
    elif speech_file:
        print("[5/5] lip sync")
        try:
            graph, lids = lipsync_graph(current, upload(speech_file), vseed, f"{name}/lipsync")
            f = out_file(step(graph, "lip sync"), lids["final"])
            current = os.path.join(job_dir, "video_lipsync.mp4")
            shutil.copy2(f, current)
            recipe["steps"]["lipsync"] = graph
        except RuntimeError as e:
            lipsync_ok = False
            print(f"  lip sync failed ({str(e).splitlines()[0][:200]})\n  -> keeping the video and adding the voice without lip sync."
                  "  Tip: lip sync needs a clearly visible, mostly frontal face (close-up / medium shot).")
    else:
        print("[5/5] lip sync: not needed")

    # final mix: video + speech + effects --------------------------------------------------
    print("final mix")
    graph, out = mix_graph(current, speech_file and upload(speech_file), sfx_file and upload(sfx_file),
                           int(job.get("sound_volume", -10)) if speech_file else 0, f"{name}/final",
                           frame_cap=math.ceil((dur + 0.6) * 25) if talk else 0)
    final = os.path.join(job_dir, "final.mp4")
    shutil.copy2(out_file(step(graph, "mix"), out), final)

    json.dump(recipe, open(os.path.join(job_dir, "recipe.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"\nrendered in {(time.time() - t_start) / 60:.1f} min ->", final)
    return final, dur, lipsync_ok


def main():
    a = parse()
    if a.image_only:
        build(a)
        return
    job_file = a.job if a.job.lower().endswith(".txt") else os.path.join(a.job, "job.txt")
    _job = read_job(job_file)
    seconds = max(1.0, min(5.0, float(_job.get("seconds", 5))))
    job_lipsync = _job.get("lipsync", "infinitetalk").lower()
    # attempt 1: as written. attempt 2 (only if QA fails): the FAST route - new seed, LatentSync lip sync
    # on a draft-preset video (~15 min instead of ~30). Only 2 attempts, so the worst case is ~1.5x, not 3x.
    attempts = [(0, None, None), (101, "latentsync", "draft")]
    t0, best = time.time(), None
    audio_only = False
    for n, (bump, mode, preset) in enumerate(attempts, 1):
        if n > 1 and audio_only:  # picture was fine: redo only voice + sound + mix (~3 min)
            print(f"\n=== attempt {n}/{len(attempts)}: keeping the video, redoing voice/sound/mix ===")
            a.reuse_video, mode, preset = True, None, None
        elif n > 1:
            print(f"\n=== attempt {n}/{len(attempts)}: fast route (new seed, {mode} lip sync, {preset} preset) ===")
            a.reuse_video = False
        try:
            final, dur, ok = build(a, bump, mode, preset)
        except (RuntimeError, OSError) as e:
            print(f"  attempt {n} crashed: {str(e).splitlines()[0][:200]}")
            if n < len(attempts):
                try:
                    qa.ensure_comfy()
                except RuntimeError as e2:
                    sys.exit(str(e2))
                continue
            sys.exit("all attempts failed; see the messages above")
        print("checking the result ...")
        problems, warnings, info = qa.check(final, dur, seconds, ok)
        print("  checked:", ", ".join(f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}" for k, v in info.items()))
        for w in warnings:
            print("  WARNING:", w)
        if not problems:
            print(f"\nDONE in {(time.time() - t0) / 60:.1f} min (QA passed) -> {final}")
            return
        for pr in problems:
            print("  PROBLEM:", pr)
        # InfiniteTalk bakes the speech into the picture, so only LatentSync/silent jobs can keep the video
        audio_only = (mode or job_lipsync) != "infinitetalk" and all(any(w in pr for w in ("audio", "silent", "speech")) and "lip sync" not in pr for pr in problems)
        keep = os.path.join(os.path.dirname(final), f"final_attempt{n}.mp4")
        shutil.copy2(final, keep)
        best = best or final
    print(f"\nDONE, but QA still reports problems after {len(attempts)} attempts (kept {best}). "
          "Try a closer face framing or a different image/seed.")
    sys.exit(2)


if __name__ == "__main__":
    main()
