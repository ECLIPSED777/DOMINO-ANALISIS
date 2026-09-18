"""
Servidor API de Alto Rendimiento (FastAPI) para el Asistente de Dominó Profesional.
Procesa frames de imagen, ejecuta visión artificial y teoría de juegos,
y responde en menos de 100 ms para alimentar el HUD Web y la 'nubecita' flotante.
"""

import time
import base64
import cv2
import numpy as np
from typing import Optional, List, Dict
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from game_logic import DominoGameState, Tile, PlayerPosition, MoveRecommendation
from vision import DominoVision, VisionAnalysisResult


app = FastAPI(
    title="Domino Vamos AI Assistant API",
    description="Motor analista y asistente en tiempo real para Dominó 2v2",
    version="1.0.0"
)

# Habilitar CORS para permitir integraciones desde cualquier cliente móvil o web
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instancias singleton del estado de juego y visión artificial
game_state = DominoGameState(target_score=100)
vision_engine = DominoVision()


class ManualEndsRequest(BaseModel):
    left_end: Optional[int] = None
    right_end: Optional[int] = None


class ManualMoveRequest(BaseModel):
    player: str
    v1: int
    v2: int
    target_end: str  # 'izquierda', 'derecha', 'salida'


class Base64AnalyzeRequest(BaseModel):
    image_base64: str
    left_end: Optional[int] = None
    right_end: Optional[int] = None


@app.post("/api/analyze")
async def analyze_frame_endpoint(
    file: Optional[UploadFile] = File(None),
    image_base64: Optional[str] = Form(None),
    left_end: Optional[int] = Form(None),
    right_end: Optional[int] = Form(None),
):
    """
    Endpoint principal: recibe una captura de pantalla del juego,
    ejecuta OpenCV para extraer estado y calcula la mejor jugada en < 100 ms.
    """
    start_time = time.time()

    # 1. Decodificar la imagen
    image_bgr = None
    if file:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        image_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    elif image_base64:
        if "," in image_base64:
            image_base64 = image_base64.split(",")[1]
        decoded = base64.b64decode(image_base64)
        nparr = np.frombuffer(decoded, np.uint8)
        image_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if image_bgr is None:
        raise HTTPException(status_code=400, detail="No se pudo decodificar la imagen proporcionada.")

    # 2. Configurar extremos conocidos si vienen en el request
    known_ends = None
    if left_end is not None and right_end is not None:
        known_ends = (left_end, right_end)
        game_state.set_board_ends(left_end, right_end)
    elif game_state.board_ends[0] is not None:
        known_ends = game_state.board_ends

    # 3. Procesar visión artificial con OpenCV
    vision_res: VisionAnalysisResult = vision_engine.analyze_frame(image_bgr, known_ends=known_ends)

    # 4. Actualizar estado lógico del juego
    if vision_res.hero_tiles:
        detected_tiles = [dt.tile for dt in vision_res.hero_tiles]
        game_state.set_hero_hand(detected_tiles)

    # Registrar pases detectados
    for passed_player in vision_res.passes_detected:
        game_state.register_pass(passed_player)

    # 5. Generar recomendación táctica
    recommendation = None
    if vision_res.is_hero_turn or True:  # Siempre calcular mejor opción disponible
        rec: Optional[MoveRecommendation] = game_state.evaluate_best_move()
        if rec:
            recommendation = rec.to_dict()
            # Asociar bounding box de la ficha si está en las detectadas
            for dt in vision_res.hero_tiles:
                if dt.tile == rec.tile:
                    recommendation["bbox"] = {
                        "x": dt.bbox[0],
                        "y": dt.bbox[1],
                        "w": dt.bbox[2],
                        "h": dt.bbox[3]
                    }
                    break

    total_latency_ms = round((time.time() - start_time) * 1000.0, 2)

    return {
        "success": True,
        "is_hero_turn": vision_res.is_hero_turn,
        "turn_player": vision_res.turn_player.value if vision_res.turn_player else None,
        "hero_tiles": [
            {"tile": dt.tile.to_dict(), "bbox": dt.bbox, "confidence": dt.confidence}
            for dt in vision_res.hero_tiles
        ],
        "player_counts": {k.value: v for k, v in vision_res.player_counts.items()},
        "passes_detected": [p.value for p in vision_res.passes_detected],
        "board_ends": list(game_state.board_ends),
        "recommendation": recommendation,
        "vision_time_ms": vision_res.processing_time_ms,
        "total_latency_ms": total_latency_ms
    }


@app.post("/api/reset")
def reset_round_endpoint():
    """Reinicia la mano actual para una nueva ronda."""
    game_state.reset_round()
    return {"success": True, "message": "Mano reiniciada con éxito (7 fichas por jugador)."}


@app.post("/api/set_ends")
def set_board_ends_endpoint(req: ManualEndsRequest):
    """Permite ajustar o corregir manualmente los dos números de los extremos abiertos."""
    game_state.set_board_ends(req.left_end, req.right_end)
    return {"success": True, "board_ends": game_state.board_ends}


@app.post("/api/manual_move")
def manual_move_endpoint(req: ManualMoveRequest):
    """Permite registrar manualmente una jugada realizada en la mesa."""
    try:
        player = PlayerPosition(req.player)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Jugador no válido. Opciones: {[p.value for p in PlayerPosition]}")

    tile = Tile(req.v1, req.v2)
    game_state.register_play(player, tile, req.target_end)
    return {
        "success": True,
        "board_ends": list(game_state.board_ends),
        "player_counts": {k.value: v for k, v in game_state.player_counts.items()},
        "played_count": len(game_state.played_tiles)
    }


@app.get("/api/state")
def get_current_state():
    """Retorna la telemetría completa del estado de la partida."""
    return {
        "hero_hand": [t.to_dict() for t in game_state.hero_hand],
        "board_ends": list(game_state.board_ends),
        "player_counts": {k.value: v for k, v in game_state.player_counts.items()},
        "void_suits": {k.value: list(v) for k, v in game_state.void_suits.items()},
        "unseen_count": len(game_state.unseen_tiles),
        "score_blue": game_state.score_blue,
        "score_red": game_state.score_red,
        "target_score": game_state.target_score
    }


# Montar interfaz web estática
app.mount("/", StaticFiles(directory="interface", html=True), name="interface")


if __name__ == "__main__":
    import uvicorn
    print("Iniciando servidor del Asistente de Dominó Profesional en http://localhost:8000 ...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
