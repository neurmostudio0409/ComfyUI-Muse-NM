"""
NM Muse Mock 假生成器
分類:
  utils/NM/Muse/mock — NMMockImageNode / NMMockVideoNode /
                       NMMockAudioNode / NMMockTextNode

用途:不接真模型、零 VRAM、免下載——輸出型別與真模型節點完全一致
(IMAGE / VIDEO / AUDIO / STRING),拿來:
  * 搭 Hub / Sampler 組範例與整合測試工作流,任何機器秒跑
  * 外部前端系統開發時的假後端(確定性輸出,同 prompt+seed 必同結果)
換真模型時直接把線改接到真節點即可,孔位不用動。
"""

import hashlib

from ..config.settings import CATEGORY_MOCK


def _hash01(*parts) -> float:
    """prompt/seed → 0~1 的確定性亂數(不用 random,重跑結果一致)"""
    digest = hashlib.md5("|".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") / 0xFFFFFFFF


def _gradient_frame(width, height, hue_a, hue_b, phase=0.0):
    """兩色漸層圖 [1,H,W,C];phase 讓影片逐幀流動"""
    import numpy as np
    import torch

    x = (np.linspace(0.0, 1.0, width)[None, :] + phase) % 1.0
    y = np.linspace(0.0, 1.0, height)[:, None]
    r = hue_a[0] * (1 - x) + hue_b[0] * x
    g = hue_a[1] * (1 - y) + hue_b[1] * y
    b = hue_a[2] * (1 - x) * (1 - y) + hue_b[2] * x * y
    arr = np.stack([r * np.ones_like(y * x), g * np.ones_like(x),
                    b], axis=-1).astype(np.float32)
    return torch.from_numpy(arr).unsqueeze(0)


def _hues(prompt, seed):
    a = (_hash01(prompt, seed, "r"), _hash01(prompt, seed, "g"),
         _hash01(prompt, seed, "b"))
    b = (_hash01(prompt, seed, "R"), _hash01(prompt, seed, "G"),
         _hash01(prompt, seed, "B"))
    return a, b


class NMMockImageNode:
    """假圖片模型:prompt+seed → 確定性漸層 IMAGE batch"""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "prompt": ("STRING", {"default": "", "multiline": True}),
            "width": ("INT", {"default": 512, "min": 16, "max": 4096, "step": 8}),
            "height": ("INT", {"default": 512, "min": 16, "max": 4096, "step": 8}),
            "batch_size": ("INT", {"default": 1, "min": 1, "max": 16}),
            "seed": ("INT", {"default": 0, "min": 0, "max": 2**31 - 1}),
        }}

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "generate"
    CATEGORY = CATEGORY_MOCK

    def generate(self, prompt, width, height, batch_size, seed):
        import torch

        a, b = _hues(prompt, seed)
        frames = [_gradient_frame(width, height, a, b, phase=i * 0.13)
                  for i in range(batch_size)]
        print(f"🎭 Mock 圖片:{batch_size} 張 {width}x{height}(hash 決定配色)")
        return (torch.cat(frames, dim=0),)


