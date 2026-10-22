# Phase 1-ter — La conviction peut-elle se mesurer ?

*Protocole écrit le 2026-10-22 avec Nathan, **avant** toute mesure, à
commiter avant que le script existe. Les résultats sont ajoutés en bas, sous
une ligne datée ; rien au-dessus de cette ligne ne bouge après coup. Fait
suite à `docs/desk/phase1bis_vente_variance.md`, dont il reprend toute la
mécanique.*

---

## 1. La question

Nathan veut que le système prenne plus de risque **quand il a de bonnes
raisons d'y croire**. La version honnête de cette idée : la conviction doit
être un **chiffre mesuré avant d'entrer**, et sa valeur doit être vérifiée sur
le passé.

> **Quand l'assurance est chère, le vendeur gagne-t-il davantage le mois
> suivant ? Et si oui, vendre plus dans ces moments-là rapporte-t-il plus, à
> pire baisse égale, qu'une taille fixe ?**

La seconde moitié est la vraie question. Gagner plus en perdant aussi plus
dans les krachs, ce n'est pas de la conviction : c'est du levier.

## 2. Le signal : la grosseur de la prime

Le jour d'entrée *t*, avec uniquement ce qui est connu ce jour-là :

```
S(t) = VIX(t) − RV_passée(t)
RV_passée(t) = √(252/21 × Σ r²) sur les 21 séances jusqu'à t incluse
```

Exemple : VIX 20, agitation des 21 dernières séances 12 → prime de 8.

**Un seul signal décide.** Le niveau du VIX et le rapport VIX / agitation
passée sont mesurés avec la même règle et rapportés à côté, **sans changer
le verdict** — tester plusieurs signaux et garder le meilleur reviendrait à se
mentir.

## 3. La règle de taille — 3 paliers, plafond ×2

À chaque entrée, *S(t)* est classé par rapport à **toutes les valeurs de S des
séances antérieures** (fenêtre qui s'allonge, jamais l'avenir) :

| *S(t)* dans… | Multiplicateur |
|---|---|
| le tiers bas de son historique | ×0,5 |
| le tiers du milieu | ×1 |
| le tiers haut | **×2** |

Rodage : tant que moins de 252 séances d'historique sont disponibles (1990),
le multiplicateur vaut ×1.

