/**
 * E99 World Portal — Real-Time Navigation Controller
 *
 * 3D mode: Builds a live world map from tour.json.
 *   - Drone path rendered as a glowing tube
 *   - Each viewpoint is a glowing sphere with a floating panorama thumbnail
 *   - Click any viewpoint to jump into its 360° photo sphere
 *   - Orbit, fly, and cinematic tour modes
 *
 * 360° mode: Pannellum photo sphere viewer.
 *   - Configured with per-scene haov/vaov so partial panoramas fill the screen
 *   - Hotspot navigation between connected viewpoints
 *   - Back-to-map button returns to 3D world
 *
 * Live updates: polls /api/status every 3 s during pipeline runs,
 *   adding new viewpoints to both views without a page reload.
 */

// ── Global state ──────────────────────────────────────────────────────────────
let activePortalMode = 'three';
let scene, camera, renderer, controls;
let mainMeshGroup = null;
let viewpointObjects = [];   // THREE.Group[] with userData.sceneId — raycasted
let billboardGroups = [];    // same groups, rotated toward camera each frame
let isFlyMode = false;
const keys = { w: false, a: false, s: false, d: false, q: false, e: false };
let mouseLook = { drag: false, prevX: 0, prevY: 0, yaw: 0, pitch: 0 };
const FLY_SPEED = 0.08;

let isCinematicTouring = false;
let activeTween = null;

let tourConfig = null;
let metaData = null;
let pannellumViewer = null;
let currentPanoIdx = 0;
let sceneOrderList = [];
let knownViewpointIds = new Set();
let lastTourMtime = 0;

let raycaster, mouse;

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', boot);

async function boot() {
    updateLoading(5, 'Connecting to server...');
    tourConfig = await fetchTourConfig();
    metaData   = tourConfig._meta || {};
    sceneOrderList = metaData.scene_order || Object.keys(tourConfig.scenes || {});

    updateLoading(25, 'Initialising 3D engine...');
    setupThree();

    updateLoading(45, 'Building world map...');
    await buildWorld();

    updateLoading(78, 'Initialising 360° viewer...');
    if (sceneOrderList.length > 0) initPannellum();

    updateLoading(92, 'Wiring controls...');
    setupInterface();
    setupRaycast();

    updateLoading(100, 'Ready.');
    setTimeout(() => {
        const ldr = document.getElementById('loading-screen');
        if (ldr) {
            ldr.classList.add('fade-out');
            ldr.style.pointerEvents = 'none';
            setTimeout(() => ldr.style.display = 'none', 600);
        }
        onResize();
    }, 350);

    pollLiveUpdates();
}

// ── Tour config fetch ─────────────────────────────────────────────────────────
async function fetchTourConfig() {
    try {
        const r = await fetch('/api/tour');
        if (!r.ok) throw new Error(r.status);
        return await r.json();
    } catch {
        return { scenes: {}, _meta: { positions: {}, scene_order: [], connections: [] } };
    }
}

// ── Three.js setup ────────────────────────────────────────────────────────────
function setupThree() {
    const container = document.getElementById('three-viewer');

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x080812);
    scene.fog = new THREE.FogExp2(0x080812, 0.035);

    camera = new THREE.PerspectiveCamera(52, innerWidth / innerHeight, 0.05, 500);
    camera.position.set(0, 8, 12);

    renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    renderer.setSize(innerWidth, innerHeight);
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.outputEncoding = THREE.sRGBEncoding;
    container.appendChild(renderer.domElement);

    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.maxPolarAngle = Math.PI * 0.88;
    controls.minDistance = 1;
    controls.maxDistance = 60;

    // Lighting
    scene.add(new THREE.AmbientLight(0x9090cc, 0.55));
    const sun = new THREE.DirectionalLight(0xffffff, 0.9);
    sun.position.set(6, 14, 6);
    sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024);
    scene.add(sun);
    scene.add(Object.assign(new THREE.DirectionalLight(0x6366f1, 0.35), {
        position: new THREE.Vector3(-8, 6, -8)
    }));

    mainMeshGroup = new THREE.Group();
    scene.add(mainMeshGroup);

    raycaster = new THREE.Raycaster();
    mouse     = new THREE.Vector2();

    window.addEventListener('resize', onResize);
    renderer.setAnimationLoop(renderFrame);
}

