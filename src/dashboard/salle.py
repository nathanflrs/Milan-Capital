# src/dashboard/salle.py
"""
L'API de la salle des marchés (dashboard v2).

Tout ce que la salle affiche vient d'ici, et tout ce qu'elle lit vient des
journaux écrits par le code (src/equipe/journaux.py) : aucun chiffre n'est
recalculé dans le navigateur. Une seule action d'écriture : la décision du
CIO sur une leçon de l'Audit.

Le direct passe par le flux d'événements existant (/api/events/stream) :
téléphone et Mac reçoivent les mêmes événements, au même moment.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.equipe import journaux as jx
from src.equipe.socle import DOSSIER, NEW_YORK, lire_memos, slug

MEMOS = DOSSIER / "memos"
CHAINES = Path("logs/desk/chaines")

EQUIPE = [
    {"titre": "CIO", "nature": "humain", "modele": None,
     "mission": "Fixe la charte et les protocoles, valide les leçons, décide au point d'étape."},
    {"titre": "Volatility Trader", "nature": "code", "modele": None,
     "mission": "Ouvre un barreau par semaine et ferme ceux à 7 jours, selon le protocole."},
    {"titre": "Execution Trader", "nature": "code", "modele": None,
     "mission": "Couvre l'exposition au marché en micro-futures MES, deux fois par jour."},
    {"titre": "Risk Manager", "nature": "claude", "modele": "Opus 5.5",
     "mission": "Relit chaque ouverture et peut la freiner, chiffres à l'appui."},
    {"titre": "Research Analyst", "nature": "claude", "modele": "Sonnet 5.5 · Haiku 5.5",
     "mission": "Météo du matin, veille des nouvelles en séance, alerte en cas de choc."},
    {"titre": "Middle Office", "nature": "claude", "modele": "Sonnet 5.5",
     "mission": "Rapproche le registre et le courtier, écrit le rapport du soir."},
    {"titre": "Audit", "nature": "claude", "modele": "Sonnet 5.5",
     "mission": "Post-mortems, revue du vendredi, leçons proposées au CIO."},
]

# Emploi du temps, heure de New York, du lundi au vendredi (vendredi seul : 4).
AGENDA = [
    ("Research Analyst", "briefing", [time(8, 30)], None),
    ("Research Analyst", "veille", [time(9, 30)] + [time(h, m) for h in range(10, 16) for m in (0, 30)]
     + [time(16, 0)], None),
    ("Volatility Trader", "séance", [time(10, 30), time(15, 30)], None),
    ("Execution Trader", "couverture", [time(10, 30), time(15, 30)], None),
    ("Risk Manager", "relecture des ouvertures", [time(10, 30), time(15, 30)], None),
    ("Middle Office", "rapport du soir", [time(16, 30)], None),
    ("Audit", "post-mortem s'il y a lieu", [time(16, 50)], None),
    ("Audit", "revue de la semaine", [time(17, 15)], 4),
]


def prochaine(heures: List[time], jour_semaine: Optional[int],
              maintenant: Optional[datetime] = None) -> datetime:
    """Prochaine occurrence (UTC) d'une tâche planifiée à New York."""
    m = (maintenant or datetime.now(timezone.utc)).astimezone(NEW_YORK)
    for decalage in range(0, 9):
        j = m.date() + timedelta(days=decalage)
        if j.weekday() > 4 or (jour_semaine is not None and j.weekday() != jour_semaine):
            continue
        for h in sorted(heures):
            t = datetime.combine(j, h, NEW_YORK)
            if t > m:
                return t.astimezone(timezone.utc)
    raise ValueError("aucune occurrence")


def prochaines_taches(maintenant: Optional[datetime] = None) -> List[dict]:
    t = [{"membre": qui, "tache": quoi,
          "a": prochaine(h, js, maintenant).isoformat(timespec="minutes")}
         for qui, quoi, h, js in AGENDA]
    return sorted(t, key=lambda x: x["a"])


# ── Le desk ─────────────────────────────────────────────────────────────────

def _derniere_chaine(dossier: Path = CHAINES):
    if not dossier.exists():
        return None
    fichiers = sorted(dossier.glob("*.parquet"))
    return fichiers[-1] if fichiers else None


