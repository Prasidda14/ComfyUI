# Character sheet

## Identity (keep this exact)

A curvy young Asian woman in her early 20s. Soft round face with full cheeks, fair smooth skin, soft glam makeup, glossy lips, dark brown almond eyes, small nose, friendly closed-mouth smile. Short black bob with thick straight bangs and side pieces framing the cheeks. Extremely large heavy bust with deep cleavage, wide hips, thick thighs, soft hourglass figure, plump curvy body. Small silver hoop earrings.

Outfit: two separate pieces - a very tight fitted light grey scoop-neck short-sleeve t-shirt with a deep neckline, tucked into a grey high-waist bodycon mini skirt with a visible waistband, bare legs.

The original still is a seated bust shot (564x1002), shot indoors against a beige wall, with a small Japanese watermark in the top-right corner. Exclude the watermark and the armchair from generated sheets.

## Files

| File | Purpose |
|------|---------|
| `assets/character/source.jpg` | original Pinterest still (pin 1126322188118496502) |
| `assets/character/character.json` | identity, outfit, style, per-view prompts |
| `assets/character/sheet_front.png` | full body, facing camera (768x1344, Z-Image, seed 401) |
| `assets/character/sheet_three_quarter.png` | 45 degrees (480x832, Wan I2V, turn_040) |
| `assets/character/sheet_side.png` | profile (480x832, Wan I2V, turn_060) |
| `assets/character/sheet_back.png` | back (480x832, Wan I2V, turn_080) |
| `assets/character/sheet_face.png` | head and shoulders close-up (768x1344, Z-Image, seed 469) |
| `assets/character/sheet_contact.jpg` | labelled 6-panel sheet (5 views + original) |
| `assets/character/turntable.mp4` | Wan I2V orbit clip, 81 frames, 480x832 |
| `assets/character/turn_*.png` | raw turntable frames at 0/20/40/60/80/100 percent |
| `assets/character/character.png` | default Animate reference (copy of the front) |
| `assets/character/_t2i_attempt/` | Z-Image side/back attempts (all front-facing, archived) |

## How the sheet is made

Two stages. Z-Image at cfg 1 does not follow camera-angle prompts: all four T2I "views" came out front-facing, so the side and back come from a Wan 2.2 I2V orbit instead.

### 1. Front and face with Z-Image

```
ComfyUI_windows_portable\python_embeded\python.exe -s -u tools\sheet.py projects\motion_asian_baddie --views front --seed 401 --model uncensored --overwrite
ComfyUI_windows_portable\python_embeded\python.exe -s -u tools\sheet.py projects\motion_asian_baddie --views face --seed 469 --model uncensored --overwrite
```

- Model: Z-Image Turbo (`uncensored`: z_image_nsfw_v2-Q8_0.gguf + Z-Image-AbliteratedV1.Q8_0.gguf)
- 768x1344, 9 steps, cfg 1.0, shift 3.0, sampler res_multistep / simple
- About 1.2 min per image on the RTX 4060 8 GB
- The base model produced a smaller bust and merged top and skirt into a dress; the uncensored model followed the outfit and body spec better.

### 2. Turnaround with Wan 2.2 I2V

```
ComfyUI_windows_portable\python_embeded\python.exe -s -u tools\turntable.py projects\motion_asian_baddie\assets\character\sheet_front.png --seed 7
```

- Prompt: slow camera orbit to the right, showing the side and then the back, subject stands still
- Graph: Wan 2.2 I2V base Q3, 480x832, 81 frames, draft preset (4 + 4 steps, cfg 1)
- About 8.2 min; frame 1 anchors identity, later frames reveal the side and back
- Extracts `turn_000/020/040/060/080/100.png`; copied 040 to three-quarter, 060 to side, 080 to back
- Re-extract without re-rendering: add `--extract-only`
- Different orbit or seed: change `--prompt` / `--seed`, rerun

### 3. Contact sheet

```
ComfyUI_windows_portable\python_embeded\python.exe -s -u tools\sheet_contact.py projects\motion_asian_baddie\assets\character
```

Output: `sheet_contact.jpg`, 3 columns, labelled, includes the original pin for comparison.

## Can Wan make the sheet itself?

- Wan 2.2 Animate: no. It consumes one reference image and a driving video. It cannot generate new views.
- Wan 2.2 I2V: yes for the turnaround, and this project uses it. Starting from a full-body front gives a full-body orbit with stable identity. Limit: 480p output and only what the start frame contains.
- Z-Image Turbo: good for the front and the face; unreliable for side/back at cfg 1.
- Identity-locked editing (Qwen-Image-Edit, Flux Kontext, IPAdapter) is not installed and is heavy for 8 GB. Revisit only if likeness is not close enough.

This is the recommended recipe: Z-Image front and face, Wan I2V turnaround, pick and crop, then Animate.

## Known gaps

- Likeness is close but not exact. The generated bust is large but still smaller than the pin; pushing the prompt further makes it cartoonish.
- Turntable views are 480x832. That matches Animate's working resolution, but do not use them as 720p beauty shots.
- The back view has slight fabric shimmer. Acceptable for reference.
- Feet are bare. Add shoes per clip if the driving video has them.
- Small hoop earrings can flicker in Animate; remove them if they do.

## Picking the reference for Animate

1. Open the driving clip's first frame next to the sheet.
2. Choose the view with the closest pose, shoulder angle, and framing.
3. Crop to the clip's aspect ratio (9:16 for phone clips) and keep head to toe if the motion is full body.
4. No watermark, plain background, arms and legs not touching the body.
5. Remove the earrings if they flicker; small jewelry is a common artifact source.
6. Save as `videos\<idea>\assets\character.png`.

Reference-to-first-frame match is the largest single quality factor in Wan Animate. A perfect character design in the wrong pose will still render poorly.
