// Finds a running ECHO MOVE backend and keeps a live /ws/events connection.
// Order: ?server=… (remembered) → same origin (backend serving the UI) → localhost:8000.
// Everything degrades gracefully: with no backend the UI stays fully usable offline.
(function () {
  "use strict";
  const C = window.ECHO_CONFIG;
  const handlers = {};
  const B = window.EchoBackend = {
    online: false, base: null, health: null, ws: null,
    on(type, fn) { (handlers[type] = handlers[type] || []).push(fn); },
    url(path) { return B.base + path; },
    async json(path, opts) {
      const r = await fetch(B.url(path), opts);
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      return r.json();
    },
    connect,
  };
  const emit = (type, data) => (handlers[type] || []).forEach(fn => { try { fn(data); } catch (e) { console.error(e); } });

  function candidates() {
    const c = [];
    if (C.explicit) c.push(C.apiBase);
    if (/^https?:$/.test(location.protocol)) c.push(location.origin);
    c.push('http://localhost:8000');
    return [...new Set(c)];
  }

  async function probe(base) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 2000);
    try {
      const r = await fetch(base + '/health', {signal: ctl.signal, cache: 'no-store'});
      if (!r.ok) return null;
      const j = await r.json();
      return j && j.status === 'ok' ? j : null;
    } catch (e) { return null; } finally { clearTimeout(timer); }
  }

  function pill() {
    const el = document.getElementById('beSt');
    if (!el) return;
    if (B.online) {
      const h = B.health;
      el.className = 'pill on';
      el.textContent = `● Backend v${h.version} · ${h.yolo ? 'AI' : 'DEMO'} · ${h.cameras} cam`;
      el.title = B.base + (h.notify && h.notify.length ? ` · thông báo: ${h.notify.join(', ')}` : '');
    } else {
      el.className = 'pill off';
      el.textContent = '○ Chưa kết nối backend';
      el.title = 'Chạy `make run` hoặc `docker compose up` rồi tải lại trang';
    }
  }

  function setState(base, health) {
    const was = B.online;
    B.online = !!health; B.base = base; B.health = health;
    if (B.online) {
      C.apiBase = base;
      C.wsUrl = base.replace(/^http/, 'ws') + '/ws/pose';
      const inp = document.getElementById('wsurl');
      if (inp && document.activeElement !== inp) inp.value = C.wsUrl;
      openEvents();
    } else closeEvents();
    pill();
    if (was !== B.online) emit('status', B.online);
  }

  async function connect() {
    for (const base of candidates()) {
      const h = await probe(base);
      if (h) { setState(base, h); return true; }
    }
    setState(null, null);
    return false;
  }

  async function heartbeat() {
    if (B.online) {
      const h = await probe(B.base);
      if (h) { B.health = h; pill(); } else setState(null, null);
    } else await connect();
  }

  let retry = 0;
  function openEvents() {
    if (B.ws) return;
    let ws;
    try { ws = new WebSocket(B.base.replace(/^http/, 'ws') + '/ws/events'); } catch (e) { return; }
    B.ws = ws;
    ws.onopen = () => { retry = 0; };
    ws.onmessage = e => {
      let ev; try { ev = JSON.parse(e.data); } catch (err) { return; }
      if (ev && ev.type && !ev.ping) emit('event', ev);
    };
    ws.onclose = () => {
      B.ws = null;
      if (B.online) setTimeout(openEvents, Math.min(30000, 1000 * 2 ** retry++));
    };
  }

  function closeEvents() {
    if (B.ws) { const ws = B.ws; B.ws = null; try { ws.close(); } catch (e) {} }
  }

  pill();
  connect();
  setInterval(heartbeat, 15000);
})();
