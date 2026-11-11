/* Realistic 3D worker for ECHO MOVE.
 *
 * A rigged humanoid (Mixamo skeleton, web/assets/models/worker.glb) dressed as a worker
 * (hi-vis vest, hard hat, gloves, boots) and posed from COCO-17 keypoints by retargeting
 * limb directions onto bones. Until / unless the GLTF loads, a procedural humanoid with the
 * same skeleton is shown, so the same retargeting code drives both.
 *
 * Plain script (no ES modules) so the UI keeps working from file://.
 * Public API: window.Human3D.{init, update, setLevel, setEnv, render, resize, info}
 */
(function () {
  'use strict';

  const RIG = 'mixamorig';
  const MODEL_URL = 'assets/models/worker.glb';
  const MODEL_JS = 'assets/models/worker_glb.js';
  const VIS = 0.3;
  const LEVEL_HEX = {SAFE: 0x22c55e, WARNING: 0xf59e0b, RISK: 0xef4444, CRITICAL: 0xef4444};

  // bone -> child bone that defines its pointing direction
  const DRIVEN = {
    LeftArm: 'LeftForeArm', LeftForeArm: 'LeftHand',
    RightArm: 'RightForeArm', RightForeArm: 'RightHand',
    LeftUpLeg: 'LeftLeg', LeftLeg: 'LeftFoot',
    RightUpLeg: 'RightLeg', RightLeg: 'RightFoot',
    Neck: 'Head'
  };
  // bone -> [from keypoint, to keypoint] (COCO indices; 'neck'/'head' are synthetic)
  const TARGET = {
    LeftArm: [5, 7], LeftForeArm: [7, 9], RightArm: [6, 8], RightForeArm: [8, 10],
    LeftUpLeg: [11, 13], LeftLeg: [13, 15], RightUpLeg: [12, 14], RightLeg: [14, 16],
    Neck: ['neck', 'head']
  };
  // [parent kp, child kp, dims key] used to recover depth from foreshortening
  const CHAIN = [[5, 7, 'upperArm'], [7, 9, 'foreArm'], [6, 8, 'upperArm'], [8, 10, 'foreArm'],
                 [11, 13, 'thigh'], [13, 15, 'shin'], [12, 14, 'thigh'], [14, 16, 'shin']];

  const V = () => new THREE.Vector3();
  const st = {
    ok: false, mode: 'none', loading: false, error: null,
    scene: null, cam: null, rnd: null, ctl: null, el: null, clock: null,
    holder: null, rig: null, bones: null, rest: null, dims: null,
    level: 'SAFE', env: [], visible: false, lastPose: 0,
    uniforms: {uGlow: {value: null}},
    fx: {}
  };

  // ---------------------------------------------------------------- scene
  function init(container) {
    if (typeof THREE === 'undefined') return false;
    st.el = container;
    st.uniforms.uGlow.value = new THREE.Color(LEVEL_HEX.SAFE);
    const W = container.clientWidth || 500, H = container.clientHeight || 500;
    st.scene = new THREE.Scene();
    st.scene.background = new THREE.Color(0x0b1220);
    st.scene.fog = new THREE.Fog(0x0b1220, 7, 18);
    st.cam = new THREE.PerspectiveCamera(38, W / H, 0.05, 60);
    st.cam.position.set(0.9, 1.55, 4.6);
    st.rnd = new THREE.WebGLRenderer({antialias: true});
    st.rnd.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    st.rnd.setSize(W, H);
    st.rnd.shadowMap.enabled = true;
    st.rnd.shadowMap.type = THREE.PCFSoftShadowMap;
    st.rnd.outputEncoding = THREE.sRGBEncoding;
    st.rnd.toneMapping = THREE.ACESFilmicToneMapping;
    st.rnd.toneMappingExposure = 1.05;
    container.appendChild(st.rnd.domElement);
    if (THREE.OrbitControls) {
      st.ctl = new THREE.OrbitControls(st.cam, st.rnd.domElement);
      st.ctl.target.set(0, 0.85, 0);
      st.ctl.enableDamping = true;
      st.ctl.maxPolarAngle = Math.PI * 0.49;
      st.ctl.minDistance = 1.5; st.ctl.maxDistance = 10;
      st.ctl.update();
    }
    st.clock = new THREE.Clock();
    buildLights();
    buildWorkshop();
    buildFx();
    st.holder = new THREE.Group();
    st.scene.add(st.holder);
    attachRig(buildProceduralRig(), 'procedural');
    linearize(st.scene);
    st.ok = true;
    loadModel();
    return true;
  }

  function buildLights() {
    const hemi = new THREE.HemisphereLight(0xdbeafe, 0x3f3a33, 0.75);
    const key = new THREE.DirectionalLight(0xfff4e0, 1.6);
    key.position.set(2.5, 5, 3);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    Object.assign(key.shadow.camera, {left: -3, right: 3, top: 3, bottom: -3, near: 0.5, far: 15});
    key.shadow.bias = -0.0005;
    const rim = new THREE.DirectionalLight(0x93c5fd, 0.55);
    rim.position.set(-3, 2.5, -3);
    st.scene.add(hemi, key, rim);
    st.fx.lights = {hemi, key, rim};
  }

  function stripeTexture() {
    const c = document.createElement('canvas');
    c.width = 128; c.height = 16;
    const x = c.getContext('2d');
    x.fillStyle = '#facc15'; x.fillRect(0, 0, 128, 16);
    x.fillStyle = '#111';
    for (let i = -16; i < 128; i += 32) {
      x.beginPath(); x.moveTo(i, 16); x.lineTo(i + 16, 0); x.lineTo(i + 32, 0); x.lineTo(i + 16, 16); x.fill();
    }
    const t = new THREE.CanvasTexture(c);
    t.wrapS = THREE.RepeatWrapping;
    t.encoding = THREE.sRGBEncoding;
    return t;
  }

  function concreteTexture() {
    const c = document.createElement('canvas');
    c.width = c.height = 256;
    const x = c.getContext('2d');
    x.fillStyle = '#5b6068'; x.fillRect(0, 0, 256, 256);
    for (let i = 0; i < 2600; i++) {
      const g = 80 + Math.random() * 40 | 0;
      x.fillStyle = `rgba(${g},${g + 2},${g + 6},.35)`;
      x.fillRect(Math.random() * 256, Math.random() * 256, 2, 2);
    }
    x.strokeStyle = 'rgba(30,30,30,.35)'; x.lineWidth = 2;
    x.strokeRect(0, 0, 256, 256);
    const t = new THREE.CanvasTexture(c);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.repeat.set(10, 10);
    t.encoding = THREE.sRGBEncoding;
    return t;
  }

  function buildWorkshop() {
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(24, 24),
      new THREE.MeshStandardMaterial({map: concreteTexture(), roughness: 0.92}));
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    st.scene.add(floor);

    // Yellow/black safety zone around the work area.
    const tex = stripeTexture();
    const mat = new THREE.MeshStandardMaterial({map: tex, roughness: 0.6});
    const half = 1.3, w = 0.09;
    [[0, half, 2 * half, 0], [0, -half, 2 * half, 0], [half, 0, 2 * half, 1], [-half, 0, 2 * half, 1]].forEach(([x, z, len, rot]) => {
      const t = tex.clone(); t.needsUpdate = true; t.repeat.set(len * 4, 1);
      const m = new THREE.Mesh(new THREE.PlaneGeometry(len + w, w), mat.clone());
      m.material.map = t;
      m.rotation.x = -Math.PI / 2;
      m.rotation.z = rot ? Math.PI / 2 : 0;
      m.position.set(x, 0.002, z);
      m.receiveShadow = true;
      st.scene.add(m);
    });

    // Back wall + crates + pallet rack for context.
    const wall = new THREE.Mesh(new THREE.PlaneGeometry(24, 6),
      new THREE.MeshStandardMaterial({color: 0x1f2937, roughness: 0.95}));
    wall.position.set(0, 3, -4.5);
    st.scene.add(wall);
    const band = new THREE.Mesh(new THREE.PlaneGeometry(24, 0.25), new THREE.MeshStandardMaterial({color: 0xf59e0b, roughness: 0.7}));
    band.position.set(0, 1.2, -4.49);
    st.scene.add(band);

    const wood = new THREE.MeshStandardMaterial({color: 0xa16207, roughness: 0.85});
    const card = new THREE.MeshStandardMaterial({color: 0xb08850, roughness: 0.9});
    const crate = (x, z, s, m, ry) => {
      const b = new THREE.Mesh(new THREE.BoxGeometry(s, s, s), m);
      b.position.set(x, s / 2, z); b.rotation.y = ry || 0;
      b.castShadow = b.receiveShadow = true;
      st.scene.add(b);
      return b;
    };
    crate(-2.3, -1.6, 0.7, wood, 0.2); crate(-2.3, -1.6, 0.5, card).position.y = 0.95;
    crate(-1.6, -2.2, 0.6, card, -0.3); crate(2.4, -1.9, 0.8, wood, 0.1);
    const pallet = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.14, 1.0), wood);
    pallet.position.set(2.2, 0.07, -0.6); pallet.castShadow = pallet.receiveShadow = true;
    st.scene.add(pallet);
    crate(1.0, -0.9, 0.38, card, 0.15);

    const steel = new THREE.MeshStandardMaterial({color: 0x2563eb, roughness: 0.5, metalness: 0.4});
    const orange = new THREE.MeshStandardMaterial({color: 0xea580c, roughness: 0.5, metalness: 0.4});
    for (const x of [-3.6, -1.4]) for (const z of [-3.9, -3.1]) {
      const p = new THREE.Mesh(new THREE.BoxGeometry(0.08, 3, 0.08), steel);
      p.position.set(x, 1.5, z); p.castShadow = true; st.scene.add(p);
    }
    for (const y of [0.4, 1.4, 2.4]) {
      const s = new THREE.Mesh(new THREE.BoxGeometry(2.3, 0.08, 0.9), orange);
      s.position.set(-2.5, y, -3.5); s.castShadow = s.receiveShadow = true; st.scene.add(s);
      crate(-3.0, -3.5, 0.5, card).position.y = y + 0.29;
      crate(-2.0, -3.5, 0.45, wood).position.y = y + 0.27;
    }
  }

  function buildFx() {
    // Warning beacon on a pole.
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 2.2, 10),
      new THREE.MeshStandardMaterial({color: 0x374151, metalness: 0.6, roughness: 0.4}));
    pole.position.set(1.7, 1.1, -1.4); pole.castShadow = true;
    const lampMat = new THREE.MeshStandardMaterial({color: LEVEL_HEX.SAFE, emissive: LEVEL_HEX.SAFE, emissiveIntensity: 1.5});
    const lamp = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.16, 18), lampMat);
    lamp.position.set(1.7, 2.28, -1.4);
    const lampLight = new THREE.PointLight(LEVEL_HEX.SAFE, 0.6, 5, 2);
    lampLight.position.copy(lamp.position);
    st.scene.add(pole, lamp, lampLight);

    // Floor ring under the worker coloured by safety level.
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.62, 0.68, 64),
      new THREE.MeshBasicMaterial({color: LEVEL_HEX.SAFE, transparent: true, opacity: 0.7, side: THREE.DoubleSide}));
    ring.rotation.x = -Math.PI / 2; ring.position.y = 0.004;
    st.scene.add(ring);

    // Two CCTV cameras with faint tracking beams to the worker's chest.
    const camMat = new THREE.MeshStandardMaterial({color: 0xe5e7eb, roughness: 0.4, metalness: 0.3});
    const beams = [[-1.9, 2.6, 1.6], [1.9, 2.6, 1.6]].map(p => {
      const body = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.1, 0.24), camMat);
      body.position.set(p[0], p[1], p[2]);
      body.lookAt(0, 1.1, 0);
      st.scene.add(body);
      const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.004, 0.004, 1, 6),
        new THREE.MeshBasicMaterial({color: LEVEL_HEX.SAFE, transparent: true, opacity: 0.35, depthWrite: false}));
      st.scene.add(beam);
      return {from: body.position.clone(), beam};
    });

    // Dust/smoke particles (shown for DUST/SMOKE hazards).
    const N = 900, pos = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 8;
      pos[i * 3 + 1] = Math.random() * 3.2;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 6;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const dust = new THREE.Points(g, new THREE.PointsMaterial({color: 0xd6d3d1, size: 0.035, transparent: true, opacity: 0.55, depthWrite: false}));
    dust.visible = false;
    st.scene.add(dust);

    // Fire glow (FIRE hazard).
    const fire = new THREE.PointLight(0xff6a00, 0, 6, 2);
    fire.position.set(-1.8, 0.6, -0.8);
    const flame = new THREE.Mesh(new THREE.ConeGeometry(0.25, 0.8, 16),
      new THREE.MeshBasicMaterial({color: 0xff7a1a, transparent: true, opacity: 0.85}));
    flame.position.set(-1.8, 0.4, -0.8);
    flame.visible = false;
    st.scene.add(fire, flame);

    Object.assign(st.fx, {lamp, lampLight, ring, beams, dust, fire, flame});
  }

  // ---------------------------------------------------------------- worker look
  function hardHat(scale) {
    const g = new THREE.Group();
    const yellow = new THREE.MeshStandardMaterial({color: 0xfacc15, roughness: 0.35, metalness: 0.05});
    const dome = new THREE.Mesh(new THREE.SphereGeometry(10.8, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2), yellow);
    dome.scale.set(1, 0.82, 1.12);
    const brim = new THREE.Mesh(new THREE.CylinderGeometry(12.6, 12.8, 0.7, 40), yellow);
    brim.scale.set(1, 1, 1.18); brim.position.set(0, 0.2, 1.4);
    const ridge = new THREE.Mesh(new THREE.TorusGeometry(10.6, 0.9, 8, 28, Math.PI), yellow);
    ridge.rotation.y = Math.PI / 2;
    ridge.scale.set(1.13, 0.84, 1);
    const band = new THREE.Mesh(new THREE.CylinderGeometry(10.9, 10.9, 1.6, 32, 1, true),
      new THREE.MeshStandardMaterial({color: 0x1f2937, roughness: 0.8, side: THREE.DoubleSide}));
    band.position.y = 0.9; band.scale.set(1, 1, 1.12);
    g.add(dome, brim, ridge, band);
    g.traverse(o => { if (o.isMesh) o.castShadow = true; });
    g.position.set(0, 13.2, 0.4);
    g.scale.setScalar(scale);
    return g;
  }

  function face(head, scale, eyeY, eyeZ) {
    const white = new THREE.MeshStandardMaterial({color: 0xf8fafc, roughness: 0.3});
    const iris = new THREE.MeshStandardMaterial({color: 0x1e293b, roughness: 0.2});
    const brow = new THREE.MeshStandardMaterial({color: 0x3b2a20, roughness: 0.9});
    [-1, 1].forEach(k => {
      const e = new THREE.Mesh(new THREE.SphereGeometry(1.25, 14, 10), white);
      e.position.set(3.0 * k, eyeY, eyeZ); e.scale.set(1, 0.8, 0.6);
      const p = new THREE.Mesh(new THREE.SphereGeometry(0.62, 10, 8), iris);
      p.position.set(3.0 * k, eyeY, eyeZ + 0.65);
      const b = new THREE.Mesh(new THREE.BoxGeometry(3, 0.55, 0.8), brow);
      b.position.set(3.0 * k, eyeY + 2.1, eyeZ - 0.2); b.rotation.z = -0.12 * k;
      [e, p, b].forEach(m => { m.position.multiplyScalar(scale); m.scale.multiplyScalar(scale); head.add(m); });
    });
    const mouth = new THREE.Mesh(new THREE.BoxGeometry(2.6, 0.35, 0.6), new THREE.MeshStandardMaterial({color: 0x7f3f35, roughness: 0.8}));
    mouth.position.set(0, eyeY - 4.6, eyeZ - 0.4).multiplyScalar(scale);
    mouth.scale.setScalar(scale);
    head.add(mouth);
  }

  // Scene colours are authored in sRGB; the renderer works in linear space.
  function linearize(root) {
    root.traverse(o => {
      const mats = o.material ? (Array.isArray(o.material) ? o.material : [o.material]) : [];
      mats.forEach(m => {
        if (m.userData.linear || m.onBeforeCompile.toString().indexOf('echoRegion') >= 0) return;
        if (m.color) m.color.convertSRGBToLinear();
        if (m.emissive) m.emissive.convertSRGBToLinear();
        m.userData.linear = true;
      });
    });
  }
  const lin = hex => new THREE.Color(hex).convertSRGBToLinear();

  // Colours the single-material Xbot surface as worker clothing, using bind-pose height.
  function dressMaterial(mat) {
    const m = new THREE.MeshStandardMaterial({
      color: 0xffffff, roughness: 0.78, metalness: 0.0, skinning: true, side: THREE.FrontSide
    });
    m.onBeforeCompile = shader => {
      shader.uniforms.uGlow = st.uniforms.uGlow;
      shader.vertexShader = 'varying vec3 vRest;\n' + shader.vertexShader.replace(
        '#include <begin_vertex>', '#include <begin_vertex>\n vRest = position;');
      shader.fragmentShader = `varying vec3 vRest;\nuniform vec3 uGlow;
vec3 echoRegion(vec3 p, out float stripe) {
  float ax = abs(p.x);
  stripe = 0.0;
  if (p.y > 1.47 && ax < 0.17) return vec3(0.80, 0.60, 0.47);
  if (ax > 0.70) return vec3(0.55, 0.41, 0.20);
  if (p.y > 1.05) {
    if (ax < 0.215) {
      if ((p.y > 1.16 && p.y < 1.195) || (p.y > 1.29 && p.y < 1.325)) { stripe = 1.0; return vec3(0.85); }
      return vec3(1.0, 0.36, 0.02);
    }
    return vec3(0.14, 0.20, 0.34);
  }
  if (p.y > 0.99) return vec3(0.14, 0.20, 0.34);
  if (p.y > 0.95) return vec3(0.07, 0.06, 0.05);
  if (p.y < 0.115) return vec3(0.09, 0.07, 0.05);
  return vec3(0.16, 0.19, 0.25);
}
` + shader.fragmentShader
        .replace('#include <color_fragment>', '#include <color_fragment>\n float echoStripe;\n diffuseColor.rgb = pow(echoRegion(vRest, echoStripe), vec3(2.2));')
        .replace('#include <emissivemap_fragment>', '#include <emissivemap_fragment>\n totalEmissiveRadiance += uGlow * echoStripe * 0.9;');
    };
    m.customProgramCacheKey = () => 'echo-worker-' + (mat && mat.name);
    return m;
  }

  // ---------------------------------------------------------------- rigs
  function buildProceduralRig() {
    const root = new THREE.Group();
    root.name = 'procedural';
    const mk = (n, parent, x, y, z) => {
      const o = new THREE.Object3D(); o.name = RIG + n; o.position.set(x, y, z); parent.add(o); return o;
    };
    const skin = new THREE.MeshStandardMaterial({color: 0xcc9977, roughness: 0.7});
    const shirt = new THREE.MeshStandardMaterial({color: 0x24345a, roughness: 0.8});
    const vest = new THREE.MeshStandardMaterial({color: 0xff5c05, roughness: 0.6});
    const pants = new THREE.MeshStandardMaterial({color: 0x29303f, roughness: 0.85});
    const boot = new THREE.MeshStandardMaterial({color: 0x17120d, roughness: 0.7});
    const glove = new THREE.MeshStandardMaterial({color: 0x8c6a33, roughness: 0.8});
    const stripe = new THREE.MeshStandardMaterial({color: 0xdddddd, emissive: LEVEL_HEX.SAFE, emissiveIntensity: 0.8});
    st.fx.procStripe = stripe;
    const shade = m => { m.castShadow = true; m.receiveShadow = true; return m; };
    const limb = (bone, child, r, mat) => {
      const d = child.position.clone(), L = d.length();
      const g = new THREE.Group();
      const c = shade(new THREE.Mesh(new THREE.CylinderGeometry(r * 0.9, r, L, 16), mat));
      c.position.y = L / 2;
      const s = shade(new THREE.Mesh(new THREE.SphereGeometry(r, 16, 12), mat));
      g.add(c, s);
      g.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize());
      bone.add(g);
    };

    const hips = mk('Hips', root, 0, 1.04, 0.02);
    const sp = mk('Spine', hips, 0, 0.102, 0);
    const sp1 = mk('Spine1', sp, 0, 0.101, -0.01);
    const sp2 = mk('Spine2', sp1, 0, 0.091, -0.014);
    const neck = mk('Neck', sp2, 0, 0.167, -0.025);
    const head = mk('Head', neck, 0, 0.096, 0.017);
    mk('HeadTop_End', head, 0, 0.178, 0.026);

    const pelvis = shade(new THREE.Mesh(new THREE.SphereGeometry(0.15, 20, 14), pants));
    pelvis.scale.set(1.1, 0.75, 0.8); hips.add(pelvis);
    const torso = shade(new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.15, 0.42, 20), vest));
    torso.scale.set(1, 1, 0.62); torso.position.y = 0.12; sp1.add(torso);
    [0.02, 0.15].forEach(y => {
      const s = new THREE.Mesh(new THREE.CylinderGeometry(0.167, 0.163, 0.035, 20, 1, true), stripe);
      s.scale.set(1.01, 1, 0.63); s.position.y = y; sp1.add(s);
    });
    const chest = shade(new THREE.Mesh(new THREE.SphereGeometry(0.17, 20, 12), vest));
    chest.scale.set(1.05, 0.55, 0.65); chest.position.y = 0.17; sp2.add(chest);
    const nk = shade(new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.055, 0.12, 12), skin));
    nk.position.y = 0.05; neck.add(nk);
    const hd = shade(new THREE.Mesh(new THREE.SphereGeometry(0.1, 24, 18), skin));
    hd.scale.set(0.92, 1.1, 1); hd.position.set(0, 0.09, 0.015); head.add(hd);
    const nose = new THREE.Mesh(new THREE.ConeGeometry(0.015, 0.04, 8), skin);
    nose.rotation.x = Math.PI / 2; nose.position.set(0, 0.075, 0.112); head.add(nose);
    face(head, 0.01, 10, 10.6);
    head.add(hardHat(0.01));

    [['Left', 1], ['Right', -1]].forEach(([s, k]) => {
      const sh = mk(s + 'Shoulder', sp2, 0.046 * k, 0.109, -0.026);
      const arm = mk(s + 'Arm', sh, 0.106 * k, -0.005, -0.022);
      const fa = mk(s + 'ForeArm', arm, 0.278 * k, 0, 0);
      const hand = mk(s + 'Hand', fa, 0.283 * k, 0, 0);
      mk(s + 'HandMiddle4', hand, 0.17 * k, 0, 0);
      const up = mk(s + 'UpLeg', hips, 0.082 * k, -0.0675, -0.016);
      const leg = mk(s + 'Leg', up, 0, -0.444, 0.003);
      const foot = mk(s + 'Foot', leg, 0, -0.444, -0.03);
      const toe = mk(s + 'ToeBase', foot, 0, -0.087, 0.107);
      mk(s + 'Toe_End', toe, 0, 0, 0.093);
      limb(sh, arm, 0.055, vest);
      limb(arm, fa, 0.05, shirt);
      limb(fa, hand, 0.042, shirt);
      const gl = shade(new THREE.Mesh(new THREE.BoxGeometry(0.15, 0.05, 0.09), glove));
      gl.position.x = 0.07 * k; hand.add(gl);
      limb(up, leg, 0.078, pants);
      limb(leg, foot, 0.062, pants);
      const bt = shade(new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.1, 0.27), boot));
      bt.position.set(0, -0.05, 0.06); foot.add(bt);
    });
    return root;
  }

  function attachRig(root, mode) {
    const bones = {};
    root.traverse(o => {
      if (o.name && o.name.indexOf(RIG) === 0) bones[o.name.slice(RIG.length)] = o;
      if (o.isMesh) { o.castShadow = true; o.frustumCulled = false; }
    });
    if (!bones.Hips || !bones.LeftArm || !bones.RightUpLeg || !bones.Head) return false;
    if (st.rig) st.holder.remove(st.rig);
    st.holder.position.set(0, 0, 0);
    st.holder.add(root);
    st.rig = root;
    st.bones = bones;
    st.mode = mode;
    captureRest();
    st.holder.visible = st.visible;
    return true;
  }

  function bodyPos(o) { return st.holder.worldToLocal(o.getWorldPosition(V())); }
  function bodyQuat(o) {
    const hq = st.holder.getWorldQuaternion(new THREE.Quaternion()).invert();
    return hq.multiply(o.getWorldQuaternion(new THREE.Quaternion()));
  }

  function captureRest() {
    const b = st.bones;
    st.holder.updateMatrixWorld(true);
    const rest = {};
    Object.keys(b).forEach(n => {
      rest[n] = {local: b[n].quaternion.clone(), body: bodyQuat(b[n]), pos: bodyPos(b[n])};
    });
    Object.keys(DRIVEN).forEach(n => {
      rest[n].dir = rest[DRIVEN[n]].pos.clone().sub(rest[n].pos).normalize();
    });
    const P = n => rest[n].pos;
    const sh = P('LeftArm').clone().add(P('RightArm')).multiplyScalar(0.5);
    const hp = P('LeftUpLeg').clone().add(P('RightUpLeg')).multiplyScalar(0.5);
    const up = sh.clone().sub(hp).normalize();
    const lat = P('LeftArm').clone().sub(P('RightArm')).add(P('LeftUpLeg').clone().sub(P('RightUpLeg')));
    rest.basisInv = basis(up, lat).invert();
    st.rest = rest;
    st.dims = {
      torso: sh.distanceTo(hp),
      shW: P('LeftArm').distanceTo(P('RightArm')),
      hipW: P('LeftUpLeg').distanceTo(P('RightUpLeg')),
      upperArm: P('LeftArm').distanceTo(P('LeftForeArm')),
      foreArm: P('LeftForeArm').distanceTo(P('LeftHand')),
      thigh: P('LeftUpLeg').distanceTo(P('LeftLeg')),
      shin: P('LeftLeg').distanceTo(P('LeftFoot'))
    };
  }

  // Orthonormal body frame: x = character's left, y = up (hips -> shoulders), z = facing.
  function basis(up, lat) {
    const y = up.clone().normalize();
    let x = lat.clone().sub(y.clone().multiplyScalar(lat.dot(y)));
    if (x.lengthSq() < 1e-8) {
      const ref = Math.abs(y.x) < 0.9 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 0, -1);
      x = ref.sub(y.clone().multiplyScalar(ref.dot(y)));
    }
    x.normalize();
    const z = new THREE.Vector3().crossVectors(x, y).normalize();
    return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x, y, z));
  }

  function loadModel() {
    if (!THREE.GLTFLoader) { st.error = 'GLTFLoader missing'; return; }
    st.loading = true;
    const loader = new THREE.GLTFLoader();
    const onLoad = gltf => {
      st.loading = false;
      const root = gltf.scene;
      root.traverse(o => {
        if (o.isSkinnedMesh) {
          o.material = dressMaterial(o.material);
          o.castShadow = true; o.receiveShadow = true;
        }
      });
      const tmp = {};
      root.traverse(o => { if (o.name && o.name.indexOf(RIG) === 0) tmp[o.name.slice(RIG.length)] = o; });
      if (tmp.Head) {
        tmp.Head.add(hardHat(1));
        face(tmp.Head, 1, 10.3, 12.1);
      }
      linearize(root);
      if (!attachRig(root, 'gltf')) st.error = 'unexpected skeleton';
    };
    const fromEmbedded = () => {
      const parse = () => {
        try {
          const bin = atob(window.ECHO_WORKER_GLB);
          const buf = new Uint8Array(bin.length);
          for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
          loader.parse(buf.buffer, '', onLoad, e => { st.loading = false; st.error = String(e && e.message || e); });
        } catch (e) { st.loading = false; st.error = e.message; }
      };
      if (window.ECHO_WORKER_GLB) return parse();
      const s = document.createElement('script');
      s.src = MODEL_JS;
      s.onload = parse;
      s.onerror = () => { st.loading = false; st.error = 'model not found'; };
      document.head.appendChild(s);
    };
    if (location.protocol === 'file:') fromEmbedded();
    else loader.load(MODEL_URL, onLoad, undefined, fromEmbedded);
  }

  // ---------------------------------------------------------------- pose
  // Keypoints -> body-space 3D points in metres (origin at hip midpoint, y up, z to camera).
  function lift(kps, aspect, world) {
    const ok = i => kps[i] && kps[i][2] > VIS;
    if (![5, 6, 11, 12].every(ok)) return null;
    const P = [], D = st.dims;
    let side = false;
    if (world && world.length >= 17) {
      for (let i = 0; i < 17; i++) P[i] = new THREE.Vector3(world[i][0], -world[i][1], -world[i][2]);
      const hm = P[11].clone().add(P[12]).multiplyScalar(0.5);
      P.forEach(p => p.sub(hm));
    } else {
      const img = kps.map(k => new THREE.Vector3((k[0] - 0.5) * aspect, 0.5 - k[1], 0));
      const hm = img[11].clone().add(img[12]).multiplyScalar(0.5);
      const sm = img[5].clone().add(img[6]).multiplyScalar(0.5);
      const shW = img[5].distanceTo(img[6]), hipW = img[11].distanceTo(img[12]);
      // Image units per metre from the least foreshortened segment (widths are only a fallback:
      // detector shoulder/hip points sit wider than the skeleton's joint centres).
      const seg = (a, b, key) => ok(a) && ok(b) ? img[a].distanceTo(img[b]) / D[key] : 0;
      const u = Math.max(sm.distanceTo(hm) / D.torso,
        seg(11, 13, 'thigh'), seg(12, 14, 'thigh'), seg(13, 15, 'shin'), seg(14, 16, 'shin'),
        seg(5, 7, 'upperArm'), seg(6, 8, 'upperArm'), seg(7, 9, 'foreArm'), seg(8, 10, 'foreArm'),
        0.6 * shW / D.shW, 0.6 * hipW / D.hipW, 1e-4);
      side = shW / u < 0.4 * D.shW && hipW / u < 0.45 * D.hipW;
      for (let i = 0; i < 17; i++) P[i] = img[i].clone().sub(hm).divideScalar(u);
      P.hipX = hm.x / u;
      // Recover depth lost in projection: a limb shorter than its true length points at the camera.
      // Small shortening is treated as noise (keypoint jitter, body proportions).
      const depth = (l, L) => L * Math.sqrt(Math.max(0, 1 - Math.pow(l / (0.88 * L), 2)));
      const torso2 = P[5].clone().add(P[6]).multiplyScalar(0.5).length();
      const dzT = depth(torso2, D.torso);
      [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10].forEach(i => { P[i].z += dzT; });
      CHAIN.forEach(([a, b, key]) => {
        if (!ok(a) || !ok(b)) return;
        let dz = depth(Math.hypot(P[b].x - P[a].x, P[b].y - P[a].y), D[key]);
        // Feet stay under the body: a shin runs from a forward knee back down to the ankle.
        if (key === 'shin' && P[a].z > 0) dz = -Math.min(dz, P[a].z);
        const extra = P[a].z + dz - P[b].z;
        if (b === 7 || b === 8 || b === 13 || b === 14) {
          const kids = b === 7 ? [9] : b === 8 ? [10] : b === 13 ? [15] : [16];
          kids.forEach(k => { P[k].z += extra; });
        }
        P[b].z += extra;
      });
    }
    const sm = P[5].clone().add(P[6]).multiplyScalar(0.5);
    const hm = P[11].clone().add(P[12]).multiplyScalar(0.5);
    const up = sm.clone().sub(hm);
    let lat = P[5].clone().sub(P[6]).add(P[11].clone().sub(P[12]));
    if (side && Math.abs(up.clone().normalize().x) < 0.9) {
      const head = ok(0) ? P[0] : sm;
      const dx = (head.x - sm.x) || (sm.x - hm.x) || 1;
      lat = new THREE.Vector3().crossVectors(up, new THREE.Vector3(Math.sign(dx), 0, 0));
    }
    const ears = ok(3) && ok(4) ? P[3].clone().add(P[4]).multiplyScalar(0.5) : null;
    P.neck = sm;
    P.head = ears || (ok(0) ? P[0] : sm.clone().add(up.clone().normalize().multiplyScalar(0.25)));
    P.up = up; P.lat = lat; P.ok = ok;
    return P;
  }

  const tmpQ = new THREE.Quaternion();
  function setBodyQuat(bone, q, alpha) {
    const parentQ = bodyQuat(bone.parent).invert();
    const local = parentQ.multiply(q);
    bone.quaternion.slerp(local, alpha);
    bone.updateMatrixWorld(true);
  }
  function relax(bone, alpha) {
    bone.quaternion.slerp(st.rest[bone.name.slice(RIG.length)].local, alpha);
    bone.updateMatrixWorld(true);
  }

  function pose(P) {
    const b = st.bones, R = st.rest, a = 0.45;
    st.holder.updateMatrixWorld(true);
    const Qb = basis(P.up, P.lat);
    const hipsQ = Qb.clone().multiply(R.basisInv).multiply(R.Hips.body);
    setBodyQuat(b.Hips, hipsQ, a);
    ['Spine', 'Spine1', 'Spine2', 'Head', 'LeftShoulder', 'RightShoulder', 'LeftHand', 'RightHand'].forEach(n => b[n] && relax(b[n], a));
    Object.keys(TARGET).forEach(n => {
      const [f, t] = TARGET[n];
      const okF = typeof f === 'string' || P.ok(f), okT = typeof t === 'string' || P.ok(t);
      if (!okF || !okT) { relax(b[n], 0.15); return; }
      const dir = P[t].clone().sub(P[f]);
      if (dir.lengthSq() < 1e-8) return;
      tmpQ.setFromUnitVectors(R[n].dir, dir.normalize());
      setBodyQuat(b[n], tmpQ.clone().multiply(R[n].body), a);
    });
    // Keep feet flat on the floor while upright; let them follow the shins when lying down.
    const upright = P.up.clone().normalize().y > 0.5;
    const fwd = new THREE.Vector3(0, 0, 1).applyQuaternion(Qb);
    const yaw = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.atan2(fwd.x, fwd.z));
    ['LeftFoot', 'RightFoot'].forEach(n => {
      if (!b[n]) return;
      if (upright) setBodyQuat(b[n], yaw.clone().multiply(R[n].body), a);
      else relax(b[n], a);
    });
    // Grounding: lowest body point rests on the floor.
    st.holder.updateMatrixWorld(true);
    const probes = [['LeftToe_End', 0], ['RightToe_End', 0], ['LeftFoot', 0.08], ['RightFoot', 0.08],
      ['LeftHand', 0.04], ['RightHand', 0.04], ['Head', 0.1], ['HeadTop_End', 0.05], ['Hips', 0.11],
      ['LeftLeg', 0.06], ['RightLeg', 0.06], ['LeftForeArm', 0.05], ['RightForeArm', 0.05], ['Spine2', 0.13]];
    let minY = Infinity;
    probes.forEach(([n, r]) => { if (b[n]) minY = Math.min(minY, b[n].getWorldPosition(V()).y - r); });
    if (isFinite(minY)) st.holder.position.y += (0 - minY) * (st.visible ? 0.5 : 1);
    const tx = Math.max(-1, Math.min(1, P.hipX || 0));
    st.holder.position.x += (tx - st.holder.position.x) * 0.3;
  }

  function update(person, aspect) {
    if (!st.ok || !st.bones) return;
    const kps = person && person.keypoints;
    const P = kps && kps.length >= 17 ? lift(kps, aspect || 4 / 3, person.world) : null;
    if (!P) {
      st.visible = false;
      st.holder.visible = false;
      return;
    }
    const wasHidden = !st.visible;
    st.visible = true;
    st.holder.visible = true;
    if (wasHidden) for (let i = 0; i < 6; i++) pose(P);
    else pose(P);
    st.lastPose = performance.now();
  }

  // ---------------------------------------------------------------- status visuals
  function setLevel(level) {
    if (!LEVEL_HEX[level]) level = 'SAFE';
    if (level === st.level) return;
    st.level = level;
    const c = lin(LEVEL_HEX[level]);
    st.uniforms.uGlow.value.copy(c);
    const fx = st.fx;
    if (!fx.lamp) return;
    fx.lamp.material.color.copy(c); fx.lamp.material.emissive.copy(c);
    fx.lampLight.color.copy(c);
    fx.ring.material.color.copy(c);
    fx.beams.forEach(bm => bm.beam.material.color.copy(c));
    if (fx.procStripe) fx.procStripe.emissive.copy(c);
  }

  function setEnv(names) { st.env = names || []; }

  function render() {
    if (!st.ok) return;
    const dt = Math.min(st.clock.getDelta(), 0.1), t = st.clock.elapsedTime, fx = st.fx;
    const alarm = st.level !== 'SAFE';
    const pulse = 0.5 + 0.5 * Math.sin(t * (alarm ? 9 : 2));
    fx.lamp.material.emissiveIntensity = alarm ? 0.6 + 2 * pulse : 1.2;
    fx.lampLight.intensity = alarm ? 0.4 + 1.6 * pulse : 0.5;
    fx.ring.material.opacity = 0.35 + 0.45 * pulse;
    fx.ring.scale.setScalar(1 + (alarm ? 0.08 * pulse : 0.02 * pulse));
    fx.ring.position.x = st.holder.position.x;
    st.uniforms.uGlow.value.copy(lin(LEVEL_HEX[st.level])).multiplyScalar(alarm ? 0.4 + 0.8 * pulse : 0.6);
    const chest = st.bones && st.bones.Spine2 && st.visible ? st.bones.Spine2.getWorldPosition(V()) : null;
    fx.beams.forEach(bm => {
      if (!chest) { bm.beam.visible = false; return; }
      const d = chest.clone().sub(bm.from), L = d.length();
      bm.beam.visible = true;
      bm.beam.scale.set(1, L, 1);
      bm.beam.position.copy(bm.from).add(chest).multiplyScalar(0.5);
      bm.beam.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize());
      bm.beam.material.opacity = 0.15 + 0.3 * pulse;
    });
    const has = n => st.env.indexOf(n) >= 0;
    const dusty = has('DUST') || has('SMOKE');
    fx.dust.visible = dusty;
    if (dusty) fx.dust.rotation.y += dt * 0.05;
    st.scene.fog.near = dusty ? 1.5 : 7;
    st.scene.fog.far = dusty ? 8 : 18;
    const dark = has('DARK');
    fx.lights.key.intensity = dark ? 0.25 : 1.6;
    fx.lights.hemi.intensity = dark ? 0.12 : 0.75;
    const fire = has('FIRE');
    fx.flame.visible = fire;
    fx.fire.intensity = fire ? 2.2 + Math.random() * 1.2 : 0;
    if (fire) fx.flame.scale.set(1, 0.85 + Math.random() * 0.3, 1);
    if (st.ctl) st.ctl.update();
    st.rnd.render(st.scene, st.cam);
  }

  function resize() {
    if (!st.ok || !st.el) return;
    const W = st.el.clientWidth, H = st.el.clientHeight;
    if (!W || !H) return;
    st.cam.aspect = W / H;
    st.cam.updateProjectionMatrix();
    st.rnd.setSize(W, H);
  }

  function info() {
    return {ok: st.ok, mode: st.mode, loading: st.loading, error: st.error, visible: st.visible, level: st.level};
  }

  window.Human3D = {init, update, setLevel, setEnv, render, resize, info};
})();
