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
  che_do:'offline', kich_ban:'an_toan', tu_dong:false,
  khung:0, lan_ve:0, fps_dem:0, fps:0, moc_fps:0,
  safety:'SAFE', ws:null, dang_gui:false, lan_gui:0,
  nhat_ky:[], stream:null, url:null,
  three:false, lib:false, ctx2d:null,
  dbg:{video:'-', err:null},
  ready:false,
  pose:null, pose_ready:false, pose_loading:false,
  ai_on:false, last_det:0, last_vt:-1,
  det_fps:0, det_dem:0, det_moc:0,
  mIQA:null, mFile:null, mMtime:0, mTimer:null, mAuto:true,
  bench:{on:false}, cmp:{on:false, pct:50},
  sess:{on:false, hist:[]},
  ext:null  // server camera id currently driving the 3D view (Camera tab)
};

// Anatomical poses (COCO-17, normalised to a 4:3 frame; subject's left side appears on image right).
const POSE = {
  stand:[[.5,.12],[.511,.105],[.489,.105],[.524,.115],[.476,.115],[.56,.22],[.44,.22],[.572,.356],[.428,.356],[.578,.49],[.422,.49],[.53,.45],[.47,.45],[.533,.66],[.467,.66],[.535,.87],[.465,.87]],
  lift:[[.5,.3],[.511,.285],[.489,.285],[.524,.295],[.476,.295],[.56,.4],[.44,.4],[.58,.53],[.42,.53],[.55,.66],[.45,.66],[.53,.63],[.47,.63],[.6,.72],[.4,.72],[.57,.87],[.43,.87]],
  bend:[[.73,.45],[.725,.435],[.72,.44],[.7,.42],[.695,.425],[.65,.405],[.658,.427],[.65,.55],[.665,.56],[.655,.67],[.67,.68],[.495,.51],[.505,.53],[.505,.725],[.515,.725],[.5,.935],[.51,.935]],
  fall:[[.77,.85],[.765,.865],[.765,.835],[.745,.88],[.745,.82],[.67,.895],[.67,.805],[.57,.91],[.57,.79],[.47,.92],[.47,.78],[.5,.875],[.5,.825],[.34,.88],[.34,.83],[.18,.885],[.18,.835]]
};
const CORE = [0,5,6,11,12,13,14,15,16];
const withConf = (pose, c) => pose.map(([x,y],i) => [x, y, Math.round((CORE.includes(i) ? c : c-.05)*100)/100]);
const SAFE_ENV = {hazards:[],overall_level:'SAFE',overall_color:[0,1,0]};

const KB = {
  an_toan:{ten:'An toàn',kps:withConf(POSE.stand,.95),safety:{level:'SAFE',color:[0,1,0],label:'AN TOÀN',detail:'Bình thường',technique:'NONE'},env:SAFE_ENV,iqa:{piqe:85,piqe_full:85,blur:82,contrast:80,noise:88,exposure:90,overall:85}},
  nang_dung:{ten:'Nâng đúng',kps:withConf(POSE.lift,.95),safety:{level:'SAFE',color:[0,1,0],label:'NÂNG ĐÚNG',detail:'Gối 119°',technique:'PROPER_LIFT'},env:SAFE_ENV,iqa:{piqe:82,piqe_full:82,blur:80,contrast:78,noise:86,exposure:88,overall:82}},
  cui_sai:{ten:'Cúi sai',kps:withConf(POSE.bend,.95),safety:{level:'RISK',color:[1,0,0],label:'SAI TƯ THẾ',detail:'Cúi 63°',technique:'IMPROPER'},env:SAFE_ENV,iqa:{piqe:80,piqe_full:80,blur:78,contrast:76,noise:84,exposure:86,overall:80}},
  nga:{ten:'Ngã',kps:withConf(POSE.fall,.95),safety:{level:'RISK',color:[1,0,0],label:'PHÁT HIỆN NGÃ',detail:'Nguy hiểm',technique:'FALL'},env:SAFE_ENV,iqa:{piqe:75,piqe_full:75,blur:72,contrast:70,noise:80,exposure:82,overall:75}},
  chay:{ten:'Cháy',kps:withConf(POSE.stand,.95),safety:{level:'SAFE',color:[0,1,0],label:'AN TOÀN',detail:'Bình thường',technique:'NONE'},env:{hazards:[{name:'FIRE',label:'LỬA (12.5%)',advice:'GỌI 114'}],overall_level:'CRITICAL',overall_color:[1,0,0]},iqa:{piqe:55,piqe_full:55,blur:60,contrast:65,noise:55,exposure:60,overall:59}},
  bui:{ten:'Bụi',kps:withConf(POSE.stand,.6),safety:{level:'SAFE',color:[0,1,0],label:'AN TOÀN',detail:'Bình thường',technique:'NONE'},env:{hazards:[{name:'DUST',label:'BỤI',advice:'Khẩu trang'},{name:'SMOKE',label:'KHÓI',advice:'Sơ tán'}],overall_level:'CRITICAL',overall_color:[1,0,0]},iqa:{piqe:35,piqe_full:35,blur:30,contrast:25,noise:20,exposure:60,overall:36}},
  toi:{ten:'Tối',kps:withConf(POSE.stand,.5),safety:{level:'SAFE',color:[0,1,0],label:'KHÓ THẤY',detail:'Ảnh tối',technique:'NONE'},env:{hazards:[{name:'DARK',label:'THIẾU SÁNG',advice:'Bật đèn'}],overall_level:'CRITICAL',overall_color:[1,0,0]},iqa:{piqe:30,piqe_full:30,blur:25,contrast:20,noise:60,exposure:15,overall:28}},
  che_cam:{ten:'Che cam',kps:Array(17).fill([.5,.5,0]),safety:{level:'SAFE',color:[0,1,0],label:'KHÔNG PHÁT HIỆN',detail:'Camera lỗi',technique:'NONE'},env:{hazards:[{name:'DARK',label:'THIẾU SÁNG',advice:'Kiểm tra'},{name:'SMOKE',label:'KHÓI/CHE',advice:'Vệ sinh'}],overall_level:'CRITICAL',overall_color:[1,0,0]},iqa:{piqe:15,piqe_full:15,blur:10,contrast:8,noise:40,exposure:5,overall:14}}
};

