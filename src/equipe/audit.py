# src/equipe/audit.py
"""
L'Audit : « si on perd, on apprend » — sans jamais se corriger tout seul.

Deux tâches (docs/desk/equipe.md, section 3) :
- **post-mortem à chaud** (chaque soir, 16 h 50 New York), seulement s'il
  s'est passé quelque chose : frein du Risk Manager, alerte, membre en échec,
  incident du desk. Journée calme → aucun appel, coût nul ;
- **revue du vendredi** (17 h 15) : la semaine de chaque membre, ce qui a
  marché, ce qui doit changer, et le mémo commun de l'équipe au CIO.

Le circuit des leçons :
    Audit propose → logs/equipe/propositions.jsonl (en attente)
    CIO valide    → python -m src.equipe valider <id>  → carnet du membre
    CIO rejette   → python -m src.equipe rejeter <id> "raison"
Les membres ne lisent dans leur carnet QUE des leçons validées par le CIO :
l'Audit ne peut pas modifier le comportement de l'équipe à lui seul.

Distinction imposée à chaque post-mortem (« si on perd, on apprend ») : une
perte NORMALE est le prix de la prime et ne s'apprend pas — changer les
règles après elle, c'est se suradapter ; une VRAIE ERREUR (bug, règle violée,
donnée fausse) doit devenir une leçon, et si possible un test automatique.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from src.equipe import journaux as jx
from src.equipe import socle as sc

MEMBRE = "Audit"
MODELE = sc.SONNET
MEMBRES = Literal["Volatility Trader", "Execution Trader", "Risk Manager",
                  "Research Analyst", "Middle Office", "Audit"]
PROPOSITIONS = sc.DOSSIER / "propositions.jsonl"

MANDAT_COMMUN = """\
Tu es l'Audit du desk. Tu juges sur pièces : chaque constat cite le journal, \
le mémo ou l'ordre qui le prouve. Tu ne changes rien toi-même : tu proposes \
des leçons au CIO, qui les valide ou les rejette.

Pour chaque problème, tranche explicitement :
- « perte normale » : le prix attendu de la stratégie, déjà prévu par les \
tests. Aucune leçon : changer les règles après une perte normale, c'est se \
suradapter au passé.
- « vraie erreur » : bug, règle violée, donnée fausse, raisonnement contredit \
par les faits. Une leçon, et si possible un test automatique qui empêchera \
qu'elle se reproduise.
- « à juger plus tard » : une décision dont on ne connaîtra la qualité qu'à \
l'échéance (un frein du Risk Manager, par exemple). Dis quand et comment elle \
sera jugée.

Une leçon est courte, actionnable, attribuée à un membre. Indique si elle \
change une règle écrite (charte, protocole, document de l'équipe) : dans ce \
cas, seul le CIO peut décider. Ne repropose pas une leçon déjà en attente ou \
déjà validée (outil propositions)."""


class Incident(BaseModel):
    quoi: str
    preuve: str = Field(description="Journal, mémo ou ordre qui le montre.")
    nature: Literal["perte normale", "vraie erreur", "à juger plus tard", "rien à signaler"]
    cause_probable: str


class Lecon(BaseModel):
    membre: MEMBRES
    lecon: str
    justification: str
    change_une_regle: bool
    test_automatique: str = Field(description="Le test qui l'empêcherait de se reproduire ; vide si aucun.")


class PostMortem(sc.Memo):
    incidents: List[Incident]
    lecons_proposees: List[Lecon]


class BilanMembre(BaseModel):
    membre: MEMBRES
    ce_qu_il_a_fait: str
    qualite: Literal["solide", "correcte", "à améliorer", "pas assez de données"]
    a_ameliorer: str


class Revue(sc.Memo):
    bilan_par_membre: List[BilanMembre]
    constats: List[Incident]
    lecons_proposees: List[Lecon]
    memo_au_cio: str = Field(description="Le mémo commun de l'équipe pour la semaine, en markdown.")


# ── Déclencheurs ────────────────────────────────────────────────────────────

def declencheurs(jour: date, dossier: Path = sc.DOSSIER, db: Path = jx.EVENEMENTS) -> List[str]:
    """Ce qui, aujourd'hui, mérite un post-mortem. Vide = journée calme, pas d'appel."""
    raisons = []
    for m in sc.lire_memos(jour.isoformat(), dossier=dossier / "memos"):
        if m["membre"] == MEMBRE:
            continue
        if not m["ok"]:
            raisons.append(f"{m['membre']} ({m['tache']}) en échec : {m['erreur']}")
        elif m["tache"] == "relecture" and m["memo"]["decision"] == "freiner":
            raisons.append(f"Frein du Risk Manager : {m['memo']['motif_principal']}")
        elif (m["memo"] or {}).get("alerte"):
            raisons.append(f"Alerte du Research Analyst : {m['memo']['recap_court']}")
    for e in jx.evenements(jour, types=("desk",), db=db):
        if e["gravite"] in ("warning", "critical") and e["qui"] != "Risk Manager":
            raisons.append(f"Desk — {e['qui']} : {e['message'][:160]}")
    return raisons


# ── Propositions au CIO ─────────────────────────────────────────────────────

def _propositions(chemin: Path = PROPOSITIONS) -> List[dict]:
    if not chemin.exists():
        return []
    return [json.loads(l) for l in chemin.read_text().splitlines() if l.strip()]


def _ecrire_propositions(props: List[dict], chemin: Path) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in props))
    tmp.replace(chemin)


