"""
Le Risk Manager, avec un faux client Claude.

Ce qui est verrouillé ici :
- approuver laisse passer, freiner arrête ;
- panne, refus, mémo invalide : pas d'ouverture (règle 3 de l'équipe) ;
- une alerte du Research Analyst freine d'office, sans consulter Claude ;
- il travaille avec ses outils, qui lisent l'état exact de la séance ;
- son scénario de stress réévalue le vrai livre d'après ouverture ;
- ses verdicts sont sauvés et relus comme historique.
"""
import json
import math
from datetime import date
from types import SimpleNamespace as NS

import pytest

from src.equipe import contexte as cx
from src.equipe import risk_manager as rm
from src.equipe import socle as sc
from src.options import decisions as dc
from src.options.registre import Livre
from tests.test_equipe_socle import FauxClient, bloc_texte, reponse
from tests.test_options_structure import SPOT, VL, chaine

LUNDI = date(2026, 10, 26)


def verdict(decision="approuver", motif="Prime 3,1 points au-dessus de la réalisée."):
    return json.dumps({
        "recap_court": f"{decision.capitalize()} : {motif}"[:130], "recap_detail": "…",
        "decision": decision, "motif_principal": motif,
        "verifications": [{"element": "prime", "constat": "IV 15 % vs réalisée 11,9 %",
                           "statut": "ok"}],
        "confiance": 4, "ce_qui_me_ferait_changer_d_avis": "Une annonce de la Fed."})


@pytest.fixture
def seance():
    ch = chaine(echeances=("20261120", "20261127"))
    plan = dc.planifier(Livre(plus_haut=VL), ch, SPOT, VL, LUNDI, "10:30", True)
    (ouvrir,) = [a for a in plan.actions if isinstance(a, dc.Ouvrir)]
    clotures = [700 * math.exp(0.0075 * ((-1) ** i)) for i in range(90)]
    ctx = cx.construire(ouvrir, Livre(plus_haut=VL), ch, SPOT, VL, LUNDI, clotures)
    return ouvrir, ctx, cx.fonction_de_stress(ouvrir, SPOT, LUNDI)


def relire(seance, client, tmp_path):
    _, ctx, stress = seance
    return rm.relire(ctx, stress, LUNDI, client=client, dossier=tmp_path, publier=False)


def test_memo_du_soir_range_a_la_date_de_new_york(tmp_path):
    from datetime import datetime, timezone
    r = sc.Resultat(memo=NS(model_dump=lambda: {"alerte": True}), cout=0.0, tours=1)
    # 23 h 30 à New York le 26 = 3 h 30 UTC le 27.
    p = sc.sauver_memo("Research Analyst", "veille", r, tmp_path,
                       datetime(2026, 10, 27, 3, 30, tzinfo=timezone.utc))
    assert p.parent.name == "2026-10-26"


def test_volatilite_realisee():
    assert cx.vol_realisee([100.0] * 30, 21) == 0.0
    alterne = [100 * math.exp(0.01 * ((-1) ** i)) for i in range(30)]
    assert cx.vol_realisee(alterne, 21) == pytest.approx(2 * 0.01 * math.sqrt(252) * 100 *
                                                          math.sqrt(21 / 20) / 2 * 2, rel=0.05)
    assert cx.vol_realisee([100.0] * 10, 21) is None


def test_instantane_complet(seance):
    _, ctx, _ = seance
    p, l, m = ctx["proposition"], ctx["livre"], ctx["marche"]
    assert p["echeance"] == "20261127" and p["lots"] == 1
    assert p["point_mort_bas"] < p["vente_put_et_call"] < p["point_mort_haut"]
    assert l["etat_charte"] == "normal" and l["stress_charte_apres_usd"] < 0
    assert m["vol_realisee_21j_pct"] is not None and m["prime_vs_realisee_21j_points"] is not None
    assert [x["echeance"] for x in m["structure_par_terme"]] == ["20261120", "20261127"]


def test_approuver_laisse_passer(seance, tmp_path):
    ok, motif, r = relire(seance, FauxClient([reponse([bloc_texte(verdict())])]), tmp_path)
    assert ok and motif.startswith("Approuvé") and r.ok


def test_freiner_arrete(seance, tmp_path):
    c = FauxClient([reponse([bloc_texte(verdict("freiner", "CPI demain, IV sous la réalisée."))])])
    ok, motif, _ = relire(seance, c, tmp_path)
    assert not ok and "CPI demain" in motif


@pytest.mark.parametrize("client", [
    FauxClient([], panne=TimeoutError("API")),
    FauxClient([reponse([], stop="refusal")]),
    FauxClient([reponse([bloc_texte('{"decision": "approuver"}')])]),
])
def test_pas_d_avis_valide_pas_d_ouverture(seance, tmp_path, client):
    ok, motif, _ = relire(seance, client, tmp_path)
    assert not ok and "Pas d'avis valide" in motif


def test_alerte_freine_sans_consulter_claude(seance, tmp_path):
    alerte = sc.Resultat(memo=NS(model_dump=lambda: {"alerte": True,
                                                     "recap_court": "Trump : droits de douane 50 %"}),
                         cout=0.0, tours=1)
    from datetime import datetime, timezone
    sc.sauver_memo("Research Analyst", "veille", alerte, tmp_path / "memos",
                   datetime(2026, 10, 26, 13, 5, tzinfo=timezone.utc))
    client = FauxClient([])                                  # tout appel lèverait une erreur
    ok, motif, _ = relire(seance, client, tmp_path)
    assert not ok and "Frein d'office" in motif and "douane" in motif
    assert client.requetes == []


def test_il_travaille_avec_ses_outils(seance, tmp_path):
    appels = [NS(type="tool_use", id="1", name="proposition", input={}),
              NS(type="tool_use", id="2", name="scenario_de_stress",
                 input={"choc_cours": -0.10, "variation_vol": 0.15}),
              NS(type="tool_use", id="3", name="memos_du_research_analyst", input={})]
    c = FauxClient([reponse(appels, stop="tool_use"), reponse([bloc_texte(verdict())])])
    ok, _, r = relire(seance, c, tmp_path)
    assert ok and r.tours == 2
    res = [m for m in c.requetes[1]["messages"] if m["role"] == "user"][-1]["content"]
    assert json.loads(res[0]["content"])["echeance"] == "20261127"
    stress = json.loads(res[1]["content"])
    ouvrir, _, _ = seance
    perte_max = ouvrir.butterfly.perte_max_lot
    assert -perte_max - 1 <= stress["resultat_usd"] < 0         # borné par les ailes
    assert "Aucun mémo" in res[2]["content"]
    noms = {t["name"] for t in c.requetes[0]["tools"]}
    assert {"proposition", "etat_du_livre", "marche", "scenario_de_stress",
            "mes_derniers_verdicts", "mon_carnet"} <= noms
    assert c.requetes[0]["model"] == sc.OPUS


def test_verdicts_sauves_puis_relus_comme_historique(seance, tmp_path):
    relire(seance, FauxClient([reponse([bloc_texte(verdict("freiner", "Fed jeudi."))])]), tmp_path)
    appel = [NS(type="tool_use", id="h", name="mes_derniers_verdicts", input={})]
    c = FauxClient([reponse(appel, stop="tool_use"), reponse([bloc_texte(verdict())])])
    relire(seance, c, tmp_path)
    res = [m for m in c.requetes[1]["messages"] if m["role"] == "user"][-1]["content"]
    (h,) = json.loads(res[0]["content"])
    assert h["decision"] == "freiner" and h["motif"] == "Fed jeudi."
