// Dialogs
document.querySelectorAll("[data-open]").forEach((btn) => {
  btn.addEventListener("click", () => document.getElementById(btn.dataset.open).showModal());
});
document.querySelectorAll("dialog.modal").forEach((dlg) => {
  dlg.querySelectorAll("[data-close]").forEach((btn) =>
    btn.addEventListener("click", () => dlg.close()));
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
});
const initial = document.body.dataset.dlg;
if (initial) {
  const dlg = document.getElementById("dlg-" + initial);
  if (dlg) dlg.showModal();
}

// Inline form toggles (income edit, group rename, add forms)
document.querySelectorAll("[data-toggle]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const target = document.querySelector(btn.dataset.toggle);
    target.classList.toggle("hidden");
    const input = target.querySelector("input:not([type=hidden])");
    if (input && !target.classList.contains("hidden")) input.focus();
  });
});

// Personal preferences: apply instantly, persist in the background
function savePref(field, value) {
  const body = new URLSearchParams();
  body.set(field, value);
  fetch("/prefs", { method: "POST", body });
}

document.querySelectorAll("[data-accent-value]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const value = btn.dataset.accentValue;
    if (value === "teal") {
      document.documentElement.removeAttribute("data-accent");
    } else {
      document.documentElement.setAttribute("data-accent", value);
    }
    document.querySelectorAll("[data-accent-value]").forEach((x) =>
      x.classList.toggle("active", x === btn));
    savePref("accent", value);
  });
});

document.querySelectorAll("[data-theme-value]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const value = btn.dataset.themeValue;
    if (value === "system") {
      document.documentElement.removeAttribute("data-theme");
    } else {
      document.documentElement.setAttribute("data-theme", value);
    }
    document.querySelectorAll("[data-theme-value]").forEach((x) =>
      x.classList.toggle("active", x === btn));
    savePref("theme", value);
  });
});
