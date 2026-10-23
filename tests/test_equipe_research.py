"""
Research Analyst, sources et veille — avec de faux flux et un faux client.

Ce qui est verrouillé ici :
- un flux en panne n'arrête pas les autres ; les titres sont datés et dédoublonnés ;
- la courbe du VIX est lue correctement (normale / inversée) ;
- le briefing utilise Sonnet, la recherche web limitée aux domaines du fonds ;
- une alerte du briefing ou d'une analyse est vue par le desk (frein d'office) ;
- veille : rien de neuf → aucun appel à Claude ; du neuf → tri par Haiku ;
  gravité ≥ 3 → analyse par Sonnet ; un tri raté ne marque rien comme lu.
"""
import json
import time
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from src.equipe import alertes, research, socle as sc, sources as so, veille as vl
from tests.test_equipe_socle import FauxClient, bloc_texte, reponse

JOUR = date(2026, 10, 22)


def faux_flux(entrees_par_source):
    def parse(url):
        source = next(s for s, u in so.FLUX.items() if u == url)
        e = entrees_par_source.get(source)
        if isinstance(e, Exception):
            raise e
        return NS(entries=e or [])
    return parse


def entree(titre, il_y_a_heures=1):
    t = (datetime.now(timezone.utc) - timedelta(hours=il_y_a_heures)).timetuple()
    return {"title": titre, "summary": "…", "link": "https://wsj.com/x", "published_parsed": t}


def test_titres_flux_en_panne_et_filtre_de_date():
    parse = faux_flux({"WSJ marchés": [entree("Tech selloff deepens", 1), entree("Vieux titre", 30)],
                       "Federal Reserve": ConnectionError("délai dépassé")})
    t = so.titres(datetime.now(timezone.utc) - timedelta(hours=6), parse=parse)
    assert [x["titre"] for x in t if "titre" in x] == ["Tech selloff deepens"]
    assert any(x.get("source") == "Federal Reserve" and "erreur" in x for x in t)
    assert so.empreinte("WSJ", "Tech Selloff Deepens ") == so.empreinte("WSJ", "tech selloff deepens")


def test_courbe_du_vix():
    csv_de = lambda niveau: "DATE,OPEN,HIGH,LOW,CLOSE\n10/21/2026,1,1,1,%s\n" % niveau
    normale = so.volatilite_cboe(lire=lambda url: csv_de({"VIX9D": 14, "VIX": 16, "VIX3M": 18}[
        url.split("/")[-1].split("_")[0]]))
    assert normale["structure"].startswith("normale")
    inversee = so.volatilite_cboe(lire=lambda url: csv_de({"VIX9D": 30, "VIX": 26, "VIX3M": 22}[
        url.split("/")[-1].split("_")[0]]))
    assert inversee["structure"].startswith("inversée")


def meteo(gravite=2, alerte=False):
    return json.dumps({
        "recap_court": f"Météo {gravite}/5", "recap_detail": "…", "gravite": gravite,
        "alerte": alerte, "evenements_du_jour": [{"heure_new_york": "08:30", "titre": "CPI",
                                                  "importance": 3, "source": "bls.gov"}],
        "nouvelles_cles": [], "regime_volatilite": "VIX 16, courbe normale",
        "implications_pour_le_desk": "RAS", "signalements": "", "sources": ["bls.gov"]})


SOURCES = dict(titres_fn=lambda depuis: [], vol_fn=lambda: {"VIX": 16},
               desk_fn=lambda: {"barreaux": []})


def test_briefing_sonnet_et_recherche_limitee(tmp_path):
    c = FauxClient([reponse([bloc_texte(meteo())])])
    r = research.briefing(JOUR, client=c, dossier=tmp_path, publier=False, **SOURCES)
    assert r.ok and r.memo.gravite == 2
    req = c.requetes[0]
    assert req["model"] == sc.SONNET
    web = [t for t in req["tools"] if t.get("type") == "web_search_20260209"]
    assert web and set(web[0]["allowed_domains"]) == set(so.DOMAINES)
    assert alertes.alerte_du_jour(JOUR, tmp_path / "memos") is None


def test_alerte_du_briefing_vue_par_le_desk(tmp_path):
    c = FauxClient([reponse([bloc_texte(meteo(5, True))])])
    research.briefing(JOUR, client=c, dossier=tmp_path, publier=False, **SOURCES)
    # le mémo est rangé à la date de New York d'aujourd'hui
    aujourd_hui = datetime.now(sc.NEW_YORK).date()
    assert alertes.alerte_du_jour(aujourd_hui, tmp_path / "memos")["memo"]["gravite"] == 5


def test_meteo_d_hier_pour_le_calibrage(tmp_path):
    hier = datetime(2026, 10, 21, 13, 0, tzinfo=timezone.utc)
    r = sc.Resultat(memo=NS(model_dump=lambda: json.loads(meteo(4))), cout=0, tours=1)
    sc.sauver_memo(research.MEMBRE, "briefing", r, tmp_path / "memos", hier)
    outils = {o.nom: o for o in research._outils(JOUR, tmp_path, **SOURCES)}
    (m,) = outils["ma_meteo_d_hier"].fonction()
    assert m["jour"] == "2026-10-21" and m["gravite"] == 4


# ── Veille ──────────────────────────────────────────────────────────────────

