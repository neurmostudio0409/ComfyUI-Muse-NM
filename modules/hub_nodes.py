"""
NM Muse 集成樞紐 (Hub)
分類:
  utils/NM/Muse — NMMuseHubNode

與 NMMuseNode 的差異:
  * 輸入孔命名乾淨(images / video / audio / model_path / text,無 _in 後綴)
    ——這些孔是接模型輸出用的,名稱要與下游輸出孔一致
  * 專為外部前端系統驅動設計:所有狀態(prompt / media_json / only_tagged)
    都是 widget,可由 /prompt API 的 workflow JSON 直接填值;
    媒體先 POST /upload/image(subfolder=nm_muse),再組 media_json
  * 運算邏輯委託 NMMuseNode.compose(單一來源);原節點維持不動,
    既有工作流不受影響
"""

from ..config.settings import CATEGORY_PROMPT
from .muse_nodes import NMMuseNode


class NMMuseHubNode:
    """
    ComfyUI 節點:Muse 集成樞紐——image / audio / video / 3D / text
    五媒體 input/output 對稱的多媒體集成器
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "提示詞;輸入 @ 或點擊媒體縮圖插入 @tag;@text 引用上游 text",
                }),
                "media_json": ("STRING", {
                    "default": "[]",
                    "multiline": False,
                    "tooltip": "已上傳媒體列表(節點前端維護;外部系統可經 API 直接填值)",
                }),
            },
            "optional": {
                "only_tagged": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "開啟時只輸出提示詞中 @ 到的媒體;關閉時輸出全部上傳的媒體",
                }),
                "images": ("IMAGE", {
                    "tooltip": "模型輸出圖片(生成結果、CLIP 前處理等),與上傳圖片合併輸出",
                }),
                "video": ("VIDEO", {
                    "tooltip": "模型輸出影片(LTX / WAN 等),優先於上傳影片",
                }),
                "audio": ("AUDIO", {
                    "tooltip": "模型輸出音訊(TTS / 音樂生成等),優先於上傳音訊",
                }),
                "model_path": ("STRING", {
                    "forceInput": True,
                    "tooltip": "3D 模型檔案路徑(image-to-3D 輸出等),優先於上傳 3D 檔",
                }),
                "text": ("STRING", {
                    "forceInput": True,
                    "tooltip": "模型輸出文字(LLM 等);提示詞中用 @text 引用,未引用則附加在尾端",
                }),
            },
        }

    RETURN_TYPES = NMMuseNode.RETURN_TYPES
    RETURN_NAMES = NMMuseNode.RETURN_NAMES
    FUNCTION = "compose"
    CATEGORY = CATEGORY_PROMPT

    def compose(self, prompt, media_json, only_tagged=False,
                images=None, video=None, audio=None, model_path=None, text=None):
        return NMMuseNode().compose(
            prompt, media_json,
            only_tagged=only_tagged,
            images_in=images,
            video_in=video,
            audio_in=audio,
            model_in=model_path,
            text_in=text,
        )


NODE_CLASS_MAPPINGS = {
    "NMMuseHubNode": NMMuseHubNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NMMuseHubNode": "NM Muse 集成樞紐 (Hub)",
}
