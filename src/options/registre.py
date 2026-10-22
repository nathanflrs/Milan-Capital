# src/options/registre.py
"""
Pièce 6 de la couche options : ce que le desk croit détenir, et la preuve que
le courtier est d'accord.

Pourquoi deux sources
---------------------
Le desk tient son propre registre (logs/desk/livre.json) : quel butterfly,
ouvert quand, à quel prix, combien de MES. C'est ce registre qui sait *pourquoi*
une position existe. Le courtier, lui, sait *ce qui existe vraiment*.

Avant toute décision, les deux sont rapprochés. S'ils divergent — un ordre
rempli à moitié, une intervention manuelle, un bug — **le desk ne décide
rien** : il signale l'écart et attend un humain. C'est le critère F2 du
protocole (docs/desk/phase2_observation.md) : zéro écart inexpliqué.

On n'« adopte » jamais automatiquement la version du courtier : corriger le
registre sans comprendre l'écart, c'est effacer la trace de l'erreur.

Échelle hebdomadaire (amendement 1 du protocole)
------------------------------------------------
Le livre contient plusieurs barreaux à la fois : un iron butterfly ouvert
chaque semaine, fermé à 7 jours. Chaque barreau est mesuré séparément (son
crédit, son débit de fermeture, son vega à l'entrée) ; le résultat net du
desk, lui, se lit sur la valeur liquidative du compte depuis l'armement, le
compte ne contenant que le desk.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

LIVRE = Path("logs/desk/livre.json")
SYMBOLE = "XSP"

Cle = Tuple[str, float, str]      # (type, strike, échéance) ; ('MES', 0, échéance)


@dataclass
class Butterfly:
    """Un barreau de l'échelle : un iron butterfly ouvert, d'un ou plusieurs lots."""
    echeance: str
    aile_put: float
    centre: float
    aile_call: float
    lots: int
    ouvert_le: str
    credit: float                 # prime encaissée par unité, prix d'exécution moyen
    vega_lot: float
    perte_max_lot: float
    iv_atm: float

    @property
    def jambes(self) -> Tuple[Tuple[str, float, int], ...]:
        """(type, strike, sens) : +1 acheté, −1 vendu."""
        return (("P", self.aile_put, +1), ("P", self.centre, -1),
                ("C", self.centre, -1), ("C", self.aile_call, +1))

    def dte(self, aujourd_hui: date) -> int:
        return (datetime.strptime(self.echeance, "%Y%m%d").date() - aujourd_hui).days


@dataclass
class Cycle:
    """Un barreau fermé : ce qu'on mesure pour le protocole."""
    echeance: str
    lots: int
    ouvert_le: str
    ferme_le: str
    credit: float
    debit_fermeture: float
    vega_ouverture: float         # vega_lot × lots, en $ par point de vol

    @property
    def resultat_options(self) -> float:
        return (self.credit - self.debit_fermeture) * 100 * self.lots

    @property
    def resultat_par_point(self) -> float:
        """Résultat ÷ vega à l'entrée : comparable à la simulation, quelle que soit la taille."""
        return self.resultat_options / self.vega_ouverture if self.vega_ouverture else 0.0


