# src/notify/interventions.py
"""
Ce qui attend une réponse du CIO.

Une notification « Action requise » ouvre la page de sa demande, dans la salle.
Un même problème garde la même demande (la clé) : il se signale à chaque passage
tant que personne n'a répondu, et se tait dès que le CIO a dit « je m'en occupe ».
Répondre n'envoie aucun ordre : la réponse est écrite ici, et c'est tout.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

CHEMIN = Path("logs/interventions.json")
REPONSES = {"je_m_en_occupe": "Je m'en occupe", "regle": "C'est réglé"}


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def lister(chemin: Path = CHEMIN) -> List[dict]:
    """Les demandes, de la plus récente à la plus ancienne."""
    try:
        d = json.loads(chemin.read_text())
    except (OSError, ValueError):
        return []
    return d if isinstance(d, list) else []


def _sauver(demandes: List[dict], chemin: Path) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(f"{chemin.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(demandes, indent=1, ensure_ascii=False))
    os.replace(tmp, chemin)


def demander(cle: str, titre: str, texte: str, chemin: Path = CHEMIN, envoyer=None) -> dict:
    """Ouvre la demande, ou la met à jour si ce problème est déjà ouvert, et notifie."""
    demandes = lister(chemin)
    maintenant = _maintenant().isoformat(timespec="seconds")
    d = next((x for x in demandes if x["cle"] == cle and x["statut"] == "ouverte"), None)
    if d is None:
        d = {"id": uuid.uuid4().hex[:10], "cle": cle, "titre": titre, "texte": texte,
             "statut": "ouverte", "reponse": None, "ouverte_le": maintenant,
             "signalee_le": maintenant, "fermee_le": None}
        demandes.insert(0, d)
    else:
        d.update(titre=titre, texte=texte, signalee_le=maintenant)
    _sauver(demandes[:200], chemin)
    if d["reponse"] != "je_m_en_occupe":
        try:
            if envoyer is None:
                from src.notify.push import send_push as envoyer
            envoyer(f"🔴 {titre}", texte[:300], url=f"/interventions/{d['id']}", tag=cle)
        except Exception as e:         # une notification ne doit jamais arrêter un pod
            print(f"(notification non envoyée : {e})")
    return d


def repondre(demande_id: str, reponse: str, chemin: Path = CHEMIN) -> dict:
    if reponse not in REPONSES:
        raise ValueError("réponse inconnue")
    demandes = lister(chemin)
    d = next((x for x in demandes if x["id"] == demande_id), None)
    if d is None:
        raise KeyError(demande_id)
    d["reponse"] = reponse
    if reponse == "regle":
        d.update(statut="fermee", fermee_le=_maintenant().isoformat(timespec="seconds"))
    _sauver(demandes, chemin)
    return d


def resoudre(cle: str, chemin: Path = CHEMIN) -> bool:
    """Le problème a disparu tout seul (le pod repart) : la demande se ferme."""
    demandes = lister(chemin)
    ouvertes = [d for d in demandes if d["cle"] == cle and d["statut"] == "ouverte"]
    if not ouvertes:
        return False
    for d in ouvertes:
        d.update(statut="fermee", reponse=d["reponse"] or "automatique",
                 fermee_le=_maintenant().isoformat(timespec="seconds"))
    _sauver(demandes, chemin)
    return True


def signalee_a_l_instant(prefixe: str, minutes: int = 5, chemin: Path = CHEMIN,
                         maintenant: Optional[datetime] = None) -> bool:
    """Une demande de ce pod vient-elle d'être signalée ? (Évite d'alerter deux fois.)"""
    seuil = (maintenant or _maintenant()) - timedelta(minutes=minutes)
    return any(d["cle"].startswith(prefixe) and d["statut"] == "ouverte"
               and datetime.fromisoformat(d["signalee_le"]) >= seuil for d in lister(chemin))


def incident(pod: str, nom: str, role: str, texte: str, envoyer=None) -> dict:
    """Un pod signale un problème critique. L'écart courtier a sa propre clé : le pod la referme."""
    genre = "ecart" if texte.startswith("Écart") else "incident"
    return demander(f"{pod}-{genre}", f"Action requise · {nom} — {role}", texte, envoyer=envoyer)
