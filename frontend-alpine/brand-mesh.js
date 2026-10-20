/* CoMesh — Kopf-Animation: ein winziges Mesh.
 *
 * Miniatur der Szene aus dem Erklär-Deck: Knoten, verbunden durch Leitungen, auf
 * denen Datenpakete wandern. Zwei Größenordnungen von Knoten (Hubs und Blätter),
 * damit es nach Netz aussieht und nicht nach Perlenkette.
 *
 * Regeln:
 *   - Farben aus den CSS-Variablen (Hell/Dunkel automatisch richtig)
 *   - prefers-reduced-motion: genau ein Standbild, keine Schleife
 *   - Hintergrund-Tab: Zeichnen pausiert
 *   - devicePixelRatio-skaliert, maximal 30 Bilder/s
 */
(function () {
  "use strict";

  var KNOTEN = 9;
  var PAKETE = 4;
  var FPS_MAX = 30;
  var laeuft = false;
  var raf = 0;
  var letzteZeit = 0;
  var farben = {};
  var knoten = [];
  var kanten = [];
  var pakete = [];

  function cssVar(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  function farbenLesen() {
    farben.linie = cssVar("--line-strong", "rgba(255,255,255,0.16)");
    farben.knoten = cssVar("--text-mute", "rgba(255,255,255,0.45)");
    farben.akzent = cssVar("--brass-soft", "#e2c885");
    farben.aktiv = cssVar("--brand", "#c9a24a");
  }

  function knotenBauen(w, h) {
    knoten = [];
    kanten = [];
    pakete = [];
    // Knoten über die ganze Fläche verteilen, nicht in einer Mittellinie:
    // zwei Reihen mit Versatz, damit Leitungen schräg laufen.
    for (var i = 0; i < KNOTEN; i++) {
      var spalte = i % 5;
      var reihe = i < 5 ? 0 : 1;
      var x = (spalte + 0.5) / 5 * w + (reihe ? w / 10 : 0) + (Math.random() - 0.5) * (w / 16);
      var y = h * (reihe ? 0.72 : 0.28) + (Math.random() - 0.5) * (h * 0.26);
      var hub = i % 4 === 0;
      knoten.push({
        x0: Math.min(w - 6, Math.max(6, x)), y0: Math.min(h - 6, Math.max(6, y)),
        phase: Math.random() * Math.PI * 2,
        amp: 1.2 + Math.random() * 2.0,
        r: hub ? 2.5 : 1.5 + Math.random() * 0.6,
        hub: hub,
        x: 0, y: 0,
      });
      knoten[i].x = knoten[i].x0;
      knoten[i].y = knoten[i].y0;
    }
    // Kanten: benachbarte Knoten gleicher Reihe, plus Kreuzverbindungen zur anderen Reihe
    for (var a = 0; a < 5; a++) {
      if (a < 4) kanten.push([a, a + 1]);
      if (a >= 4) { /* Reihe 2 */ }
    }
    for (var b = 5; b < KNOTEN; b++) {
      if (b < KNOTEN - 1) kanten.push([b, b + 1]);
    }
    for (var c = 0; c < 4; c++) kanten.push([c, 5 + c]);          // Kreuz
    kanten.push([1, 7]);
    kanten.push([3, 6]);

    for (var p = 0; p < PAKETE; p++) {
      pakete.push({
        kante: Math.floor(Math.random() * kanten.length),
        t: Math.random(),
        speed: 0.14 + Math.random() * 0.16,
      });
    }
  }

  function zeichnen(dt, statisch) {
    var cv = document.getElementById("brand-mesh");
    if (!cv) return;
    var ctx = cv.getContext("2d");
    var dpr = window.devicePixelRatio || 1;
    var w = cv.clientWidth;
    var h = cv.clientHeight;
    if (!w || !h) return;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(h * dpr);
      knotenBauen(w, h);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    // Größenstufe aus dem Markup: 1 = Kopfanimation, 3 = Hintergrundfläche.
    var stufe = parseFloat(cv.dataset.meshScale || "1") || 1;

    var t = statisch ? 0.8 : performance.now() / 1000;
    for (var i = 0; i < knoten.length; i++) {
      var k = knoten[i];
      k.x = k.x0 + Math.sin(t * 0.45 + k.phase) * k.amp;
      k.y = k.y0 + Math.cos(t * 0.36 + k.phase * 1.3) * k.amp;
    }

    // Leitungen
    for (var e = 0; e < kanten.length; e++) {
      var a = knoten[kanten[e][0]], b = knoten[kanten[e][1]];
      var dx = b.x - a.x, dy = b.y - a.y;
      var d = Math.sqrt(dx * dx + dy * dy);
      var naehe = Math.max(0, 1 - d / (w * 0.6));
      var mitPaket = pakete.some(function (pk) { return pk.kante === e; });
      // Leitungen bekommen einen Verlauf statt einer flachen Farbe: das Auge liest
      // dann eine Ader mit Licht drin, keinen gezogenen Strich. Aktive Adern glühen.
      if (mitPaket) {
        var verlauf = ctx.createLinearGradient(a.x, a.y, b.x, b.y);
        verlauf.addColorStop(0, farben.aktiv);
        verlauf.addColorStop(0.5, farben.akzent);
        verlauf.addColorStop(1, farben.aktiv);
        ctx.strokeStyle = verlauf;
        ctx.shadowBlur = 6 * stufe;
        ctx.shadowColor = farben.akzent;
      } else {
        ctx.strokeStyle = farben.linie;
      }
      ctx.lineWidth = (mitPaket ? 1.1 : 1) * stufe;
      ctx.globalAlpha = 0.14 + naehe * 0.34 + (mitPaket ? 0.16 : 0);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.quadraticCurveTo(a.x + dx * 0.5, a.y + dy * 0.5 - 5 * naehe * stufe, b.x, b.y);
      ctx.stroke();
      ctx.shadowBlur = 0;
    }

    // Knoten: Hubs mit Ring, Blätter als Punkt
    for (var n = 0; n < knoten.length; n++) {
      var kn = knoten[n];
      ctx.globalAlpha = 0.62;
      ctx.fillStyle = farben.knoten;
      ctx.beginPath();
      ctx.arc(kn.x, kn.y, kn.r * stufe, 0, Math.PI * 2);
      ctx.fill();
      if (kn.hub) {
        ctx.globalAlpha = 0.85;
        ctx.strokeStyle = farben.akzent;
        ctx.lineWidth = 0.9 * stufe;
        ctx.beginPath();
        ctx.arc(kn.x, kn.y, kn.r * stufe + 2.6 * stufe, 0, Math.PI * 2);
        ctx.stroke();
      }
    }

    // Datenpakete
    for (var pi = 0; pi < pakete.length; pi++) {
      var pk = pakete[pi];
      if (!statisch) {
        pk.t += dt * pk.speed;
        if (pk.t > 1) { pk.t = 0; pk.kante = Math.floor(Math.random() * kanten.length); }
      }
      var pa = knoten[kanten[pk.kante][0]], pb = knoten[kanten[pk.kante][1]];
      var mx = pa.x + (pb.x - pa.x) * 0.5;
      var my = pa.y + (pb.y - pa.y) * 0.5 - 3;
      var mt = 1 - pk.t;
      var px = mt * mt * pa.x + 2 * mt * pk.t * mx + pk.t * pk.t * pb.x;
      var py = mt * mt * pa.y + 2 * mt * pk.t * my + pk.t * pk.t * pb.y;
      ctx.globalAlpha = 0.95;
      ctx.fillStyle = farben.akzent;
      ctx.shadowBlur = 9 * stufe;
      ctx.shadowColor = farben.akzent;
      ctx.beginPath();
      ctx.arc(px, py, 1.9 * stufe, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
    }
    ctx.globalAlpha = 1;
  }

  function schleife(jetzt) {
    if (!laeuft) return;
    raf = requestAnimationFrame(schleife);
    if (jetzt - letzteZeit < 1000 / FPS_MAX) return;
    var dt = Math.min(0.05, (jetzt - letzteZeit) / 1000 || 0.033);
    letzteZeit = jetzt;
    zeichnen(dt, false);
  }

  function reduzierteBewegung() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function starten() {
    var cv = document.getElementById("brand-mesh");
    if (!cv) return false;
    if (cv.dataset.bereit === "1") return true;
    cv.dataset.bereit = "1";
    farbenLesen();
    knotenBauen(cv.clientWidth || 232, cv.clientHeight || 48);
    // Erst ein Standbild: das setzt den Zeichenpuffer auf die richtige Größe und
    // füllt die Fläche auch dann, wenn die Schleife nicht anläuft (versteckter Tab).
    zeichnen(0, true);
    if (reduzierteBewegung()) {
      return true;
    }
    laeuft = true;
    letzteZeit = 0;
    raf = requestAnimationFrame(schleife);
    return true;
  }

  function themenWechselBeobachten() {
    if (typeof MutationObserver === "undefined") return;
    new MutationObserver(function () {
      farbenLesen();
      var cv = document.getElementById("brand-mesh");
      if (cv && !laeuft) zeichnen(0, true);
    }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  }

  // Die Topbar wird ueber x-html gebaut und bei jedem Sprachwechsel ersetzt.
  // Dann ist das Canvas ein NEUES Element: der Beobachter muss weiterlaufen und
  // das neue Element entweder anwerfen (Schleife) oder wenigstens einmal
  // statisch zeichnen (reduzierte Bewegung). Vorher disconnectete er sich nach
  // dem ersten Erfolg — nach einem Sprachwechsel blieb die Grafik leer.
  function beobachten() {
    starten();
    if (typeof MutationObserver === "undefined") return;
    new MutationObserver(function () {
      var cv = document.getElementById("brand-mesh");
      if (!cv) return;
      if (cv.dataset.bereit === "1") return;
      cv.dataset.bereit = "1";
      if (!laeuft) zeichnen(0, true);
    }).observe(document.body, { childList: true, subtree: true });
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      laeuft = false;
      cancelAnimationFrame(raf);
    } else if (document.getElementById("brand-mesh") && !reduzierteBewegung()) {
      laeuft = true;
      letzteZeit = 0;
      raf = requestAnimationFrame(schleife);
    }
  });

  window.addEventListener("resize", function () {
    var cv = document.getElementById("brand-mesh");
    if (cv) { cv.dataset.bereit = ""; knotenBauen(cv.clientWidth || 232, cv.clientHeight || 48); }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { themenWechselBeobachten(); beobachten(); });
  } else {
    themenWechselBeobachten();
    beobachten();
  }

  window.mountBrandMesh = starten;
})();
