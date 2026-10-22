#!/usr/bin/env python
"""
Desk de volatilité — phase 1 : la vente de volatilité tient-elle sur 30 ans ?

    python -m scripts.desk_phase1_indices_cboe

Protocole : docs/desk/phase1_indices_cboe.md, écrit le 2026-10-22 AVANT toute
mesure. Rien n'est réglé ici qui n'y soit écrit.

Données (logs/desk_cache/, téléchargées une fois) :
    PUT, CNDR, VIX   cdn.cboe.com/api/global/us_indices/daily_prices/<X>_History.csv
    ^SP500TR         query1.finance.yahoo.com/v8/finance/chart (JSON brut)
    DTB3             fred.stlouisfed.org (bons du Trésor 3 mois, % annuel)

L'historique quotidien de PUT est clairsemé au début : les mesures longues se
font en mensuel (un point par fin de mois), les mesures « pire séance » sur la
seule partie où les séries sont quotidiennes.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "logs" / "desk_cache"
OUT = ROOT / "logs" / "desk_phase1_results.json"

CBOE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{}_History.csv"
YAHOO_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/%5ESP500TR"
             "?period1=473385600&period2=1792000000&interval=1d")
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3"

CHARTE_PERTE_MAX = -0.15      # docs/charte.md, section 5
CHARTE_REDUCTION = -0.08
C3_SEUIL = 0.02               # protocole, critère C3

PERIODES = {
    "tout": (None, None),
    "avant_2008": (None, "2007-12-31"),
    "depuis_2008": ("2008-01-01", None),
    "depuis_2015": ("2015-01-01", None),
}


def _fetch(url: str, path: Path) -> None:
    if path.exists():
        return
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        path.write_bytes(r.read())


def charger() -> tuple[pd.DataFrame, pd.Series]:
    """Séries quotidiennes (niveaux) et taux sans risque quotidien (% annuel)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    series = {}
    for s in ("PUT", "CNDR", "VIX"):
        p = CACHE / f"{s}_History.csv"
        _fetch(CBOE_URL.format(s), p)
        d = pd.read_csv(p, parse_dates=["DATE"]).set_index("DATE")
        series[s] = d[s if s != "VIX" else "CLOSE"].astype(float)

    p = CACHE / "sp500tr.json"
    _fetch(YAHOO_URL, p)
    res = json.loads(p.read_text())["chart"]["result"][0]
    idx = pd.to_datetime(res["timestamp"], unit="s").normalize()
    series["SPTR"] = pd.Series(res["indicators"]["quote"][0]["close"], index=idx,
                               dtype=float)

    p = CACHE / "DTB3.csv"
    _fetch(FRED_URL, p)
    rf = pd.read_csv(p, parse_dates=["observation_date"], na_values=".")
    rf = rf.set_index("observation_date")["DTB3"].astype(float)

    niveaux = pd.DataFrame(series).sort_index()
    niveaux = niveaux[~niveaux.index.duplicated(keep="last")]
    return niveaux, rf.ffill()


def mensuel(niveaux: pd.DataFrame, rf: pd.Series) -> pd.DataFrame:
    fin = niveaux[["PUT", "CNDR", "SPTR"]].resample("ME").last()
    r = fin.pct_change()
    # taux annuel moyen du mois, ramené au mois
    r["RF"] = (rf.resample("ME").mean() / 100 / 12).reindex(r.index)
    return r.dropna()


def debut_quotidien(s: pd.Series) -> pd.Timestamp:
    """Première date après laquelle la série n'a plus de trou de plus de 5 jours."""
    s = s.dropna()
    trous = s.index.to_series().diff().dt.days
    gros = trous[trous > 5]
    return gros.index.max() if len(gros) else s.index.min()


def baisse_max(niveau: pd.Series) -> tuple[float, str, str, int | None]:
    """Pire baisse depuis un plus haut, son creux, et les mois/jours pour revenir."""
    pic = niveau.cummax()
    dd = niveau / pic - 1
    creux = dd.idxmin()
    debut = niveau[:creux].idxmax()
    apres = niveau[creux:]
    retour = apres[apres >= pic[creux]]
    duree = (retour.index[0] - debut).days if len(retour) else None
    return float(dd.min()), str(debut.date()), str(creux.date()), duree


