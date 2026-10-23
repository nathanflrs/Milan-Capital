# src/prop/indicateurs.py
"""
Ce que le prop trader voit des 500 titres : des indicateurs calculés par le
code, jamais par Claude.

Les chiffres partent des clôtures quotidiennes collectées chaque soir
(src/market/collect.py, logs/market/). À 9 h 45, la dernière barre est donc
celle d'hier : le cours du jour vient du courtier, par un autre outil.

Logique pure, sans réseau : testée sur des séries construites à la main.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

COLONNES = ["secteur", "cours", "r1_pct", "r5_pct", "r20_pct", "r63_pct", "adx",
            "ecart_mm20_pct", "ecart_mm50_pct", "ecart_mm200_pct", "rsi", "vol20_pct",
            "ecart_plus_haut_52s_pct", "volume_relatif", "volume_dollars_20j_m"]

CRITERES = {
    "r1_pct": "rendement de la dernière séance",
    "r5_pct": "rendement sur 5 séances",
    "r20_pct": "rendement sur 20 séances",
    "r63_pct": "momentum sur 3 mois",
    "adx": "force de la tendance (ADX 14)",
    "ecart_mm50_pct": "écart à la moyenne mobile 50 jours",
    "ecart_mm200_pct": "écart à la moyenne mobile 200 jours",
    "rsi": "RSI 14",
    "vol20_pct": "volatilité réalisée 20 jours, annualisée",
    "ecart_plus_haut_52s_pct": "distance au plus haut de 52 semaines",
    "volume_relatif": "volume de la dernière séance ÷ moyenne 20 jours",
}


def _wilder(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(alpha=1 / n, adjust=False).mean()


def adx(haut: pd.Series, bas: pd.Series, cloture: pd.Series, n: int = 14) -> pd.Series:
    """ADX de Wilder : force de la tendance, quel que soit son sens (0-100)."""
    prec = cloture.shift()
    tr = pd.concat([haut - bas, (haut - prec).abs(), (bas - prec).abs()], axis=1).max(axis=1)
    monte, baisse = haut.diff(), -bas.diff()
    dm_plus = monte.where((monte > baisse) & (monte > 0), 0.0)
    dm_moins = baisse.where((baisse > monte) & (baisse > 0), 0.0)
    atr = _wilder(tr, n)
    di_plus = 100 * _wilder(dm_plus, n) / atr
    di_moins = 100 * _wilder(dm_moins, n) / atr
    dx = 100 * (di_plus - di_moins).abs() / (di_plus + di_moins).replace(0, np.nan)
    return _wilder(dx.fillna(0), n)


def rsi(cloture: pd.Series, n: int = 14) -> pd.Series:
    d = cloture.diff()
    hausse, baisse = _wilder(d.clip(lower=0), n), _wilder(-d.clip(upper=0), n)
    rs = hausse / baisse.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100.0)


def _pct(a: float, b: float) -> Optional[float]:
    return None if not b or pd.isna(a) or pd.isna(b) else round((a / b - 1) * 100, 2)


def ligne(df: pd.DataFrame) -> Optional[dict]:
    """Les indicateurs d'un titre, sur ses barres quotidiennes (Open/High/Low/Close/Volume)."""
    df = df.dropna(subset=["Close"])
    if len(df) < 30:
        return None
    c, h, b, v = df["Close"], df["High"], df["Low"], df["Volume"]
    dernier = float(c.iloc[-1])
    rendements = np.log(c / c.shift()).dropna()
    mm = lambda n: float(c.iloc[-n:].mean()) if len(c) >= n else float("nan")
    vol_moy = float(v.iloc[-21:-1].mean()) if len(v) > 21 else float("nan")
    return {
        "cours": round(dernier, 2),
        "r1_pct": _pct(dernier, c.iloc[-2]),
        "r5_pct": _pct(dernier, c.iloc[-6]) if len(c) > 5 else None,
        "r20_pct": _pct(dernier, c.iloc[-21]) if len(c) > 20 else None,
        "r63_pct": _pct(dernier, c.iloc[-64]) if len(c) > 63 else None,
        "adx": round(float(adx(h, b, c).iloc[-1]), 1),
        "ecart_mm20_pct": _pct(dernier, mm(20)),
        "ecart_mm50_pct": _pct(dernier, mm(50)),
        "ecart_mm200_pct": _pct(dernier, mm(200)),
        "rsi": round(float(rsi(c).iloc[-1]), 1),
        "vol20_pct": round(float(rendements.iloc[-20:].std() * math.sqrt(252) * 100), 1),
        "ecart_plus_haut_52s_pct": _pct(dernier, h.iloc[-252:].max()),
        "volume_relatif": round(float(v.iloc[-1]) / vol_moy, 2) if vol_moy else None,
        "volume_dollars_20j_m": round(float((c * v).iloc[-20:].mean()) / 1e6, 1),
    }


