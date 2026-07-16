// NM Muse 靈感提示欄 — 前端擴充
// 功能:上傳圖片/影片/音訊、媒體縮圖列、@tag 自動完成、點縮圖插入 @tag
// 狀態存在 prompt / media_json 兩個 widget,隨工作流序列化

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

// 共用同一套工具列:靈感提示欄 + 集成樞紐 Hub + 取樣器 Sampler
const NODE_CLASSES = new Set(["NMMuseNode", "NMMuseHubNode", "NMMuseSamplerNode"]);
const UPLOAD_SUBFOLDER = "nm_muse";

const IMAGE_EXTS = ["png", "jpg", "jpeg", "webp", "bmp", "gif", "tiff"];
const VIDEO_EXTS = ["mp4", "webm", "mov", "avi", "mkv"];
const AUDIO_EXTS = ["wav", "mp3", "flac", "ogg", "m4a"];
const MODEL3D_EXTS = ["glb", "gltf", "obj", "fbx", "stl", "ply", "usdz"];
const ACCEPT = [...IMAGE_EXTS, ...VIDEO_EXTS, ...AUDIO_EXTS, ...MODEL3D_EXTS]
    .map((e) => "." + e).join(",");
const TAG_PREFIX = { image: "img", video: "vid", audio: "aud", model: "mdl" };
const KIND_ICON = { image: "🖼️", video: "🎬", audio: "🎵", model: "🧊" };

function kindOf(name) {
    const ext = (name.split(".").pop() || "").toLowerCase();
    if (IMAGE_EXTS.includes(ext)) return "image";
    if (VIDEO_EXTS.includes(ext)) return "video";
    if (AUDIO_EXTS.includes(ext)) return "audio";
    if (MODEL3D_EXTS.includes(ext)) return "model";
    return "";
}

function nextTag(kind, media) {
    const prefix = TAG_PREFIX[kind] || "med";
    const taken = new Set(media.map((m) => m.tag));
    let n = 1;
    while (taken.has(`${prefix}${n}`)) n++;
    return `${prefix}${n}`;
}

app.registerExtension({
    name: "NM.Muse",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!NODE_CLASSES.has(nodeData.name)) return;
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated?.apply(this, arguments);
            setupMuse(this);
            return r;
        };
    },
});

