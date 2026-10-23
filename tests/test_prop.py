"""
Le prop trader, sans courtier ni appel réel à Claude.

Ce qui est verrouillé ici :
- les indicateurs (ADX, RSI, écran) sont ceux qu'on croit, sur des séries construites ;
- le budget du CIO est appliqué par le code : S&P 500 seul, 8 positions, 8 %
  par position, 1 % de risque, stop du bon côté et à moins de 15 %, entrée à
  moins de 1 % du cours, tailles divisées par deux à −8 %, rien à −15 %,
  pause à −2 % sur la séance ;
- un stop élargi au-delà de 1 % de risque est refusé ; sortir l'est jamais ;
- le registre ferme au prix réel ce que le stop ou l'objectif ont exécuté chez
  le courtier, et s'arrête sur un écart inexpliqué ;
- le résultat du jour se calcule depuis la clôture d'hier (ou l'entrée du jour) ;
- l'agenda lit Nasdaq une fois par jour, garde le passé en cache, ne garde que le S&P 500 ;
- le plan de Claude passe par ses outils et devient des demandes normalisées ;
- la relecture du Risk Manager freine ce qu'elle ne mentionne pas, et tout le lot en cas de panne ;
- rien ne part sans PROP_ENABLED et EXECUTION_ENABLED.
"""
import json
from datetime import date
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd
import pytest

from src.equipe import risk_manager as rm
from src.prop import calendrier as cal
from src.prop import indicateurs as ind
from src.prop import livre as lv
from src.prop import ordres as od
from src.prop import regles as rg
from src.prop import trader as tr
from tests.test_equipe_socle import FauxClient, bloc_texte, reponse

VL = 1_000_000.0
JOUR = date(2026, 10, 26)


def barres(n=260, tendance=0.002, bruit=0.0, depart=100.0, graine=0):
    rng = np.random.default_rng(graine)
    c = depart * np.exp(np.cumsum(tendance + bruit * rng.standard_normal(n)))
    idx = pd.bdate_range(end="2026-10-23", periods=n)
    return pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c,
                         "Volume": np.full(n, 1e6)}, index=idx)


# ── Indicateurs ─────────────────────────────────────────────────────────────

def test_adx_fort_en_tendance_faible_sans():
    tendance = barres(tendance=0.01)
    plat = barres(tendance=0.0)
    plat["Close"] = 100 * (1 + 0.02 * np.sin(np.arange(len(plat))))      # va-et-vient sans tendance
    plat["High"], plat["Low"] = plat.Close * 1.01, plat.Close * 0.99
    a_t = ind.adx(tendance.High, tendance.Low, tendance.Close).iloc[-1]
    a_p = ind.adx(plat.High, plat.Low, plat.Close).iloc[-1]
    assert a_t > 40 and a_p < 30


def test_rsi_aux_extremes():
    assert ind.rsi(barres(tendance=0.01).Close).iloc[-1] == pytest.approx(100)
    assert ind.rsi(barres(tendance=-0.01).Close).iloc[-1] == pytest.approx(0, abs=1e-6)


def test_ecran_et_classement():
    ohlcv = {"HAUT": barres(tendance=0.004), "BAS": barres(tendance=-0.004), "COURT": barres(n=10)}
    membres = pd.DataFrame({"sector": ["Energy", "Energy", "Energy"], "sub_industry": ["x"] * 3},
                           index=["HAUT", "BAS", "COURT"])
    t = ind.ecran(ohlcv, membres)
    assert set(t.index) == {"HAUT", "BAS"}                       # trop court : écarté
    assert t.at["HAUT", "r20_pct"] == pytest.approx((np.exp(0.004 * 20) - 1) * 100, abs=0.01)
    assert t.at["HAUT", "ecart_mm200_pct"] > 0 > t.at["BAS", "ecart_mm200_pct"]
    assert [x["ticker"] for x in ind.classer(t, "r63_pct", "croissant", 5)] == ["BAS", "HAUT"]
    with pytest.raises(ValueError):
        ind.classer(t, "inconnu")
    assert ind.secteurs(t)[0]["titres"] == 2 and ind.largeur(t)["au_dessus_mm200_pct"] == 50


# ── Budget ──────────────────────────────────────────────────────────────────

