r"""
Graphify - build a dependency graph of this project.

Nodes: batch files, Python scripts, UI pages, studio API routes, ComfyUI node
classes, custom-node packs, model files, config/binary files and data folders.
Edges: runs / imports / serves / fetch / define / uses / provides / loaded by / data / http / stops.

Usage:
  python -s tools\graphify.py                 write graph.json + print a summary
  python -s tools\graphify.py --out other.json
  python -s tools\graphify.py --open          open graph in default browser
"""
import argparse
import json
import os
import re
import sys
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
CUSTOM_NODES_DIR = os.path.join(ROOT, "ComfyUI_windows_portable", "ComfyUI", "custom_nodes")

# Base / known ComfyUI node classes used across pipelines
INITIAL_NODES = [
    "BlockifyMask", "CLIPLoaderGGUF", "CLIPTextEncode", "CLIPVisionEncode", "CLIPVisionLoader",
    "CreateVideo", "DownloadAndLoadSAM2Model", "DrawMaskOnImage", "DWPreprocessor", "GetVideoComponents",
    "GrowMask", "ImageFromBatch", "ImageScale", "KSampler", "LoadImage", "LoadVideo",
    "LoraLoaderModelOnly", "ModelSamplingSD3", "PixelPerfectResolution", "PrimitiveString",
    "Sam2Segmentation", "SaveVideo", "TrimVideoLatent", "UnetLoaderGGUF", "VAEDecode", "VAELoader",
    "WanAnimateToVideo",
]

CORE_NODES = [
    "AudioAdjustVolume", "AudioEncoderEncode", "AudioEncoderLoader", "AudioMerge",
    "BasicScheduler", "CFGGuider", "CLIPLoader", "CLIPTextEncode", "CLIPVisionEncode",
    "CLIPVisionLoader", "ConditioningZeroOut", "CreateVideo", "EmptySD3LatentImage",
    "GetVideoComponents", "ImageBatch", "ImageScale", "KSampler", "KSamplerAdvanced",
    "KSamplerSelect", "LoadAudio", "LoadImage", "LoadVideo", "LoraLoaderModelOnly",
    "ModelPatchLoader", "ModelSamplingAuraFlow", "ModelSamplingSD3", "PrimitiveString",
    "RandomNoise", "SamplerCustomAdvanced", "SaveAudio", "SaveImage", "SaveVideo",
    "TrimVideoLatent", "VAEDecode", "VAEDecodeTiled", "VAELoader", "WanAnimateToVideo",
    "WanImageToVideo", "WanInfiniteTalkToVideo",
]

BASE_PACK_NODES = {
    "ComfyUI-GGUF": [
        "CLIPLoaderGGUF", "UnetLoaderGGUF", "DualCLIPLoaderGGUF",
        "QuadrupleCLIPLoaderGGUF", "TripleCLIPLoaderGGUF", "UnetLoaderGGUFAdvanced"
    ],
    "ComfyUI-segment-anything-2": [
        "Sam2Segmentation", "DownloadAndLoadSAM2Model", "Florence2toCoordinates",
        "Sam2AutoSegmentation", "Sam2VideoSegmentation", "Sam2VideoSegmentationAddPoints"
    ],
    "comfyui_controlnet_aux": [
        "DWPreprocessor", "PixelPerfectResolution", "AIO_Preprocessor",
        "AnimeFace_SemSegPreprocessor", "CannyEdgePreprocessor", "OpenposePreprocessor"
    ],
    "ComfyUI-KJNodes": [
        "GrowMask", "ImageFromBatch", "BlockifyMask", "DrawMaskOnImage"
    ],
    "ComfyUI-Chatterbox": [
        "ChatterboxTTS"
    ],
    "ComfyUI-MMAudio": [
        "MMAudioModelLoader", "MMAudioFeatureUtilsLoader", "MMAudioSampler", "MMAudioVoCoderLoader"
    ],
    "ComfyUI-VideoHelperSuite": [
        "VHS_VideoCombine", "VHS_LoadVideoPath", "VHS_AudioToVHSAudio", "VHS_LoadAudio", "VHS_BatchManager"
    ],
    "ComfyUI-Frame-Interpolation": [
        "RIFE VFI", "FILM VFI", "GMFSS Fortuna VFI"
    ],
    "ComfyUI-LatentSyncWrapper": [
        "LatentSyncNode", "VideoLengthAdjuster"
    ],
    "videos_repo_utils": [
        "ChatterboxUnloadAll"
    ],
}

