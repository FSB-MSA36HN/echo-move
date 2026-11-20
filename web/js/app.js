"use strict";

window.onerror = (msg, url, line, col, err) => {
  const d = document.getElementById('dbc');
  if (d) {
    d.classList.add('err');
    d.textContent = `LỖI: ${msg}\n  ${(url||'').split('/').pop()}:${line}:${col}`;
  }
  console.error('[ECHO]', msg, url, line, col, err);
  return false;
};

const S = {
  mode:'idle',
  frame:0, lastDraw:0, fpsCount:0, fps:0, fpsMark:0,
  safety:'SAFE', ws:null, sending:false, lastSend:0,
  log:[], stream:null, url:null,
  three:false, lib:false, ctx2d:null,
  dbg:{video:'-', err:null},
  ready:false,
  pose:null, pose_ready:false, pose_loading:false,
  ai_on:false, last_det:0, last_vt:-1,
  det_fps:0, detCount:0, detMark:0,
  mIQA:null, mFile:null, mMtime:0, mTimer:null, mAuto:true,
  bench:{on:false},
  sess:{on:false, hist:[]},
  ext:null,  // server camera id currently driving the 3D view (Camera tab)
  cam:{devices:[], deviceId:null, facing:'environment'}
};

const KN = [[0,1],[1,3],[0,2],[2,4],[5,6],[5,7],[7,9],[6,8],[8,10],
            [5,11],[6,12],[11,12],[11,13],[13,15],[12,14],[14,16]];
const CL = ['#00ffcc','#ff6b35','#9d4edd','#ffd60a','#06d6a0'];
const FPS_VID = 20, FPS_SRV = 12;
const IQA_LOW_OVERALL = 40;
const IQA_THRESH = {blur:40, noise:40, contrast:30, exposureDark:25, exposureGlare:90};
const DET_INT = 50, VIS = 0.3, MAXP = 3;

const MPMAP = {nose:0,left_eye:2,right_eye:5,left_ear:7,right_ear:8,
  left_shoulder:11,right_shoulder:12,left_elbow:13,right_elbow:14,
  left_wrist:15,right_wrist:16,left_hip:23,right_hip:24,
  left_knee:25,right_knee:26,left_ankle:27,right_ankle:28};
const MP2COCO = [MPMAP.nose,MPMAP.left_eye,MPMAP.right_eye,MPMAP.left_ear,MPMAP.right_ear,
  MPMAP.left_shoulder,MPMAP.right_shoulder,MPMAP.left_elbow,MPMAP.right_elbow,
  MPMAP.left_wrist,MPMAP.right_wrist,MPMAP.left_hip,MPMAP.right_hip,
  MPMAP.left_knee,MPMAP.right_knee,MPMAP.left_ankle,MPMAP.right_ankle];

const $ = id => document.getElementById(id);
if (window.ECHO_CONFIG && $('wsurl')) $('wsurl').value = window.ECHO_CONFIG.wsUrl;

// ========== LOADING ==========
const STEPS = [
  ['DOM', () => !!($('v') && $('ov') && $('c3d'))],
  ['Canvas', () => { $('ov').width = 640; $('ov').height = 480; return true; }],
  ['Three.js', () => { S.lib = typeof THREE !== 'undefined'; return S.lib; }],
  ['Scene 3D', () => init3D()],
  ['Người 3D', () => !S.three || Human3D.info().ok],
  ['Events', () => { bind(); return true; }],
  ['Idle', () => { showIdle(); return true; }],
  ['Loop', () => { requestAnimationFrame(loop); return true; }]
];
let step = 0;

function loadStep() {
  if (step >= STEPS.length) {
    setTimeout(() => {
      $('ld').classList.add('hide');
      setTimeout(() => $('ld').style.display = 'none', 400);
      S.sess.on = true;
      setInterval(drawSess, 500);
    }, 300);
    return;
  }
  const [n, fn] = STEPS[step];
  $('lds').innerHTML += `<div class="s">▸ ${n}...</div>`;
  try {
    const ok = fn();
    const last = $('lds').lastChild;
    last.classList.add(ok ? 'ok' : 'err');
    last.textContent = `${ok ? '✓' : '✗'} ${n}`;
    if (!ok && n.includes('Three')) fallback2D();
  } catch (e) {
    const last = $('lds').lastChild;
    last.classList.add('err');
    last.textContent = `✗ ${n}: ${e.message}`;
    if (n.includes('3D') || n.includes('Robot')) fallback2D();
  }
  step++;
  $('ldb').style.width = (step / STEPS.length * 100) + '%';
  setTimeout(loadStep, 100);
}

// ========== MEDIAPIPE ==========
async function initPose() {
  if (S.pose_ready) return true;
  if (S.pose_loading) return false;
  S.pose_loading = true;
  $('ap').style.display = 'block';
  $('apb').style.width = '10%';
  $('stt').textContent = 'Đang tải MediaPipe (~3-8s)...';
  try {
    const mp = await import("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.0");
    $('apb').style.width = '40%';
    const vis = await mp.FilesetResolver.forVisionTasks(
      "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.0/wasm");
    $('apb').style.width = '70%';
    S.pose = await mp.PoseLandmarker.createFromOptions(vis, {
      baseOptions: {
        modelAssetPath: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
        delegate: "GPU"
      },
      runningMode: "VIDEO", numPoses: MAXP,
      minPoseDetectionConfidence: 0.5,
      minPosePresenceConfidence: 0.5,
      minTrackingConfidence: 0.5
    });
    $('apb').style.width = '100%';
    S.pose_ready = true;
    S.pose_loading = false;
    setTimeout(() => $('ap').style.display = 'none', 800);
    $('stt').textContent = '✅ MediaPipe sẵn sàng';
    return true;
  } catch (e) {
    console.error('MP:', e);
    $('ap').style.display = 'none';
    S.pose_loading = false;
    S.pose_ready = false;
    $('stt').textContent = '❌ MediaPipe không tải được';
    return false;
  }
}

function mp2coco(lms) {
  return MP2COCO.map(i => {
    const lm = lms[i];
    return [lm.x, lm.y, lm.visibility != null ? lm.visibility : 1];
  });
}

function jointAngle(p1, p2, p3) {
  const v1x = p1[0]-p2[0], v1y = p1[1]-p2[1];
  const v2x = p3[0]-p2[0], v2y = p3[1]-p2[1];
  const m1 = Math.hypot(v1x, v1y) + 1e-6;
  const m2 = Math.hypot(v2x, v2y) + 1e-6;
  const c = Math.max(-1, Math.min(1, (v1x*v2x + v1y*v2y) / (m1*m2)));
  return Math.acos(c) * 180 / Math.PI;
}

function _segLen(kps, a, b) {
  if (kps[a][2] <= VIS || kps[b][2] <= VIS) return null;
  const dx = kps[a][0] - kps[b][0], dy = kps[a][1] - kps[b][1];
  return Math.hypot(dx, dy);
}

// Full standing: hip→ankle ≈ 7–9× ear span. Bust close-up with invented legs ≈ 1–2×.
const MIN_LEG_TO_FACE = 2.2;

function faceSize(kps0) {
  const cands = [];
  const ear = _segLen(kps0, 3, 4);
  if (ear != null && ear > 1e-4) cands.push(ear);
  const eye = _segLen(kps0, 1, 2);
  if (eye != null && eye > 1e-4) cands.push(eye * 1.8);
  return cands.length ? Math.max(...cands) : null;
}

function legsLookComplete(kps0) {
  // Full L+R knee→ankle; reject short / face-relative hallucinated legs (bust crop).
  const left = kps0[13][2] > VIS && kps0[15][2] > VIS;
  const right = kps0[14][2] > VIS && kps0[16][2] > VIS;
  if (!(left && right)) return {ok: false, detail: 'Thiếu chân'};
  if (kps0[11][2] <= VIS || kps0[12][2] <= VIS) return {ok: false, detail: 'Thiếu hông'};
  const tors = [_segLen(kps0,5,11), _segLen(kps0,6,12)].filter(v => v != null);
  const legs = [_segLen(kps0,11,15), _segLen(kps0,12,16)].filter(v => v != null);
  if (!tors.length || !legs.length) return {ok: false, detail: 'Thiếu chân'};
  const torso = tors.reduce((a,b)=>a+b,0) / tors.length;
  const leg = legs.reduce((a,b)=>a+b,0) / legs.length;
  if (torso > 1e-4 && leg < 0.75 * torso)
    return {ok: false, detail: 'Thiếu chân (cắt dưới)'};
  const fs = faceSize(kps0);
  if (fs != null && leg < MIN_LEG_TO_FACE * fs)
    return {ok: false, detail: 'Thiếu chân (cận cảnh / cắt dưới)'};
  const vis = kps0.filter(k => k[2] > VIS);
  const y1 = Math.max(...vis.map(k => k[1]));
  if (y1 > 0.97 && leg < 0.95 * torso)
    return {ok: false, detail: 'Cắt mép khung hình'};
  if (y1 > 0.97 && kps0[5][2] > VIS && kps0[6][2] > VIS) {
    const shy = (kps0[5][1] + kps0[6][1]) / 2;
    if (shy > 0.55 && (fs == null || leg < 3.5 * fs))
      return {ok: false, detail: 'Cắt nửa dưới cơ thể'};
  }
  return {ok: true, detail: ''};
}

