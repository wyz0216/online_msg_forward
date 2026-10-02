const form = document.querySelector("#composer-form");
const content = form.elements.content;
const upload = form.elements.upload;
const status = document.querySelector("#composer-status");
const sendButton = form.querySelector('[type="submit"]');
const selectedFile = document.querySelector("[data-selected-file]");
const clearFile = document.querySelector("[data-clear-file]");
const toast = document.querySelector("[data-toast]");
const dropZone = document.querySelector("[data-drop-zone]");
const progressBox = document.querySelector("[data-upload-progress]");
const progressBar = document.querySelector("#upload-progress");
const progressLabel = document.querySelector("[data-progress-label]");
let toastTimer;
let sending = false;

function notify(message) {
  clearTimeout(toastTimer);
  toast.textContent = message;
  toastTimer = setTimeout(() => { toast.textContent = ""; }, 3000);
}

function showStatus(message, error = false) {
  status.textContent = message;
  status.dataset.error = String(error);
}

function updateFile() {
  const file = upload.files[0];
  selectedFile.hidden = !file;
  clearFile.hidden = !file;
  selectedFile.textContent = file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB` : "";
  const tooLarge = file && file.size > Number(form.dataset.maxUploadBytes);
  upload.setCustomValidity(tooLarge ? "文件超过大小限制，请重新选择。" : "");
  showStatus(tooLarge ? "文件超过大小限制，请重新选择。" : "", Boolean(tooLarge));
}

upload.addEventListener("change", updateFile);
clearFile.addEventListener("click", () => { upload.value = ""; updateFile(); });

function selectFiles(files) {
  if (sending) return;
  if (files.length !== 1) {
    showStatus("每次只能发送一个文件，请选择单个文件。", true);
    return;
  }
  if (files[0].size > Number(form.dataset.maxUploadBytes)) {
    showStatus("文件超过大小限制，请重新选择。", true);
    return;
  }
  const transfer = new DataTransfer();
  transfer.items.add(files[0]);
  upload.files = transfer.files;
  updateFile();
  showStatus("文件已选择，点击发送即可上传。");
}

form.addEventListener("paste", (event) => {
  if (!event.clipboardData?.files.length) return;
  event.preventDefault();
  selectFiles([...event.clipboardData.files]);
});

function isFileDrag(event) {
  return [...(event.dataTransfer?.types || [])].includes("Files");
}

form.addEventListener("dragover", (event) => {
  if (!isFileDrag(event)) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = sending ? "none" : "copy";
  dropZone.classList.toggle("drag-active", !sending);
});
form.addEventListener("dragleave", (event) => {
  if (!form.contains(event.relatedTarget)) dropZone.classList.remove("drag-active");
});
form.addEventListener("drop", (event) => {
  if (!isFileDrag(event)) return;
  event.preventDefault();
  event.stopPropagation();
  dropZone.classList.remove("drag-active");
  if ([...event.dataTransfer.items].some((item) => item.webkitGetAsEntry?.()?.isDirectory)) {
    showStatus("暂不支持上传文件夹，请选择单个文件。", true);
    return;
  }
  selectFiles([...event.dataTransfer.files]);
});
// Prevent a file dropped outside the composer from replacing the page.
document.addEventListener("dragover", (event) => { if (isFileDrag(event)) event.preventDefault(); });
document.addEventListener("drop", (event) => {
  if (!isFileDrag(event)) return;
  event.preventDefault();
  notify("请将文件拖到左侧或上方的发送区域。");
});

content.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && !event.isComposing) {
    event.preventDefault();
    form.requestSubmit();
  }
});

function sendMessage(data) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", form.action);
    xhr.timeout = 300000;
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const percent = Math.floor(event.loaded / event.total * 100);
        progressBar.value = percent;
        progressLabel.textContent = percent < 100 ? `正在上传 ${percent}%` : "已上传 100%，正在保存…";
        if (percent === 100) showStatus("上传完成，正在等待服务器保存…");
      } else {
        progressBar.removeAttribute("value");
        progressLabel.textContent = "正在上传…";
      }
    };
    xhr.onload = () => {
      if (new URL(xhr.responseURL).pathname === "/login") {
        reject(new Error("登录已过期，请在新标签页重新登录后重试。输入内容已保留。"));
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
        return;
      }
      let result = {};
      try { result = JSON.parse(xhr.responseText); } catch { /* Non-JSON server error. */ }
      const errors = {
        "File is too large": "文件超过大小限制，请重新选择。",
        "Invalid expiration": "自动删除时间无效，请重新选择。",
        "Message content or file is required": "请先输入文本，或选择一个文件。",
      };
      reject(new Error(xhr.status === 413 ? "文件超过服务器大小限制，请选择更小的文件。" : errors[result.detail] || "发送失败，内容已保留，可以重试。"));
    };
    xhr.onerror = () => reject(new Error("网络连接中断，内容已保留。请先查看消息是否已收到，再重试。"));
    xhr.ontimeout = () => reject(new Error("发送超时，内容已保留。请先查看消息是否已收到，再重试。"));
    xhr.send(data);
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (sending) return;
  if (!content.value.trim() && !upload.files.length) {
    showStatus("请先输入文本，或选择一个文件。", true);
    content.focus();
    return;
  }
  const data = new FormData(form);
  const controls = [...form.querySelectorAll("input, textarea, select, button")];
  sending = true;
  controls.forEach((control) => { control.disabled = true; });
  sendButton.setAttribute("aria-busy", "true");
  sendButton.textContent = "正在发送…";
  progressBox.hidden = !upload.files.length;
  progressBar.value = 0;
  progressLabel.textContent = "准备上传 0%…";
  showStatus(upload.files.length ? "正在上传，请稍候…" : "正在保存，请稍候…");
  try {
    await sendMessage(data);
    window.location.assign("/");
  } catch (error) {
    showStatus(error.message, true);
    progressBox.hidden = true;
    status.focus();
    sending = false;
    controls.forEach((control) => { control.disabled = false; });
    sendButton.removeAttribute("aria-busy");
    sendButton.textContent = "重试发送 ↗";
  }
});

document.querySelector("[data-refresh-button]").addEventListener("click", () => {
  if (sending) return;
  if ((content.value.trim() || upload.files.length) && !window.confirm("刷新会清空尚未发送的内容，确定刷新吗？")) return;
  window.location.reload();
});

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // Some browsers deny clipboard access even on HTTPS; try the fallback.
    }
  }
  const previousFocus = document.activeElement;
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.cssText = "position:fixed;left:-9999px;top:0";
  document.body.appendChild(textarea);
  try {
    textarea.focus();
    textarea.select();
    if (!document.execCommand("copy")) throw new Error("Copy failed");
  } finally {
    textarea.remove();
    previousFocus?.focus();
  }
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("button, a");
  if (!button) return;
  if (button.matches("[data-copy-text]")) {
    try {
      await copyText(button.dataset.copyText || "");
      notify("已复制到剪贴板");
    } catch {
      notify("复制失败，请长按或选中文本手动复制。");
    }
  }
  if (button.matches("[data-preview-target]")) {
    const dialog = document.getElementById(button.dataset.previewTarget);
    const image = dialog.querySelector(".image-full");
    image.src = image.dataset.src;
    dialog.showModal();
  }
  if (button.matches("[data-preview-close]")) document.getElementById(button.dataset.previewClose).close();
  if (button.matches("[data-page-link]") && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
    event.preventDefault();
    loadMessages(button.href);
  }
});

document.addEventListener("click", (event) => {
  if (event.target.matches(".image-dialog")) event.target.close();
});

document.addEventListener("submit", (event) => {
  if (event.target.matches("[data-share-form]")) {
    event.preventDefault();
    if (sending) return;
    const shareForm = event.target;
    if (shareForm.hasAttribute("data-share-revoke") && !window.confirm("取消分享后，原链接将立即失效。确定取消吗？")) return;
    changeShare(shareForm);
  }
  if (event.target.matches("[data-delete-form]")) {
    if (sending || !window.confirm("确定删除这条消息吗？删除后无法恢复。")) event.preventDefault();
  }
  if (event.target.matches("#message-filters")) {
    event.preventDefault();
    const filters = event.target;
    const url = new URL(filters.action);
    url.search = new URLSearchParams({q: filters.elements.q.value, kind: event.submitter?.value || filters.dataset.kind});
    loadMessages(url.href);
  }
});

async function changeShare(shareForm) {
  const button = shareForm.querySelector("button");
  if (button.disabled) return;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    const response = await fetch(shareForm.action, {method: "POST", headers: {Accept: "application/json"}});
    if (new URL(response.url).pathname === "/login") throw new Error("登录已过期，请重新登录。");
    if (!response.ok) throw new Error("分享操作失败，请刷新消息列表后重试。");
    const result = await response.json();
    if (result.share_path) {
      try {
        await copyText(new URL(result.share_path, window.location.origin).href);
        notify("分享链接已复制，对方无需登录即可查看。");
      } catch {
        notify("分享已开启，请在消息下方选中链接手动复制。");
      }
    } else {
      notify("已取消分享，原链接已失效。");
    }
    await loadMessages(window.location.href, false);
  } catch (error) {
    notify(error instanceof TypeError ? "分享操作失败，请检查网络后重试。" : error.message);
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

let listRequest;
async function loadMessages(url, pushHistory = true) {
  listRequest?.abort();
  const controller = new AbortController();
  listRequest = controller;
  const panel = document.querySelector("#message-results");
  panel.setAttribute("aria-busy", "true");
  try {
    const response = await fetch(url, {signal: controller.signal});
    if (new URL(response.url).pathname === "/login") throw new Error("登录已过期，请重新登录。");
    if (!response.ok) throw new Error("消息加载失败，请重试。");
    const doc = new DOMParser().parseFromString(await response.text(), "text/html");
    const replacement = doc.querySelector("#message-results");
    if (!replacement) throw new Error("消息加载失败，请重试。");
    if (controller.signal.aborted) return;
    panel.replaceWith(replacement);
    if (pushHistory) history.pushState(null, "", url);
    replacement.setAttribute("tabindex", "-1");
    replacement.focus({preventScroll: true});
    replacement.scrollIntoView({block: "start"});
  } catch (error) {
    if (error.name !== "AbortError") notify(error instanceof TypeError ? "消息加载失败，请检查网络后重试。" : error.message);
  } finally {
    if (listRequest === controller) panel.removeAttribute("aria-busy");
  }
}
window.addEventListener("popstate", () => loadMessages(window.location.href, false));
