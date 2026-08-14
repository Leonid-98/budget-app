// All handlers use event delegation so they keep working after htmx
// swaps #page (boosted links/forms replace that subtree on every action).

function openDialog(id) {
  const dlg = document.getElementById(id);
  if (dlg && !dlg.open) dlg.showModal();
}

function setPref(field, value, btn) {
  const attr = field === "accent" ? "data-accent" : "data-theme";
  const defaultValue = field === "accent" ? "teal" : "system";
  if (value === defaultValue) {
    document.documentElement.removeAttribute(attr);
  } else {
    document.documentElement.setAttribute(attr, value);
  }
  btn.closest(".accent-row").querySelectorAll("[data-" + field + "-value]")
    .forEach((x) => x.classList.toggle("active", x === btn));
  const body = new URLSearchParams();
  body.set(field, value);
  fetch("/prefs", { method: "POST", body });
}

document.addEventListener("click", (e) => {
  const opener = e.target.closest("[data-open]");
  if (opener) return openDialog(opener.dataset.open);

  const closer = e.target.closest("[data-close]");
  if (closer) return closer.closest("dialog").close();

  if (e.target instanceof HTMLDialogElement) return e.target.close(); // backdrop

  const toggler = e.target.closest("[data-toggle]");
  if (toggler) {
    const target = document.querySelector(toggler.dataset.toggle);
    target.classList.toggle("hidden");
    const input = target.querySelector("input:not([type=hidden])");
    if (input && !target.classList.contains("hidden")) input.focus();
    return;
  }

  const accentBtn = e.target.closest("[data-accent-value]");
  if (accentBtn) return setPref("accent", accentBtn.dataset.accentValue, accentBtn);

  const themeBtn = e.target.closest("[data-theme-value]");
  if (themeBtn) return setPref("theme", themeBtn.dataset.themeValue, themeBtn);
});

// Reopen the dialog requested by the server (?dlg=...) — on first load and
// after every htmx swap, so e.g. Settings stays open across its own actions.
function openFromState() {
  const page = document.getElementById("page");
  if (page && page.dataset.dlg) openDialog("dlg-" + page.dataset.dlg);
}
document.addEventListener("DOMContentLoaded", openFromState);
document.body.addEventListener("htmx:afterSwap", openFromState);
