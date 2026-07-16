"""
NM Muse 取樣器 (Sampler)
分類:
  utils/NM/Muse — NMMuseSamplerNode

定位:這顆節點本身就是 sampler——接模型物件(MODEL)+ Muse 提示欄,
直接在節點內取樣生成:
  * image_model / video_model / audio_model(MODEL)+ clip(CLIP)+ vae(VAE)
  * mode=auto 時「接哪個生哪個」(優先序 image > video > audio)
  * 空 latent 從 model 的 latent_format 自動推導:
      latent_dimensions 2 → 圖片 [B,C,H/8,W/8]
      latent_dimensions 3 → 影片 [B,C,T,H/sr,W/sr](比例依家族對照表)
      latent_dimensions 1 → 音訊 [B,C,L](44.1kHz/2048 壓縮)
  * 上傳圖(@tag)+ denoise<1 → img2img(image 模式)
  * 輸出精簡:images / video / audio / prompt / media_info

已知限制(README 亦註明):LTX 官方流程建議搭 LTXVConditioning(frame_rate),
本節點用一般 conditioning,LTX 家族請先實測;音訊模型以 44.1kHz VAE 家族為準。
"""

import json

from ..config.settings import CATEGORY_PROMPT
from . import media_loader
from .prompt_utils import parse_media_json, resolve_prompt

# 影片家族 latent 比例對照:(空間比, 時間比)
VIDEO_LATENT_RATIOS = {
    "LTXV": (32, 8),
    "Wan": (8, 4),
    "Hunyuan": (8, 4),
    "Cosmos": (8, 8),
    "Mochi": (8, 6),
}
DEFAULT_VIDEO_RATIO = (8, 4)

MODALITY_ORDER = ("image", "video", "audio")


def pick_modality(mode: str, has_image: bool, has_video: bool, has_audio: bool):
    """決定生成模態;回傳 modality 字串或 None(純函式,可單元測試)"""
    connected = {"image": has_image, "video": has_video, "audio": has_audio}
    if mode in MODALITY_ORDER:
        return mode if connected[mode] else None
    for m in MODALITY_ORDER:  # auto:接哪個生哪個
        if connected[m]:
            return m
    return None


def video_ratio_for(latent_format_name: str):
    """依 latent_format 類名前綴找影片比例;找不到用預設 (8,4)"""
    for prefix, ratio in VIDEO_LATENT_RATIOS.items():
        if latent_format_name.startswith(prefix):
            return ratio
    return DEFAULT_VIDEO_RATIO


def _sampler_choices():
    """comfy 環境給完整清單;CI 無 comfy 時 fallback"""
    try:
        import comfy.samplers
        return (comfy.samplers.KSampler.SAMPLERS, comfy.samplers.KSampler.SCHEDULERS)
    except Exception:
        return (["euler"], ["normal"])


