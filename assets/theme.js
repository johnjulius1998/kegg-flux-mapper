(function () {
  var KEY = "kfm-theme";
  var mq = window.matchMedia("(prefers-color-scheme: dark)");

  function stored() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }
  function apply() {
    var theme = stored() || (mq.matches ? "dark" : "light");
    document.documentElement.setAttribute("data-bs-theme", theme);
  }

  apply();
  mq.addEventListener("change", apply);

  window.kfmToggleTheme = function () {
    var next = document.documentElement.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
    try { localStorage.setItem(KEY, next); } catch (e) {}
    document.documentElement.setAttribute("data-bs-theme", next);
  };
})();
