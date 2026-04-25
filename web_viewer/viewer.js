/**
 * E99 3D Explorer — Three.js Viewer
 * ===================================
 * Interactive point cloud and mesh viewer with first-person navigation.
 * Loads PLY/OBJ files and provides WASD + mouse camera controls.
 */

// ═══════════════════════════════════════════════════════════════
// State
// ═══════════════════════════════════════════════════════════════

const state = {
    scene: null,
    camera: null,
    renderer: null,
    clock: null,
    pointCloud: null,
    mesh: null,
    trajectoryLine: null,
    cameraFrustums: null,

    // Navigation
    moveSpeed: 0.1,
    sprintMultiplier: 3.0,
    mouseSensitivity: 0.002,
    euler: { yaw: 0, pitch: 0 },
    velocity: new THREE.Vector3(),
    keys: {},
    isPointerLocked: false,

    // Auto-fly
    autoFly: false,
    autoFlyT: 0,
    autoFlyPositions: [],

    // Stats
    pointCount: 0,
    cameraCount: 0,
    fpsFrames: 0,
    fpsTime: 0,
    currentFPS: 0,

    // Settings
    pointSize: 2.0,
    showTrajectory: true,
    showCameras: true,
};

// ═══════════════════════════════════════════════════════════════
// Initialization
// ═══════════════════════════════════════════════════════════════

function init() {
    console.log('[E99 Viewer] Initializing...');
    const canvas = document.getElementById('render-canvas');

    // Scene
    state.scene = new THREE.Scene();
    state.scene.background = new THREE.Color(0x0a0a12);
    state.scene.fog = new THREE.FogExp2(0x0a0a12, 0.002);

    // Camera — large far plane for big models
    state.camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.001, 10000);
    state.camera.position.set(0, 2, 5);

    // Renderer
    state.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
    state.renderer.setSize(window.innerWidth, window.innerHeight);
    state.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    if (state.renderer.outputEncoding !== undefined) {
        state.renderer.outputEncoding = THREE.sRGBEncoding;
    }

    // Clock
    state.clock = new THREE.Clock();

    // Ambient light
    const ambient = new THREE.AmbientLight(0xffffff, 0.8);
    state.scene.add(ambient);

    // Hemisphere light (sky/ground)
    const hemi = new THREE.HemisphereLight(0x87ceeb, 0x362d59, 0.4);
    state.scene.add(hemi);

    // Grid helper (subtle)
    const grid = new THREE.GridHelper(50, 50, 0x1a1a30, 0x12121f);
    grid.material.opacity = 0.3;
    grid.material.transparent = true;
    state.scene.add(grid);

    // Event listeners
    setupControls();
    setupSettings();
    window.addEventListener('resize', onResize);

    // Show file modal
    showFileModal();

    // Start render loop
    animate();
    console.log('[E99 Viewer] Init complete');
}

// ═══════════════════════════════════════════════════════════════
// Controls
// ═══════════════════════════════════════════════════════════════

function setupControls() {
    const canvas = document.getElementById('render-canvas');

    // Pointer Lock
    const requestPointerLock = () => {
        if (!state.isPointerLocked) {
            canvas.requestPointerLock();
        }
    };
    
    canvas.addEventListener('click', requestPointerLock);
    
    const overlay = document.getElementById('start-overlay');
    overlay.addEventListener('click', requestPointerLock);

    document.addEventListener('pointerlockchange', () => {
        state.isPointerLocked = document.pointerLockElement === canvas;
        const overlay = document.getElementById('start-overlay');
        if (state.isPointerLocked) {
            overlay.classList.add('hidden');
        } else {
            overlay.classList.remove('hidden');
        }
    });

    // Mouse movement
    document.addEventListener('mousemove', (e) => {
        if (!state.isPointerLocked) return;

        state.euler.yaw -= e.movementX * state.mouseSensitivity;
        state.euler.pitch -= e.movementY * state.mouseSensitivity;

        // Clamp pitch
        state.euler.pitch = Math.max(-Math.PI / 2 + 0.01, Math.min(Math.PI / 2 - 0.01, state.euler.pitch));
    });

    // Keyboard
    document.addEventListener('keydown', (e) => {
        state.keys[e.key.toLowerCase()] = true;

        // Toggle auto-fly
        if (e.key.toLowerCase() === 'f') {
            state.autoFly = !state.autoFly;
            state.autoFlyT = 0;
            console.log('Auto-fly:', state.autoFly ? 'ON' : 'OFF');
        }
    });

    document.addEventListener('keyup', (e) => {
        state.keys[e.key.toLowerCase()] = false;
    });

    // Scroll wheel — adjust speed
    document.addEventListener('wheel', (e) => {
        state.moveSpeed *= e.deltaY > 0 ? 0.9 : 1.1;
        state.moveSpeed = Math.max(0.005, Math.min(2.0, state.moveSpeed));
        document.getElementById('speed-slider').value = state.moveSpeed;
        document.getElementById('speed-value').textContent = state.moveSpeed.toFixed(2);
    });
}

