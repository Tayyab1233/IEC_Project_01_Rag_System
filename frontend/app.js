// Frontend application logic for the Production RAG Service

document.addEventListener("DOMContentLoaded", () => {
    let currentTenant = "user_a";

    const tenantSelect = document.getElementById("tenantSelect");
    const customTenantInput = document.getElementById("customTenantInput");
    const docList = document.getElementById("docList");
    const docCountBadge = document.getElementById("docCountBadge");
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("fileInput");
    const browseBtn = document.getElementById("browseBtn");
    const refreshDocsBtn = document.getElementById("refreshDocsBtn");
    const uploadProgress = document.getElementById("uploadProgress");
    const chatForm = document.getElementById("chatForm");
    const queryInput = document.getElementById("queryInput");
    const charCount = document.getElementById("charCount");
    const chatStream = document.getElementById("chatStream");
    const alertBanner = document.getElementById("alertBanner");

    // -------------------------------------------------------------------------
    // Tenant Selection
    // -------------------------------------------------------------------------
    tenantSelect.addEventListener("change", (e) => {
        if (e.target.value === "custom") {
            customTenantInput.style.display = "inline-block";
            customTenantInput.focus();
        } else {
            customTenantInput.style.display = "none";
            currentTenant = e.target.value;
            loadDocuments();
        }
    });

    customTenantInput.addEventListener("blur", () => {
        const val = customTenantInput.value.trim();
        if (val) {
            currentTenant = val;
            loadDocuments();
        }
    });

    // -------------------------------------------------------------------------
    // Document Upload & Management
    // -------------------------------------------------------------------------
    browseBtn.addEventListener("click", () => fileInput.click());
    dropzone.addEventListener("click", (e) => {
        if (e.target !== browseBtn) fileInput.click();
    });

    ["dragenter", "dragover"].forEach(evt => {
        dropzone.addEventListener(evt, (e) => {
            e.preventDefault();
            dropzone.classList.add("dragover");
        });
    });

    ["dragleave", "drop"].forEach(evt => {
        dropzone.addEventListener(evt, (e) => {
            e.preventDefault();
            dropzone.classList.remove("dragover");
        });
    });

    dropzone.addEventListener("drop", (e) => {
        const files = e.dataTransfer.files;
        if (files.length > 0) handleFileUpload(files[0]);
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) handleFileUpload(e.target.files[0]);
    });

    refreshDocsBtn.addEventListener("click", loadDocuments);

    async function handleFileUpload(file) {
        uploadProgress.style.display = "block";
        showAlert(null);

        const formData = new FormData();
        formData.append("file", file);

        try {
            const res = await fetch("/documents", {
                method: "POST",
                headers: { "X-User-ID": currentTenant },
                body: formData,
            });

            const data = await res.json();
            if (!res.ok) {
                showAlert(`Upload Error: ${data.message || "Failed to upload document"}`, "danger");
            } else {
                showAlert(`Successfully uploaded ${data.filename} (${data.chunk_count} chunks indexed).`, "warning");
                loadDocuments();
            }
        } catch (err) {
            showAlert(`Network Error: ${err.message}`, "danger");
        } finally {
            uploadProgress.style.display = "none";
            fileInput.value = "";
        }
    }

    async function loadDocuments() {
        try {
            const res = await fetch("/documents", {
                headers: { "X-User-ID": currentTenant },
            });
            const data = await res.json();
            renderDocuments(data.documents || []);
        } catch (err) {
            console.error("Failed to fetch documents", err);
        }
    }

    function renderDocuments(docs) {
        docCountBadge.textContent = `${docs.length} Docs`;
        if (docs.length === 0) {
            docList.innerHTML = `<div class="empty-state">No documents uploaded for tenant '<strong>${currentTenant}</strong>'.</div>`;
            return;
        }

        docList.innerHTML = docs.map(d => `
            <div class="doc-card" id="doc-${d.id}">
                <div class="doc-card-info">
                    <h4 title="${d.filename}">${d.filename}</h4>
                    <div class="doc-meta">
                        <span>${d.chunk_count} chunks</span> &bull; 
                        <span>${Math.round(d.file_size_bytes / 1024)} KB</span>
                    </div>
                </div>
                <button class="btn btn-sm btn-danger-outline delete-doc-btn" data-id="${d.id}" title="Delete document">✕</button>
            </div>
        `).join("");

        document.querySelectorAll(".delete-doc-btn").forEach(btn => {
            btn.addEventListener("click", async (e) => {
                const docId = e.target.getAttribute("data-id");
                if (confirm("Delete document and its Qdrant vectors?")) {
                    await deleteDocument(docId);
                }
            });
        });
    }

    async function deleteDocument(docId) {
        try {
            const res = await fetch(`/documents/${docId}`, {
                method: "DELETE",
                headers: { "X-User-ID": currentTenant },
            });
            if (res.status === 204) {
                loadDocuments();
            } else {
                alert("Failed to delete document");
            }
        } catch (err) {
            alert(`Error: ${err.message}`);
        }
    }

    // -------------------------------------------------------------------------
    // Chat & Grounded Query
    // -------------------------------------------------------------------------
    queryInput.addEventListener("input", (e) => {
        charCount.textContent = e.target.value.length;
    });

    chatForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const query = queryInput.value.trim();
        if (!query) return;

        appendUserMessage(query);
        queryInput.value = "";
        charCount.textContent = "0";
        showAlert(null);

        const loadingMsgId = appendAssistantLoading();

        try {
            const res = await fetch("/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-User-ID": currentTenant,
                },
                body: JSON.stringify({ message: query }),
            });

            const data = await res.json();
            removeMessage(loadingMsgId);

            if (res.status === 400) {
                showAlert(`Security Alert (400 Bad Request): ${data.message}`, "danger");
                appendAssistantMessage({
                    answer: `⚠️ **Security Alert**: The query was rejected by safety guardrails. ${data.message}`,
                    citations: [],
                    retrieved_chunks: [],
                    latency_ms: 0,
                    model: "SafetyGuardrail",
                    refused: true,
                });
            } else if (res.status === 422) {
                showAlert(`Validation Error: ${data.message}`, "danger");
            } else if (res.ok) {
                appendAssistantMessage(data);
            } else {
                showAlert(`Server Error (${res.status}): ${data.message || "Unknown error"}`, "danger");
            }
        } catch (err) {
            removeMessage(loadingMsgId);
            showAlert(`Connection Error: ${err.message}`, "danger");
        }
    });

    function appendUserMessage(text) {
        const msgDiv = document.createElement("div");
        msgDiv.className = "message user-message";
        msgDiv.innerHTML = `
            <div class="message-header">
                <strong>You (${currentTenant})</strong>
                <span class="timestamp">${new Date().toLocaleTimeString()}</span>
            </div>
            <div class="message-body">${escapeHtml(text)}</div>
        `;
        chatStream.appendChild(msgDiv);
        chatStream.scrollTop = chatStream.scrollHeight;
    }

    function appendAssistantLoading() {
        const id = "loading-" + Date.now();
        const msgDiv = document.createElement("div");
        msgDiv.id = id;
        msgDiv.className = "message assistant-message";
        msgDiv.innerHTML = `
            <div class="message-header">
                <strong>AI Assistant</strong>
                <span class="timestamp">Retrieving & generating...</span>
            </div>
            <div class="message-body">
                <span class="pulse-dot" style="display:inline-block; margin-right:6px;"></span>
                Evaluating hybrid RRF evidence...
            </div>
        `;
        chatStream.appendChild(msgDiv);
        chatStream.scrollTop = chatStream.scrollHeight;
        return id;
    }

    function appendAssistantMessage(data) {
        const msgDiv = document.createElement("div");
        msgDiv.className = "message assistant-message";

        // Highlight inline citations
        let formattedAnswer = escapeHtml(data.answer);
        formattedAnswer = formattedAnswer.replace(
            /\[File:\s*([^\|\]]+?)\s*\|\s*Location:\s*([^\]]+?)\]/g,
            '<span class="citation-pill">📄 $1 &bull; $2</span>'
        );

        const latencyBadge = `<span class="badge badge-outline">${data.latency_ms || 0}ms</span>`;
        const modelBadge = `<span class="badge badge-accent">${data.model || "gemini-3.8-flash"}</span>`;
        const chunksCount = data.retrieved_chunks ? data.retrieved_chunks.length : 0;

        let chunksInspectionHtml = "";
        if (chunksCount > 0) {
            const chunksItems = data.retrieved_chunks.map((c, i) => `
                <div class="chunk-card">
                    <div class="chunk-card-header">
                        <strong>#${i + 1} ${c.file_name} (${c.page_or_section})</strong>
                        <span>Score: ${(c.score * 100).toFixed(1)}%</span>
                    </div>
                    <div>${escapeHtml(c.text.substring(0, 180))}...</div>
                </div>
            `).join("");

            chunksInspectionHtml = `
                <div class="chunk-inspection-box">
                    <button class="chunk-toggle-btn" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'flex' : 'none'">
                        🔍 Inspect ${chunksCount} Retrieved Evidence Chunks
                    </button>
                    <div class="retrieved-chunks-list" style="display: none;">
                        ${chunksItems}
                    </div>
                </div>
            `;
        }

        msgDiv.innerHTML = `
            <div class="message-header">
                <div>
                    <strong>AI Assistant</strong>
                    ${modelBadge}
                    ${latencyBadge}
                </div>
                <span class="timestamp">${new Date().toLocaleTimeString()}</span>
            </div>
            <div class="message-body" style="white-space: pre-line;">${formattedAnswer}</div>
            ${chunksInspectionHtml}
        `;

        chatStream.appendChild(msgDiv);
        chatStream.scrollTop = chatStream.scrollHeight;
    }

    function removeMessage(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    function showAlert(text, type = "warning") {
        if (!text) {
            alertBanner.style.display = "none";
            return;
        }
        alertBanner.className = `alert-banner alert-${type}`;
        alertBanner.innerHTML = text;
        alertBanner.style.display = "block";
    }

    function escapeHtml(str) {
        return (str || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Initial load
    loadDocuments();
});


// === Copy Buttons & Retrieved Chunks History Enhancer ===
(function () {
  const chunkHistory = [];

  function escapeHtmlSafe(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function attachCopyButton(msgEl, textProvider) {
    if (!msgEl || msgEl.querySelector(".copy-msg-btn")) return;
    const header =
      msgEl.querySelector(".message-header, .msg-header, header, .chat-meta") ||
      msgEl.firstElementChild;
    if (!header) return;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "copy-msg-btn";
    btn.textContent = "Copy";
    btn.title = "Copy text to clipboard";

    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const rawText = textProvider().trim();
      if (!rawText) return;
      try {
        await navigator.clipboard.writeText(rawText);
        btn.textContent = "Copied!";
        btn.classList.add("copied");
        setTimeout(() => {
          btn.textContent = "Copy";
          btn.classList.remove("copied");
        }, 1600);
      } catch (_) {
        btn.textContent = "Failed";
        setTimeout(() => (btn.textContent = "Copy"), 1400);
      }
    });

    header.appendChild(btn);
  }

  function scanMessagesForCopyButtons() {
    document
      .querySelectorAll(".message, .chat-message, [class*='message-card'], [class*='bubble']")
      .forEach((el) => {
        attachCopyButton(el, () => {
          const clone = el.cloneNode(true);
          clone
            .querySelectorAll(
              ".copy-msg-btn, .message-header, .msg-header, details, .citations, .citation-pills"
            )
            .forEach((n) => n.remove());
          return clone.innerText || clone.textContent || "";
        });
      });
  }

  function renderChunkHistory() {
    const listEl = document.getElementById("chunks-history-list");
    const countEl = document.getElementById("history-turn-count");
    if (!listEl || !countEl) return;

    countEl.textContent = `${chunkHistory.length} ${chunkHistory.length === 1 ? "Turn" : "Turns"}`;

    if (chunkHistory.length === 0) {
      listEl.innerHTML = `
        <div class="empty-history-state">
          <p>Submit a grounded query to inspect and track retrieved evidence chunks, relevance scores, and source citations across turns.</p>
        </div>`;
      return;
    }

    listEl.innerHTML = chunkHistory
      .map((entry, idx) => {
        const turnNum = chunkHistory.length - idx;
        const chunksHtml =
          entry.chunks.length === 0
            ? `<div class="history-chunk-item"><span class="history-chunk-snippet">No chunks retrieved (blocked or empty corpus).</span></div>`
            : entry.chunks
                .map((c, cIdx) => {
                  const scorePct =
                    typeof c.score === "number"
                      ? `${(c.score <= 1 ? c.score * 100 : c.score).toFixed(1)}%`
                      : "N/A";
                  return `
                    <div class="history-chunk-item">
                      <div class="history-chunk-top">
                        <span class="history-chunk-source">#${cIdx + 1} ${escapeHtmlSafe(c.file_name)} (${escapeHtmlSafe(c.page_or_section)})</span>
                        <span class="history-chunk-score">${scorePct}</span>
                      </div>
                      <div class="history-chunk-snippet">${escapeHtmlSafe(c.text)}</div>
                    </div>`;
                })
                .join("");

        return `
          <div class="history-turn-card">
            <div class="history-turn-header">
              <div class="history-turn-query">Turn ${turnNum}: "${escapeHtmlSafe(entry.query)}"</div>
              <div class="history-turn-meta">${entry.chunks.length} chunks ? ${escapeHtmlSafe(entry.time)}</div>
            </div>
            ${chunksHtml}
          </div>`;
      })
      .join("");
  }

  // Intercept /chat responses to record retrieved chunks per turn
  const origFetch = window.fetch;
  window.fetch = async function (...args) {
    let requestQuery = "";
    try {
      const [resource, init] = args;
      const url = typeof resource === "string" ? resource : resource?.url || "";
      if (url.includes("/chat") && init?.body && typeof init.body === "string") {
        const parsed = JSON.parse(init.body);
        requestQuery = parsed.query || parsed.question || "";
      }
    } catch (_) {}

    const response = await origFetch.apply(this, args);

    try {
      const url = typeof args[0] === "string" ? args[0] : args[0]?.url || "";
      if (url.includes("/chat") && response.ok) {
        const cloned = response.clone();
        const data = await cloned.json();
        const chunks = Array.isArray(data.retrieved_chunks) ? data.retrieved_chunks : [];
        chunkHistory.unshift({
          query: requestQuery || "Query",
          chunks,
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        });
        renderChunkHistory();
      }
    } catch (_) {}

    setTimeout(scanMessagesForCopyButtons, 60);
    return response;
  };

  document.addEventListener("DOMContentLoaded", () => {
    scanMessagesForCopyButtons();
    const observer = new MutationObserver(() => scanMessagesForCopyButtons());
    observer.observe(document.body, { childList: true, subtree: true });

    const clearBtn = document.getElementById("clear-chunk-history-btn");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        chunkHistory.length = 0;
        renderChunkHistory();
      });
    }
  });
})();
