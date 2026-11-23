# Local Video Generation Plan: image reference, audio, lip sync, replication

_Researched 2026-11-05 for this laptop._

## 1. Your hardware and its limits

| Part | Spec | What it means |
|---|---|---|
| GPU | RTX 4060 Laptop, **8 GB VRAM**, CUDA 13.1 driver | Workable with GGUF quantized models plus offloading. 480p is the realistic sweet spot; 720p only for short clips with 5B models. |
| System RAM | **16 GB** | **This is the real bottleneck.** Offloading a 14B model plus its text encoder needs more than 16 GB, so ComfyUI will crash or thrash. |
| CPU | i7-14700HX (20C/28T) | Fine. |
| Disk | 580 GB free on C: | Fine. Plan on 150–250 GB for models. |
| Python | 3.13 system install | Don't use it for AI tools. Use the portable/bundled Python that each tool ships with (3.11/3.12). |

### Do these before installing anything
1. **Upgrade RAM to 32 GB, or 64 GB if you can.** This is the most useful upgrade you can make. HX-class laptops almost always have 2 SO-DIMM slots (DDR5). A 2×16 or 2×32 GB kit is cheap, and it's the difference between 14B models running reliably and crashing.
2. Until then, **set the Windows pagefile to 48–64 GB on the SSD**: System → Advanced → Performance → Virtual memory → custom size.
3. Update the NVIDIA Studio/Game driver (yours is current), plug in AC power, and set the Windows power mode to "Best performance".
4. Close Brave, the Epic launcher and Unreal while generating. They take VRAM.

---

## 2. The verdict (what's best for you)

