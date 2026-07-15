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
]


# ----------------------------------------------------------------------
# 節點註冊
# ----------------------------------------------------------------------

def test_node_mappings(pkg):
    assert set(pkg.NODE_CLASS_MAPPINGS) == {"NMMuseNode"}
    assert set(pkg.NODE_DISPLAY_NAME_MAPPINGS) == set(pkg.NODE_CLASS_MAPPINGS)
    assert pkg.WEB_DIRECTORY == "./web"


def test_category_and_outputs(pkg):
    node = pkg.NODE_CLASS_MAPPINGS["NMMuseNode"]
    assert node.CATEGORY == "utils/NM/Muse"
    assert node.RETURN_TYPES == (
        "STRING", "STRING", "IMAGE", "VIDEO", "AUDIO", "STRING")
    # 不落地原則:不是 OUTPUT_NODE
    assert not getattr(node, "OUTPUT_NODE", False)


def test_input_types(pkg):
    it = pkg.NODE_CLASS_MAPPINGS["NMMuseNode"].INPUT_TYPES()
    assert "prompt" in it["required"]
    assert "media_json" in it["required"]
    assert "only_tagged" in it["optional"]


def test_web_js_exists(pkg):
    assert os.path.exists(os.path.join(ROOT, "web", "js", "muse.js"))


# ----------------------------------------------------------------------
# media_json 解析
# ----------------------------------------------------------------------

def test_parse_media_json_valid(pkg):
    u = _utils()
    media = u.parse_media_json(json.dumps(MEDIA))
    assert [m["tag"] for m in media] == ["img1", "img2", "vid1", "aud1"]


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
    assert [m["tag"] for m in got] == ["img1", "img2", "vid1", "aud1"]


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
    assert s.kind_of("d.txt") == ""


# ----------------------------------------------------------------------
# compose(無檔案環境:媒體載入器會略過不存在的檔案)
# ----------------------------------------------------------------------

def test_compose_without_files(pkg):
    node = pkg.NODE_CLASS_MAPPINGS["NMMuseNode"]()
    prompt, resolved, images, video, audio, info = node.compose(
        "把 @img1 動起來", json.dumps(MEDIA), only_tagged=True)
    assert prompt == "把 @img1 動起來"
    assert "[image img1: cat.png]" in resolved
    # 檔案不存在 → 載入結果為 None,但不拋例外
    assert images is None and video is None and audio is None
    parsed = json.loads(info)
    assert parsed["selected"] == ["img1"]
    assert parsed["counts"]["image"] == 1
