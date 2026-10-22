"""
Pièces 3 et 4 — risque du livre, limites de la charte, couverture MES.
Ce qui est verrouillé ici :

- un MES compte pour 50 unités XSP, un contrat d'option pour 100 ;
- les seuils −8 % et −15 % se déclenchent exactement où la charte le dit ;
- le stress d'un iron butterfly ne dépasse jamais la perte maximale annoncée ;
- un put vendu sans ailes, de même taille, est refusé par le stress ;
- la couverture ne bouge pas sous un MES d'exposition, et neutralise au-delà.
"""
from datetime import date

import pytest

from src.options import risque as rq
from src.options import structure as st
from tests.test_options_structure import AUJ, SPOT, VL, chaine


def livre_butterfly(lots=3):
    b = st.construire(chaine(), SPOT, AUJ)
    return b, rq.Livre([rq.Position(j.type, j.sens * lots, j.strike, b.echeance, b.iv_atm)
                        for j in b.jambes])


def test_unites_mes_et_options():
    assert rq.Livre([rq.Position("MES", 1)]).delta_unites(SPOT, AUJ) == 50
    call_profond = rq.Livre([rq.Position("C", 1, 500.0, "20261120", 0.15)])
    assert call_profond.delta_unites(SPOT, AUJ) == pytest.approx(100, abs=1)


@pytest.mark.parametrize("vl,etat", [(100, "normal"), (92.01, "normal"), (92, "reduire"),
                                     (85.01, "reduire"), (85, "arret"), (70, "arret")])
def test_seuils_de_baisse(vl, etat):
    assert rq.etat_baisse(vl, 100) == etat


def test_facteur_taille():
    assert [rq.facteur_taille(e) for e in ("normal", "reduire", "arret")] == [1.0, 0.5, 0.0]


def test_stress_du_butterfly_borne_par_sa_perte_max():
    b, livre = livre_butterfly(lots=3)
    perte_stress = -livre.stress(SPOT, AUJ)
    assert 0 < perte_stress <= 3 * b.perte_max_lot
    ctrl = rq.controler_ouverture(livre, 3 * b.perte_max_lot, SPOT, AUJ, VL, VL)
    assert ctrl.ok, ctrl.raisons


def test_put_vendu_sans_ailes_refuse_par_le_stress():
    # 30 puts à la monnaie vendus nus : à −20 %, chacun perd ~150 points × 100.
    nu = rq.Livre([rq.Position("P", -30, 766.0, "20261120", 0.15)])
    ctrl = rq.controler_ouverture(nu, 0.0, SPOT, AUJ, VL, VL)
    assert not ctrl.ok and any("stress" in r for r in ctrl.raisons)


def test_ouverture_refusee_a_l_arret_et_au_dela_de_2_pourcents():
    b, livre = livre_butterfly(lots=3)
    assert not rq.controler_ouverture(livre, 3 * b.perte_max_lot, SPOT, AUJ, 0.84 * VL, VL).ok
    trop = rq.controler_ouverture(livre, 0.03 * VL, SPOT, AUJ, VL, VL)
    assert not trop.ok and any("2 %" in r for r in trop.raisons)


@pytest.mark.parametrize("delta,mes", [(0, 0), (40, 0), (-50, 0), (51, -1), (120, -2),
                                       (-76, 2), (-260, 5)])
def test_couverture_mes(delta, mes):
    assert rq.mes_a_trader(delta) == mes


def test_couverture_ramene_le_livre_pres_de_zero():
    b, livre = livre_butterfly(lots=3)
    choque = rq.Livre(livre.positions)
    # Le marché a monté de 3 % : le vendeur de straddle devient vendeur de marché.
    delta = choque.delta_unites(SPOT * 1.03, AUJ)
    assert delta < -50
    n = rq.mes_a_trader(delta)
    couvert = rq.Livre(livre.positions + [rq.Position("MES", n)])
    assert abs(couvert.delta_unites(SPOT * 1.03, AUJ)) <= rq.UNITES_PAR_MES / 2
