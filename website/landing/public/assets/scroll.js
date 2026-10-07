/* scroll.js — animaciones ligadas al scroll (estilo Apple), vanilla, sin dependencias.
   - [data-hero]        : el hero se encoge/desvanece al salir
   - [data-parallax=n]  : desplazamiento vertical relativo al scroll
   - .scrub-text        : las palabras se encienden según el scroll
   - .story             : sección sticky; el progreso activa [data-step] y expone --p
   Usa un solo rAF, solo transform/opacity, y respeta prefers-reduced-motion. */
(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const vh = () => innerHeight;

  // partir .scrub-text en palabras
  document.querySelectorAll('.scrub-text').forEach(el => {
    const html = el.innerHTML;
    // conserva etiquetas simples (<em>, <b>) separando solo el texto
    const tmp = document.createElement('div'); tmp.innerHTML = html;
    const out = [];
    const walk = (node, cls) => {
      node.childNodes.forEach(n => {
        if (n.nodeType === 3) {
          n.textContent.split(/(\s+)/).forEach(t => {
            if (!t) return;
            if (/^\s+$/.test(t)) out.push(' ');
            else out.push(`<span class="sw ${cls}">${t}</span>`);
          });
        } else walk(n, (cls + ' ' + (n.className || '') + ' ' + (n.tagName === 'EM' ? 'em' : '')).trim());
      });
    };
    walk(tmp, '');
    el.innerHTML = out.join('');
    el.setAttribute('aria-label', tmp.textContent.trim());
    el.querySelectorAll('.sw').forEach(s => s.setAttribute('aria-hidden', 'true'));
  });

  const hero = document.querySelector('[data-hero]');
  const para = [...document.querySelectorAll('[data-parallax]')];
  const texts = [...document.querySelectorAll('.scrub-text')].map(el => ({ el, w: [...el.querySelectorAll('.sw')] }));
  const stories = [...document.querySelectorAll('.story')].map(el => ({
    el, steps: [...el.querySelectorAll('[data-step]')], n: new Set([...el.querySelectorAll('[data-step]')].map(x => x.dataset.step)).size, last: -1,
  }));

  if (reduce) {
    texts.forEach(t => t.w.forEach(s => (s.style.opacity = 1)));
    stories.forEach(s => s.el.classList.add('static'));
    return;
  }

  let ticking = false;
  const update = () => {
    ticking = false;
    const y = scrollY, H = vh();

    if (hero) {
      const p = clamp(y / (H * 0.9));
      hero.style.transform = `translate3d(0,${p * 60}px,0) scale(${1 - p * 0.07})`;
      hero.style.opacity = String(1 - p * 0.85);
    }

    para.forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.bottom < -200 || r.top > H + 200) return;
      const speed = parseFloat(el.dataset.parallax) || 0.15;
      const off = (r.top + r.height / 2 - H / 2) * -speed;
      el.style.setProperty('--py', off.toFixed(1) + 'px');
      el.style.transform = `translate3d(0,${off.toFixed(1)}px,0)`;
    });

    texts.forEach(({ el, w }) => {
      const r = el.getBoundingClientRect();
      // 0 cuando el bloque entra por abajo, 1 cuando llega al ~35% de la pantalla
      const p = clamp((H * 0.9 - r.top) / (H * 0.55 + r.height));
      const n = w.length;
      w.forEach((s, i) => {
        const a = clamp(p * (n + 6) - i, 0, 1);
        s.style.opacity = (0.16 + a * 0.84).toFixed(3);
        s.style.filter = a < 1 ? `blur(${((1 - a) * 3).toFixed(1)}px)` : 'none';
      });
    });

    stories.forEach(st => {
      const r = st.el.getBoundingClientRect();
      const total = r.height - H;
      const p = clamp(-r.top / total);
      st.el.style.setProperty('--p', p.toFixed(4));
      const idx = Math.min(st.n - 1, Math.floor(p * st.n));
      if (idx !== st.last) {
        st.last = idx;
        st.steps.forEach((s, i) => {
          const k = +s.dataset.step;
          s.classList.toggle('on', k === idx);
          s.classList.toggle('past', k < idx);
        });
        st.el.dataset.active = idx;
      }
    });
  };
  const req = () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } };
  addEventListener('scroll', req, { passive: true });
  addEventListener('resize', req);
  update();
})();