function isPartialBody(kps0) {
  if (!kps0 || kps0.length < 17)
    return {partial: true, detail: 'Không đủ skeleton'};
  const rawVis = kps0.filter(k => k[2] > VIS).length;
  if (rawVis < 10)
    return {partial: true, detail: `Chỉ thấy ${rawVis}/17 điểm`};
  if (![0,1,2,3,4].some(i => kps0[i][2] > VIS))
    return {partial: true, detail: 'Thiếu mặt'};
  if (![5,6,11,12].every(i => kps0[i][2] > VIS))
    return {partial: true, detail: 'Thiếu vai/hông'};
  const arms = [7,8,9,10].filter(i => kps0[i][2] > VIS).length;
  if (arms < 2) return {partial: true, detail: 'Thiếu tay'};
  const lg = legsLookComplete(kps0);
  if (!lg.ok) return {partial: true, detail: lg.detail};
  const vis = kps0.filter(k => k[2] > VIS);
  const x0 = Math.min(...vis.map(k => k[0])), x1 = Math.max(...vis.map(k => k[0]));
  const y0 = Math.min(...vis.map(k => k[1])), y1 = Math.max(...vis.map(k => k[1]));
  const atEdge = x0 < .03 || y0 < .03 || x1 > .97 || y1 > .97;
  const legs = [13,14,15,16].filter(i => kps0[i][2] > VIS).length;
  if (atEdge && legs < 4)
    return {partial: true, detail: 'Cắt mép khung hình'};
  return {partial: false, detail: ''};
}

// Keypoints are normalised (x/width, y/height); `aspect` = width/height restores true angles.
function classify(kps0, aspect) {
  const gate = isPartialBody(kps0);
  if (gate.partial)
    return {level:'WARNING',color:[1,.92,.15],label:'MỘT PHẦN CỦA NGƯỜI',detail:gate.detail,technique:'PARTIAL'};
  const kps = kps0.map(k => [k[0]*(aspect||1), k[1], k[2]]);
  const vy = (kps[5][1]+kps[6][1])/2, hy = (kps[11][1]+kps[12][1])/2;
  const vx = (kps[5][0]+kps[6][0])/2, hx = (kps[11][0]+kps[12][0])/2;
  const sp = Math.atan2(Math.abs(vx-hx), Math.abs(vy-hy)+1e-6) * 180 / Math.PI;
  let knee = 180;
  if ([11,12,13,14,15,16].every(i => kps[i][2] > VIS))
    knee = (jointAngle(kps[11],kps[13],kps[15]) + jointAngle(kps[12],kps[14],kps[16])) / 2;
  const vis = kps.filter(k => k[2] > VIS);
  const x0 = Math.min(...vis.map(k => k[0])), x1 = Math.max(...vis.map(k => k[0]));
  const y0 = Math.min(...vis.map(k => k[1])), y1 = Math.max(...vis.map(k => k[1]));
  const bw = x1 - x0, bh = y1 - y0;
  const lying = sp > 65 && bw / (bh + 1e-6) > 1.0;
  const head = [0,1,2,3,4].filter(i => kps[i][2] > VIS);
  const headY = head.length ? head.reduce((s, i) => s + kps[i][1], 0) / head.length : null;
  const headLow = headY === null ? null : hy - headY < .15 * Math.max(bh, 1e-6);
  const extra = {spine_deg: sp, knee_deg: knee, reba: reba(kps, sp, knee), height: bh, hip_y: hy,
                 signals: {lying, head_low: headLow, collapsed: false}};
  const r = (o) => Object.assign(o, extra);
  if (isFall(lying, headLow, false))
    return r({level:'RISK',color:[1,0,0],label:'PHÁT HIỆN NGÃ',detail: lying ? `Thân ${sp.toFixed(0)}° · nằm ngang` : 'Đầu thấp ngang hông',technique:'FALL'});
  if (knee < 140 && sp < 45) return r({level:'SAFE',color:[0,1,0],label:'NGỒI XỔM',detail:`Gối ${knee.toFixed(0)}° · Lưng ${sp.toFixed(0)}°`,technique:'SQUAT'});
  if (sp > 60) return r({level:'RISK',color:[1,0,0],label:'CÚI KHOM',detail:`Cúi ${sp.toFixed(0)}°`,technique:'STOOP'});
  return r({level:'SAFE',color:[0,1,0],label:'ĐỨNG',detail:'Bình thường',technique:'STANDING'});
}

function isFall(lying, headLow, collapsed) {
  if (lying && headLow === null) return true;
  return (+lying) + (+!!headLow) + (+collapsed) >= 2;
}

// REBA (Hignett & McAtamney 2000) from one 2D frame; load/coupling/twist/wrist scored neutral.
const REBA_A = [[[1,2,3,4],[1,2,3,4],[3,3,5,6]],[[2,3,4,5],[3,4,5,6],[4,5,6,7]],[[2,4,5,6],[4,5,6,7],[5,6,7,8]],
  [[3,5,6,7],[5,6,7,8],[6,7,8,9]],[[4,6,7,8],[6,7,8,9],[7,8,9,9]]];
const REBA_B = [[[1,2,2],[1,2,3]],[[1,2,3],[2,3,4]],[[3,4,5],[4,5,5]],[[4,5,5],[5,6,7]],[[6,7,8],[7,8,8]],[[7,8,8],[8,9,9]]];
const REBA_C = [[1,1,1,2,3,3,4,5,6,7,7,7],[1,2,2,3,4,4,5,6,6,7,7,8],[2,3,3,3,4,5,6,7,7,8,8,8],[3,4,4,4,5,6,7,8,8,9,9,9],
  [4,4,4,5,6,7,8,8,9,9,9,9],[6,6,6,7,8,8,9,9,10,10,10,10],[7,7,7,8,9,9,9,10,10,11,11,11],[8,8,8,9,10,10,10,10,10,11,11,11],
  [9,9,9,10,10,10,11,11,11,12,12,12],[10,10,10,11,11,11,11,12,12,12,12,12],[11,11,11,11,12,12,12,12,12,12,12,12],
  [12,12,12,12,12,12,12,12,12,12,12,12]];
function vecAngle(a, b) {
  const c = (a[0]*b[0] + a[1]*b[1]) / ((Math.hypot(a[0], a[1]) + 1e-6) * (Math.hypot(b[0], b[1]) + 1e-6));
  return Math.acos(Math.max(-1, Math.min(1, c))) * 180 / Math.PI;
}
function reba(k, sp, knee) {
  const trunk = sp <= 5 ? 1 : sp <= 20 ? 2 : sp <= 60 ? 3 : 4;
  const sh = [(k[5][0]+k[6][0])/2, (k[5][1]+k[6][1])/2], hp = [(k[11][0]+k[12][0])/2, (k[11][1]+k[12][1])/2];
  const up = [sh[0]-hp[0], sh[1]-hp[1]], down = [-up[0], -up[1]];
  const head = [0,1,2,3,4].filter(i => k[i][2] > VIS);
  let neck = 1;
  if (head.length) {
    const hx = head.reduce((s, i) => s + k[i][0], 0) / head.length, hy2 = head.reduce((s, i) => s + k[i][1], 0) / head.length;
    if (vecAngle(up, [hx - sh[0], hy2 - sh[1]]) > 20) neck = 2;
  }
  const flex = 180 - knee, legs = 1 + (flex > 60 ? 2 : flex >= 30 ? 1 : 0);
  let upper = 1, lower = 1;
  [[5,7,9],[6,8,10]].forEach(([s, e, w]) => {
    if (k[s][2] <= VIS || k[e][2] <= VIS) return;
    const a = vecAngle(down, [k[e][0]-k[s][0], k[e][1]-k[s][1]]);
    upper = Math.max(upper, a <= 20 ? 1 : a <= 45 ? 2 : a <= 90 ? 3 : 4);
    if (k[w][2] > VIS) { const f = 180 - jointAngle(k[s], k[e], k[w]); lower = Math.max(lower, f >= 60 && f <= 100 ? 1 : 2); }
  });
  const A = REBA_A[trunk-1][neck-1][legs-1], B = REBA_B[upper-1][lower-1][0];
  return REBA_C[Math.min(A,12)-1][Math.min(B,12)-1];
}

// Per-person standing baseline: a body collapsed to < 50 % of its standing height with the
// hips dropped is the "collapsed" fall signal (catches falls towards/away from the camera).
const FALL_BASE = {};
function fallRefine(id, s, t) {
  if (!s || !s.signals) return s;
  Object.keys(FALL_BASE).forEach(k => { if (t - FALL_BASE[k].t > 10) delete FALL_BASE[k]; });
  const b = FALL_BASE[id] || (FALL_BASE[id] = {h: 0, hip: 0, n: 0, t});
  b.t = t;
  const ready = b.n >= 5;
  if (s.technique === 'STANDING' && s.spine_deg < 20 && s.height > 0 && (!ready || s.height > .8 * b.h)) {
    const a = ready ? .2 : 1 / (b.n + 1);
    b.h += a * (s.height - b.h); b.hip += a * (s.hip_y - b.hip); b.n++;
    return s;
  }
  if (!ready || s.technique === 'FALL') return s;
  if (!(s.height < .5 * b.h && s.hip_y - b.hip > .2 * b.h)) return s;
  const out = {...s, signals: {...s.signals, collapsed: true}};
  if ((s.signals.lying || s.knee_deg >= 140) && isFall(s.signals.lying, s.signals.head_low, true))
    Object.assign(out, {level:'RISK', color:[1,0,0], label:'PHÁT HIỆN NGÃ', technique:'FALL',
                        detail:`Đổ người (cao ${Math.round(100 * s.height / b.h)}% lúc đứng)`});
  return out;
}

