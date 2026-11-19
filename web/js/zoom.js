// Per-section zoom: expand one .panel to cover the ops console viewport.
(function () {
  "use strict";

  let active = null;

  function btnHtml() {
    return '<button type="button" class="zoom-btn b sm ghost" title="Phóng to section" aria-label="Zoom section">⛶</button>';
  }

  function exit() {
    if (!active) return;
    active.classList.remove("panel-zoom");
    const b = active.querySelector(".zoom-btn");
    if (b) { b.textContent = "⛶"; b.title = "Phóng to section"; b.setAttribute("aria-pressed", "false"); }
    active = null;
    document.body.classList.remove("panel-zoom-open");
    window.dispatchEvent(new Event("resize"));
  }

  function enter(panel) {
    if (active === panel) { exit(); return; }
    exit();
    active = panel;
    panel.classList.add("panel-zoom");
    document.body.classList.add("panel-zoom-open");
    const b = panel.querySelector(".zoom-btn");
    if (b) { b.textContent = "✕"; b.title = "Thu nhỏ"; b.setAttribute("aria-pressed", "true"); }
    window.dispatchEvent(new Event("resize"));
  }

  function ensureBtn(panel) {
    const hd = panel.querySelector(".panel-hd");
    if (!hd || hd.querySelector(".zoom-btn")) return;
    const actions = hd.querySelector(".panel-hd-actions") || (() => {
      const d = document.createElement("div");
      d.className = "panel-hd-actions";
      // Move trailing chips/controls into actions if they are direct children after h3
      const kids = [...hd.children].filter(el => el.tagName !== "H3" && !el.classList.contains("panel-hd-actions"));
      kids.forEach(el => d.appendChild(el));
      hd.appendChild(d);
      return d;
    })();
    actions.insertAdjacentHTML("beforeend", btnHtml());
    actions.querySelector(".zoom-btn").addEventListener("click", e => {
      e.stopPropagation();
      enter(panel);
    });
  }

  function init() {
    document.querySelectorAll("#app .panel").forEach(ensureBtn);
    document.addEventListener("keydown", e => {
      if (e.key === "Escape" && active) { e.preventDefault(); exit(); }
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();

  window.EchoZoom = { enter, exit, active: () => active };
})();