class NMMuseSamplerNode:
    """ComfyUI 節點:Muse 多模態取樣器(MODEL + 提示欄 → 直接生成)"""

    @classmethod
    def INPUT_TYPES(cls):
        samplers, schedulers = _sampler_choices()
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "提示詞;輸入 @ 或點擊媒體縮圖插入 @tag",
                }),
                "media_json": ("STRING", {
                    "default": "[]",
                    "multiline": False,
                    "tooltip": "(由前端維護)已上傳媒體列表;第一張上傳圖 + denoise<1 = img2img",
                }),
                "negative_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "負面提示詞",
                }),
                "mode": (["auto", "image", "video", "audio"], {
                    "default": "auto",
                    "tooltip": "auto = 接哪個模型生哪個(優先序 image > video > audio)",
                }),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2**48 - 1,
                                 "control_after_generate": True}),
                "steps": ("INT", {"default": 20, "min": 1, "max": 200}),
                "cfg": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 30.0, "step": 0.1}),
                "sampler_name": (samplers, {"default": samplers[0]}),
                "scheduler": (schedulers, {"default": schedulers[0]}),
                "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01,
                                      "tooltip": "image 模式且有上傳圖時 <1.0 = img2img"}),
                "width": ("INT", {"default": 512, "min": 64, "max": 8192, "step": 8}),
                "height": ("INT", {"default": 512, "min": 64, "max": 8192, "step": 8}),
                "video_frames": ("INT", {"default": 49, "min": 1, "max": 1024,
                                         "tooltip": "video 模式的幀數"}),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0,
                                  "tooltip": "video 模式輸出的幀率"}),
                "audio_seconds": ("FLOAT", {"default": 10.0, "min": 1.0, "max": 300.0,
                                            "tooltip": "audio 模式的長度(秒)"}),
            },
            "optional": {
                "image_model": ("MODEL", {"tooltip": "圖片模型(SD/SDXL/Flux…)"}),
                "video_model": ("MODEL", {"tooltip": "影片模型(LTX/WAN/Hunyuan…)"}),
                "audio_model": ("MODEL", {"tooltip": "音訊模型(Stable Audio 家族)"}),
                "clip": ("CLIP", {"tooltip": "文字編碼器(對應所選模型)"}),
                "vae": ("VAE", {"tooltip": "解碼器(對應所選模型)"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "VIDEO", "AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("images", "video", "audio", "prompt", "media_info")
    FUNCTION = "generate"
    CATEGORY = CATEGORY_PROMPT

    # ------------------------------------------------------------------
    def _empty_latent(self, model, modality, width, height, video_frames,
                      audio_seconds):
        import torch

        lf = model.get_model_object("latent_format")
        ch = lf.latent_channels
        dims = getattr(lf, "latent_dimensions", 2)
        name = type(lf).__name__

        if modality == "audio" or dims == 1:
            length = max(2, int(round((audio_seconds * 44100 / 2048) / 2) * 2))
            return torch.zeros([1, ch, length])
        if modality == "video" or dims == 3:
            sr, tr = video_ratio_for(name)
            t = ((video_frames - 1) // tr) + 1
            print(f"🎬 影片 latent:{name} 比例 {sr}/{tr} → [1,{ch},{t},{height//sr},{width//sr}]")
            return torch.zeros([1, ch, t, height // sr, width // sr])
        return torch.zeros([1, ch, height // 8, width // 8])

    def _encode(self, clip, text):
        import nodes as core_nodes
        return core_nodes.CLIPTextEncode().encode(clip, text)[0]

    # ------------------------------------------------------------------
    def generate(self, prompt, media_json, negative_prompt, mode, seed, steps,
                 cfg, sampler_name, scheduler, denoise, width, height,
                 video_frames, fps, audio_seconds,
                 image_model=None, video_model=None, audio_model=None,
                 clip=None, vae=None):
        modality = pick_modality(mode, image_model is not None,
                                 video_model is not None, audio_model is not None)
        if modality is None:
            raise RuntimeError(
                f"mode={mode} 但對應的模型輸入沒接。請接上 image_model / "
                "video_model / audio_model 至少一個")
        if clip is None:
            raise RuntimeError("需要 clip 輸入(文字編碼);請接對應模型的 CLIP")
        if vae is None:
            raise RuntimeError("需要 vae 輸入(解碼);請接對應模型的 VAE")

        model = {"image": image_model, "video": video_model,
                 "audio": audio_model}[modality]

        import nodes as core_nodes

        media = parse_media_json(media_json)
        resolved = resolve_prompt(prompt, media)
        positive = self._encode(clip, prompt)
        negative = self._encode(clip, negative_prompt)

        # 空 latent;image 模式且有上傳圖 + denoise<1 → img2img
        latent = None
        uploads = [m for m in media if m["kind"] == "image"]
        if modality == "image" and denoise < 1.0 and uploads:
            init = media_loader.load_image_batch(uploads[:1])
            if init is not None:
                latent = core_nodes.VAEEncode().encode(vae, init)[0]["samples"]
                print(f"🖼️ img2img:以 @{uploads[0]['tag']} 為底,denoise={denoise}")
        if latent is None:
            latent = self._empty_latent(model, modality, width, height,
                                        video_frames, audio_seconds)

        print(f"🎲 Muse Sampler:{modality} / {sampler_name}+{scheduler} / "
              f"steps={steps} cfg={cfg} seed={seed}")
        samples = core_nodes.common_ksampler(
            model, seed, steps, cfg, sampler_name, scheduler,
            positive, negative, {"samples": latent}, denoise=denoise)[0]

        images = video = audio = None
        if modality == "audio":
            decode = core_nodes.NODE_CLASS_MAPPINGS["VAEDecodeAudio"]()
            audio = decode.decode(vae, samples)[0]
            dur = audio["waveform"].shape[-1] / audio["sample_rate"]
            print(f"✅ 音訊生成完成({dur:.1f} 秒)")
        else:
            frames = core_nodes.VAEDecode().decode(vae, samples)[0]
            if modality == "video":
                images = frames
                try:
                    from fractions import Fraction

                    from comfy_api.latest import InputImpl, Types
                    video = InputImpl.VideoFromComponents(
                        Types.VideoComponents(images=frames, audio=None,
                                              frame_rate=Fraction(fps)))
                except Exception as e:
                    print(f"⚠️ 無法包 VIDEO 物件(仍可用 images 幀輸出): {e}")
                print(f"✅ 影片生成完成({frames.shape[0]} 幀 @ {fps}fps)")
            else:
                images = frames
                print(f"✅ 圖片生成完成({frames.shape[0]} 張 {frames.shape[2]}x{frames.shape[1]})")

        media_info = json.dumps({
            "modality": modality,
            "prompt_resolved": resolved,
            "seed": seed, "steps": steps, "cfg": cfg,
            "sampler": sampler_name, "scheduler": scheduler,
            "media": media,
        }, ensure_ascii=False)

        return (images, video, audio, prompt, media_info)


NODE_CLASS_MAPPINGS = {
    "NMMuseSamplerNode": NMMuseSamplerNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NMMuseSamplerNode": "NM Muse 取樣器 (Sampler)",
}
