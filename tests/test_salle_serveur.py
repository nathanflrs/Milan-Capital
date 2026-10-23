"""
Le serveur sert la salle des marchés. Ce qui est verrouillé ici :

- l'adresse principale et chaque écran rendent la salle (liens profonds) ;
- l'ancien tableau de bord reste à /v1 ;
- les données de la salle exigent une connexion ;
- le manifeste et le service worker sont ceux de la v2 (cache purgé,
  notification qui ouvre le bon écran).
"""
import pytest
from fastapi.testclient import TestClient

from src.dashboard import server


@pytest.fixture(scope="module")
def client():
    return TestClient(server.app)


@pytest.mark.parametrize("chemin", ["/", "/equipe", "/equipe/risk-manager", "/fil", "/rapports", "/protocole"])
def test_chaque_ecran_rend_la_salle(client, chemin):
    r = client.get(chemin)
    assert r.status_code == 200
    assert "Salle des marchés" in r.text and 'id="root"' in r.text
    assert r.headers["cache-control"] == "no-cache"


def test_la_v1_reste_consultable(client):
    r = client.get("/v1")
    assert r.status_code == 200 and "Salle des marchés" not in r.text


def test_les_donnees_exigent_une_connexion(client):
    for chemin in ("/api/salle/etat", "/api/salle/equipe", "/api/salle/propositions"):
        assert client.get(chemin).status_code == 401
    assert client.post("/api/salle/propositions/x/decision", json={"valider": True}).status_code == 401


def test_fichiers_de_la_salle(client):
    page = client.get("/").text
    script = page.split('src="')[1].split('"')[0]
    assert script.startswith("/salle-assets/") and client.get(script).status_code == 200
    assert client.get("/favicon.svg").headers["content-type"].startswith("image/svg")


def test_manifeste_et_service_worker(client):
    m = client.get("/manifest.json").json()
    assert m["theme_color"] == "#13213B" and m["name"] == "Milan Capital"
    sw = client.get("/sw.js").text
    assert "milan-salle-v2" in sw and "caches.delete" in sw and "navigate(url)" in sw
