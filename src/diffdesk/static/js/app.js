/* diffdesk UI helpers */
(function () {
  "use strict";

  // Soft loading indicator for form submits
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.dataset.noLoading === "1") return;
    var btn = form.querySelector('button[type="submit"], input[type="submit"]');
    if (btn && !btn.disabled) {
      btn.dataset.originalText = btn.textContent;
      btn.disabled = true;
      if (btn.tagName === "BUTTON") {
        btn.innerHTML = '<span class="spinner"></span> Working…';
      }
    }
  });

  // Keyboard: n = new review when not typing
  document.addEventListener("keydown", function (e) {
    var tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || e.metaKey || e.ctrlKey || e.altKey) {
      return;
    }
    if (e.key === "n" || e.key === "N") {
      window.location.href = "/reviews/new";
    }
    if (e.key === "d" || e.key === "D") {
      window.location.href = "/";
    }
    if (e.key === "r" || e.key === "R") {
      window.location.href = "/reviews";
    }
  });

  // Auto-dismiss alerts
  document.querySelectorAll("[data-autohide]").forEach(function (el) {
    setTimeout(function () {
      el.style.opacity = "0";
      el.style.transition = "opacity .4s";
      setTimeout(function () { el.remove(); }, 400);
    }, 4000);
  });
})();
