# src/options/structure.py
"""
Pièce 2 de la couche options : quel iron butterfly ouvrir, et combien.

Règles : docs/desk/phase2_observation.md, section 2. Rien n'est réglé ici
qui n'y soit écrit.

    échéance  le vendredi le plus proche de 30 jours, entre 25 et 35
    centre    le prix d'exercice le plus proche du cours (put ET call vendus)
    ailes     cours ± 2,5 × IV_ATM × √(jours/365), arrondies vers l'extérieur
    taille    min( 0,11 % × VL ÷ vega d'un lot , 2 % × VL ÷ perte max d'un lot )

L'entrée est une photo de chaîne au format du collecteur (src/options/collect.py) :
une ligne par contrat, colonnes echeance, dte, strike, type, bid, ask, delta,
vega, vol_implicite. Le desk et les études lisent donc exactement les mêmes
données.

Ce module ne parle pas au courtier : il calcule, il ne passe aucun ordre.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, List, Optional, Tuple

import pandas as pd

DTE_CIBLE, DTE_MIN, DTE_MAX = 30, 25, 35
LARGEUR_AILES = 2.5        # en mouvements attendus jusqu'à l'échéance
VEGA_CIBLE = 0.0011        # 0,11 % de la valeur liquidative par point de vol (phase 1-bis)
PERTE_MAX_POSITION = 0.02  # charte, section 5
MULTIPLICATEUR = 100


class PasDeButterfly(ValueError):
    """La chaîne ne permet pas d'ouvrir la position prévue — la raison est dans le message."""


@dataclass(frozen=True)
class Jambe:
    type: str            # 'P' ou 'C'
    strike: float
    sens: int            # +1 acheté, −1 vendu
    bid: float
    ask: float
    delta: Optional[float]
    vega: Optional[float]

    @property
    def milieu(self) -> float:
        return (self.bid + self.ask) / 2


@dataclass(frozen=True)
class Butterfly:
    echeance: str
    dte: int
    spot: float
    iv_atm: float
    mouvement: float          # 1 mouvement attendu, en points d'indice
    centre: float
    aile_put: float
    aile_call: float
    jambes: Tuple[Jambe, ...]

    @property
    def credit_milieu(self) -> float:
        """Prime encaissée par lot (par unité), au milieu des fourchettes."""
        return -sum(j.sens * j.milieu for j in self.jambes)

    @property
    def credit_naturel(self) -> float:
        """Prime encaissée en vendant au bid et en achetant à l'ask : le pire prix affiché."""
        return -sum(j.sens * (j.ask if j.sens > 0 else j.bid) for j in self.jambes)

    @property
    def perte_max_lot(self) -> float:
        """Perte maximale d'un lot en dollars, au crédit naturel (le cas prudent).

        À l'échéance, le butterfly perd au plus l'écart entre le centre et
        l'aile la plus éloignée, moins la prime encaissée.
        """
        largeur = max(self.centre - self.aile_put, self.aile_call - self.centre)
        return (largeur - self.credit_naturel) * MULTIPLICATEUR

    @property
    def vega_lot(self) -> float:
        """Dollars perdus par lot si la volatilité monte d'un point (vendeur : positif = exposé)."""
        return -sum(j.sens * (j.vega or 0.0) for j in self.jambes) * MULTIPLICATEUR

    @property
    def delta_lot(self) -> float:
        """Delta d'un lot, en unités de sous-jacent (× 100)."""
        return sum(j.sens * (j.delta or 0.0) for j in self.jambes) * MULTIPLICATEUR


def choisir_echeance(echeances: Iterable[str], aujourd_hui: date) -> Optional[str]:
    """Le vendredi le plus proche de 30 jours, entre 25 et 35 ; None s'il n'y en a pas."""
    candidates = []
    for e in set(echeances):
        d = datetime.strptime(e, "%Y%m%d").date()
        dte = (d - aujourd_hui).days
        if d.weekday() == 4 and DTE_MIN <= dte <= DTE_MAX:
            candidates.append((abs(dte - DTE_CIBLE), dte, e))
    # À égalité de distance, la plus courte : moins de temps exposé.
    return min(candidates)[2] if candidates else None


