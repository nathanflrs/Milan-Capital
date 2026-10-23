# src/prop/regles.py
"""
Le budget du prop trader, appliqué par le code (docs/desk/pods.md, section 1).

Claude propose ; ce module dispose. Aucune proposition ne part sans y être
passée, et la quantité est toujours calculée ici, jamais par Claude :

    quantité = la plus petite de
        risque permis (1 % de la VL) ÷ |entrée − stop|
        taille demandée (≤ 8 % de la VL) ÷ entrée
    × 1/2 si le fonds est à −8 % de son plus haut.

Logique pure : pas de courtier, pas d'appel à Claude.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from src.options import risque as rq
from src.prop.livre import Livre, Position

MAX_POSITIONS = 8
TAILLE_MAX = 0.08
RISQUE_MAX = 0.01
PAUSE_JOUR = 0.02
STOP_MAX = 0.15
ECART_ENTREE_MAX = 0.01


@dataclass(frozen=True)
class Demande:
    """Une proposition du prop trader, telle qu'il l'a écrite."""
    ticker: str
    sens: int                   # +1 achat, −1 vente à découvert
    entree: float               # prix limite
    stop: float
    objectif: float
    taille_pct: float           # % de la VL demandé
    these: str = ""
    catalyseur: str = ""
    horizon: str = ""


@dataclass(frozen=True)
class Ordre:
    """Une demande acceptée par le code, quantité calculée."""
    demande: Demande
    quantite: int
    limite: float
    risque_usd: float
    montant_usd: float

    @property
    def ticker(self) -> str:
        return self.demande.ticker


def etat_du_fonds(vl: float, plus_haut: float) -> str:
    """'normal', 'reduire' (−8 %) ou 'arret' (−15 %) : les limites du fonds priment."""
    return rq.etat_baisse(vl, max(plus_haut, vl))


def peut_ouvrir(livre: Livre, jour, vl: float, plus_haut: float,
                perte_du_jour: float) -> Tuple[bool, str]:
    etat = etat_du_fonds(vl, plus_haut)
    if etat == "arret":
        return False, "Fonds à −15 % de son plus haut : aucune ouverture (charte)."
    if livre.en_pause(jour) or perte_du_jour <= -PAUSE_JOUR * vl:
        return False, (f"Pause du pod : {perte_du_jour:+,.0f} $ dans la séance "
                       f"(seuil −{PAUSE_JOUR:.0%} de la VL). Sorties seulement, jusqu'à demain.")
    return True, "Ouvertures permises."


def valider(demandes: Sequence[Demande], livre: Livre, vl: float, plus_haut: float,
            membres: Iterable[str], cours: Dict[str, float]) -> Tuple[List[Ordre], List[Tuple[str, str]]]:
    """(ordres acceptés, [(ticker, motif du refus)])."""
    membres = set(membres)
    facteur = 0.5 if etat_du_fonds(vl, plus_haut) == "reduire" else 1.0
    deja = {p.ticker for p in livre.positions}
    places = MAX_POSITIONS - len(livre.positions)
    acceptes: List[Ordre] = []
    refus: List[Tuple[str, str]] = []

    for d in demandes:
        t = d.ticker
        dernier = cours.get(t)
        motif = None
        if t not in membres:
            motif = "hors du S&P 500 (ou ETF) : interdit"
        elif t in deja or any(o.ticker == t for o in acceptes):
            motif = "déjà en portefeuille ou proposé deux fois"
        elif d.sens not in (1, -1):
            motif = "sens inconnu"
        elif not dernier or dernier <= 0:
            motif = "aucun cours du courtier pour vérifier le prix"
        elif not (d.entree > 0 and d.stop > 0 and d.objectif > 0):
            motif = "prix manquant (entrée, stop ou objectif)"
        elif abs(d.entree / dernier - 1) > ECART_ENTREE_MAX:
            motif = f"entrée {d.entree:g} à plus de 1 % du dernier cours {dernier:g}"
        elif d.sens * (d.entree - d.stop) <= 0:
            motif = "stop du mauvais côté de l'entrée"
        elif d.sens * (d.objectif - d.entree) <= 0:
            motif = "objectif du mauvais côté de l'entrée"
        elif abs(d.entree - d.stop) / d.entree > STOP_MAX:
            motif = "stop à plus de 15 % de l'entrée"
        elif not 0 < d.taille_pct <= TAILLE_MAX * 100:
            motif = f"taille {d.taille_pct:g} % hors de ]0 ; 8 %]"
        elif len(acceptes) >= places:
            motif = f"plus de place : {MAX_POSITIONS} positions au plus"
        if motif:
            refus.append((t, motif))
            continue

        par_risque = RISQUE_MAX * vl * facteur / abs(d.entree - d.stop)
        par_taille = d.taille_pct / 100 * vl * facteur / d.entree
        q = int(math.floor(min(par_risque, par_taille)))
        if q < 1:
            refus.append((t, "quantité nulle après les limites"))
            continue
        acceptes.append(Ordre(d, q, round(d.entree, 2), round(q * abs(d.entree - d.stop), 2),
                              round(q * d.entree, 2)))
    return acceptes, refus


def valider_ajustement(p: Position, action: str, prix: float, cours: Optional[float],
                       vl: float) -> Optional[str]:
    """Motif du refus d'un ajustement, ou None s'il est permis. Sortir l'est toujours."""
    if action == "sortir":
        return None
    if action not in ("deplacer_stop", "deplacer_objectif"):
        return f"action inconnue : {action}"
    if not prix or prix <= 0:
        return "nouveau prix manquant"
    if not cours:
        return "aucun cours pour vérifier le nouveau prix"
    if action == "deplacer_stop":
        if p.sens * (cours - prix) <= 0:
            return f"stop {prix:g} du mauvais côté du cours {cours:g}"
        risque = p.sens * p.quantite * (p.entree - prix)
        if risque > RISQUE_MAX * vl:
            return f"le stop élargi porterait le risque à {risque:,.0f} $ (> 1 % de la VL)"
        return None
    if p.sens * (prix - cours) <= 0:
        return f"objectif {prix:g} du mauvais côté du cours {cours:g}"
    return None


def exposition(positions: Sequence[Position], ordres: Sequence[Ordre], cours: Dict[str, float],
               secteurs: Dict[str, str], vl: float) -> dict:
    """Exposition du pod après le lot proposé : brute, nette, par secteur, risque aux stops."""
    lignes = [(p.ticker, p.sens * p.quantite * cours.get(p.ticker, p.entree), p.risque_au_stop())
              for p in positions]
    lignes += [(o.ticker, o.demande.sens * o.montant_usd, o.risque_usd) for o in ordres]
    par_secteur: Dict[str, float] = {}
    for t, m, _ in lignes:
        s = secteurs.get(t, "?")
        par_secteur[s] = par_secteur.get(s, 0.0) + m
    pct = lambda x: round(x / vl * 100, 2)
    return {"positions_apres": len(lignes),
            "exposition_brute_pct_vl": pct(sum(abs(m) for _, m, _ in lignes)),
            "exposition_nette_pct_vl": pct(sum(m for _, m, _ in lignes)),
            "risque_total_aux_stops_pct_vl": pct(sum(max(r, 0) for _, _, r in lignes)),
            "nette_par_secteur_pct_vl": {s: pct(m) for s, m in sorted(par_secteur.items())}}
