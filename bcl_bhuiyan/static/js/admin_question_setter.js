/* ==========================================================================
   IELTS Bhuiyan Admin - MCQ Options Tabular Editor & Sync
   ========================================================================== */

document.addEventListener("DOMContentLoaded", function() {
    function initTabularWrapper(wrapper) {
        if (!wrapper || wrapper.dataset.initialized) return;
        wrapper.dataset.initialized = "true";

        const tbody = wrapper.querySelector(".mcq-table-tbody");
        const textarea = wrapper.querySelector(".mcq-raw-textarea");
        const addBtn = wrapper.querySelector(".btn-mcq-add-row");

        if (!tbody || !textarea) return;

        function createRowElement(order, key, text, isCorrect) {
            const tr = document.createElement("tr");
            tr.className = "mcq-table-row";
            tr.style.borderBottom = "1px solid rgba(255,255,255,0.08)";
            const safeText = (text || "").replace(/"/g, '&quot;');
            const safeKey = (key || "").replace(/"/g, '&quot;');
            tr.innerHTML = `
                <td style="text-align: center; padding: 8px 6px;">
                  <input type="number" class="mcq-field-order" value="${order}" min="1" max="99" style="width: 50px; text-align: center; padding: 6px 4px; border-radius: 4px; font-weight: 600; background: #1e293b; color: #f8fafc; border: 1px solid #475569;" />
                </td>
                <td style="text-align: center; padding: 8px 6px;">
                  <input type="text" class="mcq-field-key" value="${safeKey}" placeholder="e.g. A" style="width: 100px; text-align: center; padding: 6px 8px; font-weight: 700; text-transform: uppercase; border-radius: 4px; background: #1e293b; color: #38bdf8; border: 1px solid #475569;" />
                </td>
                <td style="padding: 8px 6px;">
                  <input type="text" class="mcq-field-text" value="${safeText}" placeholder="Enter choice text..." style="width: 100%; box-sizing: border-box; padding: 7px 10px; border-radius: 4px; background: #1e293b; color: #ffffff; border: 1px solid #475569;" />
                </td>
                <td style="text-align: center; padding: 8px 6px;">
                  <input type="checkbox" class="mcq-field-correct" ${isCorrect ? 'checked="checked"' : ''} style="width: 18px; height: 18px; cursor: pointer; accent-color: #22c55e;" title="Mark as correct answer" />
                </td>
                <td style="text-align: center; padding: 8px 6px;">
                  <input type="checkbox" class="mcq-field-delete" style="width: 18px; height: 18px; cursor: pointer; accent-color: #ef4444;" title="Delete this option" />
                </td>
            `;
            return tr;
        }

        function syncRowsToTextarea() {
            const items = [];
            const correctKeys = [];
            const rows = tbody.querySelectorAll(".mcq-table-row");

            let activeIdx = 1;
            rows.forEach(tr => {
                const delInput = tr.querySelector(".mcq-field-delete");
                const isDeleted = Boolean(delInput && delInput.checked);

                if (isDeleted) {
                    tr.style.opacity = "0.35";
                    tr.style.textDecoration = "line-through";
                    return;
                } else {
                    tr.style.opacity = "1";
                    tr.style.textDecoration = "none";
                }

                const orderInput = tr.querySelector(".mcq-field-order");
                const keyInput = tr.querySelector(".mcq-field-key");
                const textInput = tr.querySelector(".mcq-field-text");
                const correctInput = tr.querySelector(".mcq-field-correct");

                if (orderInput && !orderInput.value) {
                    orderInput.value = activeIdx;
                }

                const key = (keyInput ? keyInput.value : "").trim() || (activeIdx <= 26 ? String.fromCharCode(64 + activeIdx) : String(activeIdx));
                const text = (textInput ? textInput.value : "").trim();
                const isCor = Boolean(correctInput && correctInput.checked);

                if (key || text) {
                    items.push({
                        order: parseInt(orderInput ? orderInput.value : activeIdx) || activeIdx,
                        key: key,
                        text: text || key,
                        is_correct: isCor
                    });
                    if (isCor) {
                        correctKeys.push(key);
                    }
                    activeIdx++;
                }
            });

            textarea.value = JSON.stringify(items);

            // Auto-update correct_answer field in the same inline question
            if (correctKeys.length > 0) {
                const inline = wrapper.closest(".inline-related") || wrapper.closest(".form-row") || wrapper.closest("fieldset");
                if (inline) {
                    const ca = inline.querySelector("textarea[name*='correct_answer'], input[name*='correct_answer']");
                    if (ca) {
                        ca.value = correctKeys.join(", ");
                    }
                }
            }
        }

        // Live sync on typing or toggling checkboxes
        tbody.addEventListener("input", syncRowsToTextarea);
        tbody.addEventListener("change", syncRowsToTextarea);

        // Add Option Row
        if (addBtn) {
            addBtn.addEventListener("click", function(e) {
                e.preventDefault();
                const rows = tbody.querySelectorAll(".mcq-table-row");
                const nextOrder = rows.length + 1;
                let nextKey = String(nextOrder);
                if (rows.length > 0) {
                    const lastKey = rows[rows.length - 1].querySelector(".mcq-field-key").value.trim().toUpperCase();
                    if (lastKey.length === 1 && lastKey >= "A" && lastKey < "Z") {
                        nextKey = String.fromCharCode(lastKey.charCodeAt(0) + 1);
                    }
                } else {
                    nextKey = "A";
                }

                const newRow = createRowElement(nextOrder, nextKey, "", false);
                tbody.appendChild(newRow);
                const textInput = newRow.querySelector(".mcq-field-text");
                if (textInput) textInput.focus();
                syncRowsToTextarea();
            });
        }

        // Preset Buttons
        wrapper.querySelectorAll(".btn-mcq-preset").forEach(btn => {
            btn.addEventListener("click", function(e) {
                e.preventDefault();
                const p = btn.dataset.preset;
                tbody.innerHTML = "";
                let newRows = [];

                if (p === "abcd") {
                    newRows = [
                        { order: 1, key: "A", text: "", isCorrect: false },
                        { order: 2, key: "B", text: "", isCorrect: false },
                        { order: 3, key: "C", text: "", isCorrect: false },
                        { order: 4, key: "D", text: "", isCorrect: false },
                    ];
                } else if (p === "tfng") {
                    newRows = [
                        { order: 1, key: "TRUE", text: "TRUE", isCorrect: false },
                        { order: 2, key: "FALSE", text: "FALSE", isCorrect: false },
                        { order: 3, key: "NOT GIVEN", text: "NOT GIVEN", isCorrect: false },
                    ];
                } else if (p === "ynng") {
                    newRows = [
                        { order: 1, key: "YES", text: "YES", isCorrect: false },
                        { order: 2, key: "NO", text: "NO", isCorrect: false },
                        { order: 3, key: "NOT GIVEN", text: "NOT GIVEN", isCorrect: false },
                    ];
                }

                newRows.forEach(r => {
                    tbody.appendChild(createRowElement(r.order, r.key, r.text, r.isCorrect));
                });
                syncRowsToTextarea();
            });
        });

        // Initial sync
        syncRowsToTextarea();
    }

    // Initialize all existing wrappers on page load
    document.querySelectorAll(".mcq-tabular-wrapper").forEach(initTabularWrapper);

    // Watch for dynamically added Question inlines ("Add another Question")
    const observer = new MutationObserver(function() {
        document.querySelectorAll(".mcq-tabular-wrapper").forEach(initTabularWrapper);
    });
    observer.observe(document.body, { childList: true, subtree: true });
});