MEMBRES = ["AAPL", "XOM", "JPM", "NVDA", "BRK-B"]
COURS = {"AAPL": 200.0, "XOM": 100.0, "JPM": 250.0, "NVDA": 150.0, "BRK-B": 480.0}


def demande(t="AAPL", sens=1, entree=None, stop=None, objectif=None, taille=8.0):
    e = entree or COURS[t]
    return rg.Demande(t, sens, e, stop or e * (1 - 0.05 * sens), objectif or e * (1 + 0.10 * sens), taille)


def test_quantite_la_plus_petite_des_deux_limites():
    # Stop à 5 % : le risque de 1 % permet 10 000 / 10 = 1 000 titres, la taille de 8 %
    # 80 000 / 200 = 400. C'est la taille qui borne.
    (o,), refus = rg.valider([demande()], lv.Livre(), VL, VL, MEMBRES, COURS)
    assert not refus and o.quantite == 400 and o.risque_usd == 4000
    # Stop à 2 $ : 10 000 / 2 = 5 000 > 400 ; stop large à 12 % : 10 000 / 24 = 416 → 416 vs 400.
    (o,), _ = rg.valider([demande(stop=176.0, taille=8)], lv.Livre(), VL, VL, MEMBRES, COURS)
    assert o.quantite == 400
    (o,), _ = rg.valider([demande(stop=176.0, taille=2)], lv.Livre(), VL, VL, MEMBRES, COURS)
    assert o.quantite == 100
    # Risque qui borne : stop à 14 % sur XOM, taille 8 % → 800 titres × 14 $ = 11 200 > 10 000.
    (o,), _ = rg.valider([demande("XOM", stop=86.0)], lv.Livre(), VL, VL, MEMBRES, COURS)
    assert o.quantite == 714 and o.risque_usd <= 0.01 * VL


def test_vente_a_decouvert():
    (o,), refus = rg.valider([demande("XOM", sens=-1)], lv.Livre(), VL, VL, MEMBRES, COURS)
    assert not refus and o.demande.stop > o.limite > o.demande.objectif


@pytest.mark.parametrize("d, motif", [
    (rg.Demande("SPY", 1, 500, 490, 520, 5), "S&P 500"),
    (demande(entree=203.0), "plus de 1 %"),
    (demande(stop=205.0), "stop du mauvais côté"),
    (demande(sens=-1, stop=190.0), "stop du mauvais côté"),
    (demande(objectif=190.0), "objectif du mauvais côté"),
    (demande(stop=160.0), "15 %"),
    (demande(taille=9.0), "taille"),
    (rg.Demande("JPM", 1, 250, 240, 0, 5), "prix manquant"),
])
def test_refus(d, motif):
    ordres, refus = rg.valider([d], lv.Livre(), VL, VL, MEMBRES, COURS)
    assert not ordres and motif in refus[0][1]


def test_pas_de_cours_pas_d_ordre():
    _, refus = rg.valider([demande("NVDA")], lv.Livre(), VL, VL, MEMBRES, {})
    assert "aucun cours" in refus[0][1]


def position(t="AAPL", sens=1, q=100, entree=200.0, stop=190.0, objectif=220.0, ouvert="2026-10-23", id_=None):
    return lv.Position(id_ or f"x-{t}", t, sens, q, entree, stop, objectif, ouvert,
                       q * abs(entree - stop))


def test_huit_positions_au_plus_et_une_par_titre():
    livre = lv.Livre(positions=[position(f"T{i}") for i in range(7)] + [position("AAPL")])
    _, refus = rg.valider([demande("XOM")], livre, VL, VL, MEMBRES, COURS)
    assert "plus de place" in refus[0][1]
    livre.positions.pop(0)
    ordres, refus = rg.valider([demande("AAPL"), demande("XOM"), demande("JPM")], livre, VL, VL,
                               MEMBRES, COURS)
    assert [o.ticker for o in ordres] == ["XOM"]
    assert "déjà" in refus[0][1] and "plus de place" in refus[1][1]