// ═══════════════════════════════════════════════════════════════
// Settings UI
// ═══════════════════════════════════════════════════════════════

function setupSettings() {
    // Point size
    document.getElementById('point-size-slider').addEventListener('input', (e) => {
        state.pointSize = parseFloat(e.target.value);
        document.getElementById('point-size-value').textContent = state.pointSize.toFixed(1);
        if (state.pointCloud && state.pointCloud.material) {
            const baseSize = state.basePointSize || 0.005;
            state.pointCloud.material.size = baseSize * (state.pointSize / 2.0);
        }
    });

    // Speed
    document.getElementById('speed-slider').addEventListener('input', (e) => {
        state.moveSpeed = parseFloat(e.target.value);
        document.getElementById('speed-value').textContent = state.moveSpeed.toFixed(2);
    });

    // FOV
    document.getElementById('fov-slider').addEventListener('input', (e) => {
        const fov = parseInt(e.target.value);
        document.getElementById('fov-value').textContent = fov + '°';
        state.camera.fov = fov;
        state.camera.updateProjectionMatrix();
    });

    // Trajectory toggle
    document.getElementById('toggle-trajectory').addEventListener('change', (e) => {
        state.showTrajectory = e.target.checked;
        if (state.trajectoryLine) state.trajectoryLine.visible = state.showTrajectory;
    });

    // Cameras toggle
    document.getElementById('toggle-cameras').addEventListener('change', (e) => {
        state.showCameras = e.target.checked;
        if (state.cameraFrustums) state.cameraFrustums.visible = state.showCameras;
    });
}

// ═══════════════════════════════════════════════════════════════
// File Loading
// ═══════════════════════════════════════════════════════════════

function showFileModal() {
    document.getElementById('file-modal').classList.remove('hidden');
    document.getElementById('loading-screen').classList.add('fade-out');

    const dropZone = document.getElementById('file-drop-zone');
    const fileInput = document.getElementById('file-input');

    // Click to browse
    dropZone.addEventListener('click', () => fileInput.click());

    // File input change
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            loadLocalFile(e.target.files[0]);
        }
    });

    // Drag and drop
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length > 0) {
            loadLocalFile(e.dataTransfer.files[0]);
        }
    });

    // URL load button
    document.getElementById('load-url-btn').addEventListener('click', () => {
        const url = document.getElementById('model-url').value.trim();
        if (url) loadFromURL(url);
    });

    // Check for available models from server
    fetchAvailableModels();
}

function fetchAvailableModels() {
    fetch('/api/models')
        .then(r => r.json())
        .then(models => {
            const container = document.getElementById('sample-models');
            if (models && models.length > 0) {
                const title = document.createElement('p');
                title.style.cssText = 'font-size: 12px; color: var(--text-muted); margin-bottom: 8px;';
                title.textContent = 'Available reconstructions:';
                container.appendChild(title);

                models.forEach(model => {
                    const btn = document.createElement('button');
                    btn.className = 'sample-model-btn';
                    btn.textContent = `📦 ${model.name} (${model.size})`;
                    btn.addEventListener('click', () => loadFromURL(model.url));
                    container.appendChild(btn);
                });
            }
        })
        .catch(() => {
            // Server not available — that's OK, user can still drag & drop
        });
}