MODEL_PACK = {
    "sam2_hiera_base_plus.safetensors": "ComfyUI-segment-anything-2",
    "dw-ll_ucoco_384_bs5.torchscript.pt": "comfyui_controlnet_aux",
    "yolox_l.onnx": "comfyui_controlnet_aux",
    "mmaudio_large_44k_v2_fp16.safetensors": "ComfyUI-MMAudio",
    "mmaudio_synchformer_fp16.safetensors": "ComfyUI-MMAudio",
    "mmaudio_vae_44k_fp16.safetensors": "ComfyUI-MMAudio",
    "apple_DFN5B-CLIP-ViT-H-14-384_fp16.safetensors": "ComfyUI-MMAudio",
    "bigvgan_discriminator_optimizer.pt": "ComfyUI-MMAudio",
    "bigvgan_generator.pt": "ComfyUI-MMAudio",
    "wav2vec2-chinese-base_fp16.safetensors": "ComfyUI-LatentSyncWrapper",
    "rife49.pth": "ComfyUI-Frame-Interpolation",
}

DATA_EDGES = {
    "py:studio.py": ["jobs", "voices", "images"],
    "py:make.py": ["jobs", "voices"],
    "py:motion.py": ["jobs"],
    "py:upscale.py": ["jobs"],
    "py:pointcheck.py": ["jobs"],
    "py:shots.py": ["projects"],
    "py:sheet.py": ["projects"],
    "py:sheet_contact.py": ["projects"],
    "py:turntable.py": ["projects"],
    "py:new_idea.py": ["projects"],
    "py:image.py": ["projects"],
}

MODEL_RE = r"[A-Za-z0-9_\-\.]+\.(?:safetensors|gguf|pth|pt|onnx)"


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def scan_installed_custom_nodes():
    """Scan custom_nodes directory to dynamically discover packs and node class mappings."""
    pack_nodes = {k: list(v) for k, v in BASE_PACK_NODES.items()}
    if not os.path.isdir(CUSTOM_NODES_DIR):
        return pack_nodes

    for pack in os.listdir(CUSTOM_NODES_DIR):
        pdir = os.path.join(CUSTOM_NODES_DIR, pack)
        if os.path.isdir(pdir) and not pack.startswith("__"):
            for root, _, files in os.walk(pdir):
                for f in files:
                    if f.endswith(".py"):
                        txt = read(os.path.join(root, f))
                        m = re.search(r"NODE_CLASS_MAPPINGS\s*=\s*\{([^}]+)\}", txt)
                        if m:
                            keys = re.findall(r"[\"']([A-Za-z0-9_\- ]+)[\"']\s*:", m.group(1))
                            for k in keys:
                                if k not in pack_nodes.setdefault(pack, []):
                                    pack_nodes[pack].append(k)
    return pack_nodes


class Graph:
    def __init__(self):
        self.nodes = {}
        self.edges = set()

    def node(self, node_id, label, group):
        if node_id not in self.nodes:
            self.nodes[node_id] = {"id": node_id, "label": label, "group": group}
        return node_id

    def edge(self, a, b, kind):
        if a in self.nodes and b in self.nodes and a != b:
            self.edges.add((a, b, kind))


