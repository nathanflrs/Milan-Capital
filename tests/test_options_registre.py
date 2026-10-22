"""
Pièce 6 — registre (Middle Office) et rapprochement. Ce qui est verrouillé ici :

- un barreau ouvert se traduit par exactement quatre jambes attendues ;
- plusieurs barreaux s'additionnent, et deux jambes opposées s'annulent ;
- registre et courtier d'accord → ok ; la moindre différence → écart nommé ;
- une position inconnue du registre est un écart, jamais adoptée en silence ;
- les lignes hors desk (une action, un autre future) sont montrées, pas confondues ;
- un barreau fermé devient une mesure : résultat, résultat par point de vol ;
- le registre survit à un redémarrage, écrit d'un bloc.
"""
from datetime import date
from types import SimpleNamespace as NS

import pytest

from src.options import registre as rg

E, E2 = "20261120", "20261127"


def bf(lots=1, echeance=E, centre=765.0, ouvert="2026-10-22"):
    return rg.Butterfly(echeance=echeance, aile_put=centre - 85, centre=centre,
                        aile_call=centre + 85, lots=lots, ouvert_le=ouvert, credit=24.70,
                        vega_lot=139.4, perte_max_lot=6035.0, iv_atm=0.155)


def pos(secType, symbol, q, right="", strike=0.0, echeance=E):
    return NS(contract=NS(secType=secType, symbol=symbol, right=right, strike=strike,
                          lastTradeDateOrContractMonth=echeance), position=float(q))


def courtier(b, mes=None):
    p = [pos("OPT", "XSP", s * b.lots, t, k, b.echeance) for t, k, s in b.jambes]
    if mes:
        p.append(pos("FUT", "MES", mes, echeance="20261218"))
    return p


def test_quatre_jambes_par_barreau():
    assert rg.Livre(barreaux=[bf(3)]).attendu() == {
        ("P", 680.0, E): 3, ("P", 765.0, E): -3, ("C", 765.0, E): -3, ("C", 850.0, E): 3}


def test_les_barreaux_s_additionnent():
    livre = rg.Livre(barreaux=[bf(1, E), bf(1, E2, centre=770.0)])
    assert len(livre.attendu()) == 8
    # Même échéance, centres voisins : l'aile de l'un peut tomber sur le corps
    # de l'autre — les quantités s'additionnent, et zéro disparaît.
    # Centres 765 et 850 : le call 850 (aile du premier, +1 ; corps du second,
    # −1) et le put 765 (corps du premier, −1 ; aile du second, +1) s'annulent.
    a = rg.Livre(barreaux=[bf(1, E, 765.0), bf(1, E, 850.0)]).attendu()
    assert ("C", 850.0, E) not in a and ("P", 765.0, E) not in a
    assert a[("C", 765.0, E)] == -1 and a[("P", 850.0, E)] == -1
    assert a[("P", 680.0, E)] == 1 and a[("C", 935.0, E)] == 1


def test_accord_avec_le_courtier():
    b = bf(1)
    livre = rg.Livre(barreaux=[b])
    livre.mes_trade("20261218", -1)
    r = rg.rapprocher(livre, courtier(b, mes=-1))
    assert r.ok and r.resume() == "registre et courtier d'accord"


def test_compte_vide_registre_vide():
    assert rg.rapprocher(rg.Livre(), []).ok


def test_remplissage_partiel_est_un_ecart():
    r = rg.rapprocher(rg.Livre(barreaux=[bf(3)]), courtier(bf(2)))
    assert not r.ok and len(r.ecarts) == 4
    assert "attendu +3, courtier +2" in r.resume()


def test_position_inconnue_jamais_adoptee():
    livre = rg.Livre()
    r = rg.rapprocher(livre, [pos("FUT", "MES", 2, echeance="20261218")])
    assert not r.ok and r.ecarts == ((("MES", 0.0, "20261218"), 0, 2),)
    assert livre.mes == {}


def test_lignes_hors_desk_montrees_sans_etre_des_ecarts():
    r = rg.rapprocher(rg.Livre(), [pos("STK", "AAPL", 390), pos("OPT", "SPY", -1, "P", 760)])
    assert r.ok and r.hors_desk == ("STK AAPL +390", "OPT SPY -1")


def test_un_barreau_ferme_devient_une_mesure():
    b1, b2 = bf(1, E), bf(1, E2, 770.0)
    livre = rg.Livre(barreaux=[b1, b2])
    c = livre.fermer(b1, debit=10.20, le="2026-11-13")
    assert c.resultat_options == pytest.approx((24.70 - 10.20) * 100)
    assert c.resultat_par_point == pytest.approx(1450 / 139.4)
    assert livre.barreaux == [b2] and livre.cycles == [c]


def test_garde_fous():
    with pytest.raises(ValueError):
        rg.Livre().fermer(bf(), 1.0, "x")              # barreau inconnu
    with pytest.raises(ValueError):
        rg.Livre().ouvrir(bf(lots=0))
    livre = rg.Livre()
    livre.noter_vl(1_040_000); livre.noter_vl(1_020_000)
    assert livre.plus_haut == 1_040_000
    livre.mes_trade("20261218", 2); livre.mes_trade("20261218", -2)
    assert livre.mes == {}


def test_jours_restants():
    assert bf(echeance=E).dte(date(2026, 11, 13)) == 7


def test_le_registre_survit_a_un_redemarrage(tmp_path):
    chemin = tmp_path / "livre.json"
    livre = rg.Livre(barreaux=[bf(1), bf(1, E2, 770.0)], mes={"20261218": -1},
                     plus_haut=1_031_980.0, vl_armement=1_031_980.0)
    livre.cycles.append(rg.Cycle(E, 1, "a", "b", 24.7, 10.2, 139.4))
    rg.sauver(livre, chemin)
    assert not chemin.with_suffix(".tmp").exists()
    assert rg.charger(chemin) == livre
    assert rg.charger(tmp_path / "absent.json") == rg.Livre()