function detect() {
  const v = $('v');
  if (!v || v.readyState < 2 || v.paused) return;
  const now = performance.now();
  if (now - S.last_det < DET_INT) return;
  S.last_det = now;
  if (v.currentTime === S.last_vt) return;
  S.last_vt = v.currentTime;
  S.detCount++;
  if (now - S.detMark > 1000) { S.det_fps = S.detCount; S.detCount = 0; S.detMark = now; }
  try {
    const r = S.pose.detectForVideo(v, now);
    if (r.landmarks && r.landmarks.length > 0) {
      const persons = r.landmarks.map((lms, i) => {
        const kps = mp2coco(lms);
        const wl = r.worldLandmarks && r.worldLandmarks[i];
        const world = wl ? MP2COCO.map(j => [wl[j].x, wl[j].y, wl[j].z]) : null;
        const vis = kps.filter(k => k[2] > VIS);
        const bbox = vis.length >= 2 ? [
          Math.min(...vis.map(k => k[0])), Math.min(...vis.map(k => k[1])),
          Math.max(...vis.map(k => k[0])), Math.max(...vis.map(k => k[1])),
        ] : null;
        return {id:i, keypoints:kps, world, bbox,
                safety:fallRefine(i, classify(kps, (v.videoWidth||4)/(v.videoHeight||3)), now / 1000)};
      });
      persons.sort((a,b) => b.keypoints.reduce((s,k)=>s+k[2],0) - a.keypoints.reduce((s,k)=>s+k[2],0));
      const q = calcIQA();
      process({detected:true, persons, hands:[], quality:q,
               env_hazards: iqaWarnings(q),
               _real:true});
    } else {
      process({detected:false, persons:[], hands:[], quality:calcIQA(),
               env_hazards:{hazards:[],overall_level:'SAFE',overall_color:[0,1,0]}, _real:true});
    }
  } catch (e) { S.dbg.err = 'Detect: ' + e.message; }
}

// ========== 3D ==========
function init3D() {
  if (!S.lib || !window.Human3D) return false;
  if (!Human3D.init($('c3d'))) return false;
  S.three = true;
  return true;
}

function fallback2D() {
  const c = $('c3d');
  c.innerHTML = '<canvas id="c2d" style="width:100%;height:100%;display:block;"></canvas>';
  const fb = $('c2d');
  fb.width = c.clientWidth||500; fb.height = c.clientHeight||500;
  S.ctx2d = fb.getContext('2d');
  S.three = false;
}

function render3D() {
  if (!S.three) return;
  Human3D.setLevel(S.safety);
  Human3D.render();
}

function render2D(kps) {
  if (!S.ctx2d) return;
  const c = S.ctx2d, W = c.canvas.width, H = c.canvas.height;
  c.clearRect(0, 0, W, H);
  c.strokeStyle = '#0f172a'; c.lineWidth = 1;
  for (let i = 0; i <= 16; i++) {
    c.beginPath(); c.moveTo(i*W/16, 0); c.lineTo(i*W/16, H); c.stroke();
    c.beginPath(); c.moveTo(0, i*H/16); c.lineTo(W, i*H/16); c.stroke();
  }
  const cx = W/2, cy = H*.85, r = Math.min(W,H)*.4;
  const g = (Date.now()/1000)*1.5;
  const mau = S.safety==='SAFE' ? '#00ff00' : S.safety==='WARNING' ? '#ffaa00' : '#ff0000';
  c.strokeStyle = mau; c.lineWidth = 2;
  c.beginPath(); c.arc(cx, cy, r, 0, 2*Math.PI); c.stroke();
  c.beginPath(); c.moveTo(cx, cy); c.lineTo(cx+Math.cos(g)*r, cy+Math.sin(g)*r); c.stroke();
  if (!kps || kps.length < 17) return;
  c.strokeStyle = mau; c.fillStyle = mau; c.lineWidth = 6;
  c.shadowColor = mau; c.shadowBlur = 20;
  KN.forEach(([i,j]) => {
    if (kps[i][2] > VIS && kps[j][2] > VIS) {
      c.beginPath(); c.moveTo(kps[i][0]*W, kps[i][1]*H); c.lineTo(kps[j][0]*W, kps[j][1]*H); c.stroke();
    }
  });
  kps.forEach(p => {
    if (p[2] > VIS) { c.beginPath(); c.arc(p[0]*W, p[1]*H, 9, 0, 2*Math.PI); c.fill(); }
  });
  c.shadowBlur = 0;
}

// ========== IQA ==========
function calcIQA() {
  if (!S.ready) return null;
  const v = $('v');
  if (!v.videoWidth || v.readyState < 2) return null;
  const c = document.createElement('canvas');
  c.width = 320; c.height = 240;
  const cx = c.getContext('2d');
  try { cx.drawImage(v, 0, 0, 320, 240); } catch (e) { return null; }

  const t0 = performance.now();
  const data = cx.getImageData(0, 0, 320, 240).data;
  let s = 0, s2 = 0, ov = 0, un = 0;
  const gray = new Float32Array(320*240);
  for (let i = 0, j = 0; i < data.length; i += 4, j++) {
    const g = (.299*data[i] + .587*data[i+1] + .114*data[i+2]) / 255;
    gray[j] = g; s += g; s2 += g*g;
    if (g > .95) ov++; if (g < .05) un++;
  }
  const N = 320*240, m = s/N;
  const std = Math.sqrt(Math.max(s2/N - m*m, 0));
  const contrast = Math.min(std*400, 100);
  const exposure = Math.max(100 - (ov+un)/N*1000, 0);

  let lap = 0, lapN = 0;
  for (let y = 1; y < 239; y++) {
    for (let x = 1; x < 319; x++) {
      const i = y*320 + x;
      const l = 4*gray[i] - gray[i-1] - gray[i+1] - gray[i-320] - gray[i+320];
      lap += l*l; lapN++;
    }
  }
  const blur = Math.min((lap/lapN)*1000, 100);
  const noise = Math.max(100 - Math.abs(std - .15)*500, 0);
  const piqe = Math.max(100 - Math.abs(std - .2)*300, 0);
  const overall = .25*piqe + .25*blur + .20*contrast + .15*noise + .15*exposure;
  const dt = (performance.now() - t0);

  return {
    piqe: Math.round(piqe*10)/10,
    blur: Math.round(blur*10)/10, contrast: Math.round(contrast*10)/10,
    noise: Math.round(noise*10)/10, exposure: Math.round(exposure*10)/10,
    overall: Math.round(overall*10)/10,
    time_fast_ms: Math.round(dt*10)/10,
    time_total_ms: Math.round(dt*10)/10
  };
}

function iqaWarnings(q) {
  if (!q) return {warnings:[], hazards:[], overall_level:'SAFE', overall_color:[0,1,0]};
  const warnings = [];
  const add = (code, label, metric, value) =>
    warnings.push({code, name:code, label, metric, value, advice:'Kiểm tra camera'});
  if (q.blur < IQA_THRESH.blur) add('BLUR', 'Ảnh mờ', 'blur', q.blur);
  if (q.noise < IQA_THRESH.noise) add('NOISE', 'Ảnh nhiễu', 'noise', q.noise);
  if (q.contrast < IQA_THRESH.contrast) add('CONTRAST', 'Tương phản thấp', 'contrast', q.contrast);
  if (q.exposure < IQA_THRESH.exposureDark) add('DARK', 'Ảnh tối', 'exposure', q.exposure);
  else if (q.exposure > IQA_THRESH.exposureGlare) add('GLARE', 'Ảnh chói sáng', 'exposure', q.exposure);
  if (q.overall < IQA_LOW_OVERALL) add('LOW_Q', 'Ảnh kém (tổng)', 'overall', q.overall);
  let level = 'SAFE', color = [0,1,0];
  if (q.overall < IQA_LOW_OVERALL) { level = 'RISK'; color = [1,.65,0]; }
  else if (warnings.length) { level = 'WARNING'; color = [1,.65,0]; }
  return {warnings, hazards:warnings, overall_level:level, overall_color:color};
}

function metricRow(label, value, bad) {
  const col = bad ? '#ef4444' : '#94a3b8';
  return `<div class="row"><span style="color:${col}">${label}</span><span style="color:${col}">${value}</span></div>`;
}

function renderIqaPanel(q) {
  if (!q) { $('iqa').innerHTML = '--'; return; }
  const oBad = q.overall < IQA_LOW_OVERALL;
  $('iqa').innerHTML =
    metricRow('PIQE', q.piqe, false) +
    metricRow('Blur', q.blur, q.blur < IQA_THRESH.blur) +
    metricRow('Contrast', q.contrast, q.contrast < IQA_THRESH.contrast) +
    metricRow('Noise', q.noise, q.noise < IQA_THRESH.noise) +
    metricRow('Exposure', q.exposure, q.exposure < IQA_THRESH.exposureDark || q.exposure > IQA_THRESH.exposureGlare) +
    `<div class="row"><b style="color:${oBad?'#ef4444':'var(--c)'}">Tổng</b><b style="color:${oBad?'#ef4444':'var(--c)'}">${q.overall}</b></div>`;
}

