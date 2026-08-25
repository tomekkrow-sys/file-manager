_held_windows: list = []


def keep_window(w) -> None:
    """Zapobiega usunięciu okna przez GC po wyjściu z funkcji przełączającej."""
    _held_windows.append(w)
