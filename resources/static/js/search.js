(function () {
    // Root + routes from data-* attributes
    const root = document.getElementById('searchRoot');
    const ROUTES = {
      api: root.dataset.api,
      slit: root.dataset.slit,
      spectrum: root.dataset.spectrum,
      placeholder: root.dataset.placeholder
    };
  
    // --- State ---
    const qsInit = new URLSearchParams(location.search);
    const state = {
      q: qsInit.get('q') || '',
      dateFrom: qsInit.get('date_from') || '',
      dateTo: qsInit.get('date_to') || '',
      instrument: new Set((qsInit.get('instrument') || '').split(',').filter(Boolean)),
      flags: new Set((qsInit.get('flags') || '').split(',').filter(Boolean)),
      exp: { min: qsInit.get('exp_min') || '', max: qsInit.get('exp_max') || '' },
      frames: { min: qsInit.get('frames_min') || '', max: qsInit.get('frames_max') || '' },
      sortBy: qsInit.get('sort') || '-date_obs',
      page: 1,
    };
  
    // --- Helpers ---
    const el = sel => document.querySelector(sel);
    const els = sel => [...document.querySelectorAll(sel)];
  
    function upsertChip(key, label, removeFn) {
      const wrap = el('#activeChips');
      const id = `chip-${key}-${btoa(label).replace(/=/g,'')}`;
      const existed = el('#'+id);
      if (existed) return existed;
      const chip = document.createElement('span');
      chip.className = 'chip';
      chip.id = id;
      chip.innerHTML = `<span>${label}</span><button type="button" class="btn-close btn-sm" aria-label="remove"></button>`;
      chip.querySelector('.btn-close').addEventListener('click', () => { removeFn?.(); runSearch(); });
      wrap.appendChild(chip); return chip;
    }
  
    function syncChips() {
      el('#activeChips').innerHTML = '';
      if (state.q) upsertChip('q', state.q, () => { state.q=''; el('#q').value=''; });
      if (state.dateFrom || state.dateTo) {
        const label = `${state.dateFrom || '…'} ~ ${state.dateTo || '…'}`;
        upsertChip('date', label, () => {
          state.dateFrom=''; state.dateTo='';
          el('#dateFrom').value=''; el('#dateTo').value='';
        });
      }
      state.instrument.forEach(v => upsertChip('inst-'+v, v, () => {
        state.instrument.delete(v);
        const pill = els(`[data-filter="instrument"] .filter-pill[data-value="${v}"]`)[0];
        pill?.classList.remove('active');
      }));
      state.flags.forEach(v => upsertChip('flag-'+v, v, () => {
        state.flags.delete(v);
        const pill = els(`[data-filter="flags"] .filter-pill[data-value="${v}"]`)[0];
        pill?.classList.remove('active');
      }));
      if (state.exp.min || state.exp.max)
        upsertChip('exp', `노출 ${state.exp.min||'…'}~${state.exp.max||'…'}s`, () => {
          state.exp={min:'',max:''}; el('#expMin').value=''; el('#expMax').value='';
        });
      if (state.frames.min || state.frames.max)
        upsertChip('frames', `프레임 ${state.frames.min||'…'}~${state.frames.max||'…'}`, () => {
          state.frames={min:'',max:''}; el('#framesMin').value=''; el('#framesMax').value='';
        });
    }
  
    // --- UI Events ---
    el('#q').addEventListener('keydown', (e)=>{ if(e.key==='Enter'){ state.q = e.target.value.trim(); runSearch(); }});
    el('#runSearch').addEventListener('click', ()=>{ state.q = el('#q').value.trim(); runSearch(); });
    el('#quickRange').addEventListener('click', ()=>{
      const to = new Date();
      const from = new Date(Date.now() - 6*24*3600*1000);
      el('#dateFrom').value = from.toISOString().slice(0,10);
      el('#dateTo').value = to.toISOString().slice(0,10);
      state.dateFrom = el('#dateFrom').value; state.dateTo = el('#dateTo').value;
      syncChips(); runSearch();
    });
    el('#dateFrom').addEventListener('change', e=>{ state.dateFrom = e.target.value; syncChips();});
    el('#dateTo').addEventListener('change', e=>{ state.dateTo = e.target.value; syncChips();});
  
    els('.filter-pill').forEach(pill=>{
      pill.addEventListener('click', ()=>{
        const group = pill.closest('[data-filter]').dataset.filter;
        const val = pill.dataset.value;
        if (group==='instrument') {
          if (state.instrument.has(val)) state.instrument.delete(val); else state.instrument.add(val);
        }
        if (group==='flags') {
          if (state.flags.has(val)) state.flags.delete(val); else state.flags.add(val);
        }
        pill.classList.toggle('active');
        syncChips(); runSearch();
      });
    });
  
    el('#sortBy').addEventListener('change', e=>{ state.sortBy = e.target.value; runSearch(); });
  
    // --- Render ---
    function renderResults(items, total) {
      const wrap = el('#results');
      wrap.innerHTML = '';
      el('#summary').textContent = `${total}건 결과`;
      const tpl = el('#tplResultCard');
      items.forEach(it => {
        const node = tpl.content.cloneNode(true);
        node.querySelector('.thumb').src = it.thumb_url || ROUTES.placeholder;
        node.querySelector('.target-name').textContent = it.target || '(unknown target)';
        node.querySelector('.filename').textContent = it.filename || it.file_id || '';
        node.querySelector('.date-obs').textContent = it.date_obs || '';
        node.querySelector('.exptime').textContent = (typeof it.exptime === 'number' ? it.exptime.toFixed(2) : it.exptime) + ' s';
        node.querySelector('.frames').textContent = (it.frames ?? '-') + '';
        node.querySelector('.shape').textContent = it.shape || '-';
        node.querySelector('.flags').textContent = (it.flags||[]).join(', ');
        node.querySelector('[data-action="open-slit"]').href = ROUTES.slit + `?file_id=${encodeURIComponent(it.file_id)}`;
        node.querySelector('[data-action="open-spectrum"]').href = ROUTES.spectrum + `?file_id=${encodeURIComponent(it.file_id)}`;
        wrap.appendChild(node);
      });
    }
  
    // --- Fetch ---
    async function runSearch(pushUrl=true) {
      syncChips();
      const qs = new URLSearchParams();
      if (state.q) qs.set('q', state.q);
      if (state.dateFrom) qs.set('date_from', state.dateFrom);
      if (state.dateTo) qs.set('date_to', state.dateTo);
      if (state.instrument.size) qs.set('instrument', [...state.instrument].join(','));
      if (state.flags.size) qs.set('flags', [...state.flags].join(','));
      if (state.exp.min) qs.set('exp_min', state.exp.min);
      if (state.exp.max) qs.set('exp_max', state.exp.max);
      if (state.frames.min) qs.set('frames_min', state.frames.min);
      if (state.frames.max) qs.set('frames_max', state.frames.max);
      if (state.sortBy) qs.set('sort', state.sortBy);
  
      if (pushUrl) {
        const url = new URL(location.href);
        url.search = qs.toString();
        history.replaceState({}, '', url);
      }
  
      try {
        const res = await fetch(ROUTES.api + '?' + qs.toString());
        if (!res.ok) throw new Error('검색 실패');
        const data = await res.json(); // { items: [], total: n }
        renderResults(data.items || [], data.total || 0);
      } catch (e) {
        console.error(e);
        renderResults([], 0);
        el('#summary').textContent = '검색 중 문제가 발생했습니다.';
      }
    }
  
    // Initial
    (async ()=>{ await runSearch(false); })();
  })();
  