def test_limites_du_fonds():
    (o,), _ = rg.valider([demande()], lv.Livre(), 920_000, VL, MEMBRES, COURS)     # −8 %
    assert o.quantite == int(0.08 * 920_000 * 0.5 / 200)
    ok, motif = rg.peut_ouvrir(lv.Livre(), JOUR, 850_000, VL, 0.0)                 # −15 %
    assert not ok and "15 %" in motif
    ok, motif = rg.peut_ouvrir(lv.Livre(), JOUR, VL, VL, -20_000)                  # −2 % sur la séance
    assert not ok and "Pause" in motif
    assert not rg.peut_ouvrir(lv.Livre(pause_le=JOUR.isoformat()), JOUR, VL, VL, 0.0)[0]
    assert rg.peut_ouvrir(lv.Livre(pause_le="2026-10-23"), JOUR, VL, VL, 0.0)[0]


def test_ajustements():
    p = position()                                  # achat 100 à 200, stop 190
    assert rg.valider_ajustement(p, "sortir", 0, None, VL) is None
    assert rg.valider_ajustement(p, "deplacer_stop", 199.0, 205.0, VL) is None
    assert "mauvais côté" in rg.valider_ajustement(p, "deplacer_stop", 206.0, 205.0, VL)
    big = position(q=1000, stop=195.0)
    assert "1 %" in rg.valider_ajustement(big, "deplacer_stop", 185.0, 198.0, VL)
    assert "mauvais côté" in rg.valider_ajustement(p, "deplacer_objectif", 201.0, 205.0, VL)


def test_exposition():
    e = rg.exposition([position("AAPL")], [rg.Ordre(demande("XOM", sens=-1, taille=2), 200, 100.0, 1000.0, 20_000.0)],
                      {"AAPL": 210.0}, {"AAPL": "IT", "XOM": "Energy"}, VL)
    assert e["exposition_brute_pct_vl"] == pytest.approx(4.1)
    assert e["exposition_nette_pct_vl"] == pytest.approx(0.1)
    assert e["nette_par_secteur_pct_vl"] == {"Energy": -2.0, "IT": 2.1}
    assert e["risque_total_aux_stops_pct_vl"] == pytest.approx(0.2)


# ── Registre ────────────────────────────────────────────────────────────────

def pos_courtier(symbole, q, sec="STK"):
    return NS(contract=NS(secType=sec, symbol=symbole), position=q)


def fill(ref, q, prix, com=1.0, le="2026-10-26 15:02:00"):
    return NS(execution=NS(orderRef=ref, shares=q, price=prix, time=le),
              commissionReport=NS(commission=com))


def test_stop_execute_chez_le_courtier_ferme_au_prix_reel():
    livre = lv.Livre(positions=[position(id_="a"), position("BRK-B", -1, 10, 480, 500, 440, id_="b")])
    rap = lv.rapprocher(livre, [pos_courtier("BRK B", -10), pos_courtier("XSP", 1, "OPT")],
                        [fill("prop:a:stop", 60, 189.9), fill("prop:a:stop", 40, 189.8),
                         fill("prop:b:entree", 10, 480)], JOUR)
    assert rap.ok and [t.motif for t in rap.fermes] == ["stop"]
    t = rap.fermes[0]
    assert t.sortie == pytest.approx(189.86) and t.commissions == 2.0
    assert t.r == pytest.approx((100 * (189.86 - 200) - 2) / 1000)
    assert [p.id for p in livre.positions] == ["b"]


def test_ecart_inexplique_arrete_le_pod():
    livre = lv.Livre(positions=[position(id_="a")])
    rap = lv.rapprocher(livre, [], [], JOUR)                        # disparu, sans exécution
    assert not rap.ok and "AAPL" in rap.resume() and livre.positions
    rap = lv.rapprocher(lv.Livre(), [pos_courtier("TSLA", 5)], [], JOUR)   # inconnu au registre
    assert not rap.ok and "TSLA" in rap.resume()


def test_fermeture_partielle():
    livre = lv.Livre(positions=[position(q=100, id_="a")])
    t = livre.fermer(livre.positions[0], 210.0, "2026-10-26", "sortie", quantite=40)
    assert t.quantite == 40 and t.risque_initial_usd == 400 and t.r == pytest.approx(1.0)
    assert livre.positions[0].quantite == 60 and livre.positions[0].risque_initial_usd == 600