// ── Build 3D world from tour.json ─────────────────────────────────────────────
async function buildWorld() {
    const positions  = metaData.positions  || {};
    const sceneOrder = metaData.scene_order || sceneOrderList;

    if (sceneOrder.length === 0) {
        addWaitingRing();
        document.getElementById('scene-counter').textContent = 'Awaiting pipeline...';
        return;
    }

    // Map minimap coords (0–100) → world units (roughly –9 to +9)
    const wp = {};
    for (const [id, pos] of Object.entries(positions)) {
        const [mx, my] = Array.isArray(pos) ? pos : [50, 50];
        wp[id] = new THREE.Vector3((mx - 50) * 0.18, 0, (my - 50) * 0.18);
    }

    // Ground
    const ground = new THREE.Mesh(
        new THREE.PlaneGeometry(35, 35),
        new THREE.MeshStandardMaterial({ color: 0x0b0b18, roughness: 1 })
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.02;
    ground.receiveShadow = true;
    mainMeshGroup.add(ground);
    mainMeshGroup.add(new THREE.GridHelper(30, 60, 0x18183a, 0x101020));

    // Path tube
    const pathPts = sceneOrder.filter(id => wp[id]).map(id => wp[id].clone().setY(0.03));
    if (pathPts.length >= 2) {
        const curve = new THREE.CatmullRomCurve3(pathPts, false, 'centripetal');
        const segs  = Math.max(60, pathPts.length * 8);
        mainMeshGroup.add(new THREE.Mesh(
            new THREE.TubeGeometry(curve, segs, 0.045, 8, false),
            new THREE.MeshBasicMaterial({ color: 0x4338ca, transparent: true, opacity: 0.75 })
        ));
        // Soft glow halo around path
        mainMeshGroup.add(new THREE.Mesh(
            new THREE.TubeGeometry(curve, segs, 0.14, 8, false),
            new THREE.MeshBasicMaterial({ color: 0x6366f1, transparent: true, opacity: 0.07 })
        ));
    }

    // Viewpoint markers
    const tex  = new THREE.TextureLoader();
    const sGeo = new THREE.SphereGeometry(0.19, 24, 24);
    for (let i = 0; i < sceneOrder.length; i++) {
        const id  = sceneOrder[i];
        const pos = wp[id];
        if (!pos) continue;
        spawnViewpoint(id, pos, i, tex, sGeo);
        knownViewpointIds.add(id);
    }

    // Frame camera over scene
    if (pathPts.length > 0) {
        const box  = new THREE.Box3();
        pathPts.forEach(p => box.expandByPoint(p));
        const ctr  = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const span = Math.max(size.x, size.z, 4);
        camera.position.set(ctr.x + span * 0.2, span * 0.75, ctr.z + span * 1.05);
        controls.target.set(ctr.x, 0, ctr.z);
        controls.update();
    }

    drawMinimap();
    document.getElementById('scene-counter').textContent = `${sceneOrder.length} viewpoints`;
    document.getElementById('hud-mode-badge').textContent = '3D World Map';
}

// ── Spawn one viewpoint marker ────────────────────────────────────────────────
function spawnViewpoint(id, pos, index, texLoader, sGeo) {
    texLoader = texLoader || new THREE.TextureLoader();
    sGeo      = sGeo      || new THREE.SphereGeometry(0.19, 24, 24);

    const group = new THREE.Group();
    group.position.copy(pos).setY(0.19);
    group.userData = { sceneId: id, viewpointIndex: index };

    // Glowing sphere
    const isStart = index === 0;
    const sphere  = new THREE.Mesh(sGeo.clone(), new THREE.MeshStandardMaterial({
        color:             isStart ? 0x34d399 : 0x6366f1,
        emissive:          isStart ? 0x0c3320 : 0x1a1a55,
        emissiveIntensity: 0.65,
        roughness:         0.15,
        metalness:         0.4,
    }));
    sphere.castShadow = true;
    group.add(sphere);

    // Floating panorama thumbnail
    const panoUrl = `/panoramas/${id}.jpg`;
    texLoader.load(panoUrl,
        (tex) => {
            // Border frame
            const border = new THREE.Mesh(
                new THREE.PlaneGeometry(1.06, 0.56),
                new THREE.MeshBasicMaterial({ color: 0x6366f1, side: THREE.DoubleSide, transparent: true, opacity: 0.85 })
            );
            border.position.y = 0.75;
            group.add(border);

            // Image plane
            const img = new THREE.Mesh(
                new THREE.PlaneGeometry(1.0, 0.5),
                new THREE.MeshBasicMaterial({ map: tex, side: THREE.DoubleSide })
            );
            img.position.y = 0.75;
            img.position.z = 0.003;
            group.add(img);
        },
        undefined,
        () => {
            // Placeholder when panorama not yet ready
            const ph = new THREE.Mesh(
                new THREE.PlaneGeometry(1.0, 0.5),
                new THREE.MeshBasicMaterial({ color: 0x1c1c3a, side: THREE.DoubleSide, transparent: true, opacity: 0.6 })
            );
            ph.position.y = 0.75;
            group.add(ph);
        }
    );

    mainMeshGroup.add(group);
    viewpointObjects.push(group);
    billboardGroups.push(group);
}

function addWaitingRing() {
    mainMeshGroup.add(new THREE.GridHelper(20, 40, 0x18183a, 0x101020));
    const ring = new THREE.Mesh(
        new THREE.TorusGeometry(2.0, 0.045, 8, 60),
        new THREE.MeshBasicMaterial({ color: 0x6366f1, transparent: true, opacity: 0.4 })
    );
    ring.rotation.x = -Math.PI / 2;
    ring.userData.spinRing = true;
    mainMeshGroup.add(ring);
}

// ── Render loop ───────────────────────────────────────────────────────────────
function renderFrame() {
    if (activePortalMode !== 'three') return;
    if (typeof TWEEN !== 'undefined') TWEEN.update();

    // Billboard: rotate each viewpoint group to face camera around Y axis only
    if (billboardGroups.length > 0) {
        billboardGroups.forEach(g => {
            g.rotation.y = Math.atan2(
                camera.position.x - g.position.x,
                camera.position.z - g.position.z
            );
        });
    }

    // Spin waiting ring
    mainMeshGroup.children.forEach(c => {
        if (c.userData.spinRing) c.rotation.z += 0.004;
    });

    if (isFlyMode && !isCinematicTouring) {
        const fwd = new THREE.Vector3();
        camera.getWorldDirection(fwd);
        fwd.y = 0; fwd.normalize();
        const right = new THREE.Vector3(-fwd.z, 0, fwd.x);
        if (keys.w) camera.position.addScaledVector(fwd,   FLY_SPEED);
        if (keys.s) camera.position.addScaledVector(fwd,  -FLY_SPEED);
        if (keys.a) camera.position.addScaledVector(right, -FLY_SPEED);
        if (keys.d) camera.position.addScaledVector(right,  FLY_SPEED);
        if (keys.q) camera.position.y -= FLY_SPEED * 0.6;
        if (keys.e) camera.position.y += FLY_SPEED * 0.6;
        controls.target.copy(camera.position).addScaledVector(
            camera.getWorldDirection(new THREE.Vector3()), 1.0
        );
    } else if (!isCinematicTouring) {
        controls.update();
    }

    renderer.render(scene, camera);
}

// ── Raycasting — click viewpoint → enter panorama ─────────────────────────────
function setupRaycast() {
    renderer.domElement.addEventListener('click', e => {
        if (isFlyMode || isCinematicTouring || activePortalMode !== 'three') return;
        mouse.x =  (e.clientX / innerWidth)  * 2 - 1;
        mouse.y = -(e.clientY / innerHeight) * 2 + 1;
        raycaster.setFromCamera(mouse, camera);
        const hits = raycaster.intersectObjects(viewpointObjects, true);
        if (!hits.length) return;
        let obj = hits[0].object;
        while (obj && !obj.userData?.sceneId) obj = obj.parent;
        if (obj?.userData?.sceneId) enterPano(obj.userData.sceneId);
    });

    renderer.domElement.addEventListener('mousemove', e => {
        if (activePortalMode !== 'three') return;
        mouse.x =  (e.clientX / innerWidth)  * 2 - 1;
        mouse.y = -(e.clientY / innerHeight) * 2 + 1;
        raycaster.setFromCamera(mouse, camera);
        const hits = raycaster.intersectObjects(viewpointObjects, true);
        renderer.domElement.style.cursor = (hits.length && !isFlyMode) ? 'pointer' : '';
    });
}

function enterPano(sceneId) {
    const idx = sceneOrderList.indexOf(sceneId);
    if (idx >= 0) currentPanoIdx = idx;
    switchMode('pano');
    if (pannellumViewer) pannellumViewer.loadScene(sceneId);
}

// ── Pannellum 360° viewer ─────────────────────────────────────────────────────
function initPannellum() {
    if (!tourConfig?.scenes || !Object.keys(tourConfig.scenes).length) return;
    const firstScene = sceneOrderList[0] || Object.keys(tourConfig.scenes)[0];

    try {
        if (pannellumViewer) { try { pannellumViewer.destroy(); } catch {} pannellumViewer = null; }

        pannellumViewer = pannellum.viewer('panorama-viewer', {
            default: {
                firstScene,
                sceneFadeDuration: 700,
                autoLoad: true,
                compass: true,
                autoRotate: -1.5,
                autoRotateInactivityDelay: 3000,
            },
            scenes: tourConfig.scenes,
        });

        pannellumViewer.on('scenechange', scId => {
            currentPanoIdx = Math.max(0, sceneOrderList.indexOf(scId));
            updatePanoUI(scId);
            drawMinimap();
        });

        document.getElementById('btn-prev').onclick = () => {
            if (currentPanoIdx > 0) pannellumViewer.loadScene(sceneOrderList[--currentPanoIdx]);
        };
        document.getElementById('btn-next').onclick = () => {
            if (currentPanoIdx < sceneOrderList.length - 1)
                pannellumViewer.loadScene(sceneOrderList[++currentPanoIdx]);
        };

        let autoRunning = false, autoTimer = null;
        document.getElementById('btn-auto-tour').onclick = () => {
            autoRunning = !autoRunning;
            const btn = document.getElementById('btn-auto-tour');
            btn.classList.toggle('active', autoRunning);
            btn.textContent = autoRunning ? '⏹ Stop Tour' : '▶ Auto Tour';
            if (autoRunning) {
                const step = () => {
                    if (!autoRunning) return;
                    currentPanoIdx = (currentPanoIdx + 1) % sceneOrderList.length;
                    pannellumViewer.loadScene(sceneOrderList[currentPanoIdx]);
                    autoTimer = setTimeout(step, metaData?.auto_tour_delay || 4000);
                };
                step();
            } else {
                clearTimeout(autoTimer);
            }
        };

        document.getElementById('btn-back-map')?.addEventListener('click', () => switchMode('three'));
    } catch (err) {
        console.warn('Pannellum init error:', err);
    }
}

// ── Live polling ──────────────────────────────────────────────────────────────
async function pollLiveUpdates() {
    const check = async () => {
        try {
            const r = await fetch('/api/status');
            if (!r.ok) return;
            const status = await r.json();

            const newIds = (status.ready_viewpoints || []).filter(id => !knownViewpointIds.has(id));
            const tourChanged = status.tour_mtime && status.tour_mtime !== lastTourMtime;

            if (newIds.length || tourChanged) {
                const fresh = await fetchTourConfig();
                tourConfig     = fresh;
                metaData       = fresh._meta || {};
                sceneOrderList = metaData.scene_order || Object.keys(fresh.scenes || {});
                if (status.tour_mtime) lastTourMtime = status.tour_mtime;

                const positions = metaData.positions || {};
                const tex = new THREE.TextureLoader();
                for (const id of newIds) {
                    const pos = positions[id];
                    if (!pos) continue;
                    const [mx, my] = pos;
                    const idx = sceneOrderList.indexOf(id);
                    spawnViewpoint(
                        id,
                        new THREE.Vector3((mx - 50) * 0.18, 0, (my - 50) * 0.18),
                        idx >= 0 ? idx : sceneOrderList.length,
                        tex
                    );
                    knownViewpointIds.add(id);
                }

                if (Object.keys(tourConfig.scenes || {}).length > 0) initPannellum();
                drawMinimap();
                flashLiveBadge();

                const count = sceneOrderList.length;
                document.getElementById('scene-counter').textContent =
                    activePortalMode === 'three' ? `${count} viewpoints` :
                    `${currentPanoIdx + 1} / ${count}`;
            }

            // Processing stage indicator
            const pipe = status.pipeline || {};
            const busy = pipe.stage && pipe.stage !== 'done';
            const ind  = document.getElementById('processing-indicator');
            if (ind) {
                ind.classList.toggle('hidden', !busy);
                const lbl = ind.querySelector('.proc-label');
                if (lbl) lbl.textContent = pipe.stage ? pipe.stage.replace(/_/g, ' ') : '';
            }
        } catch { /* silent — server may be starting up */ }

        setTimeout(check, 3000);
    };
    check();
}

function flashLiveBadge() {
    const b = document.getElementById('live-badge');
    if (!b) return;
    b.classList.add('visible');
    setTimeout(() => b.classList.remove('visible'), 2800);
}

// ── Minimap ───────────────────────────────────────────────────────────────────
function drawMinimap() {
    const svg = document.getElementById('minimap-svg');
    if (!svg) return;
    const positions = metaData?.positions || {};
    const order     = metaData?.scene_order || sceneOrderList;

    if (!order.length) {
        svg.innerHTML = '<text x="50" y="54" text-anchor="middle" fill="rgba(99,102,241,0.4)" font-size="7" font-family="sans-serif">No data</text>';
        return;
    }

    svg.innerHTML = '';
    const pts = order.map(id => positions[id]).filter(Boolean);

    // Path line
    if (pts.length >= 2) {
        const d = pts.map((p, i) => `${i ? 'L' : 'M'} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
        svg.innerHTML += `<path d="${d}" stroke="#4338ca" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`;
    }

    // Dots
    for (let i = 0; i < order.length; i++) {
        const p = positions[order[i]];
        if (!p) continue;
        const isCur = activePortalMode === 'pano' && i === currentPanoIdx;
        svg.innerHTML += `<circle cx="${p[0]}" cy="${p[1]}" r="${isCur ? 5 : 2.8}" fill="${i === 0 ? '#34d399' : '#6366f1'}" opacity="${isCur ? 1 : 0.85}"/>`;
    }

    // Pulse ring on current pano position
    if (activePortalMode === 'pano') {
        const p = positions[order[currentPanoIdx]];
        if (p) svg.innerHTML +=
            `<circle cx="${p[0]}" cy="${p[1]}" r="5" fill="none" stroke="#34d399" stroke-width="1.2">
               <animate attributeName="r" values="5;9;5" dur="1.8s" repeatCount="indefinite"/>
               <animate attributeName="opacity" values="0.9;0.1;0.9" dur="1.8s" repeatCount="indefinite"/>
             </circle>`;
    }
}

// ── Mode switcher ─────────────────────────────────────────────────────────────
function switchMode(mode) {
    if (activePortalMode === mode) return;
    activePortalMode = mode;
    const is3 = mode === 'three';

    document.getElementById('tab-three').classList.toggle('active', is3);
    document.getElementById('tab-pano').classList.toggle('active', !is3);
    document.getElementById('three-viewer').style.visibility = is3 ? 'visible' : 'hidden';
    const panoDom = document.getElementById('panorama-viewer');
    panoDom.style.visibility = is3 ? 'hidden' : 'visible';
    panoDom.style.pointerEvents = is3 ? 'none' : 'auto';
    document.getElementById('three-controls').classList.toggle('hidden', !is3);
    document.getElementById('pano-controls').classList.toggle('hidden', is3);
    document.getElementById('help-three-orbit').classList.toggle('hidden', !is3 || isFlyMode);
    document.getElementById('help-three-fly').classList.toggle('hidden', !is3 || !isFlyMode);
    document.getElementById('help-pano').classList.toggle('hidden', is3);
    document.getElementById('hud-mode-badge').textContent = is3 ? '3D World Map' : '360° Street View';

    if (!is3 && pannellumViewer) {
        setTimeout(() => pannellumViewer.resize(), 80);
        updatePanoUI(sceneOrderList[currentPanoIdx]);
    } else {
        document.getElementById('scene-counter').textContent = `${sceneOrderList.length} viewpoints`;
    }
    drawMinimap();
}

// ── Controls setup ────────────────────────────────────────────────────────────
function setupInterface() {
    document.getElementById('tab-three').addEventListener('click', () => switchMode('three'));
    document.getElementById('tab-pano').addEventListener('click', () => switchMode('pano'));
    document.getElementById('btn-mode-orbit').addEventListener('click', () => setNav(false));
    document.getElementById('btn-mode-fly').addEventListener('click', () => setNav(true));
    document.getElementById('btn-shade-mesh').addEventListener('click', () => setShading('solid'));
    document.getElementById('btn-shade-wire').addEventListener('click', () => setShading('wire'));
    document.getElementById('btn-cinematic').addEventListener('click', toggleCinematic);

    window.addEventListener('keydown', e => { const k = e.key.toLowerCase(); if (k in keys) keys[k] = true; });
    window.addEventListener('keyup',   e => { const k = e.key.toLowerCase(); if (k in keys) keys[k] = false; });

    const dom = renderer.domElement;
    dom.addEventListener('mousedown', e => {
        if (isFlyMode) { mouseLook.drag = true; mouseLook.prevX = e.clientX; mouseLook.prevY = e.clientY; }
    });
    window.addEventListener('mouseup', () => { mouseLook.drag = false; });
    dom.addEventListener('mousemove', e => {
        if (!isFlyMode || !mouseLook.drag || isCinematicTouring) return;
        const dx = e.clientX - mouseLook.prevX, dy = e.clientY - mouseLook.prevY;
        mouseLook.prevX = e.clientX; mouseLook.prevY = e.clientY;
        mouseLook.yaw  -= dx * 0.003;
        mouseLook.pitch = Math.max(-Math.PI / 2.1, Math.min(Math.PI / 2.1, mouseLook.pitch - dy * 0.003));
        const dir = new THREE.Vector3(
            Math.cos(mouseLook.pitch) * Math.sin(mouseLook.yaw),
            Math.sin(mouseLook.pitch),
            Math.cos(mouseLook.pitch) * Math.cos(mouseLook.yaw)
        );
        controls.target.copy(camera.position).add(dir);
        camera.lookAt(controls.target);
    });
}

function setNav(fly) {
    isFlyMode = fly;
    document.getElementById('btn-mode-orbit').classList.toggle('active', !fly);
    document.getElementById('btn-mode-fly').classList.toggle('active', fly);
    document.getElementById('help-three-orbit').classList.toggle('hidden', fly);
    document.getElementById('help-three-fly').classList.toggle('hidden', !fly);
    if (fly) {
        controls.enabled = false;
        const dir = camera.getWorldDirection(new THREE.Vector3());
        mouseLook.yaw   = Math.atan2(dir.x, dir.z);
        mouseLook.pitch = Math.asin(Math.max(-1, Math.min(1, dir.y)));
    } else {
        controls.enabled = true;
        controls.target.copy(camera.position).addScaledVector(camera.getWorldDirection(new THREE.Vector3()), 4);
        controls.update();
    }
}

function setShading(mode) {
    const wire = mode === 'wire';
    document.getElementById('btn-shade-mesh').classList.toggle('active', !wire);
    document.getElementById('btn-shade-wire').classList.toggle('active', wire);
    mainMeshGroup.traverse(c => {
        if (!c.isMesh || c.material?.map) return; // skip textured panorama planes
        if (wire) {
            c.userData._mat = c.material;
            c.material = new THREE.MeshBasicMaterial({ color: 0x6366f1, wireframe: true, transparent: true, opacity: 0.28 });
        } else if (c.userData._mat) {
            c.material = c.userData._mat;
        }
    });
}

// ── Cinematic tour ────────────────────────────────────────────────────────────
function toggleCinematic() {
    isCinematicTouring = !isCinematicTouring;
    const btn = document.getElementById('btn-cinematic');
    btn.classList.toggle('active', isCinematicTouring);
    btn.textContent = isCinematicTouring ? '⏹ Stop Tour' : '🎬 Cinematic Tour';
    if (isCinematicTouring) {
        controls.enabled = false;
        runCinematic();
    } else {
        if (!isFlyMode) controls.enabled = true;
        if (activeTween) activeTween.stop();
    }
}

function runCinematic() {
    const positions = metaData?.positions || {};
    const order     = metaData?.scene_order || sceneOrderList;
    const wpts      = order.filter(id => positions[id]).map(id => {
        const [mx, my] = positions[id];
        return new THREE.Vector3((mx - 50) * 0.18, 1.6, (my - 50) * 0.18);
    });
    if (wpts.length < 2) { toggleCinematic(); return; }

    let step = 0;
    const fly = () => {
        if (!isCinematicTouring) return;
        const nxt  = (step + 1) % wpts.length;
        const look = wpts[(nxt + 1) % wpts.length];
        activeTween = new TWEEN.Tween(camera.position)
            .to({ x: wpts[nxt].x, y: wpts[nxt].y, z: wpts[nxt].z }, 3800)
            .easing(TWEEN.Easing.Sinusoidal.InOut)
            .onUpdate(() => camera.lookAt(look))
            .onComplete(() => { step = nxt; fly(); })
            .start();
    };
    new TWEEN.Tween(camera.position)
        .to({ x: wpts[0].x, y: wpts[0].y, z: wpts[0].z }, 1800)
        .easing(TWEEN.Easing.Cubic.Out)
        .onComplete(fly)
        .start();
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function updatePanoUI(scId) {
    const sc = tourConfig?.scenes?.[scId];
    document.getElementById('scene-counter').textContent =
        `${sc?.title || scId}  (${currentPanoIdx + 1} / ${sceneOrderList.length})`;
}

function onResize() {
    if (camera && renderer) {
        camera.aspect = innerWidth / innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(innerWidth, innerHeight);
    }
    if (pannellumViewer && activePortalMode === 'pano') pannellumViewer.resize();
}

function updateLoading(pct, text) {
    const bar = document.getElementById('loading-progress');
    const lbl = document.getElementById('loading-status');
    if (bar) bar.style.width = pct + '%';
    if (lbl) lbl.textContent = text;
}
