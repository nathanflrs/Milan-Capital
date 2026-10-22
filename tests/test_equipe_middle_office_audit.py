"""
Middle Office, Audit et journaux — avec un faux client et de faux journaux.

Ce qui est verrouillé ici :
- les journées sont bornées à l'heure de New York ;
- les coûts sont agrégés par membre, avec le cumul du mois ;
- la calibration du Research Analyst est calculée par le code, jamais par Claude ;
- le rapport du soir donne au Middle Office tous ses outils ;
- journée calme → aucun post-mortem, aucun appel ;
- un frein, une alerte ou un échec déclenchent le post-mortem ;
- les leçons proposées attendent le CIO ; validées, elles entrent dans le carnet
  du membre, que celui-ci relit ; une décision ne se prend qu'une fois.
"""
import json
import sqlite3
from datetime import date, datetime, timezone
from types import SimpleNamespace as NS

import pytest

from src.equipe import audit as au
from src.equipe import journaux as jx
from src.equipe import middle_office as mo
from src.equipe import risk_manager as rm
from src.equipe import socle as sc
from tests.test_equipe_socle import FauxClient, bloc_texte, reponse

JOUR = date(2026, 10, 23)


def base_evenements(chemin, lignes):
    with sqlite3.connect(chemin) as c:
        c.execute("CREATE TABLE events (id TEXT, timestamp TEXT, type TEXT, severity TEXT, "
                  "title TEXT, body TEXT, meta TEXT, acknowledged INTEGER)")
        for i, (ts, typ, sev, qui, msg) in enumerate(lignes):
            c.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,0)",
                      (str(i), ts, typ, sev, qui, msg, json.dumps({"moment": "10:30"})))


def memo(tmp, membre, tache, contenu, ok=True, heure=15):
    r = sc.Resultat(memo=NS(model_dump=lambda: contenu) if ok else None, cout=0.01, tours=1,
                    erreur=None if ok else "panne")
    sc.sauver_memo(membre, tache, r, tmp / "memos", datetime(2026, 10, 23, heure, 0, tzinfo=timezone.utc))


# ── Journaux ────────────────────────────────────────────────────────────────

def test_bornes_a_l_heure_de_new_york():
    a, b = jx.bornes(JOUR)
    assert a.startswith("2026-10-23T04:00") and b.startswith("2026-10-24T04:00")   # EDT


def test_evenements_du_jour_seulement(tmp_path):
    db = tmp_path / "events.db"
    base_evenements(db, [("2026-10-23T14:31:00+00:00", "desk", "info", "Volatility Trader", "Ouverture"),
                         ("2026-10-24T02:00:00+00:00", "equipe", "info", "Middle Office", "Rapport"),
                         ("2026-10-24T05:00:00+00:00", "desk", "info", "Volatility Trader", "Lendemain"),
                         ("2026-10-23T15:00:00+00:00", "execution", "info", "v1", "Hors desk")])
    e = jx.evenements(JOUR, db=db)
    assert [x["message"] for x in e] == ["Ouverture", "Rapport"]   # 22 h à New York compte encore


def test_couts_par_membre_et_du_mois(tmp_path):
    c = tmp_path / "couts.csv"
    c.write_text("horodatage,membre,tache,modele,tours,entree,sortie,cache_lu,cache_ecrit,"
                 "recherches_web,cout_usd,statut\n"
                 "2026-10-23T13:00:00+00:00,Research Analyst,briefing,s,1,0,0,0,0,6,0.20,ok\n"
                 "2026-10-23T15:00:00+00:00,Risk Manager,relecture,o,2,0,0,0,0,0,0.30,ok\n"
                 "2026-10-02T15:00:00+00:00,Risk Manager,relecture,o,2,0,0,0,0,0,0.50,ok\n")
    k = jx.couts(JOUR, chemin=c)
    assert k["periode_usd"] == 0.5 and k["par_membre_usd"]["Risk Manager"] == 0.3
    assert k["mois_en_cours_usd"] == 1.0


def test_calibration_calculee_par_le_code(tmp_path):
    memo(tmp_path, "Research Analyst", "briefing", {"gravite": 4, "alerte": True}, heure=12)
    fichiers = {"SPX": "DATE,SPX\n10/22/2026,7757.17\n10/23/2026,7660.20\n",
                "VIX": "DATE,OPEN,HIGH,LOW,CLOSE\n10/22/2026,1,1,1,16.68\n10/23/2026,1,1,1,21.40\n"}
    lire = lambda url: fichiers["SPX" if "SPX" in url else "VIX"]
    (l,) = jx.mettre_a_jour_calibration(tmp_path / "memos", tmp_path / "calib.csv", lire)
    assert l["gravite"] == "4" and float(l["sp500_pct"]) == pytest.approx(-1.25, abs=0.01)
    assert float(l["vix_points"]) == pytest.approx(4.72)
    # idempotent : une journée n'est comptée qu'une fois
    assert len(jx.mettre_a_jour_calibration(tmp_path / "memos", tmp_path / "calib.csv", lire)) == 1


def test_criteres_en_simulation():
    s = [{"valeur_liquidative": "1031992", "mode": "simulation"},
         {"valeur_liquidative": "1032150", "mode": "simulation"}]
    e = [{"type": "desk", "gravite": "critical", "message": "Écart avec le courtier — MES +2"}]
    c = jx.criteres(s, e, {"cycles": []})
    assert c["F1_incidents_critiques"] == 1 and c["F2_ecarts_avec_le_courtier"] == 1
    assert c["P1_resultat_usd"] == 158 and "Simulation" in c["P1_note"]
    assert c["F3_F4_note"].startswith("Pas encore")


# ── Middle Office ───────────────────────────────────────────────────────────

