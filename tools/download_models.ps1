# Re-downloads every model this repo uses (skips/resumes files already present).
#   powershell -ExecutionPolicy Bypass -File tools\download_models.ps1
$root = Split-Path $PSScriptRoot -Parent
$hf = 'https://huggingface.co'
$ls = "$root\ComfyUI_windows_portable\ComfyUI\custom_nodes\ComfyUI-LatentSyncWrapper\checkpoints"
$jobs = @(
  # Wan 2.2 I2V 14B - draft (Q3_K_M) and realism (Q4_K_M)
  @("$hf/QuantStack/Wan2.2-I2V-A14B-GGUF/resolve/main/HighNoise/Wan2.2-I2V-A14B-HighNoise-Q3_K_M.gguf", "$root\models\unet\Wan2.2-I2V-A14B-HighNoise-Q3_K_M.gguf"),
  @("$hf/QuantStack/Wan2.2-I2V-A14B-GGUF/resolve/main/LowNoise/Wan2.2-I2V-A14B-LowNoise-Q3_K_M.gguf", "$root\models\unet\Wan2.2-I2V-A14B-LowNoise-Q3_K_M.gguf"),
  @("$hf/QuantStack/Wan2.2-I2V-A14B-GGUF/resolve/main/HighNoise/Wan2.2-I2V-A14B-HighNoise-Q4_K_M.gguf", "$root\models\unet\Wan2.2-I2V-A14B-HighNoise-Q4_K_M.gguf"),
  @("$hf/QuantStack/Wan2.2-I2V-A14B-GGUF/resolve/main/LowNoise/Wan2.2-I2V-A14B-LowNoise-Q4_K_M.gguf", "$root\models\unet\Wan2.2-I2V-A14B-LowNoise-Q4_K_M.gguf"),
  # text encoder, VAE, 4-step speed LoRAs
  @("$hf/city96/umt5-xxl-encoder-gguf/resolve/main/umt5-xxl-encoder-Q5_K_M.gguf", "$root\models\text_encoders\umt5-xxl-encoder-Q5_K_M.gguf"),
  @("$hf/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors", "$root\models\vae\wan_2.1_vae.safetensors"),
  @("$hf/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors", "$root\models\loras\wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors"),
  @("$hf/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors", "$root\models\loras\wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors"),
  # Z-Image Turbo (photoreal stills / character refs)
  @("$hf/unsloth/Z-Image-Turbo-GGUF/resolve/main/z-image-turbo-Q6_K.gguf", "$root\models\unet\z-image-turbo-Q6_K.gguf"),
  @("$hf/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b_fp8_mixed.safetensors", "$root\models\text_encoders\qwen_3_4b_fp8_mixed.safetensors"),
  @("$hf/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors", "$root\models\vae\ae.safetensors"),
  # Z-Image uncensored: NSFW v2 finetune + abliterated text encoder
  @("$hf/lesliemore/z-image-turbo-nsfw-v2-GGUF/resolve/main/z_image_nsfw_v2-Q8_0.gguf", "$root\models\unet\z_image_nsfw_v2-Q8_0.gguf"),
  @("$hf/BennyDaBall/Qwen3-4b-Z-Image-Turbo-AbliteratedV1/resolve/main/Z-Image-AbliteratedV1.Q8_0.gguf", "$root\models\text_encoders\Z-Image-AbliteratedV1.Q8_0.gguf"),
  # Wan 2.2 Remix v3.0 I2V (uncensored finetune) Q4_K_M
  @("$hf/BigDannyPt/Wan-2.2-Remix-GGUF/resolve/main/I2V/v3.0/High/wan22RemixT2VI2V_i2vHighV30-Q4_K_M.gguf", "$root\models\unet\wan22RemixT2VI2V_i2vHighV30-Q4_K_M.gguf"),
  @("$hf/BigDannyPt/Wan-2.2-Remix-GGUF/resolve/main/I2V/v3.0/Low/wan22RemixT2VI2V_i2vLowV30-Q4_K_M.gguf", "$root\models\unet\wan22RemixT2VI2V_i2vLowV30-Q4_K_M.gguf"),
  # Remix Q3_K_M: default on 16 GB RAM machines (Q4 pair needs ~32 GB RAM to run smoothly)
  @("$hf/BigDannyPt/Wan-2.2-Remix-GGUF/resolve/main/I2V/v3.0/High/wan22RemixT2VI2V_i2vHighV30-Q3_K_M.gguf", "$root\models\unet\wan22RemixT2VI2V_i2vHighV30-Q3_K_M.gguf"),
  @("$hf/BigDannyPt/Wan-2.2-Remix-GGUF/resolve/main/I2V/v3.0/Low/wan22RemixT2VI2V_i2vLowV30-Q3_K_M.gguf", "$root\models\unet\wan22RemixT2VI2V_i2vLowV30-Q3_K_M.gguf"),
  # InfiniteTalk (audio-driven talking video, keeps the face): Wan 2.1 I2V 480p + patch + audio/vision encoders + 4-step LoRA
  @("$hf/city96/Wan2.1-I2V-14B-480P-gguf/resolve/main/wan2.1-i2v-14b-480p-Q3_K_M.gguf", "$root\models\unet\wan2.1-i2v-14b-480p-Q3_K_M.gguf"),
  @("$hf/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/model_patches/wan2.1_infiniteTalk_single_fp16.safetensors", "$root\models\model_patches\wan2.1_infiniteTalk_single_fp16.safetensors"),
  @("$hf/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors", "$root\models\clip_vision\clip_vision_h.safetensors"),
  @("$hf/Kijai/wav2vec2_safetensors/resolve/main/wav2vec2-chinese-base_fp16.safetensors", "$root\models\audio_encoders\wav2vec2-chinese-base_fp16.safetensors"),
  @("$hf/Kijai/WanVideo_comfy/resolve/main/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors", "$root\models\loras\lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"),
  # MMAudio (video -> sound effects / ambience), fp16
  @("$hf/Kijai/MMAudio_safetensors/resolve/main/mmaudio_large_44k_v2_fp16.safetensors", "$root\models\mmaudio\mmaudio_large_44k_v2_fp16.safetensors"),
  @("$hf/Kijai/MMAudio_safetensors/resolve/main/mmaudio_vae_44k_fp16.safetensors", "$root\models\mmaudio\mmaudio_vae_44k_fp16.safetensors"),
  @("$hf/Kijai/MMAudio_safetensors/resolve/main/mmaudio_synchformer_fp16.safetensors", "$root\models\mmaudio\mmaudio_synchformer_fp16.safetensors"),
  @("$hf/Kijai/MMAudio_safetensors/resolve/main/apple_DFN5B-CLIP-ViT-H-14-384_fp16.safetensors", "$root\models\mmaudio\apple_DFN5B-CLIP-ViT-H-14-384_fp16.safetensors"),
  # LatentSync 1.5 (fits 8 GB; 1.6 needs 18 GB)
  @("$hf/ByteDance/LatentSync-1.5/resolve/main/latentsync_unet.pt", "$ls\latentsync_unet.pt"),
  @("$hf/ByteDance/LatentSync-1.5/resolve/main/whisper/tiny.pt", "$ls\whisper\tiny.pt"),
  @("$hf/stabilityai/sd-vae-ft-mse/resolve/main/config.json", "$ls\vae\config.json"),
  @("$hf/stabilityai/sd-vae-ft-mse/resolve/main/diffusion_pytorch_model.safetensors", "$ls\vae\diffusion_pytorch_model.safetensors")
)
foreach ($j in $jobs) {
  New-Item -ItemType Directory -Force (Split-Path $j[1]) | Out-Null
  Write-Output "-> $($j[1])"
  & curl.exe -L --fail --retry 5 --retry-delay 5 -C - -s -S -o $j[1] $j[0]
}
Write-Output 'done'
