/**
 * E99 Coherent World Portal — Unified 3D Graphics Controller
 * ============================================================
 * Implements a state-of-the-art Three.js rendering environment for the mapped 3D mesh
 * alongside the original Pannellum 360 photo sphere engine. Features smooth orbit/fly navigation,
 * custom lighting arrays, cinematic camera tours, and hybrid mode switching.
 */

// ═══════════════════════════════════════════════════════════════════════
// GLOBAL STATE
// ═══════════════════════════════════════════════════════════════════════

// Portal Modes: 'three' (3D Coherent World) vs 'pano' (360° Photo Spheres)
let activePortalMode = 'three';

// Three.js Core
let scene, camera, renderer, controls;
let mainMeshGroup = null;
let pointCloudGroup = null;
let isFlyMode = false;

// Lighting & Shading Cache
let meshMaterial = null;
let wireframeMaterial = null;

// Navigation States (Fly Mode)
const keysPressed = { w: false, a: false, s: false, d: false, q: false, e: false };
let mouseLook = { isDragging: false, prevX: 0, prevY: 0, yaw: 0, pitch: 0 };
const flySpeed = 0.15;

// Cinematic Tour State
let isCinematicTouring = false;
let tourTween = null;

// Tour Config Cache
let tourConfig = null;
let metaData = null;
let pannellumViewer = null;
let currentPanoIdx = 0;
let sceneOrderList = [];

// ═══════════════════════════════════════════════════════════════════════
// INITIALIZATION PORTAL
// ═══════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', initPortal);

async function initPortal() {
    updateLoading(10, 'Fetching spatial configuration...');

    // 1. Fetch JSON configuration
    try {
        const response = await fetch('/api/tour');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        tourConfig = await response.json();
        metaData = tourConfig._meta || {};
        sceneOrderList = metaData.scene_order || Object.keys(tourConfig.scenes || {});
    } catch (err) {
        console.warn('Could not load tour.json via API, proceeding with default mesh loader.', err);
    }

    updateLoading(30, 'Initializing Three.js Graphics Context...');

    // 2. Setup Three.js Context
    setupThreeEnvironment();

    updateLoading(50, 'Loading Reconstructed 3D Geometry...');

    // 3. Load Main 3D Mesh
    await loadCoherent3DMesh();

    updateLoading(85, 'Initializing Hybrid UI Engines...');

    // 4. Setup Optional Pannellum Engine in Background
    if (tourConfig && tourConfig.scenes && Object.keys(tourConfig.scenes).length > 0) {
        initPannellumViewer();
    } else {
        document.getElementById('tab-pano').style.display = 'none'; // hide if no pano scenes
    }

    // 5. Setup UI Event Listeners
    setupPortalInterface();

    updateLoading(100, 'Environment Ready!');

    // 6. Reveal World
    setTimeout(() => {
        const loader = document.getElementById('loading-screen');
        if (loader) loader.classList.add('fade-out');
        onWindowResize(); // Force perfect sizing
    }, 500);
}

// ═══════════════════════════════════════════════════════════════════════
// THREE.JS ENVIRONMENT SETUP
// ═══════════════════════════════════════════════════════════════════════

