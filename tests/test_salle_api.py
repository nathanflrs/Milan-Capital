"""
API de la salle des marchés. Journaux fictifs dans un dossier temporaire.

Ce qui est verrouillé ici :
- sans connexion, rien n'est servi ;
- l'emploi du temps est calculé à l'heure de New York (vendredi pour la revue) ;
- la courbe de gain du livre est bornée par les ailes ;
- les voyants de l'équipe suivent les événements (au travail → terminé / échec) ;
- la décision du CIO passe, s'écrit dans le carnet, et ne se prend qu'une fois.
"""
import json
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from src.dashboard import salle

JEUDI_SOIR = datetime(2026, 10, 22, 22, 0, tzinfo=timezone.utc)      # 18 h à New York


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs/desk").mkdir(parents=True)
    (tmp_path / "logs/equipe").mkdir(parents=True)

    def require_auth(request: Request) -> str:
        if request.headers.get("x-test") != "cio":
            raise HTTPException(401, "Non authentifié")
        return "nathan"

    app = FastAPI()
    app.include_router(salle.creer_routeur(require_auth))
    return TestClient(app, headers={"x-test": "cio"})


def evenements(lignes):
    with sqlite3.connect("logs/events.db") as c:
        c.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, timestamp TEXT, type TEXT, "
                  "severity TEXT, title TEXT, body TEXT, meta TEXT, acknowledged INTEGER)")
        for i, (ts, typ, sev, qui, msg, meta) in enumerate(lignes):
            c.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,0)",
                      (f"t{i}{ts}", ts, typ, sev, qui, msg, json.dumps(meta)))


def test_sans_connexion_rien(client):
    assert TestClient(client.app).get("/api/salle/etat").status_code == 401


def test_emploi_du_temps_a_l_heure_de_new_york():
    t = {(x["membre"], x["tache"]): x["a"] for x in salle.prochaines_taches(JEUDI_SOIR)}
    assert t[("Research Analyst", "briefing")] == "2026-10-23T12:30+00:00"   # vendredi 8 h 30 NY
    assert t[("Audit", "revue de la semaine")] == "2026-10-23T21:15+00:00"
    samedi = datetime(2026, 10, 24, 15, 0, tzinfo=timezone.utc)
    assert salle.prochaine([salle.time(8, 30)], None, samedi).isoformat().startswith("2026-10-26")


def test_courbe_de_gain_bornee_par_les_ailes():
    b = [{"aile_put": 680.0, "centre": 765.0, "aile_call": 850.0, "credit": 24.65, "lots": 1}]
    c = salle.courbe_de_gain(b, 765.0)
    gains = [p["gain_usd"] for p in c]
    assert max(gains) == pytest.approx(2465, abs=50)              # près du centre
    assert min(gains) == pytest.approx(-(85 - 24.65) * 100, abs=1)   # au-delà des ailes
    assert salle.courbe_de_gain([], 765.0) == []


def test_statuts():
    assert salle.statut_membre([]) == "en_veille"
    assert salle.statut_membre([{"phase": "debut", "gravite": "info"}]) == "au_travail"
    assert salle.statut_membre([{"phase": "debut", "gravite": "info"},
                                {"phase": "fin", "gravite": "info", "ok": True}]) == "termine"
    assert salle.statut_membre([{"phase": "fin", "gravite": "warning", "ok": False}]) == "echec"
    assert salle.statut_membre([{"phase": "fin", "gravite": "critical", "ok": True}]) == "alerte"


def test_etat_du_desk(client):
    with open("logs/desk/seances.csv", "w") as f:
        f.write("jour,moment,mode,valeur_liquidative,barreaux,mes,delta_avant_couverture,"
                "mes_demandes,cycles_fermes\n")
        aujourd_hui = datetime.now(salle.NEW_YORK).date().isoformat()
        f.write(f"{aujourd_hui},10:30,simulation,1031992,0,0,0,0,0\n")
        f.write(f"{aujourd_hui},15:30,simulation,1032150,0,0,0,0,0\n")
    e = client.get("/api/salle/etat").json()
    assert e["mode"] == "simulation" and e["valeur"] == 1032150
    assert e["resultat_du_jour"] == 158 and e["etat_charte"] == "normal"
    assert len(e["prochaines_taches"]) == 6