def test_resultat_du_jour():
    livre = lv.Livre(positions=[position(ouvert="2026-10-23"), position("XOM", -1, 50, 100, 105, 90,
                                                                         ouvert=JOUR.isoformat())])
    livre.trades.append(lv.Trade("c", "JPM", 1, 10, 240, 245, "2026-10-20", JOUR.isoformat(), "objectif",
                                 100, 1.0))
    r, sans = lv.resultat_du_jour(livre, JOUR, {"AAPL": 205.0, "XOM": 101.0},
                                  {"AAPL": 202.0, "XOM": 99.0, "JPM": 244.0})
    # AAPL : 100 × (205 − 202) ; XOM ouvert aujourd'hui : −50 × (101 − 100) ; JPM : 10 × (245 − 244) − 1
    assert r == 300 - 50 + 9 and not sans
    assert lv.resultat_du_jour(livre, JOUR, {}, {})[1] == ["AAPL", "XOM"]


def test_registre_sur_disque(tmp_path):
    livre = lv.Livre(positions=[position()], pause_le="2026-10-26", compteur=3)
    lv.sauver(livre, tmp_path / "l.json")
    relu = lv.charger(tmp_path / "l.json")
    assert relu.positions == livre.positions and relu.compteur == 3
    assert relu.nouvel_id(JOUR, "XOM") == "261026-XOM-4"
    with pytest.raises(ValueError):
        relu.ouvrir(position())


# ── Agenda ──────────────────────────────────────────────────────────────────

def faux_nasdaq(appels):
    def telecharger(url):
        appels.append(url)
        if "earnings" in url:
            return {"data": {"rows": [{"symbol": "BRK.B", "time": "time-after-hours", "name": "Berkshire"},
                                      {"symbol": "ZZZZ", "time": "time-pre-market", "name": "Hors indice"}]}}
        if "dividends" in url:
            return {"data": {"calendar": {"rows": [{"symbol": "XOM", "dividend_Rate": 0.99}]}}}
        return {"data": {"rows": [{"country": "United States", "eventName": "CPI", "gmt": "12:30"},
                                  {"country": "Japan", "eventName": "PMI"}]}}
    return telecharger


def test_agenda(tmp_path):
    appels = []
    a = cal.agenda(date(2026, 10, 23), MEMBRES, 2, telecharger=faux_nasdaq(appels), dossier=tmp_path)
    assert {r["ticker"] for r in a["resultats"]} == {"BRK-B"}
    assert a["resultats"][0]["moment"] == "apres_cloture"
    assert a["ex_dividendes"][0]["ticker"] == "XOM"
    assert [e["evenement"] for e in a["economie_du_jour"]] == ["CPI"]
    assert [r["jour"] for r in a["resultats"]] == ["2026-10-23", "2026-10-26"]   # le week-end sauté
    assert [r["jour"] for r in a["resultats_recents"]] == ["2026-10-21", "2026-10-22"]
    n = len(appels)
    cal.agenda(date(2026, 10, 23), MEMBRES, 1, telecharger=faux_nasdaq(appels), dossier=tmp_path)
    assert len(appels) == n                                         # passé : relu du cache

    def panne(url):
        raise OSError("hors ligne")
    assert cal.agenda(date(2026, 10, 23), MEMBRES, 1, telecharger=panne, dossier=tmp_path / "v")["erreurs"]


# ── Le Prop Trader (faux client Claude) ─────────────────────────────────────

def contexte(tmp_path, livre=None):
    ohlcv = {t: barres(depart=COURS[t] / np.exp(0.002 * 260), graine=i) for i, t in enumerate(MEMBRES)}
    membres = pd.DataFrame({"sector": ["IT", "Energy", "Financials", "IT", "Financials"],
                            "sub_industry": ["a", "b", "c", "a", "c"]}, index=MEMBRES)
    return tr.Contexte(jour=JOUR, moment="ouverture", table=ind.ecran(ohlcv, membres), ohlcv=ohlcv,
                       membres=membres, agenda={"resultats": [], "ex_dividendes": []},
                       livre=livre or lv.Livre(), vl=VL, plus_haut=VL, perte_du_jour=0.0,
                       ouvertures=(True, "Ouvertures permises."),
                       cours=lambda ts: {t: COURS[t] for t in ts if t in COURS},
                       titres=lambda depuis: [], dossier=tmp_path, as_of="2026-10-23")


