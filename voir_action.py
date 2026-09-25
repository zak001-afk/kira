# -*- coding: utf-8 -*-
"""Affiche l'action que KIRA comprend pour une phrase.

Usage :
    python voir_action.py cherche dans le c les dossiers dell
    python voir_action.py            (puis écris la phrase)
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from kira_open import parse_open_command


def main():
    phrase = " ".join(sys.argv[1:]).strip()
    if not phrase:
        try:
            phrase = input("Écris la phrase exacte dite à KIRA : ").strip()
        except EOFError:
            return
    print()
    print("Phrase :", phrase)
    print("Action :", parse_open_command(phrase))
    print()
    print("(None = KIRA n'y voit pas d'action -> partie au chat)")


if __name__ == "__main__":
    main()
