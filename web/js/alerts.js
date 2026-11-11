// Alerting in the browser: temporal confirmation (same rules as backend alerts/engine.py),
// siren (WebAudio), desktop notifications and toasts. Confirmed alerts from real video
// are reported to the backend event log when one is connected.
(function () {
  "use strict";
  const RULES = {fallS: 1.5, postureS: 3, qualityS: 5, cooldownS: 30, graceS: 0.5, lowQ: 40};
  const MESSAGES = {
    FALL: ['CRITICAL', 'Phát hiện công nhân bị ngã'],
    POSTURE: ['WARNING', 'Cúi sai tư thế kéo dài'],
    CAMERA: ['WARNING', 'Chất lượng camera kém / bị che'],
  };
  const LABEL = {FALL: 'NGÃ', POSTURE: 'CÚI SAI', CAMERA: 'CAMERA'};

  // ---------------------------------------------------------------- engine
  function Engine() { this.ep = {}; this.last = {}; this.hips = {}; }
  Engine.prototype.reset = function () { this.ep = {}; this.hips = {}; };
  Engine.prototype.check = function (key, active, t, confirmS) {
    const ep = this.ep[key] || (this.ep[key] = {start: null, lastTrue: 0, fired: false});
    if (!active) {
      if (ep.start !== null && t - ep.lastTrue > RULES.graceS) this.ep[key] = {start: null, lastTrue: 0, fired: false};
      return false;
    }
    if (ep.start === null) ep.start = t;
    ep.lastTrue = t;
    if (ep.fired || t - ep.start < confirmS) return false;
    if (t - (this.last[key] ?? -1e9) < RULES.cooldownS) return false;
    ep.fired = true; this.last[key] = t;
    return true;
  };
  Engine.prototype.rapidDrop = function (id, kps, t) {
    if (!kps || kps.length < 17 || kps[11][2] < .3 || kps[12][2] < .3) return false;
    const ys = kps.filter(k => k[2] > .3).map(k => k[1]);
    const h = Math.max(...ys) - Math.min(...ys);
    const hist = (this.hips[id] = (this.hips[id] || []).filter(x => t - x[0] <= 1.5));
    hist.push([t, (kps[11][1] + kps[12][1]) / 2, h]);
    if (hist.length < 2) return false;
    const tallest = Math.max(...hist.map(x => x[2]));
    return tallest > 0 && hist[hist.length - 1][1] - Math.min(...hist.map(x => x[1])) > .25 * tallest;
  };
  Engine.prototype.update = function (persons, quality, t) {
    const out = [];
    (persons || []).forEach((p, i) => {
      const id = p.id ?? i, s = p.safety || {}, tech = s.technique || 'NONE';
      const rapid = this.rapidDrop(id, p.keypoints, t);
      if (this.check('FALL|' + id, tech === 'FALL', t, RULES.fallS * (rapid ? .5 : 1)))
        out.push({type: 'FALL', track_id: id, detail: rapid ? 'Ngã đột ngột' : 'Nằm trên sàn'});
      if (this.check('POSTURE|' + id, tech === 'IMPROPER', t, RULES.postureS))
        out.push({type: 'POSTURE', track_id: id, detail: s.detail || ''});
    });
    if (quality && typeof quality.overall === 'number' &&
        this.check('CAMERA', quality.overall < RULES.lowQ, t, RULES.qualityS))
      out.push({type: 'CAMERA', track_id: null, detail: `IQA ${Math.round(quality.overall)}/100`});
    return out;
  };

  // ---------------------------------------------------------------- siren
  let actx = null;
  const muteKey = 'echo_muted';
  let muted = false;
  try { muted = localStorage.getItem(muteKey) === '1'; } catch (e) {}

  function audio() {
    if (!actx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      actx = new AC();
    }
    if (actx.state === 'suspended') actx.resume();
    return actx;
  }
  // Browsers only allow audio after a user gesture: unlock on the first click/key.
  const unlock = () => { audio(); document.removeEventListener('pointerdown', unlock); document.removeEventListener('keydown', unlock); };
  document.addEventListener('pointerdown', unlock);
  document.addEventListener('keydown', unlock);

  function siren(level) {
    if (muted) return;
    const ctx = audio();
    if (!ctx || ctx.state !== 'running') return;
    const t0 = ctx.currentTime, osc = ctx.createOscillator(), g = ctx.createGain();
    osc.type = 'sawtooth';
    osc.connect(g); g.connect(ctx.destination);
    if (level === 'CRITICAL') {
      for (let i = 0; i < 4; i++) {
        osc.frequency.setValueAtTime(650, t0 + i * .6);
        osc.frequency.linearRampToValueAtTime(1250, t0 + i * .6 + .3);
        osc.frequency.linearRampToValueAtTime(650, t0 + i * .6 + .6);
      }
      g.gain.setValueAtTime(.0001, t0);
      g.gain.exponentialRampToValueAtTime(.18, t0 + .05);
      g.gain.setValueAtTime(.18, t0 + 2.3);
      g.gain.exponentialRampToValueAtTime(.0001, t0 + 2.4);
      osc.start(t0); osc.stop(t0 + 2.45);
    } else {
      osc.type = 'square';
      osc.frequency.setValueAtTime(880, t0);
      g.gain.setValueAtTime(.0001, t0);
      [0, .3].forEach(d => {
        g.gain.setValueAtTime(.12, t0 + d);
        g.gain.setValueAtTime(.0001, t0 + d + .15);
      });
      osc.start(t0); osc.stop(t0 + .5);
    }
  }

  // ---------------------------------------------------------------- toasts
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const fmtTime = ts => new Date(ts * 1000).toLocaleTimeString('vi-VN');

  function toast(ev) {
    const box = document.getElementById('toasts');
    if (!box) return;
    const el = document.createElement('div');
    el.className = 'toast ' + (ev.level === 'CRITICAL' ? 'crit' : 'warn');
    const who = ev.track_id != null ? ` · người #${ev.track_id}` : '';
    el.innerHTML = `<b>${ev.level === 'CRITICAL' ? '🚨' : '⚠️'} ${esc(ev.message)}</b>
      <div>${esc(ev.source)}${who} · ${fmtTime(ev.ts || ev.t)}</div>
      ${ev.detail ? `<div class="d">${esc(ev.detail)}</div>` : ''}`;
    el.onclick = () => { el.remove(); if (window.EchoTabs) window.EchoTabs.show('evt'); };
    box.prepend(el);
    while (box.children.length > 4) box.lastChild.remove();
    setTimeout(() => el.remove(), ev.level === 'CRITICAL' ? 15000 : 8000);
  }

  function notify(ev) {
    if (!('Notification' in window) || Notification.permission !== 'granted' || !document.hidden) return;
    try {
      new Notification('ECHO MOVE — ' + ev.message, {
        body: `${ev.source}${ev.track_id != null ? ' · người #' + ev.track_id : ''} · ${ev.detail || ''}`,
        tag: `${ev.type}-${ev.source}`, requireInteraction: ev.level === 'CRITICAL',
      });
    } catch (e) {}
  }

  // ---------------------------------------------------------------- public API
  const seen = new Set();
  const pending = {};  // type → time a browser alert was posted (dedupes the /ws/events echo)
  const engines = {};
  const A = window.EchoAlerts = {
    RULES, MESSAGES, LABEL, Engine, esc,
    count: 0,
    get muted() { return muted; },
    setMuted(m) {
      muted = !!m;
      try { localStorage.setItem(muteKey, muted ? '1' : '0'); } catch (e) {}
      paintMute();
      if (!muted) {
        audio();
        if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission();
      }
    },
    /** Show/sound one event. Backend events carry an id and are shown once. */
    raise(ev, fromServer) {
      if (ev.id != null) {
        if (seen.has(ev.id)) return;
        seen.add(ev.id);
      }
      if (fromServer && ev.source === 'browser' && Date.now() - (pending[ev.type] || 0) < 10000) return;
      A.count++;
      toast(ev); siren(ev.level); notify(ev);
      document.dispatchEvent(new CustomEvent('echo:alert', {detail: ev}));
    },
    /** Run local confirmation on one processed frame (browser-side detection / scenarios). */
    observe(stream, persons, quality, opts) {
      const eng = engines[stream] || (engines[stream] = new Engine());
      const t = performance.now() / 1000;
      for (const a of eng.update(persons, quality, t)) {
        const [level, message] = MESSAGES[a.type];
        const ev = {...a, level, message, source: opts.source, ts: Date.now() / 1000};
        A.raise(ev);
        if (opts.report && window.EchoBackend && EchoBackend.online) report(ev, opts.snapshot);
      }
    },
    reset(stream) { if (engines[stream]) engines[stream].reset(); },
  };

  function report(ev, snapshot) {
    pending[ev.type] = Date.now();
    let image = null;
    try { image = snapshot ? snapshot() : null; } catch (e) {}
    fetch(EchoBackend.url('/api/events'), {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({type: ev.type, detail: ev.detail, track_id: ev.track_id, source: 'browser', image}),
    }).then(r => r.ok ? r.json() : null).then(saved => { if (saved && saved.id != null) seen.add(saved.id); })
      .catch(() => {});
  }

  function paintMute() {
    const b = document.getElementById('bMute');
    if (!b) return;
    b.textContent = muted ? '🔕' : '🔔';
    b.title = muted ? 'Còi đang tắt — bấm để bật' : 'Còi đang bật — bấm để tắt';
    b.classList.toggle('muted', muted);
  }

  if (window.EchoBackend) EchoBackend.on('event', ev => A.raise(ev, true));
  const mb = document.getElementById('bMute');
  if (mb) mb.onclick = () => A.setMuted(!muted);
  paintMute();
})();
