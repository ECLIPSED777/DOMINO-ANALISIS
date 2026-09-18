"""
Motor de Lógica, Inferencia Bayesiana y Teoría de Juegos para Dominó Profesional (2 vs 2).
Diseñado específicamente para las reglas competitivas de 'Domino Vamos'.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Set, Dict, Optional
import itertools


class PlayerPosition(str, Enum):
    HERO = "Hero"               # Sur (Usuario - ECLIPSE RAM)
    RIVAL_LEFT = "Rival_Izq"    # Oeste (Jesus - Rival que juega después de Hero)
    PARTNER = "Companero"       # Norte (lucho - Compañero de frente)
    RIVAL_RIGHT = "Rival_Der"   # Este (luifermen - Rival que juega antes de Hero)


# Orden de juego antihorario oficial: Hero -> Rival Izq -> Compañero -> Rival Der -> Hero
TURN_ORDER = [
    PlayerPosition.HERO,
    PlayerPosition.RIVAL_LEFT,
    PlayerPosition.PARTNER,
    PlayerPosition.RIVAL_RIGHT,
]


@dataclass(frozen=True)
class Tile:
    v1: int
    v2: int

    def __post_init__(self):
        # Normalizar siempre con el valor menor primero para hashing y comparación consistentes
        if self.v1 > self.v2:
            object.__setattr__(self, "v1", self.v2)
            object.__setattr__(self, "v2", self.v1)

    @property
    def points(self) -> int:
        return self.v1 + self.v2

    @property
    def is_double(self) -> bool:
        return self.v1 == self.v2

    def contains(self, val: int) -> bool:
        return self.v1 == val or self.v2 == val

    def other(self, val: int) -> int:
        if self.v1 == val:
            return self.v2
        if self.v2 == val:
            return self.v1
        raise ValueError(f"El valor {val} no está presente en la ficha {self}")

    def __repr__(self) -> str:
        return f"[{self.v1}|{self.v2}]"

    def to_dict(self) -> dict:
        return {"v1": self.v1, "v2": self.v2, "points": self.points, "is_double": self.is_double}


# Las 28 fichas fijas del Dominó Clásico
ALL_28_TILES: Set[Tile] = {
    Tile(i, j) for i in range(7) for j in range(i, 7)
}


@dataclass
class MoveRecommendation:
    tile: Tile
    target_end: str          # 'izquierda', 'derecha' o 'salida'
    resulting_end: int       # Nuevo número que queda expuesto en la mesa
    confidence: float        # 0.0 a 1.0
    action_type: str         # 'DOMINADA_DIRECTA', 'FORZAR_TRANQUE', 'APOYO_COMPANERO', 'CASTIGO_RIVAL', etc.
    reasoning: str           # Explicación táctica en lenguaje natural
    score_analysis: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "tile": self.tile.to_dict(),
            "target_end": self.target_end,
            "resulting_end": self.resulting_end,
            "confidence": round(self.confidence, 2),
            "action_type": self.action_type,
            "reasoning": self.reasoning,
            "score_analysis": self.score_analysis
        }


class DominoGameState:
    """
    Rastrea el estado global de la partida de 28 fichas y computa la mejor jugada.
    """
    def __init__(self, target_score: int = 100):
        self.target_score = target_score
        self.score_blue: int = 0  # Equipo Hero + lucho
        self.score_red: int = 0   # Equipo luifermen + Jesus

        # Estado de la mano actual
        self.hero_hand: Set[Tile] = set()
        self.played_tiles: List[Tuple[PlayerPosition, Tile, str]] = []
        self.board_ends: Tuple[Optional[int], Optional[int]] = (None, None)  # (izq, der)

        # Conteo de fichas restantes por jugador (inicia en 7)
        self.player_counts: Dict[PlayerPosition, int] = {
            pos: 7 for pos in PlayerPosition
        }

        # Matriz de Pases (100% determinista):
        # Si un jugador pasa, este conjunto almacena los palos que NO posee
        self.void_suits: Dict[PlayerPosition, Set[int]] = {
            pos: set() for pos in PlayerPosition
        }

        # Historial de palos propuestos/apoyados por cada jugador
        self.favored_suits: Dict[PlayerPosition, List[int]] = {
            pos: [] for pos in PlayerPosition
        }

        # Salidor de la ronda
        self.starter: Optional[PlayerPosition] = None

    def reset_round(self, starter: Optional[PlayerPosition] = None):
        """Reinicia los contadores para una nueva mano de 7 fichas por jugador."""
        self.hero_hand.clear()
        self.played_tiles.clear()
        self.board_ends = (None, None)
        self.player_counts = {pos: 7 for pos in PlayerPosition}
        self.void_suits = {pos: set() for pos in PlayerPosition}
        self.favored_suits = {pos: [] for pos in PlayerPosition}
        self.starter = starter

    def set_hero_hand(self, tiles: List[Tile]):
        """Actualiza las fichas visibles en el atril de Hero."""
        self.hero_hand = set(tiles)
        self.player_counts[PlayerPosition.HERO] = len(self.hero_hand)

    def set_board_ends(self, left: Optional[int], right: Optional[int]):
        """Actualiza los dos extremos abiertos de la mesa."""
        self.board_ends = (left, right)

    def register_play(self, player: PlayerPosition, tile: Tile, target_end: str):
        """Registra la jugada de una ficha en la mesa por un jugador."""
        self.played_tiles.append((player, tile, target_end))
        self.player_counts[player] = max(0, self.player_counts[player] - 1)

        # Si Hero jugó la ficha, removerla de su atril
        if player == PlayerPosition.HERO and tile in self.hero_hand:
            self.hero_hand.remove(tile)

        # Actualizar extremos de la mesa
        left, right = self.board_ends
        if left is None and right is None:
            # Es la primera ficha (salida)
            self.board_ends = (tile.v1, tile.v2)
            self.favored_suits[player].extend([tile.v1, tile.v2])
        elif target_end == "izquierda" and left is not None:
            new_left = tile.other(left)
            self.board_ends = (new_left, right)
            self.favored_suits[player].append(new_left)
        elif target_end == "derecha" and right is not None:
            new_right = tile.other(right)
            self.board_ends = (left, new_right)
            self.favored_suits[player].append(new_right)

    def register_pass(self, player: PlayerPosition):
        """
        Inferencia Determinista:
        Si un jugador pasa, NO tiene ninguno de los dos extremos abiertos actuales.
        """
        left, right = self.board_ends
        if left is not None:
            self.void_suits[player].add(left)
        if right is not None:
            self.void_suits[player].add(right)

    @property
    def played_tiles_set(self) -> Set[Tile]:
        return {t for _, t, _ in self.played_tiles}

    @property
    def unseen_tiles(self) -> Set[Tile]:
        """Conjunto de fichas que no están en la mano de Hero ni han sido jugadas."""
        return ALL_28_TILES - self.hero_hand - self.played_tiles_set

    def get_suit_remaining_counts(self) -> Dict[int, int]:
        """Calcula cuántas fichas de cada número (0 a 6) faltan por salir."""
        counts = {i: 0 for i in range(7)}
        for tile in self.unseen_tiles:
            counts[tile.v1] += 1
            if tile.v1 != tile.v2:
                counts[tile.v2] += 1
        return counts

    def get_legal_moves(self) -> List[Tuple[Tile, str, int]]:
        """
        Retorna lista de jugadas posibles: (ficha, 'izquierda' | 'derecha', nuevo_extremo).
        Si la mesa está vacía, todas las fichas en mano son válidas para salir.
        """
        left, right = self.board_ends

        # Caso mesa vacía (Salida de mano)
        if left is None or right is None:
            return [(t, "salida", t.v1) for t in self.hero_hand]

        legal_moves = []
        for tile in self.hero_hand:
            # Puede jugarse a la izquierda
            if tile.contains(left):
                new_end = tile.other(left)
                legal_moves.append((tile, "izquierda", new_end))
            # Puede jugarse a la derecha (evitando duplicar si es doble y ambos extremos son iguales)
            if tile.contains(right) and not (left == right and tile.is_double and (tile, "izquierda", tile.other(left)) in legal_moves):
                new_end = tile.other(right)
                legal_moves.append((tile, "derecha", new_end))

        return legal_moves

    def evaluate_best_move(self) -> Optional[MoveRecommendation]:
        """
        Algoritmo Principal de Decisión de Teoría de Juegos:
        Evalúa todas las jugadas legales con ponderaciones matemáticas profesionales:
        1. Dominada Directa: Si una jugada deja la mano en 0 fichas, domina la partida.
        2. Análisis de Tranque: Si el juego puede trancarse, calcula la ventaja de puntos.
        3. Explotación de Pases (Void Suits): Cuadrar a palos donde el rival de la derecha pasa.
        4. Apoyo al Compañero (lucho): Favorecer el palo fuerte que inició el compañero.
        5. Control de Fichas Pesadas: Desahogo de puntos altos si hay amenaza de cierre.
        """
        legal_moves = self.get_legal_moves()
        if not legal_moves:
            return None

        # Si sólo hay una ficha en atril y es legal: Dominada instantánea
        if len(self.hero_hand) == 1:
            tile, end, res_end = legal_moves[0]
            return MoveRecommendation(
                tile=tile,
                target_end=end,
                resulting_end=res_end,
                confidence=1.0,
                action_type="DOMINADA_DIRECTA",
                reasoning=f"¡Última ficha en atril! Juega {tile} a la {end} para cantar ¡DOMINÓ! y ganar la mano.",
                score_analysis={"hero_points_left": 0}
            )

        # Caso: Salida de Mano (Mesa vacía)
        left, right = self.board_ends
        if left is None:
            return self._evaluate_opening_move()

        # Evaluación heurística multidimensional de cada jugada legal
        best_move = None
        best_score = -999999.0
        best_reason = ""
        best_action = "JUGADA_ESTANDAR"

        suit_counts = self.get_suit_remaining_counts()
        hero_hand_counts = self._count_suits_in_hand()
        partner_voids = self.void_suits[PlayerPosition.PARTNER]
        rival_left_voids = self.void_suits[PlayerPosition.RIVAL_LEFT]
        rival_right_voids = self.void_suits[PlayerPosition.RIVAL_RIGHT]

        # Estimación de puntos en mano de Hero
        total_hero_points = sum(t.points for t in self.hero_hand)

        for tile, target_end, resulting_end in legal_moves:
            score = 0.0
            reasons = []

            # 1. ¿Esta jugada deja a Hero con 0 fichas?
            if len(self.hero_hand) == 1:
                score += 10000.0
                reasons.append("Canta ¡Dominó!")

            # 2. Descarte de puntos pesados (en fases avanzadas)
            points_weight = tile.points * 1.5
            score += points_weight
            if tile.points >= 9:
                reasons.append(f"Desahoga {tile.points} puntos pesados ({tile})")

            # 3. ¿El rival de la izquierda (Jesus) pasa con este nuevo extremo?
            # En sentido antihorario, Hero le juega a Jesus. Si Jesus no lleva ese número, pasa obligado.
            if resulting_end in rival_left_voids:
                score += 40.0
                reasons.append(f"Obliga a pasar al rival de la izquierda (Jesus es fallo a {resulting_end})")

            # 4. ¿El rival de la derecha (luifermen) pasa?
            if resulting_end in rival_right_voids:
                score += 25.0
                reasons.append(f"Mantiene bloqueado al rival de la derecha")

            # 5. Cuidado con pasar al compañero (lucho): penalización severa si lucho es fallo a ese número
            if resulting_end in partner_voids:
                # Penalizar solo si ambos extremos quedarían vedados para el compañero
                other_end = right if target_end == "izquierda" else left
                if other_end in partner_voids:
                    score -= 55.0
                    reasons.append(f"ADVERTENCIA: Bloquea al compañero (lucho es fallo a {resulting_end})")
                else:
                    score -= 15.0

            # 6. Apoyar al palo favorito del compañero
            partner_favors = self.favored_suits[PlayerPosition.PARTNER]
            if partner_favors and resulting_end == partner_favors[0]:
                score += 35.0
                reasons.append(f"Apoya la salida del compañero (juega al {resulting_end})")

            # 7. Cuadrar a nuestro propio palo dominante en mano
            if hero_hand_counts.get(resulting_end, 0) >= 2:
                score += 20.0
                reasons.append(f"Control de palo propio (tienes {hero_hand_counts[resulting_end]} fichas del {resulting_end})")

            # 8. Evaluación de Tranque Ofensivo
            # Si quedan 0 fichas de ese número en las no vistas, ese extremo queda muerto/cerrado
            if suit_counts.get(resulting_end, 0) == 0:
                # Comprobar si ambos extremos se trancarían
                other_end = right if target_end == "izquierda" else left
                if suit_counts.get(other_end, 0) == 0 or resulting_end == other_end:
                    # El juego se tranca en este turno. ¿Nos conviene?
                    estimated_hero_pts = total_hero_points - tile.points
                    if estimated_hero_pts <= 10:
                        score += 80.0
                        best_action = "FORZAR_TRANQUE"
                        reasons.append(f"¡FORZAR TRANQUE! Quedas con solo {estimated_hero_pts} pts. Victoria altamente favorable")
                    else:
                        score -= 40.0
                        reasons.append(f"Peligro de tranque con puntaje alto ({estimated_hero_pts} pts)")

            # 9. Manejo de dobles
            if tile.is_double:
                # Deshacerse del doble si es alto ([6|6], [5|5], [4|4])
                if tile.points >= 8:
                    score += 15.0
                    reasons.append(f"Suelta el doble pesado {tile}")
                else:
                    score += 5.0

            # Selección del mejor tiro
            if score > best_score:
                best_score = score
                best_move = (tile, target_end, resulting_end)
                best_reason = ". ".join(reasons) if reasons else f"Jugada posicional estándar con {tile}"
                if "Dominó" in best_reason:
                    best_action = "DOMINADA_DIRECTA"
                elif "FORZAR TRANQUE" in best_reason:
                    best_action = "FORZAR_TRANQUE"
                elif "lucho" in best_reason:
                    best_action = "APOYO_COMPANERO"
                elif "Jesus" in best_reason:
                    best_action = "CASTIGO_RIVAL"
                else:
                    best_action = "DESCARTE_ESTRATEGICO"

        # Confianza normalizada
        confidence = min(0.99, max(0.60, 0.65 + (best_score / 150.0)))

        return MoveRecommendation(
            tile=best_move[0],
            target_end=best_move[1],
            resulting_end=best_move[2],
            confidence=confidence,
            action_type=best_action,
            reasoning=best_reason,
            score_analysis={
                "evaluated_moves_count": len(legal_moves),
                "best_move_score": round(best_score, 1),
                "hero_points_after_move": total_hero_points - best_move[0].points
            }
        )

    def _evaluate_opening_move(self) -> MoveRecommendation:
        """
        Regla de Apertura Oficial:
        - Si tenemos el [6|6], es salida obligatoria por reglamento.
        - Si es salida libre:
          - Si tenemos dobles acompañados (ej. [4|4] con 2 o más cuatros), salir por ese doble.
          - Si no tenemos doble acompañado, salir por ficha mixta del palo dominante (como [2|3]).
        """
        # 1. ¿Tenemos el [6|6]?
        d6 = Tile(6, 6)
        if d6 in self.hero_hand:
            return MoveRecommendation(
                tile=d6,
                target_end="salida",
                resulting_end=6,
                confidence=1.0,
                action_type="SALIDA_OBLIGATORIA",
                reasoning="Salida reglamentaria oficial con el Doble Seis [6|6]."
            )

        # 2. Conteo de palos en mano
        counts = self._count_suits_in_hand()
        # Encontrar el palo dominante
        dominant_suit = max(counts.items(), key=lambda x: x[1])[0]

        # ¿Tenemos el doble del palo dominante?
        double_dom = Tile(dominant_suit, dominant_suit)
        if double_dom in self.hero_hand and counts[dominant_suit] >= 3:
            return MoveRecommendation(
                tile=double_dom,
                target_end="salida",
                resulting_end=dominant_suit,
                confidence=0.95,
                action_type="SALIDA_DOBLE_ACOMPANADO",
                reasoning=f"Salida clásica con doble acompañado {double_dom}. Tienes {counts[dominant_suit]} fichas de este palo."
            )

        # 3. Salida mixta recomendada (evitar el [0|0] desacompañado)
        # Buscar ficha mixta que combine los dos palos más fuertes de la mano
        sorted_suits = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        s1 = sorted_suits[0][0]
        s2 = sorted_suits[1][0] if len(sorted_suits) > 1 else s1

        candidate = None
        for t in self.hero_hand:
            if not t.is_double and ((t.v1 == s1 and t.v2 == s2) or (t.v1 == s2 and t.v2 == s1)):
                candidate = t
                break

        if not candidate:
            # Seleccionar la mejor ficha mixta que contenga el palo dominante
            for t in sorted(self.hero_hand, key=lambda x: x.points):
                if not t.is_double and t.contains(s1):
                    candidate = t
                    break

        if not candidate:
            candidate = min(self.hero_hand, key=lambda x: x.points)

        return MoveRecommendation(
            tile=candidate,
            target_end="salida",
            resulting_end=candidate.v1,
            confidence=0.88,
            action_type="SALIDA_MIXTA_ESTRATEGICA",
            reasoning=f"Salida táctica con {candidate}. Inicia tu serie fuerte sin comprometer dobles vulnerables."
        )

    def _count_suits_in_hand(self) -> Dict[int, int]:
        """Cuenta la frecuencia de cada palo (0 a 6) en la mano de Hero."""
        counts = {i: 0 for i in range(7)}
        for t in self.hero_hand:
            counts[t.v1] += 1
            if t.v1 != t.v2:
                counts[t.v2] += 1
        return counts
