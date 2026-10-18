/* CoMesh — Kopf-Animation: ein winziges Mesh.
 *
 * Gedacht als Miniatur der Szene aus dem Erklär-Deck: ein paar Knoten, verbunden
 * durch Leitungen, auf denen Datenpakete wandern. Bewusst klein und leise — sie
 * soll den Kopf beleben, nicht davon ablenken.
 *
 * Regeln, die eingehalten werden:
 *   - Farben kommen aus den CSS-Variablen, damit Hell/Dunkel automatisch stimmt
 *   - prefers-reduced-motion: genau ein statisches Bild, keine Dauerschleife
 *   - Tab im Hintergrund: Zeichnen pausiert (kein Stromverbrauch)
 *   - Canvas wird mit devicePixelRatio skaliert, sonst franst es auf Retina aus
 */
(function () {
  "use strict";

  var KNOTEN = 6;
  var FPS_MAX = 30;                 // mehr braucht es nicht, spart Rechenzeit
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
    farben.linie = cssVar("--line-strong", "rgba(255,255,255,0.14)");
    farben.knoten = cssVar("--text-mute", "rgba(255,255,255,0.45)");
    farben.akzent = cssVar("--brass-soft", "#e2c885");
    farben.aktiv = cssVar("--brand", "#c9a24a");
  }

  function knotenBauen(w, h) {
    knoten = [];
    kanten = [];
    pakete = [];
    for (var i = 0; i < KNOTEN; i++) {
      // Gleichmäßig verteilt mit etwas Streuung, mittig in der Höhe
      var x = (i + 0.5) / KNOTEN * w + (Math.random() - 0.5) * (w / (KNOTEN * 2.2));
      var y = h / 2 + (Math.random() - 0.5) * (h * 0.44);
      knoten.push({
        x0: x, y0: y,
        phase: Math.random() * Math.PI * 2,
        amp: 1.4 + Math.random() * 1.6,
        r: 1.5 + Math.random() * 0.9,
        x: x, y: y,
      });
    }
    // Kanten: jeder Knoten hängt am nächsten und am übernächsten
    for (var a = 0; a < knoten.length; a++) {
      kanten.push([a, (a + 1) % knoten.length]);
      if (a % 2 === 0) kanten.push([a, (a + 2) % knoten.length]);
    }
    // Drei Pakete, versetzt
    for (var p = 0; p < 3; p++) {
      pakete.push({ kante: Math.floor(Math.random() * kanten.length), t: Math.random(), speed: 0.16 + Math.random() * 0.12 });
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

    // Knotenpositionen: langsame, organische Bewegung
    var t = statisch ? 0.6 : performance.now() / 1000;
    for (var i = 0; i < knoten.length; i++) {
      var k = knoten[i];
      k.x = k.x0 + Math.sin(t * 0.5 + k.phase) * k.amp;
      k.y = k.y0 + Math.cos(t * 0.4 + k.phase * 1.3) * k.amp;
    }

    // Leitungen
    ctx.lineWidth = 1;
    for (var e = 0; e < kanten.length; e++) {
      var a = knoten[kanten[e][0]], b = knoten[kanten[e][1]];
      var dx = b.x - a.x, dy = b.y - a.y;
      var d = Math.sqrt(dx * dx + dy * dy);
      var naehe = Math.max(0, 1 - d / (w * 0.55));
      ctx.strokeStyle = farben.linie;
      ctx.globalAlpha = 0.10 + naehe * 0.22;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      // leichte Wölbung, damit es nicht nach Gitter aussieht
      ctx.quadraticCurveTo(a.x + dx * 0.5, a.y + dy * 0.5 - 4 * naehe, b.x, b.y);
      ctx.stroke();
    }

    // Knoten
    for (var n = 0; n < knoten.length; n++) {
      var kn = knoten[n];
      ctx.globalAlpha = 0.55;
      ctx.fillStyle = farben.knoten;
      ctx.beginPath();
      ctx.arc(kn.x, kn.y, kn.r, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 0.9;
      ctx.strokeStyle = farben.akzent;
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      ctx.arc(kn.x, kn.y, kn.r + 2.1, 0, Math.PI * 2);
      ctx.stroke();
    }

    // Datenpakete auf den Leitungen
    for (var pi = 0; pi < pakete.length; pi++) {
      var pk = pakete[pi];
      if (!statisch) {
        pk.t += dt * pk.speed;
        if (pk.t > 1) {
          pk.t = 0;
          pk.kante = Math.floor(Math.random() * kanten.length);
        }
      }
      var pa = knoten[kanten[pk.kante][0]], pb = knoten[kanten[pk.kante][1]];
      var mx = pa.x + (pb.x - pa.x) * 0.5;
      var my = pa.y + (pb.y - pa.y) * 0.5 - 3;
      // quadratische Bézier an der Stelle t
      var mt = 1 - pk.t;
      var px = mt * mt * pa.x + 2 * mt * pk.t * mx + pk.t * pk.t * pb.x;
      var py = mt * mt * pa.y + 2 * mt * pk.t * my + pk.t * pk.t * pb.y;
      ctx.globalAlpha = 0.85;
      ctx.fillStyle = farben.aktiv;
      ctx.beginPath();
      ctx.arc(px, py, 1.6, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  function schleife(jetzt) {
    if (!laeuft) return;
    raf = requestAnimationFrame(schleife);
    var dt = Math.min(0.05, (jetzt - letzteZeit) / 1000 || 0);
    if (jetzt - letzteZeit < 1000 / FPS_MAX) return;
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
    knotenBauen(cv.clientWidth || 150, cv.clientHeight || 34);
    if (reduzierteBewegung()) {
      zeichnen(0, true);            // ein Standbild, keine Schleife
      return true;
    }
    laeuft = true;
    letzteZeit = 0;
    raf = requestAnimationFrame(schleife);
    return true;
  }

  // Theme-Wechsel: Farben neu lesen, einmal neu zeichnen
  function themenWechselBeobachten() {
    if (typeof MutationObserver === "undefined") return;
    new MutationObserver(function () {
      farbenLesen();
      var cv = document.getElementById("brand-mesh");
      if (cv && !laeuft) zeichnen(0, true);
    }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  }

  // Die Topbar kommt über x-html und wird bei Sprachwechseln neu gebaut —
  // deshalb beobachten statt auf einen Zeitpunkt zu raten (idempotent über data-bereit).
  function beobachten() {
    if (starten()) return;
    if (typeof MutationObserver === "undefined") return;
    var mo = new MutationObserver(function () {
      if (starten()) mo.disconnect();
    });
    mo.observe(document.body, { childList: true, subtree: true });
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
    if (cv) { cv.dataset.bereit = ""; knotenBauen(cv.clientWidth || 150, cv.clientHeight || 34); }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { themenWechselBeobachten(); beobachten(); });
  } else {
    themenWechselBeobachten();
    beobachten();
  }

  window.mountBrandMesh = starten;
})();
