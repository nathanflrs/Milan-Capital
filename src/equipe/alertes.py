# src/equipe/alertes.py
"""
L'état d'alerte du desk, posé par le Research Analyst.

Une alerte est un mémo du Research Analyst dont le champ `alerte` est vrai.
Elle vaut pour le jour où elle a été posée (heure de New York) : le
lendemain, le briefing du matin repart de zéro. Tant qu'elle court, toute
ouverture est freinée d'office, sans même consulter le Risk Manager
(docs/desk/equipe.md, section 2).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from src.equipe.socle import DOSSIER, lire_memos

RESEARCH = "Research Analyst"


def alerte_du_jour(jour: date, dossier: Path = DOSSIER / "memos") -> Optional[dict]:
    """Le dernier mémo d'alerte du jour, ou None."""
    alertes = [m for m in lire_memos(jour.isoformat(), RESEARCH, dossier)
               if m.get("ok") and (m.get("memo") or {}).get("alerte")]
    return alertes[-1] if alertes else None