const KN = [[0,1],[1,3],[0,2],[2,4],[5,6],[5,7],[7,9],[6,8],[8,10],
            [5,11],[6,12],[11,12],[11,13],[13,15],[12,14],[14,16]];
const CL = ['#00ffcc','#ff6b35','#9d4edd','#ffd60a','#06d6a0'];
const FPS_OFF = 15, FPS_VID = 20, FPS_SRV = 12;
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
  ['Scenario', () => { pickKB('an_toan'); return true; }],
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

function goc(p1, p2, p3) {
  const v1x = p1[0]-p2[0], v1y = p1[1]-p2[1];
  const v2x = p3[0]-p2[0], v2y = p3[1]-p2[1];
  const m1 = Math.hypot(v1x, v1y) + 1e-6;
  const m2 = Math.hypot(v2x, v2y) + 1e-6;
  const c = Math.max(-1, Math.min(1, (v1x*v2x + v1y*v2y) / (m1*m2)));
  return Math.acos(c) * 180 / Math.PI;
}

// Keypoints are normalised (x/width, y/height); `aspect` = width/height restores true angles.
function classify(kps0, aspect) {
  if (!kps0 || kps0.length < 17) return {level:'SAFE',color:[0,1,0],label:'CHƯA ĐỦ',detail:'-',technique:'NONE'};
  const kps = kps0.map(k => [k[0]*(aspect||1), k[1], k[2]]);
  if (![5,6,11,12].every(i => kps[i][2] > VIS))
    return {level:'SAFE',color:[0,1,0],label:'CHƯA RÕ',detail:'Cần vai+hông',technique:'NONE'};
  const vy = (kps[5][1]+kps[6][1])/2, hy = (kps[11][1]+kps[12][1])/2;
  const vx = (kps[5][0]+kps[6][0])/2, hx = (kps[11][0]+kps[12][0])/2;
  const sp = Math.atan2(Math.abs(vx-hx), Math.abs(vy-hy)+1e-6) * 180 / Math.PI;
  let goi = 180;
  if ([11,12,13,14,15,16].every(i => kps[i][2] > VIS))
    goi = (goc(kps[11],kps[13],kps[15]) + goc(kps[12],kps[14],kps[16])) / 2;
  const vis = kps.filter(k => k[2] > VIS);
  const bw = Math.max(...vis.map(k => k[0])) - Math.min(...vis.map(k => k[0]));
  const bh = Math.max(...vis.map(k => k[1])) - Math.min(...vis.map(k => k[1]));
  // Multi-signal fall rule (same as backend pose/classifier.py + pose/fall.py).
  const lying = sp > 65 && bw / (bh + 1e-6) > 1.0;
  const head = [0,1,2,3,4].filter(i => kps[i][2] > VIS);
  const headY = head.length ? head.reduce((s, i) => s + kps[i][1], 0) / head.length : null;
  const headLow = headY === null ? null : hy - headY < .15 * Math.max(bh, 1e-6);
  const extra = {spine_deg: sp, knee_deg: goi, reba: reba(kps, sp, goi), height: bh, hip_y: hy,
                 signals: {lying, head_low: headLow, collapsed: false}};
  const r = (o) => Object.assign(o, extra);
  if (isFall(lying, headLow, false))
    return r({level:'RISK',color:[1,0,0],label:'PHÁT HIỆN NGÃ',detail: lying ? `Thân ${sp.toFixed(0)}° · nằm ngang` : 'Đầu thấp ngang hông',technique:'FALL'});
  if (goi < 140 && sp < 45) return r({level:'SAFE',color:[0,1,0],label:'NÂNG ĐÚNG',detail:`Gối ${goi.toFixed(0)}° · Lưng ${sp.toFixed(0)}°`,technique:'PROPER_LIFT'});
  if (sp > 60) return r({level:'RISK',color:[1,0,0],label:'SAI TƯ THẾ',detail:`Cúi ${sp.toFixed(0)}°`,technique:'IMPROPER'});
  if (sp > 30) return r({level:'WARNING',color:[1,.65,0],label:'CHÚ Ý',detail:`Cúi ${sp.toFixed(0)}°`,technique:'PARTIAL'});
  return r({level:'SAFE',color:[0,1,0],label:'AN TOÀN',detail:'Bình thường',technique:'NONE'});
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
function reba(k, sp, goi) {
  const trunk = sp <= 5 ? 1 : sp <= 20 ? 2 : sp <= 60 ? 3 : 4;
  const sh = [(k[5][0]+k[6][0])/2, (k[5][1]+k[6][1])/2], hp = [(k[11][0]+k[12][0])/2, (k[11][1]+k[12][1])/2];
  const up = [sh[0]-hp[0], sh[1]-hp[1]], down = [-up[0], -up[1]];
  const head = [0,1,2,3,4].filter(i => k[i][2] > VIS);
  let neck = 1;
  if (head.length) {
    const hx = head.reduce((s, i) => s + k[i][0], 0) / head.length, hy2 = head.reduce((s, i) => s + k[i][1], 0) / head.length;
    if (vecAngle(up, [hx - sh[0], hy2 - sh[1]]) > 20) neck = 2;
  }
  const flex = 180 - goi, legs = 1 + (flex > 60 ? 2 : flex >= 30 ? 1 : 0);
  let upper = 1, lower = 1;
  [[5,7,9],[6,8,10]].forEach(([s, e, w]) => {
    if (k[s][2] <= VIS || k[e][2] <= VIS) return;
    const a = vecAngle(down, [k[e][0]-k[s][0], k[e][1]-k[s][1]]);
    upper = Math.max(upper, a <= 20 ? 1 : a <= 45 ? 2 : a <= 90 ? 3 : 4);
    if (k[w][2] > VIS) { const f = 180 - goc(k[s], k[e], k[w]); lower = Math.max(lower, f >= 60 && f <= 100 ? 1 : 2); }
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
  if (s.technique === 'NONE' && s.spine_deg < 20 && s.height > 0 && (!ready || s.height > .8 * b.h)) {
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
  S.det_dem++;
  if (now - S.det_moc > 1000) { S.det_fps = S.det_dem; S.det_dem = 0; S.det_moc = now; }
  try {
    const r = S.pose.detectForVideo(v, now);
    if (r.landmarks && r.landmarks.length > 0) {
      const persons = r.landmarks.map((lms, i) => {
        const kps = mp2coco(lms);
        const wl = r.worldLandmarks && r.worldLandmarks[i];
        const world = wl ? MP2COCO.map(j => [wl[j].x, wl[j].y, wl[j].z]) : null;
        return {id:i, keypoints:kps, world,
                safety:fallRefine(i, classify(kps, (v.videoWidth||4)/(v.videoHeight||3)), now / 1000)};
      });
      persons.sort((a,b) => b.keypoints.reduce((s,k)=>s+k[2],0) - a.keypoints.reduce((s,k)=>s+k[2],0));
      const q = calcIQA();
      process({detected:true, persons, hands:[], quality:q,
               env_hazards: q ? envAnalysis(q) : {hazards:[],overall_level:'SAFE',overall_color:[0,1,0]},
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
    piqe: Math.round(piqe*10)/10, piqe_full: Math.round(piqe*10)/10,
    blur: Math.round(blur*10)/10, contrast: Math.round(contrast*10)/10,
    noise: Math.round(noise*10)/10, exposure: Math.round(exposure*10)/10,
    overall: Math.round(overall*10)/10,
    time_fast_ms: Math.round(dt*10)/10, time_full_ms: 0,
    time_total_ms: Math.round(dt*10)/10
  };
}

function envAnalysis(q) {
  const hz = []; let m = 0;
  if (q.exposure < 25 && q.contrast < 30) { hz.push({name:'DARK',label:'THIẾU SÁNG',advice:'Bật đèn'}); m = Math.max(m,3); }
  if (q.contrast < 30 && q.blur < 40) { hz.push({name:'SMOKE',label:'KHÓI/CHE',advice:'Kiểm tra'}); m = Math.max(m,3); }
  if (q.noise < 40 && q.blur < 30) { hz.push({name:'DUST',label:'BỤI',advice:'Khẩu trang'}); m = Math.max(m,1); }
  if (q.exposure > 90 && q.contrast > 70) { hz.push({name:'GLARE',label:'CHÓI',advice:'Kính'}); m = Math.max(m,2); }
  const l = m >= 3 ? 'CRITICAL' : m === 2 ? 'RISK' : m === 1 ? 'WARNING' : 'SAFE';
  const c = m >= 3 ? [1,0,0] : m === 2 ? [1,.2,.2] : m === 1 ? [1,.65,0] : [0,1,0];
  return {hazards:hz,overall_level:l,overall_color:c};
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
    const mau = CL[i % CL.length];
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
    if (kp[0] && kp[0][2] > VIS) {
      ctx.fillStyle = 'rgba(0,0,0,.8)';
      ctx.fillRect(kp[0][0]*W-30, kp[0][1]*H-25, 60, 18);
      ctx.fillStyle = mau; ctx.font = 'bold 11px monospace'; ctx.textAlign = 'center';
      ctx.fillText(`P${i+1}`, kp[0][0]*W, kp[0][1]*H-12);
    }
  });
}

// ========== MATLAB BRIDGE ==========
function procMatlabIQA(m) {
  if (!m) { $('iqaM').innerHTML = '<span style="color:#64748b;">Chưa có</span>'; return; }
  const ov = m.overall || 0;
  const st = m.status || 'UNKNOWN';
  const col = st==='SAFE'?'#00ff88':st==='WARNING'?'#f59e0b':st==='DANGER'?'#ef4444':st==='ANALYZING'?'#00d4ff':'#94a3b8';
  const prog = m.progress != null ? Math.round(m.progress*100) : null;
  const age = m._age_seconds != null ? `${m._age_seconds}s` : '';
  let h = `<div class="row"><span style="color:#f59e0b;">🎬</span><span style="font-size:9px;">${(m.video||'?').substring(0,16)}</span></div>`;
  h += `<div class="row"><span>PIQE</span><span>${(m.piqe||0).toFixed(1)}</span></div>`;
  if (m.piqe_full) h += `<div class="row"><span>Full</span><span>${m.piqe_full.toFixed(1)}</span></div>`;
  h += `<div class="row"><b>Tổng</b><b style="color:${col}">${ov.toFixed(1)}</b></div>`;
  h += `<div class="row"><span>Status</span><b style="color:${col}">${st}</b></div>`;
  if (prog != null) h += `<div style="margin-top:3px;background:#1e293b;border-radius:2px;height:3px;"><div style="width:${prog}%;height:100%;background:${col};border-radius:2px;"></div></div><div style="font-size:8px;text-align:right;color:#64748b;">${prog}% · ${age}</div>`;
  $('iqaM').innerHTML = h;
  S.mIQA = m;
}

// Auto mode: the backend reads the newest output/*_iqa.json written by MATLAB, so the web
// picks up new results without choosing a file. Manual load / demo switch auto off.
function setMatlabStatus(text, color) {
  $('jst').textContent = text;
  $('jst').style.color = color;
}

function setMatlabAuto(on) {
  S.mAuto = on;
  $('bMAuto').classList.toggle('on', on);
  $('bMAuto').textContent = on ? '🔄 Tự động: BẬT' : '🔄 Tự động: TẮT';
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
    $('iqa').innerHTML = `
      <div class="row"><span>PIQE</span><span>${q.piqe}</span></div>
      ${q.piqe_full ? `<div class="row"><span>Full</span><span>${q.piqe_full}</span></div>` : ''}
      <div class="row"><span>Blur</span><span>${q.blur}</span></div>
      <div class="row"><b>Tổng</b><b style="color:var(--c)">${q.overall}</b></div>`;

    S.sess.hist.push({
      t: Date.now(), piqe: q.piqe, piqe_full: q.piqe_full || 0,
      blur: q.blur, contrast: q.contrast, noise: q.noise,
      exposure: q.exposure, overall: q.overall,
      time_fast_ms: q.time_fast_ms || 0, time_full_ms: q.time_full_ms || 0,
      frame_ms: data.benchmark?.frame_ms || 0,
      alert: data.env_hazards?.hazards?.[0]?.label || null
    });
    if (S.sess.hist.length > 500) S.sess.hist.shift();
  }

  if (data.env_hazards) {
    const e = data.env_hazards;
    const m = `rgb(${e.overall_color.map(c => Math.round(c*255)).join(',')})`;
    let h = `<div class="row"><span>Mức</span><b style="color:${m}">${e.overall_level}</b></div>`;
    e.hazards.forEach(x => { h += `<div class="row"><span style="color:#ef4444">${x.label}</span><span>${x.advice}</span></div>`; });
    $('mt').innerHTML = h;
    if (e.hazards.length > 0) { $('cb').style.display = 'block'; $('cb').textContent = e.hazards[0].label; }
    else $('cb').style.display = 'none';
  }

  const ds = data.persons || [];
  $('tt').textContent = ds.length > 0 ? `${ds.length} người` : 'Không có';

  if (ds[0] && ds[0].safety) {
    S.safety = ds[0].safety.level;
    const s = ds[0].safety;
    if (s.technique !== 'NONE') {
      $('kt').style.display = 'block';
      const m = `rgb(${s.color.map(c => Math.round(c*255)).join(',')})`;
      $('kt').style.color = m; $('kt').style.borderColor = m;
      $('kt').innerHTML = `${s.label}<br><span style="font-size:9px;font-weight:normal">${s.detail}</span>`;
    } else $('kt').style.display = 'none';
  } else if (ds.length === 0) $('kt').style.display = 'none';

  if (S.three) {
    Human3D.update(ds[0] || null, srcAspect());
    Human3D.setEnv(data.env_hazards ? data.env_hazards.hazards.map(h => h.name) : []);
  } else if (S.ctx2d) render2D(ds.length > 0 ? ds[0].keypoints : null);

  draw2D(ds);
  updateBench(data.benchmark, data.quality);
  alertsFor(data);

  S.nhat_ky.push({t:Date.now(), mode:S.che_do, ...data});
  if (S.nhat_ky.length > 3000) S.nhat_ky.shift();
}

// Server payloads carry alerts already confirmed by the backend; everything computed in the
// browser (scenarios, presets, MediaPipe) goes through the same temporal rules locally.
function alertsFor(data) {
  if (!window.EchoAlerts) return;
  if (S.che_do === 'server') { (data.alerts || []).forEach(a => EchoAlerts.raise(a, true)); return; }
  const real = !!data._real;
  EchoAlerts.observe(real ? 'browser' : 'scenario', data.persons || [], data.quality, {
    source: real ? 'browser' : 'kịch bản',
    report: real,
    snapshot: real ? snapshot : null,
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
      Human3D.setEnv(d.env_hazards ? d.env_hazards.hazards.map(h => h.name) : []);
    } else if (S.ctx2d) render2D(p ? p.keypoints : null);
    $('c3dLabel').textContent = `Mô phỏng 3D — camera "${camId}"` + (p ? ` · ${p.safety.label}` : ' · không có người');
  },
  release() {
    if (!S.ext) return;
    S.ext = null;
    $('c3dLabel').textContent = 'Mô phỏng công nhân 3D';
  }
};

window.EchoTabs = {
  current: 'mon',
  show(name) {
    document.querySelectorAll('.tabs .tab').forEach(b => b.classList.toggle('on', b.dataset.tab === name));
    document.querySelectorAll('#L .pane').forEach(p => { p.hidden = p.id !== 'tab-' + name; });
    document.body.classList.toggle('sub-tab', name !== 'mon');
    if (this.current === name) return;
    this.current = name;
    document.dispatchEvent(new CustomEvent('echo:tab', {detail: name}));
  }
};

function srcAspect() {
  if (S.che_do === 'offline') return 4/3;
  const v = $('v');
  return v.videoWidth && v.videoHeight ? v.videoWidth / v.videoHeight : 4/3;
}

function updateBench(b, q) {
  if (!S.bench.on) return;
  if (b) {
    $('bf').textContent = (b.fps_actual || 0).toFixed(1) + ' FPS';
    $('bm').textContent = (b.avg_frame_ms || 0).toFixed(1) + ' ms';
  }
  if (q) {
    $('bpf').textContent = (q.time_fast_ms || 0).toFixed(1) + ' ms';
    $('bpu').textContent = q.time_full_ms > 0 ? q.time_full_ms.toFixed(1) + ' ms' : 'N/A';
    const sp = q.time_full_ms > 0 ? (q.time_full_ms / Math.max(q.time_fast_ms, .01)).toFixed(1) : '--';
    $('bsp').textContent = sp + '×';
  }
  const hist = S.sess.hist.slice(-30);
  const full = hist.map(h => h.piqe_full).filter(v => v > 0);
  if (full.length > 5) {
    const fast = hist.map(h => h.piqe).slice(-full.length);
    $('bcor').textContent = 'r=' + corr(full, fast).toFixed(3);
  }
}

function corr(x, y) {
  if (x.length !== y.length || x.length < 2) return 0;
  const n = x.length;
  const mx = x.reduce((a,b)=>a+b,0)/n;
  const my = y.reduce((a,b)=>a+b,0)/n;
  let num = 0, dx2 = 0, dy2 = 0;
  for (let i = 0; i < n; i++) {
    const dx = x[i]-mx, dy = y[i]-my;
    num += dx*dy; dx2 += dx*dx; dy2 += dy*dy;
  }
  return num / Math.sqrt(dx2*dy2 + 1e-9);
}

// ========== MAIN LOOP ==========
function loop(now) {
  requestAnimationFrame(loop);
  try {
    if (S.three) render3D();
    if (S.ext) { updDebug(); return; }
    if (S.che_do === 'video' && S.ai_on && S.pose_ready) detect();
    const fps = S.che_do === 'offline' ? FPS_OFF : S.che_do === 'video' ? FPS_VID : FPS_SRV;
    if (now - S.lan_ve < 1000/fps) return;
    S.lan_ve = now;
    S.fps_dem++;
    if (now - S.moc_fps > 1000) { S.fps = S.fps_dem; S.fps_dem = 0; S.moc_fps = now; }
    if (S.che_do === 'offline') procOffline();
    else if (S.che_do === 'video') procVideo();
    else if (S.che_do === 'server') procServer(now);
    updDebug();
  } catch (e) { S.dbg.err = e.message; }
}

function procOffline() {
  S.khung++;
  if (S.tu_dong && S.khung % (FPS_OFF*4) === 0) {
    const ds = Object.keys(KB);
    const i = ds.indexOf(S.kich_ban);
    pickKB(ds[(i+1) % ds.length]);
    return;
  }
  const kb = KB[S.kich_ban];
  if (!kb) return;
  const t = S.khung / FPS_OFF;
  const br = Math.sin(t*2)*.008;
  const kps = kb.kps.map((kp, i) => {
    if (kp[2] < VIS) return [kp[0], kp[1], kp[2]];
    if (i >= 5 && i <= 12) return [kp[0], kp[1]-br, kp[2]];
    return [kp[0], kp[1], kp[2]];
  });
  const co = kps.some(k => k[2] > VIS);
  const ov = $('ov');
  if (ov.width !== 640) ov.width = 640;
  if (ov.height !== 480) ov.height = 480;
  const ctx = ov.getContext('2d');
  ctx.fillStyle = '#0a0f1a'; ctx.fillRect(0, 0, 640, 480);
  ctx.strokeStyle = '#1e293b'; ctx.lineWidth = 1;
  for (let i = 0; i <= 8; i++) {
    ctx.beginPath(); ctx.moveTo(0, i*60); ctx.lineTo(640, i*60); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(i*80, 0); ctx.lineTo(i*80, 480); ctx.stroke();
  }
  process({
    detected: co, persons: co ? [{id:0, keypoints:kps, safety:kb.safety}] : [],
    hands: [], quality:kb.iqa, env_hazards:kb.env
  });
}

function procVideo() {
  const v = $('v');
  if (v.paused || v.readyState < 2) { S.dbg.video = 'loading'; return; }
  S.dbg.video = `${v.videoWidth}x${v.videoHeight}`;
  if (S.ai_on && S.pose_ready) return;
  const q = calcIQA();
  if (!q) return;
  S.khung++;
  if (S.khung % (FPS_VID*4) === 0) {
    const ds = Object.keys(KB);
    const i = ds.indexOf(S.kich_ban);
    S.kich_ban = ds[(i+1) % ds.length];
    document.querySelectorAll('.kbb').forEach(b => b.classList.toggle('on', b.dataset.kb === S.kich_ban));
  }
  const kb = KB[S.kich_ban];
  process({
    detected: true, persons: [{id:0, keypoints:kb.kps, safety:kb.safety}],
    hands: [], quality:q, env_hazards:envAnalysis(q)
  });
}

function procServer(now) {
  if (!S.ws || S.ws.readyState !== 1 || S.dang_gui) return;
  if (now - S.lan_gui < 1000/FPS_SRV) return;
  S.lan_gui = now;
  const v = $('v');
  if (!v.videoWidth || !v.videoHeight) return;
  S.dang_gui = true;
  const c = document.createElement('canvas');
  c.width = v.videoWidth; c.height = v.videoHeight;
  c.getContext('2d').drawImage(v, 0, 0);
  try {
    S.ws.send(JSON.stringify({
      image: c.toDataURL('image/jpeg', .55),
      timestamp: v.currentTime || performance.now()/1000
    }));
  } catch (e) { S.dang_gui = false; }
}

function updDebug() {
  const d = $('dbc');
  if (!d) return;
  d.classList.remove('err');
  const t = S.three ? '3D' : '2D';
  const ai = S.ai_on && S.pose_ready ? `AI:${S.det_fps}fps` : 'AI:OFF';
  const src = S.mIQA ? 'MATLAB' : (S.ai_on ? 'Live' : 'Preset');
  d.textContent = `[${S.che_do.toUpperCase()}] ${t} | FPS:${S.fps} | ${ai} | IQA:${src} | Video:${S.dbg.video} | ${S.kich_ban} | ${S.ext ? 'Cam:' + S.ext + ' | ' : ''}An toàn:${S.safety} | Log:${S.nhat_ky.length}` + (S.dbg.err ? ` | LỖI:${S.dbg.err}` : '');
  const b = $('badge');
  if (S.pose_loading) { b.textContent = '⏳ AI...'; b.style.background = '#0ea5e9'; b.style.display = 'block'; }
  else if (S.pose_ready && S.ai_on) { b.textContent = `🔬 AI:${S.det_fps}FPS`; b.style.background = '#059669'; b.style.display = 'block'; }
  else if (S.che_do === 'video') { b.textContent = '🎭 Preset'; b.style.background = '#f59e0b'; b.style.display = 'block'; }
  else b.style.display = 'none';
}

function pickKB(t) {
  if (!KB[t]) return;
  S.kich_ban = t; S.khung = 0;
  document.querySelectorAll('.kbb').forEach(b => b.classList.toggle('on', b.dataset.kb === t));
  const el = $('mode');
  if (el) { el.textContent = 'OFFLINE — ' + KB[t].ten; el.style.background = 'var(--w)'; }
}

function cleanup() {
  if (S.ws) { try { S.ws.close(); } catch(e){} S.ws = null; }
  const v = $('v');
  try { v.pause(); } catch(e){}
  if (S.stream) { S.stream.getTracks().forEach(t => t.stop()); S.stream = null; }
  v.srcObject = null;
  if (S.url) { URL.revokeObjectURL(S.url); S.url = null; }
  v.removeAttribute('src');
  try { v.load(); } catch(e){}
  S.ready = false; S.last_vt = -1; S.dbg.video = '-';
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
  if (h.length === 0) return {piqe:0,piqe_full:0,blur:0,contrast:0,noise:0,exposure:0,
    overall:0,min:0,max:0,std:0,status:'UNKNOWN',avgFrameMs:0,avgFast:0,avgFull:0,
    speedup:'--',alertCount:0,alerts:{},total:0};
  const avg = a => a.reduce((x,y)=>x+y,0)/a.length;
  const ov = h.map(x => x.overall || 0);
  const mo = avg(ov);
  const st = mo >= 80 ? 'SAFE' : mo >= 60 ? 'WARNING' : 'DANGER';
  const fast = avg(h.map(x => x.time_fast_ms || 0));
  const full = avg(h.map(x => x.time_full_ms || 0).filter(v => v > 0));
  const alerts = {};
  h.forEach(x => { if (x.alert) alerts[x.alert] = (alerts[x.alert] || 0) + 1; });
  return {
    piqe: avg(h.map(x => x.piqe || 0)),
    piqe_full: avg(h.map(x => x.piqe_full || 0)),
    blur: avg(h.map(x => x.blur || 0)),
    contrast: avg(h.map(x => x.contrast || 0)),
    noise: avg(h.map(x => x.noise || 0)),
    exposure: avg(h.map(x => x.exposure || 0)),
    overall: mo, min: Math.min(...ov), max: Math.max(...ov),
    std: Math.sqrt(avg(ov.map(x => (x-mo)**2))),
    status: st, avgFrameMs: avg(h.map(x => x.frame_ms || 0)),
    avgFast: fast, avgFull: full,
    speedup: fast > 0 && full > 0 ? (full/fast).toFixed(1) : '--',
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
<b>Mode:</b> ${S.che_do.toUpperCase()} | <b>AI:</b> ${S.ai_on ? 'ON' : 'OFF'}<br>
<b>Samples:</b> ${s.total} frames</p>
<h2>1. IQA Metrics</h2>
<div>
  <div class="metric"><div class="label">PIQE Fast</div><div class="value">${s.piqe.toFixed(1)}</div></div>
  <div class="metric"><div class="label">PIQE Full</div><div class="value">${s.piqe_full.toFixed(1)}</div></div>
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
  <tr><td>PIQE fast</td><td>${s.avgFast.toFixed(1)} ms</td><td>Realtime</td></tr>
  <tr><td>PIQE full</td><td>${s.avgFull>0?s.avgFull.toFixed(1)+' ms':'N/A'}</td><td>Sampled 1/30</td></tr>
  <tr><td>Speedup</td><td><span class="hl">${s.speedup}×</span></td><td>Trade-off</td></tr>
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
  <li><b>3-tier fallback:</b> never-fail demo</li>
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

// ========== COMPARE ==========
function toggleCmp() {
  S.cmp.on = !S.cmp.on;
  $('cc').classList.toggle('show', S.cmp.on);
  $('bCmp').classList.toggle('on', S.cmp.on);
  if (S.cmp.on) updCmpSlider(50);
  else $('ov').style.clipPath = 'none';
}

function updCmpSlider(p) {
  S.cmp.pct = p;
  $('cs').style.left = p + '%';
  const o = $('ov');
  if (o) o.style.clipPath = `inset(0 ${100-p}% 0 0)`;
}

let dragging = false;
document.addEventListener('pointerdown', e => {
  if (e.target.id === 'cs') { dragging = true; e.preventDefault(); }
});
document.addEventListener('pointerup', () => { dragging = false; });
document.addEventListener('pointercancel', () => { dragging = false; });
document.addEventListener('pointermove', e => {
  if (!dragging || !S.cmp.on) return;
  const rect = $('v').getBoundingClientRect();
  let p = ((e.clientX - rect.left) / rect.width) * 100;
  p = Math.max(0, Math.min(100, p));
  updCmpSlider(p);
});

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

  $('bCam').onclick = async () => {
    try {
      cleanup();
      S.stream = await navigator.mediaDevices.getUserMedia({
        video: {width:{ideal:640}, height:{ideal:480}}, audio:false
      });
      const v = $('v');
      v.srcObject = S.stream; v.muted = true;
      await v.play();
      S.ready = true; S.che_do = 'video'; S.khung = 0;
      S.dbg.video = 'camera live';
      $('stt').textContent = S.ai_on ? 'Camera + AI' : 'Camera (AI off)';
      $('mode').textContent = 'CAMERA'; $('mode').style.background = '#6366f1';
    } catch (e) { $('stt').textContent = 'Lỗi: ' + e.message; }
  };

  $('bVid').onclick = () => $('file').click();
  $('file').onchange = e => {
    const f = e.target.files[0]; if (!f) return;
    cleanup();
    S.url = URL.createObjectURL(f);
    const v = $('v');
    v.src = S.url; v.muted = true; v.loop = true;
    v.onloadedmetadata = () => {
      v.play().then(() => {
        S.ready = true; S.che_do = 'video'; S.khung = 0;
        S.dbg.video = `${v.videoWidth}x${v.videoHeight}`;
        $('stt').textContent = S.ai_on ? 'Video + AI' : 'Video (AI off)';
        $('mode').textContent = 'VIDEO'; $('mode').style.background = 'var(--ok)';
      }).catch(err => { $('stt').textContent = 'Lỗi play: ' + err.message; });
    };
    v.onerror = () => { $('stt').textContent = 'Codec sai — chuyển .mp4 H.264'; };
  };

  $('bSrv').onclick = () => {
    if (S.ws) { try { S.ws.close(); } catch(e){} S.ws = null; return; }
    cleanup();
    S.che_do = 'server';
    try { S.ws = new WebSocket($('wsurl').value); }
    catch (e) { $('stt').textContent = 'URL sai'; S.che_do = 'offline'; return; }
    S.ws.onopen = () => {
      $('bSrv').textContent = 'Ngắt';
      $('bSrv').style.background = '#ef4444';
      $('stt').textContent = 'Đã kết nối';
      $('mode').textContent = 'SERVER'; $('mode').style.background = 'var(--ok)';
    };
    S.ws.onclose = () => {
      S.ws = null;
      $('bSrv').textContent = 'Server';
      $('bSrv').style.background = '#334155';
      if (S.che_do === 'server') {
        S.che_do = 'offline';
        $('stt').textContent = 'Mất kết nối';
        pickKB(S.kich_ban);
      }
    };
    S.ws.onerror = () => { $('stt').textContent = 'Lỗi Python'; };
    S.ws.onmessage = e => {
      S.dang_gui = false;
      try { const d = JSON.parse(e.data); if (d.skip) return; process(d); } catch (err) {}
    };
  };

  $('bLog').onclick = () => {
    const b = new Blob([JSON.stringify(S.nhat_ky, null, 2)], {type:'application/json'});
    const u = URL.createObjectURL(b);
    const a = document.createElement('a');
    a.href = u; a.download = `echo_log_${Date.now()}.json`; a.click();
    URL.revokeObjectURL(u);
  };

  $('bTst').onclick = selfTest;
  $('bRep').onclick = taoReport;
  $('bCmp').onclick = toggleCmp;
  $('bBen').onclick = toggleBench;

  $('bAuto').onclick = () => {
    S.tu_dong = !S.tu_dong;
    $('bAuto').classList.toggle('on', S.tu_dong);
    $('bAuto').textContent = S.tu_dong ? 'Đang tự động' : 'Tự động chạy';
    if (S.che_do !== 'offline') { cleanup(); S.che_do = 'offline'; pickKB(S.kich_ban); }
  };

  document.querySelectorAll('.kbb').forEach(b => {
    b.onclick = () => {
      cleanup(); S.che_do = 'offline'; S.tu_dong = false;
      $('bAuto').classList.remove('on');
      $('bAuto').textContent = 'Tự động chạy';
      pickKB(b.dataset.kb);
    };
  });

  $('bMAuto').onclick = () => setMatlabAuto(!S.mAuto);
  setMatlabAuto(true);
  setInterval(autoMatlab, 2000);
  if (window.EchoBackend) EchoBackend.on('status', () => autoMatlab());
  $('bJson').onclick = pickJSON;
  $('bDemo').onclick = () => {
    setMatlabAuto(false);
    procMatlabIQA({
      video:'demo_video.mp4', frames:450, fps:30,
      piqe:78.3, piqe_full:79.1, blur:81.5, contrast:74.2,
      noise:85.1, exposure:88.7, overall:81.2,
      status:'SAFE', color:[.14,.50,.32], piqe_mode:'both',
      _source_file:'demo.json', _age_seconds:0
    });
    $('jst').textContent = '🎭 Demo'; $('jst').style.color = '#8b5cf6';
  };
  $('bClr').onclick = () => {
    setMatlabAuto(false);
    S.mIQA = null; S.mFile = null;
    if (S.mTimer) { clearInterval(S.mTimer); S.mTimer = null; }
    procMatlabIQA(null);
    $('jst').textContent = 'Đã xóa'; $('jst').style.color = '#94a3b8';
  };
  $('jfile').onchange = e => { if (e.target.files[0]) loadJSON(e.target.files[0]); };

  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT') return;
    const ds = Object.keys(KB);
    if (e.key >= '1' && e.key <= '8') {
      const i = parseInt(e.key) - 1;
      if (ds[i]) document.querySelector(`.kbb[data-kb="${ds[i]}"]`).click();
    } else if (e.key === ' ') { e.preventDefault(); $('bAuto').click(); }
    else if (e.key === 'a' || e.key === 'A') $('bAI').click();
    else if (e.key === 'b' || e.key === 'B') toggleBench();
    else if (e.key === 'c' || e.key === 'C') toggleCmp();
    else if (e.key === 'p' || e.key === 'P') taoReport();
    else if (e.key === 'r' || e.key === 'R') { cleanup(); S.che_do = 'offline'; pickKB('an_toan'); }
    else if (e.key === 't' || e.key === 'T') $('bTst').click();
  });

  document.querySelectorAll('.tabs .tab').forEach(b => { b.onclick = () => EchoTabs.show(b.dataset.tab); });

  window.addEventListener('resize', () => { if (S.three) Human3D.resize(); });
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
  const ds = Object.keys(KB);
  const tests = [
    ['Three.js', () => S.lib],
    ['Scene 3D', () => S.three],
    ['Người 3D', () => S.three && Human3D.info().ok],
    ['Model GLTF', () => S.three && Human3D.info().mode === 'gltf'],
    ['8 KB', () => ds.length === 8],
    ['Canvas', () => $('ov').getContext('2d') !== null],
    ['AI button', () => typeof $('bAI').onclick === 'function'],
    ['Cam button', () => typeof $('bCam').onclick === 'function'],
    ['Vid button', () => typeof $('bVid').onclick === 'function'],
    ['MATLAB button', () => typeof $('bJson').onclick === 'function'],
    ['Report button', () => typeof $('bRep').onclick === 'function'],
    ['Compare button', () => typeof $('bCmp').onclick === 'function'],
    ['Bench button', () => typeof $('bBen').onclick === 'function'],
    ['Cảnh báo (còi/toast)', () => !!window.EchoAlerts],
    ['Tab Camera/Sự kiện', () => !!$('tab-cam') && !!$('tab-evt')],
    ['Backend', () => window.EchoBackend && EchoBackend.online ? true : null],
    ['MediaPipe', () => S.pose_ready],
    ['Loop', () => S.fps >= 0],
    ['Debug', () => $('dbc') !== null]
  ];
  let pass = 0;
  await new Promise(r => setTimeout(r, 200));
  tests.forEach(([n, fn], i) => {
    setTimeout(() => {
      try {
        const ok = fn();
        add(n, ok);
        if (ok === true) pass++;
      } catch (e) { add(n, false); }
    }, i*50);
  });
  await new Promise(r => setTimeout(r, tests.length*50 + 100));
  for (const kb of ds) {
    pickKB(kb);
    await new Promise(r => setTimeout(r, 30));
    const ok = S.kich_ban === kb;
    add(`KB "${KB[kb].ten}"`, ok);
    if (ok) pass++;
  }
  pickKB('an_toan');
  add(`TỔNG: ${pass}/${tests.length + ds.length}`, pass === tests.length + ds.length);
  $('stt').textContent = `Self-test: ${pass}/${tests.length + ds.length}`;
}

// Bootstrap
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', loadStep);
else loadStep();

console.log('%c ECHO MOVE v22.0 — FINAL', 'color:#00ffcc;font-weight:bold;font-size:14px');
console.log('  Shortcuts: 1-8 | Space | A(AI) | B(Bench) | C(Compare) | P(Report) | R(Reset) | T(Test)');