def tri(gravite_max, retenus=()):
    return json.dumps({"recap_court": f"Veille : gravité {gravite_max}", "recap_detail": "…",
                       "retenus": [{"titre": t, "source": "WSJ marchés", "gravite": g,
                                    "raison": "…"} for t, g in retenus],
                       "gravite_max": gravite_max})


def analyse(alerte):
    return json.dumps({"recap_court": "Analyse", "recap_detail": "…", "gravite": 5 if alerte else 3,
                       "alerte": alerte, "faits_verifies": "…", "impact_pour_le_desk": "…",
                       "signalements": "", "sources": ["wsj.com"]})


def flux_fixe(*titres):
    return lambda depuis: [{"source": "WSJ marchés", "titre": t, "resume": "",
                            "publie_utc": "2026-10-22T20:00:00+00:00",
                            "id": so.empreinte("WSJ marchés", t)} for t in titres]


def test_rien_de_neuf_aucun_appel(tmp_path):
    c = FauxClient([])
    b = vl.passage(client=c, dossier=tmp_path, titres_fn=flux_fixe(), publier=False)
    assert b["nouveaux"] == 0 and c.requetes == [] and b["cout_usd"] == 0


def test_tri_haiku_puis_titres_marques_lus(tmp_path):
    c = FauxClient([reponse([bloc_texte(tri(1))])])
    b = vl.passage(client=c, dossier=tmp_path, titres_fn=flux_fixe("Fed minutes due"), publier=False)
    assert b["nouveaux"] == 1 and not b["escalade"]
    assert c.requetes[0]["model"] == sc.HAIKU and "fallbacks" not in c.requetes[0]
    c2 = FauxClient([])
    assert vl.passage(client=c2, dossier=tmp_path, titres_fn=flux_fixe("Fed minutes due"),
                      publier=False)["nouveaux"] == 0
    assert c2.requetes == []


def test_gravite_3_declenche_une_analyse_sonnet_et_l_alerte(tmp_path):
    haiku = FauxClient([reponse([bloc_texte(tri(5, [("Trump: 50% tariffs on EU", 5)]))])])
    sonnet = FauxClient([reponse([bloc_texte(analyse(True))])])
    b = vl.passage(client=haiku, client_analyse=sonnet, dossier=tmp_path, publier=False,
                   titres_fn=flux_fixe("Trump: 50% tariffs on EU"))
    assert b["escalade"] and b["alerte"]
    assert sonnet.requetes[0]["model"] == sc.SONNET
    assert "50% tariffs" in sonnet.requetes[0]["messages"][0]["content"]
    aujourd_hui = datetime.now(sc.NEW_YORK).date()
    assert alertes.alerte_du_jour(aujourd_hui, tmp_path / "memos") is not None


def test_tri_rate_ne_marque_rien_comme_lu(tmp_path):
    rate = FauxClient([], panne=TimeoutError("API"))
    vl.passage(client=rate, dossier=tmp_path, titres_fn=flux_fixe("CPI hotter"), publier=False)
    c = FauxClient([reponse([bloc_texte(tri(2))])])
    b = vl.passage(client=c, dossier=tmp_path, titres_fn=flux_fixe("CPI hotter"), publier=False)
    assert b["nouveaux"] == 1 and len(c.requetes) == 1


def test_journal_des_passages(tmp_path):
    vl.passage(client=FauxClient([]), dossier=tmp_path, titres_fn=flux_fixe(), publier=False)
    lignes = (tmp_path / "veille.csv").read_text().splitlines()
    assert lignes[0].startswith("horodatage") and len(lignes) == 2


def test_aucun_domaine_refuse_par_la_recherche_web():
    # 400 au premier briefing réel : la liste entière est refusée si un seul
    # domaine bloque le robot d'Anthropic.
    assert not set(so.DOMAINES) & set(so.DOMAINES_REFUSES)


def test_briefing_tardif_le_dit(tmp_path):
    tard = datetime(2026, 10, 22, 21, 54, tzinfo=timezone.utc)      # 17 h 54 à New York
    c = FauxClient([reponse([bloc_texte(meteo())])])
    research.briefing(client=c, dossier=tmp_path, publier=False, maintenant=tard, **SOURCES)
    assert "TARDIF" in c.requetes[0]["messages"][0]["content"]
    tot = datetime(2026, 10, 23, 12, 30, tzinfo=timezone.utc)       # 8 h 30 à New York
    c = FauxClient([reponse([bloc_texte(meteo())])])
    research.briefing(client=c, dossier=tmp_path, publier=False, maintenant=tot, **SOURCES)
    assert "TARDIF" not in c.requetes[0]["messages"][0]["content"]


def test_deux_analyses_par_jour_sauf_choc(tmp_path):
    # Budget du CIO : au-delà de deux analyses Sonnet dans la journée, une
    # gravité 3 ou 4 n'en déclenche plus ; une gravité 5 passe toujours.
    for i, (titre, g) in enumerate([("A", 4), ("B", 4), ("C", 4), ("D", 5)]):
        haiku = FauxClient([reponse([bloc_texte(tri(g, [(titre, g)]))])])
        sonnet = FauxClient([reponse([bloc_texte(analyse(False))])])
        b = vl.passage(client=haiku, client_analyse=sonnet, dossier=tmp_path, publier=False,
                       titres_fn=flux_fixe(titre))
        assert b["escalade"] == (i != 2) and len(sonnet.requetes) == (0 if i == 2 else 1)
    assert "budget" in b.get("analyse_reportee", "") or b["escalade"]
