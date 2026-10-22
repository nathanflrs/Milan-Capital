#!/usr/bin/env python
"""
Thèse n°1 — test préalable de la section 8.

    python -m scripts.test_these_01_prealable

Protocole : docs/theses/these_01_test_prealable.md, écrit le 2026-10-11 AVANT
toute mesure. Rien n'est réglé ici qui n'y soit écrit.

La question
-----------
Le portefeuille AMH d'Eisfeldt, Schubert et Zhang (acheteur des entreprises
les plus exposées à l'IA générative, vendeur des moins exposées) a gagné ~5 %
dans les deux semaines suivant ChatGPT. L'écart a-t-il continué de se creuser
de 2023 à 2026 ? S'il s'est refermé, la thèse perd sa raison d'être.

Chaîne de données
-----------------
    score (GVKEY) → nom (même site) → ticker + CIK (SEC, nom exact)
    CIK → actions en circulation point-in-time (SEC XBRL frames)
    CIK → code SIC (SEC submissions)
    ticker → prix (yfinance) → capitalisation au jour de formation

Le rapprochement par le nom est exact ou n'est pas : une entreprise mal
rapprochée tomberait dans le mauvais quintile sans que rien ne le signale.
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CACHE = ROOT / "logs" / "these01_cache"
UA = "MQC_ARENA research@milancapital.io"
AMH_SITE = "https://artificialminushuman.com/data/"

# Fixé par le protocole, section 3 à 5
MIN_PRICE = 5.0
MIN_MCAP = 100e6
EVENT_FORMATION = "2022-11-29"
EVENT_START, EVENT_END = "2022-11-30", "2022-12-14"
TEST_START = "2023-01-01"
MAKER_SIC = [(3570, 3579), (3670, 3679), (7370, 7379)]
MIN_SECTOR_FIRMS = 10
NW_LAGS = 5
EXCHANGES = {"NYSE", "Nasdaq", "CBOE"}


# ─── Téléchargements, avec cache ────────────────────────────────────────────

def _get(url: str, path: Path, sec: bool = False) -> bytes:
    if path.exists():
        return path.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if sec:
        time.sleep(0.12)  # 10 requêtes/s maximum chez la SEC
    path.write_bytes(data)
    return data


def load_scores() -> pd.DataFrame:
    s = pd.read_csv(io.BytesIO(_get(AMH_SITE + "genaiexp_estz_firmscores.csv",
                                    CACHE / "firmscores.csv")))
    n = pd.read_csv(io.BytesIO(_get(AMH_SITE + "genaiexp_data_assets.csv",
                                    CACHE / "data_assets.csv")))
    df = s.merge(n[["gvkey", "name"]], on="gvkey", how="left")
    return df.rename(columns={"firmgenaiexp_estz_total": "score"})[["gvkey", "name", "score"]]


def load_sec_tickers() -> pd.DataFrame:
    raw = json.loads(_get("https://www.sec.gov/files/company_tickers_exchange.json",
                          CACHE / "company_tickers_exchange.json", sec=True))
    df = pd.DataFrame(raw["data"], columns=raw["fields"])
    return df[df["exchange"].isin(EXCHANGES)]


_LEGAL = {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
          "limited", "plc", "llc", "lp", "the", "sa", "nv", "ag", "se", "de", "new"}


def norm_name(name: str) -> str:
    s = str(name).lower().replace("&", " and ")
    s = re.sub(r"/[a-z]{2,3}/?", " ", s)            # « CORP /DE/ » des noms SEC
    toks = [t for t in re.split(r"[^a-z0-9]+", s) if t and t not in _LEGAL]
    return "".join(toks)


def match(scores: pd.DataFrame, sec: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Nom exact, normalisé. Ambigu (plusieurs CIK) → écarté. Une seule classe par CIK."""
    sec = sec.copy()
    sec["key"] = sec["name"].map(norm_name)
    # une société, un ticker : la première ligne SEC (classe principale)
    sec = sec.drop_duplicates("cik")
    ambiguous = set(sec.loc[sec["key"].duplicated(keep=False), "key"])
    sec = sec[~sec["key"].isin(ambiguous)]

    sc = scores.dropna(subset=["name", "score"]).copy()
    sc["key"] = sc["name"].map(norm_name)
    dup_sc = set(sc.loc[sc["key"].duplicated(keep=False), "key"])
    sc = sc[~sc["key"].isin(dup_sc)]

    m = sc.merge(sec[["key", "cik", "ticker", "exchange"]], on="key", how="inner")
    stats = {
        "scores_total": int(scores["score"].notna().sum()),
        "scores_avec_nom": int(scores.dropna(subset=["name", "score"]).shape[0]),
        "rapproches": int(len(m)),
    }
    return m.drop(columns="key"), stats