def ecran(ohlcv: Dict[str, pd.DataFrame], membres: pd.DataFrame) -> pd.DataFrame:
    """Le tableau des 500 titres : une ligne par ticker, les colonnes de COLONNES."""
    lignes = {}
    for t, df in ohlcv.items():
        l = ligne(df)
        if l:
            secteur = membres.at[t, "sector"] if t in membres.index else ""
            lignes[t] = {"secteur": secteur, **l}
    return pd.DataFrame.from_dict(lignes, orient="index").reindex(columns=COLONNES)


def classer(table: pd.DataFrame, critere: str, ordre: str = "decroissant", n: int = 20,
            secteur: str = "") -> List[dict]:
    """Les n titres en tête (ou en queue) d'un critère, éventuellement dans un secteur."""
    if critere not in CRITERES:
        raise ValueError(f"critère inconnu : {critere} (possibles : {', '.join(CRITERES)})")
    t = table[table["secteur"] == secteur] if secteur else table
    t = t.dropna(subset=[critere]).sort_values(critere, ascending=(ordre == "croissant"))
    n = max(1, min(int(n), 40))
    return [{"ticker": k, **{c: (None if pd.isna(v) else v) for c, v in r.items()}}
            for k, r in t.head(n).iterrows()]


def secteurs(table: pd.DataFrame) -> List[dict]:
    """Performance médiane par secteur, et part des titres au-dessus de leur moyenne 200 jours."""
    sortie = []
    for s, g in table.groupby("secteur"):
        if not s:
            continue
        sortie.append({"secteur": s, "titres": len(g),
                       **{f"mediane_{c}": round(float(g[c].median()), 2)
                          for c in ("r1_pct", "r5_pct", "r20_pct", "r63_pct")},
                       "part_au_dessus_mm200_pct": round(float((g["ecart_mm200_pct"] > 0).mean()) * 100, 0)})
    return sorted(sortie, key=lambda x: x["mediane_r20_pct"], reverse=True)


def largeur(table: pd.DataFrame) -> dict:
    """Santé du marché dans son ensemble : combien de titres montent, sont en tendance…"""
    t = table.dropna(subset=["r1_pct"])
    return {"titres": len(t),
            "en_hausse_hier_pct": round(float((t["r1_pct"] > 0).mean()) * 100, 0),
            "au_dessus_mm50_pct": round(float((t["ecart_mm50_pct"] > 0).mean()) * 100, 0),
            "au_dessus_mm200_pct": round(float((t["ecart_mm200_pct"] > 0).mean()) * 100, 0),
            "a_moins_de_2pct_du_plus_haut_52s": int((t["ecart_plus_haut_52s_pct"] > -2).sum()),
            "mediane_r1_pct": round(float(t["r1_pct"].median()), 2),
            "mediane_r20_pct": round(float(t["r20_pct"].median()), 2)}
