/* Ruban.S portfolio - public site behaviour (vanilla JavaScript, no dependencies) */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- navigation ---------- */
  var nav = $("#nav"), toggle = $("#navToggle"), menu = $("#navMenu");
  function closeMenu() {
    if (!menu) return;
    menu.classList.remove("open");
    toggle.setAttribute("aria-expanded", "false");
    document.body.classList.remove("menu-open");
  }
  if (toggle) {
    toggle.addEventListener("click", function () {
      var open = menu.classList.toggle("open");
      toggle.setAttribute("aria-expanded", String(open));
      document.body.classList.toggle("menu-open", open);
    });
    $$("a", menu).forEach(function (a) { a.addEventListener("click", closeMenu); });
  }
  function onScroll() { if (nav) nav.classList.toggle("scrolled", window.scrollY > 20); }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* ---------- scroll reveal + skill bars ---------- */
  var revealEls = $$(".reveal");
  if ("IntersectionObserver" in window && !reduced) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    revealEls.forEach(function (el, i) {
      el.style.setProperty("--d", ((i % 4) * 0.08) + "s");
      io.observe(el);
    });
  } else {
    revealEls.forEach(function (el) { el.classList.add("in"); });
  }

  /* ---------- active nav link ---------- */
  var spyLinks = {};
  $$("[data-spy]").forEach(function (a) { spyLinks[a.getAttribute("data-spy")] = a; });
  var spyTargets = Object.keys(spyLinks).map(function (id) { return document.getElementById(id); }).filter(Boolean);
  if (spyTargets.length && "IntersectionObserver" in window) {
    var spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          Object.keys(spyLinks).forEach(function (k) { spyLinks[k].classList.toggle("active", k === e.target.id); });
        }
      });
    }, { rootMargin: "-45% 0px -50% 0px" });
    spyTargets.forEach(function (t) { spy.observe(t); });
  }

  /* ---------- typing effect ---------- */
  var typed = $("#typed");
  if (typed && !reduced) {
    var words = (typed.getAttribute("data-words") || "").split("|").filter(Boolean);
    if (words.length) {
      var w = 0, c = 0, deleting = false;
      var tick = function () {
        var word = words[w];
        c += deleting ? -1 : 1;
        typed.textContent = word.slice(0, c);
        var delay = deleting ? 45 : 95;
        if (!deleting && c === word.length) { deleting = true; delay = 1500; }
        else if (deleting && c === 0) { deleting = false; w = (w + 1) % words.length; delay = 350; }
        setTimeout(tick, delay);
      };
      typed.textContent = "";
      setTimeout(tick, 600);
    }
  }

  /* ---------- project category filter ---------- */
  var chips = $$(".chip[data-filter]");
  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      chips.forEach(function (c) { c.classList.toggle("active", c === chip); });
      var f = chip.getAttribute("data-filter");
      $$(".project-card").forEach(function (card) {
        card.hidden = !(f === "all" || card.getAttribute("data-category") === f);
      });
    });
  });

  /* ---------- viewer modal (certificates + screenshots) ---------- */
  var viewer = $("#viewer"), vBody = $("#viewerBody"), vTitle = $("#viewerTitle"), vFoot = $("#viewerFoot");
  var lastFocus = null;
  function openViewer(el) {
    if (!viewer) return;
    lastFocus = document.activeElement;
    var src = el.getAttribute("data-src"), type = el.getAttribute("data-type");
    var title = el.getAttribute("data-title") || "", link = el.getAttribute("data-link");
    vTitle.textContent = title;
    vBody.textContent = "";
    vFoot.textContent = "";
    if (type === "pdf") {
      var frame = document.createElement("iframe");
      frame.src = src; frame.title = title;
      vBody.appendChild(frame);
    } else {
      var img = document.createElement("img");
      img.src = src; img.alt = title;
      vBody.appendChild(img);
    }
    var open = document.createElement("a");
    open.className = "btn btn-ghost btn-sm"; open.href = src; open.target = "_blank"; open.rel = "noopener noreferrer";
    open.innerHTML = '<i class="bi bi-box-arrow-up-right"></i> Open in new tab';
    vFoot.appendChild(open);
    if (link) {
      var verify = document.createElement("a");
      verify.className = "btn btn-primary btn-sm"; verify.href = link; verify.target = "_blank"; verify.rel = "noopener noreferrer";
      verify.innerHTML = '<i class="bi bi-patch-check"></i> Verify credential';
      vFoot.appendChild(verify);
    }
    viewer.hidden = false;
    document.body.style.overflow = "hidden";
    $("#viewerClose").focus();
  }
  function closeViewer() {
    if (!viewer || viewer.hidden) return;
    viewer.hidden = true;
    vBody.textContent = "";
    document.body.style.overflow = "";
    if (lastFocus) lastFocus.focus();
  }
  $$("[data-viewer]").forEach(function (el) { el.addEventListener("click", function () { openViewer(el); }); });
  if (viewer) {
    $("#viewerClose").addEventListener("click", closeViewer);
    viewer.addEventListener("click", function (e) { if (e.target === viewer) closeViewer(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") { closeViewer(); closeMenu(); } });
  }

  /* ---------- contact form ---------- */
  var form = $("#contactForm");
  if (form) {
    var loadedAt = Date.now();
    var status = $("#formStatus"), submit = $("#cSubmit");
    var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
    var emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

    var setErr = function (name, msg) {
      var small = $('.err[data-for="' + name + '"]', form);
      if (small) small.textContent = msg || "";
      var input = form.elements[name];
      if (input) input.closest(".field").classList.toggle("invalid", !!msg);
    };
    var setStatus = function (msg, ok) {
      status.textContent = msg;
      status.className = "form-status " + (ok ? "ok" : "fail");
    };

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var data = {
        name: form.elements.name.value.trim(),
        email: form.elements.email.value.trim(),
        subject: form.elements.subject.value.trim(),
        message: form.elements.message.value.trim(),
        website: form.elements.website.value,
        elapsed_ms: Date.now() - loadedAt
      };
      var bad = false;
      ["name", "email", "subject", "message"].forEach(function (k) { setErr(k, ""); });
      if (data.name.length < 2) { setErr("name", "Please enter your name."); bad = true; }
      if (!emailRe.test(data.email)) { setErr("email", "Please enter a valid email address."); bad = true; }
      if (data.subject.length < 3) { setErr("subject", "Please enter a subject."); bad = true; }
      if (data.message.length < 10) { setErr("message", "Your message should be at least 10 characters."); bad = true; }
      if (bad) { setStatus("Please fix the highlighted fields.", false); return; }

      submit.disabled = true;
      $(".spinner", submit).hidden = false;
      setStatus("Sending...", true);

      fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        body: JSON.stringify(data)
      }).then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (body) { return { res: res, body: body }; });
      }).then(function (r) {
        if (r.res.ok && r.body.ok) {
          setStatus(r.body.message || "Thank you! Your message has been sent.", true);
          form.reset();
          loadedAt = Date.now();
        } else {
          if (r.body.fields) Object.keys(r.body.fields).forEach(function (k) { setErr(k, r.body.fields[k]); });
          var msg = r.body.error || (r.res.status === 429
            ? "You have sent several messages recently. Please try again later."
            : "Something went wrong. Please try again, or email me directly.");
          setStatus(msg, false);
        }
      }).catch(function () {
        setStatus("Network error. Please check your connection and try again.", false);
      }).finally(function () {
        submit.disabled = false;
        $(".spinner", submit).hidden = true;
      });
    });
  }

  /* ---------- GitHub panel ---------- */
  var gh = $("#ghPanel");
  if (gh) {
    var profileBox = $("#ghProfile"), repoBox = $("#ghRepos");
    var LANG_COLORS = { Python: "#3572A5", JavaScript: "#f1e05a", HTML: "#e34c26", CSS: "#a56de2", Java: "#b07219", TypeScript: "#3178c6", "Jupyter Notebook": "#DA5B0B" };
    var el = function (tag, cls, text) {
      var n = document.createElement(tag);
      if (cls) n.className = cls;
      if (text != null) n.textContent = text;
      return n;
    };
    var showError = function (msg) {
      profileBox.textContent = "";
      repoBox.textContent = "";
      repoBox.appendChild(el("div", "gh-error", msg));
      profileBox.style.display = "none";
    };
    var renderGithub = function (d) {
      var u = d.user;
      profileBox.textContent = "";
      if (u.avatar_url) {
        var av = el("img"); av.src = u.avatar_url; av.alt = ""; av.width = 96; av.height = 96; av.loading = "lazy";
        profileBox.appendChild(av);
      }
      profileBox.appendChild(el("h3", "", u.name || u.login));
      profileBox.appendChild(el("p", "handle", "@" + u.login));
      if (u.bio) profileBox.appendChild(el("p", "muted", u.bio));
      var stats = el("div", "gh-stats");
      [["Public repos", u.public_repos], ["Followers", u.followers]].forEach(function (s) {
        var box = el("div"); box.appendChild(el("strong", "", String(s[1]))); box.appendChild(el("span", "", s[0])); stats.appendChild(box);
      });
      profileBox.appendChild(stats);

      repoBox.textContent = "";
      if (!d.repos.length) { repoBox.appendChild(el("div", "gh-error", "No public repositories to show yet.")); return; }
      d.repos.forEach(function (r) {
        var a = el("a", "repo"); a.href = r.html_url; a.target = "_blank"; a.rel = "noopener noreferrer";
        a.appendChild(el("h4", "", r.name));
        a.appendChild(el("p", "", r.description || "No description provided."));
        var meta = el("div", "repo-meta");
        if (r.language) {
          var lang = el("span"); var dot = el("span", "lang-dot");
          dot.style.background = LANG_COLORS[r.language] || "#FF7043";
          lang.appendChild(dot); lang.appendChild(document.createTextNode(r.language)); meta.appendChild(lang);
        }
        if (r.stars) meta.appendChild(el("span", "", "★ " + r.stars));
        a.appendChild(meta);
        repoBox.appendChild(a);
      });
    };
    var loadGithub = function () {
      fetch(gh.getAttribute("data-endpoint"))
        .then(function (res) { return res.json().then(function (b) { return { ok: res.ok, body: b }; }); })
        .then(function (r) {
          if (r.ok && r.body.ok) renderGithub(r.body);
          else showError(r.body.error || "GitHub data is unavailable right now.");
        })
        .catch(function () { showError("GitHub data is unavailable right now."); });
    };
    // Load only when the section approaches the viewport (keeps the first page load fast).
    if ("IntersectionObserver" in window) {
      var ghObs = new IntersectionObserver(function (entries) {
        if (entries[0].isIntersecting) { ghObs.disconnect(); loadGithub(); }
      }, { rootMargin: "300px" });
      ghObs.observe(gh);
    } else { loadGithub(); }
  }
})();