def plan(**kw):
    base = {"recap_court": "Un achat.", "recap_detail": "…", "lecture_du_marche": "Calme.",
            "trades": [{"ticker": "brk.b", "sens": "achat", "entree": 480.0, "stop": 465.0,
                        "objectif": 510.0, "taille_pct_vl": 5.0, "horizon": "3 séances",
                        "catalyseur": "Résultats", "these": "…", "invalidation": "…", "conviction": 3}],
            "ajustements": [], "signalements": ""}
    base.update(kw)
    return json.dumps(base)


def appel_outil(nom, entree, id_="o1"):
    return NS(type="tool_use", name=nom, input=entree, id=id_)


def test_le_plan_passe_par_les_outils(tmp_path):
    ctx = contexte(tmp_path)
    client = FauxClient([
        reponse([appel_outil("ecran", {"critere": "r20_pct", "ordre": "decroissant", "n": 3, "secteur": ""}),
                 appel_outil("cours_actuels", {"tickers": ["BRK.B", "SPY"]}, "o2"),
                 appel_outil("fiche", {"ticker": "BRK-B"}, "o3")], stop="tool_use"),
        reponse([bloc_texte(plan())]),
    ])
    r = tr.proposer(ctx, client=client, publier=False)
    assert r.ok
    resultats = {b["tool_use_id"]: b for b in client.requetes[1]["messages"][-2]["content"]}
    assert len(json.loads(resultats["o1"]["content"])) == 3
    cours = json.loads(resultats["o2"]["content"])
    assert cours["cours"] == {"BRK-B": 480.0} and cours["hors_s&p500"] == ["SPY"]
    assert json.loads(resultats["o3"]["content"])["sous_industrie"] == "c"
    (d,) = tr.demandes(r.memo)
    assert d.ticker == "BRK-B" and d.sens == 1
    assert client.requetes[0]["model"] == tr.MODELE
    assert 'chemin="docs/desk/pods.md"' in client.requetes[0]["system"][1]["text"]        # ses règles dans son contexte
    assert list((tmp_path / "memos").glob("*/prop-trader-ouverture-*.json"))


def test_plan_invalide_rien(tmp_path):
    r = tr.proposer(contexte(tmp_path), client=FauxClient([reponse([bloc_texte("{}")])]), publier=False)
    assert not r.ok and r.memo is None


# ── Relecture du Risk Manager ───────────────────────────────────────────────

def lot(*tickers):
    return {"lot": [{"ticker": t} for t in tickers], "livre": {}, "agenda": {}}


def verdict_lot(*decisions):
    return json.dumps({"recap_court": "…", "recap_detail": "…", "lecture_du_risque": "…", "confiance": 3,
                       "decisions": [{"ticker": t, "decision": d, "motif": "m", "verifications": []}
                                     for t, d in decisions]})


def test_relecture_prop(tmp_path):
    client = FauxClient([reponse([bloc_texte(verdict_lot(("AAPL", "approuver"), ("XOM", "freiner")))])])
    v, msg, _ = rm.relire_prop(lot("AAPL", "XOM", "JPM"), JOUR, client=client, dossier=tmp_path, publier=False)
    assert v["AAPL"][0] and not v["XOM"][0]
    assert not v["JPM"][0] and "aucune décision" in v["JPM"][1]
    assert msg == "1 approuvé(s), 2 freiné(s)."


def test_relecture_prop_en_panne_freine_tout(tmp_path):
    v, msg, _ = rm.relire_prop(lot("AAPL"), JOUR, client=FauxClient([], panne=RuntimeError("API")),
                               dossier=tmp_path, publier=False)
    assert v == {"AAPL": (False, "pas d'avis valide du Risk Manager")} and "aucune ouverture" in msg


# ── Verrous ─────────────────────────────────────────────────────────────────

def test_rien_ne_part_sans_les_deux_verrous():
    assert od.mode_autorise({}) == "simulation"
    assert od.mode_autorise({"PROP_ENABLED": "true"}) == "simulation"
    assert od.mode_autorise({"EXECUTION_ENABLED": "true", "DESK_ENABLED": "true"}) == "simulation"
    assert od.mode_autorise({"PROP_ENABLED": "true", "EXECUTION_ENABLED": "true"}) == "reel"
    assert od.symbole_ibkr("BRK-B") == "BRK B"
