# src/equipe/risk_manager.py
"""
Le Risk Manager : relit chaque proposition qui augmente le risque, avant
qu'elle parte.

Règles (docs/desk/equipe.md) :
- il ne relit que les **ouvertures** ; fermetures et couvertures réduisent le
  risque et ne lui sont jamais soumises ;
- il peut **approuver** ou **freiner**, jamais demander plus ;
- pas d'avis valide (panne, refus, mémo invalide) = **pas d'ouverture** ;
- une alerte du Research Analyst freine d'office, sans le consulter.

Il travaille avec des outils en lecture seule sur l'état exact de la séance
(livre, proposition, chaîne, mémos du jour, son propre historique), et peut
rejouer des scénarios de stress de son choix. Chaque frein sera jugé : le
barreau freiné aurait-il gagné ou perdu ?
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from src.equipe import socle as sc
from src.equipe.alertes import alerte_du_jour

MEMBRE = "Risk Manager"
MODELE = sc.OPUS
EFFORT = "high"

MANDAT = """\
Tu es le Risk Manager du desk. Avant chaque ouverture d'un barreau (un iron \
butterfly XSP, vendeur de volatilité), le Volatility Trader te soumet sa \
proposition. Elle a déjà passé les limites codées de la charte (perte max par \
position, stress −20 %, vega total, état de baisse). Ton travail est ce que le \
code ne sait pas faire : juger le contexte.

Ta seule autorité : APPROUVER ou FREINER. Freiner coûte la prime d'une \
semaine ; approuver à tort peut coûter la perte maximale du barreau. Chacun de \
tes freins sera rejoué à l'échéance du barreau freiné : a-t-il évité une perte \
ou coûté un gain ? Un frein doit donc reposer sur un fait que tu as vérifié \
avec tes outils et que tu cites, chiffre à l'appui — jamais sur une \
inquiétude vague. Inversement, ne laisse pas passer un vrai signal par \
politesse.

Ce que tu examines, au minimum :
1. La prime : la volatilité implicite vendue est-elle au-dessus de la \
volatilité réalisée récente ? Vendre sous la réalisée, c'est vendre \
l'assurance moins cher que le risque qu'elle couvre.
2. Le calendrier : un événement majeur (Fed, inflation, emploi, annonce \
politique, résultats géants) tombe-t-il pendant la vie du barreau, et le \
Research Analyst l'a-t-il signalé ?
3. Le régime : la structure par terme est-elle inversée (volatilité courte au- \
dessus de la longue), signe de stress en cours ?
4. Le livre : concentration sur une échéance, exposition après ouverture, \
scénarios de stress que tu juges pertinents au-delà du −20 % réglementaire.
5. La qualité des données : prix incohérents, fourchettes anormales, grecques \
absentes.
6. Ton carnet : les leçons validées par le CIO.

Rends ton verdict avec la liste de tes vérifications. Si tes outils ne te \
permettent pas de vérifier un point, dis-le dans la vérification \
correspondante plutôt que de supposer."""


class Verification(BaseModel):
    element: str = Field(description="Ce qui est vérifié, ex. « prime vs volatilité réalisée ».")
    constat: str = Field(description="Ce que les outils montrent, chiffres compris.")
    statut: Literal["ok", "attention", "bloquant"]


class Verdict(sc.Memo):
    decision: Literal["approuver", "freiner"]
    motif_principal: str = Field(description="La raison de la décision, en une ou deux phrases chiffrées.")
    verifications: List[Verification]
    confiance: int = Field(ge=1, le=5, description="1 = très incertain, 5 = très sûr.")
    ce_qui_me_ferait_changer_d_avis: str


def _outils(contexte: dict, stress: callable, memos_dossier: Path,
            jour: date, carnet: Path) -> List[sc.Outil]:
    """Outils en lecture seule sur l'état figé de la séance."""
    def historique() -> list:
        sortie = []
        d = memos_dossier
        if d.exists():
            for f in sorted(d.glob("*/risk-manager-relecture-*.json"))[-10:]:
                m = json.loads(f.read_text())
                if m.get("memo"):
                    sortie.append({"jour": f.parent.name, "decision": m["memo"]["decision"],
                                   "motif": m["memo"]["motif_principal"]})
        return sortie

    def memos_research() -> list:
        return [{"heure": m["horodatage"], "memo": m["memo"]}
                for m in sc.lire_memos(jour.isoformat(), "Research Analyst", memos_dossier)
                if m.get("ok")] or "Aucun mémo du Research Analyst aujourd'hui."

    return [
        sc.Outil("proposition", "La proposition du Volatility Trader : barreau, prix, "
                 "perte maximale, vega, volatilité implicite, mouvement attendu.", {},
                 lambda: contexte["proposition"]),
        sc.Outil("etat_du_livre", "Le livre avant l'ouverture : barreaux ouverts, MES, valeur "
                 "liquidative, plus haut, état de la charte, exposition, vega, stress.", {},
                 lambda: contexte["livre"]),
        sc.Outil("marche", "Le marché à l'instant de la séance : cours XSP, volatilité réalisée "
                 "récente, volatilité implicite à la monnaie par échéance (structure par "
                 "terme), fourchettes.", {}, lambda: contexte["marche"]),
        sc.Outil("scenario_de_stress", "Réévalue le livre APRÈS ouverture pour un choc de "
                 "cours (ex. -0.10 = −10 %) et une variation de volatilité implicite en "
                 "points (ex. 0.15 = +15 points). Rend le gain (négatif = perte) en dollars.",
                 {"choc_cours": {"type": "number"}, "variation_vol": {"type": "number"}},
                 lambda choc_cours, variation_vol: {
                     "choc_cours": choc_cours, "variation_vol": variation_vol,
                     "resultat_usd": round(stress(choc_cours, variation_vol), 2)}),
        sc.Outil("memos_du_research_analyst", "Briefing du matin et analyses de la veille "
                 "d'aujourd'hui.", {}, memos_research),
        sc.Outil("mes_derniers_verdicts", "Tes 10 derniers verdicts, pour rester cohérent.",
                 {}, historique),
        sc.Outil("mon_carnet", "Les leçons validées par le CIO pour le Risk Manager.", {},
                 lambda: carnet.read_text() if carnet.exists() else "Carnet vide pour l'instant."),
    ]


