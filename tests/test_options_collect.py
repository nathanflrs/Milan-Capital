"""
Collecteur de chaînes d'options (étape 2) : ce qui est verrouillé ici.

- on garde les vendredis de 7 à 60 jours, rien d'autre ;
- les prix d'exercice proches sont tous gardés, les lointains un sur cinq ;
- un prix absent (NaN, -1) devient None, jamais un faux zéro ;
- une ligne garde le contrat exact, même sans grecques ;
- le fichier du jour n'est visible qu'une fois complet.
"""
import math
from datetime import date
from types import SimpleNamespace

import pandas as pd

from src.options import collect

AUJ = date(2026, 10, 22)   # un jeudi


def test_echeances_vendredis_entre_7_et_60_jours():
    echeances = [
        "20261023",   # vendredi, 1 jour : trop proche
        "20261030",   # vendredi, 8 jours
        "20261102",   # lundi : quotidienne écartée
        "20261120",   # vendredi, 29 jours
        "20261218",   # vendredi, 57 jours
        "20261225",   # vendredi, 64 jours : trop loin
    ]
    assert collect.choisir_echeances(echeances, AUJ) == ["20261030", "20261120", "20261218"]


def test_strikes_fins_pres_du_cours_et_espaces_plus_loin():
    spot = 100.0
    strikes = [85.0, 87.0, 90.0, 96.0, 97.0, 99.5, 100.0, 103.0, 104.0, 110.0, 113.0, 120.0]
    # ±3 % : 97 → 103 tous gardés ; au-delà, seulement les multiples de 5
    # jusqu'à ±12 % (90 et 110), rien au-delà (85, 120).
    assert collect.choisir_strikes(strikes, spot) == [90.0, 97.0, 99.5, 100.0, 103.0, 110.0]


def test_prix_absents_deviennent_none():
    assert collect._nombre(float("nan")) is None
    assert collect._nombre(-1) is None
    assert collect._nombre(None) is None
    assert collect._nombre(0.0) == 0.0
    assert collect._nombre("1.5") == 1.5


def _contrat(droit="P", strike=760.0):
    return SimpleNamespace(lastTradeDateOrContractMonth="20261120", strike=strike,
                           right=droit, conId=123)


def test_ligne_complete_avec_grecques():
    g = SimpleNamespace(impliedVol=0.15, delta=-0.48, gamma=0.013, vega=0.85,
                        theta=-0.19, optPrice=12.3, undPrice=762.5)
    t = SimpleNamespace(bid=11.96, ask=12.03, bidSize=10, askSize=12, last=12.04,
                        close=7.63, volume=1500, modelGreeks=g)
    r = collect.ligne("SPY", 763.6, _contrat(), t, "2026-10-22T19:45:00+00:00", AUJ)
    assert r["dte"] == 29 and r["type"] == "P" and r["conid"] == 123
    assert (r["bid"], r["ask"]) == (11.96, 12.03)
    assert r["delta"] == -0.48 and r["theta"] == -0.19       # négatifs conservés
    assert r["vol_implicite"] == 0.15


def test_ligne_sans_prix_ni_grecques_garde_le_contrat():
    nan = float("nan")
    t = SimpleNamespace(bid=-1, ask=nan, bidSize=nan, askSize=nan, last=nan,
                        close=nan, volume=nan, modelGreeks=None)
    r = collect.ligne("XSP", 766.0, _contrat("C", 800.0), t, "h", AUJ)
    assert r["strike"] == 800.0 and r["type"] == "C"
    assert all(r[k] is None for k in ("bid", "ask", "vol_implicite", "delta", "theta"))


def test_ecriture_atomique(tmp_path):
    chemin = tmp_path / "2026-10-22" / "SPY.parquet"
    collect._ecrire(pd.DataFrame({"strike": [760.0], "bid": [1.0]}), chemin)
    assert chemin.exists() and not chemin.with_suffix(".tmp").exists()
    assert pd.read_parquet(chemin)["strike"].tolist() == [760.0]


def test_journal_suit_le_dossier_choisi(tmp_path):
    j = tmp_path / "journal.csv"
    rangee = {c: "x" for c in collect.COLONNES_JOURNAL}
    collect._ecrire_journal(rangee, j)
    collect._ecrire_journal(rangee, j)
    lignes = j.read_text().strip().splitlines()
    assert lignes[0].split(",") == collect.COLONNES_JOURNAL and len(lignes) == 3
