// Alerting in the browser: temporal confirmation (same rules as backend alerts/engine.py),
// siren (WebAudio), desktop notifications and toasts. Confirmed alerts from real video
// are reported to the backend event log when one is connected.
(function () {
  "use strict";
  const RULES = {fallS: 1.5, postureS: 3, cooldownS: 30, graceS: 0.5};
  // FALL / SQUAT / STOOP: confirm + snapshot. STANDING / PARTIAL: log only (confirm 0, no image).
  const ACTION = {FALL: 1, SQUAT: 1, STOOP: 1};
  const MESSAGES = {
    FALL: ['CRITICAL', 'Phát hiện công nhân bị ngã'],
    STANDING: ['INFO', 'Công nhân đang đứng'],
    SQUAT: ['INFO', 'Công nhân ngồi xổm'],
    STOOP: ['WARNING', 'Công nhân cúi khom lưng'],
    PARTIAL: ['WARNING', 'Chỉ nhận diện một phần cơ thể'],
  };
  const LABEL = {FALL: 'NGÃ', STANDING: 'ĐỨNG', SQUAT: 'XỔM', STOOP: 'CÚI KHOM', PARTIAL: 'MỘT PHẦN'};

  function Engine() { this.ep = {}; this.last = {}; this.hips = {}; this.tr = {}; }
  Engine.prototype.reset = function () { this.ep = {}; this.hips = {}; this.tr = {}; };
  Engine.prototype.check = function (key, active, t, confirmS, graceS, cooldownS) {
    const ep = this.ep[key] || (this.ep[key] = {start: null, lastTrue: 0, fired: false});
    if (!active) {
      if (ep.start !== null && t - ep.lastTrue > (graceS || RULES.graceS)) this.ep[key] = {start: null, lastTrue: 0, fired: false};
      return false;
    }
    if (ep.start === null) ep.start = t;
    ep.lastTrue = t;
    if (ep.fired || t - ep.start < confirmS) return false;
    if (t - (this.last[key] ?? -1e9) < (cooldownS ?? RULES.cooldownS)) return false;
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
      const id = p.id ?? i, s = p.safety || {}, tech = s.technique || 'STANDING';
      const tr = this.tr[id] || (this.tr[id] = {});
      tr.seen = t;
      const rapid = this.rapidDrop(id, p.keypoints, t);
      const fallS = RULES.fallS * (rapid ? .5 : 1);
      if (this.check('FALL|' + id, tech === 'FALL', t, fallS))
        out.push({type: 'FALL', track_id: id, detail: rapid ? 'Ngã đột ngột' : 'Nằm trên sàn'});
      if (this.check('STOOP|' + id, tech === 'STOOP', t, RULES.postureS))
        out.push({type: 'STOOP', track_id: id, detail: s.detail || ''});
      if (this.check('SQUAT|' + id, tech === 'SQUAT', t, RULES.postureS))
        out.push({type: 'SQUAT', track_id: id, detail: s.detail || ''});
      if (this.check('PARTIAL|' + id, tech === 'PARTIAL', t, 0))
        out.push({type: 'PARTIAL', track_id: id, detail: s.detail || ''});
      if (this.check('STANDING|' + id, tech === 'STANDING', t, 0))
        out.push({type: 'STANDING', track_id: id, detail: s.detail || ''});
    });
    return out;
  };

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

  function beep(freq, dur, type) {
    if (muted) return;
    const ctx = audio(); if (!ctx) return;
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = type || 'square'; o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.2, ctx.currentTime + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + dur);
    o.connect(g); g.connect(ctx.destination);
    o.start(); o.stop(ctx.currentTime + dur + 0.05);
  }

  function siren(level) {
    if (muted) return;
    if (level === 'CRITICAL') {
      beep(880, 0.25); setTimeout(() => beep(660, 0.25), 280); setTimeout(() => beep(880, 0.35), 560);
    } else if (level === 'WARNING') {
      beep(740, 0.15); setTimeout(() => beep(740, 0.15), 200);
    } else {
      beep(520, 0.1, 'sine');
    }
  }

  function toast(a) {
    const box = document.getElementById('toasts'); if (!box) return;
    const lvl = (MESSAGES[a.type] || ['WARNING'])[0];
    const cls = lvl === 'CRITICAL' ? 'crit' : lvl === 'INFO' ? 'info' : 'warn';
    const el = document.createElement('div');
    el.className = 'toast ' + cls;
    el.innerHTML = `<b>${LABEL[a.type] || a.type}</b> · ${esc(a.message || '')}<div class="d">${esc(a.detail || '')}</div>`;
    el.onclick = () => {
      el.remove();
      if (window.EchoTabs) window.EchoTabs.show('evt');
      else {
        const p = document.getElementById('panel-events');
        if (p) p.scrollIntoView({behavior: 'smooth', block: 'nearest'});
      }
    };
    box.appendChild(el);
    setTimeout(() => el.remove(), 8000);
  }

  function notify(a) {
    if (!('Notification' in window) || Notification.permission !== 'granted') return;
    try {
      new Notification(LABEL[a.type] || a.type, {body: (a.message || '') + (a.detail ? ' — ' + a.detail : ''), tag: a.type});
    } catch (e) {}
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  const engine = new Engine();
  const recent = [];

  function raise(a, fromServer) {
    const lvl = (MESSAGES[a.type] || ['WARNING', a.message || a.type])[0];
    const action = !!ACTION[a.type];
    const full = {
      type: a.type, level: lvl, message: a.message || MESSAGES[a.type][1],
      detail: a.detail || '', track_id: a.track_id ?? null, t: a.t || Date.now() / 1000,
      source: a.source || 'browser',
    };
    recent.push(full); if (recent.length > 50) recent.shift();
    // Log-only (STANDING / PARTIAL): save quietly — no siren / desktop notify.
    if (action) { siren(lvl); toast(full); notify(full); }
    else toast(full);
    if (!fromServer && window.EchoBackend && EchoBackend.online) {
      const body = {type: full.type, detail: full.detail, source: full.source,
                    track_id: full.track_id, image: action ? (a.image || null) : null};
      EchoBackend.json('/api/events', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)}).catch(() => {});
    }
  }

  window.EchoAlerts = {
    LABEL, MESSAGES, esc,
    raise,
    observe(source, persons, quality, opts) {
      const t = performance.now() / 1000;
      const alerts = engine.update(persons, quality, t);
      alerts.forEach(a => {
        a.source = (opts && opts.source) || source;
        if (ACTION[a.type] && opts && opts.report && opts.snapshot) {
          try { a.image = opts.snapshot(); } catch (e) {}
        }
        if (opts && opts.report === false) return;
        raise(a, false);
      });
      return alerts;
    },
    muted() { return muted; },
    setMuted(v) {
      muted = !!v;
      try { localStorage.setItem(muteKey, muted ? '1' : '0'); } catch (e) {}
      const b = document.getElementById('bMute');
      if (b) { b.classList.toggle('muted', muted); b.textContent = muted ? '🔕' : '🔔'; }
      if (!muted) audio();
    },
    unlock() { audio(); if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission(); },
  };

  document.addEventListener('DOMContentLoaded', () => {
    const b = document.getElementById('bMute');
    if (b) {
      b.classList.toggle('muted', muted);
      b.textContent = muted ? '🔕' : '🔔';
      b.onclick = () => { EchoAlerts.unlock(); EchoAlerts.setMuted(!EchoAlerts.muted()); };
    }
    document.addEventListener('pointerdown', () => EchoAlerts.unlock(), {once: true});
  });
})();
