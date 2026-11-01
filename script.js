// Small page behaviours. The game lives in rally.js.
(function () {
  // Placeholder links that haven't been filled in yet shouldn't jump to the top of the page.
  document.querySelectorAll('a[href="#"]').forEach(function (a) {
    a.addEventListener("click", function (e) { e.preventDefault(); });
  });
})();