def build():
    g = Graph()
    bats = sorted(f for f in os.listdir(ROOT) if f.lower().endswith(".bat"))
    pys = sorted(f for f in os.listdir(TOOLS) if f.lower().endswith(".py"))
    htmls = sorted(f for f in os.listdir(TOOLS) if f.lower().endswith(".html"))

    for b in bats:
        g.node("bat:" + b, b, "entry")
    for p in pys:
        g.node("py:" + p, p, "script")
    for h in htmls:
        g.node("ui:" + h, h, "ui")

    ps1 = "download_models.ps1"
    if os.path.exists(os.path.join(TOOLS, ps1)):
        g.node("ps:" + ps1, ps1, "script")

    g.node("ext:comfy", "ComfyUI server (:8188)", "core")
    g.node("ext:studio", "Studio server (:8190)", "core")
    g.node("core:comfy", "ComfyUI core", "core")

    texts = {p: read(os.path.join(TOOLS, p)) for p in pys}
    bat_texts = {b: read(os.path.join(ROOT, b)) for b in bats}
    html_texts = {h: read(os.path.join(TOOLS, h)) for h in htmls}

    for b, t in bat_texts.items():
        for p in pys:
            if re.search(r"tools[\\/]+" + re.escape(p), t, re.I):
                g.edge("bat:" + b, "py:" + p, "runs")
        if "start_comfyui.bat" in t and b != "start_comfyui.bat":
            g.edge("bat:" + b, "bat:start_comfyui.bat", "runs")

    yaml = "extra_model_paths.yaml"
    if os.path.exists(os.path.join(ROOT, yaml)):
        g.node("cfg:" + yaml, yaml, "config")
        for b in ("start_comfyui.bat",):
            if b in bats:
                g.edge("bat:" + b, "cfg:" + yaml, "uses")

    cookies = "cookies_instagram.txt"
    if os.path.exists(os.path.join(ROOT, cookies)):
        g.node("cfg:" + cookies, cookies, "config")
        if "cookies_json_to_netscape.py" in pys:
            g.edge("py:cookies_json_to_netscape.py", "cfg:" + cookies, "uses")

    ffmpeg = os.path.join(TOOLS, "bin", "ffmpeg.exe")
    if os.path.exists(ffmpeg):
        g.node("bin:ffmpeg", "ffmpeg (tools\\bin)", "binary")
        if "start_comfyui.bat" in bats:
            g.edge("bat:start_comfyui.bat", "bin:ffmpeg", "uses")
        for p, code in texts.items():
            if re.search(r"\bffmpeg\b", code, re.I):
                g.edge("py:" + p, "bin:ffmpeg", "uses")

    if "start_comfyui.bat" in bats:
        g.edge("bat:start_comfyui.bat", "ext:comfy", "runs")
    if "studio.bat" in bats:
        g.edge("bat:studio.bat", "ext:studio", "runs")
    if "stop_all.bat" in bats:
        g.edge("bat:stop_all.bat", "ext:comfy", "stops")
        g.edge("bat:stop_all.bat", "ext:studio", "stops")

    stems = {os.path.splitext(p)[0] for p in pys}
    for p in pys:
        me = os.path.splitext(p)[0]
        for s in stems:
            if s != me and re.search(r"^\s*(?:import|from)\s+" + re.escape(s) + r"\b", texts[p], re.M):
                g.edge("py:" + p, "py:" + s + ".py", "import")

    for h in htmls:
        if h in texts.get("studio.py", ""):
            g.edge("py:studio.py", "ui:" + h, "serve")

    studio = texts.get("studio.py", "")
    routes = set(re.findall(r'u\.path\s*==\s*"([^"]+)"', studio))
    routes |= set(re.findall(r'u\.path\.startswith\(\s*"([^"]+)"', studio))
    for group in re.findall(r"u\.path\s+in\s+\(([^)]*)\)", studio):
        routes |= set(re.findall(r'"([^"]+)"', group))
    for r in sorted(routes):
        g.node("api:" + r, r, "api")
        g.edge("py:studio.py", "api:" + r, "define")

    for h in htmls:
        t = html_texts[h]
        for path in re.findall(r'(?:fetch|api)\(\s*["\']([^"\'?]+)', t):
            if path in routes:
                g.edge("ui:" + h, "api:" + path, "fetch")
        for path in re.findall(r'href="(/[^"?#]+)"', t):
            if path in routes:
                g.edge("ui:" + h, "api:" + path, "link")

    # Discover ComfyUI nodes used across scripts
    discovered_nodes = set(INITIAL_NODES)
    for p, code in texts.items():
        for m in re.findall(r"\.add\(\s*[\"']([A-Za-z0-9_\- ]+)[\"']", code):
            discovered_nodes.add(m)
        for m in re.findall(r"[\"']class_type[\"']\s*:\s*[\"']([A-Za-z0-9_\- ]+)[\"']", code):
            discovered_nodes.add(m)

    pack_nodes = scan_installed_custom_nodes()
    node_to_pack = {}
    for pack, nodes in pack_nodes.items():
        for n in nodes:
            node_to_pack[n] = pack

    used_nodes = set()
    for p, code in texts.items():
        for n in discovered_nodes:
            if re.search(r"(\b" + re.escape(n) + r"\b|[\"']" + re.escape(n) + r"[\"'])", code):
                g.node("node:" + n, n, "comfy")
                used_nodes.add(n)
                g.edge("py:" + p, "node:" + n, "uses")

    for n in used_nodes:
        if n in node_to_pack:
            pack = node_to_pack[n]
            g.node("pack:" + pack, pack, "pack")
            g.edge("pack:" + pack, "node:" + n, "provides")
        else:
            g.edge("core:comfy", "node:" + n, "provides")

    models = set()
    for p in pys:
        models |= set(re.findall(MODEL_RE, texts[p]))
    for m in sorted(models):
        g.node("model:" + m, m, "model")
        pack = "ComfyUI-GGUF" if m.lower().endswith(".gguf") else MODEL_PACK.get(m)
        if pack:
            g.node("pack:" + pack, pack, "pack")
            g.edge("model:" + m, "pack:" + pack, "loaded by")
        else:
            g.edge("model:" + m, "core:comfy", "loaded by")

    for p in pys:
        for m in models:
            if m in texts[p]:
                g.edge("py:" + p, "model:" + m, "uses")

    for p in pys:
        if "8188" in texts[p]:
            g.edge("py:" + p, "ext:comfy", "http")

    for d in ("jobs", "projects", "voices", "models", "images"):
        if os.path.isdir(os.path.join(ROOT, d)):
            g.node("dir:" + d, d + "\\", "data")
    for p, dirs in DATA_EDGES.items():
        for d in dirs:
            g.edge(p, "dir:" + d, "data")

    if os.path.exists(os.path.join(TOOLS, ps1)):
        g.edge("ps:" + ps1, "dir:models", "data")

    return g