| Need | Best pick for 8 GB / 16 GB | Quant | Why |
|---|---|---|---|
| **Main app** | **Wan2GP (WanGP by DeepBeepMeep)** | built-in | Built for low VRAM (as little as 6 GB for some models). One UI covers Wan 2.2, InfiniteTalk, Wan Animate, LTX-2.x, Hunyuan, Qwen/Flux image models, Mat Anyone masking and LoRAs. Its memory manager beats hand-tuned ComfyUI on weak machines. |
| **Power-user app** | **ComfyUI (portable)** + ComfyUI-GGUF + WanVideoWrapper | – | Repeatable saved workflows, chaining, upscaling. Use it once Wan2GP results are good. |
| **Image → video (core)** | **Wan 2.2 I2V A14B** (high-noise + low-noise) + **Lightx2v 4-step LoRA** | **Q4_K_M** with 32 GB RAM; **Q3_K_M** on 16 GB RAM | Best open I2V quality that runs on 8 GB. About 3 min for a 5 s 480p clip with the speed LoRA. |
| I2V fallback / fast drafts | **Wan 2.2 TI2V-5B** | **Q8_0** or FP8 | Fits easily and can do 720p at 24 fps. Lower quality than 14B. |
| **Image + audio → lip-synced talking video** | **InfiniteTalk** (MeiGen, on Wan 2.1 14B) | **Q4_K_M** (Q3 on 16 GB RAM) + Lightx2v LoRA | Best open audio-driven lip sync with full-body and head motion, long clips, low-VRAM GGUF path. Single- and multi-speaker. |
| **Video with native audio in one pass** | **LTX-2.3 distilled** (via Wan2GP or a GGUF workflow) | Q4 / FP8 distilled | Generates speech, SFX and ambience in sync with the picture. Runs on 8 GB only in community low-VRAM mode with short, low-res clips. Treat it as **experimental** here. |
| **Replicate (motion transfer / character swap)** | **Wan 2.2 Animate 14B** (in Wan2GP, or Kijai's WanVideoWrapper) | Q3_K_M / Q4_K_M | Copies body and face motion from a driving video onto your reference character, or replaces a person in a video. Newer WanGP builds also list **SCAIL 2** as an alternative to try. |
| **Re-dub lips on an existing video** | **LatentSync 1.5** | fp16 | Needs 8 GB. **Not 1.6, which needs 18 GB.** InfiniteTalk's video-to-video mode is the other option. |
| **Voice / audio track** | Local TTS: **IndexTTS-2**, **Chatterbox** or **F5-TTS** (voice cloning); **MMAudio** for SFX on silent clips | – | InfiniteTalk needs an audio file, so make the voice first. |
| **Consistent character stills** | **Qwen-Image-Edit** or **Flux Kontext** (GGUF Q4) | Q4_K_M | Builds a character sheet (front, 3/4, side, outfits) to use as I2V start frames. |
| Upscale / smooth | **SeedVR2** or RealESRGAN, plus **RIFE** interpolation | – | Render at 480p, then upscale to 1080p and interpolate 16→32 fps. |

### Skip these on this laptop
- **LTX-2.5** (Aug–Oct 2026): best open audio+video quality, but even the community Q4 GGUF is about 13 GB and the Gemma-4 encoder is about 8 GB. Needs 16–24 GB VRAM.
- **Kandinsky 6.0 Video Lite (3B, MIT, has audio)**: the official lowest preset is 16 GB, though SD measured about 7.9 GiB peak. Worth retesting once a GGUF or Wan2GP build is out. Watch this one.
- **MiniMax H3**: too large, and its license excludes US/EU/UK.
- **Wan 2.2 S2V**: very heavy (needs 60–80 GB natively). InfiniteTalk does the same job better on 8 GB.
- **Phantom** (multi-reference identity): about 70 GB VRAM.
- **HunyuanVideo 1.5**: about 14 GB even with FP8 and offload.

### About "Open-Higgsfield"
`Anil-matcha/Open-Higgsfield-AI` is a desktop **front-end for paid cloud APIs**. It's free software, but every generation needs paid API keys. It is **not local and not uncensored**, so it doesn't fit your goal. Watch out for look-alikes: `Autom8AI` is a stale fork (inactive since April 2026), `wide-trace/open-higgsfield` has no license, and `ml-doom/higgsfield` is an unrelated ML training framework. Its useful idea, a "studio" with presets, camera moves and character slots, is something you can get locally with Wan2GP presets, ComfyUI saved workflows and Wan camera LoRAs.

### About "uncensored"
Open-weight models run locally (Wan 2.1/2.2, InfiniteTalk, Animate, LTX) have **no server-side filter**. You control the prompt and output. Community finetunes and LoRAs (Civitai, Hugging Face) widen what the base models do well. Use plain base GGUFs from reputable uploaders (QuantStack, city96, Kijai) and add LoRAs as needed. Legal line: don't generate content of real people without their consent, and never anything involving minors. Voice cloning should be your own voice or one you have permission to use.

---

## 3. Quantization guide for 8 GB VRAM

Weights stream from RAM to the GPU, so **VRAM sets speed and resolution, and system RAM sets which quant you can load at all.**

| Model | 16 GB RAM (now) | 32 GB+ RAM (after upgrade) | Notes |
|---|---|---|---|
| Wan 2.2 I2V A14B (×2 experts) | Q3_K_M (~7 GB each) | **Q4_K_M** (~9 GB each); Q5_K_M if 64 GB | Only one expert is in VRAM at a time. Under Q3_K_S, faces and hands degrade noticeably. |
| Wan 2.2 TI2V-5B | Q8_0 | Q8_0 / FP16 | Near lossless at Q8. |
| InfiniteTalk (Wan 2.1 14B base + InfiniteTalk weights) | Q3_K_M | **Q4_K_M** | Plus the wav2vec2 audio encoder (small). |
| Wan 2.2 Animate 14B | Q3_K_M | Q4_K_M | Plus pose/face preprocessors. |
| UMT5-XXL text encoder | **GGUF Q5_K_M** or fp8_e4m3fn | fp8 / Q8 | Runs on CPU/RAM, so it competes with the model for RAM. |
| VAE (Wan 2.1 / 2.2) | bf16 | bf16 | Use tiled VAE decode on 8 GB. |
| LTX-2.3 distilled | Q3/Q4 + fp8 Gemma encoder | Q4_K_M | Experimental at 8 GB. |

Rule of thumb: **Q4_K_M is the quality/size sweet spot. Q5/Q6 only help if you have RAM to spare. Q8 for 5B-class models. Don't use Q2.**

Settings that save VRAM: 832×480 (or 480×832 portrait), 81 frames (5 s at 16 fps), Lightx2v 4–6 steps at CFG 1, block swap 20–30 (ComfyUI wrapper) or WanGP profile 4/5, SageAttention 2 (big speedup on RTX 40), tiled VAE.

---

## 4. Setup steps

### Phase 0: prep (½ day)
- [ ] RAM upgrade (or 48–64 GB pagefile)
- [ ] Install **Git** (already installed) and the **Visual Studio 2022 Build Tools** (C++ workload), needed for SageAttention and Triton
- [ ] Install **ffmpeg** and add it to PATH
- [x] Folder layout: **everything lives in this repo (`Desktop\Videos`)**. See README.md.
  ```
  Videos\
    ComfyUI_windows_portable\
    models\        (shared via extra_model_paths.yaml)
    projects\<project>\{refs,audio,shots}
    tools\         shots.py runner, download_models.ps1
  ```

> **Status 2026-11-05:** ComfyUI v0.44 portable + GGUF, VHS, KJNodes, RIFE, SeedVR2, LatentSync (forced to 1.5) installed. Wan 2.2 I2V Q3_K_M + Q4_K_M, umt5 Q5_K_M, VAE, lightx2v LoRAs downloaded. Draft pipeline smoke-tested OK. Lip sync not yet tested on a real face.

### Phase 1: Wan2GP, the main engine (1 day)
- [ ] Install **Wan2GP** from `github.com/deepbeepmeep/Wan2GP`, either with **Pinokio** (one click) or manually: Python 3.11 venv → `pip install torch` (CUDA 12.8 build) → `pip install -r requirements.txt` → install the SageAttention wheel
- [ ] Launch with a low-VRAM profile (`--profile 4`, or 5 if it OOMs) and `--attention sage2`
- [ ] Test 1: **Wan 2.2 TI2V-5B**, image → 5 s 480p. Confirms the stack works.
- [ ] Test 2: **Wan 2.2 I2V 14B** (WanGP picks its quantized weights) + Lightx2v LoRA, 480p, 4–6 steps
- [ ] Test 3: **InfiniteTalk**, a portrait plus a 10 s WAV → talking video
- [ ] Test 4: **Wan 2.2 Animate**, reference image plus a short dance/talk driving clip (use Mat Anyone for the mask)
- [ ] Test 5 (optional): **LTX-2.3 distilled** text/image → video with audio
- [ ] Log time, peak VRAM and RAM for each in `projects/benchmarks.md`

### Phase 2: ComfyUI, for repeatable pipelines (1–2 days)
- [ ] **ComfyUI Windows portable** (ships its own Python and Torch)
- [ ] Custom nodes (via ComfyUI-Manager):
  - `ComfyUI-Manager`
  - `city96/ComfyUI-GGUF` (loads GGUF unet and text encoders)
  - `kijai/ComfyUI-WanVideoWrapper` (Wan 2.2, InfiniteTalk, Animate, block swap, Lynx/Stand-In)
  - `kijai/ComfyUI-KJNodes`, `Kosinkadink/ComfyUI-VideoHelperSuite`
  - `ComfyUI-Frame-Interpolation` (RIFE), `ComfyUI-SeedVR2` or an upscaler
  - `ComfyUI-LatentSyncWrapper` (1.5), plus a TTS node pack (IndexTTS-2 or Chatterbox) if you want TTS inside the graph
- [ ] Models (Hugging Face: `QuantStack/Wan2.2-I2V-A14B-GGUF`, `Kijai/WanVideo_comfy` and `Kijai/WanVideo_comfy_GGUF` for InfiniteTalk/Animate, `Comfy-Org/Wan_2.2_ComfyUI_Repackaged` for VAE and encoders):
  - `models/unet/` GGUF high + low noise I2V, InfiniteTalk, Animate
  - `models/text_encoders/` umt5-xxl (fp8 or GGUF)
  - `models/vae/` wan_2.1_vae / wan2.2_vae
  - `models/loras/` Lightx2v I2V 4-step distill LoRA (Wan 2.2 and 2.1 versions)
  - `models/clip_vision/` clip_vision_h (for 2.1-based InfiniteTalk)
- [ ] Share the model folder with Wan2GP through `extra_model_paths.yaml` to avoid duplicates
- [ ] Build and save 4 template workflows: `i2v_480p.json`, `talk_infinitetalk.json`, `animate_replace.json`, `upscale_interp.json`

### Phase 3: consistency pipeline (ongoing)
How to keep the same character across shots:
1. **Character bible**: make 1 hero image, then 8–15 variants with Qwen-Image-Edit or Flux Kontext (angles, expressions, outfits). Keep it in `refs/`.
2. **Every shot starts from a ref image** (I2V, not T2V). Keep the same lighting and style words in every prompt, using a prompt template.
3. **Identity helpers**: Stand-In or Lynx (WanVideoWrapper, strength about 0.6) when the face drifts.
4. **Shot chaining**: use the last frame of clip N as the first frame of clip N+1 (or InfiniteTalk/SVI-style long-video modes).
5. **Character LoRA** (best consistency): train a Wan 2.2/2.1 LoRA on 20–40 images from the bible. **8 GB can't train 14B**, so rent a 24–48 GB cloud GPU (RunPod or Vast, about $1–3 total) and use `musubi-tuner` or `ostris/ai-toolkit`. Then run the LoRA locally.
6. **Fixed recipe**: same seed family, sampler, steps, resolution and LoRA strengths. Save the workflow JSON with every final shot.

### Phase 4: production loop
```
script → TTS voice (audio/*.wav)
       → keyframe image per shot (Qwen-Edit/Flux + character LoRA)
       → shot type?
           talking  → InfiniteTalk (image + wav)      → lip-synced clip
           action   → Wan 2.2 I2V 14B (+ camera LoRA) → clip (+ MMAudio SFX)
           replicate→ Wan 2.2 Animate (ref + driving video)
       → upscale (SeedVR2) + RIFE → assemble/mix audio in ffmpeg/DaVinci Resolve
```

---

## 5. Expected performance (RTX 4060 Laptop 8 GB, rough)

| Job | Settings | Time |
|---|---|---|
| Wan 2.2 TI2V-5B | 5 s, 480p, Q8 | ~3–5 min |
| Wan 2.2 I2V 14B | 5 s, 480p, Q4 + Lightx2v 4–6 steps | ~3–6 min (much slower if RAM swaps) |
| InfiniteTalk | 10 s talking, 480p, Q4 + Lightx2v | ~8–15 min |
| Wan Animate | 5 s, 480p | ~6–12 min |
| 720p 14B | – | Usually OOM or very slow. Upscale instead. |

Laptop GPUs throttle, so use a cooling pad and consider a mild undervolt/power limit (MSI Afterburner) for long batches.

---

## 6. Risks and open questions
- **16 GB RAM** is the biggest risk. Expect OOMs and pagefile thrash with 14B models until you upgrade.
- 8 GB numbers in community guides are anecdotal. Benchmark yourself in Phase 1.
- LTX-2.3/2.5 and Kandinsky 6 Lite move fast. Re-check in a month for better low-VRAM builds; native audio in one pass would simplify the pipeline.
- Licenses: Wan 2.x is Apache-2.0 and InfiniteTalk is Apache-2.0. LTX-2.x is free under $10M revenue. Kandinsky 6 is MIT. Check before commercial use.

## 7. Key links
- Wan2GP: https://github.com/deepbeepmeep/Wan2GP
- ComfyUI: https://github.com/comfyanonymous/ComfyUI
- ComfyUI-GGUF: https://github.com/city96/ComfyUI-GGUF
- WanVideoWrapper: https://github.com/kijai/ComfyUI-WanVideoWrapper
- Wan 2.2: https://github.com/Wan-Video/Wan2.2
- InfiniteTalk: https://github.com/MeiGen-AI/InfiniteTalk
- LTX-2 / 8 GB fork: https://huggingface.co/Lightricks/LTX-2 , https://github.com/nalexand/LTX-2-OPTIMIZED
- LatentSync: https://github.com/bytedance/LatentSync
- Kandinsky 6 Lite: https://huggingface.co/kandinskylab/Kandinsky-6.0-Lite-5s-Diffusers
- Open-Higgsfield (API front-end, not local): https://github.com/Anil-matcha/Open-Higgsfield-AI
