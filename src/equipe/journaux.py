# src/equipe/journaux.py
"""
Ce que le Middle Office et l'Audit lisent : les journaux du fonds, tels que
le code les a écrits. Aucun chiffre de ce module ne vient de Claude.

    événements      logs/events.db            (bus : types « desk » et « equipe »)
    séances         logs/desk/seances.csv      (relevé chiffré de chaque séance)
    ordres          logs/desk/ordres.csv       (simulés ou réels)
    registre        logs/desk/livre.json
    coûts           logs/equipe/couts.csv
    calibration     logs/equipe/calibration.csv (gravité annoncée / mouvement réel)
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from src.equipe.socle import DOSSIER, NEW_YORK, lire_memos

EVENEMENTS = Path("logs/events.db")
SEANCES = Path("logs/desk/seances.csv")
ORDRES = Path("logs/desk/ordres.csv")
LIVRE = Path("logs/desk/livre.json")
COUTS = DOSSIER / "couts.csv"
CALIBRATION = DOSSIER / "calibration.csv"
CBOE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{}_History.csv"


def bornes(debut: date, fin: Optional[date] = None) -> Tuple[str, str]:
    """Bornes UTC (ISO) couvrant les journées de New York de `debut` à `fin` incluses."""
    fin = fin or debut
    a = datetime.combine(debut, time.min, NEW_YORK).astimezone(timezone.utc)
    b = datetime.combine(fin + timedelta(days=1), time.min, NEW_YORK).astimezone(timezone.utc)
    return a.isoformat(), b.isoformat()


def evenements(debut: date, fin: Optional[date] = None, types: Iterable[str] = ("desk", "equipe"),
               db: Path = EVENEMENTS) -> List[dict]:
    if not db.exists():
        return []
    a, b = bornes(debut, fin)
    types = list(types)
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as c:
        c.row_factory = sqlite3.Row
        lignes = c.execute(
            f"SELECT timestamp, type, severity, title, body, meta FROM events "
            f"WHERE timestamp >= ? AND timestamp < ? AND type IN ({','.join('?' * len(types))}) "
            f"ORDER BY timestamp", (a, b, *types)).fetchall()
    sortie = []
    for l in lignes:
        meta = json.loads(l["meta"] or "{}")
        sortie.append({"heure_utc": l["timestamp"][:19], "type": l["type"],
                       "gravite": l["severity"], "qui": l["title"], "message": l["body"],
                       "moment": meta.get("moment"), "mode": meta.get("mode"),
                       "cout_usd": meta.get("cout_usd")})
    return sortie


def _csv(chemin: Path) -> List[dict]:
    if not chemin.exists():
        return []
    with chemin.open(newline="") as f:
        return list(csv.DictReader(f))


def _jour_ny(horodatage: str) -> date:
    return datetime.fromisoformat(horodatage).astimezone(NEW_YORK).date()


def seances(debut: date, fin: Optional[date] = None, chemin: Path = SEANCES) -> List[dict]:
    fin = fin or debut
    return [s for s in _csv(chemin) if debut.isoformat() <= s["jour"] <= fin.isoformat()]


def ordres(debut: date, fin: Optional[date] = None, chemin: Path = ORDRES) -> List[dict]:
    fin = fin or debut
    return [o for o in _csv(chemin) if debut <= _jour_ny(o["horodatage"]) <= fin]


def couts(debut: date, fin: Optional[date] = None, chemin: Path = COUTS) -> dict:
    """Coûts de l'équipe sur la période, par membre, avec le cumul du mois."""
    fin = fin or debut
    lignes = _csv(chemin)
    periode = [l for l in lignes if debut <= _jour_ny(l["horodatage"]) <= fin]
    mois = [l for l in lignes if _jour_ny(l["horodatage"]).strftime("%Y-%m") == fin.strftime("%Y-%m")]
    par_membre: Dict[str, float] = {}
    for l in periode:
        par_membre[l["membre"]] = par_membre.get(l["membre"], 0.0) + float(l["cout_usd"])
    return {"periode_usd": round(sum(par_membre.values()), 4),
            "par_membre_usd": {k: round(v, 4) for k, v in par_membre.items()},
            "appels": len(periode), "echecs": sum(1 for l in periode if l["statut"] != "ok"),
            "mois_en_cours_usd": round(sum(float(l["cout_usd"]) for l in mois), 4)}


def livre(chemin: Path = LIVRE) -> dict:
    return json.loads(chemin.read_text()) if chemin.exists() else {
        "barreaux": [], "mes": {}, "cycles": [], "note": "registre vide (simulation)"}


