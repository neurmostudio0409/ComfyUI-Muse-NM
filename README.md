# ComfyUI-Muse-NM

**NM Muse 靈感提示欄** — Grok 官網風格的媒體提示輸入節點:
上傳圖片 / 影片 / 音訊,在提示詞中用 `@tag` 引用剛上傳的媒體,
輸出全部是 ComfyUI 通用型別,可以接**任何**下游模型節點。

```
┌─────────────────────────────────┐
│  NM Muse 靈感提示欄              │
│  ┌───────────────────────────┐  │      prompt ──────→ LLM / 圖生 / 影生 提示詞
│  │ 把 @img1 做成賽博龐克風,   │  │      prompt_resolved → LLM(tag 已展開)
│  │ 動作參考 @vid1             │  │      images ──────→ 圖生圖 / ControlNet / 視覺理解 / 3D
│  └───────────────────────────┘  │      video  ──────→ 影片模型 / VHS
│  [⬆ 上傳媒體]  輸入 @ 引用媒體   │      audio  ──────→ 聲音模型 / 對嘴
│  ┌────┐ ┌────┐ ┌────┐           │      media_info ──→ 自訂節點(JSON)
│  │🖼️  │ │🎬  │ │🎵  │           │
│  │img1│ │vid1│ │aud1│           │
│  └────┘ └────┘ └────┘           │
└─────────────────────────────────┘
```

## 功能

- **上傳媒體**:節點上的「⬆ 上傳媒體」按鈕,多選圖片(png/jpg/webp…)、
  影片(mp4/webm/mov…)、音訊(wav/mp3/flac…),存進 `input/nm_muse/`
- **@tag 引用**:每個媒體自動命名 `img1`、`vid1`、`aud1`…
  - 提示詞輸入 `@` 跳出自動完成選單
  - 點媒體縮圖直接插入 `@tag`
  - 縮圖右上角 × 移除媒體
- **通用輸出**(與模型無關,想接什麼接什麼):

| 輸出 | 型別 | 說明 |
|------|------|------|
| `prompt` | STRING | 原始提示詞(含 `@tag`) |
| `prompt_resolved` | STRING | `@img1` 展開為 `[image img1: cat.png]`,適合餵 LLM |
| `images` | IMAGE | 上傳圖片組成的 batch(尺寸不一以第一張為準縮放) |
| `video` | VIDEO | 第一部上傳影片(核心 VIDEO 型別,可接 Save Video / 影片模型) |
| `audio` | AUDIO | 第一段上傳音訊(`{waveform, sample_rate}`) |
| `media_info` | STRING | 完整媒體清單 JSON,供自訂節點解析 |

- **only_tagged** 開關:開啟時只輸出提示詞中 `@` 到的媒體;預設輸出全部
- **不落地原則**:本節點不寫任何檔案,上傳檔走 ComfyUI 內建 `/upload/image`
- **一鍵送出**(不用去點 ComfyUI 的 Run):
  - 節點上的「**⬆ 生成**」按鈕直接送出目前工作流
  - 提示詞欄 **Ctrl+Enter**(Mac 為 Cmd+Enter)快捷送出
  - 想「改完自動跑」可搭配 ComfyUI 內建 Auto Queue:Queue 按鈕旁選單改為
    `change` 模式,任何 widget 變動即自動排隊執行

## 搭配範例

- **ComfyUI-Grok-NM**:`prompt_resolved` → Grok Chat;`images` → Grok Vision;
  `prompt` + `images`(取第一張)→ Grok Imagine 圖生影片
- **本地模型**:`prompt` → CLIP Text Encode;`images` → IPAdapter / ControlNet
- **聲音**:`audio` → 對嘴(LatentSync 等);`prompt` → TTS 文字
- **3D**:`images` → 任何 image-to-3D 節點

## 安裝

1. 放進 `ComfyUI/custom_nodes/`,執行 `install_requirements.bat`
2. 重啟 ComfyUI,節點在 **utils/NM/Muse** 分類
3. 無需 API key、無外部服務

## 結構

```
ComfyUI-Muse-NM/
├── __init__.py            # 節點註冊 + WEB_DIRECTORY
├── config/settings.py     # 常數(副檔名、tag 規則、分類)
├── modules/
│   ├── muse_nodes.py      # NMMuseNode
│   ├── media_loader.py    # input/ 檔案 → IMAGE/VIDEO/AUDIO
│   └── prompt_utils.py    # @tag 解析(純 Python)
├── web/js/muse.js         # 前端:上傳、縮圖列、@ 自動完成
└── tests/                 # pytest(不需 torch / ComfyUI)
```

## 測試

```bash
pytest tests -v
```

GitHub Actions 於 push / PR 自動跑測試;推 `v*` tag 自動打包 zip 發 Release。
