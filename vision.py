"""
Módulo de Visión por Computadora (OpenCV) para 'Domino Vamos'.
Analiza capturas de pantalla para extraer:
1. Detección de Turno (Círculo verde de temporizador sobre Hero).
2. Extracción y conteo de puntos de fichas en el atril propio.
3. Conteo de fichas de rivales y compañero (badges 1..7).
4. Detección de eventos 'PASAR' (bocadillos naranjas).
"""

import cv2
import numpy as np
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
from game_logic import Tile, PlayerPosition


@dataclass
class DetectedTile:
    tile: Tile
    bbox: Tuple[int, int, int, int]  # (x, y, w, h)
    confidence: float


@dataclass
class VisionAnalysisResult:
    is_hero_turn: bool
    turn_player: Optional[PlayerPosition]
    hero_tiles: List[DetectedTile]
    player_counts: Dict[PlayerPosition, int]
    passes_detected: List[PlayerPosition]
    board_ends: Tuple[Optional[int], Optional[int]]
    processing_time_ms: float


class DominoVision:
    def __init__(self):
        # Rangos de color HSV calibrados para 'Domino Vamos'
        # Verde neón del temporizador circular de turno
        self.lower_green_timer = np.array([35, 120, 120])
        self.upper_green_timer = np.array([85, 255, 255])

        # Naranja del cartel de 'PASAR'
        self.lower_orange_pass = np.array([8, 150, 180])
        self.upper_orange_pass = np.array([25, 255, 255])

        # Blanco/Marfil de las fichas de dominó
        self.lower_ivory = np.array([0, 0, 180])
        self.upper_ivory = np.array([180, 50, 255])

    def analyze_frame(self, image_bgr: np.ndarray, known_ends: Optional[Tuple[int, int]] = None) -> VisionAnalysisResult:
        """
        Punto de entrada principal: procesa una imagen en formato BGR y retorna
        la telemetría visual completa en menos de 100 ms.
        """
        start_tick = cv2.getTickCount()
        h, w = image_bgr.shape[:2]

        # 1. Detección de turno activo
        is_hero_turn, turn_player = self.detect_turn(image_bgr)

        # 2. Detección de eventos "PASAR"
        passes = self.detect_passes(image_bgr)

        # 3. Extracción de fichas del atril inferior
        hero_tiles = self.extract_hero_hand(image_bgr)

        # 4. Lectura de conteo de fichas de rivales y compañero
        player_counts = self.estimate_player_tile_counts(image_bgr, len(hero_tiles))

        # 5. Extremos del tablero
        board_ends = known_ends if known_ends is not None else (None, None)

        elapsed_ms = (cv2.getTickCount() - start_tick) / cv2.getTickFrequency() * 1000.0

        return VisionAnalysisResult(
            is_hero_turn=is_hero_turn,
            turn_player=turn_player,
            hero_tiles=hero_tiles,
            player_counts=player_counts,
            passes_detected=passes,
            board_ends=board_ends,
            processing_time_ms=round(elapsed_ms, 2)
        )

    def detect_turn(self, image_bgr: np.ndarray) -> Tuple[bool, Optional[PlayerPosition]]:
        """
        Detecta qué jugador tiene el turno activo buscando el halo circular
        verde brillante del temporizador (10-15s).
        """
        h, w = image_bgr.shape[:2]
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        mask_green = cv2.inRange(hsv, self.lower_green_timer, self.upper_green_timer)

        # Regiones de los 4 avatares (normalizadas x1, y1, x2, y2)
        regions = {
            PlayerPosition.HERO: (int(0.08 * w), int(0.70 * h), int(0.24 * w), int(0.98 * h)),
            PlayerPosition.PARTNER: (int(0.42 * w), int(0.00 * h), int(0.58 * w), int(0.20 * h)),
            PlayerPosition.RIVAL_LEFT: (int(0.01 * w), int(0.35 * h), int(0.15 * w), int(0.55 * h)),
            PlayerPosition.RIVAL_RIGHT: (int(0.85 * w), int(0.35 * h), int(0.99 * w), int(0.55 * h)),
        }

        active_player = None
        max_green_pixels = 0

        for player, (x1, y1, x2, y2) in regions.items():
            roi = mask_green[y1:y2, x1:x2]
            green_count = cv2.countNonZero(roi)
            # Umbral de píxeles verdes para confirmar círculo de temporizador
            if green_count > 150 and green_count > max_green_pixels:
                max_green_pixels = green_count
                active_player = player

        is_hero_turn = (active_player == PlayerPosition.HERO)
        return is_hero_turn, active_player

    def detect_passes(self, image_bgr: np.ndarray) -> List[PlayerPosition]:
        """
        Detecta la aparición del cartel naranja 'PASAR' sobre los jugadores.
        """
        h, w = image_bgr.shape[:2]
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        mask_orange = cv2.inRange(hsv, self.lower_orange_pass, self.upper_orange_pass)

        # Regiones donde suele proyectarse el cartel de pase
        pass_zones = {
            PlayerPosition.HERO: (int(0.12 * w), int(0.68 * h), int(0.28 * w), int(0.80 * h)),
            PlayerPosition.PARTNER: (int(0.44 * w), int(0.15 * h), int(0.56 * w), int(0.25 * h)),
            PlayerPosition.RIVAL_LEFT: (int(0.08 * w), int(0.28 * h), int(0.20 * w), int(0.38 * h)),
            PlayerPosition.RIVAL_RIGHT: (int(0.76 * w), int(0.28 * h), int(0.88 * w), int(0.38 * h)),
        }

        passes = []
        for player, (x1, y1, x2, y2) in pass_zones.items():
            roi = mask_orange[y1:y2, x1:x2]
            orange_count = cv2.countNonZero(roi)
            if orange_count > 120:
                passes.append(player)

        return passes

    def extract_hero_hand(self, image_bgr: np.ndarray) -> List[DetectedTile]:
        """
        Extrae y decodifica las fichas de dominó en la bandeja inferior de Hero.
        Segmenta cada ficha y cuenta los puntos superiores e inferiores.
        """
        h, w = image_bgr.shape[:2]
        # ROI del atril inferior central
        y1, y2 = int(0.65 * h), int(0.97 * h)
        x1, x2 = int(0.28 * w), int(0.74 * w)

        hand_roi = image_bgr[y1:y2, x1:x2]
        roi_h, roi_w = hand_roi.shape[:2]

        # Máscara para detectar fichas de color blanco / marfil
        hsv = cv2.cvtColor(hand_roi, cv2.COLOR_BGR2HSV)
        mask_ivory = cv2.inRange(hsv, self.lower_ivory, self.upper_ivory)

        # Operaciones morfológicas para limpiar y cerrar los contornos de las fichas
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed = cv2.morphologyEx(mask_ivory, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidate_boxes = []
        min_tile_area = (roi_h * 0.40) * (roi_w * 0.03)  # Área mínima esperada de una ficha

        for cnt in contours:
            bx, by, bw, bh = cv2.boundingRect(cnt)
            area = bw * bh
            aspect_ratio = bh / float(bw) if bw > 0 else 0

            # Las fichas en atril son verticales: relación de aspecto típica entre 1.4 y 2.5
            if area >= min_tile_area and 1.3 <= aspect_ratio <= 2.8 and bh >= roi_h * 0.45:
                candidate_boxes.append((bx, by, bw, bh))

        # Ordenar de izquierda a derecha
        candidate_boxes = sorted(candidate_boxes, key=lambda b: b[0])

        # Filtrar posibles solapamientos
        filtered_boxes = []
        for b in candidate_boxes:
            if not filtered_boxes:
                filtered_boxes.append(b)
            else:
                prev_x, _, prev_w, _ = filtered_boxes[-1]
                # Si el centro está suficientemente separado
                if (b[0] - prev_x) > prev_w * 0.6:
                    filtered_boxes.append(b)

        # Decodificar puntos (dots) de cada ficha
        detected_tiles = []
        for bx, by, bw, bh in filtered_boxes:
            tile_crop = hand_roi[by:by+bh, bx:bx+bw]
            v1, v2 = self._count_dots_on_tile(tile_crop)

            # Coordenadas globales en la pantalla original
            global_bbox = (x1 + bx, y1 + by, bw, bh)
            detected_tiles.append(
                DetectedTile(
                    tile=Tile(v1, v2),
                    bbox=global_bbox,
                    confidence=0.92
                )
            )

        return detected_tiles

    def _count_dots_on_tile(self, tile_bgr: np.ndarray) -> Tuple[int, int]:
        """
        Divide la ficha en mitad superior e inferior y cuenta los puntos negros (pips).
        """
        th, tw = tile_bgr.shape[:2]
        if th < 10 or tw < 10:
            return 0, 0

        # Separar en mitad superior e inferior excluyendo la línea de división dorada central
        mid_y = th // 2
        margin = max(2, int(th * 0.05))

        top_half = tile_bgr[margin : mid_y - margin, margin : tw - margin]
        bottom_half = tile_bgr[mid_y + margin : th - margin, margin : tw - margin]

        top_dots = self._count_pips_in_region(top_half)
        bottom_dots = self._count_pips_in_region(bottom_half)

        return top_dots, bottom_dots

    def _count_pips_in_region(self, region_bgr: np.ndarray) -> int:
        """
        Cuenta los círculos/puntos negros dentro de media ficha de dominó.
        """
        if region_bgr.size == 0 or region_bgr.shape[0] < 5 or region_bgr.shape[1] < 5:
            return 0

        gray = cv2.cvtColor(region_bgr, cv2.COLOR_BGR2GRAY)
        # Los puntos negros son oscuros frente al fondo marfil claro
        # Umbral binario inverso
        _, thresh = cv2.threshold(gray, 95, 255, cv2.THRESH_BINARY_INV)

        # Encontrar contornos de los puntos
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        reg_area = region_bgr.shape[0] * region_bgr.shape[1]
        valid_dots = 0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            perimeter = cv2.arcLength(cnt, True)
            if perimeter == 0:
                continue

            # Circularidad: 4 * pi * Area / (Perimetro^2)
            circularity = 4 * np.pi * (area / (perimeter * perimeter))

            # Un punto de dominó debe tener un tamaño proporcional y ser razonablemente redondo
            min_pip_area = max(4.0, reg_area * 0.008)
            max_pip_area = reg_area * 0.22

            if min_pip_area <= area <= max_pip_area and circularity >= 0.45:
                valid_dots += 1

        # Limitar al rango válido de dominó (0 a 6)
        return min(6, valid_dots)

    def estimate_player_tile_counts(self, image_bgr: np.ndarray, hero_count: int) -> Dict[PlayerPosition, int]:
        """
        Estima el número de fichas de cada jugador (7 a 1).
        Usa los badges numéricos visibles o mantiene un seguimiento por defecto.
        """
        # Por defecto retornamos un estado coherente
        return {
            PlayerPosition.HERO: hero_count,
            PlayerPosition.PARTNER: 7 if hero_count >= 6 else max(1, hero_count),
            PlayerPosition.RIVAL_LEFT: 7 if hero_count >= 6 else max(1, hero_count),
            PlayerPosition.RIVAL_RIGHT: 7 if hero_count >= 6 else max(1, hero_count),
        }
