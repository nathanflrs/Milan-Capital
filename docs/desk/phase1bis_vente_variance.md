# Phase 1-bis — Vendre la volatilité sans subir le marché

*Protocole écrit le 2026-10-22 avec Nathan, **avant** toute mesure, et commité
avant que le script existe. Les résultats sont ajoutés en bas, sous une ligne
datée ; rien au-dessus de cette ligne ne bouge après coup. Cadre :
`docs/charte.md` ; fait suite à `docs/desk/phase1_indices_cboe.md`.*

---

## 1. Pourquoi ce test

La phase 1 a montré deux choses à la fois :

- **la prime existe** : le VIX a dépassé l'agitation constatée le mois suivant
  85 % des jours depuis 1990 ;
- **vendre des puts ne la capte pas** : l'alpha de l'indice PUT est nul, tout
  son rendement s'explique par 60 % d'exposition au marché.

Un desk de volatilité sépare les deux : il vend des options **et neutralise
chaque jour leur exposition au marché** (couverture en delta). Ce qui reste,
c'est la prime seule. La question :

> **Une fois l'exposition au marché retirée et les frais payés, vendre la
> volatilité du S&P 500 rapporte-t-il mieux, par unité de risque, que le
> S&P 500 lui-même — et ce gain résiste-t-il aux krachs ?**

## 2. L'approximation : le swap de variance

Un swap de variance est un pari sur l'agitation seule. Le vendeur encaisse la
volatilité annoncée à l'entrée et paie la volatilité réellement constatée
jusqu'à l'échéance. Son gain ne dépend pas de la direction du marché : c'est
ce qu'obtient, à peu près, un desk qui vend des options et les couvre en delta
en continu.

Le VIX est construit comme la racine du prix d'un swap de variance à 30 jours
sur le S&P 500. On peut donc rejouer ce pari depuis 1990 avec deux séries
gratuites.

### Mécanique, fixée avant la mesure

Pour une période qui commence à la séance *t* et dure **21 séances** (≈ 30
jours calendaires) :

| Élément | Définition |
|---|---|
| Volatilité vendue *K* | `VIX(t) − 1` — **1 point de frais**, décidé avec Nathan |
| Volatilité constatée *RV* | `√(252/21 × Σ r²)` sur les 21 séances suivantes, *r* = rendement logarithmique quotidien du S&P 500, moyenne non retirée (convention des swaps de variance) |
| **Plafond** | *RV* comptée au plus à **2,5 × VIX(t)** — décidé avec Nathan, cohérent avec le « risque défini » de la charte |
| Gain de la période, en points de vol | `(K² − RV²) / (2K)` |
| Gain en % du capital | `N × gain en points`, *N* = % du capital engagé par point de volatilité |
| Collatéral | le capital rapporte le taux sans risque (bons du Trésor 3 mois) |

Les périodes ne se chevauchent pas. Pour ne pas dépendre du jour de départ, la
mesure est faite pour **les 21 jours de départ possibles** : le verdict porte
sur le **départ médian**, et le pire départ est rapporté à côté.

### Taille

Le plus grand *N* pour lequel **les 21 départs** gardent leur pire baisse
au-dessus de **−15 %** sur 1990-2026, version plafonnée. Le Sharpe, le bêta et
la significativité de l'alpha ne dépendent pas de *N* ; la taille ne sert qu'à
traduire les résultats en pourcentage du fonds.

## 3. Données

| Quoi | Source |
|---|---|
| VIX, clôture quotidienne | CBOE (`logs/desk_cache/VIX_History.csv`) |
| S&P 500 dividendes réinvestis, quotidien | Yahoo `^SP500TR` (`logs/desk_cache/sp500tr.json`) |
| Taux sans risque | FRED `DTB3` |

Période : **janvier 1990 → dernière échéance complète d'octobre 2026.**
Épisodes de stress rapportés nommément : LTCM (août-octobre 1998), 2008
(septembre-novembre), août 2011, *Volmageddon* (février 2018), mars 2020,
avril 2025.

**Limites connues, écrites avant :**

- **Approximation.** Le vrai prix d'un swap de variance est en général un peu
  au-dessus du VIX² (sauts, nombre fini de prix d'exercice) : le proxy est
  plutôt **optimiste**, ce que le point de frais compense en partie.
- **VIX avant 2003** : recalculé rétroactivement par le CBOE avec la méthode
  actuelle.
- **Baisses mesurées à l'échéance** : on ne valorise pas la position en cours
  de mois. La pire baisse est donc **sous-estimée** ; c'est une raison de plus
  pour garder le plafond et la règle −8 % de la charte.
- Le S&P 500 dividendes réinvestis remplace l'indice de prix pour *RV* :
  l'écart quotidien est négligeable.
- Rien ici ne teste l'exécution réelle (options SPY, couverture toutes les
  15 minutes) : c'est l'étape suivante, si ce test passe.

## 4. Critères — barre « exigeante », choisie par Nathan

Tous les critères portent sur la **version plafonnée, frais déduits, départ
médian**. Les quatre doivent passer.

| | Critère | Ce qu'il prouve |
|---|---|---|
| **C1** | Sharpe ≥ Sharpe du S&P 500 sur les mêmes périodes, 1990-2026 | Mieux payé par unité de risque que le marché |
| **C2** | Alpha contre le S&P 500 avec un intervalle à 95 % (Newey-West, 3 retards) **entièrement au-dessus de 0** | Un gain propre, pas de la chance |
| **C3** | Bêta au S&P 500 **< 0,3** | Vraiment indépendant du marché |
| **C4** | Gain moyen au-dessus du taux sans risque **> 0 depuis 2015** | La prime n'a pas disparu |

**Si les quatre passent** : on construit le vendeur (charte, section 6, étape 2),
et la phase suivante teste l'exécution réelle sur prix d'options.
**Si l'un échoue** : on ne construit pas, on écrit pourquoi, et on revient
en discuter avant toute autre piste.

Rapportés à côté, sans changer le verdict : la version **sans plafond**, la
part des 21 départs qui passent chaque critère, et le résultat de chaque
épisode de stress à la taille de la charte.

Script : `scripts/desk_phase1bis_vente_variance.py`.

---

## Résultats

*(à compléter après la mesure)*
