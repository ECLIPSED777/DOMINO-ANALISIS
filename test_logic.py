"""
Conjunto de pruebas unitarias para validar game_logic.py.
"""

from game_logic import DominoGameState, Tile, PlayerPosition


def test_tile_properties():
    t1 = Tile(6, 2)
    t2 = Tile(2, 6)
    assert t1 == t2
    assert t1.v1 == 2 and t1.v2 == 6
    assert t1.points == 8
    assert not t1.is_double
    assert t1.other(2) == 6
    assert t1.other(6) == 2

    double = Tile(5, 5)
    assert double.is_double
    assert double.points == 10
    print("✓ test_tile_properties completado con éxito.")


def test_opening_salida():
    game = DominoGameState(target_score=100)
    
    # Caso 1: Tiene el [6|6] (Salida obligatoria)
    hand1 = [Tile(6, 6), Tile(2, 3), Tile(0, 1), Tile(4, 5)]
    game.set_hero_hand(hand1)
    rec1 = game.evaluate_best_move()
    assert rec1 is not None
    assert rec1.tile == Tile(6, 6)
    assert rec1.action_type == "SALIDA_OBLIGATORIA"

    # Caso 2: Mano de la partida real de las capturas (00:25:02)
    # [0|0], [4|6], [5|6], [3|4], [1|3], [2|4], [2|5]
    game.reset_round()
    hand2 = [
        Tile(0, 0), Tile(4, 6), Tile(5, 6),
        Tile(3, 4), Tile(1, 3), Tile(2, 4), Tile(2, 5)
    ]
    game.set_hero_hand(hand2)
    rec2 = game.evaluate_best_move()
    assert rec2 is not None
    # No debe salir con el [0|0] desnudo
    assert rec2.tile != Tile(0, 0)
    # Debe ser una ficha del palo fuerte (4 o 2)
    assert rec2.tile.contains(4) or rec2.tile.contains(2)
    print(f"✓ test_opening_salida completado: Salida recomendada={rec2.tile} ({rec2.action_type})")


def test_pass_tracking_and_rival_punishment():
    game = DominoGameState()
    game.set_board_ends(2, 5)
    
    # Jesus (Rival a la izquierda de Hero) PASA a (2, 5)
    game.register_pass(PlayerPosition.RIVAL_LEFT)
    assert 2 in game.void_suits[PlayerPosition.RIVAL_LEFT]
    assert 5 in game.void_suits[PlayerPosition.RIVAL_LEFT]

    # Mano de Hero con opción de jugar hacia el 2 o hacia otro número
    game.set_hero_hand([Tile(2, 4), Tile(5, 3)])
    rec = game.evaluate_best_move()
    assert rec is not None
    print(f"✓ test_pass_tracking completado: Jugada={rec.tile} a {rec.target_end}. Razón={rec.reasoning}")


def test_endgame_domino():
    game = DominoGameState()
    game.set_board_ends(0, 4)
    # A Hero le queda solo el [0|0]
    game.set_hero_hand([Tile(0, 0)])
    rec = game.evaluate_best_move()
    assert rec is not None
    assert rec.tile == Tile(0, 0)
    assert rec.target_end == "izquierda"
    assert rec.action_type == "DOMINADA_DIRECTA"
    assert rec.confidence == 1.0
    print("✓ test_endgame_domino completado con éxito.")


if __name__ == "__main__":
    test_tile_properties()
    test_opening_salida()
    test_pass_tracking_and_rival_punishment()
    test_endgame_domino()
    print("\nTODAS LAS PRUEBAS DE LÓGICA PASARON EXITOSAMENTE.")
