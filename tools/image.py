"""
Photoreal stills with Z-Image Turbo (GGUF Q6_K) -> character reference / start images.

  run_image.bat projects\\example "sitting at a cafe table holding a coffee cup" --count 4
  run_image.bat projects\\example "..." --name hero --seed 7 --width 768 --height 1344

The project's `character` and `style` are added to the prompt (same as the video runner),
so stills and videos describe the same person. Results: <project>/refs/<name>_s<seed>.png
plus a matching _recipe.json. Pick the best one and use it as "image" in project.json.
"""
import argparse, json, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shots import G, run_graph, out_file  # noqa: E402


MODELS = {
    # NSFW v2 finetune + abliterated Qwen3-4B encoder (no refusals / no concept gaps)
    "uncensored": {"unet": "z_image_nsfw_v2-Q8_0.gguf", "clip": "Z-Image-AbliteratedV1.Q8_0.gguf", "clip_gguf": True},
    # original Z-Image Turbo (best general photo quality, weak on nudity)
    "base": {"unet": "z-image-turbo-Q6_K.gguf", "clip": "qwen_3_4b_fp8_mixed.safetensors", "clip_gguf": False},
}


def zimage_graph(prompt, seed, width, height, steps, prefix, model="uncensored"):
    cfg = MODELS[model]
    g = G()
    m = g.add("UnetLoaderGGUF", unet_name=cfg["unet"])
    m = g.add("ModelSamplingAuraFlow", model=[m, 0], shift=3.0)
    if cfg["clip_gguf"]:
        clip = g.add("CLIPLoaderGGUF", clip_name=cfg["clip"], type="lumina2")
    else:
        clip = g.add("CLIPLoader", clip_name=cfg["clip"], type="lumina2", device="default")
    vae = g.add("VAELoader", vae_name="ae.safetensors")
    pos = g.add("CLIPTextEncode", clip=[clip, 0], text=prompt)
    neg = g.add("ConditioningZeroOut", conditioning=[pos, 0])
    lat = g.add("EmptySD3LatentImage", width=width, height=height, batch_size=1)
    s = g.add("KSampler", model=[m, 0], positive=[pos, 0], negative=[neg, 0], latent_image=[lat, 0],
              seed=seed, steps=steps, cfg=1.0, sampler_name="res_multistep", scheduler="simple", denoise=1.0)
    img = g.add("VAEDecode", samples=[s, 0], vae=[vae, 0])
    out = g.add("SaveImage", images=[img, 0], filename_prefix=prefix)
    return g.nodes, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("action", nargs="?", default="portrait photo, upper body, looking at the camera")
    ap.add_argument("--name", default="hero")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--width", type=int, default=768)    # 768x1344 ~ same shape as 480x832 video
    ap.add_argument("--height", type=int, default=1344)
    ap.add_argument("--steps", type=int, default=9)
    ap.add_argument("--raw", action="store_true", help="use the prompt as-is (no character/style)")
    ap.add_argument("--model", choices=list(MODELS), help="default: project.json image_model, else uncensored")
    a = ap.parse_args()

    proj = os.path.abspath(a.project)
    p = json.load(open(os.path.join(proj, "project.json"), encoding="utf-8-sig"))
    model = a.model or p.get("image_model", "uncensored")
    print("model:", model)
    parts = [a.action] if a.raw else [p.get("character", ""), a.action, p.get("style", "")]
    prompt = ". ".join(x for x in parts if x)
    refs = os.path.join(proj, "refs")
    os.makedirs(refs, exist_ok=True)
    print("prompt:", prompt)

    for k in range(a.count):
        seed = a.seed + k
        tag = f"{a.name}_s{seed}"
        graph, out = zimage_graph(prompt, seed, a.width, a.height, a.steps,
                                  f"{os.path.basename(proj)}/img_{tag}", model)
        f = out_file(run_graph(graph, tag), out)
        dst = os.path.join(refs, tag + ".png")
        shutil.copy2(f, dst)
        json.dump({"model": model, "prompt": prompt, "seed": seed, "width": a.width, "height": a.height, "steps": a.steps,
                   "graph": graph}, open(os.path.join(refs, tag + "_recipe.json"), "w", encoding="utf-8"),
                  indent=1, ensure_ascii=False)
        print("  saved", dst)


if __name__ == "__main__":
    main()
