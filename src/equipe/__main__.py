# src/equipe/__main__.py
"""
Les tâches planifiées de l'équipe.

    python -m src.equipe briefing      # Research Analyst, 8 h 30 (New York)
    python -m src.equipe veille        # Research Analyst, toutes les 30 min en séance

Le Risk Manager ne se lance pas d'ici : il est appelé par la séance du desk,
à chaque ouverture proposée (src/options/desk.py).
"""
from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Tâches de l'équipe de Milan Capital.")
    p.add_argument("tache", choices=["briefing", "veille"])
    tache = p.parse_args(argv).tache
    if tache == "briefing":
        from src.equipe import research
        return 0 if research.briefing().ok else 1
    from src.equipe import veille
    veille.passage()
    return 0


if __name__ == "__main__":
    sys.exit(main())
