"""
NM Muse 多圖上傳 (Multi Image)
分類:
  utils/NM/Muse — NMMuseMultiImageNode

自 ComfyUI-Grok-NM 的 GrokMultiImageNode 移植:
  * 介面(web/js/multi_image.js):Upload Images / Remove All /
    編號縮圖 / 單張 ×,上傳進 input/nm_muse/(GET /muse/media 可列出)
  * 輸出 OUTPUT_IS_LIST 跨尺寸 image list——各張保持原尺寸不合批,
    接收端需支援 list(INPUT_IS_LIST,如 GrokVideoRefsNode);
    接一般 IMAGE 孔會逐張執行(ComfyUI map-over 行為)
  * image_paths widget 可由外部前端經 API 直接填值(通道原則)
"""

from ..config.settings import CATEGORY_PROMPT
from . import media_loader


class NMMuseMultiImageNode:
    """ComfyUI 節點:多張不同尺寸圖上傳,輸出跨尺寸 image list"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_paths": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "(由前端維護)每行一個 input 目錄相對路徑;"
                               "外部系統可經 API 直接填值",
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "INT")
    RETURN_NAMES = ("image_list", "count")
    OUTPUT_IS_LIST = (True, False)
    FUNCTION = "load"
    CATEGORY = CATEGORY_PROMPT

    def load(self, image_paths):
        rels = [p.strip() for p in (image_paths or "").splitlines() if p.strip()]
        tensors = media_loader.load_image_list(rels)
        if not tensors:
            raise RuntimeError("沒有可載入的圖片:請用節點上的「Upload Images」上傳")
        print(f"🖼️ Muse 多圖上傳:載入 {len(tensors)} 張(各自原尺寸)")
        return (tensors, len(tensors))


NODE_CLASS_MAPPINGS = {
    "NMMuseMultiImageNode": NMMuseMultiImageNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NMMuseMultiImageNode": "NM Muse 多圖上傳 (Multi Image)",
}
