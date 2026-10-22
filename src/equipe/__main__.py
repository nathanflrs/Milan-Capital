# src/equipe/__main__.py
"""
Les tâches de l'équipe, et les décisions du CIO.

Tâches planifiées (heure de New York, lundi-vendredi) :
    python -m src.equipe briefing      # Research Analyst, 8 h 30
    python -m src.equipe veille        # Research Analyst, toutes les 30 min en séance
    python -m src.equipe rapport       # Middle Office, 16 h 30
    python -m src.equipe audit         # Audit : post-mortem du jour s'il y a lieu, 16 h 50
    python -m src.equipe revue         # Audit : revue de la semaine, vendredi 17 h 15

Décisions du CIO sur les leçons proposées par l'Audit :
    python -m src.equipe propositions             # celles en attente
    python -m src.equipe valider <id>             # → carnet du membre
    python -m src.equipe rejeter <id> "raison"

Le Risk Manager ne se lance pas d'ici : la séance du desk l'appelle à chaque
ouverture proposée (src/options/desk.py).
"""
from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Tâches de l'équipe de Milan Capital.")
    p.add_argument("tache", choices=["briefing", "veille", "rapport", "audit", "revue",
                                     "propositions", "valider", "rejeter"])
    p.add_argument("id", nargs="?")
    p.add_argument("raison", nargs="?", default="")
    a = p.parse_args(argv)

    if a.tache == "briefing":
        from src.equipe import research
        return 0 if research.briefing().ok else 1
    if a.tache == "veille":
        from src.equipe import veille
        veille.passage()
        return 0
    if a.tache == "rapport":
        from src.equipe import middle_office
        return 0 if middle_office.rapport().ok else 1
    from src.equipe import audit
    if a.tache == "audit":
        r = audit.postmortem()
        return 0 if r is None or r.ok else 1
    if a.tache == "revue":
        return 0 if audit.revue().ok else 1
    if a.tache == "propositions":
        attente = [x for x in audit._propositions() if x["statut"] == "en_attente"]
        for x in attente:
            regle = "  ⚠ change une règle écrite" if x["change_une_regle"] else ""
            print(f"{x['id']}  [{x['membre']}]{regle}\n  {x['lecon']}\n  pourquoi : {x['justification']}\n")
        print(f"{len(attente)} proposition(s) en attente.")
        return 0
    if not a.id:
        p.error("il faut l'identifiant de la proposition")
    d = audit.decider(a.id, a.tache == "valider", a.raison)
    print(f"{d['id']} : {d['statut']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
