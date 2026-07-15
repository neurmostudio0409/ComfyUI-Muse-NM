"""
ComfyUI-Muse-NM 集中設定
所有常數、節點分類都定義在這裡(本套件無外部 API,不需 .env)
"""

import os
import sys

# Windows 主控台可能是 cp950,emoji/中文輸出前先切 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ----------------------------------------------------------------------
# 路徑
# ----------------------------------------------------------------------
CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(CONFIG_DIR)

# 上傳檔案放在 ComfyUI input 目錄下的這個子資料夾(前端上傳時指定)
UPLOAD_SUBFOLDER = "nm_muse"

# ----------------------------------------------------------------------
# ComfyUI 節點分類
# ----------------------------------------------------------------------
CATEGORY_PROMPT = "utils/NM/Muse"

# ----------------------------------------------------------------------
# 媒體種類與副檔名
# ----------------------------------------------------------------------
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".avi", ".mkv"}
AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}

# @tag 前綴(依媒體種類自動編號:img1, vid1, aud1…)
TAG_PREFIXES = {"image": "img", "video": "vid", "audio": "aud"}

# 提示詞中的 tag 語法:@img1、@vid2…(前端與後端共用此規則)
TAG_PATTERN = r"@([A-Za-z][A-Za-z0-9_\-]*)"


def kind_of(filename: str) -> str:
    """依副檔名判斷媒體種類;不認得回傳空字串"""
    ext = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    return ""