function setupThreeEnvironment() {
    const container = document.getElementById('three-viewer');

    // Scene
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0a0a0f);

    // Camera
    camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.set(0, 5, 15);

    // Renderer
    renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.outputEncoding = THREE.sRGBEncoding;
    container.appendChild(renderer.domElement);

    // OrbitControls
    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.maxPolarAngle = Math.PI / 2 + 0.1; // allow looking slightly below horizon

    // Custom Studio Lighting Array
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xffffff, 1.0);
    dirLight1.position.set(10, 20, 10);
    dirLight1.castShadow = true;
    dirLight1.shadow.mapSize.width = 2048;
    dirLight1.shadow.mapSize.height = 2048;
    dirLight1.shadow.bias = -0.0001;
    scene.add(dirLight1);

    // Atmospheric Key Lights for wow aesthetics
    const rimLight = new THREE.DirectionalLight(0x818cf8, 0.8);
    rimLight.position.set(-15, 10, -15);
    scene.add(rimLight);

    const floorGrid = new THREE.GridHelper(50, 50, 0x6366f1, 0x222244);
    floorGrid.position.y = -0.05;
    scene.add(floorGrid);

    // Mesh Group Container
    mainMeshGroup = new THREE.Group();
    scene.add(mainMeshGroup);

    // Window Resize Observer
    window.addEventListener('resize', onWindowResize);

    // Start Frame Loop
    renderer.setAnimationLoop(animateFrame);
}

// ═══════════════════════════════════════════════════════════════════════
// GEOMETRY LOADERS
// ═══════════════════════════════════════════════════════════════════════

function loadCoherent3DMesh() {
    return new Promise((resolve) => {
        const objLoader = new THREE.OBJLoader();

        objLoader.load(
            '/data/output/final_mesh.obj',
            (object) => {
                // Shared materials
                meshMaterial = new THREE.MeshStandardMaterial({
                    color: 0xe0e0e0,
                    roughness: 0.4,
                    metalness: 0.1,
                    side: THREE.DoubleSide
                });

                wireframeMaterial = new THREE.MeshBasicMaterial({
                    color: 0x34d399,
                    wireframe: true,
                    transparent: true,
                    opacity: 0.25
                });

                // Apply materials & shadows
                object.traverse((child) => {
                    if (child.isMesh) {
                        child.material = meshMaterial;
                        child.castShadow = true;
                        child.receiveShadow = true;
                        // Optimize normal shading
                        child.geometry.computeVertexNormals();
                    }
                });

                // Automatically Center and Frame Geometry
                const box = new THREE.Box3().setFromObject(object);
                const center = box.getCenter(new THREE.Vector3());
                const size = box.getSize(new THREE.Vector3());
                const maxDim = Math.max(size.x, size.y, size.z);

                // Offset geometry inside group so its center is exactly at scene origin (0,0,0)
                object.position.x = -center.x;
                object.position.y = -center.y + size.y / 2; // place flat on ground grid
                object.position.z = -center.z;

                mainMeshGroup.add(object);

                // Adjust camera view gracefully to frame the loaded environment
                camera.position.set(0, size.y * 0.8, maxDim * 1.2);
                controls.target.set(0, size.y * 0.3, 0);
                controls.update();

                // Mouse yaw/pitch base cache
                mouseLook.yaw = Math.atan2(-camera.position.x, -camera.position.z);
                mouseLook.pitch = Math.asin(camera.position.y / camera.position.length());

                // Build Minimap
                drawMinimapPath(box);

                updateLoading(70, 'Mesh parsed successfully.');
                resolve(true);
            },
            (xhr) => {
                if (xhr.total > 0) {
                    const percent = Math.round((xhr.loaded / xhr.total) * 100);
                    updateLoading(50 + percent * 0.3, `Downloading 3D Mesh (${percent}%)...`);
                }
            },
            (err) => {
                console.error('Failed to load final_mesh.obj:', err);
                // Try falling back to clean point cloud if OBJ is missing
                loadPointCloudFallback().then(resolve);
            }
        );
    });
}

function loadPointCloudFallback() {
    return new Promise((resolve) => {
        updateLoading(65, 'Trying dense point cloud fallback...');
        const plyLoader = new THREE.PLYLoader();
        plyLoader.load(
            '/data/output/dense_cloud_clean.ply',
            (geometry) => {
                const material = new THREE.PointsMaterial({
                    size: 0.05,
                    vertexColors: geometry.hasAttribute('color'),
                    color: geometry.hasAttribute('color') ? 0xffffff : 0x818cf8
                });
                const points = new THREE.Points(geometry, material);

                // Center points
                geometry.computeBoundingBox();
                const center = geometry.boundingBox.getCenter(new THREE.Vector3());
                points.position.sub(center);

                mainMeshGroup.add(points);
                resolve(true);
            },
            undefined,
            () => {
                // Trigger error screen if all geometry fails
                document.getElementById('loading-screen').classList.add('hidden');
                document.getElementById('error-screen').classList.remove('hidden');
                resolve(false);
            }
        );
    });
}

