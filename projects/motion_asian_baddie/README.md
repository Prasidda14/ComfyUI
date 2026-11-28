# motion_asian_baddie

One fixed character, many short driving clips, rendered with Wan 2.2 Animate (Mix / replacement mode).

- Character source: `assets/character/source.jpg` (Pinterest pin 1126322188118496502)
- Identity spec (prompt source of truth): `assets/character/character.json`
- Character sheet + picked reference: `assets/character/`
- Character notes and method: `character_sheet.md`
- Runner: `tools/motion.py` (UI: http://127.0.0.1:8190/motion)
- Tooling: `tools/sheet.py` (Z-Image front/face), `tools/turntable.py` (Wan I2V turnaround),
  `tools/sheet_contact.py` (labelled contact sheet), `tools/new_idea.py` (scaffold an idea)

## Folder map

```
projects/motion_asian_baddie/
  README.md                  this file: index, rules, lifecycle
  character_sheet.md         identity spec, how the sheet is made, how to pick the Animate reference
  assets/
    character/
      source.jpg             the original still
      character.json         identity / outfit / view prompts
      character.md           human notes
      character.png          default Animate reference (copy of the front view)
      sheet_front.png        768x1344, Z-Image
      sheet_face.png         768x1344, Z-Image
      sheet_three_quarter.png 480x832, Wan I2V turntable (turn_040)
      sheet_side.png         480x832, Wan I2V turntable (turn_060)
      sheet_back.png         480x832, Wan I2V turntable (turn_080)
      sheet_contact.jpg      labelled 6-panel sheet (5 views + original)
      turntable.mp4          Wan I2V orbit clip used for the views
      turn_*.png             raw turntable frames at 0/20/40/60/80/100 percent
      _t2i_attempt/          Z-Image side/back attempts (all came out front, archived)
  videos/
    _template/               copy this for a new idea (or use tools/new_idea.py)
    01_ig_ddq0/
      README.md              one-screen summary: source, status, render settings, output
      research.md            what we learned about the clip, motion breakdown, decisions
      todo.md                checklist
      how_to_work.md         exact steps and commands for this video
      assets/                drive_original.mp4, drive.mp4, character.png, notes
```

## Video index

| # | Idea folder | Source | Status | Output |
|---|-------------|--------|--------|--------|
| 01 | `videos/01_ig_ddq0` | Instagram `Ddq0_NrBk-E` (login wall, not downloaded) | character ready, blocked on source | - |

Completed pipeline test outside this project (different character): `jobs/pin_swap/motion.mp4`, 480x832, 4.81 s.

## Lifecycle for every video

1. Create the folder: `python -s -u tools\new_idea.py motion_asian_baddie "short title"` (or copy `videos\_template`).
2. Research the source: duration, fps, framing, camera, motion, light, occlusions. Fill `research.md`.
3. Put `drive_original.mp4` and the chosen `character.png` in the idea's `assets/`.
4. Normalize the source to 16 fps (see `how_to_work.md`). Animate samples frames as 16 fps; a 30 fps source plays ~2x slow.
5. Render in place:
   `ComfyUI_windows_portable\python_embeded\python.exe -s -u tools\motion.py "projects\motion_asian_baddie\videos\01_ig_ddq0"`
   or use the UI, which renders into `jobs\<name>`.
6. QA the result (face, hands, mask edges, background, identity). Record findings.
7. Update the idea README, `todo.md`, and the table above.

## Defaults

| Setting | Value | Why |
|---------|-------|-----|
| Resolution | 480x832 | 14B Q3 on 8 GB VRAM |
| Frames | 49-77 (1 + 4k) | hard single-chunk limit, 77 = 4.8 s at 16 fps |
| Steps | 6, cfg 1.0 | relight LoRA + LightX2V distill |
| Seed | fixed per shot | reproducibility |
| Aim point | 0.50 / 0.55 | subject center, slightly below the face |
| Relight | 1 | match source lighting |
| Source fps | 16 | output fps |

Reference time on the RTX 4060 8 GB: 480x832 / 77 frames / 6 steps = about 31 minutes including pose + mask preprocessing.

## Rules

- One idea = one folder. Nothing loose at project root except this file, `character_sheet.md`, and `assets/`.
- The multi-view sheet is a design library. Feed Animate exactly ONE view, chosen to match the driving clip's first frame.
- Keep source clips at or below 77 frames until chunked long-video support lands.
- One person per pass. Multi-person clips need separate passes and masks (planned).
- Never use arbitrary Wan 2.2 LoRAs with Animate; the LightX2V distill and the relight LoRA are the supported pair.
