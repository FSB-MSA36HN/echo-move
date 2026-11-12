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
      <div class="camimg"><img alt="${esc(cam.id)}" data-src="${esc(EchoBackend.url('/api/cameras/' + encodeURIComponent(cam.id) + '/stream'))}">
        <svg class="zdraw" viewBox="0 0 1 1" preserveAspectRatio="none"></svg></div>
      <div class="camh"><b>${esc(cam.id)}</b><span style="color:${col}">● ${txt}</span>
        <button class="b sm" data-cfg="${esc(cam.id)}" title="Vùng nguy hiểm & luật cảnh báo">⚙</button></div>
      <div class="camm" data-meta>${meta(cam)}</div>
    </div>`;
  }

  function meta(cam) {
    const q = cam.quality != null ? ` · IQA ${Math.round(cam.quality)}` : '';
    const err = cam.error ? ` · <span style="color:#ef4444">${esc(cam.error)}</span>` : '';
    const z = (cam.zones || []).length ? ` · ${cam.zones.length} vùng cấm` : '';
    const off = (cam.disabled_rules || []).length ? ` · tắt ${cam.disabled_rules.map(esc).join(', ')}` : '';
    return `${esc(cam.source)}<br>${cam.fps} FPS · ${cam.persons} người${q}${z}${off} · kết nối lại ${cam.reconnects}${err}`;
  }

  // ---------------------------------------------------------------- zone / rule editor
  const RULE_NAMES = {FALL: 'Ngã', MANDOWN: 'Không dậy sau ngã', RECOVERED: 'Đã đứng dậy', POSTURE: 'Cúi sai',
    ERGO: 'REBA tích lũy', ZONE: 'Vùng cấm', PPE: 'Đồ bảo hộ', CAMERA: 'Chất lượng ảnh', OFFLINE: 'Mất tín hiệu'};
  const ED = {id: null, zones: [], disabled: [], rules: [], drawing: null};

  async function openEditor(id) {
    let cfg;
    try { cfg = await EchoBackend.json('/api/cameras/' + encodeURIComponent(id) + '/config'); }
    catch (e) { return; }
    Object.assign(ED, {id, zones: cfg.zones, disabled: cfg.disabled_rules, rules: cfg.rules, drawing: null});
    paintEditor();
  }

  function closeEditor() {
    ED.id = null; ED.drawing = null;
    const p = $('camCfg'); if (p) p.remove();
    paintSvg();
  }

  function paintEditor() {
    let p = $('camCfg');
    if (!p) { p = document.createElement('div'); p.id = 'camCfg'; p.className = 'card camcfg'; box().appendChild(p); }
    const zones = ED.zones.map((z, i) => `<div class="zrow"><input data-zn="${i}" value="${esc(z.name)}" maxlength="40">
        <label>chờ <input data-zd="${i}" type="number" min="0" step="0.5" value="${z.dwell_s}"> s</label>
        <span class="evm">${z.points.length} điểm</span><button class="b sm" data-zx="${i}">✕</button></div>`).join('')
      || '<div class="evm">Chưa có vùng nào.</div>';
    const rules = ED.rules.map(r => `<label class="rule"><input type="checkbox" data-rule="${r}" ${ED.disabled.includes(r) ? '' : 'checked'}> ${esc(RULE_NAMES[r] || r)}</label>`).join('');
    const drawing = ED.drawing
      ? `<div class="hint">Bấm lên hình camera <b>${esc(ED.id)}</b> để thêm điểm (${ED.drawing.length} điểm).
           <button class="b sm" id="zDone" ${ED.drawing.length < 3 ? 'disabled' : ''}>✓ Xong vùng</button>
           <button class="b sm" id="zCancel">Hủy</button></div>`
      : '<button class="b sm" id="zNew">✏️ Vẽ vùng mới</button>';
    p.innerHTML = `<h4>⚙ Camera ${esc(ED.id)} — vùng nguy hiểm & luật cảnh báo</h4>
      ${zones}${drawing}
      <div class="rules">${rules}</div>
      <div><button class="b" id="cfgSave">💾 Lưu</button> <button class="b" id="cfgClose">Đóng</button>
        <span class="evm" id="cfgMsg"></span></div>`;
    p.querySelectorAll('[data-zn]').forEach(el => { el.oninput = () => { ED.zones[el.dataset.zn].name = el.value; }; });
    p.querySelectorAll('[data-zd]').forEach(el => { el.oninput = () => { ED.zones[el.dataset.zd].dwell_s = +el.value || 0; }; });
    p.querySelectorAll('[data-zx]').forEach(el => { el.onclick = () => { ED.zones.splice(+el.dataset.zx, 1); paintEditor(); }; });
    p.querySelectorAll('[data-rule]').forEach(el => {
      el.onchange = () => {
        ED.disabled = ED.disabled.filter(r => r !== el.dataset.rule);
        if (!el.checked) ED.disabled.push(el.dataset.rule);
      };
    });
    if ($('zNew')) $('zNew').onclick = () => { ED.drawing = []; paintEditor(); };
    if ($('zCancel')) $('zCancel').onclick = () => { ED.drawing = null; paintEditor(); };
    if ($('zDone')) $('zDone').onclick = () => {
      ED.zones.push({name: 'Vùng ' + (ED.zones.length + 1), points: ED.drawing, dwell_s: 1});
      ED.drawing = null; paintEditor();
    };
    $('cfgClose').onclick = closeEditor;
    $('cfgSave').onclick = save;
    paintSvg();
  }

  function paintSvg() {
    box().querySelectorAll('.cam').forEach(el => {
      const svg = el.querySelector('.zdraw');
      const on = el.dataset.id === ED.id;
      el.classList.toggle('editing', on && !!ED.drawing);
      if (!svg) return;
      if (!on) { svg.innerHTML = ''; return; }
      const poly = pts => pts.map(p => p.join(',')).join(' ');
      svg.innerHTML = ED.zones.map(z => `<polygon points="${poly(z.points)}" class="zp"/>`).join('') +
        (ED.drawing ? `<polyline points="${poly(ED.drawing)}" class="zn"/>` +
          ED.drawing.map(p => `<circle cx="${p[0]}" cy="${p[1]}" r=".008" class="zc"/>`).join('') : '');
    });
  }

  async function save() {
    const msg = $('cfgMsg');
    try {
      await EchoBackend.json('/api/cameras/' + encodeURIComponent(ED.id) + '/config', {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({zones: ED.zones, disabled_rules: ED.disabled}),
      });
      msg.textContent = '✓ Đã lưu — áp dụng ngay';
      msg.style.color = '#10b981';
      refresh();
    } catch (e) { msg.textContent = 'Lỗi: ' + e.message; msg.style.color = '#ef4444'; }
  }

  function addPoint(el, ev) {
    const r = el.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width));
    const y = Math.min(1, Math.max(0, (ev.clientY - r.top) / r.height));
    ED.drawing.push([+x.toFixed(4), +y.toFixed(4)]);
    paintEditor();
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
      box().innerHTML = `<div class="camtip">Bấm vào một camera để mô phỏng 3D người đầu tiên trong khung hình. Nút ⚙ để vẽ vùng nguy hiểm và bật/tắt luật cảnh báo.</div>
        <div class="camgrid">${cams.map(card).join('')}</div>`;
      box().querySelectorAll('.cam').forEach(el => {
        el.onclick = ev => {
          const cfg = ev.target.closest('[data-cfg]');
          if (cfg) { ev.stopPropagation(); openEditor(cfg.dataset.cfg); return; }
          if (ED.drawing && ED.id === el.dataset.id && ev.target.closest('.camimg')) {
            addPoint(el.querySelector('.camimg'), ev); return;
          }
          select(el.dataset.id);
        };
      });
      streams(true);
      if (ED.id) paintEditor();
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
