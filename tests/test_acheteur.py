"""
L'acheteur de volatilité, sans courtier.

Ce qui est verrouillé ici :
- le jour de réaction : le lendemain si publié après la clôture, le jour même sinon ;
- le mouvement habituel se mesure clôture avant → clôture de réaction, sur
  les 8 derniers résultats, et rien sous 4 ;
- candidats : ce soir après la clôture, ou demain avant l'ouverture, dans l'univers ;
- l'échéance expire après le jour de réaction ;
- achat seulement sous 85 % du mouvement habituel ;
- prime : 0,5 % de la VL par straddle, 2 % au total, moitié à −8 % ;
- le registre se rapproche des options sur actions du compte (XSP exclu) ;
- rien ne part sans ACHETEUR_ENABLED et EXECUTION_ENABLED.
"""
from datetime import date, datetime
from types import SimpleNamespace as NS

import pandas as pd
import pytest

from src.acheteur import livre as lv
from src.acheteur import seance as se
from src.acheteur import strategie as st

VL = 1_000_000.0


def test_jour_de_reaction():
    assert st.jour_de_reaction(datetime(2026, 10, 23, 16, 5)) == date(2026, 10, 26)   # vendredi soir → lundi
    assert st.jour_de_reaction(datetime(2026, 10, 22, 7, 0)) == date(2026, 10, 22)
    assert st.jour_de_reaction(datetime(2026, 10, 22, 16, 0)) == date(2026, 10, 23)


def test_mouvement_habituel():
    jours = pd.bdate_range("2026-01-01", "2026-10-23")
    c = pd.Series(100.0, index=jours)
    pubs = []
    for i, (j, saut) in enumerate([("2026-02-02", 0.04), ("2026-04-01", -0.06), ("2026-06-01", 0.05),
                                   ("2026-08-03", -0.03), ("2026-09-01", 0.02)]):
        reaction = pd.Timestamp(j)
        c.loc[reaction:] *= 1 + saut
        # La moitié publiée la veille au soir, l'autre le matin même.
        pubs.append(datetime.combine((reaction - pd.offsets.BDay(1)).date(), datetime.min.time()).replace(hour=16, minute=30)
                    if i % 2 else reaction.to_pydatetime().replace(hour=7))
    h = st.mouvement_habituel(c, pubs)
    assert h["moyenne"] == pytest.approx((0.04 + 0.06 + 0.05 + 0.03 + 0.02) / 5)
    assert st.mouvement_habituel(c, pubs, n=3)["mouvements"] == pytest.approx([0.02, 0.03, 0.05])
    assert st.mouvement_habituel(c, pubs[:3]) is None                       # trop peu d'historique
    futur = pubs + [datetime(2026, 11, 2, 16, 30)]
    assert st.mouvement_habituel(c, futur)["moyenne"] == pytest.approx(h["moyenne"])


def test_candidats():
    res = [{"ticker": "AAPL", "jour": "2026-10-23", "moment": "apres_cloture"},
           {"ticker": "MSFT", "jour": "2026-10-23", "moment": "avant_ouverture"},   # déjà publié
           {"ticker": "AMZN", "jour": "2026-10-26", "moment": "avant_ouverture"},
           {"ticker": "GOOG", "jour": "2026-10-26", "moment": "apres_cloture"},     # demain soir : trop tôt
           {"ticker": "TINY", "jour": "2026-10-23", "moment": "apres_cloture"}]     # hors univers
    c = st.candidats(res, date(2026, 10, 23), ["AAPL", "MSFT", "AMZN", "GOOG"])
    assert [(x["ticker"], x["reaction"]) for x in c] == [("AAPL", "2026-10-26"), ("AMZN", "2026-10-26")]


def test_echeance_apres_la_reaction():
    e = ["20261023", "20261026", "20261030", "20261120"]
    assert st.premiere_echeance(e, date(2026, 10, 26)) == "20261030"
    assert st.premiere_echeance(e, date(2026, 12, 1)) is None


def test_juger_et_taille():
    assert st.juger(8.0, 200.0, 0.05).acheter                  # prévu 4 % < 85 % de 5 %
    a = st.juger(9.0, 200.0, 0.05)                             # 4,5 % = 90 % : non
    assert not a.acheter and "90 %" in a.motif
    assert st.lots(900.0, VL, 0.0) == 5                        # 5 000 $ ÷ 900
    assert st.lots(900.0, VL, 17_000.0) == 3                   # reste 3 000 $ sur 20 000
    assert st.lots(900.0, VL, 20_000.0) == 0
    assert st.lots(900.0, VL, 0.0, facteur=0.5) == 2


def test_univers():
    t = pd.DataFrame({"volume_dollars_20j_m": [10.0, 50.0, None, 30.0]}, index=list("ABCD"))
    assert st.univers(t, 2) == ["B", "D"]


def opt(sym, right, k, e, q):
    return NS(contract=NS(secType="OPT", symbol=sym, right=right, strike=k, lastTradeDateOrContractMonth=e),
              position=q)


def test_registre_et_rapprochement(tmp_path):
    s = lv.Straddle("AAPL", "20261030", 250.0, 2, 8.4, "2026-10-23", "2026-10-26", 0.034, 0.045, 248.0)
    livre = lv.Livre([s])
    assert livre.engage_usd() == 1680
    courtier = [opt("AAPL", "C", 250.0, "20261030", 2), opt("AAPL", "P", 250.0, "20261030", 2),
                opt("XSP", "P", 600.0, "20261120", -1), NS(contract=NS(secType="STK", symbol="AAPL"), position=5)]
    assert lv.rapprocher(livre, courtier) == []
    assert "registre +2, courtier +0" in lv.rapprocher(livre, courtier[1:])[0]
    lv.sauver(livre, tmp_path / "l.json")
    relu = lv.charger(tmp_path / "l.json")
    f = relu.fermer(relu.straddles[0], 11.0, "2026-10-26", 0.06)
    assert f.resultat_usd == pytest.approx(520) and f.multiple == pytest.approx(11 / 8.4)
    assert relu.straddles == [] and relu.engage_usd() == 0


def test_historique_en_cache(tmp_path):
    appels = []

    def lire(t):
        appels.append(t)
        return [datetime(2026, 7, 30, 16, 0)]
    for _ in range(2):
        assert se.publications_passees("AAPL", date(2026, 10, 23), tmp_path, lire) == [datetime(2026, 7, 30, 16, 0)]
    assert appels == ["AAPL"]


def test_verrous():
    assert se.mode_autorise({}) == "simulation"
    assert se.mode_autorise({"ACHETEUR_ENABLED": "true"}) == "simulation"
    assert se.mode_autorise({"PROP_ENABLED": "true", "EXECUTION_ENABLED": "true"}) == "simulation"
    assert se.mode_autorise({"ACHETEUR_ENABLED": "true", "EXECUTION_ENABLED": "true"}) == "reel"