def courbe_de_gain(barreaux: List[dict], spot: Optional[float], points: int = 61) -> List[dict]:
    """Gain du livre à l'échéance, en dollars, pour des cours de ±15 % autour du spot."""
    if not barreaux or not spot:
        return []
    sortie = []
    for i in range(points):
        s = spot * (0.85 + 0.30 * i / (points - 1))
        total = 0.0
        for b in barreaux:
            jambes = ((b["aile_put"], "P", +1), (b["centre"], "P", -1),
                      (b["centre"], "C", -1), (b["aile_call"], "C", +1))
            valeur = sum(sens * (max(k - s, 0) if t == "P" else max(s - k, 0))
                         for k, t, sens in jambes)
            total += (valeur + b["credit"]) * 100 * b["lots"]
        sortie.append({"cours": round(s, 2), "gain_usd": round(total, 2)})
    return sortie


EQUITY_V1 = Path("logs/equity_curve.csv")
DEBUT_V2 = "2026-10-22"     # charte du desk de volatilité commitée (46a1654)


def historique_valeur(v1: Path = EQUITY_V1, seances_chemin: Path = jx.SEANCES) -> dict:
    """La valeur du fonds jour par jour : la v1 (relevé quotidien de l'arène,
    depuis le 2026-08-13) puis la v2 (relevé de séance du desk). Une valeur
    par jour, la dernière connue ; le relevé du desk l'emporte sur celui de la v1.

    La v1 n'est pas effacée : la salle la montre, avec un repère au passage
    au desk de volatilité (« ne jamais oublier la version actuelle »).
    """
    par_jour: Dict[str, Tuple[float, str]] = {}
    for l in jx._csv(v1):
        try:
            par_jour[l["date"]] = (float(l["netliq"]), "v1")
        except (KeyError, ValueError):
            continue
    for l in jx._csv(seances_chemin):
        par_jour[l["jour"]] = (float(l["valeur_liquidative"]), "v2")
    points = [{"jour": j, "valeur": round(v, 2), "epoque": e} for j, (v, e) in sorted(par_jour.items())]
    if points:
        depart = points[0]["valeur"]
        for p in points:
            p["resultat_depuis_debut"] = round(p["valeur"] - depart, 2)
    return {"points": points, "debut_v2": DEBUT_V2}


def etat(maintenant: Optional[datetime] = None) -> dict:
    m = (maintenant or datetime.now(timezone.utc)).astimezone(NEW_YORK)
    aujourd_hui = m.date()
    toutes = jx.seances(date(2026, 1, 1), aujourd_hui)
    du_jour = [s for s in toutes if s["jour"] == aujourd_hui.isoformat()]
    livre = jx.livre()
    derniere = toutes[-1] if toutes else None
    histo = historique_valeur()
    points = histo["points"]
    # Sans relevé de séance, la dernière valeur connue est celle du relevé
    # quotidien de la v1 : on l'affiche, en le disant (source_valeur).
    if derniere:
        valeur, source = float(derniere["valeur_liquidative"]), "seance"
    elif points:
        valeur, source = points[-1]["valeur"], f"releve_{points[-1]['epoque']}"
    else:
        valeur, source = None, None
    reference = livre.get("vl_armement") or (float(toutes[0]["valeur_liquidative"]) if toutes else None)
    plus_haut = max([livre.get("plus_haut") or 0.0] + [float(s["valeur_liquidative"]) for s in toutes]
                    + [p["valeur"] for p in points]) or None
    from src.options import risque as rq
    etat_charte = rq.etat_baisse(valeur, plus_haut) if valeur and plus_haut else None

    spot = None
    chaine = _derniere_chaine()
    if chaine is not None:
        try:
            import pandas as pd
            spot = float(pd.read_parquet(chaine, columns=["spot"])["spot"].iloc[0])
        except Exception:
            spot = None
    barreaux = []
    for b in livre.get("barreaux", []):
        e = datetime.strptime(b["echeance"], "%Y%m%d").date()
        barreaux.append({**{k: b[k] for k in ("echeance", "aile_put", "centre", "aile_call", "lots",
                                              "ouvert_le", "credit", "perte_max_lot")},
                         "jours": (e - aujourd_hui).days})
    return {
        "maintenant": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": derniere["mode"] if derniere else "simulation",
        "valeur": valeur, "source_valeur": source,
        "date_valeur": (derniere["jour"] if derniere else points[-1]["jour"] if points else None),
        "reference": reference,
        "resultat_depuis_reference": round(valeur - reference, 2) if valeur and reference else None,
        "resultat_du_jour": (round(float(du_jour[-1]["valeur_liquidative"])
                                   - float(du_jour[0]["valeur_liquidative"]), 2)
                             if len(du_jour) >= 2 else None),
        "plus_haut": plus_haut,
        "baisse_depuis_plus_haut_pct": round((valeur / plus_haut - 1) * 100, 2) if valeur and plus_haut else None,
        "etat_charte": etat_charte,
        "seuils_charte_pct": {"reduire": -8, "arret": -15},
        "barreaux": barreaux, "mes": livre.get("mes", {}),
        "cycles_fermes": len(livre.get("cycles", [])),
        "derniere_seance": derniere,
        "xsp": spot, "courbe_de_gain": courbe_de_gain(livre.get("barreaux", []), spot),
        "prochaines_taches": prochaines_taches(maintenant)[:6],
        "historique": histo,
        "couts": jx.couts(aujourd_hui),
    }