def mesures(r: pd.Series, rf: pd.Series, marche: pd.Series) -> dict:
    exc = r - rf
    niveau = (1 + r).cumprod()
    annees = len(r) / 12
    dd, debut, creux, duree = baisse_max(niveau)
    cov = np.cov(r, marche)
    return {
        "debut": str(r.index[0].date()), "fin": str(r.index[-1].date()),
        "rendement_annuel": float(niveau.iloc[-1] ** (1 / annees) - 1),
        "exces_annuel": float(exc.mean() * 12),
        "volatilite": float(r.std() * np.sqrt(12)),
        "sharpe": float(exc.mean() / exc.std() * np.sqrt(12)),
        "baisse_max": dd, "baisse_debut": debut, "baisse_creux": creux,
        "jours_pour_revenir": duree,
        "pire_mois": float(r.min()), "pire_mois_date": str(r.idxmin().date()),
        "asymetrie": float(r.skew()),
        "beta": float(cov[0, 1] / cov[1, 1]),
    }


def taille_charte(r: pd.Series, rf: pd.Series) -> dict:
    """Plus grand w tel que w × indice + (1 − w) × cash garde sa pire baisse ≥ −15 %."""
    meilleur = None
    for w in np.round(np.arange(0.01, 1.001, 0.01), 2):
        mix = w * r + (1 - w) * rf
        dd = baisse_max((1 + mix).cumprod())[0]
        if dd >= CHARTE_PERTE_MAX:
            meilleur = (w, mix, dd)
    if meilleur is None:
        return {"w": 0.0}
    w, mix, dd = meilleur
    return {"w": float(w), "baisse_max": dd,
            "exces_annuel": float((mix - rf).mean() * 12),
            "sharpe": float((mix - rf).mean() / (mix - rf).std() * np.sqrt(12))}


def quotidien(niveaux: pd.DataFrame, rf: pd.Series) -> dict:
    """Pire séance et pire baisse en quotidien, sur la partie commune quotidienne."""
    debut = max(debut_quotidien(niveaux[c]) for c in ("PUT", "CNDR", "SPTR"))
    q = niveaux.loc[debut:, ["PUT", "CNDR", "SPTR"]].dropna()
    r = q.pct_change().dropna()
    out = {"debut": str(q.index[0].date())}
    for c in r:
        dd, d0, creux, duree = baisse_max(q[c])
        out[c] = {"pire_seance": float(r[c].min()),
                  "pire_seance_date": str(r[c].idxmin().date()),
                  "baisse_max": dd, "baisse_debut": d0, "baisse_creux": creux,
                  "jours_pour_revenir": duree}
    return out


def avril_2025(niveaux: pd.DataFrame, rf: pd.Series, tailles: dict) -> dict:
    """Jour par jour du 31/03 au 30/05/2025, à pleine taille et à la taille charte."""
    fen = niveaux.loc["2025-03-31":"2025-05-30"].dropna()
    rfj = (rf.reindex(fen.index).ffill() / 100 / 252).iloc[1:]
    out = {"vix_max": float(fen["VIX"].max()),
           "vix_max_date": str(fen["VIX"].idxmax().date()),
           "vix_debut": float(fen["VIX"].iloc[0])}
    for c in ("PUT", "CNDR", "SPTR"):
        r = fen[c].pct_change().dropna()
        for nom, w in (("pleine_taille", 1.0), ("taille_charte", tailles.get(c, 1.0))):
            mix = w * r + (1 - w) * rfj
            niv = (1 + mix).cumprod()
            dd = niv / niv.cummax() - 1
            alerte = dd[dd <= CHARTE_REDUCTION]
            arret = dd[dd <= CHARTE_PERTE_MAX]
            out[f"{c}_{nom}"] = {
                "w": w,
                "pire_baisse": float(dd.min()),
                "pire_baisse_date": str(dd.idxmin().date()),
                "pire_seance": float(mix.min()),
                "pire_seance_date": str(mix.idxmin().date()),
                "resultat_30_mai": float(niv.iloc[-1] - 1),
                "reduction_-8%": str(alerte.index[0].date()) if len(alerte) else None,
                "arret_-15%": str(arret.index[0].date()) if len(arret) else None,
            }
    return out


def _ols_newey_west(y: np.ndarray, x: np.ndarray, lags: int = 3):
    X = np.column_stack([np.ones(len(x)), x])
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    e = y - X @ b
    S = (X * e[:, None]).T @ (X * e[:, None])
    for lag in range(1, lags + 1):
        w = 1 - lag / (lags + 1)
        G = (X[lag:] * e[lag:, None]).T @ (X[:-lag] * e[:-lag, None])
        S += w * (G + G.T)
    inv = np.linalg.inv(X.T @ X)
    return b, np.sqrt(np.diag(inv @ S @ inv))


