# src/options/greeks.py
"""
Pièce 1 de la couche options : le prix d'une option et ses grecques.

Pourquoi recalculer ce qu'IBKR fournit déjà
-------------------------------------------
IBKR donne les grecques du marché *tel qu'il est*. Le desk a aussi besoin de
répondre à « et si » : que vaut le livre si le S&P 500 perd 20 % et que la
volatilité bondit (test de stress de la charte) ? Seul un modèle permet de
réévaluer une option dans un monde qui n'existe pas encore.

Le modèle
---------
Black-Scholes avec rendement de dividende continu (Merton, 1973). Il est exact
pour les options européennes — c'est le cas de XSP et SPX, qui ne peuvent être
exercées qu'à l'échéance — et c'est celui qu'utilise toute la place pour
exprimer un prix en volatilité implicite.

Conventions (celles d'IBKR, pour comparer directement) :
- vega : variation du prix pour **1 point** de volatilité (0,15 → 0,16) ;
- theta : variation du prix pour **1 jour calendaire** ;
- tout est **par unité de sous-jacent** : multiplier par 100 pour un contrat.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

SQRT_2PI = math.sqrt(2 * math.pi)


def _n(x: float) -> float:
    """Densité de la loi normale."""
    return math.exp(-0.5 * x * x) / SQRT_2PI


def _N(x: float) -> float:
    """Fonction de répartition de la loi normale."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


@dataclass(frozen=True)
class Grecques:
    prix: float
    delta: float
    gamma: float
    vega: float      # par point de volatilité
    theta: float     # par jour calendaire


def _d1_d2(S: float, K: float, T: float, r: float, q: float, sigma: float):
    racine = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / racine
    return d1, d1 - racine


def grecques(S: float, K: float, T: float, sigma: float, type_: str,
             r: float = 0.04, q: float = 0.012) -> Grecques:
    """Prix et grecques d'une option européenne. T en années, type_ 'C' ou 'P'.

    r : taux sans risque ; q : rendement de dividende du S&P 500. Les valeurs
    par défaut sont des ordres de grandeur d'octobre 2026 ; le desk passe les
    siennes.
    """
    if type_ not in ("C", "P"):
        raise ValueError(f"type d'option inconnu : {type_!r}")
    if T <= 0 or sigma <= 0:
        # À l'échéance (ou sans volatilité), l'option vaut sa valeur
        # intrinsèque et n'a plus de sensibilité qu'au cours.
        intrinseque = max(S - K, 0.0) if type_ == "C" else max(K - S, 0.0)
        dans_la_monnaie = (S > K) if type_ == "C" else (S < K)
        delta = (1.0 if type_ == "C" else -1.0) if dans_la_monnaie else 0.0
        return Grecques(intrinseque, delta, 0.0, 0.0, 0.0)

    d1, d2 = _d1_d2(S, K, T, r, q, sigma)
    eq, er = math.exp(-q * T), math.exp(-r * T)
    if type_ == "C":
        prix = S * eq * _N(d1) - K * er * _N(d2)
        delta = eq * _N(d1)
        theta_an = (-S * eq * _n(d1) * sigma / (2 * math.sqrt(T))
                    - r * K * er * _N(d2) + q * S * eq * _N(d1))
    else:
        prix = K * er * _N(-d2) - S * eq * _N(-d1)
        delta = -eq * _N(-d1)
        theta_an = (-S * eq * _n(d1) * sigma / (2 * math.sqrt(T))
                    + r * K * er * _N(-d2) - q * S * eq * _N(-d1))
    gamma = eq * _n(d1) / (S * sigma * math.sqrt(T))
    vega = S * eq * _n(d1) * math.sqrt(T) / 100
    return Grecques(prix, delta, gamma, vega, theta_an / 365)


def vol_implicite(prix: float, S: float, K: float, T: float, type_: str,
                  r: float = 0.04, q: float = 0.012,
                  bas: float = 1e-4, haut: float = 5.0) -> float | None:
    """La volatilité qui redonne `prix`, par dichotomie. None si impossible.

    La dichotomie est lente mais ne diverge jamais : le prix d'une option
    croît toujours avec la volatilité. Un prix sous la valeur intrinsèque (ou
    au-dessus du maximum théorique) n'a pas de volatilité : on le dit.
    """
    if T <= 0 or prix <= 0:
        return None
    f = lambda s: grecques(S, K, T, s, type_, r, q).prix - prix
    if f(bas) > 0 or f(haut) < 0:
        return None
    for _ in range(100):
        milieu = 0.5 * (bas + haut)
        if f(milieu) > 0:
            haut = milieu
        else:
            bas = milieu
        if haut - bas < 1e-7:
            break
    return 0.5 * (bas + haut)
