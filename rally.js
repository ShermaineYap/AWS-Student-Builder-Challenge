// Rally: play badminton against a stroke-forecasting GRU.
// The GRU forward pass is written by hand below, so the browser needs no ML library.
(function () {
  "use strict";

  var LABEL = {
    "short service": "Short serve", "long service": "Long serve", "net shot": "Net shot",
    "lob": "Lob", "clear": "Clear", "drop": "Drop", "smash": "Smash",
    "defensive shot": "Defensive block", "drive": "Drive", "push/rush": "Push / rush"
  };
  var SERVES = ["short service", "long service"];
  var RALLY_SHOTS = ["net shot", "lob", "clear", "drop", "smash", "defensive shot", "drive", "push/rush"];
  // Where each shot tends to land, as distance from the net in court units (net is 324 from each baseline).
  var DEPTH = {
    "short service": [55, 110], "net shot": [25, 85], "drop": [60, 130], "defensive shot": [40, 120],
    "push/rush": [100, 190], "drive": [120, 220], "smash": [110, 210],
    "lob": [250, 305], "clear": [250, 310], "long service": [270, 312]
  };
  var POINTS_TO_WIN = 5;
  var UNREAD_TO_WIN_POINT = 3;
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- model ----------
  var M = null; // loaded model.json
  var types = SERVES.concat(RALLY_SHOTS); // overwritten by model order
  var personal = {}; // personal[incomingShot][reply] = count, learned this session

  function sigmoid(x) { return 1 / (1 + Math.exp(-x)); }
  function matVec(W, v) {
    var out = new Array(W.length);
    for (var i = 0; i < W.length; i++) {
      var s = 0, row = W[i];
      for (var j = 0; j < v.length; j++) s += row[j] * v[j];
      out[i] = s;
    }
    return out;
  }
  // Same equations as torch.nn.GRU (gate order r, z, n).
  function gruLogits(tokens) {
    var H = M.hidden, h = new Array(H).fill(0);
    for (var t = 0; t < tokens.length; t++) {
      var x = M.embedding[tokens[t]];
      var gi = matVec(M.W_ih, x), gh = matVec(M.W_hh, h);
      var nh = new Array(H);
      for (var k = 0; k < H; k++) {
        var r = sigmoid(gi[k] + M.b_ih[k] + gh[k] + M.b_hh[k]);
        var z = sigmoid(gi[H + k] + M.b_ih[H + k] + gh[H + k] + M.b_hh[H + k]);
        var n = Math.tanh(gi[2 * H + k] + M.b_ih[2 * H + k] + r * (gh[2 * H + k] + M.b_hh[2 * H + k]));
        nh[k] = (1 - z) * n + z * h[k];
      }
      h = nh;
    }
    var logits = matVec(M.W_out, h);
    for (var c = 0; c < logits.length; c++) logits[c] += M.b_out[c];
    return logits;
  }
  function softmax(a) {
    var m = Math.max.apply(null, a), e = a.map(function (v) { return Math.exp(v - m); });
    var s = e.reduce(function (p, q) { return p + q; }, 0);
    return e.map(function (v) { return v / s; });
  }
  function contextTokens(history) {
    var w = M ? M.window : 4, ctx = history.slice(-w).map(function (t) { return types.indexOf(t) + 1; });
    while (ctx.length < w) ctx.unshift(0);
    return ctx;
  }
  // Pro-play probability of every shot type coming next.
  function proProbs(history) {
    if (!M) return types.map(function () { return 1 / types.length; });
    return softmax(gruLogits(contextTokens(history)));
  }
  function replyOptions(incoming) {
    var opts = (M && M.replies[incoming]) || RALLY_SHOTS;
    opts = opts.filter(function (t) { return RALLY_SHOTS.indexOf(t) >= 0; });
    return opts.length >= 2 ? opts : RALLY_SHOTS.slice();
  }
  // Distribution over the legal options, blending pro play with what this visitor has done before.
  function predictVisitor(history, options) {
    var pro = proProbs(history), incoming = history[history.length - 1];
    var mine = personal[incoming] || {}, n = 0;
    options.forEach(function (o) { n += mine[o] || 0; });
    var alpha = Math.min(0.65, n / (n + 3)); // trust your habits more as evidence grows
    var raw = options.map(function (o) {
      var p = pro[types.indexOf(o)];
      var q = n ? ((mine[o] || 0) + 0.5) / (n + 0.5 * options.length) : 0;
      return (1 - alpha) * p + alpha * q;
    });
    var s = raw.reduce(function (a, b) { return a + b; }, 0);
    return { options: options, probs: raw.map(function (v) { return v / s; }), alpha: alpha };
  }
  function sample(options, probs, temp) {
    var w = probs.map(function (p) { return Math.pow(p, 1 / temp); });
    var s = w.reduce(function (a, b) { return a + b; }, 0), r = Math.random() * s;
    for (var i = 0; i < w.length; i++) { r -= w[i]; if (r <= 0) return options[i]; }
    return options[options.length - 1];
  }
  function opponentShot(history) {
    var incoming = history[history.length - 1];
    var options = incoming ? replyOptions(incoming) : SERVES;
    var pro = proProbs(history);
    var probs = options.map(function (o) { return pro[types.indexOf(o)] + 1e-6; });
    return sample(options, probs, 0.8);
  }

  // ---------- DOM ----------
  var dlg = document.getElementById("rally");
  var $ = function (id) { return document.getElementById(id); };
  var shotsEl = $("shots"), barsEl = $("bars"), guessTitle = $("guess-title"), startBtn = $("start-btn");
  var shuttle = $("shuttle"), lastShotEl = $("last-shot"), statusEl = $("rally-status");
  var resultEl = $("result");

  var S; // match state
  function newMatch() {
    S = { you: 0, model: 0, shots: 0, reads: 0, history: [], unread: 0, busy: false, over: false, guess: null, pos: { x: 150, y: 90 } };
    $("score-you").textContent = "0"; $("score-model").textContent = "0";
    statusEl.textContent = "First to " + POINTS_TO_WIN;
    resultEl.hidden = true; barsEl.innerHTML = ""; shotsEl.innerHTML = ""; lastShotEl.textContent = "";
    guessTitle.textContent = "Press start. The model serves.";
    startBtn.hidden = false; startBtn.textContent = "Start the match";
    placeShuttle(150, 90);
  }

  function placeShuttle(x, y, rot) {
    shuttle.setAttribute("transform", "translate(" + x.toFixed(1) + "," + y.toFixed(1) + ") rotate(" + (rot || 0) + ") scale(1)");
  }
  function landingPoint(shot, toVisitor) {
    var d = DEPTH[shot] || [100, 200];
    var dist = d[0] + Math.random() * (d[1] - d[0]);
    return { x: 40 + Math.random() * 220, y: toVisitor ? 330 + dist : 330 - dist };
  }
  function fly(shot, toVisitor) {
    var from = S.pos, to = landingPoint(shot, toVisitor);
    S.pos = to;
    var rot = toVisitor ? 180 : 0;
    if (reduceMotion) { placeShuttle(to.x, to.y, rot); return Promise.resolve(); }
    var high = ["lob", "clear", "long service"].indexOf(shot) >= 0;
    var dur = shot === "smash" ? 320 : high ? 760 : 520, peak = high ? 0.9 : shot === "smash" ? 0.1 : 0.4;
    return new Promise(function (res) {
      var t0 = performance.now();
      (function step(now) {
        var t = Math.min(1, (now - t0) / dur), e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
        var x = from.x + (to.x - from.x) * e, y = from.y + (to.y - from.y) * e;
        var s = 1 + peak * Math.sin(Math.PI * t);
        shuttle.setAttribute("transform", "translate(" + x.toFixed(1) + "," + y.toFixed(1) + ") rotate(" + rot + ") scale(" + s.toFixed(3) + ")");
        if (t < 1) requestAnimationFrame(step); else res();
      })(t0);
    });
  }

  function renderBars(pred, picked) {
    var order = pred.options.map(function (o, i) { return i; }).sort(function (a, b) { return pred.probs[b] - pred.probs[a]; });
    barsEl.innerHTML = "";
    order.forEach(function (i, rank) {
      var o = pred.options[i], pct = Math.round(pred.probs[i] * 100);
      var row = document.createElement("div");
      row.className = "bar" + (rank === 0 ? " top" : "") + (o === picked ? " picked" : "");
      row.innerHTML = '<span class="bar-name"></span><span class="bar-track"><span class="bar-fill" style="width:0"></span></span><span class="bar-pct">' + pct + "%</span>";
      row.querySelector(".bar-name").textContent = LABEL[o] + (o === picked ? " (you)" : "");
      barsEl.appendChild(row);
      requestAnimationFrame(function () { row.querySelector(".bar-fill").style.width = pct + "%"; });
    });
  }

  function setShots(options) {
    shotsEl.innerHTML = "";
    options.forEach(function (o, i) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "shot"; b.dataset.shot = o;
      b.innerHTML = "<kbd>" + (i + 1) + "</kbd><span></span>";
      b.querySelector("span").textContent = LABEL[o];
      b.setAttribute("aria-label", LABEL[o] + ", key " + (i + 1));
      b.addEventListener("click", function () { play(o); });
      shotsEl.appendChild(b);
    });
  }
  function disableShots() { shotsEl.querySelectorAll("button").forEach(function (b) { b.disabled = true; }); }

  // ---------- game loop ----------
  async function opponentHits() {
    var shot = opponentShot(S.history);
    S.history.push(shot);
    lastShotEl.textContent = "Model plays: " + LABEL[shot];
    await fly(shot, true);
    visitorTurn();
  }

  function visitorTurn() {
    var incoming = S.history[S.history.length - 1];
    var options = replyOptions(incoming);
    var pred = predictVisitor(S.history, options);
    // Argmax with a random tie-break (ties only happen if the model file failed to load).
    var best = 0, jit = pred.probs.map(function (p) { return p + Math.random() * 1e-9; });
    jit.forEach(function (p, i) { if (p > jit[best]) best = i; });
    S.guess = { pred: pred, pick: pred.options[best] };
    barsEl.innerHTML = "";
    guessTitle.innerHTML = '<span class="sealed">🔒 The model has locked in its guess.</span><br>Your shot:';
    setShots(options);
    S.busy = false;
    var first = shotsEl.querySelector("button");
    if (first && !dlg.contains(document.activeElement)) first.focus({ preventScroll: true });
  }

  async function play(shot) {
    if (S.busy || S.over) return;
    S.busy = true; disableShots();
    var g = S.guess, incoming = S.history[S.history.length - 1];
    personal[incoming] = personal[incoming] || {};
    personal[incoming][shot] = (personal[incoming][shot] || 0) + 1;
    S.shots++;
    S.history.push(shot);
    renderBars(g.pred, shot);
    var read = g.pick === shot;
    var pct = Math.round(g.pred.probs[g.pred.options.indexOf(g.pick)] * 100);
    if (read) {
      S.reads++;
      guessTitle.textContent = "Read you. It called " + LABEL[g.pick] + " at " + pct + "%.";
      lastShotEl.textContent = "You play: " + LABEL[shot];
      await fly(shot, false);
      return point("model");
    }
    S.unread++;
    guessTitle.textContent = "It guessed " + LABEL[g.pick] + " (" + pct + "%). You played " + LABEL[shot] + ".";
    lastShotEl.textContent = "You play: " + LABEL[shot];
    await fly(shot, false);
    if (S.unread >= UNREAD_TO_WIN_POINT) return point("you");
    statusEl.textContent = S.unread + " of " + UNREAD_TO_WIN_POINT + " past it";
    await wait(350);
    opponentHits();
  }

  function wait(ms) { return new Promise(function (r) { setTimeout(r, reduceMotion ? 0 : ms); }); }

  async function point(who) {
    S[who]++;
    var el = $(who === "you" ? "score-you" : "score-model");
    el.textContent = S[who];
    el.classList.remove("flash-model"); void el.offsetWidth; el.classList.add("flash-model");
    statusEl.textContent = who === "you" ? "Your point" : "Model's point";
    if (S.you >= POINTS_TO_WIN || S.model >= POINTS_TO_WIN) return finish();
    shotsEl.innerHTML = "";
    await wait(1100);
    S.history = []; S.unread = 0;
    statusEl.textContent = "First to " + POINTS_TO_WIN;
    S.pos = { x: 40 + Math.random() * 220, y: 60 };
    placeShuttle(S.pos.x, S.pos.y);
    opponentHits();
  }

  function finish() {
    S.over = true; shotsEl.innerHTML = "";
    var rate = S.shots ? Math.round((S.reads / S.shots) * 100) : 0;
    $("result-title").textContent = S.you > S.model ? "You beat it " + S.you + "–" + S.model : "The model wins " + S.model + "–" + S.you;
    $("result-body").textContent = "It read " + S.reads + " of your " + S.shots + " shots (" + rate + "%). " +
      (S.you > S.model ? "You were harder to predict than a pro rally." : "Humans fall into habits fast, and it was learning yours as you played.");
    $("result-global").textContent = "";
    resultEl.hidden = false;
    $("again-btn").focus({ preventScroll: true });
    report({ shots: S.shots, reads: S.reads, you: S.you, model: S.model });
  }

  // ---------- leaderboard (optional; the game never depends on it) ----------
  function report(r) {
    var api = (window.RALLY_API || "").replace(/\/$/, "");
    if (!api) return;
    var ctrl = new AbortController(); setTimeout(function () { ctrl.abort(); }, 4000);
    fetch(api + "/results", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify(r), signal: ctrl.signal
    }).then(function (res) { return res.ok ? res.json() : null; })
      .then(function (g) {
        if (!g || !g.shots) return;
        var rate = Math.round((g.reads / g.shots) * 100);
        $("result-global").textContent = "Across " + g.matches.toLocaleString() + " matches played on this site, the model has read " +
          rate + "% of visitors' shots, and visitors have won " + g.visitorWins.toLocaleString() + " of them.";
      })
      .catch(function () { /* offline or blocked: keep the local result only */ });
  }

  // ---------- wiring ----------
  function open() {
    if (!S || S.over) newMatch();
    if (typeof dlg.showModal === "function") dlg.showModal(); else dlg.setAttribute("open", "");
    if (!startBtn.hidden) startBtn.focus({ preventScroll: true });
    dlg.scrollTop = 0;
  }
  function close() { if (dlg.open) dlg.close(); }
  document.querySelectorAll("[data-open-rally]").forEach(function (b) { b.addEventListener("click", open); });
  document.querySelectorAll("[data-close-rally]").forEach(function (b) { b.addEventListener("click", close); });
  dlg.addEventListener("click", function (e) { if (e.target === dlg) close(); });
  startBtn.addEventListener("click", function () {
    startBtn.hidden = true;
    opponentHits();
  });
  $("again-btn").addEventListener("click", function () { newMatch(); startBtn.hidden = true; opponentHits(); });
  $("how-btn").addEventListener("click", function () {
    var how = $("how"), btn = $("how-btn");
    how.hidden = !how.hidden; btn.setAttribute("aria-expanded", String(!how.hidden));
  });
  document.addEventListener("keydown", function (e) {
    if (!dlg.open || S.busy || S.over || e.altKey || e.ctrlKey || e.metaKey) return;
    var n = parseInt(e.key, 10);
    if (n >= 1 && n <= 9) {
      var b = shotsEl.querySelectorAll("button")[n - 1];
      if (b && !b.disabled) { e.preventDefault(); b.click(); }
    }
  });

  function useModel(m) {
    M = m; types = m.types;
    var f = function (x) { return x.toLocaleString(); };
    $("m-train").textContent = f(m.metrics.train_predictions);
    $("m-test").textContent = f(m.metrics.test_predictions);
    $("m-top1").textContent = Math.round(m.metrics.gru.top1 * 100) + "%";
    $("m-top3").textContent = Math.round(m.metrics.gru.top3 * 100) + "%";
  }
  // model.js (a script tag) works even from file://; model.json is the backup route.
  if (window.RALLY_MODEL) useModel(window.RALLY_MODEL);
  else fetch("assets/model/model.json")
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(useModel)
    .catch(function () { /* no model: the game still runs and learns only from the visitor */ });

  newMatch();
  // Exposed for the parity test only.
  window.__rally = { gruLogits: gruLogits, setModel: function (m) { M = m; types = m.types; } };
})();
