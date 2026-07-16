"""
NM Muse ComfyUI 節點
分類:
  utils/NM/Muse — NMMuseNode

設計原則:
  * 集成器:image / audio / video / 3D / text 五種媒體 input、output 對稱,
    上傳與上游輸入合流後以通用型別輸出,接任何模型
    (LTX、WAN、CLIP、LLM、TTS、image-to-3D、API 套件等)
  * 影片會拆解成 frames(IMAGE)/ fps / 音軌,本地影片模型可直接接
    (參考 WhatDreamsCost LoadVideoUI 的輸出慣例)
  * 前端(web/js/muse.js)負責上傳媒體與 @tag 插入,
    狀態存在 prompt / media_json 兩個 widget 隨工作流序列化
  * 本節點不寫任何檔案;上傳檔由 ComfyUI 內建 /upload/image 進 input/
"""

import json

from ..config.settings import CATEGORY_PROMPT, TEXT_IN_TAG
from . import media_loader
from .prompt_utils import parse_media_json, resolve_prompt, used_media


class NMMuseNode:
    """
    ComfyUI 節點:Muse 靈感提示欄 / 多媒體集成器(Grok 官網風格)
    上傳圖片/影片/音訊/3D → @img1 / @vid1 / @aud1 / @mdl1 引用
    五媒體輸入孔與上傳合流,輸出含影片拆幀與首尾幀
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
                    "tooltip": "上游影片(LTX / WAN 等生成結果),優先於上傳影片",
                }),
                "audio_in": ("AUDIO", {
                    "tooltip": "上游音訊(TTS / 音樂生成等),優先於上傳音訊",
                }),
                "model_in": ("STRING", {
                    "forceInput": True,
                    "tooltip": "上游 3D 模型檔案路徑(image-to-3D 輸出等),優先於上傳 3D 檔",
                }),
                "text_in": ("STRING", {
                    "forceInput": True,
                    "tooltip": "上游文字(LLM 輸出等);提示詞中用 @text 引用,未引用則附加在尾端",
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "IMAGE", "IMAGE", "IMAGE",
                    "VIDEO", "IMAGE", "FLOAT", "AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("prompt", "prompt_resolved", "images", "first_image", "last_image",
                    "video", "video_frames", "fps", "audio", "model_path", "media_info")
    FUNCTION = "compose"
    CATEGORY = CATEGORY_PROMPT

    def compose(self, prompt, media_json, only_tagged=False,
                images_in=None, video_in=None, audio_in=None,
                model_in=None, text_in=None):
        media = parse_media_json(media_json)
        selected = used_media(prompt, media) if only_tagged else media

        images = [m for m in selected if m["kind"] == "image"]
        videos = [m for m in selected if m["kind"] == "video"]
        audios = [m for m in selected if m["kind"] == "audio"]
        models = [m for m in selected if m["kind"] == "model"]

        # ---- 圖片:上游 + 上傳合併 batch,另給首尾幀(FFLF 工作流)----
        image_batch = media_loader.load_image_batch(images) if images else None
        if images_in is not None:
            image_batch = (images_in if image_batch is None
                           else media_loader.concat_image_batches(images_in, image_batch))
        first_image = image_batch[:1] if image_batch is not None else None
        last_image = image_batch[-1:] if image_batch is not None else None

        # ---- 影片:上游優先;拆解 frames / fps / 音軌 ----
        video = video_in
        if video is None and videos:
            video = media_loader.load_video(videos[0])
        elif video is not None and videos:
            print("ℹ️ video_in 已連接,忽略上傳影片(上游優先)")
        video_frames, video_audio, fps = media_loader.video_components(video)

        # ---- 音訊優先鏈:audio_in > 上傳音訊 > 影片音軌 ----
        if audio_in is not None:
            audio = audio_in
        elif audios:
            audio = media_loader.load_audio(audios[0])
        else:
            audio = video_audio

        # ---- 3D:model_in 優先,否則取上傳 3D 檔 ----
        model_path = (model_in or "").strip()
        if not model_path and models:
            model_path = media_loader.existing_path(models[0])

        if len(videos) > 1 and video_in is None:
            print(f"⚠️ 有 {len(videos)} 部影片,VIDEO 輸出只取第一部(@{videos[0]['tag']})")
        if len(audios) > 1 and audio_in is None:
            print(f"⚠️ 有 {len(audios)} 段音訊,AUDIO 輸出只取第一段(@{audios[0]['tag']})")
        if len(models) > 1 and not model_in:
            print(f"⚠️ 有 {len(models)} 個 3D 模型,model_path 只取第一個(@{models[0]['tag']})")

        # ---- 上游 text_in:提示詞中 @text 內插;沒引用就附加在尾端 ----
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
            "fps": fps,
            "inputs_connected": {
                "images_in": images_in is not None,
                "video_in": video_in is not None,
                "audio_in": audio_in is not None,
                "model_in": bool(model_in),
                "text_in": bool(text_in),
            },
            "counts": {
                "image": len(images), "video": len(videos),
                "audio": len(audios), "model": len(models),
            },
        }, ensure_ascii=False)

        print(f"🎨 Muse: {len(images)} 圖 / {len(videos)} 影片 / {len(audios)} 音訊 / "
              f"{len(models)} 3D,提示詞 {len(out_prompt)} 字元"
              + (f",影片 {fps:.1f}fps" if fps else ""))
        return (out_prompt, resolved, image_batch, first_image, last_image,
                video, video_frames, fps, audio, model_path, media_info)


NODE_CLASS_MAPPINGS = {
    "NMMuseNode": NMMuseNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NMMuseNode": "NM Muse 靈感提示欄",
}
