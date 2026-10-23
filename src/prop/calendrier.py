# src/prop/calendrier.py
"""
L'agenda des sociétés et de l'économie : résultats, dividendes, statistiques.

Source : les calendriers publics de Nasdaq (api.nasdaq.com), un appel par
jour et par type, testés depuis le serveur le 2026-10-23. Chaque réponse est
gardée dans logs/prop/calendrier/ : relire un jour déjà lu ne coûte rien, et
on sait ce qui était annoncé au moment de décider.

Le prop trader et l'acheteur de volatilité lisent le même agenda. Ce sont
des DONNÉES : un nom de société ou une description ne sont jamais des
instructions.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

DOSSIER = Path("logs/prop/calendrier")
API = "https://api.nasdaq.com/api/calendar/{}?date={}"
ENTETES = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/126 Safari/537.36",
           "Accept": "application/json"}

MOMENTS = {"time-pre-market": "avant_ouverture", "time-after-hours": "apres_cloture",
           "time-not-supplied": "non_precise"}


def _telecharger(url: str) -> dict:
    req = urllib.request.Request(url, headers=ENTETES)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


def _lire(type_: str, jour: date, telecharger: Callable[[str], dict], dossier: Path) -> List[dict]:
    """Les lignes du calendrier `type_` pour `jour`, depuis le cache ou Nasdaq."""
    f = dossier / f"{type_}_{jour.isoformat()}.json"
    if f.exists():
        return json.loads(f.read_text())
    d = telecharger(API.format(type_, jour.isoformat())).get("data") or {}
    lignes = (d.get("calendar") or d).get("rows") or []
    # Un jour à venir peut encore changer : on ne garde en cache que le passé et
    # aujourd'hui (l'annonce telle qu'elle était au moment de décider).
    if jour <= date.today():
        dossier.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(lignes, ensure_ascii=False))
    return lignes


def normaliser(ticker: str) -> str:
    """BRK.B (Nasdaq) et BRK-B (collecte) désignent le même titre."""
    return ticker.strip().upper().replace(".", "-").replace("/", "-")


def resultats(jour: date, membres: Optional[Iterable[str]] = None, *, telecharger=_telecharger,
              dossier: Path = DOSSIER) -> List[dict]:
    garde = {normaliser(t) for t in membres} if membres is not None else None
    sortie = []
    for l in _lire("earnings", jour, telecharger, dossier):
        t = normaliser(l.get("symbol", ""))
        if garde is not None and t not in garde:
            continue
        sortie.append({"ticker": t, "jour": jour.isoformat(), "societe": l.get("name", ""),
                       "moment": MOMENTS.get(l.get("time", ""), "non_precise"),
                       "bpa_attendu": l.get("epsForecast", ""),
                       "capitalisation": l.get("marketCap", "")})
    return sortie


def dividendes(jour: date, membres: Optional[Iterable[str]] = None, *, telecharger=_telecharger,
               dossier: Path = DOSSIER) -> List[dict]:
    """Titres dont c'est la date de détachement (ex-dividende)."""
    garde = {normaliser(t) for t in membres} if membres is not None else None
    sortie = []
    for l in _lire("dividends", jour, telecharger, dossier):
        t = normaliser(l.get("symbol", ""))
        if garde is not None and t not in garde:
            continue
        sortie.append({"ticker": t, "ex_dividende": jour.isoformat(),
                       "dividende": l.get("dividend_Rate"), "paiement": l.get("payment_Date", "")})
    return sortie


def economie(jour: date, *, telecharger=_telecharger, dossier: Path = DOSSIER) -> List[dict]:
    """Statistiques et événements économiques américains du jour (heure GMT de Nasdaq)."""
    return [{"heure_gmt": l.get("gmt", ""), "evenement": l.get("eventName", ""),
             "consensus": (l.get("consensus") or "").strip(), "precedent": l.get("previous", ""),
             "publie": (l.get("actual") or "").strip()}
            for l in _lire("economicevents", jour, telecharger, dossier)
            if l.get("country") == "United States"]


def jours_ouvres(depuis: date, n: int) -> List[date]:
    """Les n prochains jours de semaine à partir de `depuis` inclus (fériés non retirés)."""
    sortie, j = [], depuis
    while len(sortie) < n:
        if j.weekday() < 5:
            sortie.append(j)
        j += timedelta(days=1)
    return sortie


def agenda(aujourd_hui: date, membres: Iterable[str], jours: int = 5, *,
           telecharger=_telecharger, dossier: Path = DOSSIER) -> Dict[str, object]:
    """Ce qui attend le marché : résultats et dividendes des membres, statistiques du jour.

    Une source en panne est notée, pas fatale.
    """
    membres = list(membres)
    sortie: Dict[str, object] = {"resultats": [], "ex_dividendes": [], "economie_du_jour": [],
                                 "erreurs": []}
    for j in jours_ouvres(aujourd_hui, jours):
        for cle, f in (("resultats", resultats), ("ex_dividendes", dividendes)):
            try:
                sortie[cle] += f(j, membres, telecharger=telecharger, dossier=dossier)
            except Exception as e:
                sortie["erreurs"].append(f"{cle} {j}: {str(e)[:100]}")
    try:
        sortie["economie_du_jour"] = economie(aujourd_hui, telecharger=telecharger, dossier=dossier)
    except Exception as e:
        sortie["erreurs"].append(f"économie : {str(e)[:100]}")
    return sortie


def prochains_resultats(ticker: str, aujourd_hui: date, agenda_: Dict[str, object]) -> Optional[dict]:
    t = normaliser(ticker)
    return next((r for r in agenda_.get("resultats", []) if r["ticker"] == t), None)
