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

## Résultats — mesurés le 2026-10-22

*Sortie complète : `logs/desk_phase1bis_results.json`. Séances du 3 janvier
1990 au 14 octobre 2026 (fin de la série Yahoo téléchargée) : 440 périodes de
21 séances par départ.*

### Deux précisions de lecture, signalées honnêtement

- **Une erreur dans le protocole.** Il affirme que le bêta ne dépend pas de la
  taille *N*. C'est faux : le bêta grandit avec *N*, seuls le Sharpe et la
  corrélation n'en dépendent pas. C3 est donc lu **à la taille de la charte**,
  la seule à laquelle le fonds opérerait — taille fixée par le protocole
  lui-même, avant de voir les critères. La corrélation est rapportée à côté.
- **« Départ médian »** n'était pas défini : c'est le départ dont le Sharpe est
  le 11e sur 21 (séance 13).

### Taille

**N = 0,11 % du capital par point de volatilité.** Pour 1 M$, environ 1 100 $
gagnés ou perdus par point d'écart entre la volatilité vendue et celle
constatée.

### Les chiffres

| 1990 → 2026, frais déduits | Plafonné, départ médian | Plafonné, pire départ | Sans plafond, médian |
|---|---|---|---|
| **Sharpe** | **0,86** | 0,73 | 0,77 |
| Sharpe du S&P 500, mêmes périodes | 0,58 | 0,62 | 0,58 |
| Gain au-dessus du taux sans risque | +2,7 %/an | +2,4 %/an | +2,6 %/an |
| Volatilité | 3,1 % | 3,3 % | 3,4 % |
| **Alpha** | **+1,6 %/an [+0,3 ; +2,9]** | +1,3 %/an | +1,5 %/an |
| Bêta à cette taille | 0,12 | 0,12 | 0,12 |
| **Corrélation au S&P 500** | **0,59** | 0,52 | 0,57 |
| Depuis 2015 | +2,1 %/an | +1,3 %/an | +1,8 %/an |
| Pire baisse | −12,3 % (2008) | −13,6 % (2020) | −15,1 % |
| Pire période | −10,1 % (mars 2020) | −10,0 % | −13,0 % |
| Périodes gagnantes | 83 % | 80 % | 83 % |

### Les critères

| | Départ médian | Part des 21 départs qui passent |
|---|---|---|
| **C1** — Sharpe ≥ S&P 500 | ✅ 0,86 ≥ 0,58 | 21 / 21 |
| **C2** — alpha à 95 % au-dessus de 0 | ✅ [+0,3 % ; +2,9 %] | 20 / 21 |
| **C3** — bêta < 0,3 | ✅ 0,12 | 21 / 21 |
| **C4** — gain depuis 2015 > 0 | ✅ +2,1 %/an | 21 / 21 |

### Épisodes de stress, à la taille de la charte

| Épisode | Résultat | VIX à l'entrée → agitation constatée |
|---|---|---|
| LTCM 1998 | −0,3 % | 31,9 → 40,5 |
| 2008 | **−11,0 %** | 35,2 → 81,3 |
| Août 2011 | −4,7 % | 20,2 → 47,4 |
| Volmageddon 2018 | −2,3 % | 13,8 → 25,9 |
| Mars 2020 | **−11,3 %** | 33,4 → 93,4 |
| Avril 2025 | −0,7 % | 24,9 → 32,8 |

### Verdict

**Les quatre critères passent.** Selon le protocole, on construit le vendeur
(charte, section 6, étape 2), et la phase suivante teste l'exécution réelle
sur prix d'options.

### Ce que le verdict ne dit pas — trois réserves

1. **« Neutre au marché » est trop fort.** Le bêta est faible parce que la
   position est petite ; la **corrélation de 0,59** dit que la stratégie perd
   quand le marché chute. Normal : l'agitation explose dans les krachs. La
   couverture en delta retire la direction, pas ce lien-là. Ce qui nous
   protège, c'est la taille et le plafond, pas la neutralité. L'agent
   couverture n'est pas un luxe.
2. **Le gain est modeste.** À la taille de la charte : environ +2,7 %/an
   au-dessus du taux sans risque. Mieux payé par unité de risque que le
   marché, mais avec peu de risque.
3. **Le proxy est flatteur et les baisses sont sous-estimées** (section 3) :
   le desk réel fera moins bien, et les pires baisses en cours de mois de
   2008 et 2020 ont été plus profondes que ce qui est mesuré ici.

### Hors protocole — que coûterait plus de taille ?

*Ajouté après la mesure, pour la question « prendre plus de risque ».*

| *N* (% du capital par point) | 0,11 (charte) | 0,25 | 0,50 |
|---|---|---|---|
| Gain au-dessus du cash | +2,7 %/an | +6,1 %/an | +12,2 %/an |
| Volatilité | 3,1 % | 7,1 % | 14,2 % |
| Pire baisse (départ médian) | −12,3 % | −27,4 % | −51,8 % |
| Pire baisse (pire des 21 départs) | −14,7 % | −31,7 % | −56,8 % |

À *N* = 0,50, la volatilité égale celle du S&P 500 et la pire baisse aussi :
même risque que le marché, Sharpe meilleur. Mais c'est hors charte, et la
charte ne se change qu'au point d'étape.
