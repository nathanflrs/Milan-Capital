"""
Pièce 5 — l'exécution. Ce qui est verrouillé ici, dans l'ordre où ça ferait
le plus de dégâts :

- sans les DEUX verrous ouverts, rien n'est transmis : simulation seulement ;
- en simulation, aucun ordre n'est placé, même par accident ;
- un ordre jamais exécuté est annulé, au plus tard au bout du délai ;
- le dernier palier est au moins aussi généreux que le prix affiché ;
- fermer, c'est exactement inverser les jambes ouvertes ;
- le MES roule une semaine avant son échéance ;
- chaque ordre laisse une ligne dans le journal.
"""
from datetime import date
from types import SimpleNamespace

import pytest

from src.options import execution as ex
from src.options import structure as st
from tests.test_options_structure import AUJ, SPOT, chaine


# ── Un faux courtier : remplit l'ordre dès que le prix limite atteint un seuil ──

class Evenement:
    def __init__(self):
        self.abonnes = []

    def __iadd__(self, f):
        self.abonnes.append(f)
        return self

    def __isub__(self, f):
        self.abonnes.remove(f)
        return self


class FauxIB:
    def __init__(self, seuil=None, whatif=True):
        self.horloge, self.seuil, self.whatif = 0.0, seuil, whatif
        self.places, self.annules, self.simules = [], [], []
        self.errorEvent = Evenement()
        self.trade = SimpleNamespace(
            orderStatus=SimpleNamespace(filled=0, avgFillPrice=0.0, status="Submitted"),
            fills=[], isDone=lambda: self.trade.orderStatus.status in ("Filled", "Cancelled"))

    def maintenant(self):
        return self.horloge

    def sleep(self, s):
        self.horloge += s

    def placeOrder(self, contrat, ordre):
        self.places.append(ordre.lmtPrice)
        if self.seuil is not None and ordre.lmtPrice >= self.seuil:
            s = self.trade.orderStatus
            s.filled, s.avgFillPrice, s.status = ordre.totalQuantity, ordre.lmtPrice, "Filled"
        return self.trade

    def cancelOrder(self, ordre):
        self.annules.append(self.horloge)
        self.trade.orderStatus.status = "Cancelled"

    def whatIfOrder(self, contrat, ordre):
        self.simules.append(ordre.lmtPrice)
        if not self.whatif:
            for f in self.errorEvent.abonnes:
                f(1, 201, "Order rejected - reason: test", None)
            return None
        return SimpleNamespace(initMarginChange="1731.27", commission=1.7976931348623157e308,
                               maxCommission="6.2", warningText="")


# ── Verrous ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("desk,exe,mode", [
    ("true", "true", "reel"), ("true", "false", "simulation"),
    ("false", "true", "simulation"), (None, None, "simulation"), ("TRUE ", "True", "reel")])
def test_deux_verrous(desk, exe, mode):
    env = {k: v for k, v in (("DESK_ENABLED", desk), ("EXECUTION_ENABLED", exe)) if v is not None}
    assert ex.mode_autorise(env) == mode


# ── Prix ────────────────────────────────────────────────────────────────────

def test_arrondis():
    assert ex.arrondir(-24.77, 0.05) == -24.75
    assert ex.arrondir(-24.66, 0.05, "haut") == -24.65
    assert ex.arrondir(7693.4, 0.25, "haut") == 7693.5
    assert ex.arrondir(7693.4, 0.25, "bas") == 7693.25


def test_paliers_du_milieu_au_prix_affiche():
    p = ex.paliers(-24.77, -24.65)
    assert p == [-24.75, -24.7, -24.65]
    assert p[-1] >= -24.65                       # au moins le prix affiché


# ── Combo ───────────────────────────────────────────────────────────────────

def test_simulation_ne_place_aucun_ordre(tmp_path):
    ib = FauxIB(seuil=-100)
    r = ex.executer_combo(ib, "BAG", 3, [-24.75, -24.65], ex.MODE_SIMULATION,
                          maintenant=ib.maintenant, journal=tmp_path / "o.csv")
    assert ib.places == [] and ib.simules == [-24.75]
    assert r.statut == "simule" and r.marge_initiale == 1731.27 and r.commission == 6.2
    assert len((tmp_path / "o.csv").read_text().splitlines()) == 2


def test_refus_simule_garde_la_raison():
    ib = FauxIB(whatif=False)
    r = ex.executer_combo(ib, "BAG", 3, [-24.75], ex.MODE_SIMULATION,
                          maintenant=ib.maintenant, journal=None)
    assert r.statut == "refuse" and "201" in r.detail


def test_reel_rempli_au_deuxieme_palier():
    ib = FauxIB(seuil=-24.71)
    r = ex.executer_combo(ib, "BAG", 3, [-24.75, -24.7, -24.65], ex.MODE_REEL,
                          maintenant=ib.maintenant, journal=None)
    assert ib.places == [-24.75, -24.7]          # le 3e palier n'a pas servi
    assert r.statut == "rempli" and r.rempli == 3 and r.prix_moyen == -24.7
    assert ib.annules == []


def test_reel_jamais_rempli_annule_dans_le_delai():
    ib = FauxIB(seuil=None)
    r = ex.executer_combo(ib, "BAG", 3, [-24.75, -24.7, -24.65], ex.MODE_REEL,
                          attente_palier=120, delai_max=900,
                          maintenant=ib.maintenant, journal=None)
    assert r.statut == "annule" and r.rempli == 0
    assert ib.annules == [900]                   # ni avant, ni après


def test_lots_nuls_rien_n_est_envoye():
    ib = FauxIB(seuil=-100)
    r = ex.executer_combo(ib, "BAG", 0, [-24.75], ex.MODE_REEL,
                          maintenant=ib.maintenant, journal=None)
    assert ib.places == [] and r.detail == "rien à envoyer"


# ── Jambes et MES ───────────────────────────────────────────────────────────

def test_fermer_c_est_inverser_les_jambes():
    b = st.construire(chaine(), SPOT, AUJ)
    ouv, fer = ex.jambes_ouverture(b), ex.jambes_fermeture(b)
    assert [a for *_, a in ouv] == ["BUY", "SELL", "SELL", "BUY"]
    assert [(t, k) for t, k, _ in ouv] == [(t, k) for t, k, _ in fer]
    assert all({a, c} == {"BUY", "SELL"} for (*_, a), (*_, c) in zip(ouv, fer))


def test_mes_roule_une_semaine_avant_l_echeance():
    echeances = ["20261218", "20270319", "20270618"]
    assert ex.choisir_mes(echeances, date(2026, 10, 22)) == "20261218"
    assert ex.choisir_mes(echeances, date(2026, 12, 11)) == "20270319"   # 7 jours avant
    with pytest.raises(ValueError):
        ex.choisir_mes(["20261218"], date(2026, 12, 15))
