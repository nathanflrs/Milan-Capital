# src/acheteur/livre.py
"""
Le registre de l'acheteur de volatilité : ses straddles ouverts et fermés.

Rapproché avec le courtier avant toute décision, comme les deux autres pods :
les options sur actions du compte n'appartiennent qu'à lui (le desk ne
traite que XSP). Un écart arrête le pod jusqu'à ce qu'un humain ait compris.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

LIVRE = Path("logs/acheteur/livre.json")

Cle = Tuple[str, str, float, str]          # (ticker, type, strike, échéance)


@dataclass
class Straddle:
    ticker: str
    echeance: str
    strike: float
    lots: int
    prime: float                 # payée par unité (× 100 par lot)
    ouvert_le: str
    reaction_le: str             # séance où le marché réagit aux résultats
    prevu: float                 # mouvement prévu à l'achat
    habituel: float              # mouvement habituel à l'achat
    spot: float = 0.0            # cours de l'action à l'achat

    @property
    def cout_usd(self) -> float:
        return self.prime * 100 * self.lots


@dataclass
class Ferme:
    ticker: str
    echeance: str
    strike: float
    lots: int
    prime: float
    vente: float
    ouvert_le: str
    ferme_le: str
    prevu: float
    habituel: float
    realise: float = 0.0         # mouvement réel de l'action, entrée → sortie

    @property
    def resultat_usd(self) -> float:
        return (self.vente - self.prime) * 100 * self.lots

    @property
    def multiple(self) -> float:
        """Vente ÷ prime : 0 = tout perdu, 1 = remboursé, 2 = doublé."""
        return self.vente / self.prime if self.prime else 0.0


@dataclass
class Livre:
    straddles: List[Straddle] = field(default_factory=list)
    fermes: List[Ferme] = field(default_factory=list)

    def engage_usd(self) -> float:
        return sum(s.cout_usd for s in self.straddles)

    def attendu(self) -> Dict[Cle, int]:
        a: Dict[Cle, int] = {}
        for s in self.straddles:
            for t in ("C", "P"):
                k = (s.ticker, t, float(s.strike), s.echeance)
                a[k] = a.get(k, 0) + s.lots
        return a

    def fermer(self, s: Straddle, vente: float, le: str, realise: float = 0.0) -> Ferme:
        self.straddles.remove(s)
        f = Ferme(s.ticker, s.echeance, s.strike, s.lots, s.prime, vente, s.ouvert_le, le,
                  s.prevu, s.habituel, realise)
        self.fermes.append(f)
        return f


def charger(chemin: Path = LIVRE) -> Livre:
    if not chemin.exists():
        return Livre()
    d = json.loads(chemin.read_text())
    return Livre([Straddle(**s) for s in d.get("straddles", [])], [Ferme(**f) for f in d.get("fermes", [])])


def sauver(livre: Livre, chemin: Path = LIVRE) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    provisoire = chemin.with_suffix(".tmp")
    provisoire.write_text(json.dumps({"straddles": [asdict(s) for s in livre.straddles],
                                      "fermes": [asdict(f) for f in livre.fermes]},
                                     indent=2, ensure_ascii=False))
    provisoire.replace(chemin)


def options_du_courtier(positions: Iterable, exclus: Iterable[str] = ("XSP",)) -> Dict[Cle, int]:
    """Options sur actions du compte (celles du desk exclues) → {clé: quantité}."""
    from src.prop.calendrier import normaliser
    exclus = set(exclus)
    sortie: Dict[Cle, int] = {}
    for p in positions:
        c, q = p.contract, int(round(float(p.position)))
        if q and c.secType == "OPT" and c.symbol not in exclus:
            k = (normaliser(c.symbol.replace(" ", "-")), c.right, float(c.strike),
                 c.lastTradeDateOrContractMonth)
            sortie[k] = sortie.get(k, 0) + q
    return sortie


def rapprocher(livre: Livre, positions: Iterable) -> List[str]:
    """Les écarts entre le registre et le courtier (liste vide : d'accord)."""
    a, c = livre.attendu(), options_du_courtier(positions)
    return [f"{k[0]} {k[1]}{k[2]:g} {k[3]} : registre {a.get(k, 0):+d}, courtier {c.get(k, 0):+d}"
            for k in sorted(set(a) | set(c)) if a.get(k, 0) != c.get(k, 0)]
