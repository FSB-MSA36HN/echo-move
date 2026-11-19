// Events deck: stats panel + hourly chart panel + image gallery panel.
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const esc = s => EchoAlerts.esc(s);
  const PAGE = 8;
  const E = {active: false, offset: 0, total: 0, unack: 0, reloadTimer: null};
  const TYPE_COLOR = {FALL: '#ef4444', STANDING: '#22c55e', SQUAT: '#38bdf8', STOOP: '#f59e0b',
                      PARTIAL: '#facc15'};

  function params(extra) {
    const p = new URLSearchParams();
    const type = $('evType').value, hours = $('evHours').value;
    if (type) p.set('type', type);
    if (hours) p.set('hours', hours);
    if ($('evUnack').checked) p.set('acknowledged', 'false');
    Object.entries(extra || {}).forEach(([k, v]) => p.set(k, v));
    return p;
  }

  function featureOffline(targetId) {
    const el = $(targetId);
    if (!el) return;
    el.innerHTML = `<div class="hint feature-guide">
      <b>Sự kiện — nhật ký tư thế đã xác nhận</b>
      <ul>
        <li><b>Thống kê</b>: tổng số, chưa xử lý, theo loại FALL / STANDING / SQUAT / STOOP (PARTIAL không tạo event).</li>
        <li><b>Biểu đồ giờ</b>: phân bố sự kiện theo khung giờ 0–23 trong khoảng lọc.</li>
        <li><b>Danh sách &amp; ảnh</b>: tối đa 8 ảnh/lần (Load more); FALL / SQUAT / STOOP.</li>
      </ul>
      <div class="guide-actions"><button class="b" data-ev-retry>↻ Thử kết nối lại</button></div>
    </div>`;
  }

  function offline() {
    featureOffline('evStats');
    const chart = $('evChart');
    if (chart) chart.style.display = 'none';
    $('evMore').innerHTML = '';
    featureOffline('evList');
    document.querySelectorAll('[data-ev-retry]').forEach(btn => {
      btn.onclick = () => EchoBackend.connect().then(load);
    });
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
        ? `<button class="b" id="evNext">Load more (${E.total - E.offset})</button>` : '';
      if ($('evNext')) $('evNext').onclick = () => load(true);
    } catch (e) {
      $('evList').innerHTML = `<div class="hint">Không tải được sự kiện: ${esc(e.message)}</div>`;
    }
  }

  function renderStats(s) {
    badge(s.unacknowledged);
    const by = s.by_type || {};
    const cell = (label, v, col) =>
      `<div class="card stat"><h4 style="color:${col}">${label}</h4><div class="big">${v}</div></div>`;
    const fa = Object.values(s.false_alarms || {}).reduce((a, b) => a + b, 0);
    $('evStats').innerHTML =
      cell('Tổng sự kiện', s.total, 'var(--c)') +
      cell('Chưa xử lý', s.unacknowledged, s.unacknowledged ? '#ef4444' : '#10b981') +
      cell('Ngã', by.FALL || 0, TYPE_COLOR.FALL) +
      cell('Đứng', by.STANDING || 0, TYPE_COLOR.STANDING) +
      cell('Ngồi xổm', by.SQUAT || 0, TYPE_COLOR.SQUAT) +
      cell('Cúi khom', by.STOOP || 0, TYPE_COLOR.STOOP) +
      cell('Báo nhầm', s.total ? `${fa} (${Math.round(100 * fa / s.total)}%)` : 0, '#94a3b8');
    chart(s.by_hour || []);
  }

  function chart(hours) {
    const c = $('evChart');
    if (!c) return;
    c._hours = hours;
    c.style.display = 'block';
    const wrap = c.parentElement;
    const W = c.width = Math.max(320, (wrap && wrap.clientWidth) || c.clientWidth || 600);
    const H = c.height = 180;
    const ctx = c.getContext('2d');
    ctx.clearRect(0, 0, W, H);
    const max = Math.max(1, ...hours), bw = W / 24;
    const padBot = 22;
    ctx.font = '12px IBM Plex Sans, system-ui, sans-serif';
    ctx.fillStyle = '#8b9bb4';
    ctx.fillText('Số sự kiện theo từng giờ (0–23h)', 8, 18);
    for (let h = 0; h < 24; h++) {
      const v = hours[h] || 0;
      const bh = (H - 28 - padBot) * v / max;
      ctx.fillStyle = v ? '#2dd4bf' : '#1e293b';
      ctx.fillRect(h * bw + 3, H - padBot - bh, bw - 6, Math.max(bh, 2));
      if (h % 2 === 0) {
        ctx.fillStyle = '#8b9bb4';
        ctx.fillText(String(h), h * bw + 4, H - 6);
      }
      if (v) {
        ctx.fillStyle = '#e8eef7';
        ctx.font = '11px IBM Plex Mono, monospace';
        ctx.fillText(String(v), h * bw + 4, H - padBot - bh - 4);
        ctx.font = '12px IBM Plex Sans, system-ui, sans-serif';
      }
    }
  }

  function row(ev) {
    const when = new Date(ev.ts * 1000);
    const who = ev.track_id != null ? '#' + ev.track_id : '-';
    const img = ev.has_image
      ? `<img class="thumb" loading="lazy" src="${esc(EchoBackend.url('/api/events/' + ev.id + '/image'))}" data-full="1" alt="">`
      : '<div class="thumb none">Không có ảnh</div>';
    const ack = ev.false_alarm ? '<span class="ok" style="color:#94a3b8">✗ Báo nhầm</span>'
      : ev.acknowledged ? '<span class="ok">✓ Đã xử lý</span>'
      : `<button class="b sm" data-ack="${ev.id}">Xác nhận</button>
         <button class="b sm" data-fa="${ev.id}" title="Đánh dấu cảnh báo sai để tinh chỉnh ngưỡng">Báo nhầm</button>`;
    const clip = ev.has_clip ? `<button class="b sm" data-clip="${ev.id}">▶ Clip</button>` : '';
    const esc8 = ev.escalated ? ' <span class="tag" style="background:#7c3aed">LEO THANG</span>' : '';
    return `<article class="ev${ev.acknowledged ? ' done' : ''}" data-id="${ev.id}">
      ${img}
      <div class="evb">
        <div><span class="tag" style="background:${TYPE_COLOR[ev.type] || '#64748b'}">${esc(EchoAlerts.LABEL[ev.type] || ev.type)}</span>
          <b>${esc(ev.message)}</b>${esc8}</div>
        <div class="evm">${when.toLocaleString('vi-VN')} · ${esc(ev.source)} · người ${who}</div>
        ${ev.detail ? `<div class="evm">${esc(ev.detail)}</div>` : ''}
      </div>
      <div class="eva">${clip}${ack}</div>
    </article>`;
  }

  function renderList(items, append) {
    const list = $('evList');
    const visible = (items || []).filter(ev => ev.type !== 'STANDING');
    if (!append) list.innerHTML = visible.length ? '' : '<div class="hint">Chưa có sự kiện trong khoảng thời gian này.</div>';
    if (visible.length) list.insertAdjacentHTML('beforeend', visible.map(row).join(''));
  }

  async function ack(id, btn, falseAlarm) {
    const eva = btn.closest('.eva');
    eva.querySelectorAll('[data-ack],[data-fa]').forEach(b => { b.disabled = true; });
    try {
      await EchoBackend.json(`/api/events/${id}/${falseAlarm ? 'false-alarm' : 'ack'}`, {method: 'POST'});
      btn.closest('.ev').classList.add('done');
      eva.querySelectorAll('[data-fa]').forEach(b => b.remove());
      const ackBtn = eva.querySelector('[data-ack]');
      if (ackBtn) {
        ackBtn.outerHTML = falseAlarm
          ? '<span class="ok" style="color:#94a3b8">✗ Báo nhầm</span>' : '<span class="ok">✓ Đã xử lý</span>';
      }
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
    v.querySelector('img').removeAttribute('src');
  }

  function scheduleReload() {
    clearTimeout(E.reloadTimer);
    E.reloadTimer = setTimeout(() => { if (E.active) load(); }, 600);
  }

  function setUnackSys(n) {
    const el = $('sysUnack');
    if (!el) return;
    el.textContent = String(n);
    el.className = 'v' + (n ? ' bad' : ' ok');
  }

  function badge(n) {
    E.unack = n;
    const b = $('evBadge');
    if (b) { b.textContent = n > 99 ? '99+' : n || ''; b.style.display = n ? 'inline-block' : 'none'; }
    setUnackSys(n);
  }

  function activate() {
    E.active = true;
    load();
    window.addEventListener('resize', () => {
      if (!E.active) return;
      const c = $('evChart');
      if (c && c.style.display !== 'none' && c._hours) chart(c._hours);
    });
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

    document.addEventListener('echo:dashboard', activate);
    EchoBackend.on('event', () => { if (E.active) scheduleReload(); else { badge(E.unack + 1); } });
    EchoBackend.on('update', () => { if (E.active) scheduleReload(); });
    EchoBackend.on('status', online => {
      if (E.active) load();
      else if (online) EchoBackend.json('/api/stats?hours=24').then(s => badge(s.unacknowledged)).catch(() => {});
      else badge(0);
    });
  }

  bind();
  if (document.getElementById('evList')) activate();
})();