Gain de la période : `N × multiplicateur × gain en points`, avec la mécanique
de la phase 1-bis inchangée (1 point de frais, agitation plafonnée à
2,5 × VIX d'entrée, 21 séances, collatéral au taux sans risque).

**Taille de base** : le plus grand *N* pour lequel les 21 départs gardent leur
pire baisse au-dessus de −15 %, comme en phase 1-bis. Le vendeur à taille fixe
(*N* = 0,11 %) sert de référence, recalculé par le même script.

## 4. Critères — barre « exigeante », choisie par Nathan

**Départ de référence : la séance 13**, départ médian de la phase 1-bis, fixé
ici avant la mesure.

| | Critère |
|---|---|
| **K1** — la prime prédit | Régression du gain de la période (en points) sur *S(t)*, départ 13 : pente **> 0** avec un intervalle à 95 % (Newey-West, 3 retards) **entièrement au-dessus de 0**. |
| **K2** — à pire baisse égale, on gagne plus | Gain annuel au-dessus du taux sans risque de la taille par conviction (à sa taille de base) **>** celui de la taille fixe (*N* = 0,11 %) : au départ 13 **et** pour au moins **15 départs sur 21**, chaque départ comparé à sa propre version fixe. |
| **K3** — ça tient dans le temps | Sur 1990-2007 **et** sur 2008-2026 séparément, départ 13, tailles inchangées : pente de K1 > 0 **et** gain de la taille par conviction > gain de la taille fixe. |

**Si les trois passent** : la taille par conviction entre dans la
spécification du vendeur, sous la limite de −15 % de la charte.
**Si l'un échoue** : le vendeur garde une taille fixe, on écrit pourquoi, et
l'idée « plus de risque » revient au point d'étape, sur résultats réels.

Rapportés à côté, sans changer le verdict : Sharpe des deux versions,
répartition des paliers, chaque épisode de stress de la phase 1-bis comparé
(taille fixe contre conviction), et les deux signaux alternatifs.

## 5. Limites connues, écrites avant

- **On ne part pas à l'aveugle.** La phase 1-bis a montré que les pires
  périodes (2008, mars 2020) ont commencé à VIX élevé. Le signal choisi n'est
  pas le niveau du VIX, mais on sait déjà que ce terrain est piégé ; le
  critère K3 et la fenêtre qui s'allonge limitent, sans l'annuler, ce biais.
- **Toutes les limites de la phase 1-bis s'appliquent** : proxy VIX
  flatteur, baisses mesurées à l'échéance seulement, exécution réelle non
  testée.
- **Un multiplicateur ×2 double aussi le coût réel** des frais d'exécution,
  ce que le point de frais forfaitaire ne capte qu'en proportion.

Script : `scripts/desk_phase1ter_conviction.py`.

---

## Résultats — mesurés le 2026-10-22

*Sortie complète : `logs/desk_phase1ter_results.json`. Même période que la
phase 1-bis (1990 → 14 octobre 2026), départ de référence 13.*

### Taille

Pour que les 21 départs restent au-dessus de −15 %, la taille de base par
conviction doit descendre à **N = 0,06 %** par point, contre 0,11 % à taille
fixe. Le palier ×2 oblige à réduire tout le reste.

### Les critères

| | Résultat | |
|---|---|---|
| **K1** — la prime prédit | pente +0,15 point de gain par point de prime, intervalle à 95 % **[−0,11 ; +0,42]** | ❌ contient 0 |
| **K2** — plus de gain à pire baisse égale | départ 13 : **+1,8 %/an** contre +2,7 % à taille fixe ; la conviction ne gagne sur **aucun des 21 départs** | ❌ |
| **K3** — tenue dans le temps | 1990-2007 : +2,1 % contre +3,6 % ; 2008-2026 : +1,6 % contre +1,9 % | ❌ |

**Verdict : les trois critères échouent. Le vendeur garde une taille fixe.**
L'idée « plus de risque » revient au point d'étape, sur résultats réels.

### Ce que la conviction a fait, au départ 13

| | Taille fixe (N = 0,11) | Conviction (N = 0,06) |
|---|---|---|
| Sharpe | 0,86 | 0,99 |
| Gain au-dessus du cash | +2,7 %/an | +1,8 %/an |
| Volatilité | 3,1 % | 1,8 % |
| Pire baisse | −12,3 % | −6,6 % |

| Épisode | Paliers | Fixe | Conviction |
|---|---|---|---|
| LTCM 1998 | 1 – 2 – 0,5 – 0,5 | −0,3 % | −1,3 % |
| 2008 | 0,5 × 4 | −11,0 % | −3,1 % |
| Août 2011 | 1 – 0,5 | −4,7 % | −2,8 % |
| Volmageddon 2018 | 1 – 0,5 | −2,3 % | −1,2 % |
| Mars 2020 | 1 – 1 – 0,5 | −11,3 % | −6,5 % |
| Avril 2025 | 2 – 2 | −0,7 % | −0,7 % |

### Hors protocole — pourquoi K2 échoue

*Ajouté après la mesure, pour comprendre ; ne change pas le verdict.*

Au départ 13, la conviction a été prudente au bon moment : en 2008, la prime
paraissait petite (l'agitation réelle avait déjà rattrapé le VIX) et le
système était à ×0,5. Mais la taille se fixe sur **le pire des 21 départs**,
et celui-là raconte l'inverse.

**Départ 14 : entrée début mars 2020** (échéance le 1er avril). Le VIX venait de bondir à 36,8,
l'agitation des 21 séances passées était encore calme → prime apparente
énorme → **palier ×2**. L'agitation a ensuite atteint 94. Une seule période :
**−12,0 %** à la taille de base, la pire baisse de toute l'étude (−13,7 %).
Les départs 9 à 17 tombent tous dans ce piège, tous à ×2, tous en mars 2020.

**La leçon :** au tout début d'un krach, le VIX bondit avant que l'agitation
réelle ne suive. La prime *paraît* alors la plus grosse au moment précis où
elle est la plus dangereuse. Le signal se trompe sur le seul mois qui
compte, et ce mois-là fixe la taille de tout le reste.

Les deux signaux rapportés à côté échouent aussi aux trois critères
(niveau du VIX : départ 13 à +1,5 %/an ; rapport VIX / agitation : +1,7 %/an).