def _cotees(chaine: pd.DataFrame, type_: str) -> pd.DataFrame:
    c = chaine[(chaine["type"] == type_) & chaine["bid"].notna() & chaine["ask"].notna()]
    return c[(c["ask"] >= c["bid"]) & (c["ask"] > 0)].set_index("strike").sort_index()


def _jambe(ligne: pd.Series, type_: str, strike: float, sens: int) -> Jambe:
    nb = lambda x: None if pd.isna(x) else float(x)
    return Jambe(type_, float(strike), sens, float(ligne["bid"]), float(ligne["ask"]),
                 nb(ligne.get("delta")), nb(ligne.get("vega")))


def construire(chaine: pd.DataFrame, spot: float, aujourd_hui: date) -> Butterfly:
    """L'iron butterfly que les règles imposent aujourd'hui, ou PasDeButterfly."""
    echeance = choisir_echeance(chaine["echeance"].unique(), aujourd_hui)
    if echeance is None:
        raise PasDeButterfly(f"aucun vendredi entre {DTE_MIN} et {DTE_MAX} jours")
    ch = chaine[chaine["echeance"] == echeance]
    puts, calls = _cotees(ch, "P"), _cotees(ch, "C")
    communs = puts.index.intersection(calls.index)
    if communs.empty:
        raise PasDeButterfly(f"{echeance} : aucun prix d'exercice coté en put et en call")

    centre = float(min(communs, key=lambda k: (abs(k - spot), k)))
    ivs = [x for x in (puts.at[centre, "vol_implicite"], calls.at[centre, "vol_implicite"])
           if not pd.isna(x)]
    if not ivs:
        raise PasDeButterfly(f"{echeance} : pas de volatilité implicite au centre {centre}")
    iv_atm = sum(ivs) / len(ivs)
    dte = (datetime.strptime(echeance, "%Y%m%d").date() - aujourd_hui).days
    mouvement = spot * iv_atm * math.sqrt(dte / 365)

    # Arrondi vers l'extérieur : l'aile est au moins à la distance prévue,
    # jamais plus près — le plafond de perte ne doit pas rétrécir en douce.
    bas = puts.index[puts.index <= spot - LARGEUR_AILES * mouvement]
    haut = calls.index[calls.index >= spot + LARGEUR_AILES * mouvement]
    if bas.empty or haut.empty:
        raise PasDeButterfly(f"{echeance} : la chaîne ne va pas jusqu'aux ailes "
                             f"(±{LARGEUR_AILES * mouvement:.1f} points)")
    aile_put, aile_call = float(bas.max()), float(haut.min())

    jambes = (
        _jambe(puts.loc[aile_put], "P", aile_put, +1),
        _jambe(puts.loc[centre], "P", centre, -1),
        _jambe(calls.loc[centre], "C", centre, -1),
        _jambe(calls.loc[aile_call], "C", aile_call, +1),
    )
    return Butterfly(echeance, dte, spot, iv_atm, mouvement, centre, aile_put, aile_call, jambes)


@dataclass(frozen=True)
class Taille:
    lots: int
    lots_vega: int        # ce que permettrait la taille testée
    lots_charte: int      # ce que permet la limite de 2 % par position
    contrainte: str       # laquelle l'emporte


def taille(valeur_liquidative: float, b: Butterfly,
           vega_cible: float = VEGA_CIBLE, perte_max: float = PERTE_MAX_POSITION) -> Taille:
    """Nombre de lots : le plus petit de la taille testée et de la limite de la charte."""
    if b.vega_lot <= 0 or b.perte_max_lot <= 0:
        raise PasDeButterfly(f"butterfly incohérent : vega {b.vega_lot:.1f}, "
                             f"perte max {b.perte_max_lot:.1f}")
    lots_vega = math.floor(vega_cible * valeur_liquidative / b.vega_lot)
    lots_charte = math.floor(perte_max * valeur_liquidative / b.perte_max_lot)
    lots = max(0, min(lots_vega, lots_charte))
    return Taille(lots, lots_vega, lots_charte,
                  "charte (2 % par position)" if lots_charte < lots_vega else "taille testée")