def build_dict():
    g = build()
    nodes = list(g.nodes.values())
    edges = [{"source": a, "target": b, "kind": k} for a, b, k in sorted(g.edges)]
    groups = {}
    for n in nodes:
        groups[n["group"]] = groups.get(n["group"], 0) + 1
    return {
        "generated": int(os.path.getmtime(__file__)),
        "nodes": nodes,
        "edges": edges,
        "groups": groups,
    }


def main():
    ap = argparse.ArgumentParser(description="Generate dependency graph for the project.")
    ap.add_argument("--out", default=os.path.join(ROOT, "graph.json"), help="Output JSON path")
    ap.add_argument("--open", action="store_true", help="Open visualization in browser")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    data = build_dict()
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print(f"Saved {out}")
    print(f"{len(data['nodes'])} nodes, {len(data['edges'])} edges")
    for k, v in sorted(data["groups"].items(), key=lambda kv: -kv[1]):
        print(f"  {k:8} {v}")

    if args.open:
        url = "http://127.0.0.1:8190/graph"
        html_file = os.path.join(TOOLS, "graph.html")
        try:
            import urllib.request
            urllib.request.urlopen("http://127.0.0.1:8190/", timeout=1)
            target = url
        except Exception:
            target = "file://" + html_file.replace("\\", "/")
        print(f"Opening {target} in browser ...")
        webbrowser.open(target)


if __name__ == "__main__":
    main()
