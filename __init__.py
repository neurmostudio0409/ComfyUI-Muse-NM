"""
ComfyUI NM Muse — 靈感提示欄(Grok 官網風格)
上傳圖片 / 影片 / 音訊,在提示詞中 @tag 引用,輸出通用型別接任何模型

結構:
  config/   — 集中設定(settings.py)
  modules/  — 節點、媒體載入、@tag 解析
  web/      — 前端擴充(上傳、縮圖、@ 自動完成)
"""

# pytest 等工具可能把本檔當「頂層模組」匯入(無父套件),
# 此時相對匯入不可用,跳過 ComfyUI 節點註冊即可。
if __package__:
    from .modules.muse_nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

    print("=" * 70)
    print("🎨 ComfyUI NM Muse - 靈感提示欄 v1.0")
    print("=" * 70)
    print("📦 功能:")
    print("   ⬆ 上傳圖片 / 影片 / 音訊(多選,存 input/nm_muse/)")
    print("   🏷️ 提示詞 @tag 引用媒體(輸入 @ 自動完成、點縮圖插入)")
    print("   🔌 輸出通用型別:prompt / prompt_resolved(STRING)、")
    print("      images(IMAGE batch)、video(VIDEO)、audio(AUDIO)、media_info(JSON)")
    print("✨ 可接任何下游:LLM、圖生、影生、聲音、3D、API 套件(如 ComfyUI-Grok-NM)")
    print("=" * 70)
else:
    NODE_CLASS_MAPPINGS = {}
    NODE_DISPLAY_NAME_MAPPINGS = {}

# ComfyUI 相容性
WEB_DIRECTORY = "./web"
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']
