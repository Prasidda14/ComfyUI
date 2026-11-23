# AI Agent Guide: Local Video Studio

Welcome to the **Local Video Studio** codebase. This file provides onboarding guidance and operating instructions for AI coding assistants (Claude Code, Cursor, Copilot, Antigravity, ChatGPT, Codex, etc.).

---

## ⚡ Step 1: Read `graph.json` First

Before grepping or reading individual scripts, **read `graph.json` at the root of the project**:

- **[graph.json](graph.json)**: A comprehensive, pre-computed dependency graph of the entire project containing 150+ nodes and 380+ directed edges.
- It details the exact relationships between:
  - **`entry`**: Batch runners (`studio.bat`, `make.bat`, `run_shots.bat`, `graphify.bat`, `start_comfyui.bat`, `stop_all.bat`).
  - **`script`**: Core Python tools in `tools/` (`studio.py`, `make.py`, `shots.py`, `motion.py`, `image.py`, `qa.py`, `upscale.py`, etc.).
  - **`ui`**: Web frontend dashboards in `tools/` (`studio.html`, `motion.html`, `library.html`, `graph.html`).
  - **`api`**: HTTP route endpoints exposed by the Studio server on `:8190`.
  - **`comfy`**: Active ComfyUI node classes used across pipelines (59 nodes).
  - **`pack`**: Custom node packages providing those nodes (`ComfyUI-Chatterbox`, `ComfyUI-MMAudio`, `ComfyUI-VideoHelperSuite`, `ComfyUI-GGUF`, `ComfyUI-LatentSyncWrapper`, etc.).
  - **`model`**: Model weights (`.gguf`, `.safetensors`, `.pth`, `.pt`, `.onnx`) and which pack or core loads them.
  - **`binary`**: Binary tools, specifically `tools\bin\ffmpeg.exe` and which scripts invoke it.
  - **`data`**: Root storage directories (`jobs/`, `projects/`, `voices/`, `models/`, `images/`).

If you modify scripts, pipelines, or node usage, **re-sync the graph** by running:
```powershell
.\graphify.bat
# or:
python -s tools\graphify.py
```

---

## 🛠 Project Architecture & Runtime

### 1. Python Environment
All batch files and tools execute inside the portable bundled Python environment:
```
ComfyUI_windows_portable\python_embeded\python.exe -s
```
Do not invoke system-wide Python unless explicitly instructed.

### 2. Services & Ports
- **ComfyUI Server**: `http://127.0.0.1:8188` (Launched via `start_comfyui.bat`)
- **Video Studio UI**: `http://127.0.0.1:8190` (Launched via `studio.bat`)
- **Graph Visualizer**: `http://127.0.0.1:8190/graph` or `tools\graph.html`

### 3. Hardware Constraint
- Runs on a **single 8 GB GPU (RTX 4060)**.
- Only **one generation job** may run at a time.
- Memory hygiene is essential: Chatterbox voice models are unpatched via `ChatterboxUnloadAll` after TTS to ensure MMAudio has headroom.

---

## 📂 Key Pipelines

1. **Full Video Pipeline** ([make.bat](make.bat) / [tools/make.py](tools/make.py)):
   - Image -> Wan 2.1 / Wan 2.2 video generation -> Chatterbox TTS speech -> LatentSync lip sync -> MMAudio sound effects -> Final composite.
2. **Character & Shot Runner** ([run_shots.bat](run_shots.bat) / [tools/shots.py](tools/shots.py)):
   - Multi-shot rendering pipeline driven by `projects/<name>/project.json`.
3. **Motion Control & Replacement** ([tools/motion.py](tools/motion.py) / `http://127.0.0.1:8190/motion`):
   - Wan 2.2 Animate 14B character transfer onto driving videos using SAM2 segmentation and DWPose.
4. **Photoreal Still Generator** ([run_image.bat](run_image.bat) / [tools/image.py](tools/image.py)):
   - Z-Image Turbo photoreal character reference still generator.

---

## Coding Style

When writing, refactoring, or reviewing code, load the **ponytail** skill (`.agents/skills/ponytail/SKILL.md`) first and follow its Ladder of Laziness: strict YAGNI, reuse existing code, prefer stdlib/native features, and write the minimal working solution.