def relire(contexte: dict, stress: callable, jour: date, *, client=None,
           dossier: Path = sc.DOSSIER, publier: bool = True) -> Tuple[bool, str, sc.Resultat]:
    """(ouverture autorisée ?, message, résultat). Toute défaillance vaut frein."""
    memos = dossier / "memos"
    alerte = alerte_du_jour(jour, memos)
    if alerte:
        motif = alerte["memo"].get("recap_court", "alerte en cours")
        r = sc.Resultat(None, 0.0, 0, erreur="alerte du Research Analyst")
        return False, f"Frein d'office : alerte du Research Analyst — {motif}", r

    if publier:
        sc.annoncer(MEMBRE, "relecture")
    consigne = (
        f"Séance du {jour.isoformat()}. Le Volatility Trader propose d'ouvrir le barreau "
        f"{contexte['proposition'].get('echeance')}. Utilise tes outils, examine chaque "
        f"point de ton mandat, puis rends ton verdict.")
    r = sc.consulter(MEMBRE, MODELE, MANDAT, "relecture", consigne, Verdict,
                     outils=_outils(contexte, stress, memos, jour,
                                    dossier / "carnets" / "risk-manager.md"),
                     effort=EFFORT, client=client, journal=dossier / "couts.csv")
    sc.sauver_memo(MEMBRE, "relecture", r, memos)
    if publier:
        sc.publier(MEMBRE, "relecture", r, notifier=True,
                   gravite="warning" if (r.memo and r.memo.decision == "freiner") else "info")
    if not r.ok:
        return False, f"Pas d'avis valide du Risk Manager ({r.erreur}) : pas d'ouverture.", r
    if r.memo.decision == "freiner":
        return False, f"Freiné par le Risk Manager : {r.memo.motif_principal}", r
    return True, f"Approuvé par le Risk Manager : {r.memo.motif_principal}", r


# ── Relecture du prop trader (docs/desk/pods.md, section 1) ─────────────────

MANDAT_PROP = """\
Tu es le Risk Manager du fonds. Le Prop Trader (un membre Claude) propose un \
lot d'ouvertures sur des actions du S&P 500, à l'achat ou à découvert. Le \
code a déjà appliqué son budget : 8 positions, 8 % de la VL par position, \
1 % de risque par trade entre l'entrée et le stop, pause à −2 % sur la \
séance, limites du fonds. Les quantités sont calculées. Ton travail est ce \
que le code ne sait pas faire : juger chaque trade dans son contexte.

Ta seule autorité, trade par trade : APPROUVER ou FREINER. Le CIO veut que \
le pod trade et apprenne ; un frein doit donc reposer sur un fait vérifié et \
cité, pas sur l'idée qu'un trade pourrait perdre — c'est le rôle du stop. \
Chacun de tes freins sera rejoué : le trade freiné aurait-il touché son stop \
ou son objectif ?

Ce que tu examines, au minimum :
1. Résultats de la société pendant l'horizon annoncé, non assumés dans la thèse.
2. Concentration : le lot et le livre parient-ils plusieurs fois la même chose \
(même secteur, même facteur, même sens) ?
3. Cohérence des niveaux : stop dans le bruit quotidien du titre (comparé à \
sa volatilité), objectif irréaliste, entrée qui poursuit un titre déjà parti.
4. Vente à découvert : titre en emballement, nouvelle contraire, dividende \
détaché pendant la vie du trade (il est dû par le vendeur).
5. Le marché : alerte du Research Analyst, statistique majeure dans l'heure.
6. Ton carnet : les leçons validées par le CIO.

Rends une décision pour CHAQUE trade du lot, avec ses vérifications. Un \
trade du lot sans décision de ta part est freiné."""


