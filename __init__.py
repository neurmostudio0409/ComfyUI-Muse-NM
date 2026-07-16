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
    from .modules.muse_nodes import (
        NODE_CLASS_MAPPINGS as _MUSE_NODES,
        NODE_DISPLAY_NAME_MAPPINGS as _MUSE_NAMES,
    )
    from .modules.hub_nodes import (
        NODE_CLASS_MAPPINGS as _HUB_NODES,
        NODE_DISPLAY_NAME_MAPPINGS as _HUB_NAMES,
    )

    NODE_CLASS_MAPPINGS = {**_MUSE_NODES, **_HUB_NODES}
    NODE_DISPLAY_NAME_MAPPINGS = {**_MUSE_NAMES, **_HUB_NAMES}

    # 給外部前端系統的查詢路由:列出已上傳的 Muse 媒體
    try:
        import os

        from aiohttp import web
        from server import PromptServer

        @PromptServer.instance.routes.get("/muse/media")
        async def list_muse_media(request):
            """GET /muse/media - 列出 input/nm_muse/ 的媒體(name/subfolder/type/kind)"""
            try:
                import folder_paths

                from .config.settings import UPLOAD_SUBFOLDER, kind_of
                base = os.path.join(folder_paths.get_input_directory(), UPLOAD_SUBFOLDER)
                files = []
                if os.path.isdir(base):
                    for name in sorted(os.listdir(base)):
                        kind = kind_of(name)
                        if kind:
                            files.append({
                                "name": name,
                                "subfolder": UPLOAD_SUBFOLDER,
                                "type": "input",
                                "kind": kind,
                            })
                return web.json_response({"success": True, "data": files})
            except Exception as e:
                return web.json_response({"success": False, "error": str(e)}, status=500)

        print("✅ 已註冊 API 路由: GET /muse/media")
    except Exception as e:
        print(f"⚠️ 無法註冊 API 路由(可能不在 ComfyUI 環境中): {e}")

    print("=" * 70)
    print("🎨 ComfyUI NM Muse - 靈感提示欄 / 多媒體集成器 v2.1")
    print("=" * 70)
    print("📦 節點:")
    print("   🖋️ NM Muse 靈感提示欄(NMMuseNode,維持相容)")
    print("   🔀 NM Muse 集成樞紐 Hub(NMMuseHubNode,輸入孔乾淨命名:")
    print("      images / video / audio / model_path / text)")
    print("📦 功能:")
    print("   ⬆ 上傳圖片 / 影片 / 音訊 / 3D(多選,存 input/nm_muse/)")
    print("   🏷️ 提示詞 @tag 引用媒體(輸入 @ 自動完成、點縮圖插入)")
    print("   🎬 影片拆解 video_frames / fps / 音軌,LTX / WAN 直接接")
    print("   🌐 外部前端:POST /upload/image 上傳 → GET /muse/media 查詢 →")
    print("      workflow JSON 填 media_json 送 /prompt")
    print("=" * 70)
else:
    NODE_CLASS_MAPPINGS = {}
    NODE_DISPLAY_NAME_MAPPINGS = {}

# ComfyUI 相容性
WEB_DIRECTORY = "./web"
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']
