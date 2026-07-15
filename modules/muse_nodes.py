"""
NM Muse ComfyUI 節點
分類:
  utils/NM/Muse — NMMuseNode

設計原則:
  * 前端(web/js/muse.js)負責上傳媒體與 @tag 插入,
    狀態存在 prompt / media_json 兩個 widget 隨工作流序列化
  * 輸出一律是通用型別(STRING / IMAGE / VIDEO / AUDIO),
    可接任何下游模型節點(LLM、圖生、影生、聲音、3D、API 套件等)
  * 本節點不寫任何檔案;上傳檔由 ComfyUI 內建 /upload/image 進 input/
"""

import json

from ..config.settings import CATEGORY_PROMPT
from . import media_loader
from .prompt_utils import parse_media_json, resolve_prompt, used_media


class NMMuseNode:
    """
    ComfyUI 節點:Muse 靈感提示欄(Grok 官網風格)
    上傳圖片/影片/音訊 → 在提示詞中 @img1 / @vid1 / @aud1 引用
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "提示詞;輸入 @ 或點擊媒體縮圖插入 @tag 引用上傳的媒體",
                }),
                "media_json": ("STRING", {
                    "default": "[]",
                    "multiline": False,
                    "tooltip": "(由前端維護)已上傳媒體列表,請勿手動編輯",
                }),
            },
            "optional": {
                "only_tagged": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "開啟時只輸出提示詞中 @ 到的媒體;關閉時輸出全部上傳的媒體",
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "IMAGE", "VIDEO", "AUDIO", "STRING")
    RETURN_NAMES = ("prompt", "prompt_resolved", "images", "video", "audio", "media_info")
    FUNCTION = "compose"
    CATEGORY = CATEGORY_PROMPT

    def compose(self, prompt, media_json, only_tagged=False):
        media = parse_media_json(media_json)
        selected = used_media(prompt, media) if only_tagged else media

        images = [m for m in selected if m["kind"] == "image"]
        videos = [m for m in selected if m["kind"] == "video"]
        audios = [m for m in selected if m["kind"] == "audio"]

        image_batch = media_loader.load_image_batch(images) if images else None
        video = media_loader.load_video(videos[0]) if videos else None
        audio = media_loader.load_audio(audios[0]) if audios else None

        if len(videos) > 1:
            print(f"⚠️ 有 {len(videos)} 部影片,VIDEO 輸出只取第一部(@{videos[0]['tag']})")
        if len(audios) > 1:
            print(f"⚠️ 有 {len(audios)} 段音訊,AUDIO 輸出只取第一段(@{audios[0]['tag']})")

        resolved = resolve_prompt(prompt, media)

        media_info = json.dumps({
            "media": media,
            "selected": [m["tag"] for m in selected],
            "counts": {
                "image": len(images), "video": len(videos), "audio": len(audios),
            },
        }, ensure_ascii=False)

        print(f"🎨 Muse: {len(images)} 圖 / {len(videos)} 影片 / {len(audios)} 音訊,"
              f" 提示詞 {len(prompt)} 字元")
        return (prompt, resolved, image_batch, video, audio, media_info)


NODE_CLASS_MAPPINGS = {
    "NMMuseNode": NMMuseNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NMMuseNode": "NM Muse 靈感提示欄",
}
