"""
Pièce 2 — quel iron butterfly ouvrir, et combien. Ce qui est verrouillé ici :

- l'échéance : vendredi le plus proche de 30 jours, rien hors de 25-35 ;
- le centre a un put ET un call cotés ;
- les ailes ne sont jamais plus près que 2,5 mouvements attendus ;
- la perte maximale annoncée n'est jamais dépassée à l'échéance, quel que
  soit le cours ;
- la limite de 2 % de la charte l'emporte sur la taille testée quand elle est
  plus stricte ;
- une chaîne trop courte refuse d'ouvrir plutôt que de rapprocher les ailes.
"""
from datetime import date

import pandas as pd
import pytest

from src.options import structure as st
from src.options.collect import choisir_strikes
from src.options.greeks import grecques

AUJ = date(2026, 10, 22)           # jeudi
SPOT, IV = 766.0, 0.15
VL = 1_031_980.0                   # valeur liquidative du compte, 2026-10-22


def chaine(echeances=("20261113", "20261120", "20261127", "20261218"),
           strikes=None, ecart=0.10, iv=IV):
    """Une chaîne XSP plausible : prix Black-Scholes ± un demi-écart."""
    strikes = strikes or choisir_strikes([k / 1 for k in range(600, 900)], SPOT)
    lignes = []
    for e in echeances:
        dte = (pd.Timestamp(e).date() - AUJ).days
        for k in strikes:
            for t in ("P", "C"):
                g = grecques(SPOT, k, dte / 365, iv, t)
                lignes.append({"echeance": e, "dte": dte, "strike": float(k), "type": t,
                               "bid": max(g.prix - ecart / 2, 0.0), "ask": g.prix + ecart / 2,
                               "delta": g.delta, "vega": g.vega, "vol_implicite": iv})
    return pd.DataFrame(lignes)


def test_echeance_la_plus_proche_de_30_jours():
    assert st.choisir_echeance(["20261113", "20261120", "20261127"], AUJ) == "20261120"   # 29 j
    assert st.choisir_echeance(["20261113", "20261127"], AUJ) is None                     # 22 j, 36 j
    # Les échéances quotidiennes (jeudi, lundi) sont ignorées.
    assert st.choisir_echeance(["20261119", "20261123"], AUJ) is None
    assert st.choisir_echeance(["20261120"], date(2026, 10, 23)) == "20261120"            # 28 j


def test_butterfly_regles_du_protocole():
    b = st.construire(chaine(), SPOT, AUJ)
    assert b.echeance == "20261120" and b.dte == 29
    assert b.centre == 766.0
    # 1 mouvement = 766 × 15 % × √(29/365) ≈ 32,4 → ailes à ±81 au moins
    assert b.mouvement == pytest.approx(32.39, abs=0.05)
    assert b.aile_put <= SPOT - 2.5 * b.mouvement and b.aile_put == 685.0
    assert b.aile_call >= SPOT + 2.5 * b.mouvement and b.aile_call == 850.0
    assert [(j.type, j.strike, j.sens) for j in b.jambes] == [
        ("P", 685.0, +1), ("P", 766.0, -1), ("C", 766.0, -1), ("C", 850.0, +1)]
    assert b.credit_naturel < b.credit_milieu        # le prix affiché coûte l'écart
    assert b.vega_lot > 0                            # vendeur de volatilité
    assert abs(b.delta_lot) < 10                     # presque neutre au marché


@pytest.mark.parametrize("cours_final", [500, 650, 685, 700, 766, 830, 850, 900, 1000])
def test_la_perte_annoncee_n_est_jamais_depassee(cours_final):
    b = st.construire(chaine(), SPOT, AUJ)
    valeur_finale = sum(j.sens * (max(j.strike - cours_final, 0) if j.type == "P"
                                  else max(cours_final - j.strike, 0)) for j in b.jambes)
    resultat = (valeur_finale + b.credit_naturel) * st.MULTIPLICATEUR
    assert resultat >= -b.perte_max_lot - 1e-6


def test_la_charte_l_emporte_sur_la_taille_testee():
    b = st.construire(chaine(), SPOT, AUJ)
    t = st.taille(VL, b)
    assert t.lots == t.lots_charte < t.lots_vega
    assert t.contrainte.startswith("charte")
    assert t.lots * b.perte_max_lot <= 0.02 * VL
    assert 2 <= t.lots <= 4                          # ~3 lots, comme écrit au protocole


def test_centre_exige_put_et_call_cotes():
    c = chaine()
    sans_call = c[~((c["strike"] == 766.0) & (c["type"] == "C") & (c["echeance"] == "20261120"))]
    assert st.construire(sans_call, SPOT, AUJ).centre in (765.0, 767.0)


def test_chaine_trop_courte_refuse_d_ouvrir():
    proches = [float(k) for k in range(730, 805)]   # ±5 % seulement
    with pytest.raises(st.PasDeButterfly, match="ailes"):
        st.construire(chaine(strikes=proches), SPOT, AUJ)


def test_pas_d_echeance_pas_de_butterfly():
    with pytest.raises(st.PasDeButterfly, match="vendredi"):
        st.construire(chaine(echeances=("20261113",)), SPOT, AUJ)
