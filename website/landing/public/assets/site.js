(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fine = matchMedia('(hover: hover)').matches;

  // barra de progreso + nav
  const prog = $('#prog');
  const onScroll = () => {
    const h = document.documentElement;
    prog.style.width = (h.scrollTop / (h.scrollHeight - h.clientHeight || 1)) * 100 + '%';
  };
  addEventListener('scroll', onScroll, { passive: true }); onScroll();

  // reveal al hacer scroll
  const io = new IntersectionObserver(es => es.forEach(e => {
    if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
  }), { threshold: .12, rootMargin: '0px 0px -6% 0px' });
  $$('.rv').forEach(el => io.observe(el));

  // titular: palabra por palabra
  $$('[data-words]').forEach(h => {
    let i = 0;
    const wrap = n => {
      if (n.nodeType === 3) {
        const f = document.createDocumentFragment();
        n.textContent.split(/(\s+)/).forEach(t => {
          if (!t.trim()) { f.append(t); return; }
          const s = document.createElement('span');
          s.className = 'w'; s.style.setProperty('--i', i++); s.textContent = t; f.append(s);
        });
        n.replaceWith(f);
      } else [...n.childNodes].forEach(wrap);
    };
    [...h.childNodes].forEach(wrap);
  });

  // foco que sigue al cursor + brillo en tarjetas + inclinación 3D
  const spot = $('#spot');
  if (fine && !reduce) {
    addEventListener('pointermove', e => {
      spot.style.transform = `translate(${e.clientX}px,${e.clientY}px) translate(-50%,-50%)`;
    }, { passive: true });
    $$('.card').forEach(c => {
      c.addEventListener('pointermove', e => {
        const r = c.getBoundingClientRect();
        const x = e.clientX - r.left, y = e.clientY - r.top;
        c.style.setProperty('--mx', x + 'px'); c.style.setProperty('--my', y + 'px');
        if (c.dataset.tilt !== undefined) {
          const rx = ((y / r.height) - .5) * -7, ry = ((x / r.width) - .5) * 7;
          c.style.transform = `perspective(900px) rotateX(${rx}deg) rotateY(${ry}deg)`;
        }
      });
      c.addEventListener('pointerleave', () => { c.style.transform = ''; });
    });
    const desk = $('.desk');
    if (desk) {
      desk.addEventListener('pointermove', e => {
        const r = desk.getBoundingClientRect();
        const rx = ((e.clientY - r.top) / r.height - .5) * -8, ry = ((e.clientX - r.left) / r.width - .5) * 8;
        desk.style.transform = `perspective(1100px) rotateX(${rx}deg) rotateY(${ry}deg)`;
      });
      desk.addEventListener('pointerleave', () => { desk.style.transform = ''; });
    }
  } else if (spot) spot.style.display = 'none';

  // contadores
  const cio = new IntersectionObserver(es => es.forEach(e => {
    if (!e.isIntersecting) return;
    cio.unobserve(e.target);
    const el = e.target, to = +el.dataset.count;
    if (reduce) { el.textContent = to; return; }
    const t0 = performance.now(), dur = 1400;
    const step = t => {
      const p = Math.min(1, (t - t0) / dur);
      el.textContent = Math.round(to * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }), { threshold: .6 });
  $$('[data-count]').forEach(el => cio.observe(el));

  // mascota del hero: salta al hacer clic
  const pet = $('.desk .pet');
  if (pet) pet.addEventListener('click', () => {
    pet.classList.add('hop');
    setTimeout(() => pet.classList.remove('hop'), 720);
  });

  // pestañas de instalación
  $$('.tab').forEach(b => b.addEventListener('click', () => {
    $$('.tab').forEach(x => x.classList.toggle('on', x === b));
    $$('.panel').forEach(p => p.classList.toggle('on', p.id === 'tab-' + b.dataset.tab));
  }));
  $$('.copy').forEach(b => b.addEventListener('click', () => {
    const txt = b.parentElement.innerText.replace(/^Copiar\s*/, '').trim();
    navigator.clipboard.writeText(txt).then(() => {
      const o = b.textContent; b.textContent = '¡Copiado!';
      setTimeout(() => (b.textContent = o), 1500);
    });
  }));

  // historial: ver más
  const tl = $('.tl'), more = $('#more');
  if (tl && more) more.addEventListener('click', () => {
    const open = tl.classList.toggle('open');
    more.textContent = open ? 'Ver menos' : 'Ver historial completo';
  });

  // compañero: una mascota que persigue el cursor por la página
  const buddy = $('#buddy');
  if (buddy && fine && !reduce) {
    let x = innerWidth * .3, tx = x, dir = 1, last = 0;
    addEventListener('pointermove', e => { tx = e.clientX - 27; }, { passive: true });
    addEventListener('click', () => {
      buddy.animate([{ translate: '0 0' }, { translate: '0 -70px' }, { translate: '0 0' }],
        { duration: 520, easing: 'cubic-bezier(.2,.8,.2,1)' });
    });
    const loop = t => {
      const d = tx - x;
      if (Math.abs(d) > 70) { x += Math.sign(d) * Math.min(3.2, Math.abs(d) * .02); dir = Math.sign(d); buddy.classList.add('walk'); }
      else buddy.classList.remove('walk');
      buddy.style.transform = `translateX(${x}px) scaleX(${dir})`;
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  } else if (buddy) buddy.remove();
})();
