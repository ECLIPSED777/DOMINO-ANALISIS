/**
 * Controlador de Frontend para Domino Vamos AI Pro.
 * Gestiona captura de pantalla, comunicación con la API FastAPI,
 * renderizado de fichas y proyección del HUD ("nubecita" y flecha táctica).
 */

// Si se abre directamente el archivo HTML (file://), apuntar por defecto a localhost:8000
const API_BASE = (window.location.origin && window.location.origin !== "null" && !window.location.protocol.startsWith("file"))
  ? window.location.origin 
  : "http://localhost:8000";

// Elementos del DOM
const videoElement = document.getElementById('videoElement');
const displayCanvas = document.getElementById('displayCanvas');
const ctx = displayCanvas.getContext('2d');
const fileInput = document.getElementById('fileInput');

const btnScreenShare = document.getElementById('btnScreenShare');
const btnWebcam = document.getElementById('btnWebcam');
const btnResetRound = document.getElementById('btnResetRound');
const btnSetEnds = document.getElementById('btnSetEnds');

const turnBadge = document.getElementById('turnBadge');
const turnText = document.getElementById('turnText');
const latencyText = document.getElementById('latencyText');

const floatingSpeechBubble = document.getElementById('floatingSpeechBubble');
const bubbleText = document.getElementById('bubbleText');
const targetArrow = document.getElementById('targetArrow');

const largeTile = document.getElementById('largeTile');
const tileTopHalf = document.getElementById('tileTopHalf');
const tileBottomHalf = document.getElementById('tileBottomHalf');
const targetEndText = document.getElementById('targetEndText');
const reasoningText = document.getElementById('reasoningText');
const actionTypeBadge = document.getElementById('actionTypeBadge');
const confidenceBadge = document.getElementById('confidenceBadge');

const inputLeftEnd = document.getElementById('inputLeftEnd');
const inputRightEnd = document.getElementById('inputRightEnd');
const handContainer = document.getElementById('handContainer');
const unseenCount = document.getElementById('unseenCount');

const countHero = document.getElementById('countHero');
const countPartner = document.getElementById('countPartner');
const countWest = document.getElementById('countWest');
const countEast = document.getElementById('countEast');

let isStreaming = false;
let streamInterval = null;
let currentBbox = null;

// Patrones estándar de posiciones para los puntos (pips) del dominó (matriz 3x3)
// 0: ninguno, 1..6: posiciones en grid de 3x3
const PIP_PATTERNS = {
  0: [],
  1: [4],                       // Centro
  2: [0, 8],                    // Esquinas diagonal
  3: [0, 4, 8],                 // Diagonal de 3
  4: [0, 2, 6, 8],              // Cuatro esquinas
  5: [0, 2, 4, 6, 8],           // Cuatro esquinas + centro
  6: [0, 2, 3, 5, 6, 8]         // Dos columnas de 3
};

function renderPips(container, count) {
  container.innerHTML = '';
  const positions = PIP_PATTERNS[count] || [];
  for (let i = 0; i < 9; i++) {
    const slot = document.createElement('div');
    if (positions.includes(i)) {
      const pip = document.createElement('div');
      pip.className = 'pip';
      slot.appendChild(pip);
    }
    container.appendChild(slot);
  }
}

function renderLargeTile(v1, v2) {
  renderPips(tileTopHalf, v1);
  renderPips(tileBottomHalf, v2);
}

// Inicialización con [0|0]
renderLargeTile(0, 0);

// Enviar frame al servidor FastAPI
async function sendFrameForAnalysis(blob) {
  const formData = new FormData();
  formData.append('file', blob, 'frame.jpg');

  const leftVal = inputLeftEnd.value ? parseInt(inputLeftEnd.value) : null;
  const rightVal = inputRightEnd.value ? parseInt(inputRightEnd.value) : null;

  if (leftVal !== null && rightVal !== null) {
    formData.append('left_end', leftVal);
    formData.append('right_end', rightVal);
  }

  const startTime = performance.now();

  try {
    const res = await fetch(`${API_BASE}/api/analyze`, {
      method: 'POST',
      body: formData
    });

    if (!res.ok) throw new Error(`HTTP Error ${res.status}`);
    const data = await res.json();

    const clientLatency = Math.round(performance.now() - startTime);
    latencyText.textContent = `${data.total_latency_ms || clientLatency} ms`;

    updateUI(data);
  } catch (err) {
    console.error("Error al analizar frame:", err);
  }
}

