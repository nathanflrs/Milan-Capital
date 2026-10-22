"""
Pièce 7a — les décisions du desk. Chaque test est une journée de desk.

Ce qui est verrouillé ici :
- sans accord avec le courtier, le desk ne décide rien ;
- un barreau par semaine, seulement au contrôle de 10 h 30 ;
- tout barreau à 7 jours ou moins est fermé, au prix qu'on peut vraiment obtenir ;
- un barreau sans prix complet n'est pas fermé à l'aveugle ;
- « arrêt » : plus aucune ouverture ; « réduire » : pas au-delà de deux barreaux ;
- le vega total ne dépasse jamais la taille testée ;
- la couverture neutralise l'exposition au-delà d'un MES.
"""
from datetime import date

import pytest

from src.options import decisions as dc
from src.options.registre import Butterfly as Barreau
from src.options.registre import Livre
from tests.test_options_structure import SPOT, VL, chaine

VENDREDI = date(2026, 10, 23)
LUNDI = date(2026, 10, 26)
CH = chaine(echeances=("20261030", "20261120", "20261127"))


def barreau(echeance="20261030", ouvert="2026-10-05", centre=765.0):
    return Barreau(echeance, centre - 85, centre, centre + 85, 1, ouvert, 24.70,
                   139.4, 6035.0, 0.15)


def actions(plan, type_):
    return [a for a in plan.actions if isinstance(a, type_)]


def test_sans_accord_avec_le_courtier_rien():
    p = dc.planifier(Livre(), CH, SPOT, VL, LUNDI, "10:30", registre_ok=False, ecarts="MES +2")
    assert p.bloque and p.actions == []
    assert "intervention humaine" in p.messages[0][1]


def test_premier_barreau_le_lundi_a_10h30():
    p = dc.planifier(Livre(plus_haut=VL), CH, SPOT, VL, LUNDI, "10:30", True)
    (o,) = actions(p, dc.Ouvrir)
    assert o.lots == 1 and o.butterfly.echeance == "20261127"     # 32 j, le plus proche de 30
    assert any(r == dc.VT and "Ouverture" in t for r, t in p.messages)


def test_pas_d_ouverture_a_15h30():
    p = dc.planifier(Livre(plus_haut=VL), CH, SPOT, VL, LUNDI, "15:30", True)
    assert actions(p, dc.Ouvrir) == []


def test_un_seul_barreau_par_semaine():
    deja = barreau("20261127", ouvert="2026-10-26")
    p = dc.planifier(Livre([deja], plus_haut=VL), CH, SPOT, VL, date(2026, 10, 27), "10:30", True)
    assert actions(p, dc.Ouvrir) == []
    # Lundi férié ou ouverture ratée : le mardi rattrape.
    p = dc.planifier(Livre(plus_haut=VL), CH, SPOT, VL, date(2026, 10, 27), "10:30", True)
    assert len(actions(p, dc.Ouvrir)) == 1


def test_sortie_a_7_jours_au_prix_reel():
    b = barreau("20261030")
    p = dc.planifier(Livre([b], plus_haut=VL), CH, SPOT, VL, VENDREDI, "15:30", True)
    (f,) = actions(p, dc.Fermer)
    assert f.barreau is b
    assert f.debit_naturel >= f.debit_milieu          # le prix affiché coûte l'écart
    # 8 jours : on garde.
    p = dc.planifier(Livre([b], plus_haut=VL), CH, SPOT, VL, date(2026, 10, 22), "15:30", True)
    assert actions(p, dc.Fermer) == []


def test_pas_de_fermeture_a_l_aveugle():
    sans_prix = CH[~((CH["echeance"] == "20261030") & (CH["strike"] == 850.0))]
    p = dc.planifier(Livre([barreau("20261030")], plus_haut=VL), sans_prix, SPOT, VL,
                     VENDREDI, "15:30", True)
    assert actions(p, dc.Fermer) == []
    assert any("prix incomplets" in t for _, t in p.messages)


def test_arret_plus_d_ouverture_mais_les_sorties_continuent():
    b = barreau("20261030")
    p = dc.planifier(Livre([b], plus_haut=VL), CH, SPOT, 0.84 * VL, date(2026, 10, 23),
                     "10:30", True)
    assert actions(p, dc.Ouvrir) == [] and len(actions(p, dc.Fermer)) == 1
    assert any("arrêt" in t for _, t in p.messages)


def test_reduction_pas_au_dela_de_deux_barreaux():
    deux = [barreau("20261120", "2026-10-12"), barreau("20261127", "2026-10-19")]
    p = dc.planifier(Livre(deux, plus_haut=VL), CH, SPOT, 0.91 * VL, LUNDI, "10:30", True)
    assert actions(p, dc.Ouvrir) == []
    p = dc.planifier(Livre(deux[:1], plus_haut=VL), CH, SPOT, 0.91 * VL, LUNDI, "10:30", True)
    assert len(actions(p, dc.Ouvrir)) == 1


def test_le_vega_ne_depasse_jamais_la_taille_testee():
    # Huit barreaux déjà ouverts (semaines passées) : un de plus dépasserait 0,11 %.
    huit = [barreau("20261120", f"2026-0{m}-0{j}") for m, j in
            ((8, 3), (8, 4), (8, 5), (8, 6), (9, 1), (9, 2), (9, 3), (9, 4))]
    p = dc.planifier(Livre(huit, plus_haut=VL), CH, SPOT, VL, LUNDI, "10:30", True)
    assert actions(p, dc.Ouvrir) == []
    assert any("taille testée" in t for _, t in p.messages)


def test_couverture_neutralise_au_dela_d_un_mes():
    n, d, msg = dc.couverture(Livre(mes={"20261218": 2}), CH, SPOT, LUNDI)
    assert d == 100 and n == -2 and "vente de 2 MES" in msg
    n, d, _ = dc.couverture(Livre(), CH, SPOT, LUNDI)
    assert n == 0 and d == 0


def test_delta_recalcule_si_la_photo_n_a_pas_la_jambe():
    b = barreau("20261218")                          # échéance absente de la photo
    d = dc.delta_livre(Livre([b]), CH, SPOT, LUNDI)
    assert abs(d) < 20                               # butterfly centré : presque neutre


def test_chaque_jambe_reevaluee_a_sa_propre_volatilite():
    # Le Risk Manager l'a repéré le 2026-10-22 : avec le smile, les ailes ont
    # une volatilité plus haute que le centre. Le vega du livre doit être celui
    # de la proposition (grecques de la photo), pas celui d'une volatilité plate.
    from src.options import structure as st
    ch = chaine(echeances=("20261127",))
    smile = ch.copy()
    loin = (smile["strike"] - SPOT).abs() > 40
    smile.loc[loin, "vol_implicite"] = 0.22                     # ailes plus chères
    from src.options.greeks import grecques
    for i, l in smile[loin].iterrows():
        g = grecques(SPOT, l["strike"], l["dte"] / 365, 0.22, l["type"])
        smile.loc[i, ["bid", "ask", "delta", "vega"]] = [g.prix - 0.05, g.prix + 0.05, g.delta, g.vega]
    p = dc.planifier(Livre(plus_haut=VL), smile, SPOT, VL, LUNDI, "10:30", True)
    (o,) = actions(p, dc.Ouvrir)
    assert abs(o.vega_total_apres) == pytest.approx(o.butterfly.vega_lot, rel=0.02)