RAPPORT = json.dumps({
    "recap_court": "Simulation : aucune ouverture, alerte du Research Analyst.", "recap_detail": "…",
    "mode": "simulation", "le_fonds": "1 031 992 $", "le_desk": "…", "l_equipe": "…",
    "criteres": [{"critere": "F1", "etat": "ok", "commentaire": "0 incident"}],
    "calibration_research": "…", "pour_le_cio": [], "ecarts_constates": []})


def test_rapport_du_soir(tmp_path):
    c = FauxClient([reponse([bloc_texte(RAPPORT)])])
    chemins = {"evenements": tmp_path / "e.db", "seances": tmp_path / "s.csv",
               "ordres": tmp_path / "o.csv", "livre": tmp_path / "l.json"}
    r = mo.rapport(JOUR, client=c, dossier=tmp_path, publier=False, chemins=chemins,
                   lire_cboe=lambda url: "DATE,SPX\n")
    assert r.ok and r.memo.mode == "simulation"
    assert c.requetes[0]["model"] == sc.SONNET
    noms = {t["name"] for t in c.requetes[0]["tools"]}
    assert {"seances_du_jour", "evenements_du_jour", "ordres_du_jour", "registre",
            "criteres_du_protocole", "memos_de_l_equipe", "couts_de_l_equipe",
            "calibration_du_research_analyst"} <= noms


# ── Audit ───────────────────────────────────────────────────────────────────

PM = json.dumps({
    "recap_court": "Un frein à juger à l'échéance.", "recap_detail": "…",
    "incidents": [{"quoi": "Frein", "preuve": "mémo relecture", "nature": "à juger plus tard",
                   "cause_probable": "CPI"}],
    "lecons_proposees": [{"membre": "Risk Manager", "lecon": "Citer l'heure de l'événement.",
                          "justification": "Le motif ne disait pas quand.", "change_une_regle": False,
                          "test_automatique": ""}]})


def test_journee_calme_pas_de_post_mortem(tmp_path):
    c = FauxClient([])
    assert au.postmortem(JOUR, client=c, dossier=tmp_path, db=tmp_path / "e.db",
                         publier=False) is None
    assert c.requetes == []


@pytest.mark.parametrize("membre,tache,contenu,ok,attendu", [
    ("Risk Manager", "relecture", {"decision": "freiner", "motif_principal": "CPI demain"}, True, "Frein"),
    ("Research Analyst", "analyse", {"alerte": True, "recap_court": "Choc"}, True, "Alerte"),
    ("Research Analyst", "briefing", None, False, "en échec"),
])
def test_declencheurs(tmp_path, membre, tache, contenu, ok, attendu):
    memo(tmp_path, membre, tache, contenu, ok)
    assert any(attendu in r for r in au.declencheurs(JOUR, tmp_path, tmp_path / "e.db"))


def test_post_mortem_puis_lecon_validee_lue_par_le_membre(tmp_path):
    memo(tmp_path, "Risk Manager", "relecture", {"decision": "freiner", "motif_principal": "CPI"})
    c = FauxClient([reponse([bloc_texte(PM)])])
    r = au.postmortem(JOUR, client=c, dossier=tmp_path, db=tmp_path / "e.db", publier=False)
    assert r.ok and "Frein du Risk Manager" in c.requetes[0]["messages"][0]["content"]
    (p,) = au._propositions(tmp_path / "propositions.jsonl")
    assert p["statut"] == "en_attente" and p["membre"] == "Risk Manager"
    # Rien dans le carnet tant que le CIO n'a pas décidé.
    assert not (tmp_path / "carnets" / "risk-manager.md").exists()
    au.decider(p["id"], True, dossier=tmp_path)
    carnet = (tmp_path / "carnets" / "risk-manager.md").read_text()
    assert "Citer l'heure de l'événement." in carnet
    # Le Risk Manager le relit avec son outil mon_carnet.
    outils = {o.nom: o for o in rm._outils({}, lambda a, b: 0, tmp_path / "memos", JOUR,
                                            tmp_path / "carnets" / "risk-manager.md")}
    assert "Citer l'heure" in outils["mon_carnet"].fonction()
    with pytest.raises(ValueError):
        au.decider(p["id"], False, "trop tard", dossier=tmp_path)


def test_rejet_n_ecrit_rien(tmp_path):
    au.proposer([au.Lecon(membre="Audit", lecon="x", justification="y", change_une_regle=True,
                          test_automatique="")], "revue", JOUR, tmp_path / "propositions.jsonl")
    (p,) = au._propositions(tmp_path / "propositions.jsonl")
    au.decider(p["id"], False, "pas convaincu", dossier=tmp_path)
    assert au._propositions(tmp_path / "propositions.jsonl")[0]["statut"] == "rejetee"
    assert not (tmp_path / "carnets").exists()
    with pytest.raises(KeyError):
        au.decider("inconnu", True, dossier=tmp_path)


def test_revue_du_vendredi(tmp_path):
    revue = json.dumps({
        "recap_court": "Semaine 1 : desk en simulation, équipe en rodage.", "recap_detail": "…",
        "bilan_par_membre": [{"membre": "Research Analyst", "ce_qu_il_a_fait": "5 briefings",
                              "qualite": "pas assez de données", "a_ameliorer": "—"}],
        "constats": [], "lecons_proposees": [], "memo_au_cio": "# Semaine 1\n…"})
    c = FauxClient([reponse([bloc_texte(revue)])])
    r = au.revue(date(2026, 10, 23), client=c, dossier=tmp_path, db=tmp_path / "e.db", publier=False)
    assert r.ok and "2026-10-19" in c.requetes[0]["messages"][0]["content"]   # lundi de la semaine
    assert c.requetes[0]["output_config"]["effort"] == "high"