function loadLocalFile(file) {
    const ext = file.name.split('.').pop().toLowerCase();
    showLoading(`Loading ${file.name}...`);

    const reader = new FileReader();
    reader.onprogress = (e) => {
        if (e.lengthComputable) {
            updateLoadingProgress(Math.round(e.loaded / e.total * 100));
        }
    };

    reader.onload = (e) => {
        if (ext === 'ply') {
            parsePLY(e.target.result, file.name);
        } else if (ext === 'obj') {
            parseOBJ(e.target.result, file.name);
        } else {
            alert('Unsupported format. Use PLY or OBJ.');
            hideLoading();
        }
    };

    if (ext === 'ply') {
        reader.readAsArrayBuffer(file);
    } else {
        reader.readAsText(file);
    }
}

function loadFromURL(url) {
    showLoading(`Loading from ${url}...`);

    const ext = url.split('.').pop().toLowerCase().split('?')[0];

    const xhr = new XMLHttpRequest();
    xhr.open('GET', url, true);
    xhr.responseType = ext === 'ply' ? 'arraybuffer' : 'text';

    xhr.onprogress = (e) => {
        if (e.lengthComputable) {
            updateLoadingProgress(Math.round(e.loaded / e.total * 100));
        }
    };

    xhr.onload = () => {
        if (xhr.status === 200) {
            if (ext === 'ply') {
                parsePLY(xhr.response, url.split('/').pop());
            } else if (ext === 'obj') {
                parseOBJ(xhr.response, url.split('/').pop());
            }
        } else {
            alert(`Failed to load: ${xhr.statusText}`);
            hideLoading();
        }
    };

    xhr.onerror = () => {
        alert('Network error loading file.');
        hideLoading();
    };

    xhr.send();
}

// ═══════════════════════════════════════════════════════════════
// PLY Parser
// ═══════════════════════════════════════════════════════════════