def load_shares() -> pd.DataFrame:
    """Actions en circulation déclarées en couverture des 10-Q/10-K, par date."""
    rows = []
    for y in range(2022, 2027):
        for q in range(1, 5):
            tag = f"CY{y}Q{q}I"
            url = ("https://data.sec.gov/api/xbrl/frames/dei/"
                   f"EntityCommonStockSharesOutstanding/shares/{tag}.json")
            try:
                d = json.loads(_get(url, CACHE / "shares" / f"{tag}.json", sec=True))
            except Exception:
                continue  # trimestre pas encore publié
            rows += [(r["cik"], r["end"], r["val"]) for r in d.get("data", [])]
    df = pd.DataFrame(rows, columns=["cik", "end", "shares"])
    df["end"] = pd.to_datetime(df["end"])
    return df.sort_values("end")


def load_sic(ciks) -> pd.Series:
    out = {}
    for i, cik in enumerate(ciks):
        url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
        try:
            d = json.loads(_get(url, CACHE / "sic" / f"{int(cik)}.json", sec=True))
            out[cik] = int(d.get("sic") or 0) or np.nan
        except Exception:
            out[cik] = np.nan
        if i % 500 == 0:
            print(f"  SIC {i}/{len(ciks)}", flush=True)
    return pd.Series(out, name="sic")


