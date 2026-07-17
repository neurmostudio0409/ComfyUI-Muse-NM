// NM Muse 多圖上傳 — 前端擴充(介面仿 MultiImageLoader:
// Upload Images / Remove All / 編號縮圖 / 單張 ×)
// 狀態存在 image_paths widget(每行一個 input 相對路徑),隨工作流序列化

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const NODE_CLASS = "NMMuseMultiImageNode";
const UPLOAD_SUBFOLDER = "nm_muse";
const ACCEPT = ".png,.jpg,.jpeg,.webp,.bmp,.gif,.tiff";

app.registerExtension({
    name: "NM.MuseMultiImage",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_CLASS) return;
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated?.apply(this, arguments);
            setupMultiImage(this);
            return r;
        };
    },
});

function setupMultiImage(node) {
    // widget 參照每次即時解析(新版前端可能替換 widget 物件)
    const wPaths = () => node.widgets?.find((w) => w.name === "image_paths");
    if (!wPaths()) return;
    try {
        const w = wPaths();
        if (w && "hidden" in w) w.hidden = true;
    } catch { /* 隱藏失敗不影響功能 */ }

    const getPaths = () =>
        (wPaths()?.value || "").split("\n").map((s) => s.trim()).filter(Boolean);
    const setPaths = (paths) => {
        const w = wPaths();
        if (w) w.value = paths.join("\n");
        renderGrid();
        node.setDirtyCanvas(true, true);
    };

    // ------------------------------------------------------------------
    // UI:工具列 + 縮圖格
    // ------------------------------------------------------------------
    const container = document.createElement("div");
    container.style.cssText =
        "width:100%;min-height:220px;background:#222;border:1px solid #353545;" +
        "border-radius:6px;padding:10px;box-sizing:border-box;display:flex;" +
        "flex-direction:column;gap:10px;overflow:hidden;";

    const topBar = document.createElement("div");
    topBar.style.cssText =
        "display:flex;flex-wrap:wrap;align-items:center;gap:8px;";

    const uploadBtn = document.createElement("button");
    uploadBtn.textContent = "Upload Images";
    uploadBtn.style.cssText =
        "background:#3a3f4b;color:#fff;border:1px solid #5a5f6b;padding:3px 10px;" +
        "border-radius:3px;cursor:pointer;font-size:11px;";

    const removeAllBtn = document.createElement("button");
    removeAllBtn.textContent = "Remove All";
    removeAllBtn.style.cssText =
        "background:#cc2222;color:#fff;border:1px solid #aa1111;padding:3px 10px;" +
        "border-radius:3px;cursor:pointer;font-size:11px;";
    removeAllBtn.onmouseenter = () => (removeAllBtn.style.background = "#ff3333");
    removeAllBtn.onmouseleave = () => (removeAllBtn.style.background = "#cc2222");
    removeAllBtn.onclick = () => setPaths([]);

    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.multiple = true;
    fileInput.accept = ACCEPT;
    fileInput.style.display = "none";

    topBar.append(uploadBtn, removeAllBtn, fileInput);

    const grid = document.createElement("div");
    grid.style.cssText =
        "display:grid;grid-template-columns:repeat(auto-fill,minmax(96px,1fr));" +
        "gap:8px;overflow-y:auto;flex-grow:1;min-height:0;";

    container.append(topBar, grid);
    node.addDOMWidget("muse_multi_image", "div", container, {
        serialize: false,
        getMinHeight: () => 240,
    });

    // ------------------------------------------------------------------
    // 上傳(ComfyUI 內建 /upload/image → input/grok_refs/)
    // ------------------------------------------------------------------
    uploadBtn.onclick = () => fileInput.click();
    fileInput.onchange = async () => {
        const paths = getPaths();
        for (const file of fileInput.files) {
            const form = new FormData();
            form.append("image", file);
            form.append("subfolder", UPLOAD_SUBFOLDER);
            form.append("type", "input");
            try {
                const resp = await api.fetchApi("/upload/image", {
                    method: "POST", body: form,
                });
                if (resp.status !== 200) {
                    alert(`上傳失敗:${file.name}(${resp.status})`);
                    continue;
                }
                const data = await resp.json();
                const rel = data.subfolder ? `${data.subfolder}/${data.name}` : data.name;
                if (!paths.includes(rel)) paths.push(rel);
            } catch (e) {
                alert(`上傳失敗:${file.name}(${e})`);
            }
        }
        fileInput.value = "";
        setPaths(paths);
    };

    // ------------------------------------------------------------------
    // 縮圖格(編號 + 單張 ×)
    // ------------------------------------------------------------------
    function renderGrid() {
        grid.innerHTML = "";
        getPaths().forEach((rel, idx) => {
            const cell = document.createElement("div");
            cell.style.cssText =
                "position:relative;border:1px solid #353545;border-radius:4px;" +
                "overflow:hidden;aspect-ratio:1;background:#111;";

            const img = document.createElement("img");
            const slash = rel.lastIndexOf("/");
            const params = new URLSearchParams({
                filename: slash >= 0 ? rel.slice(slash + 1) : rel,
                subfolder: slash >= 0 ? rel.slice(0, slash) : "",
                type: "input",
            });
            img.src = api.apiURL(`/view?${params}`);
            img.title = rel;
            img.style.cssText = "width:100%;height:100%;object-fit:cover;";
            cell.append(img);

            const num = document.createElement("div");
            num.textContent = String(idx + 1);
            num.style.cssText =
                "position:absolute;left:4px;bottom:4px;background:rgba(0,0,0,.7);" +
                "color:#fff;font-size:11px;padding:1px 6px;border-radius:3px;";
            cell.append(num);

            const del = document.createElement("div");
            del.textContent = "×";
            del.title = "移除";
            del.style.cssText =
                "position:absolute;top:4px;right:4px;width:18px;height:18px;" +
                "border-radius:50%;background:#cc2222;color:#fff;font-size:13px;" +
                "line-height:17px;text-align:center;cursor:pointer;";
            del.onclick = () => setPaths(getPaths().filter((p) => p !== rel));
            cell.append(del);

            grid.append(cell);
        });
    }

    // 工作流載入後補畫;節點移除時清 DOM(避免幽靈按鈕)
    requestAnimationFrame(renderGrid);
    const onConfigure = node.onConfigure;
    node.onConfigure = function () {
        const r = onConfigure?.apply(this, arguments);
        requestAnimationFrame(renderGrid);
        return r;
    };
    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
        container.remove();
        return onRemoved?.apply(this, arguments);
    };
}
