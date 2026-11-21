/* ==========================================================================
   IELTS Bhuiyan Admin - Question Setter UI Helpers
   ========================================================================== */

document.addEventListener("DOMContentLoaded", function() {
    function initQuickOptionsToolbar(textarea) {
        if (!textarea || textarea.dataset.hasToolbar) return;
        textarea.dataset.hasToolbar = "true";

        const container = document.createElement("div");
        container.className = "quick-options-toolbar";
        container.innerHTML = `
            <span style="font-size:11px;font-weight:700;color:#4338ca;text-transform:uppercase;letter-spacing:0.5px;margin-right:4px;">Quick Templates:</span>
            <button type="button" class="quick-opt-btn" data-template="abcd" title="Insert A, B, C, D templates">+ Options A–D</button>
            <button type="button" class="quick-opt-btn" data-template="abcde" title="Insert A to E templates">+ Options A–E</button>
            <button type="button" class="quick-opt-btn" data-template="headings" title="Insert Roman numerals i to vi for Matching Headings">+ Headings (i–vi)</button>
            <button type="button" class="quick-opt-btn" data-template="tfng" title="Insert TRUE / FALSE / NOT GIVEN">+ TRUE / FALSE / NOT GIVEN</button>
            <button type="button" class="quick-opt-btn" data-template="ynng" title="Insert YES / NO / NOT GIVEN">+ YES / NO / NOT GIVEN</button>
        `;

        textarea.parentNode.insertBefore(container, textarea);

        container.addEventListener("click", function(e) {
            const btn = e.target.closest(".quick-opt-btn");
            if (!btn) return;
            e.preventDefault();

            const t = btn.dataset.template;
            let text = "";
            if (t === "abcd") {
                text = "A. \nB. \nC. \nD. ";
            } else if (t === "abcde") {
                text = "A. \nB. \nC. \nD. \nE. ";
            } else if (t === "headings") {
                text = "i. \nii. \niii. \niv. \nv. \nvi. ";
            } else if (t === "tfng") {
                text = "TRUE. True\nFALSE. False\nNOT GIVEN. Not Given";
            } else if (t === "ynng") {
                text = "YES. Yes\nNO. No\nNOT GIVEN. Not Given";
            }

            if (textarea.value.trim() && !confirm("Replace current options text with this template?")) {
                return;
            }
            textarea.value = text;
            textarea.focus();
            const firstLineEnd = text.indexOf("\n");
            if (firstLineEnd > 0) {
                textarea.setSelectionRange(firstLineEnd, firstLineEnd);
            }
        });
    }

    // Initialize all quick_options textareas on page load
    document.querySelectorAll("textarea[name*='quick_options']").forEach(initQuickOptionsToolbar);

    // Support dynamically added inlines ("Add another Question")
    const observer = new MutationObserver(function() {
        document.querySelectorAll("textarea[name*='quick_options']").forEach(initQuickOptionsToolbar);
    });
    observer.observe(document.body, { childList: true, subtree: true });
});