function togglePointCloudLayer() {
    const btnPts = document.getElementById('btn-shade-pts');
    const isActive = btnPts.classList.toggle('active');

    if (isActive) {
        if (!pointCloudGroup) {
            pointCloudGroup = new THREE.Group();
            scene.add(pointCloudGroup);
            const plyLoader = new THREE.PLYLoader();
            plyLoader.load('/data/output/dense_cloud.ply', (geometry) => {
                const mat = new THREE.PointsMaterial({ size: 0.03, color: 0xfbbf24, transparent: true, opacity: 0.75 });
                const pts = new THREE.Points(geometry, mat);
                // Match parent mesh centering logic
                if (mainMeshGroup && mainMeshGroup.children[0]) {
                    pts.position.copy(mainMeshGroup.children[0].position);
                }
                pointCloudGroup.add(pts);
            });
        } else {
            pointCloudGroup.visible = true;
        }
    } else if (pointCloudGroup) {
        pointCloudGroup.visible = false;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// ANIMATION & CONTROLS FRAME LOOP
// ═══════════════════════════════════════════════════════════════════════

function animateFrame() {
    if (activePortalMode !== 'three') return;

    TWEEN.update();

    if (isFlyMode && !isCinematicTouring) {
        // Compute standard camera direction vectors
        const forward = new THREE.Vector3();
        camera.getWorldDirection(forward);
        forward.y = 0; // lock translation to horizontal plane
        forward.normalize();

        const right = new THREE.Vector3(-forward.z, 0, forward.x);

        // Apply Keyboard Velocities
        if (keysPressed.w) camera.position.addScaledVector(forward, flySpeed);
        if (keysPressed.s) camera.position.addScaledVector(forward, -flySpeed);
        if (keysPressed.a) camera.position.addScaledVector(right, -flySpeed);
        if (keysPressed.d) camera.position.addScaledVector(right, flySpeed);
        if (keysPressed.q) camera.position.y -= flySpeed * 0.8;
        if (keysPressed.e) camera.position.y += flySpeed * 0.8;

        // Keep camera target slightly ahead to maintain look orientation logic
        controls.target.copy(camera.position).addScaledVector(camera.getWorldDirection(new THREE.Vector3()), 1.0);
    } else if (!isCinematicTouring) {
        controls.update();
    }

    renderer.render(scene, camera);
}

// ═══════════════════════════════════════════════════════════════════════
// FIRST-PERSON / ORBIT CONTROLS HANDLING
// ═══════════════════════════════════════════════════════════════════════

function setupPortalInterface() {
    // ── PORTAL MODE TABS ──
    document.getElementById('tab-three').addEventListener('click', () => switchPortalMode('three'));
    document.getElementById('tab-pano').addEventListener('click', () => switchPortalMode('pano'));

    // ── THREE.JS MODE BUTTONS ──
    document.getElementById('btn-mode-orbit').addEventListener('click', () => setNavigationMode(false));
    document.getElementById('btn-mode-fly').addEventListener('click', () => setNavigationMode(true));

    // ── SHADING Toggles ──
    document.getElementById('btn-shade-mesh').addEventListener('click', () => setShadingMode('mesh'));
    document.getElementById('btn-shade-wire').addEventListener('click', () => setShadingMode('wire'));
    document.getElementById('btn-shade-pts').addEventListener('click', togglePointCloudLayer);

    // ── CINEMATIC TOUR ──
    document.getElementById('btn-cinematic').addEventListener('click', toggleCinematicTour);

    // ── KEYBOARD & MOUSE DRAG LOOK (Fly Mode) ──
    window.addEventListener('keydown', (e) => {
        const key = e.key.toLowerCase();
        if (key in keysPressed) keysPressed[key] = true;
    });

    window.addEventListener('keyup', (e) => {
        const key = e.key.toLowerCase();
        if (key in keysPressed) keysPressed[key] = false;
    });

    const domTarget = renderer.domElement;
    domTarget.addEventListener('mousedown', (e) => {
        if (isFlyMode) {
            mouseLook.isDragging = true;
            mouseLook.prevX = e.clientX;
            mouseLook.prevY = e.clientY;
        }
    });

    window.addEventListener('mouseup', () => { mouseLook.isDragging = false; });

    domTarget.addEventListener('mousemove', (e) => {
        if (isFlyMode && mouseLook.isDragging && !isCinematicTouring) {
            const deltaX = e.clientX - mouseLook.prevX;
            const deltaY = e.clientY - mouseLook.prevY;
            mouseLook.prevX = e.clientX;
            mouseLook.prevY = e.clientY;

            mouseLook.yaw -= deltaX * 0.003;
            mouseLook.pitch = Math.max(-Math.PI/2.1, Math.min(Math.PI/2.1, mouseLook.pitch - deltaY * 0.003));

            // Convert spherical angles to Target Vector
            const direction = new THREE.Vector3(
                Math.cos(mouseLook.pitch) * Math.sin(mouseLook.yaw),
                Math.sin(mouseLook.pitch),
                Math.cos(mouseLook.pitch) * Math.cos(mouseLook.yaw)
            );

            controls.target.copy(camera.position).add(direction);
            camera.lookAt(controls.target);
        }
    });
}

function setNavigationMode(enableFly) {
    isFlyMode = enableFly;
    document.getElementById('btn-mode-orbit').classList.toggle('active', !enableFly);
    document.getElementById('btn-mode-fly').classList.toggle('active', enableFly);

    document.getElementById('help-three-orbit').classList.toggle('hidden', enableFly);
    document.getElementById('help-three-fly').classList.toggle('hidden', !enableFly);

    if (enableFly) {
        controls.enabled = false; // detach orbit damping conflicts
        // Sync yaw/pitch cache exactly to camera's forward orientation
        const dir = camera.getWorldDirection(new THREE.Vector3());
        mouseLook.yaw = Math.atan2(dir.x, dir.z);
        mouseLook.pitch = Math.asin(dir.y);
    } else {
        controls.enabled = true;
        // push target slightly forward to reorient orbit bounds nicely
        controls.target.copy(camera.position).addScaledVector(camera.getWorldDirection(new THREE.Vector3()), 5.0);
        controls.update();
    }
}

function setShadingMode(mode) {
    const isWire = mode === 'wire';
    document.getElementById('btn-shade-mesh').classList.toggle('active', !isWire);
    document.getElementById('btn-shade-wire').classList.toggle('active', isWire);

    if (mainMeshGroup) {
        mainMeshGroup.traverse((child) => {
            if (child.isMesh) {
                child.material = isWire ? wireframeMaterial : meshMaterial;
            }
        });
    }
}

// ═══════════════════════════════════════════════════════════════════════
// AUTOMATIC CINEMATIC FLY-THROUGH TOUR
// ═══════════════════════════════════════════════════════════════════════

function toggleCinematicTour() {
    const btnTour = document.getElementById('btn-cinematic');
    isCinematicTouring = !isCinematicTouring;

    if (isCinematicTouring) {
        btnTour.classList.add('active');
        btnTour.textContent = '⏹️ Stop Cinematic';
        controls.enabled = false;
        startCinematicSequence();
    } else {
        btnTour.classList.remove('active');
        btnTour.textContent = '🎬 Cinematic Tour';
        if (!isFlyMode) controls.enabled = true;
        if (tourTween) tourTween.stop();
    }
}

function startCinematicSequence() {
    if (!metaData || !metaData.positions || sceneOrderList.length < 2) {
        alert('Cinematic flight markers not found in tour config. Freely navigate with mouse/keyboard.');
        toggleCinematicTour();
        return;
    }

    // Build cinematic spline waypoints directly mapped from extracted drone camera matrices
    const pts = metaData.positions;
    const waypoints = [];

    // Base offset matching object group adjustment cache
    let groupOffset = new THREE.Vector3(0,0,0);
    if (mainMeshGroup && mainMeshGroup.children[0]) { groupOffset.copy(mainMeshGroup.children[0].position); }

    for (const scId of sceneOrderList) {
        if (pts[scId]) {
            // Apply scale mapping logic to place waypoints perfectly matching the mesh scale coordinate array
            waypoints.push(new THREE.Vector3(
                pts[scId][0] * 0.1 + groupOffset.x,
                2.5, // keep eye height consistently safe
                pts[scId][1] * 0.1 + groupOffset.z
            ));
        }
    }

    if (waypoints.length < 2) return;

    let currentStep = 0;
    const flyToNextWaypoint = () => {
        if (!isCinematicTouring) return;

        const nextIdx = (currentStep + 1) % waypoints.length;
        const targetPos = waypoints[nextIdx];
        
        // Calculate smooth target orientation vector pointing along flight path
        const lookTarget = new THREE.Vector3().copy(targetPos);
        if (waypoints.length > 2) {
            const nextNextIdx = (nextIdx + 1) % waypoints.length;
            lookTarget.lerp(waypoints[nextNextIdx], 0.5);
        }

        const duration = 4000; // 4 seconds per node interpolation
        
        // Tween Position
        tourTween = new TWEEN.Tween(camera.position)
            .to({ x: targetPos.x, y: targetPos.y, z: targetPos.z }, duration)
            .easing(TWEEN.Easing.Quadratic.InOut)
            .onUpdate(() => {
                // Ensure dynamic look logic matches smoothly
                camera.lookAt(lookTarget);
            })
            .onComplete(() => {
                currentStep = nextIdx;
                flyToNextWaypoint();
            })
            .start();
    };

    // Smoothly fly to initial waypoint from current position first
    new TWEEN.Tween(camera.position)
        .to({ x: waypoints[0].x, y: waypoints[0].y, z: waypoints[0].z }, 2000)
        .easing(TWEEN.Easing.Cubic.Out)
        .onComplete(flyToNextWaypoint)
        .start();
}

// ═══════════════════════════════════════════════════════════════════════
// HYBRID VIEW SWITCHER: THREE.JS vs PANNELLUM ENGINE
// ═══════════════════════════════════════════════════════════════════════

function switchPortalMode(targetMode) {
    if (activePortalMode === targetMode) return;
    activePortalMode = targetMode;

    const isThree = targetMode === 'three';
    document.getElementById('tab-three').classList.toggle('active', isThree);
    document.getElementById('tab-pano').classList.toggle('active', !isThree);

    // Canvas visibility
    document.getElementById('three-viewer').style.visibility = isThree ? 'visible' : 'hidden';
    document.getElementById('panorama-viewer').classList.toggle('hidden', isThree);

    // HUD controls arrays
    document.getElementById('three-controls').classList.toggle('hidden', !isThree);
    document.getElementById('pano-controls').classList.toggle('hidden', isThree);

    // Help Guides
    document.getElementById('help-three-orbit').classList.toggle('hidden', !isThree || isFlyMode);
    document.getElementById('help-three-fly').classList.toggle('hidden', !isThree || !isFlyMode);
    document.getElementById('help-pano').classList.toggle('hidden', isThree);

    // Badges
    document.getElementById('hud-mode-badge').textContent = isThree ? '3D Mesh Environment' : '360° Photo Spheres';

    // Refresh Pannellum sizing buffers cleanly on view entry
    if (!isThree && pannellumViewer) {
        setTimeout(() => pannellumViewer.resize(), 50);
        updatePanoStatusUI(sceneOrderList[currentPanoIdx]);
    } else {
        document.getElementById('scene-counter').textContent = 'Live Map';
    }
}

// ═══════════════════════════════════════════════════════════════════════
// ORIGINAL PANNELLUM PHOTO SPHERE INTEGRATION
// ═══════════════════════════════════════════════════════════════════════

function initPannellumViewer() {
    const configObj = {
        default: tourConfig.default || { firstScene: sceneOrderList[0], sceneFadeDuration: 1000 },
        scenes: tourConfig.scenes
    };

    try {
        pannellumViewer = pannellum.viewer('panorama-viewer', configObj);
        pannellumViewer.on('scenechange', (scId) => {
            currentPanoIdx = sceneOrderList.indexOf(scId);
            updatePanoStatusUI(scId);
        });

        // Setup controller buttons cleanly
        document.getElementById('btn-prev').onclick = () => {
            if (currentPanoIdx > 0) pannellumViewer.loadScene(sceneOrderList[--currentPanoIdx]);
        };
        document.getElementById('btn-next').onclick = () => {
            if (currentPanoIdx < sceneOrderList.length - 1) pannellumViewer.loadScene(sceneOrderList[++currentPanoIdx]);
        };
        
        let panoAutoTouring = false;
        let panoTimer = null;
        document.getElementById('btn-auto-tour').onclick = () => {
            panoAutoTouring = !panoAutoTouring;
            document.getElementById('btn-auto-tour').classList.toggle('active', panoAutoTouring);
            document.getElementById('btn-auto-tour').textContent = panoAutoTouring ? '⏹️ Pause Spheres' : '▶ Play Spheres';

            const stepTour = () => {
                if (!panoAutoTouring) return;
                currentPanoIdx = (currentPanoIdx + 1) % sceneOrderList.length;
                pannellumViewer.loadScene(sceneOrderList[currentPanoIdx]);
                panoTimer = setTimeout(stepTour, 4000);
            };

            if (panoAutoTouring) stepTour();
            else clearTimeout(panoTimer);
        };
    } catch (err) {
        console.warn('Pannellum parallel setup omitted context parameters safely.', err);
    }
}

function updatePanoStatusUI(scId) {
    const scene = tourConfig.scenes[scId];
    const title = scene ? scene.title : scId;
    document.getElementById('scene-counter').textContent = `${title} (${currentPanoIdx + 1}/${sceneOrderList.length})`;
}

// ═══════════════════════════════════════════════════════════════════════
// UTILITY HELPERS
// ═══════════════════════════════════════════════════════════════════════

function onWindowResize() {
    if (camera && renderer) {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    }
    if (pannellumViewer && activePortalMode === 'pano') {
        pannellumViewer.resize();
    }
}

function updateLoading(percent, statusText) {
    const bar = document.getElementById('loading-progress');
    const label = document.getElementById('loading-status');
    if (bar) bar.style.width = percent + '%';
    if (label) label.textContent = statusText;
}

function drawMinimapPath(box) {
    // Basic graphic map renderer plotting bounding corners inside SVG
    const svg = document.getElementById('minimap-svg');
    if (!svg) return;
    svg.innerHTML = '<rect width="100" height="100" fill="none" stroke="rgba(99,102,241,0.2)" stroke-width="2"/>';
    // Add visual marker point for boundary logic
    svg.innerHTML += '<circle cx="50" cy="50" r="6" fill="#34d399" opacity="0.8"><animate attributeName="r" values="5;8;5" dur="2s" repeatCount="indefinite"/></circle>';
}
