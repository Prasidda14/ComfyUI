# Local Video Studio: Wan 2.2 I2V + LatentSync (RTX 4060 8 GB)

Everything runs from this folder. Nothing is installed system-wide.

## ▶ Start / ■ Stop / 🔍 Graph

| | file | what it does |
|---|---|---|
| ▶ **Start** | [studio.bat](studio.bat) | starts ComfyUI (http://127.0.0.1:8188) + Studio (http://127.0.0.1:8190) and opens the browser |
| ■ **Stop** | [stop_all.bat](stop_all.bat) | stops ComfyUI + Studio and frees the GPU (don't use while a video is rendering) |
| 🔍 **Graph** | [graphify.bat](graphify.bat) | rebuilds the project dependency map ([graph.json](graph.json)), visualizer at http://127.0.0.1:8190/graph |

> **Note for AI Agents & Developers**: See [AGENTS.md](AGENTS.md). Inspect [graph.json](graph.json) first for a complete dependency graph covering scripts, ComfyUI node classes, custom node packs, models, and API endpoints.

Double-click these files in **File Explorer** (`C:\Users\prasi\Desktop\Videos`), or in a terminal run `.\studio.bat` / `.\stop_all.bat` / `.\graphify.bat`.

```
Videos/
  AGENTS.md                AI assistant onboarding & architecture guide
  graph.json               dependency map across all scripts, nodes & models
  graphify.bat             rebuilds graph.json (or .\graphify.bat --open)
  start_comfyui.bat        <- 1. start ComfyUI  (http://127.0.0.1:8188)
  run_shots.bat            <- 2. render a project's shots (consistency runner)
  extra_model_paths.yaml   ComfyUI reads models from ./models
  models/
    unet/                  Wan2.2 I2V A14B high+low noise  Q3_K_M (draft) + Q4_K_M (realism)
    text_encoders/         umt5-xxl Q5_K_M (GGUF)
    vae/                   wan_2.1_vae
    loras/                 lightx2v 4-step speed LoRAs  + YOUR Civitai LoRAs go here
  projects/<name>/
    project.json           character, style, LoRAs, shots
    refs/                  reference/start images
    audio/                 voice lines (wav/mp3) for lip sync
    shots/<id>/            results + recipe.json (exact settings to re-render)
  tools/
    shots.py               the runner (called by run_shots.bat)
    download_models.ps1    re-download/resume all models
  ComfyUI_windows_portable/  ComfyUI + its own Python 3.13 / torch 2.14 cu130
  plan.md                  research + full plan
```

## Video Studio (easiest)
Double-click **`studio.bat`**. It starts ComfyUI if needed and opens **http://127.0.0.1:8190**.

1. **Job:** type a name and click **New job** (each job = a folder in `jobs\`).
2. **Picture:** write the image prompt and click **Make picture** (~1 min). Use **Try another** until you like it.
3. **Video:** write what happens.
4. **Voice** (optional): the words, the voice (female / male / your own sample), and the lip-sync mode.
5. **Sound** (optional): auto, none, or describe it.
6. Click **Make video + voice + sound**.
   - The approved picture is reused.
   - Talking video takes ~20–35 min.
   - Silent video takes ~15–20 min.
7. **Redo voice & sound only** keeps the video and changes only the audio.

Only one job runs at a time, because there is one GPU. Keep both black windows (ComfyUI + Studio) open while working.

## Motion Control (character swap)
Open **http://127.0.0.1:8190/motion**, or click the **Motion control** tab at the top of the Studio.
It uses **Wan 2.2 Animate 14B (Mix / replacement mode)**: your character image is painted into the
driving video, keeping that video's background, camera and body motion.

1. Drag a **character picture** onto the page (or browse for one).
2. Drag a **driving video** in - one visible person - and click on them in the preview to aim the mask.
3. Write the scene prompt, choose shape and length, then **Replace character in video**.

Jobs are created for you on the first upload. If the job already has a picture or video from the main
Studio, the **Use this job's picture** / **Use this job's video** buttons copy them over in one click.

Result: `jobs\<name>\motion.mp4` (with the driving video's audio) + `motion_ref.png`.
480p, up to ~5 s per run (`frames` 77 = 5 s at 16 fps); expect 10-20 min on this laptop.
Longer source videos are trimmed to the clip length. Uses `models\unet\Wan2.2-Animate-14B-Q3_K_S.gguf`,
`models\loras\wan2.2_animate_14B_relight_lora_bf16.safetensors`, SAM2 and DWPose (auto-downloaded).
The workflow also exists in ComfyUI itself: Templates → Video → **Wan2.2 Animate**.

## Automatic checks and retries (make.bat)
`make.bat` now checks its own result and fixes problems without you:
- **ComfyUI died or crashed?** It is restarted and the failed step is retried (up to 3 times; out-of-memory is handled the same way).
- **After rendering** `tools\qa.py` checks `final.mp4`: file exists, has video and audio, speech is audible and not cut off, picture is not black or frozen, and the lip-sync step did not fail.
- **Problem found?** It re-renders automatically: attempt 2 is the fast route (new seed, LatentSync lip sync, draft preset; ~15 min), or just voice+mix (~3 min) when only the audio was wrong. Failed attempts are kept as `final_attemptN.mp4`.
- **Lip-sync score:** the log shows a correlation between the speech loudness and the mouth-area motion. A weak value only prints a WARNING (it is a heuristic, not a guarantee).
- Check any video yourself: `python_embeded\python.exe tools\qa.py jobs\my_job\final.mp4 <speech seconds>`

## One-command pipeline (for scripts)
`make.bat` does everything: **prompt → reference image → video → voice + lip sync → sound effects → `final.mp4`**.

1. Double-click `start_comfyui.bat` and leave the window open.
2. Copy `jobs\_template` to `jobs\my_video` and edit **`job.txt`**. Usually you only change these:
   - `image:` the reference picture (who, outfit, place, framing)
   - `video:` what happens (motion, camera)
   - `speech:` what they say (empty = no voice)
   - `sound:` `auto` / `none` / your own sound description
3. Run `make.bat jobs\my_video`.
4. Results in `jobs\my_video\`:
   - `final.mp4`
   - `ref.png`
   - `speech.flac`
   - `video_raw.mp4`, `video_smooth.mp4`
   - `video_lipsync.mp4`
   - `recipe.json`

Models used by default (both **uncensored**):

| step | model |
|---|---|
| image | Z-Image Turbo NSFW v2 Q8 + abliterated Qwen3-4B encoder |
| video | Wan 2.2 Remix v3.0 I2V Q4_K_M (NSFW-capable, speed LoRA built in) |
| voice | Chatterbox (default voice, or clone a 5–15 s `.wav` with `voice:`) |
| lip sync | LatentSync 1.5 (needs a visible, mostly frontal face) |
| sound | MMAudio large 44k (effects/ambience matched to the video) |

Tips:
- Changing only `video:`, `speech:` or `sound:` reuses `ref.png`, so you don't wait for a new picture. Change `seed:` for a different picture or different motion.
- `preset: draft` gives fast tests. `preset: realism` is for finals.
- For lip sync, frame the shot as a close-up or medium shot. In full-body shots the face is too small. The voice is still added, just without mouth sync.
- Keep speech to 5 s or less. Longer speech extends the video back-and-forth.

## Daily use (multi-shot projects)
1. Double-click **`start_comfyui.bat`** and leave it open. Close Brave, Epic and Unreal first to free VRAM.
2. Make a project by copying `projects/example`, putting your start image in `refs/` and editing `project.json`.
3. Test motion and seeds quickly in draft mode:
   `run_shots.bat projects\myproj --preset draft --seeds 4`
4. Pick the best seed, put it in `project.json`, then render the final:
   `run_shots.bat projects\myproj --preset realism --only s01`
5. Results go in `projects\myproj\shots\s01\`:
   - `*_raw.mp4` (16 fps)
   - `*_smooth.mp4` (RIFE, 32 fps)
   - `*_final.mp4` (lip-synced with audio, 25 fps)
   - `*_last.png` (last frame)
   - `*_recipe.json` (exact settings)
   - `*_graph.json` (drag into ComfyUI to open the exact workflow)

## Presets
| preset | model | high-noise pass | low-noise pass | ~time / 5 s @480p |
|---|---|---|---|---|
| `draft` | Q3_K_M | 2 of 4 steps, speed LoRA, CFG 1 | 2 of 4 steps, speed LoRA | ~4–6 min |
| `realism` | Q4_K_M | 8 of 16 steps, **no** speed LoRA, CFG 3.5 (natural motion and skin) | speed LoRA | ~15–22 min |

A shot with `"audio"` gets an extra ~3–5 min for LatentSync 1.5 lip sync.

To tweak a preset per project:
`"preset_overrides": {"realism": {"high": {"steps": 20, "end": 10}}}`

## Consistency rules (what keeps the character the same)
- **`character`** in project.json is added to every prompt. Describe face, hair, age, outfit and accessories exactly, and keep it the same across shots.
- **`style`** is also added to every prompt, so lighting, camera and grain stay the same.
- **Start every shot from an image.** Use a `refs/...` image of the character, or `"chain"` to continue from the previous shot's last frame. That gives seamless continuation.
- **Fixed seeds** per shot. The recipe file lets you re-render a shot exactly.
- **LoRAs** apply to all shots. List them with separate strengths for the high and low passes:
  ```json
  "loras": [
    {"file": "my_character_wan22.safetensors", "high": 1.0, "low": 1.0},
    {"file": "realism_skin_wan22_i2v.safetensors", "high": 0.0, "low": 0.7}
  ]
  ```
  Rule of thumb: motion/NSFW-concept LoRAs → mainly `high`; skin/detail/realism LoRAs → mainly `low`.
- **Best consistency** comes from training a character LoRA on 20–40 images of your character, on a rented cloud GPU, and dropping it in `models/loras`. See plan.md, Phase 3.

## Civitai LoRAs (realism / NSFW)
civitai.com → Models → filter **Base model: Wan 2.2 I2V-A14B** (or "Wan 2.2 14B"), type LoRA. Log in and enable mature content to see NSFW. Many LoRAs come as a high/low pair; put both in `models/loras`. Wan 2.1 14B LoRAs often work too, mostly on the low pass. Keep it legal: fictional adults or consenting adults only.

## Lip sync (LatentSync 1.5)
Add `"audio": "audio/line.wav"` to a shot. The runner uses the 32 fps smooth video, resamples it to 25 fps, matches the length to the audio and syncs the mouth.
- Make voice lines with any TTS. Clean, dry speech gives the best result.
- The face should be fairly frontal and visible.
- `"lips_expression": 1.5` (range 1.0–3.0) controls how strong the mouth movement is.
- 1.5 is used instead of 1.6 because 1.6 needs 18 GB VRAM. **Don't `git pull` the LatentSync node blindly:** it would restore `configs/unet/stage2_512.yaml` and switch back to 1.6. The file is renamed `.disabled-use-1.5` on purpose.

## Using the ComfyUI UI directly
Drag any `shots/*/..._graph.json` into the ComfyUI browser tab to open that exact workflow and edit it by hand.

## Troubleshooting
- **Out of memory / crash:** lower `frames` to 49, use 416×736, use `draft`, close other apps. The real fix is 32 GB RAM.
- **Very slow:** Windows is swapping (16 GB RAM). Q4 swaps more than Q3.
- **First run is slow:** RIFE and LatentSync helper models download once.



