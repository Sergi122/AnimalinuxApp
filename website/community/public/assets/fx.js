(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fine = matchMedia('(hover: hover)').matches;
  const add = (tag, attrs) => { const e = document.createElement(tag); Object.assign(e, attrs); document.body.prepend(e); return e; };

  add('div', { id: 'prog' });
  const bg = add('div', { className: 'bg' }); bg.innerHTML = '<i></i><i></i><i></i>';
  const spot = fine && !reduce ? add('div', { id: 'spot' }) : null;
  const prog = document.getElementById('prog');
  const onScroll = () => {
    const h = document.documentElement;
    prog.style.width = (h.scrollTop / (h.scrollHeight - h.clientHeight || 1)) * 100 + '%';
  };
  addEventListener('scroll', onScroll, { passive: true }); onScroll();

  if (spot) addEventListener('pointermove', e => {
    spot.style.transform = `translate(${e.clientX}px,${e.clientY}px) translate(-50%,-50%)`;
  }, { passive: true });

  // las tarjetas se crean de forma asíncrona: reveal escalonado + brillo que sigue al cursor
  const io = new IntersectionObserver(es => es.forEach(e => {
    if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
  }), { threshold: .08 });
  const prep = el => {
    if (el.dataset.fx) return; el.dataset.fx = '1';
    el.classList.add('rv');
    el.style.setProperty('--d', (Math.min([...el.parentElement.children].indexOf(el), 12) * 55) + 'ms');
    io.observe(el);
    setTimeout(() => el.classList.add('in'), 2500); // red de seguridad si el observer no dispara
    if (fine && !reduce) {
      el.addEventListener('pointermove', e => {
        const r = el.getBoundingClientRect();
        el.style.setProperty('--mx', e.clientX - r.left + 'px');
        el.style.setProperty('--my', e.clientY - r.top + 'px');
      });
    }
  };
  const scan = () => document.querySelectorAll('.pack-card, .pose-card').forEach(prep);
  new MutationObserver(scan).observe(document.body, { childList: true, subtree: true });
  scan();
})();
