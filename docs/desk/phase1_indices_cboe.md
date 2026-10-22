# Phase 1 — La vente de volatilité tient-elle sur 30 ans ?

*Protocole écrit le 2026-10-22, **avant** toute mesure. Les résultats sont
ajoutés en bas, sous une ligne datée ; rien au-dessus de cette ligne ne bouge
après coup. Cadre : `docs/charte.md`, section 6, étape 1.*

---

## 1. Les questions

Le moteur du desk, le vendeur de volatilité, repose sur une affirmation : **les
options sur le S&P 500 sont, en moyenne, vendues trop cher**. Avant d'écrire
une ligne du desk, on vérifie qu'elle tient — et ce qu'elle coûte les mauvais
jours.

1. **La prime existe-t-elle ?** Vendre des puts rapporte-t-il plus, par unité
   de risque, que détenir simplement le S&P 500 ?
2. **Existe-t-elle encore ?** Une prime connue de tous peut s'être refermée.
   On regarde séparément la période récente.
3. **Que coûte-t-elle les mauvais jours ?** Pire séance, pire mois, pire baisse
   et temps pour s'en remettre — 2008, 2020, 2022, avril 2025.
4. **À quelle taille respecte-t-on la charte ?** Quelle part du capital
   peut-on exposer pour que la pire baisse historique reste au-dessus de
   −15 % ?
5. **Avril 2025.** Jour par jour, du 31 mars au 30 mai 2025 : que seraient
   devenus ces indices, et quelles règles de la charte se seraient
   déclenchées ?

## 2. Données

| Quoi | Source | Ce que c'est |
|---|---|---|
| **PUT** | CBOE, historique quotidien | Vend chaque mois un put à la monnaie sur le S&P 500, à un mois, entièrement garanti par des bons du Trésor. |
| **CNDR** | CBOE, historique quotidien | Iron condor mensuel sur le S&P 500 : vend un put et un call éloignés, achète des options encore plus éloignées qui plafonnent la perte. |
| **S&P 500 dividendes réinvestis** | yfinance `^SP500TR` | La référence : ce que rapporte le marché sans rien faire. |
| **VIX** | CBOE | Volatilité prévue par les options sur 30 jours. |
| **Taux sans risque** | yfinance `^IRX` | Bons du Trésor à 3 mois. |

**Limites connues, écrites avant :**

- Ce sont des **indices**, pas nos futures positions. PUT vend à la monnaie,
  sans protection ; notre vendeur vendra des spreads plus éloignés. CNDR est
  plus proche de ce qu'on fera, mais n'est pas identique.
- Aucun frais de transaction ni d'écart achat-vente n'est déduit. Les
  résultats sont donc un **plafond** : le desk réel fera moins bien.
- Rien ici ne teste la couverture (agent 2) ni l'agent événements : il faut
  des prix d'options, qu'on n'a pas encore.

## 3. Mesures

Pour chaque série, sur l'historique commun et sur deux moitiés
(avant / après le 1er janvier 2008), plus la période récente (2015 → 2026) :

