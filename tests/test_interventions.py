"""Une notification « Action requise » ouvre une demande à laquelle le CIO peut répondre."""
import pytest

from src.notify import alerte, interventions as iv


@pytest.fixture
def ch(tmp_path):
    return tmp_path / "interventions.json"


class Tel:
    def __init__(self):
        self.envois = []

    def __call__(self, titre, corps, url="/", tag=None):
        self.envois.append((titre, corps, url, tag))


def test_la_notification_mene_a_la_demande(ch):
    tel = Tel()
    d = iv.demander("prop-ecart", "Action requise · Prop", "LMT : écart", ch, tel)
    assert tel.envois[0][2] == f"/interventions/{d['id']}"
    assert tel.envois[0][0] == "🔴 Action requise · Prop"


def test_un_meme_probleme_garde_sa_demande_et_rappelle(ch):
    tel = Tel()
    a = iv.demander("prop-ecart", "t", "un", ch, tel)
    b = iv.demander("prop-ecart", "t", "deux", ch, tel)
    assert a["id"] == b["id"] and len(iv.lister(ch)) == 1 and len(tel.envois) == 2
    assert iv.lister(ch)[0]["texte"] == "deux"


def test_je_m_en_occupe_coupe_les_rappels(ch):
    tel = Tel()
    d = iv.demander("prop-ecart", "t", "x", ch, tel)
    assert iv.repondre(d["id"], "je_m_en_occupe", ch)["statut"] == "ouverte"
    iv.demander("prop-ecart", "t", "x", ch, tel)
    assert len(tel.envois) == 1


def test_c_est_regle_ferme_et_le_probleme_peut_revenir(ch):
    tel = Tel()
    d = iv.demander("prop-ecart", "t", "x", ch, tel)
    assert iv.repondre(d["id"], "regle", ch)["statut"] == "fermee"
    e = iv.demander("prop-ecart", "t", "x", ch, tel)
    assert e["id"] != d["id"] and len(tel.envois) == 2


def test_reponse_inconnue_et_demande_inconnue(ch):
    d = iv.demander("k", "t", "x", ch, Tel())
    with pytest.raises(ValueError):
        iv.repondre(d["id"], "acheter", ch)
    with pytest.raises(KeyError):
        iv.repondre("absente", "regle", ch)


def test_le_pod_qui_repart_ferme_sa_demande(ch):
    iv.demander("prop-ecart", "t", "x", ch, Tel())
    assert iv.resoudre("prop-ecart", ch) is True
    assert iv.lister(ch)[0]["reponse"] == "automatique"
    assert iv.resoudre("prop-ecart", ch) is False


def test_le_telephone_en_panne_n_arrete_pas_le_pod(ch):
    def casse(*a, **k):
        raise RuntimeError("non")
    assert iv.demander("k", "t", "x", ch, casse)["statut"] == "ouverte"


def test_un_ecart_a_sa_cle_et_un_incident_la_sienne(monkeypatch, ch):
    monkeypatch.setattr(iv, "CHEMIN", ch)
    monkeypatch.setattr(iv.demander, "__defaults__", (ch, None))
    assert iv.incident("prop", "Prop", "MO", "Écart avec le courtier", Tel())["cle"] == "prop-ecart"
    assert iv.incident("prop", "Prop", "MO", "Passage interrompu", Tel())["cle"] == "prop-incident"


def test_un_pod_arrete_expres_n_alerte_pas_deux_fois(monkeypatch, ch):
    monkeypatch.setattr(iv.demander, "__defaults__", (ch, Tel()))
    monkeypatch.setattr(iv.signalee_a_l_instant, "__defaults__", (5, ch, None))
    iv.demander("prop-ecart", "t", "x")
    alerte.main("echec", "milan-prop@suivi.service")
    assert [d["cle"] for d in iv.lister(ch)] == ["prop-ecart"]


def test_un_plantage_ouvre_une_demande_et_la_reussite_la_ferme(monkeypatch, ch):
    monkeypatch.setattr(iv.demander, "__defaults__", (ch, Tel()))
    monkeypatch.setattr(iv.signalee_a_l_instant, "__defaults__", (5, ch, None))
    monkeypatch.setattr(iv.resoudre, "__defaults__", (ch,))
    alerte.main("echec", "milan-prop@suivi.service")
    assert iv.lister(ch)[0]["cle"] == "echec-prop"
    alerte.main("reussite", "milan-prop@cloture.service")
    assert iv.lister(ch)[0]["statut"] == "fermee"
