# src/options/risque.py
"""
Pièces 3 et 4 de la couche options : le risque du livre, les limites de la
charte, et la couverture en micro-futures.

Le livre est exprimé en **unités d'indice XSP**. Un contrat d'option XSP
porte sur 100 unités ; un micro-future MES vaut 5 $ × SPX, et SPX = 10 × XSP,
soit **50 unités XSP**. Ramener tout à la même unité évite la classe d'erreur
la plus bête d'un desk : additionner des deltas exprimés dans des monnaies
différentes.

Limites (docs/charte.md, section 5 ; docs/desk/phase2_observation.md, section 3) :

    perte depuis le plus haut   −8 % → taille ÷ 2      −15 % → arrêt
    perte max par position      2 % de la valeur liquidative
    stress S&P −20 % en séance  perte ≤ 10 %, options réévaluées

Ce module ne parle pas au courtier.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional, Sequence

from src.options.greeks import grecques

UNITES_PAR_MES = 50          # 5 $ × SPX, SPX = 10 × XSP
MULT_OPTION = 100

REDUCTION, ARRET = -0.08, -0.15
PERTE_MAX_POSITION = 0.02
STRESS_CHOC, STRESS_PERTE_MAX = -0.20, 0.10
# Hausse de volatilité appliquée dans le stress : +30 points. Un S&P à −20 % en
# une séance n'a eu lieu qu'une fois (octobre 1987) ; en mars 2020, la
# volatilité implicite est passée d'environ 15 à plus de 80 en un mois. +30
# points en une séance est un choix prudent pour une chute de cette ampleur,
# fixé ici avant toute position.
STRESS_HAUSSE_VOL = 0.30


@dataclass(frozen=True)
class Position:
    """Une ligne du livre. type_ : 'P', 'C' ou 'MES'. quantite > 0 = acheté."""
    type_: str
    quantite: int
    strike: float = 0.0
    echeance: str = ""
    iv: float = 0.0

    def annees(self, aujourd_hui: date) -> float:
        d = datetime.strptime(self.echeance, "%Y%m%d").date()
        return max((d - aujourd_hui).days, 0) / 365


@dataclass
class Livre:
    positions: List[Position] = field(default_factory=list)
    r: float = 0.04
    q: float = 0.012

    def valeur(self, xsp: float, aujourd_hui: date, hausse_vol: float = 0.0) -> float:
        """Valeur des options en dollars. Les MES valent 0 : leur gain passe en cash chaque jour."""
        total = 0.0
        for p in self.positions:
            if p.type_ == "MES":
                continue
            g = grecques(xsp, p.strike, p.annees(aujourd_hui), p.iv + hausse_vol, p.type_,
                         self.r, self.q)
            total += p.quantite * MULT_OPTION * g.prix
        return total

    def delta_unites(self, xsp: float, aujourd_hui: date) -> float:
        """Exposition au marché, en unités XSP : +1 = gagne 1 $ si XSP monte d'un point."""
        total = 0.0
        for p in self.positions:
            if p.type_ == "MES":
                total += p.quantite * UNITES_PAR_MES
            else:
                g = grecques(xsp, p.strike, p.annees(aujourd_hui), p.iv, p.type_, self.r, self.q)
                total += p.quantite * MULT_OPTION * g.delta
        return total

    def vega_dollars(self, xsp: float, aujourd_hui: date) -> float:
        return sum(p.quantite * MULT_OPTION
                   * grecques(xsp, p.strike, p.annees(aujourd_hui), p.iv, p.type_, self.r, self.q).vega
                   for p in self.positions if p.type_ != "MES")

    def stress(self, xsp: float, aujourd_hui: date, choc: float = STRESS_CHOC,
               hausse_vol: float = STRESS_HAUSSE_VOL) -> float:
        """Gain (négatif = perte) en dollars si XSP bouge de `choc` et la volatilité de `hausse_vol`."""
        apres = xsp * (1 + choc)
        options = self.valeur(apres, aujourd_hui, hausse_vol) - self.valeur(xsp, aujourd_hui)
        mes = sum(p.quantite * UNITES_PAR_MES * (apres - xsp)
                  for p in self.positions if p.type_ == "MES")
        return options + mes


# ── Limites ─────────────────────────────────────────────────────────────────

def etat_baisse(valeur_liquidative: float, plus_haut: float) -> str:
    """'normal', 'reduire' (−8 %) ou 'arret' (−15 %), depuis le plus haut historique."""
    # Arrondi : 92 / 100 − 1 vaut −0,0799999… en virgule flottante, et la
    # réduction ne se déclenchait pas à −8 % pile (attrapé par les tests).
    baisse = round(valeur_liquidative / plus_haut - 1, 9)
    if baisse <= ARRET:
        return "arret"
    if baisse <= REDUCTION:
        return "reduire"
    return "normal"


def facteur_taille(etat: str) -> float:
    """Ce que l'état de baisse laisse de la taille normale : 1, la moitié, ou rien."""
    return {"normal": 1.0, "reduire": 0.5, "arret": 0.0}[etat]


@dataclass(frozen=True)
class Controle:
    ok: bool
    raisons: tuple = ()


def controler_ouverture(livre_apres: Livre, perte_max_position: float, xsp: float,
                        aujourd_hui: date, valeur_liquidative: float, plus_haut: float) -> Controle:
    """Toutes les limites de la charte, vérifiées AVANT d'envoyer un ordre d'ouverture."""
    raisons = []
    etat = etat_baisse(valeur_liquidative, plus_haut)
    if etat == "arret":
        raisons.append(f"baisse depuis le plus haut ≤ {ARRET * 100:.0f} % : desk à l'arrêt")
    if perte_max_position > PERTE_MAX_POSITION * valeur_liquidative + 1e-6:
        raisons.append(f"perte max de la position {perte_max_position:,.0f} $ > "
                       f"{PERTE_MAX_POSITION * 100:.0f} % de la valeur liquidative")
    s = livre_apres.stress(xsp, aujourd_hui)
    if -s > STRESS_PERTE_MAX * valeur_liquidative:
        raisons.append(f"stress {STRESS_CHOC * 100:.0f} % : perte {-s:,.0f} $ > "
                       f"{STRESS_PERTE_MAX * 100:.0f} % de la valeur liquidative")
    return Controle(not raisons, tuple(raisons))


# ── Couverture ──────────────────────────────────────────────────────────────

def mes_a_trader(delta_unites: float, seuil_mes: float = 1.0) -> int:
    """Nombre de MES à acheter (+) ou vendre (−) pour ramener l'exposition près de zéro.

    Rien tant que l'exposition reste sous `seuil_mes` contrats : se couvrir à
    chaque petit mouvement paierait des frais pour rien (protocole : un MES).
    """
    if abs(delta_unites) <= seuil_mes * UNITES_PAR_MES:
        return 0
    return -round(delta_unites / UNITES_PAR_MES)