def exploratoire(niveaux: pd.DataFrame, m: pd.DataFrame) -> dict:
    """HORS PROTOCOLE — ajouté après la mesure, pour comprendre l'échec de C1.

    1. Alpha : ce que l'indice rapporte au-delà de sa part de marché (bêta),
       erreurs de Newey-West à 3 mois.
    2. Prime de variance brute : VIX du jour contre la volatilité réellement
       constatée sur les 21 séances suivantes.
    """
    out: dict = {"alpha": {}, "prime_variance": {}}
    for c in ("PUT", "CNDR"):
        b, se = _ols_newey_west((m[c] - m["RF"]).values, (m["SPTR"] - m["RF"]).values)
        out["alpha"][c] = {"alpha_annuel": float(b[0] * 12),
                           "ic95": [float((b[0] - 1.96 * se[0]) * 12),
                                    float((b[0] + 1.96 * se[0]) * 12)],
                           "beta": float(b[1])}
    s = niveaux["SPTR"].dropna()
    realisee = np.log(s).diff().rolling(21).std().shift(-21) * np.sqrt(252) * 100
    d = pd.DataFrame({"vix": niveaux["VIX"].reindex(s.index), "realisee": realisee}).dropna()
    for a, b in (("1990", "2026"), ("1990", "2006"), ("2007", "2026"), ("2015", "2026")):
        x = d.loc[a:b]
        out["prime_variance"][f"{a}-{b}"] = {
            "vix_moyen": float(x["vix"].mean()),
            "realisee_moyenne": float(x["realisee"].mean()),
            "part_jours_vix_au_dessus": float((x["vix"] > x["realisee"]).mean())}
    return out


def main() -> None:
    niveaux, rf = charger()
    m = mensuel(niveaux, rf)
    print(f"Historique mensuel commun : {m.index[0].date()} → {m.index[-1].date()} "
          f"({len(m)} mois)\n")

    res: dict = {"periodes": {}, "taille_charte": {}}
    for nom, (a, b) in PERIODES.items():
        p = m.loc[a:b]
        res["periodes"][nom] = {c: mesures(p[c], p["RF"], p["SPTR"])
                                for c in ("PUT", "CNDR", "SPTR")}
        t = pd.DataFrame(res["periodes"][nom]).T
        print(f"── {nom} ({p.index[0].date()} → {p.index[-1].date()})")
        print(t[["rendement_annuel", "exces_annuel", "volatilite", "sharpe",
                 "baisse_max", "baisse_creux", "jours_pour_revenir", "pire_mois",
                 "asymetrie", "beta"]].to_string(float_format=lambda x: f"{x:.3f}"))
        print()

    for c in ("PUT", "CNDR", "SPTR"):
        res["taille_charte"][c] = taille_charte(m[c], m["RF"])
    print("── Taille compatible avec la charte (pire baisse ≥ −15 %, mensuel)")
    print(pd.DataFrame(res["taille_charte"]).T.to_string(float_format=lambda x: f"{x:.3f}"))
    print()

    res["quotidien"] = quotidien(niveaux, rf)
    print(f"── Quotidien depuis {res['quotidien']['debut']}")
    print(pd.DataFrame({k: v for k, v in res["quotidien"].items() if k != "debut"}).T
          .to_string(float_format=lambda x: f"{x:.3f}"))
    print()

    tailles = {c: res["taille_charte"][c]["w"] for c in ("PUT", "CNDR", "SPTR")}
    res["avril_2025"] = avril_2025(niveaux, rf, tailles)
    a = res["avril_2025"]
    print(f"── Avril 2025 (VIX {a['vix_debut']:.1f} → max {a['vix_max']:.1f} "
          f"le {a['vix_max_date']})")
    print(pd.DataFrame({k: v for k, v in a.items() if isinstance(v, dict)}).T
          .to_string(float_format=lambda x: f"{x:.3f}"))

    t, r = res["periodes"]["tout"], res["periodes"]["depuis_2008"]
    rec = res["periodes"]["depuis_2015"]
    res["criteres"] = {
        c: {"C1": t[c]["sharpe"] >= t["SPTR"]["sharpe"]
                  and r[c]["sharpe"] >= r["SPTR"]["sharpe"],
            "C2": rec[c]["exces_annuel"] > 0,
            "C3": res["taille_charte"][c].get("exces_annuel", 0) >= C3_SEUIL}
        for c in ("PUT", "CNDR")}
    print("\n── Critères", json.dumps(res["criteres"]))

    res["exploratoire_hors_protocole"] = exploratoire(niveaux, m)
    print("\n── HORS PROTOCOLE")
    print(json.dumps(res["exploratoire_hors_protocole"], indent=1))

    OUT.write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(f"\nÉcrit : {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
