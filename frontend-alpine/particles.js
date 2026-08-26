/* GPU-Pool Particle background — lightweight "AI network" effect.
 * Canvas-based, no external deps. Draws drifting dots connected by lines
 * when close, in the brand palette from style.css vars.
 */
(function () {
  const canvas = document.getElementById("bg-particles");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let W, H, particles, raf, running = true;
  const MAX_PARTICLES = 90;
  const LINK_DIST = 130;

  // Pull accent colors from style.css custom props if present.
  const cs = getComputedStyle(document.documentElement);
  const parseCss = (varName, fallback) => {
    const v = cs.getPropertyValue(varName).trim();
    return v ? v : fallback;
  };
  // Convert "#rrggbb" / "#rgb" or "r,g,b" to a comma rgb triplet.
  function toTriplet(val) {
    val = val.trim();
    if (val.startsWith("#")) {
      const h = val.slice(1);
      const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
      const n = parseInt(full, 16);
      return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
    }
    return val.replace(/[^\d,]/g, "");
  }
  const C_PART = toTriplet(parseCss("--brand", "#6366f1"));        // dot color (rgb triplet)
  const C_LINK = toTriplet(parseCss("--brand-2", "#8b5cf6"));     // line color (rgb triplet)

  function resize() {
    W = canvas.width = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }

  function makeParticle() {
    return {
      x: Math.random() * W,
      y: Math.random() * H,
      vx: (Math.random() - 0.5) * 0.6,
      vy: (Math.random() - 0.5) * 0.6,
      r: Math.random() * 1.8 + 0.6,
      a: Math.random() * 0.6 + 0.3,
    };
  }

  function init() {
    resize();
    particles = Array.from({ length: MAX_PARTICLES }, makeParticle);
  }

  function step() {
    ctx.clearRect(0, 0, W, H);
    // move + wrap
    for (const p of particles) {
      p.x += p.vx; p.y += p.vy;
      if (p.x < -10) p.x = W + 10; else if (p.x > W + 10) p.x = -10;
      if (p.y < -10) p.y = H + 10; else if (p.y > H + 10) p.y = -10;
    }
    // links
    for (let i = 0; i < particles.length; i++) {
      const a = particles[i];
      for (let j = i + 1; j < particles.length; j++) {
        const b = particles[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < LINK_DIST * LINK_DIST) {
          const d = Math.sqrt(d2);
          const alpha = (1 - d / LINK_DIST) * 0.28;
          ctx.strokeStyle = `rgba(${C_LINK},${alpha})`;
          ctx.lineWidth = 0.7;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }
    // dots
    for (const p of particles) {
      ctx.fillStyle = `rgba(${C_PART},${p.a})`;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }
    raf = requestAnimationFrame(step);
  }

  window.addEventListener("resize", resize);
  window.addEventListener("blur", () => { running = false; cancelAnimationFrame(raf); });
  window.addEventListener("focus", () => { if (!running) { running = true; raf = requestAnimationFrame(step); } });

  init();
  raf = requestAnimationFrame(step);
})();