@dataclass
class Livre:
    barreaux: List[Butterfly] = field(default_factory=list)
    mes: Dict[str, int] = field(default_factory=dict)     # échéance → quantité
    plus_haut: float = 0.0                                # valeur liquidative max
    vl_armement: float = 0.0                              # point de départ de P1
    cycles: List[Cycle] = field(default_factory=list)

    # ── Ce qu'on attend chez le courtier ────────────────────────────────────
    def attendu(self) -> Dict[Cle, int]:
        a: Dict[Cle, int] = {}
        for b in self.barreaux:
            for t, k, s in b.jambes:
                cle = (t, float(k), b.echeance)
                a[cle] = a.get(cle, 0) + s * b.lots
        for e, q in self.mes.items():
            if q:
                a[("MES", 0.0, e)] = q
        return {k: v for k, v in a.items() if v}

    # ── Mises à jour, après exécution confirmée ─────────────────────────────
    def ouvrir(self, b: Butterfly) -> None:
        if b.lots <= 0:
            raise ValueError("un barreau sans lot n'est pas un barreau")
        self.barreaux.append(b)

    def fermer(self, b: Butterfly, debit: float, le: str) -> Cycle:
        if b not in self.barreaux:
            raise ValueError("ce barreau n'est pas dans le registre")
        c = Cycle(b.echeance, b.lots, b.ouvert_le, le, b.credit, debit, b.vega_lot * b.lots)
        self.cycles.append(c)
        self.barreaux.remove(b)
        return c

    def mes_trade(self, echeance: str, quantite: int) -> None:
        self.mes[echeance] = self.mes.get(echeance, 0) + quantite
        if not self.mes[echeance]:
            del self.mes[echeance]

    def noter_vl(self, vl: float) -> None:
        self.plus_haut = max(self.plus_haut, vl)


# ── Persistance ─────────────────────────────────────────────────────────────

def charger(chemin: Path = LIVRE) -> Livre:
    if not chemin.exists():
        return Livre()
    d = json.loads(chemin.read_text())
    return Livre(
        barreaux=[Butterfly(**b) for b in d.get("barreaux", [])],
        mes={k: int(v) for k, v in d.get("mes", {}).items()},
        plus_haut=float(d.get("plus_haut", 0.0)),
        vl_armement=float(d.get("vl_armement", 0.0)),
        cycles=[Cycle(**c) for c in d.get("cycles", [])],
    )


def sauver(livre: Livre, chemin: Path = LIVRE) -> None:
    """Écriture atomique : le registre n'est jamais vu à moitié écrit."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    provisoire = chemin.with_suffix(".tmp")
    provisoire.write_text(json.dumps({
        "barreaux": [asdict(b) for b in livre.barreaux],
        "mes": livre.mes, "plus_haut": livre.plus_haut, "vl_armement": livre.vl_armement,
        "cycles": [asdict(c) for c in livre.cycles],
    }, indent=2, ensure_ascii=False))
    provisoire.replace(chemin)


# ── Rapprochement ───────────────────────────────────────────────────────────

def du_courtier(positions: Iterable) -> Tuple[Dict[Cle, int], List[str]]:
    """Positions IBKR → (positions du desk, autres lignes du compte)."""
    desk: Dict[Cle, int] = {}
    autres: List[str] = []
    for p in positions:
        c, q = p.contract, int(round(float(p.position)))
        if not q:
            continue
        if c.secType == "OPT" and c.symbol == SYMBOLE:
            cle = (c.right, float(c.strike), c.lastTradeDateOrContractMonth)
        elif c.secType == "FUT" and c.symbol == "MES":
            cle = ("MES", 0.0, c.lastTradeDateOrContractMonth)
        else:
            autres.append(f"{c.secType} {c.symbol} {q:+d}")
            continue
        desk[cle] = desk.get(cle, 0) + q
    return desk, autres


@dataclass(frozen=True)
class Rapprochement:
    ok: bool
    ecarts: Tuple[Tuple[Cle, int, int], ...]      # (clé, attendu, chez le courtier)
    hors_desk: Tuple[str, ...]

    def resume(self) -> str:
        if self.ok:
            return "registre et courtier d'accord"
        return "; ".join(f"{t}{k:g} {e} : attendu {a:+d}, courtier {c:+d}"
                         for (t, k, e), a, c in self.ecarts)


def rapprocher(livre: Livre, positions: Iterable) -> Rapprochement:
    attendu = livre.attendu()
    courtier, autres = du_courtier(positions)
    ecarts = tuple(sorted(
        (cle, attendu.get(cle, 0), courtier.get(cle, 0))
        for cle in set(attendu) | set(courtier)
        if attendu.get(cle, 0) != courtier.get(cle, 0)))
    # Une ligne hors desk n'est pas un écart du desk, mais elle est montrée :
    # le compte est censé ne contenir que lui.
    return Rapprochement(not ecarts, ecarts, tuple(autres))