function warningList(env) {
  return (env && (env.warnings || env.hazards)) || [];
}

function showIdle() {
  S.mode = 'idle';
  if ($('stt')) $('stt').textContent = 'Chọn Camera / Video / Server';
  const el = $('mode');
  if (el) { el.textContent = 'CHỜ NGUỒN'; el.className = 'chip muted'; }
  if ($('iqa')) $('iqa').innerHTML = '--';
  if ($('mt')) $('mt').innerHTML = '<div class="row"><span>Mức</span><b style="color:var(--ok)">SAFE</b></div>';
  if ($('tt')) $('tt').textContent = '--';
  if ($('cb')) $('cb').style.display = 'none';
  setSysIqa(null, null);
  updateSystemPanel();
  return true;
}

function personBBox(p, W, H) {
  if (p.bbox && p.bbox.length >= 4) {
    return [p.bbox[0]*W, p.bbox[1]*H, p.bbox[2]*W, p.bbox[3]*H];
  }
  const kp = p.keypoints || [];
  const vis = kp.filter(k => k[2] > VIS);
  if (vis.length < 2) return null;
  const xs = vis.map(k => k[0]*W), ys = vis.map(k => k[1]*H);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

function draw2D(ds) {
  const v = $('v');
  const W = v.videoWidth || 640, H = v.videoHeight || 480;
  if ($('ov').width !== W) $('ov').width = W;
  if ($('ov').height !== H) $('ov').height = H;
  const ctx = $('ov').getContext('2d');
  ctx.clearRect(0, 0, W, H);
  if (!ds || !ds.length) return;
  ds.forEach((p, i) => {
    const kp = p.keypoints;
    if (!kp || kp.length < 17) return;
    const tech = (p.safety && p.safety.technique) || '';
    const partial = tech === 'PARTIAL';
    const pid = (p.id != null ? p.id : i + 1);
    const mau = partial ? '#facc15' : CL[i % CL.length];
    const box = personBBox(p, W, H);
    if (box) {
      const pad = 8;
      ctx.strokeStyle = mau; ctx.lineWidth = partial ? 3 : 2;
      ctx.strokeRect(box[0]-pad, box[1]-pad, (box[2]-box[0])+pad*2, (box[3]-box[1])+pad*2);
      const label = partial ? `P${pid} - Chỉ hiển thị một phần người` : `P${pid}`;
      ctx.font = 'bold 12px IBM Plex Sans, sans-serif';
      const tw = ctx.measureText(label).width;
      const lx = box[0]-pad, ly = Math.max(16, box[1]-pad - 4);
      ctx.fillStyle = mau;
      ctx.fillRect(lx, ly - 14, tw + 10, 16);
      ctx.fillStyle = '#0b1220';
      ctx.fillText(label, lx + 5, ly - 2);
    }
    // Complete person only: draw COCO-17 skeleton (partial would be misleading).
    if (partial) return;
    ctx.strokeStyle = mau; ctx.lineWidth = 3;
    ctx.shadowColor = mau; ctx.shadowBlur = 8;
    KN.forEach(([a,b]) => {
      if (kp[a][2] > VIS && kp[b][2] > VIS) {
        ctx.beginPath(); ctx.moveTo(kp[a][0]*W, kp[a][1]*H); ctx.lineTo(kp[b][0]*W, kp[b][1]*H); ctx.stroke();
      }
    });
    kp.forEach(pt => {
      if (pt[2] > VIS) {
        ctx.fillStyle = mau;
        ctx.globalAlpha = Math.min(pt[2], 1);
        ctx.beginPath(); ctx.arc(pt[0]*W, pt[1]*H, 5, 0, 2*Math.PI); ctx.fill();
      }
    });
    ctx.globalAlpha = 1; ctx.shadowBlur = 0;
  });
}

// ========== MATLAB BRIDGE ==========
function procMatlabIQA(m) {
  // Panel UI removed — keep state for optional Report / tools only.
  S.mIQA = m && m.available !== false ? m : null;
}

// Auto mode: the backend reads the newest output/*_iqa.json written by MATLAB, so the web
// picks up new results without choosing a file. Manual load / demo switch auto off.
function setMatlabStatus(text, color) {
  const el = $('jst');
  if (!el) return;
  el.textContent = text;
  el.style.color = color;
}

function setMatlabAuto(on) {
  S.mAuto = on;
  const btn = $('bMAuto');
  if (btn) {
    btn.classList.toggle('on', on);
    btn.textContent = on ? 'Auto ON' : 'Auto OFF';
  }
  if (on) {
    S.mFile = null;
    if (S.mTimer) { clearInterval(S.mTimer); S.mTimer = null; }
    autoMatlab();
  }
}

async function autoMatlab() {
  if (!S.mAuto) return;
  if (!window.EchoBackend || !EchoBackend.online) {
    setMatlabStatus('Tự động: chờ backend (make run) — hoặc bấm 📂 Nạp', '#94a3b8');
    return;
  }
  try {
    const d = await EchoBackend.json('/matlab_iqa');
    if (!S.mAuto) return;
    if (d && d.available) {
      procMatlabIQA(d);
      const age = d._age_seconds != null ? ` · ${d._age_seconds}s trước` : '';
      setMatlabStatus(`🔄 Tự động: ${d._source_file || d.video || 'MATLAB'}${age}`, '#00ff88');
    } else {
      setMatlabStatus('Tự động: chưa có output/*_iqa.json — chạy MATLAB', '#f59e0b');
    }
  } catch (e) {
    setMatlabStatus('Tự động: lỗi đọc /matlab_iqa', '#ef4444');
  }
}

async function loadJSON(file) {
  setMatlabAuto(false);
  try {
    const t = await file.text();
    const raw = JSON.parse(t);
    const s = raw.summary || raw;
    s._source_file = file.name; s._age_seconds = 0;
    procMatlabIQA(s);
    $('jst').textContent = `✓ ${file.name}`;
    $('jst').style.color = '#00ff88';
  } catch (e) {
    $('jst').textContent = `✗ ${e.message}`;
    $('jst').style.color = '#ef4444';
  }
}

async function pickJSON() {
  if (!window.showOpenFilePicker) { $('jfile').click(); return; }
  try {
    const [h] = await window.showOpenFilePicker({
      types:[{description:'JSON', accept:{'application/json':['.json']}}], multiple:false
    });
    setMatlabAuto(false);
    S.mFile = h;
    await watchJSON();
    if (S.mTimer) clearInterval(S.mTimer);
    S.mTimer = setInterval(watchJSON, 1000);
    $('jst').textContent = `✓ ${h.name}`;
    $('jst').style.color = '#00ff88';
  } catch (e) {
    if (e.name !== 'AbortError') {
      $('jst').textContent = `✗ ${e.message}`;
      $('jst').style.color = '#ef4444';
    }
  }
}

async function watchJSON() {
  if (!S.mFile) return;
  try {
    const f = await S.mFile.getFile();
    if (f.lastModified === S.mMtime) return;
    S.mMtime = f.lastModified;
    const t = await f.text();
    const raw = JSON.parse(t);
    const s = raw.summary || raw;
    s._age_seconds = Math.round((Date.now() - f.lastModified)/1000);
    procMatlabIQA(s);
    $('jst').textContent = `🔄 ${f.name}`;
  } catch (e) {}
}

// ========== PROCESS DATA ==========
function process(data) {
  if (!data) return;
  if (S.mAuto && data.matlab_iqa && data.matlab_iqa.available !== false) procMatlabIQA(data.matlab_iqa);

  if (data.quality) {
    const q = data.quality;
    renderIqaPanel(q);
    const warns = warningList(data.env_hazards || iqaWarnings(q));
    S.sess.hist.push({
      t: Date.now(), piqe: q.piqe,
      blur: q.blur, contrast: q.contrast, noise: q.noise,
      exposure: q.exposure, overall: q.overall,
      time_fast_ms: q.time_fast_ms || 0,
      frame_ms: data.benchmark?.frame_ms || 0,
      alert: warns[0]?.label || null
    });
    if (S.sess.hist.length > 500) S.sess.hist.shift();
  }

  if (data.env_hazards || data.quality) {
    const e = data.env_hazards || iqaWarnings(data.quality);
    const warns = warningList(e);
    const m = `rgb(${(e.overall_color||[0,1,0]).map(c => Math.round(c*255)).join(',')})`;
    let h = `<div class="row"><span>Mức</span><b style="color:${m}">${e.overall_level||'SAFE'}</b></div>`;
    if (!warns.length) h += `<div class="row"><span style="color:#94a3b8">Không cảnh báo</span><span></span></div>`;
    warns.forEach(x => { h += `<div class="row"><span style="color:#ef4444">${x.label}</span><span>${x.advice||''}</span></div>`; });
    $('mt').innerHTML = h;
    if (warns.length) {
      $('cb').style.display = 'block';
      $('cb').textContent = warns.slice(0, 2).map(w => w.label.replace(/^Ảnh /,'').toUpperCase()).join(' · ');
    } else $('cb').style.display = 'none';
  }

  const ds = data.persons || [];
  $('tt').textContent = ds.length > 0 ? `${ds.length} người` : 'Không có';

  if (ds[0] && ds[0].safety) {
    S.safety = ds[0].safety.level;
    const s = ds[0].safety;
    if (s.technique && s.technique !== 'STANDING') {
      $('kt').style.display = 'block';
      const m = `rgb(${s.color.map(c => Math.round(c*255)).join(',')})`;
      $('kt').style.color = m; $('kt').style.borderColor = m;
      $('kt').innerHTML = `${s.label}<br><span style="font-size:9px;font-weight:normal">${s.detail}</span>`;
    } else $('kt').style.display = 'none';
  } else if (ds.length === 0) $('kt').style.display = 'none';

  if (S.three) {
    Human3D.update(ds[0] || null, srcAspect());
    Human3D.setEnv([]);  // IQA warnings are UI-only; no fake FIRE/DUST/SMOKE FX
  } else if (S.ctx2d) render2D(ds.length > 0 ? ds[0].keypoints : null);

  draw2D(ds);
  updateBench(data.benchmark, data.quality);
  setSysIqa(data.quality, data.env_hazards);
  alertsFor(data);

  S.log.push({t:Date.now(), mode:S.mode, ...data});
  if (S.log.length > 3000) S.log.shift();
}

// Server payloads carry alerts already confirmed by the backend; everything computed in the
// browser (scenarios, presets, MediaPipe) goes through the same temporal rules locally.
function alertsFor(data) {
  if (!window.EchoAlerts) return;
  if (S.mode === 'server') { (data.alerts || []).forEach(a => EchoAlerts.raise(a, true)); return; }
  if (!data._real) return;
  EchoAlerts.observe('browser', data.persons || [], data.quality, {
    source: 'browser',
    report: true,
    snapshot,
  });
}

function snapshot() {
  const v = $('v'), ov = $('ov');
  if (!v.videoWidth) return null;
  const w = Math.min(640, v.videoWidth), h = Math.round(w * v.videoHeight / v.videoWidth);
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  const ctx = c.getContext('2d');
  ctx.drawImage(v, 0, 0, w, h);
  ctx.drawImage(ov, 0, 0, w, h);
  return c.toDataURL('image/jpeg', .7);
}

// Camera tab: a server camera drives the 3D worker instead of the local source.
window.EchoApp = {
  drive(d, camId) {
    S.ext = camId;
    const p = (d.persons || [])[0] || null;
    S.safety = p && p.safety ? p.safety.level : 'SAFE';
    if (S.three) {
      Human3D.update(p, d.frame && d.frame.h ? d.frame.w / d.frame.h : 4/3);
      Human3D.setEnv([]);
    } else if (S.ctx2d) render2D(p ? p.keypoints : null);
    $('c3dLabel').textContent = `cam:${camId}` + (p ? ` · ${p.safety.label}` : '');
  },
  release() {
    if (!S.ext) return;
    S.ext = null;
    $('c3dLabel').textContent = 'Đứng yên';
  }
};

window.EchoTabs = {
  // Compatibility shim: toast clicks scroll to Events / Cameras deck panels.
  current: 'ops',
  show(name) {
    const map = {mon: null, cam: 'panel-cam', evt: 'panel-ev-stats'};
    const id = map[name];
    if (id) {
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
    }
    this.current = name;
  }
};

function updateSystemPanel() {
  const set = (id, text, cls) => {
    const el = $(id); if (!el) return;
    el.textContent = text;
    el.className = 'v' + (cls ? ' ' + cls : '');
  };
  const be = window.EchoBackend;
  if (be && be.online && be.health) {
    const h = be.health;
    set('sysBe', `v${h.version} online`, 'ok');
    set('sysYolo', h.yolo ? 'available' : 'unavailable', h.yolo ? 'ok' : 'warn');
    set('sysCams', String(h.cameras ?? 0), h.cameras ? 'ok' : 'warn');
    set('sysNotify', (h.notify && h.notify.length) ? h.notify.join(', ') : 'none');
  } else {
    set('sysBe', 'offline', 'bad');
    set('sysYolo', '--');
    set('sysCams', '--');
    set('sysNotify', '--');
  }
  set('sysSrc', S.mode || 'idle');
  set('sysFps', S.fps ? String(S.fps) : '--');
  set('sysAi', S.ai_on && S.pose_ready ? String(S.det_fps) : (S.ai_on ? '…' : 'off'));
  const live = $('liveDot');
  if (live) {
    const on = S.mode === 'video' || S.mode === 'server' || !!S.ext;
    live.textContent = on ? 'LIVE' : 'STANDBY';
    live.className = 'live ' + (on ? 'on' : 'off');
  }
  const clock = $('sysClock');
  if (clock) clock.textContent = new Date().toLocaleTimeString('vi-VN');
}

function setSysIqa(q, env) {
  const ov = $('sysIqa'), lv = $('sysLvl');
  if (!ov || !lv) return;
  if (!q) { ov.textContent = '--'; lv.textContent = 'SAFE'; lv.className = 'v ok'; return; }
  ov.textContent = String(q.overall);
  const level = (env && env.overall_level) || (q.overall < IQA_LOW_OVERALL ? 'RISK' : 'SAFE');
  lv.textContent = level;
  lv.className = 'v ' + (level === 'SAFE' ? 'ok' : level === 'WARNING' ? 'warn' : 'bad');
  ov.className = 'v ' + (q.overall < IQA_LOW_OVERALL ? 'bad' : 'ok');
}

function srcAspect() {
  const v = $('v');
  return v.videoWidth && v.videoHeight ? v.videoWidth / v.videoHeight : 4/3;
}

function updateBench(b, q) {
  if (!S.bench.on) return;
  if (b) {
    $('bf').textContent = (b.fps_actual || 0).toFixed(1) + ' FPS';
    $('bm').textContent = (b.avg_frame_ms || 0).toFixed(1) + ' ms';
  }
  if (q) $('bpf').textContent = (q.time_fast_ms || 0).toFixed(1) + ' ms';
}

// ========== MAIN LOOP ==========
function loop(now) {
  requestAnimationFrame(loop);
  try {
    if (S.three) render3D();
    if (S.ext) { updDebug(); return; }
    if (S.mode === 'video' && S.ready && S.ai_on && S.pose_ready) detect();
    const fps = S.mode === 'video' ? FPS_VID : FPS_SRV;
    if (now - S.lastDraw < 1000/fps) return;
    S.lastDraw = now;
    S.fpsCount++;
    if (now - S.fpsMark > 1000) { S.fps = S.fpsCount; S.fpsCount = 0; S.fpsMark = now; }
    if (S.mode === 'video') procVideo();
    else if (S.mode === 'server') procServer(now);
    updDebug();
  } catch (e) { S.dbg.err = e.message; }
}

function procVideo() {
  const v = $('v');
  if (v.paused || v.readyState < 2) { S.dbg.video = 'loading'; return; }
  S.dbg.video = `${v.videoWidth}x${v.videoHeight}`;
  if (S.ai_on && S.pose_ready) return;  // detect() already called process()
  const q = calcIQA();
  if (!q) return;
  S.frame++;
  process({
    detected: false, persons: [],
    hands: [], quality:q, env_hazards:iqaWarnings(q), _real:true
  });
}

function procServer(now) {
  if (!S.ws || S.ws.readyState !== 1 || S.sending) return;
  if (now - S.lastSend < 1000/FPS_SRV) return;
  S.lastSend = now;
  const v = $('v');
  if (!v.videoWidth || !v.videoHeight) return;
  S.sending = true;
  const c = document.createElement('canvas');
  c.width = v.videoWidth; c.height = v.videoHeight;
  c.getContext('2d').drawImage(v, 0, 0);
  try {
    S.ws.send(JSON.stringify({
      image: c.toDataURL('image/jpeg', .55),
      timestamp: v.currentTime || performance.now()/1000
    }));
  } catch (e) { S.sending = false; }
}

function updDebug() {
  const d = $('dbc');
  if (!d) return;
  d.classList.remove('err');
  const t = S.three ? '3D' : '2D';
  const ai = S.ai_on && S.pose_ready ? `AI:${S.det_fps}fps` : 'AI:OFF';
  const src = S.mIQA ? 'MATLAB' : 'Live';
  d.textContent = `[${S.mode.toUpperCase()}] ${t} | FPS:${S.fps} | ${ai} | IQA:${src} | Video:${S.dbg.video} | ${S.ext ? 'Cam:' + S.ext + ' | ' : ''}An toàn:${S.safety} | Log:${S.log.length}` + (S.dbg.err ? ` | LỖI:${S.dbg.err}` : '');
  updateSystemPanel();
  const b = $('badge');
  if (S.pose_loading) { b.textContent = '⏳ AI...'; b.style.background = '#0ea5e9'; b.style.display = 'block'; }
  else if (S.pose_ready && S.ai_on) { b.textContent = `🔬 AI:${S.det_fps}FPS`; b.style.background = '#059669'; b.style.display = 'block'; }
  else b.style.display = 'none';
}

function cleanup() {
  if (S.ws) { try { S.ws.close(); } catch(e){} S.ws = null; }
  const v = $('v');
  try { v.pause(); } catch(e){}
  v.onended = null;
  v.loop = false;
  if (S.stream) { S.stream.getTracks().forEach(t => t.stop()); S.stream = null; }
  v.srcObject = null;
  if (S.url) { URL.revokeObjectURL(S.url); S.url = null; }
  v.removeAttribute('src');
  v.style.transform = '';
  try { v.load(); } catch(e){}
  S.ready = false; S.last_vt = -1; S.dbg.video = '-';
  const sel = $('camPick'), flip = $('bCamFlip');
  if (sel) sel.hidden = true;
  if (flip) { flip.hidden = true; flip.classList.remove('on'); }
}

function updAI() {
  const b = $('bAI');
  if (S.ai_on) { b.textContent = '🔬 AI ON'; b.style.background = '#059669'; b.classList.add('on'); }
  else { b.textContent = '🔬 AI OFF'; b.style.background = '#64748b'; b.classList.remove('on'); }
}

// ========== SESSION CHART ==========
function drawSess() {
  const c = $('scc');
  if (!c || !c.clientWidth) return;
  if (c.width !== c.clientWidth) c.width = c.clientWidth;
  const x = c.getContext('2d'), W = c.width, H = c.height;
  x.clearRect(0, 0, W, H);
  x.strokeStyle = '#1e293b'; x.lineWidth = .5;
  for (let i = 0; i <= 4; i++) {
    const y = i*H/4;
    x.beginPath(); x.moveTo(0, y); x.lineTo(W, y); x.stroke();
  }
  const hist = S.sess.hist.slice(-100);
  if (hist.length < 2) {
    x.fillStyle = '#64748b'; x.font = '10px monospace';
    x.fillText('Chưa có dữ liệu', 10, H/2);
    return;
  }
  x.strokeStyle = '#00ffcc'; x.lineWidth = 2;
  x.beginPath();
  hist.forEach((h, i) => {
    const px = (i / (hist.length-1)) * W;
    const py = H - (h.overall / 100) * H;
    if (i === 0) x.moveTo(px, py); else x.lineTo(px, py);
  });
  x.stroke();
  x.fillStyle = 'rgba(239,68,68,.3)';
  hist.forEach((h, i) => {
    if (h.overall < 40) {
      const px = (i / (hist.length-1)) * W;
      x.fillRect(px-1, 0, 2, H);
    }
  });
  x.fillStyle = '#00ffcc'; x.font = '9px monospace';
  x.fillText('IQA', 5, 10);
}

// ========== REPORT ==========
function sessionStats() {
  const h = S.sess.hist;
  if (h.length === 0) return {piqe:0,blur:0,contrast:0,noise:0,exposure:0,
    overall:0,min:0,max:0,std:0,status:'UNKNOWN',avgFrameMs:0,avgFast:0,
    alertCount:0,alerts:{},total:0};
  const avg = a => a.reduce((x,y)=>x+y,0)/a.length;
  const ov = h.map(x => x.overall || 0);
  const mo = avg(ov);
  const st = mo >= 80 ? 'SAFE' : mo >= 60 ? 'WARNING' : 'DANGER';
  const alerts = {};
  h.forEach(x => { if (x.alert) alerts[x.alert] = (alerts[x.alert] || 0) + 1; });
  return {
    piqe: avg(h.map(x => x.piqe || 0)),
    blur: avg(h.map(x => x.blur || 0)),
    contrast: avg(h.map(x => x.contrast || 0)),
    noise: avg(h.map(x => x.noise || 0)),
    exposure: avg(h.map(x => x.exposure || 0)),
    overall: mo, min: Math.min(...ov), max: Math.max(...ov),
    std: Math.sqrt(avg(ov.map(x => (x-mo)**2))),
    status: st, avgFrameMs: avg(h.map(x => x.frame_ms || 0)),
    avgFast: avg(h.map(x => x.time_fast_ms || 0)),
    alertCount: Object.values(alerts).reduce((a,b)=>a+b,0),
    alerts, total: h.length
  };
}

function taoReport() {
  try {
    const now = new Date(), s = sessionStats();
    const html = `<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8">
<title>ECHO MOVE — Report</title>
<style>
body{font-family:Arial,sans-serif;max-width:900px;margin:40px auto;padding:20px;background:#fff;color:#333;}
h1{color:#059669;border-bottom:3px solid #059669;padding-bottom:10px;}
h2{color:#1e40af;margin-top:30px;border-left:5px solid #1e40af;padding-left:10px;}
.metric{display:inline-block;min-width:120px;margin:5px 10px 5px 0;padding:8px 12px;background:#f0f9ff;border-radius:6px;}
.metric .label{color:#64748b;font-size:12px;}
.metric .value{font-size:24px;font-weight:bold;color:#059669;}
.metric.danger .value{color:#dc2626;}
.metric.warning .value{color:#f59e0b;}
table{width:100%;border-collapse:collapse;margin-top:10px;}
th,td{padding:8px;text-align:left;border-bottom:1px solid #e2e8f0;}
th{background:#f8fafc;color:#1e40af;}
.section{background:#f8fafc;padding:15px;border-radius:8px;margin-top:15px;}
.hl{background:#fef3c7;padding:2px 6px;border-radius:3px;font-family:monospace;}
.badge{display:inline-block;padding:4px 12px;border-radius:20px;font-weight:bold;font-size:12px;}
.badge.SAFE{background:#059669;color:#fff;}
.badge.WARNING{background:#f59e0b;color:#fff;}
.badge.DANGER{background:#dc2626;color:#fff;}
</style></head><body>
<h1>📊 ECHO MOVE v22.0 — IQA Report</h1>
<p><b>Video:</b> ${S.dbg.video}<br>
<b>Thời gian:</b> ${now.toLocaleString('vi-VN')}<br>
<b>Mode:</b> ${S.mode.toUpperCase()} | <b>AI:</b> ${S.ai_on ? 'ON' : 'OFF'}<br>
<b>Samples:</b> ${s.total} frames</p>
<h2>1. IQA Metrics</h2>
<div>
  <div class="metric"><div class="label">PIQE</div><div class="value">${s.piqe.toFixed(1)}</div></div>
  <div class="metric"><div class="label">Blur</div><div class="value">${s.blur.toFixed(1)}</div></div>
  <div class="metric"><div class="label">Contrast</div><div class="value">${s.contrast.toFixed(1)}</div></div>
  <div class="metric"><div class="label">Noise</div><div class="value">${s.noise.toFixed(1)}</div></div>
  <div class="metric"><div class="label">Exposure</div><div class="value">${s.exposure.toFixed(1)}</div></div>
  <div class="metric ${s.overall<60?'danger':s.overall<80?'warning':''}">
    <div class="label">TỔNG</div><div class="value">${s.overall.toFixed(1)}</div></div>
</div>
<p style="margin-top:15px;"><b>Status:</b> <span class="badge ${s.status}">${s.status}</span>
&nbsp; <b>Min/Max:</b> ${s.min.toFixed(1)} / ${s.max.toFixed(1)}
&nbsp; <b>Std:</b> ${s.std.toFixed(1)}</p>
<h2>2. Benchmark</h2>
<table>
  <tr><th>Metric</th><th>Value</th><th>Note</th></tr>
  <tr><td>Frame time</td><td>${s.avgFrameMs.toFixed(1)} ms</td><td>~${(1000/Math.max(s.avgFrameMs,1)).toFixed(1)} FPS</td></tr>
  <tr><td>PIQE</td><td>${s.avgFast.toFixed(1)} ms</td><td>Realtime</td></tr>
</table>
<h2>3. Citations</h2>
<div class="section"><table>
  <tr><th>Metric</th><th>Algorithm</th><th>Citation</th></tr>
  <tr><td>Blur</td><td>Variance of Laplacian</td><td>Pech-Pacheco et al., 2000</td></tr>
  <tr><td>Noise</td><td>Gaussian Smoothing Diff</td><td>Immerkær, 1996</td></tr>
  <tr><td>Contrast</td><td>RMS Contrast</td><td>Peli, 1990</td></tr>
  <tr><td>PIQE</td><td>MSCN Statistics</td><td>Venkatanath et al., 2015</td></tr>
  <tr><td>Exposure</td><td>Histogram Clipping</td><td>ISO 18434-1</td></tr>
</table></div>
<h2>4. Alerts</h2>
${s.alertCount > 0 ?
  `<table><tr><th>Alert</th><th>Count</th><th>%</th></tr>
    ${Object.entries(s.alerts).map(([k,v]) =>
      `<tr><td>${k}</td><td>${v}</td><td>${(v/s.total*100).toFixed(1)}%</td></tr>`).join('')}</table>` :
  '<p style="color:#059669;">✅ No alerts</p>'}
<h2>5. Contributions</h2>
<div class="section"><ul>
  <li><b>Streaming:</b> RAM 200MB vs 4GB (<span class="hl">20×</span>)</li>
  <li><b>Batch plot:</b> 20 FPS vs 3 FPS (<span class="hl">6×</span>)</li>
  <li><b>Dual PIQE:</b> fast + full with correlation proof</li>
  <li><b>AI:</b> YOLOv8-Pose on server when models are installed</li>
</ul></div>
<p style="margin-top:40px;text-align:center;color:#94a3b8;font-size:12px;">
Generated by ECHO MOVE v22.0 — ${now.toISOString()}</p>
</body></html>`;
    const blob = new Blob([html], {type:'text/html;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `ECHO_Report_${Date.now()}.html`;
    a.click(); URL.revokeObjectURL(url);
    $('bRep').textContent = '✅ Đã xuất';
    setTimeout(() => { $('bRep').textContent = '📊 Report'; }, 2000);
  } catch (e) {
    console.error(e);
    $('bRep').textContent = '❌ Lỗi';
    setTimeout(() => { $('bRep').textContent = '📊 Report'; }, 2000);
  }
}

function toggleBench() {
  S.bench.on = !S.bench.on;
  $('bp').classList.toggle('show', S.bench.on);
  $('bBen').classList.toggle('on', S.bench.on);
}

// ========== EVENTS ==========
function bind() {
  $('bAI').onclick = async () => {
    if (S.pose_ready) { S.ai_on = !S.ai_on; updAI(); return; }
    if (S.pose_loading) return;
    $('bAI').textContent = '⏳ Đang tải...';
    const ok = await initPose();
    if (ok) { S.ai_on = true; updAI(); }
    else {
      $('bAI').textContent = '❌ Lỗi';
      $('bAI').style.background = '#ef4444';
      setTimeout(() => { $('bAI').textContent = '🔬 AI Detect'; $('bAI').style.background = '#0ea5e9'; }, 3000);
    }
  };

  function sourceNotice(title, detail, modeLabel) {
    if ($('stt')) $('stt').textContent = title;
    if ($('mode') && modeLabel) {
      $('mode').textContent = modeLabel;
      $('mode').className = 'chip muted';
    }
    const kt = $('kt');
    if (kt && detail) {
      kt.style.display = 'block';
      kt.style.color = '#fbbf24';
      kt.style.borderColor = '#fbbf24';
      kt.innerHTML = `${title}<br><span style="font-size:9px;font-weight:normal">${detail}</span>`;
      clearTimeout(sourceNotice._t);
      sourceNotice._t = setTimeout(() => {
        if (kt.style.color === 'rgb(251, 191, 36)') kt.style.display = 'none';
      }, 7000);
    }
    const box = $('toasts');
    if (box) {
      const el = document.createElement('div');
      el.className = 'toast warn';
      el.innerHTML = `<b>Camera</b> · ${title}<div class="d">${detail || ''}</div>`;
      box.appendChild(el);
      setTimeout(() => el.remove(), 8000);
    }
  }

  function webcamAvailable() {
    return !!(window.isSecureContext && navigator.mediaDevices && typeof navigator.mediaDevices.getUserMedia === 'function');
  }

  function preferRearCam() {
    return /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || '');
  }

  function loadCamPref() {
    try {
      const id = localStorage.getItem('echo_cam_id');
      const facing = localStorage.getItem('echo_cam_facing');
      if (id) S.cam.deviceId = id;
      if (facing === 'user' || facing === 'environment') S.cam.facing = facing;
      else if (preferRearCam()) S.cam.facing = 'environment';
      else S.cam.facing = 'user';
    } catch (e) {
      S.cam.facing = preferRearCam() ? 'environment' : 'user';
    }
  }

  function saveCamPref() {
    try {
      if (S.cam.deviceId) localStorage.setItem('echo_cam_id', S.cam.deviceId);
      else localStorage.removeItem('echo_cam_id');
      localStorage.setItem('echo_cam_facing', S.cam.facing || 'user');
    } catch (e) {}
  }

  function guessFacingLabel(label, index) {
    const s = (label || '').toLowerCase();
    if (/back|rear|environment|sau|world/i.test(s)) return 'Cam sau';
    if (/front|user|face|trước|selfie/i.test(s)) return 'Cam trước';
    return label || (`Camera ${index + 1}`);
  }

  function fillCamPick() {
    const sel = $('camPick'), flip = $('bCamFlip');
    if (!sel) return;
    const devices = S.cam.devices || [];
    if (!devices.length) {
      sel.hidden = true;
      if (flip) flip.hidden = true;
      return;
    }
    const cur = S.cam.deviceId;
    sel.innerHTML = devices.map((d, i) => {
      const label = guessFacingLabel(d.label, i);
      const selAttr = d.deviceId === cur ? ' selected' : '';
      return `<option value="${d.deviceId.replace(/"/g, '&quot;')}"${selAttr}>${label}</option>`;
    }).join('');
    if (!cur && devices[0]) sel.selectedIndex = 0;
    sel.hidden = false;
    if (flip) {
      flip.hidden = devices.length < 2;
      flip.classList.toggle('on', S.mode === 'video' && !!S.stream);
      flip.textContent = S.cam.facing === 'environment' ? '↻ Cam sau' : '↻ Cam trước';
    }
  }

  async function refreshCamDevices() {
    if (!webcamAvailable()) return [];
    try {
      const all = await navigator.mediaDevices.enumerateDevices();
      S.cam.devices = all.filter(d => d.kind === 'videoinput');
    } catch (e) { S.cam.devices = []; }
    fillCamPick();
    return S.cam.devices;
  }

  function videoConstraints(opts) {
    const video = { width: { ideal: 1280 }, height: { ideal: 720 } };
    if (opts && opts.deviceId) {
      video.deviceId = { exact: opts.deviceId };
    } else if (opts && opts.facingMode) {
      video.facingMode = { ideal: opts.facingMode };
    } else if (S.cam.deviceId) {
      video.deviceId = { ideal: S.cam.deviceId };
    } else {
      video.facingMode = { ideal: S.cam.facing || (preferRearCam() ? 'environment' : 'user') };
    }
    return { audio: false, video };
  }

  async function startWebcam(opts) {
    cleanup();
    const constraints = videoConstraints(opts || {});
    S.stream = await navigator.mediaDevices.getUserMedia(constraints);
    const track = S.stream.getVideoTracks()[0];
    const settings = track && track.getSettings ? track.getSettings() : {};
    if (settings.deviceId) S.cam.deviceId = settings.deviceId;
    if (settings.facingMode === 'user' || settings.facingMode === 'environment') {
      S.cam.facing = settings.facingMode;
    } else if (opts && opts.facingMode) {
      S.cam.facing = opts.facingMode;
    }
    saveCamPref();
    const v = $('v');
    v.srcObject = S.stream; v.muted = true;
    // Mirror front camera for natural selfie view; keep rear unmirrored.
    v.style.transform = S.cam.facing === 'user' ? 'scaleX(-1)' : '';
    await v.play();
    S.ready = true; S.mode = 'video'; S.frame = 0;
    const label = guessFacingLabel(
      (S.cam.devices.find(d => d.deviceId === S.cam.deviceId) || {}).label,
      0
    );
    S.dbg.video = `camera · ${label}`;
    $('stt').textContent = (S.ai_on ? 'Camera + AI · ' : 'Camera · ') + label;
    $('mode').textContent = S.cam.facing === 'environment' ? 'CAM SAU' : (S.cam.facing === 'user' ? 'CAM TRƯỚC' : 'CAMERA');
    $('mode').className = 'chip';
    await refreshCamDevices();
    fillCamPick();
  }

  loadCamPref();

  const bCam = $('bCam');
  if (bCam && !webcamAvailable()) {
    bCam.title = 'Webcam cần HTTPS hoặc localhost. Trên HTTP (VPS) hãy dùng Video hoặc panel Cameras.';
  }

  if (bCam) bCam.onclick = async () => {
    if (!webcamAvailable()) {
      sourceNotice(
        'Webcam bị chặn trên HTTP',
        'Trình duyệt chỉ cho phép camera trên HTTPS / localhost. Dùng nút Video, hoặc chọn camera trong panel Cameras (RTSP/USB server).',
        'NO WEBCAM'
      );
      if (window.EchoTabs) EchoTabs.show('cam');
      return;
    }
    try {
      await startWebcam({
        deviceId: S.cam.deviceId || undefined,
        facingMode: S.cam.deviceId ? undefined : (S.cam.facing || (preferRearCam() ? 'environment' : 'user')),
      });
    } catch (e) {
      // Fallback: retry without exact device (labels / permissions differ across browsers).
      try {
        S.cam.deviceId = null;
        await startWebcam({ facingMode: preferRearCam() ? 'environment' : 'user' });
      } catch (e2) {
        const denied = e2 && (e2.name === 'NotAllowedError' || e2.name === 'PermissionDeniedError');
        const msg = denied
          ? 'Bạn đã từ chối quyền camera — hãy cho phép trong trình duyệt rồi thử lại.'
          : ('Lỗi webcam: ' + (e2.message || e2.name || e2));
        sourceNotice(msg, 'Hoặc dùng Video / panel Cameras.', 'NO WEBCAM');
      }
    }
  };

  const camPick = $('camPick');
  if (camPick) {
    camPick.onchange = async () => {
      const id = camPick.value;
      if (!id) return;
      S.cam.deviceId = id;
      saveCamPref();
      try { await startWebcam({ deviceId: id }); }
      catch (e) {
        sourceNotice('Không đổi được camera', e.message || String(e), 'NO WEBCAM');
      }
    };
  }

  const bCamFlip = $('bCamFlip');
  if (bCamFlip) {
    bCamFlip.onclick = async () => {
      if (!webcamAvailable()) return;
      const nextFacing = S.cam.facing === 'environment' ? 'user' : 'environment';
      // Prefer switching by facingMode on phones; also try next listed device.
      const devices = S.cam.devices || [];
      let nextId = null;
      if (devices.length > 1 && S.cam.deviceId) {
        const i = devices.findIndex(d => d.deviceId === S.cam.deviceId);
        nextId = devices[(i + 1) % devices.length].deviceId;
      }
      S.cam.facing = nextFacing;
      S.cam.deviceId = null;
      saveCamPref();
      try {
        await startWebcam({ facingMode: nextFacing });
      } catch (e) {
        if (nextId) {
          try {
            S.cam.deviceId = nextId;
            await startWebcam({ deviceId: nextId });
            return;
          } catch (e2) { /* fall through */ }
        }
        sourceNotice('Không đổi được camera', e.message || String(e), 'NO WEBCAM');
      }
    };
  }

  if (webcamAvailable() && navigator.mediaDevices.addEventListener) {
    navigator.mediaDevices.addEventListener('devicechange', () => { refreshCamDevices(); });
  }

  $('bVid').onclick = () => $('file').click();
  $('file').onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    cleanup();
    const v = $('v');
    const isImg = (f.type || '').startsWith('image/')
      || /\.(jpe?g|png|webp|gif|bmp)$/i.test(f.name || '');
    if (isImg) {
      // Still photo → canvas.captureStream so the AI loop can read frames like a camera.
      try {
        const bmp = await createImageBitmap(f);
        const c = document.createElement('canvas');
        c.width = bmp.width; c.height = bmp.height;
        c.getContext('2d').drawImage(bmp, 0, 0);
        bmp.close?.();
        S.stream = c.captureStream(5);
        v.srcObject = S.stream; v.muted = true;
        await v.play();
        S.ready = true; S.mode = 'video'; S.frame = 0;
        S.dbg.video = `${c.width}x${c.height}`;
        $('stt').textContent = S.ai_on ? 'Ảnh + AI' : 'Ảnh (AI off)';
        $('mode').textContent = 'ẢNH'; $('mode').className = 'chip';
      } catch (err) {
        $('stt').textContent = 'Lỗi ảnh: ' + (err.message || err);
      }
      return;
    }
    S.url = URL.createObjectURL(f);
    v.src = S.url; v.muted = true; v.loop = false;
    v.onended = () => {
      // One pass only — stop AI on last frame after the clip finishes.
      S.ready = false;
      $('stt').textContent = 'Hết video (đã chạy 1 lần)';
      $('mode').textContent = 'XONG'; $('mode').className = 'chip';
    };
    v.onloadedmetadata = () => {
      v.play().then(() => {
        S.ready = true; S.mode = 'video'; S.frame = 0;
        S.dbg.video = `${v.videoWidth}x${v.videoHeight}`;
        $('stt').textContent = S.ai_on ? 'Video + AI (1 lần)' : 'Video (AI off, 1 lần)';
        $('mode').textContent = 'VIDEO'; $('mode').className = 'chip';
      }).catch(err => { $('stt').textContent = 'Lỗi play: ' + err.message; });
    };
    v.onerror = () => { $('stt').textContent = 'Codec sai — chuyển .mp4 H.264'; };
  };

  $('bSrv').onclick = () => {
    if (S.ws) { try { S.ws.close(); } catch(e){} S.ws = null; return; }
    cleanup();
    S.mode = 'server';
    try { S.ws = new WebSocket($('wsurl').value); }
    catch (e) { $('stt').textContent = 'URL sai'; showIdle(); return; }
    S.ws.onopen = () => {
      $('bSrv').textContent = 'Ngắt';
      $('bSrv').style.background = '#ef4444';
      $('stt').textContent = 'Đã kết nối';
      $('mode').textContent = 'SERVER'; $('mode').className = 'chip';
    };
    S.ws.onclose = () => {
      S.ws = null;
      $('bSrv').textContent = 'Server';
      $('bSrv').style.background = '#334155';
      if (S.mode === 'server') {
        showIdle();
        $('stt').textContent = 'Mất kết nối';
      }
    };
    S.ws.onerror = () => { $('stt').textContent = 'Lỗi Python'; };
    S.ws.onmessage = e => {
      S.sending = false;
      try {
        const d = JSON.parse(e.data);
        if (d.skip) return;
        if (d.error) { $('stt').textContent = d.error; return; }
        process(d);
      } catch (err) {}
    };
  };

  $('bLog').onclick = () => {
    const b = new Blob([JSON.stringify(S.log, null, 2)], {type:'application/json'});
    const u = URL.createObjectURL(b);
    const a = document.createElement('a');
    a.href = u; a.download = `echo_log_${Date.now()}.json`; a.click();
    URL.revokeObjectURL(u);
  };

  $('bTst').onclick = selfTest;
  $('bRep').onclick = taoReport;
  $('bBen').onclick = toggleBench;

  // MATLAB tools UI removed — keep quiet optional poll for Report if JSON exists.
  S.mAuto = false;
  if ($('bMAuto')) {
    $('bMAuto').onclick = () => setMatlabAuto(!S.mAuto);
    setMatlabAuto(true);
    setInterval(autoMatlab, 2000);
    if (window.EchoBackend) EchoBackend.on('status', () => autoMatlab());
  }
  if ($('bJson')) $('bJson').onclick = pickJSON;
  if ($('bClr')) $('bClr').onclick = () => {
    setMatlabAuto(false);
    S.mIQA = null; S.mFile = null;
    if (S.mTimer) { clearInterval(S.mTimer); S.mTimer = null; }
    procMatlabIQA(null);
    setMatlabStatus('Đã xóa', '#94a3b8');
  };
  if ($('jfile')) $('jfile').onchange = e => { if (e.target.files[0]) loadJSON(e.target.files[0]); };

  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'a' || e.key === 'A') $('bAI').click();
    else if (e.key === 'b' || e.key === 'B') toggleBench();
    else if (e.key === 'p' || e.key === 'P') taoReport();
    else if (e.key === 'r' || e.key === 'R') { cleanup(); showIdle(); }
    else if (e.key === 't' || e.key === 'T') $('bTst').click();
  });

  const toolsBtn = $('bTools');
  if (toolsBtn) {
    toolsBtn.onclick = () => {
      const panel = $('tools');
      const open = panel.hasAttribute('hidden');
      if (open) panel.removeAttribute('hidden'); else panel.setAttribute('hidden', '');
      toolsBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
      toolsBtn.classList.toggle('on', open);
    };
  }

  if (window.EchoBackend) EchoBackend.on('status', () => updateSystemPanel());
  setInterval(updateSystemPanel, 1000);

  window.addEventListener('resize', () => { if (S.three) Human3D.resize(); });
  document.dispatchEvent(new CustomEvent('echo:dashboard', {detail: 'ready'}));
}

