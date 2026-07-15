"""
NM Muse ComfyUI 節點
分類:
  utils/NM/Muse — NMMuseNode

設計原則:
  * 前端(web/js/muse.js)負責上傳媒體與 @tag 插入,
    狀態存在 prompt / media_json 兩個 widget 隨工作流序列化
  * 同時是「輸入樞紐」:images_in / video_in / audio_in / text_in 輸入孔
    可接上游任何模型輸出(LTX、WAN、CLIP、LLM、TTS、API 套件等),
    與上傳的媒體合流後輸出
  * 輸出一律是通用型別(STRING / IMAGE / VIDEO / AUDIO / 3D 檔案路徑),
    可接任何下游模型節點
  * 本節點不寫任何檔案;上傳檔由 ComfyUI 內建 /upload/image 進 input/
"""

import json

from ..config.settings import CATEGORY_PROMPT, TEXT_IN_TAG
from . import media_loader
from .prompt_utils import parse_media_json, resolve_prompt, used_media


class NMMuseNode:
    """
    ComfyUI 節點:Muse 靈感提示欄(Grok 官網風格)
    上傳圖片/影片/音訊/3D 模型 → 在提示詞中 @img1 / @vid1 / @aud1 / @mdl1 引用
    上游輸入(images_in/video_in/audio_in/text_in)與上傳媒體合流輸出
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "提示詞;輸入 @ 或點擊媒體縮圖插入 @tag;@text 引用上游 text_in",
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
                "images_in": ("IMAGE", {
                    "tooltip": "上游圖片(生成結果、CLIP 前處理等),與上傳圖片合併輸出",
                }),
                "video_in": ("VIDEO", {
                    "tooltip": "上游影片(LTX / WAN 等生成結果),優先於上傳影片輸出",
                }),
                "audio_in": ("AUDIO", {
                    "tooltip": "上游音訊(TTS / 音樂生成等),優先於上傳音訊輸出",
                }),
                "text_in": ("STRING", {
                    "forceInput": True,
                    "tooltip": "上游文字(LLM 輸出等);提示詞中用 @text 引用,未引用則附加在尾端",
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "IMAGE", "VIDEO", "AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("prompt", "prompt_resolved", "images", "video", "audio",
                    "model_path", "media_info")
    FUNCTION = "compose"
    CATEGORY = CATEGORY_PROMPT

    def compose(self, prompt, media_json, only_tagged=False,
                images_in=None, video_in=None, audio_in=None, text_in=None):
        media = parse_media_json(media_json)
        selected = used_media(prompt, media) if only_tagged else media

        images = [m for m in selected if m["kind"] == "image"]
        videos = [m for m in selected if m["kind"] == "video"]
        audios = [m for m in selected if m["kind"] == "audio"]
        models = [m for m in selected if m["kind"] == "model"]

        # 上傳的媒體
        image_batch = media_loader.load_image_batch(images) if images else None
        video = media_loader.load_video(videos[0]) if videos else None
        audio = media_loader.load_audio(audios[0]) if audios else None
        model_path = media_loader.existing_path(models[0]) if models else ""

        # 與上游輸入合流:圖片串接 batch;影片/音訊上游優先
        if images_in is not None:
            image_batch = (images_in if image_batch is None
                           else media_loader.concat_image_batches(images_in, image_batch))
        if video_in is not None:
            if video is not None:
                print("ℹ️ video_in 已連接,忽略上傳影片(上游優先)")
            video = video_in
        if audio_in is not None:
            if audio is not None:
                print("ℹ️ audio_in 已連接,忽略上傳音訊(上游優先)")
            audio = audio_in

        if len(videos) > 1 and video_in is None:
            print(f"⚠️ 有 {len(videos)} 部影片,VIDEO 輸出只取第一部(@{videos[0]['tag']})")
        if len(audios) > 1 and audio_in is None:
            print(f"⚠️ 有 {len(audios)} 段音訊,AUDIO 輸出只取第一段(@{audios[0]['tag']})")
        if len(models) > 1:
            print(f"⚠️ 有 {len(models)} 個 3D 模型,model_path 只取第一個(@{models[0]['tag']})")

        # 上游 text_in:提示詞中 @text 內插;沒引用就附加在尾端
        out_prompt = prompt
        if text_in:
            if f"@{TEXT_IN_TAG}" in out_prompt:
                out_prompt = out_prompt.replace(f"@{TEXT_IN_TAG}", text_in)
            else:
                out_prompt = f"{out_prompt}\n{text_in}" if out_prompt.strip() else text_in

        resolved = resolve_prompt(out_prompt, media)

        media_info = json.dumps({
            "media": media,
            "selected": [m["tag"] for m in selected],
            "model_paths": [media_loader.existing_path(m) for m in models],
            "inputs_connected": {
                "images_in": images_in is not None,
                "video_in": video_in is not None,
                "audio_in": audio_in is not None,
                "text_in": bool(text_in),
            },
            "counts": {
                "image": len(images), "video": len(videos),
                "audio": len(audios), "model": len(models),
            },
        }, ensure_ascii=False)

        print(f"🎨 Muse: {len(images)} 圖 / {len(videos)} 影片 / {len(audios)} 音訊 / "
              f"{len(models)} 3D,提示詞 {len(out_prompt)} 字元")
        return (out_prompt, resolved, image_batch, video, audio, model_path, media_info)


NODE_CLASS_MAPPINGS = {
    "NMMuseNode": NMMuseNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NMMuseNode": "NM Muse 靈感提示欄",
}
