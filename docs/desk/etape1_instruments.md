# Étape 1 — Ce que le compte peut réellement trader

*Vérifié le 2026-10-22 sur le serveur de production, par simulation d'ordre
IBKR (`whatIfOrder`) : IBKR calcule la marge et accepte ou refuse, **sans
qu'aucun ordre ne soit transmis**. Compte paper d'essai, client « Retail »
au sens de MiFID. Scripts temporaires, supprimés après usage.*

## Résultats

| Instrument | Simulation | Marge initiale | Remarque |
|---|---|---|---|
| **ETF SPY** (achat d'actions) | ❌ **refusé** | — | Client « Retail » MiFID : pas de document d'information clé (KID) pour cet ETF américain |
| Option SPY, put à la monnaie, 20/11/2026 (vente 1) | ✅ | 6 828 $ | Livrée en actions SPY à l'exercice |
| Option **XSP** (mini-SPX), put 766, 20/11/2026 (vente 1) | ✅ | 6 825 $ | Réglée en cash, exercice européen |
| Option **SPX** (SPXW), put 7 655, 20/11/2026 (vente 1) | ✅ | 68 270 $ | Réglée en cash, 10 × XSP |
| Future **MES** (micro E-mini S&P 500), déc. 2026 (achat 1) | ✅ | 2 160 $ | 5 $ × indice ≈ 38 500 $ d'exposition |
| Future ES, déc. 2026 (achat 1) | ✅ | 21 603 $ | 10 × MES |
| ETF UCITS CSPX (Londres, USD) / SXR8 (EUR) | ✅ | ~212 $ | Équivalents européens du S&P 500 |
| **Iron butterfly SPY** en un seul ordre combiné : put 723 acheté, put et call 763 vendus, call 803 acheté | ✅ | 1 731 $ | La marge est la perte maximale : le risque défini fonctionne |

Pièges rencontrés, à reproduire dans le code :

- Sans durée de validité explicite (`tif = "DAY"`), IBKR répond par
  l'avertissement 10349 et `whatIfOrder` d'ib_insync revient **vide**, ce qui
  ressemble à un refus. Toujours fixer `tif`.
- `reqSecDefOptParams("SPY")` renvoie aussi la classe `2SPY` (2 échéances) :
  filtrer `tradingClass == "SPY"`.

## Ce que ça change pour le desk

**1. Couverture du delta : les micro-futures MES.** Autorisés, très liquides,
ouverts presque 24 h sur 24. Un MES ≈ 38 500 $ d'exposition, soit environ
50 actions SPY : la couverture d'un desk de notre taille se règle finement.
Les ETF UCITS sont un plan B, mais cotent aux heures européennes.

**2. Les options SPY posent un problème que les tests n'avaient pas vu.**
Une option SPY vendue peut être **exercée contre nous** : un put exercé nous
livre des actions SPY… que nous n'avons pas le droit d'acheter. Les options
XSP et SPX n'ont pas ce problème :

| | SPY | XSP | SPX |
|---|---|---|---|
| Règlement | actions SPY | **cash** | **cash** |
| Exercice anticipé possible | oui (risque surtout avant dividende) | **non** (européen) | **non** (européen) |
| Taille, put à la monnaie | ~85 $ par point de vol | ~85 $ par point de vol | ~850 $ par point de vol |
| Lien avec notre test | indirect | **même indice que le VIX** | **même indice que le VIX** |
| Liquidité | la plus forte | plus faible : écarts à mesurer | très forte |

À la taille de la charte (~1 100 $ par point de volatilité), un seul straddle
SPX dépasse déjà la cible ; XSP permet de doser par paliers d'environ 170 $.
**Piste pour le protocole de la phase 2 : options XSP, couverture en MES**,
sous réserve des écarts achat-vente que le collecteur (étape 2) mesurera sur
XSP et SPY côte à côte.

**3. Le risque défini passe en un seul ordre.** IBKR accepte l'iron
butterfly comme un ordre combiné et n'exige que la perte maximale en marge.