def proposer(lecons: List[Lecon], source: str, jour: date,
             chemin: Path = PROPOSITIONS) -> List[str]:
    props = _propositions(chemin)
    ids = []
    for i, l in enumerate(lecons, 1):
        pid = f"{jour.strftime('%Y%m%d')}-{source[:3]}-{len(props) + 1}"
        props.append({"id": pid, "date": jour.isoformat(), "source": source,
                      "statut": "en_attente", **l.model_dump()})
        ids.append(pid)
    _ecrire_propositions(props, chemin)
    return ids


def _carnet(membre: str, dossier: Path) -> Path:
    return dossier / "carnets" / f"{membre.lower().replace(' ', '-')}.md"


def decider(pid: str, valider: bool, raison: str = "", dossier: Path = sc.DOSSIER,
            chemin: Optional[Path] = None) -> dict:
    """Décision du CIO. Validée → ajoutée au carnet du membre, que celui-ci relit à chaque tâche."""
    chemin = chemin or dossier / "propositions.jsonl"
    props = _propositions(chemin)
    p = next((x for x in props if x["id"] == pid), None)
    if p is None:
        raise KeyError(f"proposition inconnue : {pid}")
    if p["statut"] != "en_attente":
        raise ValueError(f"proposition {pid} déjà {p['statut']}")
    p["statut"] = "validee" if valider else "rejetee"
    p["decision_le"] = datetime.now(timezone.utc).date().isoformat()
    p["raison_cio"] = raison
    if valider:
        c = _carnet(p["membre"], dossier)
        c.parent.mkdir(parents=True, exist_ok=True)
        entete = "" if c.exists() else f"# Carnet — {p['membre']}\n\n*Leçons validées par le CIO.*\n"
        with c.open("a") as f:
            f.write(f"{entete}\n## {p['decision_le']} — {pid}\n\n{p['lecon']}\n\n"
                    f"*Pourquoi :* {p['justification']}\n"
                    + (f"\n*Règle écrite à modifier — décidé par le CIO.*\n" if p["change_une_regle"] else ""))
    _ecrire_propositions(props, chemin)
    return p


# ── Les deux tâches ─────────────────────────────────────────────────────────

