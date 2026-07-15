"""
提示詞 @tag 解析(純 Python,不需 torch / ComfyUI,可在 CI 直接測)
media_json 格式(前端 web/js/muse.js 寫入):
  [{"tag": "img1", "name": "cat.png", "subfolder": "nm_muse",
    "type": "input", "kind": "image"}, ...]
"""

import json
import re

from ..config.settings import TAG_PATTERN, TAG_PREFIXES

_TAG_RE = re.compile(TAG_PATTERN)


def parse_media_json(media_json: str) -> list:
    """解析前端寫入的媒體列表;格式錯誤回傳空列表(不拋例外)"""
    try:
        items = json.loads(media_json or "[]")
    except (json.JSONDecodeError, TypeError):
        print(f"⚠️ media_json 不是合法 JSON,忽略: {media_json[:80]!r}")
        return []
    if not isinstance(items, list):
        return []

    result = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if not it.get("tag") or not it.get("name"):
            continue
        if it.get("kind") not in TAG_PREFIXES:
            continue
        result.append({
            "tag": str(it["tag"]),
            "name": str(it["name"]),
            "subfolder": str(it.get("subfolder", "")),
            "type": str(it.get("type", "input")),
            "kind": it["kind"],
        })
    return result


def find_tags(prompt: str) -> list:
    """依出現順序回傳提示詞中的 @tag 名稱(不含 @,不去重)"""
    return _TAG_RE.findall(prompt or "")


def used_media(prompt: str, media: list) -> list:
    """
    回傳提示詞中實際 @ 到的媒體(依出現順序、去重);
    提示詞完全沒 @tag 時回傳全部媒體(上傳順序)。
    """
    by_tag = {m["tag"]: m for m in media}
    seen, ordered = set(), []
    for tag in find_tags(prompt):
        if tag in by_tag and tag not in seen:
            seen.add(tag)
            ordered.append(by_tag[tag])
    return ordered if ordered else list(media)


def resolve_prompt(prompt: str, media: list) -> str:
    """
    把 @tag 展開成下游 LLM 看得懂的形式:
      "@img1 換成賽博龐克風" → "[image img1: cat.png] 換成賽博龐克風"
    沒對上媒體列表的 @tag 原樣保留。
    """
    by_tag = {m["tag"]: m for m in media}

    def _sub(match):
        tag = match.group(1)
        m = by_tag.get(tag)
        if not m:
            return match.group(0)
        return f"[{m['kind']} {tag}: {m['name']}]"

    return _TAG_RE.sub(_sub, prompt or "")


def next_tag(kind: str, existing_tags: list) -> str:
    """產生同種類的下一個 tag 名稱(img1→img2…);後端保底用,平常由前端命名"""
    prefix = TAG_PREFIXES.get(kind, "med")
    n = 1
    taken = set(existing_tags)
    while f"{prefix}{n}" in taken:
        n += 1
    return f"{prefix}{n}"
