// Applies the saved ASTRA colour theme before the first paint (loaded synchronously in <head>; external file because
// the Content-Security-Policy forbids inline scripts). Mirrors src/lib/theme.ts.
(function () {
  try {
    var t = localStorage.getItem("astra.theme");
    if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
    var dark = t === "dark" || (t !== "light" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
    var m = document.querySelector('meta[name="theme-color"]');
    if (m) m.setAttribute("content", dark ? "#11131B" : "#F4F8FF");
  } catch (e) { /* storage unavailable: System default */ }
})();
