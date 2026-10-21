(() => {
  'use strict';

  const STORAGE_KEY = 'vintage-rolodex.contacts.v1';
  const SOUND_KEY = 'vintage-rolodex.sound';
  const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ#'.split('');
  const SHOW_BEHIND = 7;   // cards visible behind the open one
  const SHOW_FLIPPED = 1;  // the card mid-flip as it drops away toward you

  const $ = (sel) => document.querySelector(sel);
  const drum = $('#drum');
  const stage = $('#stage');
  const knob = $('#knob');
  const knobHub = knob.querySelector('.hub');
  const counter = $('#counter');
  const tabsEl = $('#tabs');
  const searchEl = $('#search');
  const dialog = $('#editor');
  const form = $('#editor-form');
  const formError = $('#form-error');

  // ---------- Storage ----------
  // Example cards are only written when the viewer asks for them (empty-state button).
  const SAMPLE = [
    { first: 'Ada', last: 'Lovelace', company: 'Analytical Engines Ltd.', title: 'Chief Mathematician', phone: '(555) 018-1815', email: 'ada@engines.example', address: '12 St James Sq, London', notes: 'Example. ' + 'Prefers letters to telegrams.', starred: true },
    { first: 'Desi', last: 'Arnaz', company: 'Desilu Productions', title: 'Producer', phone: '(555) 195-1951', email: 'desi@desilu.example', address: 'Culver City, CA', notes: 'Example card.' },
    { first: 'Ella', last: 'Fitzgerald', company: 'Verve Records', title: 'Vocalist', phone: '(555) 019-1917', email: 'ella@verve.example', address: 'Beverly Hills, CA', notes: 'Example. ' + 'Send flowers on opening night.' },
    { first: 'Grace', last: 'Hopper', company: 'U.S. Navy', title: 'Rear Admiral', phone: '(555) 190-6012', email: 'grace@navy.example', address: 'Arlington, VA', notes: 'Example. ' + 'Bring a nanosecond wire.', starred: true },
    { first: 'Jack', last: 'Kirby', company: 'Timely Comics', title: 'Illustrator', phone: '(555) 191-7082', email: '', address: 'Thousand Oaks, CA', notes: 'Example card.' },
    { first: 'Hedy', last: 'Lamarr', company: 'MGM', title: 'Actress & Inventor', phone: '(555) 191-4110', email: 'hedy@mgm.example', address: 'Hollywood, CA', notes: 'Example. ' + 'Ask about frequency hopping.' },
    { first: 'Thelonious', last: 'Monk', company: 'Blue Note', title: 'Pianist', phone: '(555) 194-7111', email: '', address: '243 W 63rd St, New York', notes: 'Example card.' },
    { first: 'Rosa', last: 'Parks', company: '', title: '', phone: '(555) 195-5120', email: '', address: 'Montgomery, AL', notes: 'Example card.' },
    { first: 'Nikola', last: 'Tesla', company: 'Tesla Electric Co.', title: 'Inventor', phone: '(555) 185-6071', email: 'nikola@tesla.example', address: 'Hotel New Yorker, Rm 3327', notes: 'Example. ' + 'Pigeons. Do not ask.' },
    { first: 'Orson', last: 'Welles', company: 'Mercury Theatre', title: 'Director', phone: '(555) 193-8103', email: '', address: 'New York, NY', notes: 'Example card.' },
    { first: 'Chuck', last: 'Yeager', company: 'USAF', title: 'Test Pilot', phone: '(555) 194-7101', email: '', address: 'Edwards AFB, CA', notes: 'Example card.' },
  ];

  const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 8);

  function loadLocal() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
      if (Array.isArray(parsed)) return parsed.map(normalize).filter(Boolean);
    } catch { /* storage unavailable or corrupt */ }
    return [];
  }

  function saveLocal() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(contacts)); } catch { /* best effort */ }
  }

  // Three backends: the Flask API when served from it (/vintage/), the viewer's private
  // claude.ai store when the page runs as an artifact, otherwise this browser's localStorage.
  const API = '/api/v1/contacts';

  async function api(method, path, body) {
    const res = await fetch(path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const err = new Error(`${method} ${path} failed: ${res.status}`);
      err.status = res.status;
      throw err;
    }
    return res.json();
  }

  // The API keeps a single `name`; split it so the last word is the filing surname.
  // A company-only card is stored with its company as the name.
  function fromServer(r) {
    const company = r.company || '';
    const name = (r.name || '').trim();
    let first = '', last = '';
    if (name && name !== company) {
      const parts = name.split(/\s+/);
      last = parts.length > 1 ? parts.pop() : '';
      first = parts.join(' ');
    }
    return normalize({ ...r, first, last, company, title: r.title || '' });
  }

  function toServer(c) {
    return {
      name: [c.first, c.last].filter(Boolean).join(' ') || c.company,
      company: c.company, title: c.title, phone: c.phone, email: c.email,
      address: c.address, notes: c.notes, starred: c.starred,
    };
  }

  const store = {
    mode: 'local',
    col: null,
    async put(list) {
      if (this.mode === 'local') return saveLocal();
      for (const c of list) {
        if (this.mode === 'server') {
          try {
            await api('PUT', `${API}/${encodeURIComponent(c.id)}`, toServer(c));
          } catch (err) {
            if (err.status !== 404) throw err;
            await api('POST', API, { id: c.id, ...toServer(c) });
          }
        } else {
          const { id, ...body } = c;
          await this.col.doc(id).set(body);
        }
      }
    },
    async remove(id) {
      if (this.mode === 'local') return saveLocal();
      if (this.mode === 'server') return api('DELETE', `${API}/${encodeURIComponent(id)}`);
      await this.col.doc(id).delete();
    },
  };

  // Mutations update the screen first, then persist; a failed write is reported, not hidden.
  function persist(promise) {
    Promise.resolve(promise).catch((err) => {
      toast(err && err.code === 'quota_exceeded'
        ? 'Your rolodex is full. Tear up a few cards to make room.'
        : 'That change didn’t save. Check your connection and try again.');
    });
  }

  const inArtifact = !!(window.claude && window.claude.use);
  const onServer = !inArtifact && /^https?:$/.test(location.protocol);
  let loading = inArtifact || onServer;

  function setStatus(text) { $('#status').textContent = text; }

  function useLocal() {
    store.mode = 'local';
    contacts = loadLocal();
    loading = false;
    setStatus('Saved in this browser');
    rebuild();
  }

  async function connectServer() {
    setStatus('Opening…');
    try {
      const rows = await api('GET', API);
      store.mode = 'server';
      contacts = rows.map(fromServer).filter(Boolean);
      loading = false;
      setStatus('Saved to the rolodex server');
      rebuild();
    } catch {
      useLocal();
      setStatus('Server unreachable · saved in this browser');
    }
  }

  async function connect() {
    if (onServer) return connectServer();
    if (!inArtifact) return useLocal();
    setStatus('Opening…');
    const [db, user] = await Promise.all([window.claude.use('db'), window.claude.use('user')]);
    const id = db && user ? await user.id() : null;
    if (!id) return useLocal();
    store.mode = 'account';
    store.col = db.collection('data/users/' + id);
    setStatus('Saved privately to your account');
    store.col.onSnapshot((snap) => {
      contacts = snap.docs.map((d) => normalize({ ...d.data(), id: d.id })).filter(Boolean);
      loading = false;
      rebuild(currentId());
    }, () => {
      loading = false;
      setStatus('Can’t reach your saved cards');
      rebuild(currentId());
    });
  }

  const FIELDS = ['first', 'last', 'company', 'title', 'phone', 'email', 'address', 'notes'];
  function normalize(c) {
    if (!c || typeof c !== 'object') return null;
    const okId = typeof c.id === 'string' && /^[A-Za-z0-9_~:@+-]{1,64}$/.test(c.id);
    const out = { id: okId ? c.id : uid(), starred: !!c.starred };
    for (const f of FIELDS) out[f] = typeof c[f] === 'string' ? c[f].trim() : '';
    if (!out.first && !out.last && !out.company) return null;
    return out;
  }

  // ---------- Sorting / filtering ----------
  const sortKey = (c) => (c.last || c.first || c.company).toLowerCase() + ' ' + c.first.toLowerCase();
  const letterOf = (c) => {
    const ch = (c.last || c.first || c.company).charAt(0).toUpperCase();
    return ch >= 'A' && ch <= 'Z' ? ch : '#';
  };

  let contacts = [];
  let view = [];           // filtered + sorted contacts currently on the drum
  let cardEls = [];
  let pos = 0;             // fractional position on the drum (index of the open card)
  let target = 0;
  let animating = false;
  let lastTick = 0;

  function rebuild(keepId) {
    const q = searchEl.value.trim().toLowerCase();
    view = contacts
      .filter((c) => !q || FIELDS.some((f) => c[f].toLowerCase().includes(q)))
      .sort((a, b) => sortKey(a).localeCompare(sortKey(b)));

    drum.textContent = '';
    cardEls = view.map((c, i) => {
      const el = renderCard(c, i === 0 || letterOf(view[i - 1]) !== letterOf(c));
      el.dataset.index = i;
      drum.appendChild(el);
      return el;
    });
    if (!view.length) {
      const el = renderEmpty(q);
      drum.appendChild(el);
      cardEls = [el];
    }
    $('#empty-actions').hidden = loading || contacts.length > 0;

    let idx = keepId ? view.findIndex((c) => c.id === keepId) : -1;
    if (idx < 0) idx = Math.min(Math.round(target), Math.max(view.length - 1, 0));
    pos = target = idx;
    renderTabs();
    layout();
  }

  // ---------- Card rendering ----------
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function line(label, content) {
    const li = el('li');
    li.appendChild(el('span', 'lbl', label));
    if (typeof content === 'string') li.appendChild(document.createTextNode(content));
    else li.appendChild(content);
    return li;
  }

  function copyable(text, what) {
    const s = el('span', 'copy', text);
    s.dataset.what = what;
    s.title = 'Click to copy';
    return s;
  }

  function copyText(node) {
    const text = node.textContent;
    const done = () => toast(`Copied ${node.dataset.what}: ${text}`);
    const fallback = () => {
      const r = document.createRange();
      r.selectNodeContents(node);
      const sel = getSelection();
      sel.removeAllRanges();
      sel.addRange(r);
      toast('Selected. Press Ctrl+C to copy.');
    };
    try {
      navigator.clipboard.writeText(text).then(done, fallback);
    } catch { fallback(); }
  }

  function renderCard(c, isFirstOfLetter) {
    const card = el('div', 'card');
    const face = el('div', 'index-card');
    const letter = letterOf(c);

    face.appendChild(el('div', 'card-letter', letter));

    const name = el('div', 'card-name');
    if (c.last) {
      name.appendChild(el('span', 'last', c.last));
      if (c.first) name.appendChild(document.createTextNode(', ' + c.first));
    } else {
      name.textContent = c.first || c.company;
    }
    if (c.starred) name.appendChild(el('span', 'star', '★'));
    face.appendChild(name);

    const ul = el('ul', 'card-lines');
    const role = [c.title, c.company].filter(Boolean).join(' — ');
    if (role && (c.first || c.last)) ul.appendChild(line('', role));
    if (c.phone) ul.appendChild(line('TEL', copyable(c.phone, 'phone number')));
    if (c.email) ul.appendChild(line('MAIL', copyable(c.email, 'email')));
    if (c.address) ul.appendChild(line('ADDR', c.address));
    if (c.notes) {
      const li = line('NOTE', c.notes);
      li.classList.add('note');
      ul.appendChild(li);
    }
    face.appendChild(ul);

    card.appendChild(face);
    card.appendChild(el('div', 'back'));
    card.appendChild(el('div', 'shade'));

    if (isFirstOfLetter) {
      const tab = el('div', 'tab', letter);
      const slot = LETTERS.indexOf(letter) / (LETTERS.length - 1);
      tab.style.left = `calc(${(slot * 100).toFixed(2)}% - ${(slot * 44).toFixed(1)}px)`;
      card.insertBefore(tab, face);
    }
    return card;
  }

  function renderEmpty(q) {
    const card = el('div', 'card empty');
    const face = el('div', 'index-card');
    face.appendChild(el('div', 'card-name', loading ? 'Opening your rolodex…' : q ? 'No match.' : 'No cards yet.'));
    const ul = el('ul', 'card-lines');
    if (!loading) ul.appendChild(line('', q ? `Nothing filed under “${q}”.` : 'Click “+ New Card” to file one.'));
    face.appendChild(ul);
    card.appendChild(face);
    card.appendChild(el('div', 'back'));
    card.appendChild(el('div', 'shade'));
    return card;
  }

  function renderTabs() {
    const present = new Set(view.map(letterOf));
    const current = view[Math.round(pos)];
    const curLetter = current ? letterOf(current) : null;
    tabsEl.textContent = '';
    for (const L of LETTERS) {
      const b = el('button', L === curLetter ? 'active' : '', L);
      b.type = 'button';
      b.disabled = !present.has(L);
      b.addEventListener('click', () => jumpToLetter(L));
      tabsEl.appendChild(b);
    }
  }

  // ---------- 3D layout ----------
  // Tilt (degrees, positive = top leans away from you) for a card `d` positions from the open one.
  function tiltFor(d) {
    if (d >= 1) return Math.min(22 + (d - 1) * 6.5, 80);
    if (d >= 0) return 6 + d * 16;
    if (d >= -1) return 6 + d * 186;               // the flip: swings over and down behind the base
    return -180;
  }

  function layout() {
    const empty = !view.length;
    cardEls.forEach((card, i) => {
      const d = empty ? 0 : i - pos;
      const visible = d <= SHOW_BEHIND + 1 && d >= -SHOW_FLIPPED - 1;
      if (!visible) { card.hidden = true; return; }
      card.hidden = false;
      card.style.transform = `rotateX(${tiltFor(d).toFixed(2)}deg)`;
      const shade = card.lastElementChild;
      const darkness = d > 0 ? Math.min(d * 0.07, 0.5) : Math.min(-d * 0.18, 0.55);
      shade.style.opacity = darkness.toFixed(3);
      const fade = d > SHOW_BEHIND ? SHOW_BEHIND + 1 - d : d < -SHOW_FLIPPED ? SHOW_FLIPPED + 1 + d : 1;
      card.style.opacity = Math.max(fade, 0).toFixed(3);
      card.classList.toggle('front', Math.abs(d) < 0.5);
      card.style.pointerEvents = Math.abs(d) < 0.5 || (d > 0 && d < SHOW_BEHIND) ? '' : 'none';
    });
    const n = view.length;
    counter.textContent = n ? `${Math.round(pos) + 1} / ${n}` : '0 / 0';
    knobHub.style.transform = `rotate(${(pos * 24).toFixed(1)}deg)`;
  }

  // ---------- Motion ----------
  const clampIdx = (v) => Math.max(0, Math.min(v, Math.max(view.length - 1, 0)));

  function goTo(idx) {
    target = clampIdx(Math.round(idx));
    animate();
  }

  function animate() {
    if (animating) return;
    animating = true;
    const step = () => {
      const diff = target - pos;
      if (Math.abs(diff) < 0.002) {
        pos = target;
        animating = false;
        afterMove();
        return;
      }
      // ease toward target, faster when far so long jumps don't drag on
      pos += diff * (Math.abs(diff) > 4 ? 0.22 : 0.18);
      afterMove();
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  let lastLetter = null;
  function afterMove() {
    layout();
    const r = Math.round(pos);
    if (r !== lastTick) { lastTick = r; tick(); }
    const cur = view[r];
    const L = cur ? letterOf(cur) : null;
    if (L !== lastLetter) { lastLetter = L; renderTabs(); }
  }

  function jumpToLetter(L) {
    let idx = view.findIndex((c) => letterOf(c) === L);
    if (idx < 0) {
      // first card at or after this letter
      const li = LETTERS.indexOf(L);
      idx = view.findIndex((c) => LETTERS.indexOf(letterOf(c)) >= li);
      if (idx < 0) idx = view.length - 1;
    }
    goTo(idx);
  }

  // ---------- Sound ----------
  let soundOn = true;
  try { soundOn = localStorage.getItem(SOUND_KEY) !== 'off'; } catch { /* default on */ }
  let audio = null;
  function tick() {
    if (!soundOn) return;
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === 'suspended') audio.resume();
      const t = audio.currentTime;
      const len = Math.floor(audio.sampleRate * 0.025);
      const buf = audio.createBuffer(1, len, audio.sampleRate);
      const data = buf.getChannelData(0);
      for (let i = 0; i < len; i++) data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 4);
      const src = audio.createBufferSource();
      src.buffer = buf;
      const filter = audio.createBiquadFilter();
      filter.type = 'bandpass';
      filter.frequency.value = 2400 + Math.random() * 600;
      filter.Q.value = 1.2;
      const gain = audio.createGain();
      gain.gain.value = 0.35;
      src.connect(filter).connect(gain).connect(audio.destination);
      src.start(t);
    } catch { /* audio unsupported */ }
  }
  const soundBtn = $('#btn-sound');
  function renderSound() {
    soundBtn.textContent = soundOn ? '🔊' : '🔇';
    soundBtn.setAttribute('aria-pressed', String(soundOn));
  }
  soundBtn.addEventListener('click', () => {
    soundOn = !soundOn;
    try { localStorage.setItem(SOUND_KEY, soundOn ? 'on' : 'off'); } catch { /* ignore */ }
    renderSound();
  });
  renderSound();

  // ---------- Input: wheel, drag, knob, keys ----------
  let wheelAccum = 0;
  stage.addEventListener('wheel', (e) => {
    e.preventDefault();
    wheelAccum += e.deltaY;
    const steps = Math.trunc(wheelAccum / 60);
    if (steps) {
      wheelAccum -= steps * 60;
      goTo(target + steps);
    }
  }, { passive: false });

  function dragSpinner(elm, pxPerCard, axis) {
    let start = null;
    elm.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      start = { x: e.clientX, y: e.clientY, pos, moved: false };
      elm.setPointerCapture(e.pointerId);
      stage.classList.add('dragging');
    });
    elm.addEventListener('pointermove', (e) => {
      if (!start) return;
      const delta = axis === 'y' ? start.y - e.clientY : (start.y - e.clientY) + (e.clientX - start.x);
      if (Math.abs(delta) > 4) start.moved = true;
      if (!start.moved) return;
      const next = Math.max(-0.4, Math.min(start.pos + delta / pxPerCard, view.length - 0.6));
      pos = target = next;
      afterMove();
    });
    const end = (e) => {
      if (!start) return;
      const moved = start.moved;
      start = null;
      stage.classList.remove('dragging');
      if (moved) goTo(pos);
      else if (elm === stage) clickCard(e);
    };
    elm.addEventListener('pointerup', end);
    elm.addEventListener('pointercancel', end);
  }
  dragSpinner(stage, 46, 'y');
  dragSpinner(knob, 30, 'xy');

  // Browser hit-testing is unreliable inside the 3D drum (it reports the drum itself),
  // so test the projected card rects directly: open card first, then those behind it.
  function cardIndexAt(e) {
    if (!view.length) return -1;
    const open = Math.round(pos);
    for (let i = open; i < Math.min(view.length, open + SHOW_BEHIND); i++) {
      const r = cardEls[i].querySelector('.index-card').getBoundingClientRect();
      const tabRoom = i === open ? 0 : 22; // divider tabs stick up above the card
      if (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top - tabRoom && e.clientY <= r.bottom) return i;
    }
    return -1;
  }

  const inside = (e, r) => e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;

  function clickCard(e) {
    const idx = cardIndexAt(e);
    if (idx < 0) return;
    if (idx !== Math.round(pos)) return goTo(idx);
    const hit = [...cardEls[idx].querySelectorAll('.copy')].find((n) => inside(e, n.getBoundingClientRect()));
    if (hit) copyText(hit);
  }

  stage.addEventListener('dblclick', (e) => {
    const idx = cardIndexAt(e);
    if (idx >= 0 && idx === Math.round(pos)) openEditor(view[idx]);
  });

  document.addEventListener('keydown', (e) => {
    if (dialog.open) return;
    const typing = e.target.matches('input, textarea');
    if (e.key === 'Escape' && e.target === searchEl) { searchEl.value = ''; rebuild(currentId()); stage.focus(); return; }
    if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
    switch (e.key) {
      case 'ArrowDown': case 'ArrowRight': goTo(target + 1); break;
      case 'ArrowUp': case 'ArrowLeft': goTo(target - 1); break;
      case 'PageDown': goTo(target + 10); break;
      case 'PageUp': goTo(target - 10); break;
      case 'Home': goTo(0); break;
      case 'End': goTo(view.length - 1); break;
      case 'Enter': if (view[Math.round(pos)]) openEditor(view[Math.round(pos)]); break;
      case '/': searchEl.focus(); break;
      case '+': openEditor(null); break;
      default:
        if (/^[a-z]$/i.test(e.key)) jumpToLetter(e.key.toUpperCase());
        else return;
    }
    e.preventDefault();
  });

  const currentId = () => (view[Math.round(pos)] || {}).id;

  // ---------- Search ----------
  let searchTimer;
  searchEl.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { target = 0; rebuild(); }, 120);
  });

  // ---------- Editor ----------
  let editingId = null;

  function openEditor(c) {
    editingId = c ? c.id : null;
    $('#editor-title').textContent = c ? 'Edit Card' : 'New Card';
    $('#btn-delete').hidden = !c;
    for (const f of FIELDS) form.elements[f].value = c ? c[f] : '';
    form.elements.starred.checked = !!(c && c.starred);
    formError.textContent = '';
    disarmDelete();
    dialog.showModal();
    form.elements.first.focus();
  }

  form.addEventListener('submit', (e) => {
    const data = { id: editingId || uid(), starred: form.elements.starred.checked };
    for (const f of FIELDS) data[f] = form.elements[f].value;
    const c = normalize(data);
    if (!c) {
      e.preventDefault();
      formError.textContent = 'A card needs at least a name or a company.';
      form.elements.first.focus();
      return;
    }
    if (c.email && !form.elements.email.checkValidity()) {
      e.preventDefault();
      formError.textContent = 'That email address doesn’t look right.';
      form.elements.email.focus();
      return;
    }
    e.preventDefault();
    const i = contacts.findIndex((x) => x.id === c.id);
    if (i >= 0) contacts[i] = c; else contacts.push(c);
    persist(store.put([c]));
    dialog.close();
    if (searchEl.value && !FIELDS.some((f) => c[f].toLowerCase().includes(searchEl.value.trim().toLowerCase()))) {
      searchEl.value = '';
    }
    rebuild(c.id);
    stage.focus();
  });

  $('#btn-cancel').addEventListener('click', () => { dialog.close(); stage.focus(); });

  // Tearing up takes two clicks: the first arms the button, the second deletes.
  const deleteBtn = $('#btn-delete');
  function disarmDelete() {
    deleteBtn.classList.remove('armed');
    deleteBtn.textContent = 'Tear Up';
  }
  deleteBtn.addEventListener('click', () => {
    const c = contacts.find((x) => x.id === editingId);
    if (!c) return;
    if (!deleteBtn.classList.contains('armed')) {
      deleteBtn.classList.add('armed');
      deleteBtn.textContent = 'Click again to tear up';
      return;
    }
    const label = [c.first, c.last].filter(Boolean).join(' ') || c.company;
    const idx = view.findIndex((x) => x.id === editingId);
    contacts = contacts.filter((x) => x.id !== editingId);
    persist(store.remove(c.id));
    dialog.close();
    toast(`Tore up the card for ${label}.`);
    target = Math.max(idx, 0);
    rebuild();
    stage.focus();
  });

  $('#btn-new').addEventListener('click', () => openEditor(null));

  // ---------- Import / export ----------
  let downloads = null;
  $('#btn-export').addEventListener('click', async () => {
    const data = JSON.stringify(contacts, null, 2);
    const filename = `rolodex-${new Date().toISOString().slice(0, 10)}.json`;
    if (downloads) {
      try {
        await downloads.save({ filename, data });
        toast(`Saved ${filename}.`);
      } catch (err) {
        if (err.code !== 'declined') toast('Couldn’t save the file here.');
      }
      return;
    }
    const blob = new Blob([data], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });

  $('#file-import').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text());
      if (!Array.isArray(parsed)) throw new Error('Expected a list of contacts.');
      const incoming = parsed.map(normalize).filter(Boolean);
      const byId = new Map(contacts.map((c) => [c.id, c]));
      for (const c of incoming) byId.set(c.id, c);
      const added = byId.size - contacts.length;
      contacts = [...byId.values()];
      rebuild(currentId());
      persist(store.put(incoming));
      toast(`Imported ${incoming.length} card(s): ${added} new, ${incoming.length - added} updated.`);
    } catch (err) {
      toast('Couldn’t import that file. It must be a rolodex JSON export. ' + err.message);
    }
  });

  $('#btn-examples').addEventListener('click', () => {
    const examples = SAMPLE.map((c) => normalize({ ...c }));
    contacts = contacts.concat(examples);
    target = 0;
    rebuild();
    persist(store.put(examples));
  });
  $('#btn-first').addEventListener('click', () => openEditor(null));

  // ---------- Toast ----------
  let toastTimer;
  function toast(msg) {
    const t = $('#toast');
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 3200);
  }

  // ---------- Go ----------
  rebuild();
  lastTick = Math.round(pos);
  stage.focus({ preventScroll: true });
  connect().catch(useLocal);
  if (window.claude && window.claude.use) {
    window.claude.use('downloads').then((d) => {
      downloads = d;
      $('#btn-export').hidden = !d;
    });
  }
})();