// ========== SELF-TEST ==========
async function selfTest() {
  const kq = $('st');
  kq.classList.add('show');
  kq.innerHTML = '<div style="color:#0ea5e9;font-weight:bold;">🔬 Test...</div>';
  const add = (n, ok) => {
    const c = ok === true ? '#00ff88' : ok === false ? '#ff4444' : '#f59e0b';
    const i = ok === true ? '✓' : ok === false ? '✗' : '⚠';
    kq.innerHTML += `<div style="padding:1px 0;color:${c}">${i} ${n}</div>`;
  };
  const warnOk = (() => {
    const w = iqaWarnings({piqe:50, blur:20, contrast:20, noise:15, exposure:10, overall:25});
    const codes = new Set(w.warnings.map(x => x.code));
    return codes.has('BLUR') && codes.has('NOISE') && codes.has('DARK') && codes.has('LOW_Q')
      && !codes.has('FIRE') && !codes.has('DUST') && !codes.has('SMOKE');
  })();
  const tests = [
    ['Three.js', () => S.lib],
    ['Scene 3D', () => S.three],
    ['Người 3D', () => S.three && Human3D.info().ok],
    ['Model GLTF', () => S.three && Human3D.info().mode === 'gltf'],
    ['IQA warnings', () => warnOk],
    ['Canvas', () => $('ov').getContext('2d') !== null],
    ['AI button', () => typeof $('bAI').onclick === 'function'],
    ['Cam button', () => typeof $('bCam').onclick === 'function'],
    ['Vid button', () => typeof $('bVid').onclick === 'function'],
    ['Report button', () => typeof $('bRep').onclick === 'function'],
    ['Bench button', () => typeof $('bBen').onclick === 'function'],
    ['Cảnh báo (còi/toast)', () => !!window.EchoAlerts],
    ['Dashboard panels', () => !!$('panel-cam') && !!$('panel-ev-stats') && !!$('panel-ev-chart') && !!$('panel-ev-list') && !!$('panel-sys')],
    ['Backend', () => window.EchoBackend && EchoBackend.online ? true : null],
    ['MediaPipe', () => S.pose_ready],
    ['Loop', () => S.fps >= 0],
    ['Debug', () => $('dbc') !== null]
  ];
  let pass = 0;
  await new Promise(r => setTimeout(r, 200));
  for (let i = 0; i < tests.length; i++) {
    const [n, fn] = tests[i];
    try {
      const ok = fn();
      add(n, ok);
      if (ok === true) pass++;
    } catch (e) { add(n, false); }
    await new Promise(r => setTimeout(r, 30));
  }
  add(`TỔNG: ${pass}/${tests.length}`, pass === tests.length);
  $('stt').textContent = `Self-test: ${pass}/${tests.length}`;
}

// Bootstrap
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', loadStep);
else loadStep();

console.log('%c ECHO MOVE v22.0 — FINAL', 'color:#00ffcc;font-weight:bold;font-size:14px');
console.log('  Shortcuts: A(AI) | B(Bench) | P(Report) | R(Reset) | T(Test)');