function setupMuse(node) {
    // 注意:新版前端會在節點建立後把 widget 物件換成 reactive 版,
    // 不能在這裡快取 widget 參照,每次都要從 node.widgets 重新解析。
    const wPrompt = () => node.widgets?.find((w) => w.name === "prompt");
    const wMedia = () => node.widgets?.find((w) => w.name === "media_json");
    if (!wPrompt() || !wMedia()) return;

    // media_json 由前端維護。注意:不能用 computeSize=[0,-4] 這類 hack 隱藏,
    // 新版前端會因此重建 widget 並把值打回預設,改用官方 hidden 旗標(失敗就不隱藏)。
    try {
        const w = wMedia();
        if (w && "hidden" in w) w.hidden = true;
    } catch { /* 隱藏失敗不影響功能 */ }

    const getMedia = () => {
        try {
            const v = JSON.parse(wMedia()?.value || "[]");
            return Array.isArray(v) ? v : [];
        } catch {
            return [];
        }
    };
    const setMedia = (media) => {
        const w = wMedia();
        if (w) w.value = JSON.stringify(media);
        renderChips();
        node.setDirtyCanvas(true, true);
    };

    // ------------------------------------------------------------------
    // DOM widget:工具列 + 縮圖列
    // ------------------------------------------------------------------
    const container = document.createElement("div");
    container.style.cssText =
        "display:flex;flex-direction:column;gap:6px;padding:4px 2px;width:100%;";

    const toolbar = document.createElement("div");
    toolbar.style.cssText = "display:flex;align-items:center;gap:6px;";

    const uploadBtn = document.createElement("button");
    uploadBtn.textContent = "⬆ 上傳媒體";
    uploadBtn.title = "上傳圖片 / 影片 / 音訊(可多選)";
    uploadBtn.style.cssText =
        "flex:0 0 auto;padding:5px 12px;border-radius:12px;border:1px solid var(--border-color,#555);" +
        "background:var(--comfy-input-bg,#333);color:var(--input-text,#ddd);cursor:pointer;font-size:12px;";

    const hint = document.createElement("span");
    hint.textContent = "輸入 @ 或點縮圖引用媒體";
    hint.style.cssText = "font-size:11px;opacity:.55;";

    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.multiple = true;
    fileInput.accept = ACCEPT;
    fileInput.style.display = "none";

    // 「⬆ 生成」:免去點 ComfyUI Run 的動作,打完字直接送出(grok.com 體感)
    const sendBtn = document.createElement("button");
    sendBtn.textContent = "⬆ 生成";
    sendBtn.title = "送出目前工作流(Ctrl+Enter)";
    sendBtn.style.cssText =
        "flex:0 0 auto;margin-left:auto;padding:5px 14px;border-radius:12px;border:none;" +
        "background:#4a7dff;color:#fff;cursor:pointer;font-size:12px;font-weight:600;";
    sendBtn.onclick = () => queueNow();

    async function queueNow() {
        sendBtn.disabled = true;
        sendBtn.textContent = "⏳ 排隊中…";
        try {
            await app.queuePrompt(0);
        } catch (e) {
            alert(`送出失敗:${e}`);
        } finally {
            sendBtn.disabled = false;
            sendBtn.textContent = "⬆ 生成";
        }
    }

    toolbar.append(uploadBtn, hint, sendBtn, fileInput);

    const chips = document.createElement("div");
    chips.style.cssText =
        "display:flex;flex-wrap:wrap;gap:6px;min-height:0;align-items:center;";

    container.append(toolbar, chips);
    node.addDOMWidget("muse_toolbox", "div", container, {
        serialize: false,
        getMinHeight: () => 96,
    });

    // ------------------------------------------------------------------
    // 上傳(走 ComfyUI 內建 /upload/image,進 input/nm_muse/)
    // ------------------------------------------------------------------
    uploadBtn.onclick = () => fileInput.click();
    fileInput.onchange = async () => {
        for (const file of fileInput.files) {
            const kind = kindOf(file.name);
            if (!kind) {
                alert(`不支援的檔案類型:${file.name}`);
                continue;
            }
            const form = new FormData();
            form.append("image", file);
            form.append("subfolder", UPLOAD_SUBFOLDER);
            form.append("type", "input");
            try {
                const resp = await api.fetchApi("/upload/image", {
                    method: "POST",
                    body: form,
                });
                if (resp.status !== 200) {
                    alert(`上傳失敗:${file.name}(${resp.status})`);
                    continue;
                }
                const data = await resp.json();
                const media = getMedia();
                const tag = nextTag(kind, media);
                media.push({
                    tag,
                    name: data.name,
                    subfolder: data.subfolder ?? UPLOAD_SUBFOLDER,
                    type: data.type ?? "input",
                    kind,
                });
                setMedia(media);
            } catch (e) {
                alert(`上傳失敗:${file.name}(${e})`);
            }
        }
        fileInput.value = "";
    };

    // ------------------------------------------------------------------
    // 縮圖列(點插入 @tag,× 移除)
    // ------------------------------------------------------------------
    function renderChips() {
        chips.innerHTML = "";
        for (const m of getMedia()) {
            const chip = document.createElement("div");
            chip.title = `${m.name}\n點擊插入 @${m.tag}`;
            chip.style.cssText =
                "position:relative;display:flex;flex-direction:column;align-items:center;gap:2px;" +
                "width:64px;padding:4px;border-radius:10px;border:1px solid var(--border-color,#555);" +
                "background:var(--comfy-input-bg,#333);cursor:pointer;user-select:none;";

            if (m.kind === "image") {
                const img = document.createElement("img");
                const params = new URLSearchParams({
                    filename: m.name,
                    subfolder: m.subfolder || "",
                    type: m.type || "input",
                });
                img.src = api.apiURL(`/view?${params}`);
                img.style.cssText =
                    "width:54px;height:40px;object-fit:cover;border-radius:6px;pointer-events:none;";
                chip.append(img);
            } else {
                const icon = document.createElement("div");
                icon.textContent = KIND_ICON[m.kind] || "📄";
                icon.style.cssText =
                    "width:54px;height:40px;display:flex;align-items:center;justify-content:center;" +
                    "font-size:22px;pointer-events:none;";
                chip.append(icon);
            }

            const label = document.createElement("div");
            label.textContent = "@" + m.tag;
            label.style.cssText =
                "font-size:10px;color:var(--input-text,#ddd);max-width:56px;overflow:hidden;" +
                "text-overflow:ellipsis;white-space:nowrap;pointer-events:none;";
            chip.append(label);

            const del = document.createElement("div");
            del.textContent = "×";
            del.title = "移除";
            del.style.cssText =
                "position:absolute;top:-6px;right:-6px;width:16px;height:16px;border-radius:50%;" +
                "background:#a33;color:#fff;font-size:12px;line-height:15px;text-align:center;cursor:pointer;";
            del.onclick = (e) => {
                e.stopPropagation();
                setMedia(getMedia().filter((x) => x.tag !== m.tag));
            };
            chip.append(del);

            chip.onclick = () => insertTag("@" + m.tag);
            chips.append(chip);
        }
    }

    // ------------------------------------------------------------------
    // @tag 插入與自動完成
    // ------------------------------------------------------------------
    function insertTag(text) {
        const w = wPrompt();
        if (!w) return;
        const el = w.inputEl;
        if (el && typeof el.selectionStart === "number") {
            const s = el.selectionStart, e = el.selectionEnd;
            el.value = el.value.slice(0, s) + text + " " + el.value.slice(e);
            el.selectionStart = el.selectionEnd = s + text.length + 1;
            el.focus();
            w.value = el.value;
        } else {
            w.value = (w.value || "") + (w.value ? " " : "") + text;
        }
        node.setDirtyCanvas(true, true);
    }

    // 自動完成選單(輸入 @ 時列出媒體 tag)
    const menu = document.createElement("div");
    menu.style.cssText =
        "position:fixed;z-index:10000;display:none;flex-direction:column;min-width:140px;" +
        "background:var(--comfy-menu-bg,#222);border:1px solid var(--border-color,#555);" +
        "border-radius:8px;padding:4px;box-shadow:0 4px 14px rgba(0,0,0,.5);";
    document.body.appendChild(menu);
    const hideMenu = () => (menu.style.display = "none");

    function showMenu(el, partial) {
        const items = getMedia().filter((m) =>
            m.tag.toLowerCase().startsWith(partial.toLowerCase()));
        if (!items.length) return hideMenu();

        menu.innerHTML = "";
        for (const m of items) {
            const row = document.createElement("div");
            row.textContent = `${KIND_ICON[m.kind] || ""} @${m.tag} — ${m.name}`;
            row.style.cssText =
                "padding:4px 8px;border-radius:6px;cursor:pointer;font-size:12px;" +
                "color:var(--input-text,#ddd);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";
            row.onmouseenter = () => (row.style.background = "var(--comfy-input-bg,#444)");
            row.onmouseleave = () => (row.style.background = "");
            row.onmousedown = (e) => {
                e.preventDefault();
                const s = el.selectionStart;
                const before = el.value.slice(0, s).replace(/@[\w-]*$/, "@" + m.tag + " ");
                el.value = before + el.value.slice(s);
                el.selectionStart = el.selectionEnd = before.length;
                const w = wPrompt();
                if (w) w.value = el.value;
                hideMenu();
                el.focus();
            };
            menu.append(row);
        }
        // 錨定在節點工具列上方(inputEl 在新版前端是隱藏 overlay,rect 不可靠)
        menu.style.display = "flex";
        menu.style.visibility = "hidden";
        requestAnimationFrame(() => {
            let r = container.getBoundingClientRect();
            if (!r.width && el.getBoundingClientRect().width) r = el.getBoundingClientRect();
            menu.style.left = `${Math.max(8, r.left)}px`;
            menu.style.top = `${Math.max(8, r.top - menu.offsetHeight - 6)}px`;
            menu.style.visibility = "visible";
        });
    }

    function bindAutocomplete() {
        const el = wPrompt()?.inputEl;
        if (!el || el.dataset.museBound) return;
        el.dataset.museBound = "1";
        el.addEventListener("input", () => {
            const upToCaret = el.value.slice(0, el.selectionStart);
            const match = upToCaret.match(/@([\w-]*)$/);
            if (match) showMenu(el, match[1]);
            else hideMenu();
        });
        el.addEventListener("blur", () => setTimeout(hideMenu, 150));
        // Ctrl+Enter / Cmd+Enter 直接送出
        el.addEventListener("keydown", (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                e.preventDefault();
                const w = wPrompt();
                if (w) w.value = el.value;
                queueNow();
            }
        });
    }
    // inputEl 可能延遲建立(新版前端),輪詢綁定幾次
    bindAutocomplete();
    let tries = 0;
    const timer = setInterval(() => {
        bindAutocomplete();
        if (wPrompt()?.inputEl?.dataset.museBound || ++tries > 60) clearInterval(timer);
    }, 500);

    // 工作流載入後 media_json 才有值,補畫縮圖列
    requestAnimationFrame(renderChips);
    const onConfigure = node.onConfigure;
    node.onConfigure = function () {
        const r = onConfigure?.apply(this, arguments);
        requestAnimationFrame(renderChips);
        return r;
    };

    // 節點移除時清掉 document 層級的殘留(自動完成選單、工具列 DOM),
    // 否則 graph.clear() / 換工作流後會留下幽靈按鈕
    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
        clearInterval(timer);
        menu.remove();
        container.remove();
        return onRemoved?.apply(this, arguments);
    };
}