// Actualizar Dashboard y HUD con la respuesta de la IA
function updateUI(data) {
  // 1. Estado del turno
  if (data.is_hero_turn) {
    turnBadge.className = 'status-pill turn-active';
    turnText.textContent = '¡ES TU TURNO!';
  } else {
    turnBadge.className = 'status-pill turn-waiting';
    turnText.textContent = data.turn_player ? `TURNO: ${data.turn_player}` : 'ESPERANDO TURNO';
  }

  // 2. Extremos en mesa
  if (data.board_ends && data.board_ends[0] !== null) {
    inputLeftEnd.value = data.board_ends[0];
    inputRightEnd.value = data.board_ends[1];
  }

  // 3. Conteo de fichas de jugadores
  if (data.player_counts) {
    countHero.textContent = `${data.player_counts.Hero || 0} fichas`;
    countPartner.textContent = `${data.player_counts.Companero || 0} fichas`;
    countWest.textContent = `${data.player_counts.Rival_Izq || 0} fichas`;
    countEast.textContent = `${data.player_counts.Rival_Der || 0} fichas`;
  }

  // 4. Atril de Hero
  if (data.hero_tiles) {
    handContainer.innerHTML = '';
    data.hero_tiles.forEach(dt => {
      const tileDiv = document.createElement('div');
      tileDiv.className = 'hand-tile-small';
      
      const isRecommended = data.recommendation && 
        ((data.recommendation.tile.v1 === dt.tile.v1 && data.recommendation.tile.v2 === dt.tile.v2) ||
         (data.recommendation.tile.v1 === dt.tile.v2 && data.recommendation.tile.v2 === dt.tile.v1));

      if (isRecommended) {
        tileDiv.classList.add('highlighted');
      }

      tileDiv.innerHTML = `
        <div class="tile-half" style="padding: 2px;">
          ${renderMiniPipsHtml(dt.tile.v1)}
        </div>
        <div class="tile-divider" style="height: 2px;"></div>
        <div class="tile-half" style="padding: 2px;">
          ${renderMiniPipsHtml(dt.tile.v2)}
        </div>
      `;
      handContainer.appendChild(tileDiv);
    });
  }

  // 5. Recomendación de la IA
  if (data.recommendation) {
    const rec = data.recommendation;
    renderLargeTile(rec.tile.v1, rec.tile.v2);

    targetEndText.textContent = `A LA ${rec.target_end.toUpperCase()}`;
    reasoningText.textContent = rec.reasoning;
    actionTypeBadge.textContent = rec.action_type.replace(/_/g, ' ');
    confidenceBadge.textContent = `${Math.round(rec.confidence * 100)}% ÓPTIMO`;

    // 6. Proyectar la "NUBECITA" flotante de aviso táctico
    floatingSpeechBubble.classList.remove('hidden');
    bubbleText.innerHTML = `
      Juega la ficha <strong>[${rec.tile.v1}|${rec.tile.v2}]</strong> hacia la <strong>${rec.target_end.toUpperCase()}</strong>.<br>
      <span style="font-size: 0.8rem; color: #94a3b8;">${rec.reasoning}</span>
    `;

    // 7. Flecha apuntando a la ficha (si se detectó el bbox en pantalla)
    if (rec.bbox) {
      positionArrowOnBbox(rec.bbox);
    } else {
      targetArrow.classList.add('hidden');
    }
  } else {
    floatingSpeechBubble.classList.add('hidden');
    targetArrow.classList.add('hidden');
    targetEndText.textContent = 'ESPERANDO JUGADA LEGAL';
  }
}

function renderMiniPipsHtml(count) {
  const positions = PIP_PATTERNS[count] || [];
  let html = '';
  for (let i = 0; i < 9; i++) {
    if (positions.includes(i)) {
      html += '<div style="width: 5px; height: 5px; background: #000; border-radius: 50%;"></div>';
    } else {
      html += '<div></div>';
    }
  }
  return html;
}

function positionArrowOnBbox(bbox) {
  const rect = displayCanvas.getBoundingClientRect();
  const scaleX = rect.width / displayCanvas.width;
  const scaleY = rect.height / displayCanvas.height;

  const arrowX = rect.left + (bbox.x + bbox.w / 2) * scaleX;
  const arrowY = rect.top + bbox.y * scaleY - 35;

  targetArrow.style.left = `${arrowX}px`;
  targetArrow.style.top = `${arrowY}px`;
  targetArrow.classList.remove('hidden');
}

// Control de Video / Stream
function startAnalysisLoop() {
  if (streamInterval) clearInterval(streamInterval);
  streamInterval = setInterval(() => {
    if (!isStreaming) return;

    displayCanvas.width = videoElement.videoWidth || 1280;
    displayCanvas.height = videoElement.videoHeight || 720;
    ctx.drawImage(videoElement, 0, 0, displayCanvas.width, displayCanvas.height);

    displayCanvas.toBlob(blob => {
      if (blob) sendFrameForAnalysis(blob);
    }, 'image/jpeg', 0.85);
  }, 800); // Muestreo cada 800 ms (tasa ideal para < 100 ms de procesamiento)
}

