"""
ComfyUI-Muse-NM 單元測試
不需要 torch / ComfyUI,可在 CI 直接跑
"""

import importlib.util
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_NAME = "comfyui_muse_nm"


def _load_package():
    if PKG_NAME in sys.modules:
        return sys.modules[PKG_NAME]
    spec = importlib.util.spec_from_file_location(
        PKG_NAME,
        os.path.join(ROOT, "__init__.py"),
        submodule_search_locations=[ROOT],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[PKG_NAME] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def pkg():
    return _load_package()


def _utils():
    return sys.modules[f"{PKG_NAME}.modules.prompt_utils"]


def _settings():
    return sys.modules[f"{PKG_NAME}.config.settings"]


MEDIA = [
    {"tag": "img1", "name": "cat.png", "subfolder": "nm_muse",
     "type": "input", "kind": "image"},
    {"tag": "img2", "name": "dog.jpg", "subfolder": "nm_muse",
     "type": "input", "kind": "image"},
    {"tag": "vid1", "name": "clip.mp4", "subfolder": "nm_muse",
     "type": "input", "kind": "video"},
    {"tag": "aud1", "name": "voice.wav", "subfolder": "nm_muse",
     "type": "input", "kind": "audio"},
    {"tag": "mdl1", "name": "chair.glb", "subfolder": "nm_muse",
     "type": "input", "kind": "model"},
]


# ----------------------------------------------------------------------
# 節點註冊
# ----------------------------------------------------------------------

def test_node_mappings(pkg):
    assert set(pkg.NODE_CLASS_MAPPINGS) == {
        "NMMuseNode", "NMMuseHubNode", "NMMuseSamplerNode",
        "NMMockImageNode", "NMMockVideoNode", "NMMockAudioNode", "NMMockTextNode"}
    assert set(pkg.NODE_DISPLAY_NAME_MAPPINGS) == set(pkg.NODE_CLASS_MAPPINGS)
    assert pkg.WEB_DIRECTORY == "./web"


def test_category_and_outputs(pkg):
    node = pkg.NODE_CLASS_MAPPINGS["NMMuseNode"]
    assert node.CATEGORY == "utils/NM/Muse"
    # 集成器 v2:五媒體對稱 + 影片拆解
    assert node.RETURN_NAMES == (
        "prompt", "prompt_resolved", "images", "first_image", "last_image",
        "video", "video_frames", "fps", "audio", "model_path", "media_info")
    assert node.RETURN_TYPES == (
        "STRING", "STRING", "IMAGE", "IMAGE", "IMAGE",
        "VIDEO", "IMAGE", "FLOAT", "AUDIO", "STRING", "STRING")
    # 不落地原則:不是 OUTPUT_NODE
    assert not getattr(node, "OUTPUT_NODE", False)


def test_input_types(pkg):
    it = pkg.NODE_CLASS_MAPPINGS["NMMuseNode"].INPUT_TYPES()
    assert "prompt" in it["required"]
    assert "media_json" in it["required"]
    assert "only_tagged" in it["optional"]
    # 集成器:五媒體輸入孔,接上游各種生成模型(LTX / WAN / CLIP / LLM…)
    assert it["optional"]["images_in"][0] == "IMAGE"
    assert it["optional"]["video_in"][0] == "VIDEO"
    assert it["optional"]["audio_in"][0] == "AUDIO"
    assert it["optional"]["model_in"][0] == "STRING"
    assert it["optional"]["model_in"][1]["forceInput"] is True
    assert it["optional"]["text_in"][0] == "STRING"
    assert it["optional"]["text_in"][1]["forceInput"] is True


def test_web_js_exists(pkg):
    assert os.path.exists(os.path.join(ROOT, "web", "js", "muse.js"))


# ----------------------------------------------------------------------
# media_json 解析
# ----------------------------------------------------------------------

def test_parse_media_json_valid(pkg):
    u = _utils()
    media = u.parse_media_json(json.dumps(MEDIA))
    assert [m["tag"] for m in media] == ["img1", "img2", "vid1", "aud1", "mdl1"]


def test_parse_media_json_garbage(pkg):
    u = _utils()
    assert u.parse_media_json("not json") == []
    assert u.parse_media_json("") == []
    assert u.parse_media_json('{"a":1}') == []
    # 缺欄位 / 錯 kind 的項目要被剔除
    bad = json.dumps([{"tag": "x"}, {"name": "y.png"},
                      {"tag": "z", "name": "z.xyz", "kind": "weird"}])
    assert u.parse_media_json(bad) == []


# ----------------------------------------------------------------------
# @tag 解析
# ----------------------------------------------------------------------

def test_find_tags(pkg):
    u = _utils()
    assert u.find_tags("把 @img1 和 @img2 合成,配上 @aud1") == ["img1", "img2", "aud1"]
    assert u.find_tags("沒有標籤") == []


def test_used_media_tagged_order(pkg):
    u = _utils()
    got = u.used_media("先 @vid1 再 @img2,@vid1 重複", MEDIA)
    assert [m["tag"] for m in got] == ["vid1", "img2"]


def test_used_media_fallback_all(pkg):
    """提示詞沒 @tag 時回傳全部媒體"""
    u = _utils()
    got = u.used_media("純文字提示", MEDIA)
    assert [m["tag"] for m in got] == ["img1", "img2", "vid1", "aud1", "mdl1"]


def test_resolve_prompt(pkg):
    u = _utils()
    out = u.resolve_prompt("把 @img1 動起來,@unknown 保留", MEDIA)
    assert "[image img1: cat.png]" in out
    assert "@unknown" in out


def test_next_tag(pkg):
    u = _utils()
    assert u.next_tag("image", ["img1", "img2"]) == "img3"
    assert u.next_tag("video", []) == "vid1"


def test_kind_of(pkg):
    s = _settings()
    assert s.kind_of("a.PNG") == "image"
    assert s.kind_of("b.mp4") == "video"
    assert s.kind_of("c.wav") == "audio"
    assert s.kind_of("chair.GLB") == "model"
    assert s.kind_of("d.txt") == ""


# ----------------------------------------------------------------------
# compose(無檔案環境:媒體載入器會略過不存在的檔案)
# ----------------------------------------------------------------------

def _out(node_result):
    """依 RETURN_NAMES 取輸出,測試不用記 index"""
    names = ("prompt", "prompt_resolved", "images", "first_image", "last_image",
             "video", "video_frames", "fps", "audio", "model_path", "media_info")
    return dict(zip(names, node_result))


def test_compose_without_files(pkg):
    node = pkg.NODE_CLASS_MAPPINGS["NMMuseNode"]()
    out = _out(node.compose("把 @img1 動起來", json.dumps(MEDIA), only_tagged=True))
    assert out["prompt"] == "把 @img1 動起來"
    assert "[image img1: cat.png]" in out["prompt_resolved"]
    # 檔案不存在 → 載入結果為 None / 空字串,但不拋例外
    assert out["images"] is None and out["video"] is None and out["audio"] is None
    assert out["first_image"] is None and out["last_image"] is None
    assert out["video_frames"] is None and out["fps"] == 0.0
    assert out["model_path"] == ""
    parsed = json.loads(out["media_info"])
    assert parsed["selected"] == ["img1"]
    assert parsed["counts"]["image"] == 1


def test_compose_text_in(pkg):
    """@text 內插;未引用則附加尾端"""
    node = pkg.NODE_CLASS_MAPPINGS["NMMuseNode"]()
    out = _out(node.compose("依據 @text 生成", "[]", text_in="一隻橘貓"))
    assert out["prompt"] == "依據 一隻橘貓 生成"
    out2 = _out(node.compose("生成圖片", "[]", text_in="一隻橘貓"))
    assert out2["prompt"] == "生成圖片\n一隻橘貓"
    parsed = json.loads(out2["media_info"])
    assert parsed["inputs_connected"]["text_in"] is True


class _FakeVideo:
    """假 VIDEO:get_components 拋錯 → 拆解須安全回退"""
    def get_components(self):
        raise RuntimeError("no av here")


def test_compose_passthrough_inputs(pkg):
    """上游輸入直通:video_in / audio_in / model_in 原樣輸出(不需 torch)"""
    node = pkg.NODE_CLASS_MAPPINGS["NMMuseNode"]()
    fake_video = _FakeVideo()
    fake_audio = {"waveform": None, "sample_rate": 24000}
    out = _out(node.compose("test", "[]", video_in=fake_video, audio_in=fake_audio,
                            model_in="D:/models/chair.glb"))
    assert out["video"] is fake_video
    assert out["audio"] is fake_audio
    assert out["model_path"] == "D:/models/chair.glb"
    # 拆解失敗要安全回退,不拋例外
    assert out["video_frames"] is None and out["fps"] == 0.0


def test_hub_clean_io(pkg):
    """Hub 輸入孔全是模型節點輸出(無 _in、無檔案路徑),輸出精簡對稱"""
    hub = pkg.NODE_CLASS_MAPPINGS["NMMuseHubNode"]
    it = hub.INPUT_TYPES()
    assert set(it["optional"]) == {"only_tagged", "images", "video", "audio", "text"}
    assert not any(k.endswith("_in") for k in it["optional"])
    assert "model_path" not in it["optional"]  # 輸入不收檔案路徑
    assert it["optional"]["images"][0] == "IMAGE"
    assert it["optional"]["video"][0] == "VIDEO"
    assert it["optional"]["audio"][0] == "AUDIO"
    assert it["optional"]["text"][1]["forceInput"] is True
    # 輸出精簡:與輸入對稱 + 上傳 3D 的 model_path + media_info
    assert hub.RETURN_NAMES == ("prompt", "images", "video", "audio",
                                "model_path", "media_info")
    assert hub.RETURN_TYPES == ("STRING", "IMAGE", "VIDEO", "AUDIO",
                                "STRING", "STRING")
    assert hub.CATEGORY == "utils/NM/Muse"
    assert not getattr(hub, "OUTPUT_NODE", False)


def test_hub_delegates_compose(pkg):
    """Hub compose 委託 NMMuseNode,行為一致"""
    hub = pkg.NODE_CLASS_MAPPINGS["NMMuseHubNode"]()
    fake_video = _FakeVideo()
    prompt, images, video, audio, model_path, info = hub.compose(
        "依據 @text 生成", "[]", video=fake_video, text="一隻橘貓")
    assert prompt == "依據 一隻橘貓 生成"
    assert video is fake_video
    assert images is None and audio is None and model_path == ""
    parsed = json.loads(info)
    assert parsed["inputs_connected"]["video_in"] is True
    assert parsed["inputs_connected"]["text_in"] is True


def test_sampler_io(pkg):
    """Sampler:模型輸入孔 image_model/video_model/audio_model + clip/vae"""
    s = pkg.NODE_CLASS_MAPPINGS["NMMuseSamplerNode"]
    it = s.INPUT_TYPES()
    assert set(it["optional"]) == {"image_model", "video_model", "audio_model",
                                   "clip", "vae"}
    assert it["optional"]["image_model"][0] == "MODEL"
    assert it["optional"]["video_model"][0] == "MODEL"
    assert it["optional"]["audio_model"][0] == "MODEL"
    assert it["optional"]["clip"][0] == "CLIP"
    assert it["optional"]["vae"][0] == "VAE"
    for k in ("prompt", "media_json", "negative_prompt", "mode", "seed",
              "steps", "cfg", "sampler_name", "scheduler", "denoise",
              "width", "height", "video_frames", "fps", "audio_seconds"):
        assert k in it["required"], k
    assert s.RETURN_NAMES == ("images", "video", "audio", "prompt", "media_info")
    assert not getattr(s, "OUTPUT_NODE", False)


def test_sampler_pick_modality(pkg):
    sm = sys.modules[f"{PKG_NAME}.modules.sampler_nodes"]
    # auto:接哪個生哪個,優先序 image > video > audio
    assert sm.pick_modality("auto", True, True, True) == "image"
    assert sm.pick_modality("auto", False, True, True) == "video"
    assert sm.pick_modality("auto", False, False, True) == "audio"
    assert sm.pick_modality("auto", False, False, False) is None
    # 指定 mode 但沒接對應模型 → None
    assert sm.pick_modality("video", False, True, False) == "video"
    assert sm.pick_modality("video", True, False, False) is None


def test_sampler_video_ratio(pkg):
    sm = sys.modules[f"{PKG_NAME}.modules.sampler_nodes"]
    assert sm.video_ratio_for("LTXV") == (32, 8)
    assert sm.video_ratio_for("Wan21") == (8, 4)
    assert sm.video_ratio_for("Wan22") == (8, 4)
    assert sm.video_ratio_for("Unknown") == (8, 4)


def test_sampler_empty_latent_shapes(pkg):
    """各家族空 latent 形狀(需 torch,CI 自動跳過)"""
    pytest.importorskip("torch")
    s = pkg.NODE_CLASS_MAPPINGS["NMMuseSamplerNode"]()

    class Wan21:
        latent_channels, latent_dimensions = 16, 3

    class LTXV:
        latent_channels, latent_dimensions = 128, 3

    class SD15:
        latent_channels, latent_dimensions = 4, 2

    class StableAudio1:
        latent_channels, latent_dimensions = 64, 1

    class FakeModel:
        def __init__(self, lf):
            self._lf = lf

        def get_model_object(self, name):
            return self._lf

    # Wan 8/4:832x480 33 幀 → [1,16,9,60,104]
    lat = s._empty_latent(FakeModel(Wan21()), "video", 832, 480, 33, 2.0)
    assert list(lat.shape) == [1, 16, 9, 60, 104]
    # LTXV 32/8:832x480 33 幀 → [1,128,5,15,26]
    lat = s._empty_latent(FakeModel(LTXV()), "video", 832, 480, 33, 2.0)
    assert list(lat.shape) == [1, 128, 5, 15, 26]
    # SD 圖片:512 → [1,4,64,64]
    lat = s._empty_latent(FakeModel(SD15()), "image", 512, 512, 33, 2.0)
    assert list(lat.shape) == [1, 4, 64, 64]
    # 音訊 1D:[1,64,L]
    lat = s._empty_latent(FakeModel(StableAudio1()), "audio", 512, 512, 33, 10.0)
    assert lat.dim() == 3 and lat.shape[1] == 64


def test_sampler_requires_model(pkg):
    """沒接模型 / 缺 clip / 缺 vae 要拋清楚的錯誤"""
    s = pkg.NODE_CLASS_MAPPINGS["NMMuseSamplerNode"]()
    kw = dict(negative_prompt="", mode="auto", seed=0, steps=1, cfg=1.0,
              sampler_name="euler", scheduler="normal", denoise=1.0,
              width=64, height=64, video_frames=9, fps=8.0, audio_seconds=2.0)
    with pytest.raises(RuntimeError, match="模型輸入沒接"):
        s.generate("t", "[]", **kw)
    with pytest.raises(RuntimeError, match="clip"):
        s.generate("t", "[]", image_model=object(), **kw)
    with pytest.raises(RuntimeError, match="vae"):
        s.generate("t", "[]", image_model=object(), clip=object(), **kw)


def test_mock_text_deterministic(pkg):
    """假 LLM:同 prompt+seed 必同輸出(純 Python,CI 可跑)"""
    node = pkg.NODE_CLASS_MAPPINGS["NMMockTextNode"]()
    a = node.generate("一隻貓", 7)[0]
    b = node.generate("一隻貓", 7)[0]
    c = node.generate("一隻貓", 8)[0]
    assert a == b
    assert "一隻貓" in a
    assert isinstance(c, str)


def test_mock_categories(pkg):
    mocks = [k for k in pkg.NODE_CLASS_MAPPINGS if k.startswith("NMMock")]
    assert len(mocks) == 4
    for k in mocks:
        assert pkg.NODE_CLASS_MAPPINGS[k].CATEGORY == "utils/NM/Muse/mock"


def test_mock_media_shapes(pkg):
    """假圖片/影片/音訊輸出形狀(需 torch,CI 自動跳過)"""
    pytest.importorskip("torch")
    m = pkg.NODE_CLASS_MAPPINGS
    imgs = m["NMMockImageNode"]().generate("t", 64, 48, 3, 0)[0]
    assert list(imgs.shape) == [3, 48, 64, 3]
    video, frames, fps = m["NMMockVideoNode"]().generate("t", 64, 48, 5, 8.0, 0)
    assert list(frames.shape) == [5, 48, 64, 3] and fps == 8.0
    audio = m["NMMockAudioNode"]().generate("t", 1.0, 24000, 0)[0]
    assert audio["sample_rate"] == 24000
    assert audio["waveform"].shape[-1] == 24000
    # 確定性:同參數重跑 tensor 完全一致
    imgs2 = m["NMMockImageNode"]().generate("t", 64, 48, 3, 0)[0]
    assert (imgs - imgs2).abs().max().item() == 0.0


def test_video_components_object(pkg):
    """get_components 正常時回傳 frames/audio/fps"""
    loader = sys.modules[f"{PKG_NAME}.modules.media_loader"]

    class Comps:
        images = "FRAMES"
        audio = {"waveform": "W", "sample_rate": 24000}
        frame_rate = 24

    class Vid:
        def get_components(self):
            return Comps()

    frames, audio, fps = loader.video_components(Vid())
    assert frames == "FRAMES"
    assert audio["sample_rate"] == 24000
    assert fps == 24.0
    assert loader.video_components(None) == (None, None, 0.0)