function parsePLY(arrayBuffer, filename) {
    updateLoadingStatus('Parsing PLY...');

    try {
        const bytes = new Uint8Array(arrayBuffer);

        // Find header end
        let headerEnd = 0;
        const decoder = new TextDecoder();
        const headerText = decoder.decode(bytes.subarray(0, Math.min(bytes.length, 4096)));
        const endHeaderIdx = headerText.indexOf('end_header');
        if (endHeaderIdx === -1) {
            throw new Error('Invalid PLY: no end_header found');
        }

        // Find the newline after end_header
        headerEnd = endHeaderIdx + 'end_header'.length;
        while (headerEnd < bytes.length && bytes[headerEnd] !== 10) headerEnd++;
        headerEnd++; // skip the newline

        const header = headerText.substring(0, endHeaderIdx + 'end_header'.length);
        const lines = header.split('\n');

        let vertexCount = 0;
        let isBinary = false;
        let isLittleEndian = true;
        const properties = [];

        for (const line of lines) {
            const parts = line.trim().split(/\s+/);
            if (parts[0] === 'format') {
                if (parts[1] === 'binary_little_endian') { isBinary = true; isLittleEndian = true; }
                else if (parts[1] === 'binary_big_endian') { isBinary = true; isLittleEndian = false; }
            } else if (parts[0] === 'element' && parts[1] === 'vertex') {
                vertexCount = parseInt(parts[2]);
            } else if (parts[0] === 'property') {
                properties.push({ type: parts[1], name: parts[2] });
            }
        }

        updateLoadingStatus(`Parsing ${vertexCount.toLocaleString()} vertices...`);
        updateLoadingProgress(50);

        const positions = new Float32Array(vertexCount * 3);
        const colors = new Float32Array(vertexCount * 3);
        let hasColors = false;

        // Find property indices
        const propMap = {};
        properties.forEach((p, i) => { propMap[p.name] = i; });

        if (isBinary) {
            const dataView = new DataView(arrayBuffer, headerEnd);
            let offset = 0;

            // Calculate stride
            let stride = 0;
            for (const prop of properties) {
                if (prop.type === 'float' || prop.type === 'float32' || prop.type === 'int' || prop.type === 'int32') stride += 4;
                else if (prop.type === 'double' || prop.type === 'float64') stride += 8;
                else if (prop.type === 'uchar' || prop.type === 'uint8' || prop.type === 'char' || prop.type === 'int8') stride += 1;
                else if (prop.type === 'short' || prop.type === 'int16' || prop.type === 'ushort' || prop.type === 'uint16') stride += 2;
            }

            for (let i = 0; i < vertexCount; i++) {
                let propOffset = 0;
                for (let pi = 0; pi < properties.length; pi++) {
                    const prop = properties[pi];
                    let value;
                    if (prop.type === 'float' || prop.type === 'float32') {
                        value = dataView.getFloat32(offset + propOffset, isLittleEndian);
                        propOffset += 4;
                    } else if (prop.type === 'double' || prop.type === 'float64') {
                        value = dataView.getFloat64(offset + propOffset, isLittleEndian);
                        propOffset += 8;
                    } else if (prop.type === 'uchar' || prop.type === 'uint8') {
                        value = dataView.getUint8(offset + propOffset);
                        propOffset += 1;
                    } else if (prop.type === 'char' || prop.type === 'int8') {
                        value = dataView.getInt8(offset + propOffset);
                        propOffset += 1;
                    } else if (prop.type === 'short' || prop.type === 'int16') {
                        value = dataView.getInt16(offset + propOffset, isLittleEndian);
                        propOffset += 2;
                    } else if (prop.type === 'ushort' || prop.type === 'uint16') {
                        value = dataView.getUint16(offset + propOffset, isLittleEndian);
                        propOffset += 2;
                    } else if (prop.type === 'int' || prop.type === 'int32') {
                        value = dataView.getInt32(offset + propOffset, isLittleEndian);
                        propOffset += 4;
                    } else {
                        propOffset += 4; // default
                        continue;
                    }

                    if (prop.name === 'x') positions[i * 3] = value;
                    else if (prop.name === 'y') positions[i * 3 + 1] = value;
                    else if (prop.name === 'z') positions[i * 3 + 2] = value;
                    else if (prop.name === 'red') { colors[i * 3] = value / 255; hasColors = true; }
                    else if (prop.name === 'green') { colors[i * 3 + 1] = value / 255; hasColors = true; }
                    else if (prop.name === 'blue') { colors[i * 3 + 2] = value / 255; hasColors = true; }
                }
                offset += stride;

                // Progress
                if (i % 100000 === 0) {
                    updateLoadingProgress(50 + Math.round(i / vertexCount * 40));
                }
            }
        } else {
            // ASCII PLY
            const dataText = decoder.decode(bytes.subarray(headerEnd));
            const dataLines = dataText.trim().split('\n');

            for (let i = 0; i < Math.min(vertexCount, dataLines.length); i++) {
                const values = dataLines[i].trim().split(/\s+/).map(Number);

                if ('x' in propMap) positions[i * 3] = values[propMap['x']];
                if ('y' in propMap) positions[i * 3 + 1] = values[propMap['y']];
                if ('z' in propMap) positions[i * 3 + 2] = values[propMap['z']];
                if ('red' in propMap) { colors[i * 3] = values[propMap['red']] / 255; hasColors = true; }
                if ('green' in propMap) { colors[i * 3 + 1] = values[propMap['green']] / 255; hasColors = true; }
                if ('blue' in propMap) { colors[i * 3 + 2] = values[propMap['blue']] / 255; hasColors = true; }
            }
        }

        updateLoadingProgress(90);
        updateLoadingStatus('Building point cloud...');

        createPointCloud(positions, hasColors ? colors : null, vertexCount, filename);
    } catch (err) {
        console.error('PLY parse error:', err);
        alert('Failed to parse PLY: ' + err.message);
        hideLoading();
    }
}

