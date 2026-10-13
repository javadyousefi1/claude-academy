/* Small helpers for the handout: language switch, "I've read this" checkmarks with progress,
   copy buttons, catalog search, and the current-lesson marker in the side index.
   Everything is optional: the pages read fine without JavaScript. */
(function () {
  "use strict";
  var root = document.documentElement;

  function store(key, value) {
    try {
      if (value === undefined) return localStorage.getItem(key);
      localStorage.setItem(key, value);
    } catch (e) { return null; }
    return null;
  }

  /* ---------- language */
  function setLang(lang) {
    root.setAttribute("data-lang", lang);
    store("ca-lang", lang);
    document.querySelectorAll("[data-set-lang]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-set-lang") === lang));
    });
  }
  setLang(root.getAttribute("data-lang") || "both");
  document.querySelectorAll("[data-set-lang]").forEach(function (b) {
    b.addEventListener("click", function () { setLang(b.getAttribute("data-set-lang")); });
  });

  /* ---------- read checkmarks + progress */
  var done = {};
  try { (JSON.parse(store("ca-done") || "[]") || []).forEach(function (id) { done[id] = true; }); } catch (e) { done = {}; }

  function saveDone() { store("ca-done", JSON.stringify(Object.keys(done))); }

  function countFor(slug) {
    var prefix = slug + "--", n = 0;
    Object.keys(done).forEach(function (id) { if (id.indexOf(prefix) === 0) n++; });
    return n;
  }
  function toFa(n) { return String(n).replace(/\d/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[d]; }); }

  function refreshProgress() {
    document.querySelectorAll("[data-progress-for]").forEach(function (el) {
      var total = parseInt(el.getAttribute("data-total"), 10) || 0;
      var n = Math.min(countFor(el.getAttribute("data-progress-for")), total);
      var pct = total ? Math.round((n / total) * 100) : 0;
      var bar = el.querySelector(".progress-bar > span, .card-progress > span");
      if (bar) bar.style.width = pct + "%";
      var text = el.querySelector(".progress-text");
      if (text) text.textContent = toFa(n) + " از " + toFa(total) + " خوانده شده" + (n === total && total ? " — آفرین!" : "");
    });
    document.querySelectorAll("[data-done]").forEach(function (box) {
      var id = box.getAttribute("data-done");
      var item = document.getElementById(id);
      if (item) item.classList.toggle("is-done", !!done[id]);
      var link = document.querySelector('[data-toc="' + id + '"]');
      if (link) link.classList.toggle("is-done", !!done[id]);
    });
  }

  document.querySelectorAll("[data-done]").forEach(function (box) {
    var id = box.getAttribute("data-done");
    box.checked = !!done[id];
    box.addEventListener("change", function () {
      if (box.checked) done[id] = true; else delete done[id];
      saveDone();
      refreshProgress();
    });
  });
  refreshProgress();

  /* ---------- copy buttons */
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest ? ev.target.closest(".copy") : null;
    if (!btn) return;
    var target = btn.getAttribute("data-copy-target");
    var source = target === "code"
      ? btn.closest("figure").querySelector("pre code")
      : btn.parentElement.querySelector(target);
    if (!source) return;
    var text = source.innerText.trim();
    var label = btn.textContent;
    function ok() {
      btn.classList.add("copied");
      btn.textContent = btn.closest(".en") ? "Copied" : "کپی شد";
      setTimeout(function () { btn.classList.remove("copied"); btn.textContent = label; }, 1600);
    }
    function fallback() {
      var range = document.createRange();
      range.selectNodeContents(source);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      btn.textContent = btn.closest(".en") ? "Selected: press Ctrl+C" : "انتخاب شد؛ Ctrl+C را بزن";
      setTimeout(function () { btn.textContent = label; }, 2400);
    }
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(ok, fallback);
      } else { fallback(); }
    } catch (e) { fallback(); }
  });

  /* ---------- search filters */
  function norm(s) {
    return (s || "").toLowerCase().replace(/ي/g, "ی").replace(/ك/g, "ک").replace(/‌/g, " ").replace(/\s+/g, " ").trim();
  }
  document.querySelectorAll("input[data-filter]").forEach(function (input) {
    var items = Array.prototype.slice.call(document.querySelectorAll(input.getAttribute("data-filter")));
    input.addEventListener("input", function () {
      var q = norm(input.value);
      items.forEach(function (el) {
        var hay = norm(el.getAttribute("data-search") || el.textContent);
        el.hidden = q !== "" && hay.indexOf(q) === -1;
      });
      document.querySelectorAll(".group").forEach(function (g) {
        var any = g.querySelector(".card:not([hidden])");
        g.hidden = !any;
      });
    });
  });

  /* ---------- side index: close on small screens, mark the lesson in view */
  var toc = document.querySelector(".side-toc details");
  if (toc && window.matchMedia("(max-width: 1100px)").matches) toc.removeAttribute("open");
  var links = {};
  document.querySelectorAll("[data-toc]").forEach(function (a) { links[a.getAttribute("data-toc")] = a; });
  if ("IntersectionObserver" in window && Object.keys(links).length) {
    var current = null;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        var a = links[en.target.id];
        if (!a || a === current) return;
        if (current) current.removeAttribute("aria-current");
        a.setAttribute("aria-current", "true");
        current = a;
      });
    }, { rootMargin: "-20% 0px -70% 0px" });
    document.querySelectorAll("article.item").forEach(function (el) { io.observe(el); });
  }

  /* ---------- code highlighting (highlight.js is loaded only on pages with code) */
  if (window.hljs) {
    document.querySelectorAll("figure.code pre code").forEach(function (el) {
      if (!/language-(text|plain)/.test(el.className)) {
        try { window.hljs.highlightElement(el); } catch (e) { /* plain text is fine */ }
      }
    });
  }
})();
