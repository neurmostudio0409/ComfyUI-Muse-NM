# ComfyUI-Muse-NM

**NM Muse 靈感提示欄** — Grok 官網風格的**多媒體集成器**:
image / audio / video / 3D / text 五種媒體 **input、output 對稱**,
上傳 + 上游輸入合流,在提示詞中用 `@tag` 引用媒體,
輸出全部是 ComfyUI 通用型別,可以接**任何**上下游模型節點
(LTX、WAN、CLIP、LLM、TTS、image-to-3D、API 套件…)。

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
  影片(mp4/webm/mov…)、音訊(wav/mp3/flac…)、3D 模型(glb/obj/fbx/stl…),
  存進 `input/nm_muse/`
- **輸入樞紐**:`images_in` / `video_in` / `audio_in` / `text_in` 輸入孔,
  接 LTX、WAN(API)、CLIP、LLM、TTS 等任何上游輸出——圖片與上傳圖合併成
  batch;影片/音訊上游優先;`text_in` 在提示詞用 `@text` 內插,未引用則附加尾端
- **@tag 引用**:每個媒體自動命名 `img1`、`vid1`、`aud1`…
  - 提示詞輸入 `@` 跳出自動完成選單
  - 點媒體縮圖直接插入 `@tag`
  - 縮圖右上角 × 移除媒體
- **通用輸出**(與模型無關,想接什麼接什麼):

| 輸出 | 型別 | 說明 |
|------|------|------|
| `prompt` | STRING | 提示詞(含 `@tag`;`@text` 已替換為 `text_in` 內容) |
| `prompt_resolved` | STRING | `@img1` 展開為 `[image img1: cat.png]`,適合餵 LLM |
| `images` | IMAGE | `images_in` + 上傳圖片合併 batch(尺寸不一以第一張為準縮放) |
| `first_image` / `last_image` | IMAGE | 合併 batch 的首/尾幀(LTX FFLF 首尾幀工作流直接接) |
| `video` | VIDEO | `video_in` 優先,否則第一部上傳影片(接 Save Video 等) |
| `video_frames` | IMAGE | 影片拆幀(LTX / WAN 等本地模型吃幀序列,直接接這裡) |
| `fps` | FLOAT | 影片幀率(接影片重組節點) |
| `audio` | AUDIO | 優先鏈:`audio_in` > 上傳音訊 > **影片音軌** |
| `model_path` | STRING | `model_in` 優先,否則第一個上傳 3D 模型的路徑 |
| `media_info` | STRING | 完整媒體清單 JSON(含 `model_paths`、`fps`、輸入連接狀態) |

## 兩顆節點

| 節點 | 輸入孔 | 輸出孔 | 用途 |
|------|--------|--------|------|
| **NM Muse 集成樞紐 (Hub)**(建議) | `images` / `video` / `audio` / `text`——全部接**模型節點輸出**,不收檔案路徑 | `prompt` / `images` / `video` / `audio` / `model_path` / `media_info`(精簡對稱) | 集成器 |
| NM Muse 靈感提示欄 | `*_in` 舊命名 | 11 孔完整版(含 `video_frames` / `fps` / 首尾幀) | 進階拆解 / 既有工作流 |

原則:**檔案一律走上傳(media_json),模型輸出一律走節點孔**,兩者不混。
兩顆共用同一套工具列(上傳 / @tag / ⬆生成),運算邏輯單一來源
(Hub 委託靈感提示欄的 compose)。

## 外部前端系統整合(API 驅動)

1. `POST /upload/image`(multipart:`image`=檔案、`subfolder=nm_muse`、`type=input`)上傳媒體
2. `GET /muse/media` 列出已上傳媒體(`name` / `subfolder` / `type` / `kind`)
3. 組 `media_json`(`[{"tag":"img1","name":"...","subfolder":"nm_muse","type":"input","kind":"image"}]`)
   與 `prompt` 填入 workflow JSON 的 Hub 節點 widget,`POST /prompt` 送出
4. 所有節點狀態都是 widget,外部系統可完全繞過 ComfyUI 前端操作

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