class DecisionTrade(BaseModel):
    ticker: str
    decision: Literal["approuver", "freiner"]
    motif: str = Field(description="Une ou deux phrases chiffrées.")
    verifications: List[Verification]


class VerdictLot(sc.Memo):
    decisions: List[DecisionTrade]
    lecture_du_risque: str = Field(description="Le lot et le livre dans leur ensemble.")
    # L'échelle doit être écrite : le schéma envoyé à l'API perd les bornes, et
    # la première relecture réelle (2026-10-23) a rendu une confiance hors de 1-5.
    confiance: int = Field(ge=1, le=5, description="Entier de 1 (très incertain) à 5 (très sûr).")


MODELE_PROP = sc.SONNET          # budget du CIO (docs/desk/pods.md, amendement 1)
TEXTES_PROP = ("docs/charte.md", "docs/desk/pods.md")


def relire_prop(contexte: dict, jour: date, *, client=None, dossier: Path = sc.DOSSIER,
                publier: bool = True) -> Tuple[dict, str, sc.Resultat]:
    """({ticker: (autorisé ?, motif)}, message, résultat). Toute défaillance freine tout le lot.

    Un seul appel, sans outils : le dossier (lot, livre, agenda des titres du
    lot, mémos du jour, carnet) est fourni d'emblée.
    """
    memos = dossier / "memos"
    tickers = [t["ticker"] for t in contexte["lot"]]
    if publier:
        sc.annoncer(MEMBRE, "relecture prop")
    carnet = dossier / "carnets" / "risk-manager.md"
    agenda = contexte.get("agenda") or {}
    pieces = {
        "lot_propose": contexte["lot"],
        "livre_du_pod": contexte["livre"],
        "agenda_des_titres_du_lot": {k: [x for x in v if isinstance(x, dict) and x.get("ticker") in tickers]
                                     for k, v in agenda.items() if isinstance(v, list)},
        "statistiques_du_jour": agenda.get("economie_du_jour", []),
        "research_analyst": [{k: m["memo"].get(k) for k in ("recap_court", "gravite", "alerte")}
                             for m in sc.lire_memos(jour.isoformat(), "Research Analyst", memos)
                             if m.get("ok") and m.get("memo")][-2:],
        "mon_carnet": carnet.read_text() if carnet.exists() else "Carnet vide.",
    }
    consigne = (f"Séance du {jour.isoformat()}. Le Prop Trader propose {len(tickers)} ouverture(s) : "
                f"{', '.join(tickers)}. Examine chaque trade avec le dossier, puis rends une décision "
                f"pour chacun.\n\n<dossier>\n{json.dumps(pieces, ensure_ascii=False, default=str)}\n</dossier>")
    r = sc.consulter(MEMBRE, MODELE_PROP, MANDAT_PROP, "relecture-prop", consigne, VerdictLot,
                     effort="medium", max_tours=2, client=client, journal=dossier / "couts.csv",
                     textes=TEXTES_PROP)
    sc.sauver_memo(MEMBRE, "relecture-prop", r, memos)
    if not r.ok:
        if publier:
            sc.publier(MEMBRE, "relecture prop", r, notifier=True)
        return ({t: (False, "pas d'avis valide du Risk Manager") for t in tickers},
                f"Pas d'avis valide du Risk Manager ({r.erreur}) : aucune ouverture du pod.", r)
    par_ticker = {d.ticker.upper(): d for d in r.memo.decisions}
    sortie = {}
    for t in tickers:
        d = par_ticker.get(t.upper())
        sortie[t] = (False, "aucune décision du Risk Manager : freiné") if d is None else \
            (d.decision == "approuver", d.motif)
    freines = sum(1 for ok, _ in sortie.values() if not ok)
    if publier:
        sc.publier(MEMBRE, "relecture prop", r, notifier=True,
                   gravite="warning" if freines else "info")
    return sortie, f"{len(tickers) - freines} approuvé(s), {freines} freiné(s).", r
