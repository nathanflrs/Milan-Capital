"""
Socle de l'équipe. Avec un faux client Claude, aucun appel réel, aucun coût.

Ce qui est verrouillé ici :
- le texte de référence (charte, protocole, équipe) est dans chaque contexte,
  mis en cache en fin de préfixe ;
- un mémo invalide, un refus, une panne ou une boucle sans fin donnent None,
  jamais un mémo par défaut ;
- les outils sont appelés, leur erreur est rendue au membre au lieu de tout casser ;
- Opus et Sonnet partent avec le repli serveur, Haiku sans ;
- le coût est calculé et journalisé ;
- le schéma envoyé respecte les limites des sorties structurées.
"""
import json
from types import SimpleNamespace as NS

import pytest
from pydantic import BaseModel, Field

from src.equipe import socle as sc


class Avis(sc.Memo):
    decision: str
    confiance: int = Field(ge=1, le=5)
    points: list[str]


def bloc_texte(t):
    return NS(type="text", text=t)


def usage(entree=1000, sortie=200, lu=0, ecrit=0, recherches=0):
    return NS(input_tokens=entree, output_tokens=sortie, cache_read_input_tokens=lu,
              cache_creation_input_tokens=ecrit,
              server_tool_use=NS(web_search_requests=recherches) if recherches else None)


def reponse(contenu, stop="end_turn", u=None):
    return NS(content=contenu, stop_reason=stop, usage=u or usage(), stop_details=None)


MEMO_OK = json.dumps({"recap_court": "Approuvé.", "recap_detail": "RAS.",
                      "decision": "approuver", "confiance": 4, "points": ["stress ok"]})


class FauxClient:
    """Rend les réponses prévues, dans l'ordre ; garde les requêtes reçues."""

    def __init__(self, reponses, panne=None):
        self.reponses, self.panne, self.requetes = list(reponses), panne, []
        self.messages = NS(create=self._creer)
        self.beta = NS(messages=NS(create=self._creer))

    def _creer(self, **kw):
        if self.panne:
            raise self.panne
        self.requetes.append(kw)
        return self.reponses.pop(0)


def consulter(client, **kw):
    base = dict(membre="Risk Manager", modele=sc.OPUS, mandat="Relis.", tache="test",
                consigne="Proposition : …", format_memo=Avis, client=client, journal=None)
    return sc.consulter(**{**base, **kw})


def test_memo_valide():
    c = FauxClient([reponse([bloc_texte(MEMO_OK)])])
    r = consulter(c)
    assert r.ok and r.memo.decision == "approuver" and r.tours == 1


def test_texte_de_reference_et_cache():
    c = FauxClient([reponse([bloc_texte(MEMO_OK)])])
    consulter(c)
    system = c.requetes[0]["system"]
    assert "docs/charte.md" in system[1]["text"] and "phase2_observation" in system[1]["text"]
    assert system[-1]["cache_control"] == {"type": "ephemeral"}
    assert "Risk Manager" in system[-1]["text"]


def test_repli_serveur_pour_opus_et_sonnet_pas_pour_haiku():
    for modele, attendu in ((sc.OPUS, True), (sc.SONNET, True), (sc.HAIKU, False)):
        c = FauxClient([reponse([bloc_texte(MEMO_OK)])])
        consulter(c, modele=modele)
        assert ("fallbacks" in c.requetes[0]) is attendu


@pytest.mark.parametrize("texte,raison", [
    ('{"recap_court": "x"}', "invalide"),                                   # champs manquants
    (MEMO_OK.replace('"confiance": 4', '"confiance": 9'), "invalide"),      # hors bornes
    ("pas du json", "invalide"),
])
def test_memo_invalide_ne_vaut_rien(texte, raison):
    r = consulter(FauxClient([reponse([bloc_texte(texte)])]))
    assert not r.ok and raison in r.erreur


def test_refus_panne_troncature_boucle():
    assert "refus" in consulter(FauxClient([reponse([], stop="refusal")])).erreur
    assert "tronquée" in consulter(FauxClient([reponse([], stop="max_tokens")])).erreur
    r = consulter(FauxClient([], panne=ConnectionError("réseau")))
    assert not r.ok and "ConnectionError" in r.erreur
    appel = NS(type="tool_use", id="t", name="lire", input={})
    outil = sc.Outil("lire", "lit", {}, lambda: "x")
    r = consulter(FauxClient([reponse([appel], stop="tool_use")] * 3), outils=[outil], max_tours=3)
    assert not r.ok and "3 tours" in r.erreur


