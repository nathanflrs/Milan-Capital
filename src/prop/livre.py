# src/prop/livre.py
"""
Le registre du prop trader : ses positions ouvertes, ses trades fermés, et la
preuve que le courtier est d'accord.

Même principe que le desk (src/options/registre.py) : le registre sait
*pourquoi* une position existe, le courtier sait *ce qui existe*. Avant toute
décision, les deux sont rapprochés.

Une différence : un stop ou un objectif posé chez IBKR peut s'exécuter entre
deux passages. Une position disparue du compte n'est donc pas forcément un
écart : si le courtier montre l'exécution de SON stop ou de SON objectif
(reconnue à sa référence d'ordre « prop:<id>:stop »), le trade est fermé au
prix réel. Sinon, c'est un écart, et le pod ne décide plus rien jusqu'à ce
qu'un humain ait compris.

Les actions du compte appartiennent toutes au prop trader : le desk traite
des options XSP et des MES, l'acheteur des options sur actions, la v1 ne
trade plus (mode observation).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

LIVRE = Path("logs/prop/livre.json")


@dataclass
class Position:
    id: str
    ticker: str
    sens: int                       # +1 acheté, −1 vendu à découvert
    quantite: int
    entree: float                   # prix moyen d'exécution
    stop: float
    objectif: float
    ouvert_le: str                  # date de New York
    risque_initial_usd: float       # quantité × |entrée − stop| à l'ouverture
    these: str = ""
    catalyseur: str = ""
    horizon: str = ""
    commissions: float = 0.0

    def resultat(self, cours: float) -> float:
        return self.sens * self.quantite * (cours - self.entree)

    def risque_au_stop(self) -> float:
        """Ce que la position perdrait au stop actuel (négatif = gain verrouillé)."""
        return self.sens * self.quantite * (self.entree - self.stop)


@dataclass
class Trade:
    id: str
    ticker: str
    sens: int
    quantite: int
    entree: float
    sortie: float
    ouvert_le: str
    ferme_le: str
    motif: str                      # 'stop', 'objectif', 'sortie', ou 'estime : …'
    risque_initial_usd: float
    commissions: float = 0.0
    these: str = ""

    @property
    def resultat_usd(self) -> float:
        return self.sens * self.quantite * (self.sortie - self.entree) - self.commissions

    @property
    def r(self) -> float:
        """Le résultat en multiples du risque pris : −1 = stop touché, comme prévu."""
        return self.resultat_usd / self.risque_initial_usd if self.risque_initial_usd else 0.0


@dataclass
class Livre:
    positions: List[Position] = field(default_factory=list)
    trades: List[Trade] = field(default_factory=list)
    pause_le: str = ""              # jour (New York) où la pause de −2 % a été déclenchée
    compteur: int = 0

    def nouvel_id(self, jour: date, ticker: str) -> str:
        self.compteur += 1
        return f"{jour.strftime('%y%m%d')}-{ticker}-{self.compteur}"

    def position(self, id_: str) -> Optional[Position]:
        return next((p for p in self.positions if p.id == id_), None)

    def attendu(self) -> Dict[str, int]:
        a: Dict[str, int] = {}
        for p in self.positions:
            a[p.ticker] = a.get(p.ticker, 0) + p.sens * p.quantite
        return {k: v for k, v in a.items() if v}

    def ouvrir(self, p: Position) -> None:
        if p.quantite <= 0:
            raise ValueError("une position sans quantité n'est pas une position")
        if any(x.ticker == p.ticker for x in self.positions):
            raise ValueError(f"{p.ticker} est déjà en portefeuille")
        self.positions.append(p)

    def fermer(self, p: Position, prix: float, le: str, motif: str,
               commission: float = 0.0, quantite: Optional[int] = None) -> Trade:
        """Ferme tout ou partie de la position au prix réel d'exécution."""
        if p not in self.positions:
            raise ValueError("cette position n'est pas dans le registre")
        q = p.quantite if quantite is None else min(quantite, p.quantite)
        part = q / p.quantite
        t = Trade(p.id, p.ticker, p.sens, q, p.entree, prix, p.ouvert_le, le, motif,
                  round(p.risque_initial_usd * part, 2), round(p.commissions * part + commission, 2),
                  p.these)
        self.trades.append(t)
        if q >= p.quantite:
            self.positions.remove(p)
        else:
            p.quantite -= q
            p.risque_initial_usd = round(p.risque_initial_usd - t.risque_initial_usd, 2)
            p.commissions = round(p.commissions * (1 - part), 2)
        return t

    def en_pause(self, jour: date) -> bool:
        return self.pause_le == jour.isoformat()


def resultat_du_jour(livre: Livre, jour: date, cours: Dict[str, float],
                     cloture_veille: Dict[str, float]) -> Tuple[float, List[str]]:
    """Le résultat du pod dans la séance, comme le calcule un courtier.

    Référence : la clôture d'hier, ou le prix d'entrée pour ce qui a été
    ouvert aujourd'hui. Les trades fermés aujourd'hui comptent au prix de
    sortie. Rend aussi les titres sans cours (comptés à zéro, et signalés).
    """
    j = jour.isoformat()
    total, sans_cours = 0.0, []
    ref = lambda ticker, entree, ouvert: entree if ouvert == j else cloture_veille.get(ticker, entree)
    for p in livre.positions:
        c = cours.get(p.ticker)
        if c is None:
            sans_cours.append(p.ticker)
            continue
        total += p.sens * p.quantite * (c - ref(p.ticker, p.entree, p.ouvert_le))
    for t in livre.trades:
        if t.ferme_le == j:
            total += t.sens * t.quantite * (t.sortie - ref(t.ticker, t.entree, t.ouvert_le)) \
                - t.commissions
    return round(total, 2), sans_cours