// ═══════════════════════════════════════════════════════════════
// OBJ Parser (basic)
// ═══════════════════════════════════════════════════════════════

function parseOBJ(text, filename) {
    updateLoadingStatus('Parsing OBJ...');

    const vertices = [];
    const faces = [];
    const lines = text.split('\n');

    for (const line of lines) {
        const parts = line.trim().split(/\s+/);
        if (parts[0] === 'v') {
            vertices.push(parseFloat(parts[1]), parseFloat(parts[2]), parseFloat(parts[3]));
        } else if (parts[0] === 'f') {
            const indices = parts.slice(1).map(p => parseInt(p.split('/')[0]) - 1);
            if (indices.length === 3) {
                faces.push(indices[0], indices[1], indices[2]);
            } else if (indices.length === 4) {
                faces.push(indices[0], indices[1], indices[2]);
                faces.push(indices[0], indices[2], indices[3]);
            }
        }
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));

    if (faces.length > 0) {
        geometry.setIndex(faces);
        geometry.computeVertexNormals();

        const material = new THREE.MeshStandardMaterial({
            color: 0x8888cc,
            roughness: 0.6,
            metalness: 0.2,
            side: THREE.DoubleSide,
        });

        state.mesh = new THREE.Mesh(geometry, material);
        state.scene.add(state.mesh);
        state.pointCount = vertices.length / 3;
    } else {
        // No faces — treat as point cloud
        createPointCloud(new Float32Array(vertices), null, vertices.length / 3, filename);
        return;
    }

    centerCamera();
    finishLoading(filename);
}

// ═══════════════════════════════════════════════════════════════
// Point Cloud Creation
// ═══════════════════════════════════════════════════════════════