def test_outils_appeles_et_erreurs_rendues_au_membre():
    appels = [NS(type="tool_use", id="a", name="stress", input={"choc": -0.2}),
              NS(type="tool_use", id="b", name="casse", input={})]
    c = FauxClient([reponse(appels, stop="tool_use"), reponse([bloc_texte(MEMO_OK)])])
    stress = sc.Outil("stress", "stress du livre", {"choc": {"type": "number"}},
                      lambda choc: {"perte": 5277.0, "choc": choc})
    casse = sc.Outil("casse", "toujours en panne", {}, lambda: 1 / 0)
    r = consulter(c, outils=[stress, casse])
    assert r.ok and r.tours == 2
    # La liste des messages continue de grandir après l'appel : on prend le
    # dernier message « user », celui qui porte les résultats d'outils.
    resultats = [m for m in c.requetes[1]["messages"] if m["role"] == "user"][-1]["content"]
    assert json.loads(resultats[0]["content"])["perte"] == 5277.0
    assert resultats[1]["is_error"] and "division" in resultats[1]["content"]
    assert c.requetes[0]["tools"][0]["strict"] is True


def test_pause_du_serveur_reprise():
    c = FauxClient([reponse([NS(type="server_tool_use")], stop="pause_turn"),
                    reponse([bloc_texte(MEMO_OK)])])
    assert consulter(c).ok


def test_cout_calcule_et_journalise(tmp_path):
    u = usage(entree=10_000, sortie=2_000, lu=50_000, ecrit=0, recherches=3)
    c = FauxClient([reponse([bloc_texte(MEMO_OK)], u=u)])
    r = consulter(c, modele=sc.SONNET, journal=tmp_path / "couts.csv")
    # Sonnet 5.5 : 10k × 2 $ + 2k × 10 $ + 50k × 0,20 $ (par million) + 3 recherches
    assert r.cout == pytest.approx(0.02 + 0.02 + 0.01 + 0.03)
    ligne = (tmp_path / "couts.csv").read_text().splitlines()[1]
    assert "claude-sonnet-5-5" in ligne and ",ok" in ligne


def test_schema_strict():
    s = sc.schema_strict(Avis)
    assert s["additionalProperties"] is False
    assert set(s["required"]) == {"recap_court", "recap_detail", "decision", "confiance", "points"}
    texte = json.dumps(s)
    assert "minimum" not in texte and "maximum" not in texte and '"title"' not in texte


def test_memos_sauves_et_relus(tmp_path):
    r = consulter(FauxClient([reponse([bloc_texte(MEMO_OK)])]))
    from datetime import datetime, timezone
    quand = datetime(2026, 10, 23, 14, 31, tzinfo=timezone.utc)
    sc.sauver_memo("Risk Manager", "relecture", r, tmp_path, quand)
    (m,) = sc.lire_memos("2026-10-23", "Risk Manager", tmp_path)
    assert m["ok"] and m["memo"]["decision"] == "approuver"
    assert sc.lire_memos("2026-10-24", dossier=tmp_path) == []


def test_notifications_telephone():
    envoyees = []
    envoyer = lambda titre, corps, url, tag: envoyees.append((titre, corps, url, tag))
    ok = sc.Resultat(memo=NS(recap_court="Gravité 2, rien à signaler.", recap_detail="…"),
                     cout=0.01, tours=1)
    sc.publier("Research Analyst", "veille", ok, notifier=False, envoyer=envoyer)
    assert envoyees == []                                   # veille silencieuse
    sc.publier("Research Analyst", "briefing", ok, notifier=True, envoyer=envoyer)
    assert envoyees[-1] == ("Research Analyst", "Gravité 2, rien à signaler.",
                            "/?membre=research-analyst", "research-analyst-briefing")
    rate = sc.Resultat(memo=None, cout=0.0, tours=1, erreur="panne de l'API")
    sc.publier("Research Analyst", "veille", rate, notifier=False, envoyer=envoyer)
    assert "échec" in envoyees[-1][1]                        # un échec est toujours notifié


def test_une_notification_ne_casse_jamais_rien():
    def en_panne(*a, **k):
        raise ConnectionError("Apple injoignable")
    sc.notifier_telephone("x", "y", envoyer=en_panne)       # ne lève pas