# ── Persistance ─────────────────────────────────────────────────────────────

def charger(chemin: Path = LIVRE) -> Livre:
    if not chemin.exists():
        return Livre()
    d = json.loads(chemin.read_text())
    return Livre(positions=[Position(**p) for p in d.get("positions", [])],
                 trades=[Trade(**t) for t in d.get("trades", [])],
                 pause_le=d.get("pause_le", ""), compteur=int(d.get("compteur", 0)))


def sauver(livre: Livre, chemin: Path = LIVRE) -> None:
    """Écriture atomique : le registre n'est jamais vu à moitié écrit."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    provisoire = chemin.with_suffix(".tmp")
    provisoire.write_text(json.dumps({
        "positions": [asdict(p) for p in livre.positions],
        "trades": [asdict(t) for t in livre.trades],
        "pause_le": livre.pause_le, "compteur": livre.compteur,
    }, indent=2, ensure_ascii=False))
    provisoire.replace(chemin)


# ── Rapprochement ───────────────────────────────────────────────────────────

def actions_du_courtier(positions: Iterable) -> Dict[str, int]:
    """Positions IBKR → {ticker: quantité signée}, actions seulement."""
    from src.prop.calendrier import normaliser
    sortie: Dict[str, int] = {}
    for p in positions:
        c, q = p.contract, int(round(float(p.position)))
        if q and c.secType == "STK":
            t = normaliser(c.symbol.replace(" ", "-"))
            sortie[t] = sortie.get(t, 0) + q
    return sortie


@dataclass(frozen=True)
class Sortie:
    """Une exécution de sortie vue chez le courtier : stop ou objectif touché."""
    id_position: str
    motif: str
    quantite: int
    prix: float
    commission: float
    le: str


def sorties_du_courtier(executions: Iterable) -> Dict[str, Sortie]:
    """Exécutions IBKR (ib.fills()) → sorties par position, d'après la référence d'ordre."""
    cumul: Dict[Tuple[str, str], List] = {}
    for f in executions:
        ref = getattr(f.execution, "orderRef", "") or ""
        morceaux = ref.split(":")
        # Les sorties décidées en séance sont enregistrées au moment même : seuls
        # les ordres qui travaillent seuls chez le courtier sont à rattraper ici.
        if len(morceaux) != 3 or morceaux[0] != "prop" or morceaux[2] not in ("stop", "objectif"):
            continue
        cumul.setdefault((morceaux[1], morceaux[2]), []).append(f)
    sortie = {}
    for (id_, motif), fills in cumul.items():
        q = sum(int(f.execution.shares) for f in fills)
        prix = sum(f.execution.price * f.execution.shares for f in fills) / q
        com = sum(float(getattr(f.commissionReport, "commission", 0) or 0) for f in fills
                  if f.commissionReport)
        le = max(str(f.execution.time) for f in fills)
        if id_ in sortie:                   # stop et objectif partiels (rare) : on additionne
            s = sortie[id_]
            prix = (s.prix * s.quantite + prix * q) / (s.quantite + q)
            q, com = s.quantite + q, s.commission + com
        sortie[id_] = Sortie(id_, motif, q, round(prix, 4), round(com, 2), le)
    return sortie


@dataclass
class Rapprochement:
    ok: bool
    fermes: List[Trade]
    ecarts: List[str]

    def resume(self) -> str:
        return "registre et courtier d'accord" if self.ok else "; ".join(self.ecarts)


def rapprocher(livre: Livre, positions: Iterable, executions: Iterable, jour: date) -> Rapprochement:
    """Ferme ce que les stops et objectifs ont fermé, puis vérifie que tout concorde."""
    courtier = actions_du_courtier(positions)
    sorties = sorties_du_courtier(executions)
    fermes: List[Trade] = []
    for p in list(livre.positions):
        attendu_ici = p.sens * p.quantite
        chez = courtier.get(p.ticker, 0)
        s = sorties.get(p.id)
        if chez == attendu_ici or s is None:
            continue
        # Le courtier a moins que prévu, et montre l'exécution d'un ordre de sortie
        # de cette position : on ferme ce qu'il a exécuté, au prix réel.
        if 0 < s.quantite and p.sens * chez >= 0 and abs(chez) == p.quantite - min(s.quantite, p.quantite):
            fermes.append(livre.fermer(p, s.prix, jour.isoformat(), s.motif, s.commission,
                                       quantite=s.quantite))
    attendu = livre.attendu()
    ecarts = [f"{t} : registre {attendu.get(t, 0):+d}, courtier {courtier.get(t, 0):+d}"
              for t in sorted(set(attendu) | set(courtier)) if attendu.get(t, 0) != courtier.get(t, 0)]
    return Rapprochement(not ecarts, fermes, ecarts)