function createPointCloud(positions, colors, count, filename) {
    console.log(`[E99 Viewer] Creating point cloud: ${count} points`);

    // Remove any existing point cloud
    if (state.pointCloud) {
        state.scene.remove(state.pointCloud);
        state.pointCloud.geometry.dispose();
        state.pointCloud.material.dispose();
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    if (colors) {
        geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    }

    geometry.computeBoundingSphere();
    geometry.computeBoundingBox();

    const bbox = geometry.boundingBox;
    const bsphere = geometry.boundingSphere;
    console.log(`[E99 Viewer] Bounding box:`, bbox.min, bbox.max);
    console.log(`[E99 Viewer] Center:`, bsphere.center, `Radius:`, bsphere.radius);

    // Scale point size relative to model size
    const modelRadius = bsphere.radius || 1;
    const autoPointSize = Math.max(0.002, modelRadius * 0.005);
    state.basePointSize = autoPointSize;

    const material = new THREE.PointsMaterial({
        size: autoPointSize * (state.pointSize / 2.0),
        sizeAttenuation: true,
        vertexColors: !!colors,
        color: colors ? 0xffffff : 0x6366f1,
        transparent: true,
        opacity: 0.95,
    });

    state.pointCloud = new THREE.Points(geometry, material);
    state.scene.add(state.pointCloud);

    state.pointCount = count;

    centerCamera();
    finishLoading(filename);
}

function centerCamera() {
    // Find bounding box of loaded geometry
    let box = new THREE.Box3();

    if (state.pointCloud) {
        state.pointCloud.geometry.computeBoundingBox();
        box = state.pointCloud.geometry.boundingBox.clone();
    } else if (state.mesh) {
        state.mesh.geometry.computeBoundingBox();
        box = state.mesh.geometry.boundingBox.clone();
    }

    const center = new THREE.Vector3();
    box.getCenter(center);
    const size = new THREE.Vector3();
    box.getSize(size);

    const maxDim = Math.max(size.x, size.y, size.z) || 1;
    console.log(`[E99 Viewer] Model center:`, center, `size:`, size, `maxDim:`, maxDim);

    // Position camera to see the whole scene — pull back enough
    state.camera.position.set(
        center.x,
        center.y + maxDim * 0.4,
        center.z + maxDim * 1.2
    );

    // Update camera to see distant objects
    state.camera.near = maxDim * 0.0001;
    state.camera.far = maxDim * 100;
    state.camera.updateProjectionMatrix();

    // Adjust fog to match scene scale
    state.scene.fog = new THREE.FogExp2(0x0a0a12, 0.5 / maxDim);

    state.moveSpeed = maxDim * 0.008;
    const speedSlider = document.getElementById('speed-slider');
    speedSlider.max = Math.max(1, maxDim * 0.05).toFixed(2);
    speedSlider.value = state.moveSpeed;
    document.getElementById('speed-value').textContent = state.moveSpeed.toFixed(3);

    // Look at center — compute yaw/pitch from camera to center
    const dir = new THREE.Vector3().subVectors(center, state.camera.position).normalize();
    state.euler.yaw = Math.atan2(dir.x, dir.z);
    state.euler.pitch = Math.asin(dir.y);

    console.log(`[E99 Viewer] Camera at:`, state.camera.position, `looking yaw:`, state.euler.yaw, `pitch:`, state.euler.pitch);
}

// ═══════════════════════════════════════════════════════════════
// Loading UI
// ═══════════════════════════════════════════════════════════════

function showLoading(msg) {
    document.getElementById('file-modal').classList.add('hidden');
    document.getElementById('loading-screen').classList.remove('fade-out');
    updateLoadingStatus(msg);
    updateLoadingProgress(10);
}

function hideLoading() {
    const ls = document.getElementById('loading-screen');
    ls.classList.add('fade-out');
    // Fully remove after transition so it doesn't block the canvas
    setTimeout(() => {
        ls.style.pointerEvents = 'none';
        ls.classList.add('hidden');
    }, 700);
}

function updateLoadingProgress(percent) {
    document.getElementById('loading-progress').style.width = percent + '%';
}

function updateLoadingStatus(msg) {
    document.getElementById('loading-status').textContent = msg;
}

function finishLoading(filename) {
    updateLoadingProgress(100);
    updateLoadingStatus('Ready!');

    setTimeout(() => {
        hideLoading();

        // Show HUD panels
        document.getElementById('hud-top-left').classList.remove('hidden');
        document.getElementById('hud-bottom-left').classList.remove('hidden');
        document.getElementById('hud-top-right').classList.remove('hidden');
        document.getElementById('hud-position').classList.remove('hidden');
        document.getElementById('start-overlay').classList.remove('hidden');

        // Update stats
        document.getElementById('stat-points').textContent = formatNumber(state.pointCount);
        document.getElementById('stat-cameras').textContent = state.cameraCount || '—';
    }, 500);
}

function formatNumber(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n.toString();
}

// ═══════════════════════════════════════════════════════════════
// Camera Trajectory Loading
// ═══════════════════════════════════════════════════════════════

function loadTrajectory(url) {
    fetch(url)
        .then(r => r.json())
        .then(data => {
            if (!data.cameras || data.cameras.length === 0) return;

            state.cameraCount = data.cameras.length;
            state.autoFlyPositions = data.cameras.map(c => new THREE.Vector3(...c.position));

            // Create trajectory line
            const points = state.autoFlyPositions;
            const geometry = new THREE.BufferGeometry().setFromPoints(points);

            // Color gradient
            const colors = new Float32Array(points.length * 3);
            for (let i = 0; i < points.length; i++) {
                const t = i / (points.length - 1);
                colors[i * 3] = 0.2 + 0.8 * t;       // R
                colors[i * 3 + 1] = 1.0 - 0.5 * t;   // G
                colors[i * 3 + 2] = 0.8 * (1 - t);    // B
            }
            geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

            const material = new THREE.LineBasicMaterial({ vertexColors: true, linewidth: 2 });
            state.trajectoryLine = new THREE.Line(geometry, material);
            state.scene.add(state.trajectoryLine);

            // Create camera frustum markers
            const frustumGroup = new THREE.Group();
            for (let i = 0; i < points.length; i += Math.max(1, Math.floor(points.length / 30))) {
                const marker = new THREE.Mesh(
                    new THREE.SphereGeometry(0.02, 8, 8),
                    new THREE.MeshBasicMaterial({
                        color: new THREE.Color().setHSL(i / points.length * 0.8, 0.8, 0.5)
                    })
                );
                marker.position.copy(points[i]);
                frustumGroup.add(marker);
            }
            state.cameraFrustums = frustumGroup;
            state.scene.add(frustumGroup);

            document.getElementById('stat-cameras').textContent = state.cameraCount;
        })
        .catch(() => {});
}

// ═══════════════════════════════════════════════════════════════
// Animation Loop
// ═══════════════════════════════════════════════════════════════

function animate() {
    requestAnimationFrame(animate);

    const delta = state.clock.getDelta();

    // Movement
    if (state.autoFly && state.autoFlyPositions.length >= 2) {
        updateAutoFly(delta);
    } else {
        updateMovement(delta);
    }

    // Update camera rotation from euler
    const quaternion = new THREE.Quaternion();
    const eulerThree = new THREE.Euler(state.euler.pitch, state.euler.yaw, 0, 'YXZ');
    quaternion.setFromEuler(eulerThree);
    state.camera.quaternion.copy(quaternion);

    // Render
    state.renderer.render(state.scene, state.camera);

    // FPS counter
    state.fpsFrames++;
    const now = performance.now();
    if (now - state.fpsTime > 1000) {
        state.currentFPS = Math.round(state.fpsFrames * 1000 / (now - state.fpsTime));
        state.fpsFrames = 0;
        state.fpsTime = now;
        document.getElementById('stat-fps').textContent = state.currentFPS;
    }

    // Update position display
    const pos = state.camera.position;
    document.getElementById('pos-x').textContent = pos.x.toFixed(2);
    document.getElementById('pos-y').textContent = pos.y.toFixed(2);
    document.getElementById('pos-z').textContent = pos.z.toFixed(2);
}

function updateMovement(delta) {
    const speed = state.moveSpeed * (state.keys['shift'] ? state.sprintMultiplier : 1);

    const forward = new THREE.Vector3();
    state.camera.getWorldDirection(forward);
    forward.normalize();

    const right = new THREE.Vector3();
    right.crossVectors(forward, state.camera.up).normalize();

    const move = new THREE.Vector3();

    if (state.keys['w']) move.add(forward);
    if (state.keys['s']) move.sub(forward);
    if (state.keys['a']) move.sub(right);
    if (state.keys['d']) move.add(right);
    if (state.keys['q'] || state.keys[' ']) move.y += 1;
    if (state.keys['e']) move.y -= 1;

    if (move.length() > 0) {
        move.normalize().multiplyScalar(speed);
        state.camera.position.add(move);
    }
}

function updateAutoFly(delta) {
    const positions = state.autoFlyPositions;
    const n = positions.length;

    state.autoFlyT += 0.001;
    if (state.autoFlyT >= 1) state.autoFlyT = 0;

    const tScaled = state.autoFlyT * (n - 1);
    const idx = Math.floor(tScaled);
    const frac = tScaled - idx;

    if (idx < n - 1) {
        const pos = new THREE.Vector3().lerpVectors(positions[idx], positions[idx + 1], frac);
        state.camera.position.copy(pos);

        // Look towards next position
        if (idx < n - 2) {
            const lookTarget = new THREE.Vector3().lerpVectors(positions[idx + 1], positions[idx + 2], frac);
            const dir = lookTarget.clone().sub(pos).normalize();
            state.euler.yaw = Math.atan2(dir.x, dir.z);
            state.euler.pitch = Math.asin(-dir.y);
        }
    }
}

// ═══════════════════════════════════════════════════════════════
// Resize
// ═══════════════════════════════════════════════════════════════

function onResize() {
    state.camera.aspect = window.innerWidth / window.innerHeight;
    state.camera.updateProjectionMatrix();
    state.renderer.setSize(window.innerWidth, window.innerHeight);
}

// ═══════════════════════════════════════════════════════════════
// Entry Point
// ═══════════════════════════════════════════════════════════════

window.addEventListener('DOMContentLoaded', init);
