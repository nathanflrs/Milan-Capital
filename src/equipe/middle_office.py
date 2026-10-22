# src/equipe/middle_office.py
"""
Le Middle Office : le rapport du soir (16 h 30, New York).

Le rapprochement registre / courtier, lui, est fait par le code à chaque
séance (src/options/registre.py). Ici, Claude écrit le compte rendu de la
journée pour le CIO — à partir de chiffres que le code a écrits, jamais de
chiffres qu'il invente : chaque nombre du rapport doit venir d'un outil.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from src.equipe import journaux as jx
from src.equipe import socle as sc

MEMBRE = "Middle Office"
MODELE = sc.SONNET

MANDAT = """\
Tu es le Middle Office du desk. Chaque soir, tu écris le rapport de la \
journée pour le CIO (Nathan, 18 ans, qui apprend le métier : français clair, \
termes techniques expliqués en une demi-phrase la première fois).

Règle absolue : chaque chiffre du rapport vient d'un de tes outils. Si un \
chiffre manque, écris qu'il manque. Ne recalcule pas de toi-même ce qu'un \
outil donne déjà.

Ton rapport répond, dans cet ordre :
1. Le fonds : valeur, résultat, positions. Le mode (simulation ou réel) est \
toujours dit en premier.
2. Le desk : ce que chaque séance a décidé et fait (ouvertures, fermetures, \
couvertures, ordres simulés ou réels), et pourquoi.
3. L'équipe : ce qu'a fait chaque membre (briefing, veille, relectures du \
Risk Manager), avec leurs conclusions, et leur coût.
4. Le protocole : où en sont les critères F1 à F5 et P1.
5. La calibration du Research Analyst : sa gravité annoncée contre le \
mouvement réel du marché, sur les jours disponibles.
6. Ce que le CIO doit savoir ou décider — vide si rien.

Signale tout écart entre ce qu'un membre affirme et ce que montrent les \
journaux : c'est ton métier."""


class EtatCritere(BaseModel):
    critere: str = Field(description="F1, F2, F3, F4, F5 ou P1.")
    etat: Literal["ok", "a_surveiller", "en_echec", "pas_encore_mesurable"]
    commentaire: str


class Rapport(sc.Memo):
    mode: Literal["simulation", "reel", "inconnu"]
    le_fonds: str
    le_desk: str
    l_equipe: str
    criteres: List[EtatCritere]
    calibration_research: str
    pour_le_cio: List[str] = Field(description="Points à savoir ou décider ; liste vide si rien.")
    ecarts_constates: List[str] = Field(description="Écarts entre affirmations et journaux ; vide si aucun.")


def _outils(jour: date, dossier: Path, chemins: dict) -> List[sc.Outil]:
    evts = lambda: jx.evenements(jour, db=chemins["evenements"])
    return [
        sc.Outil("seances_du_jour", "Relevé chiffré de chaque séance (valeur liquidative, barreaux, "
                 "MES, exposition avant couverture, mode).", {},
                 lambda: jx.seances(jour, chemin=chemins["seances"]) or "Aucune séance aujourd'hui."),
        sc.Outil("evenements_du_jour", "Tout ce qu'ont publié le desk et l'équipe aujourd'hui, "
                 "dans l'ordre.", {}, lambda: evts() or "Aucun événement."),
        sc.Outil("ordres_du_jour", "Ordres du jour (simulés ou réels) : instrument, prix limites, "
                 "statut, remplissage, commission.", {},
                 lambda: jx.ordres(jour, chemin=chemins["ordres"]) or "Aucun ordre."),
        sc.Outil("registre", "Le registre du desk : barreaux, MES, cycles fermés.", {},
                 lambda: jx.livre(chemins["livre"])),
        sc.Outil("criteres_du_protocole", "État des critères F1-F5 et P1, calculé par le code.", {},
                 lambda: jx.criteres(jx.seances(date(2026, 1, 1), jour, chemins["seances"]),
                                     jx.evenements(date(2026, 1, 1), jour, db=chemins["evenements"]),
                                     jx.livre(chemins["livre"]))),
        sc.Outil("memos_de_l_equipe", "Les mémos rendus aujourd'hui par chaque membre (Research "
                 "Analyst, Risk Manager).", {},
                 lambda: [{"membre": m["membre"], "tache": m["tache"], "heure": m["horodatage"],
                           "ok": m["ok"], "erreur": m["erreur"], "cout_usd": m["cout_usd"],
                           "memo": m["memo"]} for m in sc.lire_memos(jour.isoformat(),
                                                                    dossier=dossier / "memos")
                          if m["membre"] != MEMBRE] or "Aucun mémo aujourd'hui."),
        sc.Outil("couts_de_l_equipe", "Coût de l'équipe aujourd'hui, par membre, et cumul du mois.",
                 {}, lambda: jx.couts(jour, chemin=dossier / "couts.csv")),
        sc.Outil("calibration_du_research_analyst", "Gravité annoncée par le Research Analyst "
                 "contre mouvement réel du S&P 500 (%) et du VIX (points), jour par jour. La "
                 "clôture du jour n'est publiée par le CBOE que dans la soirée.", {},
                 lambda: jx._csv(dossier / "calibration.csv")[-15:] or
                 "Aucune journée complète encore (il faut un briefing et une clôture publiée)."),
        sc.Outil("mon_carnet", "Les leçons validées par le CIO pour le Middle Office.", {},
                 lambda: (dossier / "carnets" / "middle-office.md").read_text()
                 if (dossier / "carnets" / "middle-office.md").exists() else "Carnet vide."),
    ]


def rapport(jour: Optional[date] = None, *, client=None, dossier: Path = sc.DOSSIER,
            publier: bool = True, chemins: Optional[dict] = None, lire_cboe=None) -> sc.Resultat:
    jour = jour or datetime.now(sc.NEW_YORK).date()
    chemins = {"evenements": jx.EVENEMENTS, "seances": jx.SEANCES, "ordres": jx.ORDRES,
               "livre": jx.LIVRE, **(chemins or {})}
    if publier:
        sc.annoncer(MEMBRE, "rapport")
    jx.mettre_a_jour_calibration(dossier / "memos", dossier / "calibration.csv", lire_cboe)
    consigne = (f"Rapport du {jour.isoformat()}. Consulte tes outils, puis écris le rapport "
                f"du soir pour le CIO.")
    r = sc.consulter(MEMBRE, MODELE, MANDAT, "rapport", consigne, Rapport,
                     outils=_outils(jour, dossier, chemins), effort="medium", client=client,
                     journal=dossier / "couts.csv")
    sc.sauver_memo(MEMBRE, "rapport", r, dossier / "memos")
    if publier:
        sc.publier(MEMBRE, "rapport", r, notifier=True)
    return r
