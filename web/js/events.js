// "Sự kiện" tab: event history from the backend SQLite log — filters, stats, snapshots,
// acknowledge, CSV export; refreshes live from /ws/events.
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const esc = s => EchoAlerts.esc(s);
  const PAGE = 30;
  const E = {active: false, offset: 0, total: 0, unack: 0, reloadTimer: null};
  const TYPE_COLOR = {FALL: '#ef4444', MANDOWN: '#b91c1c', RECOVERED: '#10b981', POSTURE: '#f59e0b',
                      ERGO: '#d97706', ZONE: '#e11d48', PPE: '#eab308', CAMERA: '#0ea5e9', OFFLINE: '#64748b'};

  function params(extra) {
    const p = new URLSearchParams();
    const type = $('evType').value, hours = $('evHours').value;
    if (type) p.set('type', type);
    if (hours) p.set('hours', hours);
    if ($('evUnack').checked) p.set('acknowledged', 'false');
    Object.entries(extra || {}).forEach(([k, v]) => p.set(k, v));
    return p;
  }

  function offline() {
    $('evStats').innerHTML = '';
    $('evChart').style.display = 'none';
    $('evMore').innerHTML = '';
    $('evList').innerHTML = `<div class="hint"><b>Chưa kết nối backend.</b><br>
      Nhật ký sự kiện (SQLite + ảnh chụp) được lưu trên server. Chạy <code>make run</code>
      hoặc <code>docker compose up</code>; khi đó cảnh báo xác nhận từ camera server, chế độ
      Server và AI trên trình duyệt đều được ghi lại tại đây.<br>
      <button class="b" id="evRetry">↻ Thử kết nối lại</button></div>`;
    $('evRetry').onclick = () => EchoBackend.connect().then(load);
  }

  async function load(append) {
    if (!EchoBackend.online) { offline(); badge(0); return; }
    if (!append) E.offset = 0;
    const hours = $('evHours').value || 24 * 365;
    $('evCsv').href = EchoBackend.url('/api/events.csv?' + params({}).toString());
    try {
      const [page, stats] = await Promise.all([
        EchoBackend.json('/api/events?' + params({limit: PAGE, offset: E.offset})),
        append ? null : EchoBackend.json('/api/stats?hours=' + hours),
      ]);
      if (stats) renderStats(stats);
      renderList(page.items, append);
      E.total = page.total;
      E.offset += page.items.length;
      $('evMore').innerHTML = E.offset < E.total
        ? `<button class="b" id="evNext">Xem thêm (${E.total - E.offset})</button>` : '';
      if ($('evNext')) $('evNext').onclick = () => load(true);
    } catch (e) {
      $('evList').innerHTML = `<div class="hint">Không tải được sự kiện: ${esc(e.message)}</div>`;
    }
  }

  function renderStats(s) {
    badge(s.unacknowledged);
    const by = s.by_type || {};
    const cell = (label, v, col) => `<div class="card stat"><h4 style="color:${col}">${label}</h4><div class="big">${v}</div></div>`;
    const fa = Object.values(s.false_alarms || {}).reduce((a, b) => a + b, 0);
    $('evStats').innerHTML =
      cell('Tổng sự kiện', s.total, 'var(--c)') +
      cell('Chưa xử lý', s.unacknowledged, s.unacknowledged ? '#ef4444' : '#10b981') +
      cell('Ngã / không dậy', `${by.FALL || 0} / ${by.MANDOWN || 0}`, TYPE_COLOR.FALL) +
      cell('Cúi sai / REBA', `${by.POSTURE || 0} / ${by.ERGO || 0}`, TYPE_COLOR.POSTURE) +
      cell('Vùng cấm / bảo hộ', `${by.ZONE || 0} / ${by.PPE || 0}`, TYPE_COLOR.ZONE) +
      cell('Camera kém / mất', `${by.CAMERA || 0} / ${by.OFFLINE || 0}`, TYPE_COLOR.CAMERA) +
      cell('Báo nhầm', s.total ? `${fa} (${Math.round(100 * fa / s.total)}%)` : 0, '#94a3b8') +
      cell('Nguồn', Object.keys(s.by_source || {}).length, '#a78bfa');
    chart(s.by_hour || []);
  }

  function chart(hours) {
    const c = $('evChart');
    c.style.display = 'block';
    const W = c.width = c.clientWidth || 600, H = c.height = 90;
    const ctx = c.getContext('2d');
    ctx.clearRect(0, 0, W, H);
    const max = Math.max(1, ...hours), bw = W / 24;
    ctx.font = '9px Courier New';
    for (let h = 0; h < 24; h++) {
      const v = hours[h] || 0, bh = (H - 36) * v / max;
      ctx.fillStyle = v ? '#00ffcc' : '#1e293b';
      ctx.fillRect(h * bw + 2, H - 12 - bh, bw - 4, Math.max(bh, 1));
      if (h % 3 === 0) { ctx.fillStyle = '#64748b'; ctx.fillText(h + 'h', h * bw + 2, H - 1); }
      if (v) { ctx.fillStyle = '#e2e8f0'; ctx.fillText(v, h * bw + 3, H - 15 - bh); }
    }
    ctx.fillStyle = '#94a3b8';
    ctx.fillText('Sự kiện theo giờ trong ngày', 4, 10);
  }

  function row(ev) {
    const when = new Date(ev.ts * 1000);
    const who = ev.track_id != null ? '#' + ev.track_id : '-';
    const img = ev.has_image
      ? `<img class="thumb" loading="lazy" src="${esc(EchoBackend.url('/api/events/' + ev.id + '/image'))}" data-full="1">`
      : '<div class="thumb none">—</div>';
    const ack = ev.false_alarm ? '<span class="ok" style="color:#94a3b8">✗ Báo nhầm</span>'
      : ev.acknowledged ? '<span class="ok">✓ Đã xử lý</span>'
      : `<button class="b sm" data-ack="${ev.id}">Xác nhận</button>
         <button class="b sm" data-fa="${ev.id}" title="Đánh dấu cảnh báo sai để tinh chỉnh ngưỡng">Báo nhầm</button>`;
    const clip = ev.has_clip ? `<button class="b sm" data-clip="${ev.id}">▶ Clip</button>` : '';
    const esc8 = ev.escalated ? ' <span class="tag" style="background:#7c3aed">LEO THANG</span>' : '';
    return `<div class="ev${ev.acknowledged ? ' done' : ''}" data-id="${ev.id}">
      ${img}
      <div class="evb">
        <div><span class="tag" style="background:${TYPE_COLOR[ev.type] || '#64748b'}">${esc(EchoAlerts.LABEL[ev.type] || ev.type)}</span>
          <b>${esc(ev.message)}</b>${esc8}</div>
        <div class="evm">${when.toLocaleString('vi-VN')} · ${esc(ev.source)} · người ${who}</div>
        ${ev.detail ? `<div class="evm">${esc(ev.detail)}</div>` : ''}
      </div>
      <div class="eva">${clip}${ack}</div>
    </div>`;
  }

  function renderList(items, append) {
    const list = $('evList');
    if (!append) list.innerHTML = items.length ? '' : '<div class="hint">Chưa có sự kiện trong khoảng thời gian này.</div>';
    list.insertAdjacentHTML('beforeend', items.map(row).join(''));
  }

  function badge(n) {
    E.unack = n;
    const b = $('evBadge');
    if (b) { b.textContent = n > 99 ? '99+' : n || ''; b.style.display = n ? 'inline-block' : 'none'; }
  }

  async function ack(id, btn, falseAlarm) {
    const eva = btn.closest('.eva');
    eva.querySelectorAll('[data-ack],[data-fa]').forEach(b => { b.disabled = true; });
    try {
      await EchoBackend.json(`/api/events/${id}/${falseAlarm ? 'false-alarm' : 'ack'}`, {method: 'POST'});
      btn.closest('.ev').classList.add('done');
      eva.querySelectorAll('[data-fa]').forEach(b => b.remove());
      eva.querySelector('[data-ack]').outerHTML = falseAlarm
        ? '<span class="ok" style="color:#94a3b8">✗ Báo nhầm</span>' : '<span class="ok">✓ Đã xử lý</span>';
      const stats = await EchoBackend.json('/api/stats?hours=' + ($('evHours').value || 24 * 365));
      renderStats(stats);
    } catch (e) { eva.querySelectorAll('button').forEach(b => { b.disabled = false; }); }
  }

  function viewer(src, caption) {
    const v = $('imgv');
    v.querySelector('img').src = src;
    v.querySelector('.cap').innerHTML = caption || '';
    v.hidden = false;
  }

  function closeViewer() {
    const v = $('imgv');
    v.hidden = true;
    v.querySelector('img').removeAttribute('src');  // stops a playing MJPEG clip
  }

  function scheduleReload() {
    clearTimeout(E.reloadTimer);
    E.reloadTimer = setTimeout(() => { if (E.active) load(); }, 600);
  }

  function bind() {
    ['evType', 'evHours', 'evUnack'].forEach(id => { $(id).onchange = () => load(); });
    $('evRef').onclick = () => load();
    $('evList').onclick = e => {
      const btn = e.target.closest('[data-ack]');
      if (btn) { ack(btn.dataset.ack, btn, false); return; }
      const fa = e.target.closest('[data-fa]');
      if (fa) { ack(fa.dataset.fa, fa, true); return; }
      const clip = e.target.closest('[data-clip]');
      if (clip) {
        const id = clip.dataset.clip;
        viewer(EchoBackend.url(`/api/events/${id}/clip?t=${Date.now()}`),
          `Clip sự kiện #${id} (trước và sau cảnh báo) · <a href="${esc(EchoBackend.url(`/api/events/${id}/clip.mp4`))}" download onclick="event.stopPropagation()">⬇ Tải MP4</a>`);
        return;
      }
      if (e.target.matches('img.thumb')) viewer(e.target.src);
    };
    $('imgv').onclick = closeViewer;
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeViewer(); });

    document.addEventListener('echo:tab', e => {
      E.active = e.detail === 'evt';
      if (E.active) load();
    });
    EchoBackend.on('event', () => { if (E.active) scheduleReload(); else badge(E.unack + 1); });
    EchoBackend.on('update', () => { if (E.active) scheduleReload(); });
    EchoBackend.on('status', online => {
      if (E.active) load();
      else if (online) EchoBackend.json('/api/stats?hours=24').then(s => badge(s.unacknowledged)).catch(() => {});
      else badge(0);
    });
  }

  bind();
})();
