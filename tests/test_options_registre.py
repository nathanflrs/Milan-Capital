"""
Pièce 6 — registre et rapprochement. Ce qui est verrouillé ici :

- un butterfly ouvert se traduit par exactement quatre jambes attendues ;
- registre et courtier d'accord → ok ; la moindre différence → écart nommé ;
- une position inconnue du registre est un écart, jamais adoptée en silence ;
- les lignes hors desk (une action, un autre future) sont montrées, pas confondues ;
- le résultat d'un cycle est la variation de la valeur liquidative ;
- le registre survit à un redémarrage, écrit d'un bloc.
"""
from types import SimpleNamespace as NS

import pytest

from src.options import registre as rg

E = "20261120"


def bf(lots=3):
    return rg.Butterfly(echeance=E, aile_put=680.0, centre=765.0, aile_call=850.0, lots=lots,
                        ouvert_le="2026-10-22", credit=24.70, vega_lot=139.4,
                        perte_max_lot=6035.0, iv_atm=0.155, vl_ouverture=1_031_980.0)


def pos(secType, symbol, q, right="", strike=0.0, echeance=E):
    return NS(contract=NS(secType=secType, symbol=symbol, right=right, strike=strike,
                          lastTradeDateOrContractMonth=echeance), position=float(q))


def courtier_conforme(lots=3, mes=None):
    p = [pos("OPT", "XSP", lots, "P", 680), pos("OPT", "XSP", -lots, "P", 765),
         pos("OPT", "XSP", -lots, "C", 765), pos("OPT", "XSP", lots, "C", 850)]
    if mes:
        p.append(pos("FUT", "MES", mes, echeance="20261218"))
    return p


def test_quatre_jambes_attendues():
    livre = rg.Livre(butterfly=bf())
    assert livre.attendu() == {("P", 680.0, E): 3, ("P", 765.0, E): -3,
                               ("C", 765.0, E): -3, ("C", 850.0, E): 3}


def test_accord_avec_le_courtier():
    livre = rg.Livre(butterfly=bf())
    livre.mes_trade("20261218", -1)
    r = rg.rapprocher(livre, courtier_conforme(mes=-1))
    assert r.ok and r.resume() == "registre et courtier d'accord"


def test_compte_vide_registre_vide():
    assert rg.rapprocher(rg.Livre(), []).ok


def test_remplissage_partiel_est_un_ecart():
    r = rg.rapprocher(rg.Livre(butterfly=bf(3)), courtier_conforme(lots=2))
    assert not r.ok and len(r.ecarts) == 4
    assert "attendu +3, courtier +2" in r.resume()


def test_position_inconnue_jamais_adoptee():
    livre = rg.Livre()
    r = rg.rapprocher(livre, [pos("FUT", "MES", 2, echeance="20261218")])
    assert not r.ok and r.ecarts == ((("MES", 0.0, "20261218"), 0, 2),)
    assert livre.mes == {}                       # le registre n'a pas bougé


def test_lignes_hors_desk_montrees_sans_etre_des_ecarts():
    r = rg.rapprocher(rg.Livre(), [pos("STK", "AAPL", 390), pos("OPT", "SPY", -1, "P", 760)])
    assert r.ok and r.hors_desk == ("STK AAPL +390", "OPT SPY -1")


def test_resultat_d_un_cycle():
    livre = rg.Livre(butterfly=bf())
    c = livre.fermer(debit=10.20, le="2026-11-13", vl=1_036_100.0)
    assert c.resultat_options == pytest.approx((24.70 - 10.20) * 100 * 3)
    assert c.resultat_net == pytest.approx(4_120.0)
    assert livre.butterfly is None and livre.cycles == [c]


def test_garde_fous():
    livre = rg.Livre(butterfly=bf())
    with pytest.raises(ValueError):
        livre.ouvrir(bf())                       # pas deux butterflies à la fois
    with pytest.raises(ValueError):
        rg.Livre().fermer(1.0, "x", 1.0)         # rien à fermer
    livre.noter_vl(1_040_000); livre.noter_vl(1_020_000)
    assert livre.plus_haut == 1_040_000


def test_le_registre_survit_a_un_redemarrage(tmp_path):
    chemin = tmp_path / "livre.json"
    livre = rg.Livre(butterfly=bf(), mes={"20261218": -1}, plus_haut=1_031_980.0)
    livre.cycles.append(rg.Cycle(E, 3, "a", "b", 24.7, 10.2, 418.2, 1.0, 2.0))
    rg.sauver(livre, chemin)
    assert not chemin.with_suffix(".tmp").exists()
    relu = rg.charger(chemin)
    assert relu == livre
    assert rg.charger(tmp_path / "absent.json") == rg.Livre()