def load_prices(tickers) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(rendements ajustés, cours non ajustés, ) — cours brut = Close × divisions ultérieures."""
    p = CACHE / "prices.pkl"
    if p.exists():
        return pd.read_pickle(p)
    import yfinance as yf
    adj, close, splits = {}, {}, {}
    tickers = list(tickers)
    for i in range(0, len(tickers), 100):
        lot = tickers[i:i + 100]
        raw = yf.download(lot, start="2022-10-01", end="2026-10-11", interval="1d",
                          auto_adjust=False, actions=True, progress=False,
                          group_by="ticker", threads=True)
        for t in lot:
            if t not in raw.columns.get_level_values(0):
                continue
            d = raw[t]
            if d["Adj Close"].notna().sum() < 20:
                continue
            adj[t], close[t], splits[t] = d["Adj Close"], d["Close"], d["Stock Splits"]
        print(f"  prix {min(i + 100, len(tickers))}/{len(tickers)} — {len(adj)} séries", flush=True)
        time.sleep(1.0)
    out = (pd.DataFrame(adj), pd.DataFrame(close), pd.DataFrame(splits).fillna(0.0))
    pd.to_pickle(out, p)
    return out


# ─── Portefeuilles ──────────────────────────────────────────────────────────

def raw_price(close: pd.DataFrame, splits: pd.DataFrame) -> pd.DataFrame:
    """yfinance rétro-ajuste les divisions : on les ré-applique pour retrouver le cours du jour."""
    f = splits.replace(0.0, 1.0).fillna(1.0)
    # produit des divisions STRICTEMENT postérieures à chaque date
    later = f.iloc[::-1].cumprod().iloc[::-1].shift(-1).fillna(1.0)
    return close * later


def formation_table(univ: pd.DataFrame, shares: pd.DataFrame, px_raw: pd.DataFrame,
                    date: pd.Timestamp) -> pd.DataFrame:
    sh = shares[shares["end"] <= date].groupby("cik").last()["shares"]
    d = univ.copy()
    d["shares"] = d["cik"].map(sh)
    d["px"] = d["ticker"].map(px_raw.loc[:date].ffill().iloc[-1])
    d["mcap"] = d["shares"] * d["px"]
    return d.dropna(subset=["mcap"]).query("px >= @MIN_PRICE and mcap >= @MIN_MCAP")


def leg_returns(weights: pd.Series, rets: pd.DataFrame) -> pd.Series:
    """Buy-and-hold : chaque ligne dérive avec son cours ; un trou de cotation = cash."""
    r = rets[weights.index].fillna(0.0)
    growth = (1 + r).cumprod()
    value = (growth * (weights / weights.sum())).sum(axis=1)
    return value.pct_change().fillna(value.iloc[0] - 1)


def amh(form: pd.DataFrame, rets: pd.DataFrame, by_sector: bool = False) -> pd.Series:
    if by_sector:
        form = form.dropna(subset=["sic2"])
        form = form.groupby("sic2").filter(lambda g: len(g) >= MIN_SECTOR_FIRMS)
        q = form.groupby("sic2")["score"].transform(
            lambda s: pd.qcut(s.rank(method="first"), 5, labels=False))
        # même poids de capitalisation, mais Q5/Q1 définis dans chaque secteur
    else:
        q = pd.qcut(form["score"].rank(method="first"), 5, labels=False)
    hi = form[q == 4].set_index("ticker")["mcap"]
    lo = form[q == 0].set_index("ticker")["mcap"]
    return leg_returns(hi, rets) - leg_returns(lo, rets)


def run_periods(univ, shares, px_raw, rets, starts, end, **kw) -> pd.Series:
    out = []
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else end
        idx = rets.index[(rets.index >= s) & (rets.index < e)]
        if len(idx) == 0:
            continue
        form_date = rets.index[rets.index < idx[0]][-1]  # veille de la première séance
        form = formation_table(univ, shares, px_raw, form_date)
        out.append(amh(form, rets.loc[idx], **kw))
    return pd.concat(out)


def alpha(r: pd.Series, factors: pd.DataFrame, cols) -> dict:
    d = pd.concat([r.rename("amh"), factors[cols]], axis=1, join="inner").dropna()
    X = sm.add_constant(d[cols])
    fit = sm.OLS(d["amh"], X).fit(cov_type="HAC", cov_kwds={"maxlags": NW_LAGS})
    return {"alpha_an": fit.params["const"] * 252, "t": fit.tvalues["const"],
            "n": len(d), "fin": d.index[-1].date(),
            "betas": {c: round(fit.params[c], 2) for c in cols}}


def describe(name: str, r: pd.Series, factors: pd.DataFrame) -> None:
    cum = (1 + r).prod() - 1
    t = r.mean() / r.std() * np.sqrt(len(r))
    print(f"\n── {name}")
    print(f"  cumulé {r.index[0].date()} → {r.index[-1].date()} : {cum:+.1%}   "
          f"(t brut {t:+.2f}, {len(r)} séances)")
    for y, g in r.groupby(r.index.year):
        print(f"    {y} : {(1 + g).prod() - 1:+.1%}")
    for label, cols in [("Carhart", ["Mkt-RF", "SMB", "HML", "MOM"]),
                        ("FF5+MOM", ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM"])]:
        if all(c in factors.columns for c in cols):
            a = alpha(r, factors, cols)
            print(f"  alpha {label} : {a['alpha_an']:+.1%}/an (t {a['t']:+.2f}, "
                  f"jusqu'au {a['fin']}) — bêtas {a['betas']}")


def load_factors() -> pd.DataFrame:
    from pandas_datareader.famafrench import FamaFrenchReader
    p = CACHE / "factors.pkl"
    if p.exists():
        return pd.read_pickle(p)
    ff5 = FamaFrenchReader("F-F_Research_Data_5_Factors_2x3_daily", start="2022-01-01").read()[0]
    mom = FamaFrenchReader("F-F_Momentum_Factor_daily", start="2022-01-01").read()[0]
    mom.columns = ["MOM"]
    f = ff5.join(mom, how="inner") / 100.0
    f.index = f.index.to_timestamp() if hasattr(f.index, "to_timestamp") else pd.to_datetime(f.index)
    pd.to_pickle(f, p)
    return f


# ─── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    scores = load_scores()
    univ, st = match(scores, load_sec_tickers())
    print(f"Scores publiés : {st['scores_total']} | avec nom : {st['scores_avec_nom']} | "
          f"rapprochés à un ticker coté aujourd'hui : {st['rapproches']} "
          f"({st['rapproches'] / st['scores_avec_nom']:.0%})")

    shares = load_shares()
    sic = load_sic(univ["cik"].unique())
    univ["sic"] = univ["cik"].map(sic)
    univ["sic2"] = univ["sic"] // 100
    univ["maker"] = univ["sic"].apply(
        lambda s: any(a <= s <= b for a, b in MAKER_SIC) if pd.notna(s) else False)

    adj, close, splits = load_prices(univ["ticker"])
    rets = adj.pct_change(fill_method=None)
    px_raw = raw_price(close, splits)
    univ = univ[univ["ticker"].isin(adj.columns)]
    print(f"Avec prix yfinance : {len(univ)} | dont fabricants (SIC) : {int(univ['maker'].sum())}")

    factors = load_factors()

    # Étape 0 — réplication
    form = formation_table(univ, shares, px_raw, pd.Timestamp(EVENT_FORMATION))
    ev = amh(form, rets.loc[EVENT_START:EVENT_END])
    q = pd.qcut(form["score"].rank(method="first"), 5, labels=False)
    print(f"\nÉtape 0 — réplication, formation {EVENT_FORMATION} : {len(form)} sociétés "
          f"(Q5 {int((q == 4).sum())}, Q1 {int((q == 0).sum())})")
    print(f"  AMH {EVENT_START} → {EVENT_END} : {(1 + ev).prod() - 1:+.2%} "
          f"(article : ~ +5 % anormal)")
    top = form[q == 4].nlargest(8, "mcap")["ticker"].tolist()
    bot = form[q == 0].nlargest(8, "mcap")["ticker"].tolist()
    print(f"  plus grosses lignes Q5 : {top}\n  plus grosses lignes Q1 : {bot}")
    if (1 + ev).prod() - 1 <= 0:
        print("\n⛔ Réplication négative : chaîne suspecte, on s'arrête (protocole §4).")
        return

    end = rets.index[-1] + pd.Timedelta(days=1)
    starts = [pd.Timestamp(f"{y}-01-01") for y in range(2023, 2027)]

    describe("1-2. AMH, version de l'article (tous secteurs)",
             run_periods(univ, shares, px_raw, rets, starts, end), factors)
    describe("3. AMH « utilisateurs » (fabricants exclus)",
             run_periods(univ[~univ["maker"]], shares, px_raw, rets, starts, end), factors)
    describe("4. AMH intra-secteur (SIC 2 chiffres)",
             run_periods(univ, shares, px_raw, rets, starts, end, by_sector=True), factors)


if __name__ == "__main__":
    main()
