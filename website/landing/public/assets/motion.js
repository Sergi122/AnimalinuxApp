/* motion.js — detalles de movimiento estilo Apple. Vanilla, sin dependencias, respeta
   prefers-reduced-motion y solo se activa con puntero fino (no en táctil). */
(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fine = matchMedia('(hover: hover) and (pointer: fine)').matches;
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  // botones principales "magnéticos": se acercan suavemente al cursor
  if (!reduce && fine) {
    $$('.btn.primary').forEach(b => {
      b.addEventListener('pointermove', e => {
        const r = b.getBoundingClientRect();
        b.style.setProperty('--mx', ((e.clientX - r.left - r.width / 2) * 0.14).toFixed(1) + 'px');
        b.style.setProperty('--my', ((e.clientY - r.top - r.height / 2) * 0.22).toFixed(1) + 'px');
      });
      b.addEventListener('pointerleave', () => { b.style.setProperty('--mx', '0px'); b.style.setProperty('--my', '0px'); });
    });
  }

  // navegación: resalta la sección visible (subrayado animado)
  const links = $$('.nav .l[href^="#"]');
  if (links.length && 'IntersectionObserver' in window) {
    const map = new Map(links.map(a => [a.getAttribute('href').slice(1), a]));
    const io = new IntersectionObserver(es => {
      es.forEach(e => { if (e.isIntersecting) { links.forEach(l => l.classList.remove('cur')); map.get(e.target.id)?.classList.add('cur'); } });
    }, { rootMargin: '-45% 0px -50% 0px' });
    map.forEach((_, id) => { const s = document.getElementById(id); if (s) io.observe(s); });
  }
})();