// Compartir Pantalla
btnScreenShare.addEventListener('click', async () => {
  try {
    const stream = await navigator.mediaDevices.getDisplayMedia({
      video: { cursor: "always" },
      audio: false
    });
    videoElement.srcObject = stream;
    isStreaming = true;
    startAnalysisLoop();
  } catch (err) {
    console.error("Error al compartir pantalla:", err);
  }
});

// Cámara
btnWebcam.addEventListener('click', async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 1280, height: 720 }
    });
    videoElement.srcObject = stream;
    isStreaming = true;
    startAnalysisLoop();
  } catch (err) {
    console.error("Error al acceder a la cámara:", err);
  }
});

// Carga Manual de Imágenes (para pruebas inmediatas con las capturas del usuario)
fileInput.addEventListener('change', e => {
  const file = e.target.files[0];
  if (!file) return;

  const img = new Image();
  img.onload = () => {
    displayCanvas.width = img.width;
    displayCanvas.height = img.height;
    ctx.drawImage(img, 0, 0);

    displayCanvas.toBlob(blob => {
      if (blob) sendFrameForAnalysis(blob);
    }, 'image/jpeg', 0.9);
  };
  img.src = URL.createObjectURL(file);
});

// Reiniciar Mano
btnResetRound.addEventListener('click', async () => {
  try {
    const res = await fetch(`${API_BASE}/api/reset`, { method: 'POST' });
    const data = await res.json();
    alert(data.message || "Mano reiniciada.");
    inputLeftEnd.value = '';
    inputRightEnd.value = '';
    handContainer.innerHTML = '<span class="empty-hint">Nueva mano iniciada</span>';
    targetEndText.textContent = 'ESPERANDO';
  } catch (err) {
    console.error("Error al reiniciar mano:", err);
  }
});

// Fijar Extremos Manualmente
btnSetEnds.addEventListener('click', async () => {
  const left = parseInt(inputLeftEnd.value);
  const right = parseInt(inputRightEnd.value);
  if (isNaN(left) || isNaN(right)) {
    alert("Por favor introduce ambos números de extremos (0 a 6).");
    return;
  }
  try {
    await fetch(`${API_BASE}/api/set_ends`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ left_end: left, right_end: right })
    });
  } catch (err) {
    console.error("Error al fijar extremos:", err);
  }
});

// Simulación interactiva inmediata (Escenarios reales de Domino Vamos)
const btnDemoMatch = document.getElementById('btnDemoMatch');
let demoStep = 0;

const DEMO_SCENARIOS = [
  {
    is_hero_turn: true,
    turn_player: "Hero",
    total_latency_ms: 38,
    board_ends: [2, 5],
    player_counts: { Hero: 4, Companero: 3, Rival_Izq: 3, Rival_Der: 3 },
    hero_tiles: [
      { tile: { v1: 2, v2: 4, points: 6, is_double: false }, bbox: [320, 520, 60, 110], confidence: 0.95 },
      { tile: { v1: 5, v2: 6, points: 11, is_double: false }, bbox: [390, 520, 60, 110], confidence: 0.95 },
      { tile: { v1: 1, v2: 3, points: 4, is_double: false }, bbox: [460, 520, 60, 110], confidence: 0.95 },
      { tile: { v1: 0, v2: 0, points: 0, is_double: true }, bbox: [530, 520, 60, 110], confidence: 0.98 }
    ],
    recommendation: {
      tile: { v1: 2, v2: 4, points: 6 },
      target_end: "izquierda",
      resulting_end: 4,
      confidence: 0.94,
      action_type: "CASTIGO_RIVAL",
      reasoning: "Juega [2|4] a la izquierda para matar el 2 del rival y pasar al rival izquierdo (Jesus es fallo a 4). Además desahogas tu serie media.",
      bbox: { x: 320, y: 520, w: 60, h: 110 }
    }
  },
  {
    is_hero_turn: true,
    turn_player: "Hero",
    total_latency_ms: 42,
    board_ends: [0, 4],
    player_counts: { Hero: 1, Companero: 1, Rival_Izq: 2, Rival_Der: 1 },
    hero_tiles: [
      { tile: { v1: 0, v2: 0, points: 0, is_double: true }, bbox: [480, 520, 60, 110], confidence: 0.99 }
    ],
    recommendation: {
      tile: { v1: 0, v2: 0, points: 0 },
      target_end: "izquierda",
      resulting_end: 0,
      confidence: 1.0,
      action_type: "DOMINADA_DIRECTA",
      reasoning: "¡DOMINÓ DIRECTO! Coloca el [0|0] en la punta blanca. Tu equipo Azul gana la mano y suma los puntos de las 4 fichas restantes.",
      bbox: { x: 480, y: 520, w: 60, h: 110 }
    }
  }
];

if (btnDemoMatch) {
  btnDemoMatch.addEventListener('click', () => {
    const scenario = DEMO_SCENARIOS[demoStep % DEMO_SCENARIOS.length];
    demoStep++;
    updateUI(scenario);
  });
}