# ── L'équipe ────────────────────────────────────────────────────────────────

def statut_membre(evts: List[dict]) -> str:
    """Le voyant : en_veille, au_travail, termine, alerte, echec — d'après les événements du jour."""
    if not evts:
        return "en_veille"
    dernier = evts[-1]
    if dernier.get("phase") == "debut":
        return "au_travail"
    if dernier["gravite"] == "critical":
        return "alerte"
    if dernier.get("ok") is False:
        return "echec"
    return "termine"


def equipe(maintenant: Optional[datetime] = None) -> List[dict]:
    m = (maintenant or datetime.now(timezone.utc)).astimezone(NEW_YORK)
    meta_evts = _meta_evenements(m.date())
    agenda = prochaines_taches(maintenant)
    couts = jx.couts(m.date())["par_membre_usd"]
    sortie = []
    for membre in EQUIPE:
        t = membre["titre"]
        siens = [e for e in meta_evts if e["qui"] == t]
        fins = [e for e in siens if e.get("phase") != "debut"]
        prochain = next((a for a in agenda if a["membre"] == t), None)
        sortie.append({**membre, "slug": slug(t),
                       "statut": "en_veille" if t == "CIO" else statut_membre(siens),
                       "derniere_action": fins[-1] if fins else None,
                       "actions_du_jour": len(fins),
                       "prochaine_tache": prochain,
                       "cout_du_jour_usd": couts.get(t, 0.0)})
    return sortie


def _meta_evenements(jour: date) -> List[dict]:
    """Événements du jour avec les champs de meta utiles à la salle (phase, ok, tâche)."""
    import sqlite3
    if not jx.EVENEMENTS.exists():
        return []
    a, b = jx.bornes(jour)
    with sqlite3.connect(f"file:{jx.EVENEMENTS}?mode=ro", uri=True) as c:
        lignes = c.execute("SELECT timestamp, type, severity, title, body, meta FROM events "
                           "WHERE timestamp >= ? AND timestamp < ? AND type IN ('desk','equipe') "
                           "ORDER BY timestamp", (a, b)).fetchall()
    sortie = []
    for ts, typ, sev, qui, msg, meta in lignes:
        meta = json.loads(meta or "{}")
        sortie.append({"heure_utc": ts[:19], "type": typ, "gravite": sev, "qui": qui, "message": msg,
                       "tache": meta.get("tache") or meta.get("moment"), "phase": meta.get("phase"),
                       "ok": meta.get("ok"), "cout_usd": meta.get("cout_usd"),
                       "mode": meta.get("mode")})
    return sortie


