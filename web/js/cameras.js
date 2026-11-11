// "Camera" tab: server-side cameras (RTSP / USB / video file) analysed by the backend.
// Grid of MJPEG streams; selecting one drives the 3D worker from that camera.
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const esc = s => window.EchoAlerts ? EchoAlerts.esc(s) : String(s);
  const STATE = {
    online: ['Đang chạy', '#10b981'], connecting: ['Đang kết nối', '#f59e0b'],
    reconnecting: ['Mất tín hiệu — thử lại', '#ef4444'], stalled: ['Khựng hình', '#f59e0b'],
    stopped: ['Đã dừng', '#64748b'], idle: ['Chờ', '#64748b'],
  };
  const C = {active: false, selected: null, ws: null, timer: null, list: []};

  function box() { return $('camBox'); }

  function offline() {
    box().innerHTML = `<div class="hint">
      <b>Chưa kết nối backend.</b><br>
      Camera RTSP / USB do server Python đọc và phân tích. Chạy <code>make run</code>
      (hoặc <code>docker compose up</code>) rồi mở giao diện tại <code>http://localhost:8000</code>.
      <br><button class="b" id="camRetry">↻ Thử kết nối lại</button></div>`;
    $('camRetry').onclick = () => EchoBackend.connect().then(render);
  }

  function empty() {
    box().innerHTML = `<div class="hint">
      <b>Server chưa cấu hình camera.</b><br>
      Đặt biến môi trường <code>ECHO_CAMERAS</code> rồi khởi động lại backend, ví dụ:<br>
      <code>ECHO_CAMERAS="kho=rtsp://user:pass@192.168.1.10:554/stream1,cong=0"</code><br>
      Nguồn có thể là URL RTSP/HTTP, số thứ tự webcam USB (0, 1…) hoặc đường dẫn file video.
      Xem <i>docs/USER_GUIDE.md</i>.</div>`;
  }

  function card(cam) {
    const [txt, col] = STATE[cam.state] || [cam.state, '#64748b'];
    const sel = C.selected === cam.id ? ' sel' : '';
    return `<div class="cam${sel}" data-id="${esc(cam.id)}">
      <div class="camimg"><img alt="${esc(cam.id)}" data-src="${esc(EchoBackend.url('/api/cameras/' + encodeURIComponent(cam.id) + '/stream'))}"></div>
      <div class="camh"><b>${esc(cam.id)}</b><span style="color:${col}">● ${txt}</span></div>
      <div class="camm" data-meta>${meta(cam)}</div>
    </div>`;
  }

  function meta(cam) {
    const q = cam.quality != null ? ` · IQA ${Math.round(cam.quality)}` : '';
    const err = cam.error ? ` · <span style="color:#ef4444">${esc(cam.error)}</span>` : '';
    return `${esc(cam.source)}<br>${cam.fps} FPS · ${cam.persons} người${q} · kết nối lại ${cam.reconnects}${err}`;
  }

  async function refresh() {
    if (!C.active) return;
    if (!EchoBackend.online) { offline(); return; }
    let cams;
    try { cams = await EchoBackend.json('/api/cameras'); } catch (e) { offline(); return; }
    const ids = cams.map(c => c.id).join('|');
    if (ids !== C.list.map(c => c.id).join('|') || !box().querySelector('.camgrid, .hint')) {
      C.list = cams;
      if (!cams.length) { empty(); return; }
      box().innerHTML = `<div class="camtip">Bấm vào một camera để mô phỏng 3D người đầu tiên trong khung hình.</div>
        <div class="camgrid">${cams.map(card).join('')}</div>`;
      box().querySelectorAll('.cam').forEach(el => { el.onclick = () => select(el.dataset.id); });
      streams(true);
    } else {
      C.list = cams;
      cams.forEach(cam => {
        const el = box().querySelector(`.cam[data-id="${CSS.escape(cam.id)}"]`);
        if (!el) return;
        const [txt, col] = STATE[cam.state] || [cam.state, '#64748b'];
        el.querySelector('.camh span').textContent = '● ' + txt;
        el.querySelector('.camh span').style.color = col;
        el.querySelector('[data-meta]').innerHTML = meta(cam);
      });
    }
  }

  // MJPEG <img> keeps an HTTP connection open: attach only while the tab is visible.
  function streams(on) {
    box().querySelectorAll('.camimg img').forEach(img => {
      if (on) { if (!img.getAttribute('src')) img.src = img.dataset.src; }
      else img.removeAttribute('src');
    });
  }

  function select(id) {
    if (C.selected === id) { release(); return; }
    release();
    C.selected = id;
    box().querySelectorAll('.cam').forEach(el => el.classList.toggle('sel', el.dataset.id === id));
    const url = EchoBackend.base.replace(/^http/, 'ws') + '/ws/camera/' + encodeURIComponent(id);
    try { C.ws = new WebSocket(url); } catch (e) { return; }
    C.ws.onmessage = e => {
      let d; try { d = JSON.parse(e.data); } catch (err) { return; }
      if (d.error || !window.EchoApp) return;
      EchoApp.drive(d, id);
    };
    C.ws.onclose = () => { if (C.selected === id) release(); };
  }

  function release() {
    const ws = C.ws;
    C.ws = null; C.selected = null;
    if (ws) { ws.onclose = null; try { ws.close(); } catch (e) {} }
    box().querySelectorAll('.cam.sel').forEach(el => el.classList.remove('sel'));
    if (window.EchoApp) EchoApp.release();
  }

  function render() {
    C.list = [];
    refresh();
  }

  document.addEventListener('echo:tab', e => {
    const on = e.detail === 'cam';
    if (on === C.active) return;
    C.active = on;
    if (on) {
      render();
      C.timer = setInterval(refresh, 3000);
    } else {
      clearInterval(C.timer); C.timer = null;
      streams(false);
      release();
    }
  });
  if (window.EchoBackend) EchoBackend.on('status', () => { if (C.active) render(); });
})();