class NMMockVideoNode:
    """假影片模型:prompt+seed → 動態漸層 VIDEO + frames + fps"""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "prompt": ("STRING", {"default": "", "multiline": True}),
            "width": ("INT", {"default": 256, "min": 16, "max": 2048, "step": 8}),
            "height": ("INT", {"default": 256, "min": 16, "max": 2048, "step": 8}),
            "frames": ("INT", {"default": 25, "min": 2, "max": 512}),
            "fps": ("FLOAT", {"default": 8.0, "min": 1.0, "max": 60.0}),
            "seed": ("INT", {"default": 0, "min": 0, "max": 2**31 - 1}),
        }}

    RETURN_TYPES = ("VIDEO", "IMAGE", "FLOAT")
    RETURN_NAMES = ("video", "frames", "fps")
    FUNCTION = "generate"
    CATEGORY = CATEGORY_MOCK

    def generate(self, prompt, width, height, frames, fps, seed):
        import torch

        a, b = _hues(prompt, seed)
        batch = torch.cat(
            [_gradient_frame(width, height, a, b, phase=i / frames)
             for i in range(frames)], dim=0)

        video = None
        try:
            from fractions import Fraction

            from comfy_api.latest import InputImpl, Types
            video = InputImpl.VideoFromComponents(
                Types.VideoComponents(images=batch, audio=None,
                                      frame_rate=Fraction(fps)))
        except Exception as e:
            print(f"⚠️ 無法包 VIDEO 物件(非 ComfyUI 環境?): {e}")

        print(f"🎭 Mock 影片:{frames} 幀 {width}x{height} @ {fps}fps")
        return (video, batch, fps)


class NMMockAudioNode:
    """假音訊模型:prompt+seed → 正弦波 AUDIO(頻率 220~880Hz 由 hash 決定)"""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "prompt": ("STRING", {"default": "", "multiline": True}),
            "seconds": ("FLOAT", {"default": 3.0, "min": 0.5, "max": 120.0}),
            "sample_rate": ([44100, 24000, 16000], {"default": 44100}),
            "seed": ("INT", {"default": 0, "min": 0, "max": 2**31 - 1}),
        }}

    RETURN_TYPES = ("AUDIO",)
    RETURN_NAMES = ("audio",)
    FUNCTION = "generate"
    CATEGORY = CATEGORY_MOCK

    def generate(self, prompt, seconds, sample_rate, seed):
        import numpy as np
        import torch

        freq = 220.0 + 660.0 * _hash01(prompt, seed, "freq")
        t = np.arange(int(seconds * sample_rate)) / sample_rate
        # 加一點淡入淡出避免爆音
        wave = 0.4 * np.sin(2 * np.pi * freq * t)
        fade = min(int(0.02 * sample_rate), len(wave) // 4)
        if fade > 0:
            ramp = np.linspace(0.0, 1.0, fade)
            wave[:fade] *= ramp
            wave[-fade:] *= ramp[::-1]
        waveform = torch.from_numpy(wave.astype(np.float32))[None, None, :]
        print(f"🎭 Mock 音訊:{seconds:.1f}s @ {sample_rate}Hz,{freq:.0f}Hz 正弦波")
        return ({"waveform": waveform, "sample_rate": sample_rate},)


class NMMockTextNode:
    """假 LLM:prompt → 確定性模擬回應 STRING"""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "prompt": ("STRING", {"default": "", "multiline": True}),
            "seed": ("INT", {"default": 0, "min": 0, "max": 2**31 - 1}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "generate"
    CATEGORY = CATEGORY_MOCK

    STYLES = ["電影感運鏡,黃昏光線", "水彩筆觸,柔和色調",
              "賽博龐克霓虹,高對比", "極簡構圖,大量留白"]

    def generate(self, prompt, seed):
        style = self.STYLES[int(_hash01(prompt, seed) * len(self.STYLES))
                            % len(self.STYLES)]
        text = f"〔Mock LLM〕針對「{prompt or '(空白提示)'}」的建議:{style}。"
        print(f"🎭 Mock 文字:{text[:60]}")
        return (text,)


NODE_CLASS_MAPPINGS = {
    "NMMockImageNode": NMMockImageNode,
    "NMMockVideoNode": NMMockVideoNode,
    "NMMockAudioNode": NMMockAudioNode,
    "NMMockTextNode": NMMockTextNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NMMockImageNode": "NM Mock 圖片生成(假模型)",
    "NMMockVideoNode": "NM Mock 影片生成(假模型)",
    "NMMockAudioNode": "NM Mock 音訊生成(假模型)",
    "NMMockTextNode": "NM Mock 文字生成(假 LLM)",
}