# ── Calibration du Research Analyst ─────────────────────────────────────────

def clotures_cboe(indice: str, lire=None) -> Dict[str, float]:
    """{date ISO: clôture} d'un indice du CBOE (SPX, VIX…)."""
    def defaut(url):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 MilanCapital/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode()
    texte = (lire or defaut)(CBOE.format(indice))
    sortie = {}
    for l in csv.DictReader(io.StringIO(texte)):
        col = "CLOSE" if "CLOSE" in l else indice
        sortie[datetime.strptime(l["DATE"], "%m/%d/%Y").date().isoformat()] = float(l[col])
    return sortie


HEURE_LIMITE_BRIEFING = time(9, 30)       # ouverture de New York


def est_tardif(memo: dict) -> bool:
    """Un briefing écrit à ou après l'ouverture de New York."""
    h = datetime.fromisoformat(memo["horodatage"]).astimezone(NEW_YORK).time()
    return h >= HEURE_LIMITE_BRIEFING


def mettre_a_jour_calibration(memos_dossier: Path = DOSSIER / "memos",
                              chemin: Path = CALIBRATION, lire=None) -> List[dict]:
    """Ajoute chaque journée dont on connaît à la fois la météo et la clôture.

    Gravité annoncée le matin contre mouvement réel du S&P 500 (en %) et du VIX
    (en points) ce jour-là. Écrit par le code, pour que le jugement de
    l'Analyst ne dépende pas de ce qu'il en dit.
    """
    deja = {l["jour"] for l in _csv(chemin)}
    try:
        spx, vix = clotures_cboe("SPX", lire), clotures_cboe("VIX", lire)
    except Exception:
        return _csv(chemin)
    jours = sorted(spx)
    nouvelles = []
    if memos_dossier.exists():
        for d in sorted(p.name for p in memos_dossier.iterdir() if p.is_dir()):
            if d in deja or d not in spx:
                continue
            # Seuls les briefings écrits avant l'ouverture comptent : un briefing
            # tardif connaît déjà la séance et fausserait sa propre note (leçon
            # 20261022-pos-3, validée par le CIO le 2026-10-22).
            briefings = [m for m in lire_memos(d, "Research Analyst", memos_dossier)
                         if m["tache"] == "briefing" and m.get("ok") and not est_tardif(m)]
            i = jours.index(d)
            if not briefings or i == 0:
                continue
            veille = jours[i - 1]
            m = briefings[0]["memo"]
            nouvelles.append({
                "jour": d, "gravite": m["gravite"], "alerte": int(bool(m["alerte"])),
                "sp500_pct": round((spx[d] / spx[veille] - 1) * 100, 2),
                "vix_points": round(vix.get(d, float("nan")) - vix.get(veille, float("nan")), 2)})
    if nouvelles:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        nouveau = not chemin.exists()
        with chemin.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["jour", "gravite", "alerte", "sp500_pct", "vix_points"])
            if nouveau:
                w.writeheader()
            w.writerows(nouvelles)
    return _csv(chemin)


# ── Critères du protocole (phase 2) ─────────────────────────────────────────

def criteres(seances_toutes: List[dict], evts: List[dict], livre_: dict) -> dict:
    """État des critères F1-F5 et P1, calculé par le code (docs/desk/phase2_observation.md)."""
    critiques = [e for e in evts if e["type"] == "desk" and e["gravite"] == "critical"]
    ecarts = [e for e in evts if e["type"] == "desk" and "Écart avec le courtier" in e["message"]]
    cycles = livre_.get("cycles", [])
    ref = livre_.get("vl_armement") or (float(seances_toutes[0]["valeur_liquidative"])
                                        if seances_toutes else None)
    derniere = float(seances_toutes[-1]["valeur_liquidative"]) if seances_toutes else None
    mode = seances_toutes[-1]["mode"] if seances_toutes else None
    return {
        "mode": mode,
        "seances_enregistrees": len(seances_toutes),
        "F1_incidents_critiques": len(critiques),
        "F2_ecarts_avec_le_courtier": len(ecarts),
        "F3_F4_barreaux_fermes": len(cycles),
        "F3_F4_note": None if cycles else "Pas encore mesurable : aucun barreau fermé.",
        "F5_note": "Exposition avant couverture relevée à chaque séance (seances.csv).",
        "P1_reference": ref, "P1_derniere_valeur": derniere,
        "P1_resultat_usd": round(derniere - ref, 2) if ref and derniere else None,
        "P1_note": ("Référence : valeur à l'armement." if livre_.get("vl_armement")
                    else "Simulation : référence = première séance enregistrée."),
    }
