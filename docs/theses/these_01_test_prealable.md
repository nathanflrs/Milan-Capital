# Thèse n°1 — Test préalable (section 8)

*Protocole écrit le 2026-10-11, **avant** toute mesure. Les résultats sont
ajoutés en bas, sous une ligne datée ; rien au-dessus de cette ligne ne bouge
après coup.*

---

## 1. La question

La section 8 de la thèse pose une condition avant toute position :

> L'écart mesuré par Eisfeldt, Schubert et Zhang après la sortie de ChatGPT
> a-t-il continué de se creuser entre 2023 et 2026 ? S'il s'est refermé, le
> marché a déjà tout intégré et la thèse perd sa raison d'être.

« L'écart », c'est le portefeuille **AMH** (*Artificial Minus Human*) : acheteur
des entreprises dont la main-d'œuvre est la plus exposée à l'IA générative,
vendeur des moins exposées. Il a gagné ~5 % dans les deux semaines suivant le
30 novembre 2022.

## 2. Données

| Quoi | Source | Limite connue |
|---|---|---|
| Exposition par entreprise | artificialminushuman.com, `genaiexp_estz_firmscores.csv` (score `total`, mars 2023) | Identifiée par GVKEY Compustat, que nous n'avons pas |
| GVKEY → nom | même site, `genaiexp_data_assets.csv` | |
| Nom → ticker, CIK | SEC `company_tickers.json` | **Ne contient que les sociétés cotées aujourd'hui** |
| Actions en circulation, point-in-time | SEC XBRL *frames*, `dei:EntityCommonStockSharesOutstanding` | Déclaratif, parfois manquant |
| Secteur | SEC `submissions/CIK*.json`, code SIC | Code actuel, pas historique |
| Prix | yfinance, ajusté dividendes et divisions | Source gratuite |
| Facteurs | Kenneth French (Carhart, FF5) | |

**Rapprochement GVKEY → ticker par le nom** : minuscules, ponctuation et formes
juridiques retirées (inc, corp, co, ltd, plc…), correspondance **exacte**
seulement. Un nom qui correspond à plusieurs tickers est écarté. Pas de
correspondance approximative : une erreur de rapprochement placerait une
entreprise dans le mauvais quintile sans que rien ne le signale. Le taux de
rapprochement est publié.

**Biais du survivant, assumé et chiffré.** Une société rachetée ou radiée entre
2023 et 2026 n'est plus dans la liste SEC : elle disparaît des deux jambes. Le
nombre de sociétés perdues est publié.

## 3. Construction — copie de l'article, pas une variante

