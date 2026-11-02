"""Ce qui tient l'équipe sous le budget du CIO (relevé du 2026-11-02)."""
import json
from datetime import date

from src.equipe import audit as au
from src.options import desk


def _ouvrir(echeance="20261127"):
    from types import SimpleNamespace as N
    return N(butterfly=N(echeance=echeance))


def test_un_barreau_simule_deja_approuve_n_est_pas_relu(tmp_path, monkeypatch):
    chemin = tmp_path / "accords.json"
    monkeypatch.setattr(desk, "RELECTURES_SIMULEES", chemin)
    monkeypatch.setattr(desk._accord_simule, "__defaults__", (chemin,))
    monkeypatch.setattr(desk._noter_accord_simule, "__defaults__", (chemin,))
    desk._noter_accord_simule("20261127", date(2026, 10, 27))
    ok, motif = desk._relecture(None, _ouvrir(), None, None, 0, 0, date(2026, 10, 28), "simulation")
    assert ok and "2026-10-27" in motif


def test_une_autre_echeance_simulee_est_relue(tmp_path, monkeypatch):
    chemin = tmp_path / "accords.json"
    monkeypatch.setattr(desk._accord_simule, "__defaults__", (chemin,))
    desk._noter_accord_simule("20261127", date(2026, 10, 27), chemin)
    assert desk._accord_simule("20261204") is None


def test_en_reel_chaque_ouverture_reste_relue(tmp_path, monkeypatch):
    chemin = tmp_path / "accords.json"
    chemin.write_text(json.dumps({"20261127": "2026-10-27"}))
    monkeypatch.setattr(desk._accord_simule, "__defaults__", (chemin,))
    # Sans courtier ni contexte, la relecture réelle échoue : elle a bien été tentée, donc frein.
    ok, motif = desk._relecture(None, _ouvrir(), None, None, 0, 0, date(2026, 10, 28), "reel")
    assert not ok and "Relecture impossible" in motif


def test_une_raison_deja_traitee_ne_relance_pas_l_audit(tmp_path):
    ch = tmp_path / "vus.json"
    r1 = "Desk — Middle Office : Écart LMT : registre +140"
    r2 = "Desk — Middle Office : Écart LMT : registre +150"
    assert au.raisons_nouvelles([r1], date(2026, 10, 27), ch) == [r1]
    au._noter_raisons([r1], date(2026, 10, 27), ch)
    assert au.raisons_nouvelles([r2], date(2026, 10, 28), ch) == []
    assert au.raisons_nouvelles(["Autre chose"], date(2026, 10, 28), ch) == ["Autre chose"]


def test_une_raison_ancienne_peut_revenir(tmp_path):
    ch = tmp_path / "vus.json"
    au._noter_raisons(["Écart"], date(2026, 10, 1), ch)
    assert au.raisons_nouvelles(["Écart"], date(2026, 10, 20), ch) == ["Écart"]
