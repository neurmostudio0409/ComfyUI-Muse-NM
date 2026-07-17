"""
從 ComfyUI input 目錄載入上傳的媒體
torch / PIL / torchaudio 延遲匯入,讓 CI(無 torch 環境)也能載入本模組
"""

import os

from ..config.settings import PLUGIN_DIR


def _input_dir() -> str:
    try:
        import folder_paths
        return folder_paths.get_input_directory()
    except Exception:
        return os.path.join(PLUGIN_DIR, "input")


def media_path(item: dict) -> str:
    """media_json 項目 → 實際檔案路徑"""
    base = _input_dir()
    if item.get("subfolder"):
        base = os.path.join(base, item["subfolder"])
    return os.path.join(base, item["name"])


def load_image_list(rel_paths: list) -> list:
    """
    input 目錄相對路徑列表 → tensor list(各自尺寸,不合批不縮放)。
    找不到的檔案略過並警告;先確認有檔案才 import torch(CI 無 torch 安全)。
    """
    base = _input_dir()
    paths = []
    for rel in rel_paths:
        path = rel if os.path.isabs(rel) else os.path.join(base, rel)
        if os.path.exists(path):
            paths.append(path)
        else:
            print(f"⚠️ 找不到圖片 {path},略過")
    if not paths:
        return []

    try:
        import numpy as np
        import torch
        from PIL import Image, ImageOps
    except ImportError as e:
        print(f"⚠️ 缺少 torch/PIL,無法載入圖片: {e}")
        return []

    tensors = []
    for path in paths:
        pil = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        arr = np.asarray(pil).astype(np.float32) / 255.0
        tensors.append(torch.from_numpy(arr).unsqueeze(0))
    return tensors


def existing_path(item: dict) -> str:
    """media_json 項目 → 存在的檔案路徑;不存在回傳空字串(3D 模型等直接給路徑)"""
    path = media_path(item)
    if os.path.exists(path):
        return path
    print(f"⚠️ 找不到檔案 {path}")
    return ""


def concat_image_batches(a, b):
    """兩個 IMAGE batch 串接;尺寸不同時把 b 縮放成 a 的尺寸"""
    import numpy as np
    import torch
    from PIL import Image

    if a.shape[1:3] != b.shape[1:3]:
        h, w = a.shape[1], a.shape[2]
        resized = []
        for i in range(b.shape[0]):
            arr = (b[i].cpu().numpy() * 255.0).astype("uint8")
            pil = Image.fromarray(arr).resize((w, h), Image.LANCZOS)
            resized.append(torch.from_numpy(
                (np.asarray(pil).astype(np.float32) / 255.0)).unsqueeze(0))
        b = torch.cat(resized, dim=0)
    return torch.cat([a.cpu(), b.cpu()], dim=0)


# ----------------------------------------------------------------------
# 圖片 → IMAGE batch
# ----------------------------------------------------------------------
def load_image_tensor(path: str):
    """單張圖 → [1,H,W,C] float tensor"""
    import numpy as np
    import torch
    from PIL import Image

    pil = Image.open(path).convert("RGB")
    arr = np.asarray(pil).astype(np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)


def load_image_batch(items: list):
    """
    多張圖組成 IMAGE batch;尺寸不一時以第一張為準縮放。
    沒有任何可載入的檔案回傳 None——先確認再 import torch,
    讓無 torch 環境(CI)也能安全走空路徑。
    """
    paths = []
    for it in items:
        path = media_path(it)
        if os.path.exists(path):
            paths.append(path)
        else:
            print(f"⚠️ 找不到圖片 {path},略過")
    if not paths:
        return None

    try:
        import numpy as np
        import torch
        from PIL import Image
    except ImportError as e:
        print(f"⚠️ 缺少 torch/PIL,無法載入圖片: {e}")
        return None

    tensors = [load_image_tensor(p) for p in paths]

    h, w = tensors[0].shape[1], tensors[0].shape[2]
    aligned = []
    for t in tensors:
        if t.shape[1] != h or t.shape[2] != w:
            arr = (t[0].numpy() * 255.0).astype("uint8")
            pil = Image.fromarray(arr).resize((w, h), Image.LANCZOS)
            t = torch.from_numpy(
                (np.asarray(pil).astype(np.float32) / 255.0)).unsqueeze(0)
        aligned.append(t)
    return torch.cat(aligned, dim=0)


# ----------------------------------------------------------------------
# 影片 → VIDEO(ComfyUI 核心型別)
# ----------------------------------------------------------------------
def load_video(item: dict):
    """包成 VIDEO 型別;不在 ComfyUI 環境回傳 None"""
    path = media_path(item)
    if not os.path.exists(path):
        print(f"⚠️ 找不到影片 {path}")
        return None
    try:
        from comfy_api.latest import InputImpl
        return InputImpl.VideoFromFile(path)
    except Exception:
        pass
    try:  # 舊版 ComfyUI 路徑
        from comfy_api.input_impl import VideoFromFile
        return VideoFromFile(path)
    except Exception as e:
        print(f"⚠️ 無法建立 VIDEO 物件(非 ComfyUI 環境?): {e}")
        return None


def video_components(video):
    """
    VIDEO 物件拆解成 (frames IMAGE, audio dict|None, fps float)。
    LTX / WAN 等本地模型吃幀序列,不吃 VIDEO 物件(參考 WhatDreamsCost LoadVideoUI)。
    拆解失敗回傳 (None, None, 0.0),不拋例外。
    """
    if video is None:
        return None, None, 0.0
    try:
        comps = video.get_components()
        frames = comps.images
        audio = comps.audio if comps.audio and comps.audio.get("waveform") is not None else None
        fps = float(comps.frame_rate) if comps.frame_rate else 0.0
        return frames, audio, fps
    except Exception as e:
        print(f"⚠️ 影片拆解失敗(video_frames/fps 輸出為空): {e}")
        return None, None, 0.0


# ----------------------------------------------------------------------
# 音訊 → AUDIO dict
# ----------------------------------------------------------------------
def load_audio(item: dict):
    """載入為 AUDIO dict {waveform:[B,C,S], sample_rate};失敗回傳 None"""
    path = media_path(item)
    if not os.path.exists(path):
        print(f"⚠️ 找不到音訊 {path}")
        return None

    try:
        import torchaudio
        waveform, sample_rate = torchaudio.load(path)
        return {"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate}
    except Exception as e:
        print(f"⚠️ torchaudio 解碼失敗,改用 wave 保底: {e}")

    if not path.lower().endswith(".wav"):
        print("❌ 非 WAV 且 torchaudio 不可用,無法載入音訊")
        return None

    import wave

    try:
        import numpy as np
        import torch
    except ImportError as e:
        print(f"⚠️ 缺少 torch,無法載入音訊: {e}")
        return None

    with wave.open(path, "rb") as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())

    if width == 2:
        arr = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 4:
        arr = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        print(f"❌ 不支援的 WAV 位寬: {width * 8} bit")
        return None

    arr = arr.reshape(-1, channels).T  # [C, S]
    waveform = torch.from_numpy(arr.copy()).unsqueeze(0)  # [1, C, S]
    return {"waveform": waveform, "sample_rate": sample_rate}
