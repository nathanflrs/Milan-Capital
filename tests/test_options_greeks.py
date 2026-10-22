"""
Pièce 1 — prix et grecques. Ce qui est verrouillé ici :

- le prix exact d'un manuel (Hull) ;
- la parité put-call, qui relie le put et le call sans aucun modèle ;
- chaque grecque égale à la pente mesurée en bougeant l'entrée d'un cheveu ;
- le retour volatilité → prix → volatilité ;
- l'accord avec les grecques qu'IBKR a renvoyées le 2026-10-22 sur un vrai put SPY.
"""
import math

import pytest

from src.options.greeks import grecques, vol_implicite


def test_valeurs_du_manuel_hull():
    # Hull, Options, Futures and Other Derivatives, exemple 15.6 :
    # S=42, K=40, r=10 %, σ=20 %, T=6 mois → call 4,76, put 0,81.
    assert grecques(42, 40, 0.5, 0.2, "C", r=0.10, q=0).prix == pytest.approx(4.76, abs=0.01)
    assert grecques(42, 40, 0.5, 0.2, "P", r=0.10, q=0).prix == pytest.approx(0.81, abs=0.01)


@pytest.mark.parametrize("K", [600, 760, 900])
def test_parite_put_call(K):
    S, T, s, r, q = 766.0, 30 / 365, 0.15, 0.04, 0.012
    c, p = grecques(S, K, T, s, "C", r, q).prix, grecques(S, K, T, s, "P", r, q).prix
    assert c - p == pytest.approx(S * math.exp(-q * T) - K * math.exp(-r * T), abs=1e-9)


@pytest.mark.parametrize("type_", ["C", "P"])
def test_grecques_egales_aux_pentes(type_):
    S, K, T, s = 766.0, 770.0, 30 / 365, 0.15
    g = grecques(S, K, T, s, type_)
    h = 0.01
    prix = lambda **kw: grecques(**{"S": S, "K": K, "T": T, "sigma": s, "type_": type_, **kw}).prix
    assert g.delta == pytest.approx((prix(S=S + h) - prix(S=S - h)) / (2 * h), rel=1e-4)
    assert g.gamma == pytest.approx((prix(S=S + h) - 2 * g.prix + prix(S=S - h)) / h**2, rel=1e-3)
    # vega par point de vol, theta par jour calendaire
    assert g.vega == pytest.approx(prix(sigma=s + 0.005) - prix(sigma=s - 0.005), rel=1e-3)
    assert g.theta == pytest.approx(prix(T=T - 1 / 365) - g.prix, rel=2e-2)


def test_volatilite_implicite_aller_retour():
    p = grecques(766, 740, 30 / 365, 0.2134, "P").prix
    assert vol_implicite(p, 766, 740, 30 / 365, "P") == pytest.approx(0.2134, abs=1e-5)


def test_prix_impossible_na_pas_de_volatilite():
    # Un put à 1 $ alors qu'il vaut au moins 40 $ de valeur intrinsèque.
    assert vol_implicite(1.0, 700, 740, 30 / 365, "P") is None
    assert vol_implicite(0.0, 766, 740, 30 / 365, "P") is None


def test_echeance_atteinte_vaut_l_intrinseque():
    assert grecques(766, 740, 0, 0.2, "P").prix == 0
    assert grecques(700, 740, 0, 0.2, "P").prix == 40
    assert grecques(700, 740, 0, 0.2, "P").delta == -1


def test_accord_avec_ibkr_sur_un_vrai_put_spy():
    # Renvoyé par IBKR le 2026-10-22 (serveur, données différées) :
    # put SPY 764, échéance 20/11/2026 (29 jours), sous-jacent 762,466,
    # IV 15,150 % → prix 12,338, delta −0,4805, gamma 0,012739,
    # vega 0,8536, theta −0,1870.
    #
    # q = 0 : l'ETF SPY ne détache pas de dividende avant le 20 novembre
    # (IBKR l'indiquait : pvDividend = 0). Avec le 1,2 % continu par défaut,
    # pensé pour l'indice XSP, le prix sortait à 12,89 — 4,5 % trop haut.
    g = grecques(762.466, 764, 29 / 365, 0.1515002, "P", r=0.04, q=0.0)
    assert g.prix == pytest.approx(12.338, rel=0.03)
    assert g.delta == pytest.approx(-0.4805, abs=0.02)
    # Gamma : 0,01224 ici contre 0,01274 chez IBKR, 4 % d'écart alors que prix,
    # delta, vega et theta concordent. Notre gamma est vérifié par la pente
    # (test plus haut) : l'écart vient du modèle d'IBKR, non publié. On le
    # tolère ouvertement plutôt que de le masquer.
    assert g.gamma == pytest.approx(0.012739, rel=0.05)
    assert g.vega == pytest.approx(0.8536, rel=0.03)
    assert g.theta == pytest.approx(-0.1870, rel=0.10)
