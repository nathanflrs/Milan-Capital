# src/acheteur/strategie.py
"""
La règle de l'acheteur de volatilité (docs/desk/pods.md, section 2), en
logique pure : quels titres, quel mouvement habituel, acheter ou non,
combien.

Un straddle à la monnaie (un call et un put au même prix d'exercice) gagne
si l'action bouge plus que son prix, dans un sens ou dans l'autre. Le marché
fixe ce prix ; la règle n'achète que lorsqu'il est nettement inférieur au
mouvement que la société fait d'habitude le jour de ses résultats.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable, List, Optional, Sequence

import pandas as pd

UNIVERS = 50
SEUIL = 0.85
HISTORIQUE = 8
PRIME_MAX = 0.005
ENGAGE_MAX = 0.02
OUVERTURE, CLOTURE = time(9, 30), time(16, 0)


def univers(table: pd.DataFrame, n: int = UNIVERS) -> List[str]:
    """Les n titres les plus échangés en dollars (moyenne 20 jours)."""
    return list(table["volume_dollars_20j_m"].dropna().sort_values(ascending=False).head(n).index)


def prochain_jour_ouvre(j: date) -> date:
    j += timedelta(days=1)
    while j.weekday() >= 5:
        j += timedelta(days=1)
    return j


def jour_de_reaction(publication: datetime) -> date:
    """La séance où le marché réagit : le lendemain si publié après la clôture, sinon le jour même."""
    return prochain_jour_ouvre(publication.date()) if publication.time() >= CLOTURE else publication.date()


def candidats(resultats: Iterable[dict], aujourd_hui: date, eligibles: Iterable[str]) -> List[dict]:
    """Publications de ce soir (après la clôture) ou de demain matin (avant l'ouverture)."""
    eligibles = set(eligibles)
    demain = prochain_jour_ouvre(aujourd_hui)
    garde, societes = [], set()
    for r in resultats:
        if r["ticker"] not in eligibles:
            continue
        # GOOG et GOOGL : une seule société, un seul pari.
        societe = (r.get("societe") or r["ticker"]).lower()
        if societe in societes:
            continue
        if (r["jour"] == aujourd_hui.isoformat() and r["moment"] == "apres_cloture") or \
                (r["jour"] == demain.isoformat() and r["moment"] == "avant_ouverture"):
            garde.append({**r, "reaction": demain.isoformat()})
            societes.add(societe)
    return garde


def mouvement_habituel(clotures: pd.Series, publications: Sequence[datetime],
                       n: int = HISTORIQUE) -> Optional[dict]:
    """Mouvement absolu moyen, clôture avant → clôture du jour de réaction, sur les n derniers résultats.

    `clotures` : clôtures quotidiennes indexées par date. Les publications sans
    les deux clôtures (trop anciennes, à venir) sont ignorées.
    """
    c = clotures.dropna()
    c.index = pd.DatetimeIndex(c.index).tz_localize(None).normalize()
    mouvements = []
    for p in sorted(publications, reverse=True):
        reaction = pd.Timestamp(jour_de_reaction(p))
        avant = c.loc[:reaction - pd.Timedelta(days=1)]
        if reaction not in c.index or avant.empty or (reaction - avant.index[-1]).days > 5:
            continue
        mouvements.append(abs(c.loc[reaction] / avant.iloc[-1] - 1))
        if len(mouvements) == n:
            break
    if len(mouvements) < min(4, n):         # trop peu d'historique pour juger
        return None
    return {"moyenne": sum(mouvements) / len(mouvements), "mouvements": mouvements}


def premiere_echeance(echeances: Iterable[str], reaction: date) -> Optional[str]:
    """La première échéance qui expire APRÈS le jour de réaction (il reste du temps à la sortie)."""
    apres = sorted(e for e in echeances if datetime.strptime(e, "%Y%m%d").date() > reaction)
    return apres[0] if apres else None


def _pct(x: float, decimales: int) -> str:
    return f"{x * 100:.{decimales}f} %".replace(".", ",")


@dataclass(frozen=True)
class Avis:
    acheter: bool
    prevu: float                     # prix du straddle ÷ cours
    habituel: float
    ratio: float
    motif: str


def juger(prix_straddle: float, spot: float, habituel: float, seuil: float = SEUIL) -> Avis:
    prevu = prix_straddle / spot
    ratio = prevu / habituel if habituel else math.inf
    acheter = ratio < seuil
    motif = (f"mouvement prévu {_pct(prevu, 1)} contre {_pct(habituel, 1)} d'habitude "
             f"({_pct(ratio, 0)} ; achat sous {_pct(seuil, 0)})")
    return Avis(acheter, prevu, habituel, ratio, motif)


def lots(prime_par_lot_usd: float, vl: float, engage_usd: float, facteur: float = 1.0) -> int:
    """Lots permis : prime ≤ 0,5 % de la VL par straddle, 2 % au total en cours."""
    if prime_par_lot_usd <= 0:
        return 0
    budget = min(PRIME_MAX * vl, ENGAGE_MAX * vl - engage_usd) * facteur
    return max(0, int(math.floor(budget / prime_par_lot_usd)))