def historique(membre_slug: str, jours: int = 14, maintenant: Optional[datetime] = None) -> dict:
    titre = next((m["titre"] for m in EQUIPE if slug(m["titre"]) == membre_slug), None)
    if titre is None:
        raise KeyError(membre_slug)
    m = (maintenant or datetime.now(timezone.utc)).astimezone(NEW_YORK)
    memos = []
    for d in range(jours):
        j = (m.date() - timedelta(days=d)).isoformat()
        memos += [x for x in lire_memos(j, titre, MEMOS)]
    carnet = DOSSIER / "carnets" / f"{membre_slug}.md"
    return {"titre": titre, "memos": sorted(memos, key=lambda x: x["horodatage"], reverse=True),
            "carnet": carnet.read_text() if carnet.exists() else None}


# ── Rapports, décisions, protocole ──────────────────────────────────────────

def rapports(jours: int = 30, maintenant: Optional[datetime] = None) -> List[dict]:
    m = (maintenant or datetime.now(timezone.utc)).astimezone(NEW_YORK)
    sortie = []
    for d in range(jours):
        j = (m.date() - timedelta(days=d)).isoformat()
        for x in lire_memos(j, dossier=MEMOS):
            if (x["membre"], x["tache"]) in (("Middle Office", "rapport"), ("Audit", "revue"),
                                             ("Audit", "postmortem")):
                sortie.append(x)
    return sorted(sortie, key=lambda x: x["horodatage"], reverse=True)


def couts_par_jour(jours: int = 30) -> List[dict]:
    par: Dict[str, Dict[str, float]] = {}
    for l in jx._csv(jx.COUTS):
        j = jx._jour_ny(l["horodatage"]).isoformat()
        par.setdefault(j, {})
        par[j][l["membre"]] = par[j].get(l["membre"], 0.0) + float(l["cout_usd"])
    return [{"jour": j, "par_membre_usd": {k: round(v, 4) for k, v in m.items()},
             "total_usd": round(sum(m.values()), 4)} for j, m in sorted(par.items())][-jours:]


def protocole() -> dict:
    debut, fin = date(2026, 1, 1), datetime.now(NEW_YORK).date()
    return {"criteres": jx.criteres(jx.seances(debut, fin), jx.evenements(debut, fin), jx.livre()),
            "calibration": jx._csv(jx.CALIBRATION),
            "couts_par_jour": couts_par_jour(),
            "seances": jx.seances(debut, fin)[-60:]}


class Decision(BaseModel):
    valider: bool
    raison: str = ""


def creer_routeur(require_auth: Callable) -> APIRouter:
    r = APIRouter(prefix="/api/salle", dependencies=[Depends(require_auth)])

    r.get("/etat")(lambda: etat())
    r.get("/equipe")(lambda: equipe())

    @r.get("/fil")
    def _fil(jours: int = 1):
        return list(reversed(_meta_evenements_periode(jours)))[:300]
    r.get("/rapports")(lambda: rapports())
    r.get("/protocole")(lambda: protocole())

    @r.get("/equipe/{membre}")
    def _historique(membre: str):
        try:
            return historique(membre)
        except KeyError:
            raise HTTPException(404, "membre inconnu")

    @r.get("/propositions")
    def _propositions():
        from src.equipe import audit
        return list(reversed(audit._propositions()))

    @r.post("/propositions/{pid}/decision")
    def _decider(pid: str, d: Decision, user: str = Depends(require_auth)):
        from src.equipe import audit
        try:
            p = audit.decider(pid, d.valider, d.raison)
        except KeyError:
            raise HTTPException(404, "proposition inconnue")
        except ValueError as e:
            raise HTTPException(409, str(e))
        # Publié sur le bus : l'autre appareil du CIO se met à jour en direct.
        try:
            from src.events.bus import Event, get_bus
            get_bus().emit(Event(type="equipe", severity="info", title="CIO",
                                 body=f"Leçon {pid} {'validée' if d.valider else 'rejetée'} "
                                      f"({p['membre']}).",
                                 meta={"role": "CIO", "tache": "decision", "phase": "fin",
                                       "ok": True, "notifier": False}))
        except Exception:
            pass
        return p

    return r


def _meta_evenements_periode(jours: int) -> List[dict]:
    fin = datetime.now(NEW_YORK).date()
    sortie = []
    for d in range(max(1, min(jours, 14)) - 1, -1, -1):
        sortie += _meta_evenements(fin - timedelta(days=d))
    return sortie