def test_voyants_de_l_equipe(client):
    maintenant = datetime.now(timezone.utc).isoformat()
    evenements([(maintenant, "equipe", "info", "Research Analyst", "Au travail : briefing.",
                 {"phase": "debut", "tache": "briefing"})])
    eq = {m["titre"]: m for m in client.get("/api/salle/equipe").json()}
    assert eq["Research Analyst"]["statut"] == "au_travail"
    assert eq["Risk Manager"]["statut"] == "en_veille" and eq["CIO"]["nature"] == "humain"
    assert eq["Risk Manager"]["modele"] == "Opus 5.5"
    assert client.get("/api/salle/equipe/inconnu").status_code == 404


def test_decision_du_cio(client):
    from src.equipe import audit
    audit.proposer([audit.Lecon(membre="Risk Manager", lecon="Citer l'heure de l'événement.",
                                justification="…", change_une_regle=False, test_automatique="")],
                   "postmortem", datetime(2026, 10, 23).date(), salle.DOSSIER / "propositions.jsonl")
    (p,) = client.get("/api/salle/propositions").json()
    r = client.post(f"/api/salle/propositions/{p['id']}/decision", json={"valider": True})
    assert r.status_code == 200 and r.json()["statut"] == "validee"
    assert "Citer l'heure" in open("logs/equipe/carnets/risk-manager.md").read()
    assert client.post(f"/api/salle/propositions/{p['id']}/decision",
                       json={"valider": False}).status_code == 409
    assert client.post("/api/salle/propositions/x/decision", json={"valider": True}).status_code == 404
    h = client.get("/api/salle/equipe/risk-manager").json()
    assert "Citer l'heure" in h["carnet"]


def test_protocole_et_rapports_vides(client):
    p = client.get("/api/salle/protocole").json()
    assert p["criteres"]["seances_enregistrees"] == 0 and p["calibration"] == []
    assert client.get("/api/salle/rapports").json() == []
    assert client.get("/api/salle/fil?jours=3").json() == []


def test_historique_v1_puis_v2(client):
    with open("logs/equity_curve.csv", "w") as f:
        f.write("date,netliq\n2026-08-13,1020809.57\n2026-08-13,1020836.07\n2026-10-21,1031916.17\n")
    with open("logs/desk/seances.csv", "w") as f:
        f.write("jour,moment,mode,valeur_liquidative,barreaux,mes,delta_avant_couverture,"
                "mes_demandes,cycles_fermes\n2026-10-21,15:30,simulation,1031920,0,0,0,0,0\n"
                "2026-10-23,10:30,simulation,1032100,0,0,0,0,0\n")
    h = client.get("/api/salle/etat").json()["historique"]
    assert [p["jour"] for p in h["points"]] == ["2026-08-13", "2026-10-21", "2026-10-23"]
    assert h["points"][0]["valeur"] == 1020836.07              # dernière valeur du jour
    assert h["points"][1] == {"jour": "2026-10-21", "valeur": 1031920.0, "epoque": "v2",
                              "resultat_depuis_debut": round(1031920 - 1020836.07, 2)}
    assert h["debut_v2"] == "2026-10-22"


def test_les_deux_autres_pods(client):
    from src.prop import livre as lv
    livre = lv.Livre(positions=[lv.Position("a", "AAPL", 1, 10, 200.0, 190.0, 220.0, "2026-10-26", 100.0)])
    livre.trades = [lv.Trade("b", "XOM", -1, 50, 100.0, 96.0, "2026-10-22", "2026-10-23", "objectif", 250.0),
                    lv.Trade("c", "JPM", 1, 10, 250.0, 240.0, "2026-10-22", "2026-10-23", "stop", 100.0)]
    lv.sauver(livre, salle.PROP / "livre.json")
    p = client.get("/api/salle/etat").json()["pods"]
    assert p["prop"]["positions"][0]["ticker"] == "AAPL" and p["prop"]["nombre_trades"] == 2
    assert p["prop"]["resultat_realise_usd"] == 100 and p["prop"]["r_cumule"] == pytest.approx(-0.2)
    assert p["prop"]["taux_reussite_pct"] == 50 and p["prop"]["trades"][0]["ticker"] == "JPM"
    assert p["acheteur"] == {"mode": "simulation", "straddles": [], "fermes": [], "nombre_fermes": 0,
                             "resultat_usd": 0, "prime_engagee_usd": 0}
    eq = {m["titre"]: m for m in client.get("/api/salle/equipe").json()}
    assert eq["Prop Trader"]["modele"] == "Opus 5.5" and eq["Acheteur de volatilité"]["nature"] == "code"
