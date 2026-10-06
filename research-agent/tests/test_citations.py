"""Les crochets de citation [1] ne sortent jamais du flux de tokens.

Le streaming peut couper une référence en deux entre deux tokens : le filtre
doit la retenir en attente, puis la retirer une fois complète — sans abîmer
les liens markdown du type [2026](url).

    python tests/test_citations.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from atlas.agent import _strip_citations  # noqa: E402


def run(chunks: list[str]) -> str:
    return "".join(_strip_citations(iter(chunks)))


def main() -> None:
    # Référence complète en un seul chunk, avec espace avant : disparaît.
    assert run(["Le C++ [2, 5] est compilé [6]."]) == "Le C++ est compilé."

    # Référence coupée entre deux tokens : rien ne fuit, l'espacement reste juste.
    assert run(["par Bjarne [1", ", 5] aux Bell Labs."]) \
        == "par Bjarne aux Bell Labs."

    # Références adjacentes en fin de phrase.
    assert run(["Travail en équipe [1, 2] utile [8]. Fin."]) \
        == "Travail en équipe utile. Fin."

    # Texte ordinaire : intact.
    plain = "Réponse simple.\nToujours intacte."
    assert run([plain]) == plain

    # Lien markdown à chiffres : conservé tel quel.
    link = "Voir [2026](https://ex.org/a) pour plus."
    assert run([link]) == link

    # Référence restée inachevée à la fin : supprimée.
    assert run(["texte [12"]) == "texte"

    print("TESTS CITATIONS OK")


if __name__ == "__main__":
    main()
