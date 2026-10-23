# src/acheteur/seance.py
"""
Les séances de l'acheteur de volatilité (docs/desk/pods.md, section 2).

    python -m src.acheteur entree     # 15 h 30 New York : acheter avant les résultats
    python -m src.acheteur sortie     # 10 h 30 : revendre après la réaction du marché

Aucun appel à Claude : la règle est entièrement écrite dans strategie.py.

Le mode vient de mode_autorise() : réel seulement avec ACHETEUR_ENABLED et
EXECUTION_ENABLED ; sinon les ordres sont soumis à IBKR en whatIf et le
registre ne bouge pas.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from src.acheteur import livre as lv
from src.acheteur import strategie as st
from src.options import execution as ex
from src.options.execution import MODE_REEL, MODE_SIMULATION

DOSSIER = Path("logs/acheteur")
JOURNAL = DOSSIER / "ordres.csv"
CLIENT_ID = int(os.getenv("ACHETEUR_CLIENT_ID", "24"))
ROLE = "Acheteur de volatilité"


def mode_autorise(env=None) -> str:
    env = os.environ if env is None else env
    ouvert = lambda k: str(env.get(k, "false")).strip().lower() == "true"
    return MODE_REEL if ouvert("ACHETEUR_ENABLED") and ouvert("EXECUTION_ENABLED") else MODE_SIMULATION


def publications_passees(ticker: str, jour: date, dossier: Path = DOSSIER / "historique",
                         lire: Optional[Callable[[str], List[datetime]]] = None) -> List[datetime]:
    """Dates et heures (New York) des derniers résultats publiés, gardées une journée en cache."""
    f = dossier / f"{ticker}_{jour.isoformat()}.json"
    if f.exists():
        return [datetime.fromisoformat(x) for x in json.loads(f.read_text())]

    def yahoo(t: str) -> List[datetime]:
        import yfinance as yf
        d = yf.Ticker(t).get_earnings_dates(limit=16)
        sortie = []
        for ts, ligne in d.iterrows():
            if str(ligne.get("Reported EPS", "nan")) == "nan":
                continue                              # à venir : pas encore de réaction
            sortie.append(ts.tz_convert("America/New_York").tz_localize(None).to_pydatetime())
        return sortie

    pubs = (lire or yahoo)(ticker)
    dossier.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps([p.isoformat() for p in pubs]))
    return pubs


def _publier(texte: str, moment: str, mode: str, gravite: str = "info") -> None:
    print(f"[{ROLE}] {texte}")
    if gravite == "critical":
        from src.equipe.socle import notifier_telephone
        notifier_telephone(f"Acheteur — {ROLE}", texte[:180], url="/", tag="acheteur-incident")
    try:
        from src.events.bus import Event, get_bus
        get_bus().emit(Event(type="desk", severity=gravite, title=ROLE, body=texte,
                             meta={"role": ROLE, "moment": moment, "mode": mode, "pod": "acheteur"}))
    except Exception as e:
        print(f"(bus d'événements indisponible : {e})", file=sys.stderr)


def _noter(jour: date, moment: str, mode: str, vl: float, examines: int, achetes: int, vendus: int,
           engage: float, chemin: Path = DOSSIER / "seances.csv") -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    nouveau = not chemin.exists()
    with chemin.open("a", newline="") as f:
        w = csv.writer(f)
        if nouveau:
            w.writerow(["jour", "moment", "mode", "valeur_liquidative", "examines", "achetes",
                        "vendus", "prime_engagee"])
        w.writerow([jour.isoformat(), moment, mode, round(vl, 2), examines, achetes, vendus,
                    round(engage, 2)])


def _cotations(ib, contrats: List) -> List[Tuple[Optional[float], Optional[float]]]:
    lignes = [ib.reqMktData(c, "", False, False) for c in contrats]
    ib.sleep(5)
    sortie = []
    for c, l in zip(contrats, lignes):
        ib.cancelMktData(c)
        bid, ask = ex._nombre(l.bid), ex._nombre(l.ask)
        sortie.append((bid if bid and bid > 0 else None, ask if ask and ask > 0 else None))
    return sortie


def _straddle(ib, symbole: str, echeance: str, strike: float):
    """(call, put, milieu, achat au prix affiché, vente au prix affiché) ou None sans cotation."""
    from ib_insync import Option
    c = Option(symbole, echeance, strike, "C", "SMART", tradingClass=symbole)
    p = Option(symbole, echeance, strike, "P", "SMART", tradingClass=symbole)
    ib.qualifyContracts(c, p)
    if not (c.conId and p.conId):
        return None
    (cb, ca), (pb, pa) = _cotations(ib, [c, p])
    if None in (cb, ca, pb, pa):
        return None
    return c, p, (cb + ca + pb + pa) / 2, ca + pa, cb + pb


def seance(moment: str, jour: Optional[date] = None, livre_chemin: Path = lv.LIVRE) -> int:
    from ib_insync import IB, Stock

    from src.equipe.socle import NEW_YORK, notifier_telephone
    from src.market.view import load_market_view
    from src.prop import calendrier as cal
    from src.prop import indicateurs as ind
    from src.prop import ordres as od
    from src.prop import regles as rg
    from src.prop.seance import plus_haut_du_fonds

    logging.getLogger("ib_insync").setLevel(logging.CRITICAL)
    jour = jour or datetime.now(NEW_YORK).date()
    mode = mode_autorise()
    dire = lambda texte, g="info": _publier(texte, moment, mode, g)

    ib = IB()
    ib.RequestTimeout = 120
    ib.connect(os.getenv("IBKR_HOST", "127.0.0.1"), int(os.getenv("IBKR_PORT", "4002")),
               clientId=CLIENT_ID)
    try:
        ib.reqMarketDataType(int(os.getenv("OPTIONS_MARKET_DATA_TYPE", "3")))
        vl = next(float(v.value) for v in ib.accountSummary() if v.tag == "NetLiquidation")
        livre = lv.charger(livre_chemin)
        ecarts = lv.rapprocher(livre, ib.positions())
        if ecarts:
            dire(f"Écart avec le courtier : {'; '.join(ecarts)}. Le pod ne décide rien tant qu'un "
                 f"humain n'a pas compris.", "critical")
            return 1
        achetes = vendus = examines = 0
        lignes: List[str] = []

        if moment == "sortie":
            for s in [x for x in livre.straddles if x.reaction_le <= jour.isoformat()]:
                symbole = od.symbole_ibkr(s.ticker)
                q = _straddle(ib, symbole, s.echeance, s.strike)
                if q is None:
                    dire(f"{s.ticker} : pas de cotation pour revendre le straddle, nouvel essai demain.",
                         "warning")
                    continue
                _, _, milieu, _, vente_affichee = q
                contrat = ex.contrat_butterfly(ib, s.echeance, [("C", s.strike, "SELL"),
                                                                 ("P", s.strike, "SELL")], symbole)
                r = ex.executer_combo(ib, contrat, s.lots, ex.paliers(-milieu, -vente_affichee), mode,
                                      instrument=f"{s.ticker} straddle vente", journal=JOURNAL)
                examines += 1
                if mode == MODE_REEL and r.rempli >= s.lots:
                    spot = od.cours(ib, [s.ticker]).get(s.ticker, 0.0)
                    f = livre.fermer(s, -r.prix_moyen, jour.isoformat(),
                                     abs(spot / s.spot - 1) if s.spot and spot else 0.0)
                    vendus += 1
                    lignes.append(f"{f.ticker} {f.resultat_usd:+,.0f} $")
                    dire(f"{f.ticker} : straddle revendu {f.vente:.2f} (payé {f.prime:.2f}), "
                         f"{f.resultat_usd:+,.0f} $ ; mouvement réel {f.realise:.1%} contre "
                         f"{f.prevu:.1%} prévu.", "info" if f.resultat_usd >= 0 else "warning")
                elif mode == MODE_REEL and r.rempli:
                    dire(f"{s.ticker} : vente partielle ({r.rempli}/{s.lots}), le prochain "
                         f"rapprochement bloquera le pod.", "critical")
                else:
                    dire(f"{s.ticker} : vente {r.statut} ({r.detail[:100]}).")
        else:
            etat = rg.etat_du_fonds(vl, plus_haut_du_fonds(vl))
            if etat == "arret":
                dire("Fonds à −15 % de son plus haut : aucun achat (charte).", "warning")
                _noter(jour, moment, mode, vl, 0, 0, 0, livre.engage_usd())
                return 0
            facteur = 0.5 if etat == "reduire" else 1.0
            vue = load_market_view()
            eligibles = st.univers(ind.ecran(vue.ohlcv, vue.members))
            resultats = cal.resultats(jour, eligibles) + \
                cal.resultats(st.prochain_jour_ouvre(jour), eligibles)
            tenus = {s.ticker for s in livre.straddles}
            for cand in st.candidats(resultats, jour, eligibles):
                t = cand["ticker"]
                if t in tenus:
                    continue
                examines += 1
                hab = st.mouvement_habituel(vue.ohlcv[t]["Close"], publications_passees(t, jour))
                if hab is None:
                    dire(f"{t} : trop peu de résultats passés pour juger, ignoré.")
                    continue
                symbole = od.symbole_ibkr(t)
                spot = od.cours(ib, [t]).get(t)
                action = Stock(symbole, "SMART", "USD")
                ib.qualifyContracts(action)
                chaines = [c for c in ib.reqSecDefOptParams(symbole, "", "STK", action.conId)
                           if c.tradingClass == symbole]
                reaction = date.fromisoformat(cand["reaction"])
                echeance = st.premiere_echeance(chaines[0].expirations, reaction) if chaines else None
                if not (spot and echeance):
                    dire(f"{t} : pas de cours ou d'échéance après le {reaction}, ignoré.", "warning")
                    continue
                strike = min(chaines[0].strikes, key=lambda k: abs(k - spot))
                q = _straddle(ib, symbole, echeance, strike)
                if q is None:
                    dire(f"{t} : straddle {strike:g} {echeance} sans cotation, ignoré.", "warning")
                    continue
                _, _, milieu, achat_affiche, _ = q
                avis = st.juger(milieu, spot, hab["moyenne"])
                if not avis.acheter:
                    dire(f"{t} : pas d'achat — {avis.motif}.")
                    continue
                n = st.lots(achat_affiche * 100, vl, livre.engage_usd(), facteur)
                if n < 1:
                    dire(f"{t} : achat mérité ({avis.motif}) mais budget de prime épuisé.", "warning")
                    continue
                contrat = ex.contrat_butterfly(ib, echeance, [("C", strike, "BUY"), ("P", strike, "BUY")],
                                               symbole)
                r = ex.executer_combo(ib, contrat, n, ex.paliers(milieu, achat_affiche), mode,
                                      instrument=f"{t} straddle achat", journal=JOURNAL)
                if mode == MODE_REEL and r.rempli:
                    livre.straddles.append(lv.Straddle(t, echeance, strike, r.rempli, r.prix_moyen,
                                                       jour.isoformat(), cand["reaction"], avis.prevu,
                                                       avis.habituel, spot))
                    achetes += 1
                    lignes.append(f"{t} {r.rempli} lot(s)")
                    dire(f"{t} : {r.rempli} straddle(s) {strike:g} {echeance} achetés {r.prix_moyen:.2f} "
                         f"— {avis.motif}.")
                else:
                    dire(f"{t} : achat {r.statut} — {avis.motif}"
                         f"{f', marge {r.marge_initiale:,.0f} $' if r.marge_initiale else ''}.")

        if mode == MODE_REEL:
            lv.sauver(livre, livre_chemin)
        _noter(jour, moment, mode, vl, examines, achetes, vendus, livre.engage_usd())
        dire(f"{moment.capitalize()} : {examines} examiné(s), {achetes} acheté(s), {vendus} revendu(s) ; "
             f"prime engagée {livre.engage_usd():,.0f} $.")
        if lignes:
            notifier_telephone(ROLE, f"{moment.capitalize()} : {'; '.join(lignes)}.",
                               url="/?membre=acheteur-de-volatilite", tag=f"acheteur-{moment}")
        return 0
    except Exception as e:
        dire(f"Séance interrompue : {e}", "critical")
        raise
    finally:
        ib.disconnect()


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Une séance de l'acheteur de volatilité.")
    p.add_argument("moment", choices=["entree", "sortie"])
    return seance(p.parse_args(argv).moment)


if __name__ == "__main__":
    sys.exit(main())