def _outils(debut: date, fin: date, dossier: Path, db: Path, complets: bool) -> List[sc.Outil]:
    def memos():
        sortie, j = [], debut
        while j <= fin:
            for m in sc.lire_memos(j.isoformat(), dossier=dossier / "memos"):
                memo = m["memo"]
                if memo and not complets:
                    memo = {k: v for k, v in memo.items() if k != "recap_detail"}
                sortie.append({"jour": j.isoformat(), "membre": m["membre"], "tache": m["tache"],
                               "ok": m["ok"], "erreur": m["erreur"], "cout_usd": m["cout_usd"],
                               "memo": memo})
            j += timedelta(days=1)
        return sortie or "Aucun mémo sur la période."

    return [
        sc.Outil("evenements", "Tout ce qu'ont publié le desk et l'équipe sur la période.", {},
                 lambda: jx.evenements(debut, fin, db=db) or "Aucun événement."),
        sc.Outil("memos", "Les mémos de l'équipe sur la période.", {}, memos),
        sc.Outil("seances_et_ordres", "Relevés de séance et ordres sur la période.", {},
                 lambda: {"seances": jx.seances(debut, fin),
                          "ordres": jx.ordres(debut, fin)}),
        sc.Outil("couts", "Coût de l'équipe sur la période, par membre.", {},
                 lambda: jx.couts(debut, fin, chemin=dossier / "couts.csv")),
        sc.Outil("calibration_du_research_analyst", "Gravité annoncée contre mouvement réel.", {},
                 lambda: jx._csv(dossier / "calibration.csv")[-20:] or "Pas encore de données."),
        sc.Outil("propositions", "Toutes les leçons déjà proposées, avec leur statut "
                 "(en_attente, validee, rejetee).", {},
                 lambda: _propositions(dossier / "propositions.jsonl") or "Aucune proposition."),
        sc.Outil("carnets", "Les carnets de leçons validées de chaque membre.", {},
                 lambda: {f.stem: f.read_text() for f in sorted((dossier / "carnets").glob("*.md"))}
                 if (dossier / "carnets").exists() else "Aucun carnet."),
    ]


def postmortem(jour: Optional[date] = None, *, client=None, dossier: Path = sc.DOSSIER,
               db: Path = jx.EVENEMENTS, publier: bool = True) -> Optional[sc.Resultat]:
    jour = jour or datetime.now(sc.NEW_YORK).date()
    raisons = declencheurs(jour, dossier, db)
    if not raisons:
        print(f"[{MEMBRE}] Journée calme : pas de post-mortem.")
        return None
    if publier:
        sc.annoncer(MEMBRE, "postmortem")
    consigne = ("Post-mortem du " + jour.isoformat() + ". Ce qui l'a déclenché :\n"
                + "\n".join(f"- {r}" for r in raisons)
                + "\nExamine chaque point avec tes outils, tranche sa nature, propose les leçons utiles.")
    r = sc.consulter(MEMBRE, MODELE, MANDAT_COMMUN, "postmortem", consigne, PostMortem,
                     outils=_outils(jour, jour, dossier, db, complets=True), effort="high",
                     client=client, journal=dossier / "couts.csv")
    sc.sauver_memo(MEMBRE, "postmortem", r, dossier / "memos")
    if r.ok and r.memo.lecons_proposees:
        proposer(r.memo.lecons_proposees, "postmortem", jour, dossier / "propositions.jsonl")
    if publier:
        sc.publier(MEMBRE, "postmortem", r, notifier=True,
                   gravite="warning" if (r.memo and any(i.nature == "vraie erreur"
                                                        for i in r.memo.incidents)) else "info")
    return r


def revue(fin: Optional[date] = None, *, client=None, dossier: Path = sc.DOSSIER,
          db: Path = jx.EVENEMENTS, publier: bool = True) -> sc.Resultat:
    fin = fin or datetime.now(sc.NEW_YORK).date()
    debut = fin - timedelta(days=fin.weekday())          # lundi de la semaine
    if publier:
        sc.annoncer(MEMBRE, "revue")
    consigne = (f"Revue de la semaine du {debut.isoformat()} au {fin.isoformat()}. Fais le "
                f"bilan de chaque membre (y compris le code : Volatility Trader, Execution "
                f"Trader), les constats, les leçons, puis écris le mémo commun de l'équipe au CIO.")
    r = sc.consulter(MEMBRE, MODELE, MANDAT_COMMUN, "revue", consigne, Revue,
                     outils=_outils(debut, fin, dossier, db, complets=False), effort="high",
                     client=client, journal=dossier / "couts.csv")
    sc.sauver_memo(MEMBRE, "revue", r, dossier / "memos")
    if r.ok and r.memo.lecons_proposees:
        proposer(r.memo.lecons_proposees, "revue", fin, dossier / "propositions.jsonl")
    if publier:
        sc.publier(MEMBRE, "revue", r, notifier=True)
    return r