- **Quintiles** du score `total` sur l'univers rapproché ; acheteur Q5, vendeur Q1.
- **Pondération par la capitalisation** (comme l'article) : actions en
  circulation déclarées à la SEC × cours non ajusté du jour de formation.
- **Formation le premier jour de bourse de chaque année** (et le 29/11/2022
  pour la réplication), puis portefeuille conservé tel quel jusqu'à la
  formation suivante (*buy-and-hold*).
- Filtres : cours ≥ 5 $ et capitalisation ≥ 100 M$ le jour de formation —
  connus ce jour-là, donc sans regard vers l'avenir.

## 4. Étape 0 — réplication (garde-fou)

Avant de mesurer 2023-2026, on refait la mesure de l'article : AMH du
30/11/2022 au 14/12/2022.

- **Écart positif** : la chaîne de données reproduit le phénomène, on continue.
- **Écart nul ou négatif** : la chaîne est suspecte. On **s'arrête** et on
  cherche pourquoi, sans conclure sur 2023-2026.

L'article mesure un rendement *anormal* et sur l'univers complet ; on ne
s'attend pas aux mêmes 5 % au dixième près, seulement au même signe.

## 5. Le test — 2023-01-03 → dernier cours disponible

Mesures, toutes publiées quelle que soit leur direction :

1. **Rendement cumulé** de l'AMH, et rendement par année civile.
2. **Alpha Carhart** (marché, taille, value, momentum) et **alpha FF5 +
   momentum**, quotidiens, erreurs de Newey-West (5 retards).
3. **AMH « utilisateurs »** : même construction, en excluant les fabricants
   (SIC 3570-3579 ordinateurs, 3670-3679 semi-conducteurs, 7370-7379 logiciels
   et services informatiques). C'est la version qui correspond à la thèse
   (« les utilisateurs, pas les fabricants »).
4. **AMH intra-secteur** : quintiles formés à l'intérieur de chaque SIC à deux
   chiffres (secteurs d'au moins 10 sociétés), pour séparer l'effet IA de
   l'effet « secteur technologique ».

## 6. Règle de décision, fixée maintenant

Le verdict de la section 8 se lit sur la **mesure 1, version de l'article
(tous secteurs)** :

| Rendement cumulé 2023 → 2026 | Verdict |
|---|---|
| ≤ 0 | **Refermé.** La thèse perd sa raison d'être, comme écrit en section 8. Pas de position. |
| > 0 | **Creusé.** La condition de la section 8 est remplie. |

Puis deux lectures, qui ne changent pas le verdict mais disent **ce qu'il vaut
pour cette thèse-là** :

- **Si l'alpha Carhart est ≤ 0** alors que le rendement brut est positif :
  l'écart s'est creusé *par des facteurs connus* (momentum, croissance). La
  poche, neutre au marché et au momentum (section 6), n'en aurait rien capté.
  Écrit tel quel.
- **Si l'AMH « utilisateurs » est ≤ 0** : l'écart s'est creusé chez les
  fabricants, pas chez les utilisateurs. C'est l'inverse de la thèse. Écrit
  tel quel.

Une t-statistique sous 2 n'est **pas** un « refermé » : elle dit que trois ans
et demi ne suffisent pas à distinguer l'écart du hasard. Les deux sont publiés.

## 7. Ce que ce test ne dit pas

Il mesure des **cours**, pas des marges. La thèse se juge à 18 mois sur les
marges et le chiffre d'affaires par employé (section 8). Un écart de cours qui
s'est creusé peut vouloir dire « le marché découvre l'effet » (favorable) ou
« le marché l'a déjà payé d'avance » (défavorable) : ce test ne tranche pas
entre les deux, il vérifie seulement que la porte n'est pas fermée.

---

## Résultats — 2026-10-11

*Exécution de `python -m scripts.test_these_01_prealable`. Prix jusqu'au
2026-10-09 ; facteurs French jusqu'au 2026-08-31. Une seule correction entre
l'écriture du protocole et la mesure : un bug de format de date dans le
chargement des facteurs, sans effet sur les choix.*

### Données réellement utilisées

| | Nombre |
|---|---|
| Scores publiés | 5 907 |
| … dont avec un nom dans le fichier du site | 2 784 |
| … rapprochés à un ticker coté aujourd'hui (nom exact) | 2 225 (80 %) |
| … avec des prix yfinance | 2 213, dont 219 fabricants |
| … retenus à la formation du 29/11/2022 (filtres cours et capitalisation) | 1 534 |

**Limite principale** : le site ne donne un nom qu'à 2 784 des 5 907 scores,
et la table GVKEY → ticker est sous licence (WRDS). L'univers testé est donc
environ un quart des sociétés de l'article — essentiellement les grandes, celles
qui pèsent dans un portefeuille pondéré par la capitalisation. S'y ajoute le
biais du survivant annoncé (§2).

### Étape 0 — réplication : réussie

AMH du 30/11 au 14/12/2022 : **+5,14 %** (article : ~5 %). La chaîne de données
reproduit le phénomène. Plus grosses lignes : MSFT, NVDA, AVGO, VZ, ADBE côté
exposé ; TSLA, WMT, CVX, HD, KO côté non exposé.

### Mesures 2023-01-03 → 2026-10-09 (946 séances)

| | Cumulé | 2023 | 2024 | 2025 | 2026 | Alpha Carhart | Alpha FF5+MOM |
|---|---|---|---|---|---|---|---|
| **1-2. Version de l'article** | **+51,9 %** (t 1,33) | +23,3 % | +13,2 % | +2,2 % | +6,5 % | +7,8 %/an (t 0,90) | +6,1 %/an (t 0,72) |
| **3. « Utilisateurs »** (fabricants exclus) | **−2,0 %** (t 0,10) | −4,6 % | −0,7 % | +2,7 % | +0,6 % | +3,0 %/an (t 0,35) | +2,1 %/an (t 0,24) |
| **4. Intra-secteur** | **−9,6 %** (t −0,10) | +10,7 % | −11,0 % | +4,0 % | −11,7 % | +3,2 %/an (t 0,36) | +3,6 %/an (t 0,41) |

### Verdict, selon la règle du §6

**Creusé.** L'AMH de l'article a gagné +51,9 % de 2023 à octobre 2026. La
condition de la section 8 est remplie : la porte n'est pas fermée.

Les deux lectures fixées à l'avance :

- **Alpha Carhart positif (+7,8 %/an)** : l'écart ne s'explique pas entièrement
  par le marché, la taille, la value et le momentum. Mais t = 0,90 : trois ans
  et demi ne suffisent pas à le distinguer du hasard.
- **AMH « utilisateurs » ≤ 0 (−2,0 %)** : l'écart s'est creusé **chez les
  fabricants, pas chez les utilisateurs**. C'est l'inverse de la thèse, écrit
  tel quel. Retirer 219 sociétés de SIC 357x/367x/737x suffit à faire passer
  l'écart de +52 % à −2 %. La version intra-secteur (−9,6 %) dit la même chose :
  à secteur égal, être plus exposé n'a rien rapporté.

### Ce que cela signifie pour la thèse

Le marché a payé l'IA de 2023 à 2026 **là où la thèse refuse d'aller** — chez
ceux qui la fabriquent. Chez les utilisateurs, il n'a rien payé du tout.

Deux lectures restent possibles, et ce test ne tranche pas entre elles (§7) :

1. **Favorable** : le marché n'a pas encore intégré l'adoption par les
   utilisateurs — exactement l'erreur que la thèse prétend exploiter. L'écart
   reste à venir, et il viendra par les marges (le juge de la section 8).
2. **Défavorable** : l'exposition des tâches, telle que mesurée par l'article,
   ne prédit pas qui gagne chez les utilisateurs. Les prédictions sur les
   marges devront alors s'appuyer sur les conditions 2 et 3 de la section 4
   (données propres, signes concrets d'adoption), pas sur le score d'exposition
   seul.

La porte est ouverte, mais rien n'est encore acquis : **le score d'exposition
seul ne sélectionne pas les gagnants de la thèse.**