- **rendement annuel moyen** ;
- **volatilité** (à quel point la valeur s'agite, annualisée) ;
- **Sharpe** (rendement au-dessus du taux sans risque, divisé par la
  volatilité) ;
- **pire baisse depuis un plus haut**, et sa durée de récupération ;
- **pire séance, pire mois** ;
- **asymétrie** (les pertes sont-elles plus brutales que les gains ?) ;
- **bêta** au S&P 500 (quelle part du mouvement du marché on subit).

Taille compatible avec la charte (question 4) : on mélange l'indice et du
cash au taux sans risque, `w × indice + (1 − w) × cash`, rééquilibré chaque
mois, et on cherche le plus grand `w` dont la pire baisse reste au-dessus de
−15 %.

## 4. Critères, fixés avant la mesure

| | Critère | Si non |
|---|---|---|
| **C1** | Sharpe de PUT ≥ Sharpe du S&P 500, sur tout l'historique **et** sur la seconde moitié. | La prime n'est pas démontrée par cet indice : on ne construit pas le vendeur sans autre preuve. |
| **C2** | Rendement de PUT au-dessus du taux sans risque > 0 sur 2015 → 2026. | La prime s'est peut-être refermée : on le dit, et on cherche pourquoi avant de construire. |
| **C3** | À la taille `w` de la question 4, rendement au-dessus du taux sans risque ≥ 2 %/an. | La stratégie seule ne vaut pas son risque : la couverture devient une condition, pas une option. |

Mêmes critères appliqués à CNDR, rapportés à côté — sans changer le verdict
porté sur PUT.

Script : `scripts/desk_phase1_indices_cboe.py`.

---

## Résultats — mesurés le 2026-10-22

*Sortie complète : `logs/desk_phase1_results.json`. Frais non déduits.*

### Une limite de données découverte à la mesure

Le fichier gratuit du CBOE ne contient que **7 points pour PUT avant 2007**.
L'historique commun va donc de **février 2007 à octobre 2026** (237 mois), pas
30 ans. La « moitié avant 2008 » ne fait que 10 mois : elle est rapportée dans
le JSON mais **ne sert à rien**. En revanche, 2007-2026 contient trois vrais
krachs (2008, mars 2020, avril 2025) et une baisse longue (2022).

### Les chiffres

| 2007-02 → 2026-10, mensuel | PUT | CNDR | S&P 500 (div. réinvestis) |
|---|---|---|---|
| Rendement annuel | 7,2 % | 0,9 % | 11,0 % |
| Au-dessus du taux sans risque | 6,0 % | −0,4 % | 10,1 % |
| Volatilité | 10,7 % | 6,8 % | 15,4 % |
| **Sharpe** | **0,56** | **−0,06** | **0,66** |
| Pire baisse (mensuel) | −32,7 % | −19,0 % | −50,9 % |
| Pire baisse (quotidien) | −37,1 % | −19,7 % | −55,3 % |
| Temps pour revenir | 2,5 ans | 16 ans | 4,5 ans |
| Pire séance | −11,5 % (16/03/2020) | −4,5 % | −12,0 % |
| Pire mois | −17,7 % | −7,9 % | −16,8 % |
| Asymétrie | −1,69 | −1,60 | −0,56 |
| Bêta | 0,60 | 0,10 | 1,00 |

Depuis 2015 : PUT 0,67 de Sharpe contre 0,80 pour le S&P 500.

### Les critères

| | PUT | CNDR |
|---|---|---|
| **C1** — Sharpe ≥ S&P 500, partout | ❌ 0,56 < 0,66 ; 0,56 < 0,68 depuis 2008 | ❌ |
| **C2** — au-dessus du cash depuis 2015 | ✅ +6,3 %/an | ❌ −0,3 %/an |
| **C3** — ≥ 2 %/an à la taille charte | ✅ w = 43 %, +2,6 %/an, pire baisse −14,7 % | ❌ |

À pire baisse égale (−15 %), **25 % de S&P 500 + 75 % de cash rapportent
+2,5 %/an** — autant que PUT à 43 %.

### Avril 2025, jour par jour (31 mars → 30 mai)

VIX de 22,3 à **52,3 le 8 avril**.

| | Pire baisse | Pire séance | Règle déclenchée | Au 30 mai |
|---|---|---|---|---|
| PUT pleine taille | −10,2 % (8/4) | −5,7 % (4/4) | −8 % le 4 avril | −0,7 % |
| PUT à 43 % | −4,4 % | −2,4 % | aucune | +0,3 % |
| CNDR pleine taille | −5,5 % | −3,2 % | aucune | −2,8 % |
| S&P 500 | −12,1 % | −6,0 % | −8 % le 4 avril | +5,6 % |

### Verdict

**C1 échoue : selon le protocole, on ne construit pas le vendeur de
volatilité sur cette seule preuve.** C2 et C3 passent pour PUT, mais ils ne
rattrapent pas C1 : à risque égal, vendre des puts n'a pas fait mieux que
détenir un peu de S&P 500.

CNDR, la stratégie la plus proche de notre futur vendeur, échoue aux trois
critères : sur 20 ans, elle a rapporté moins que le cash.

### Hors protocole — ajouté après la mesure, pour comprendre C1

*Ces mesures n'étaient pas prévues. Elles expliquent, elles ne jugent pas.*

- **L'alpha de PUT est nul** : −0,05 %/an, intervalle à 95 % [−2,9 % ;
  +2,8 %], bêta 0,60. Tout son rendement s'explique par 60 % d'exposition au
  marché. CNDR : −1,4 %/an [−4,7 % ; +1,8 %].
- **Pourtant, la prime de variance existe dans les prix.** Le VIX a dépassé
  la volatilité constatée le mois suivant **85 % des jours** depuis 1990 (19,4
  contre 15,4 en moyenne). L'écart s'est réduit sans disparaître : 4,8 points
  en 1990-2006, 3,5 points depuis 2015.

Lecture : les options sont bien vendues trop cher en moyenne, mais **vendre un
put sans couverture, c'est surtout être acheteur du marché avec des gains
plafonnés**. La prime touchée a été mangée par les krachs et par les hausses
manquées. C'est cohérent avec la décomposition de l'indice BXM (vente de
calls couverts) par Israelov et Nielsen (*Covered Calls Uncovered*, FAJ 2015) :
la composante « volatilité » paie, la composante « marché » brouille le
résultat.

Piste que cela ouvre, **à protocoliser avant toute mesure** : vendre la
volatilité **en neutralisant l'exposition au marché** (couverture en delta),
ce que fait un vrai desk. Le test demande des prix d'options, ou une
approximation par les swaps de variance construite sur le VIX.
