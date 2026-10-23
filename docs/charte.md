# Charte de Milan Capital — le desk de volatilité

*Arrêtée le 2026-10-22 par Nathan, à partir de ses réponses. C'est le document
fondateur de la v2 : toute idée nouvelle passe devant elle. Si elle n'y entre
pas, elle attend le point d'étape.*

*La v1 — l'arène multi-agents, juin → octobre 2026 — est figée sous le tag Git
`v1-arene`. Elle fait partie de l'histoire du fonds, pas de son passif.*

---

## 1. Ce que fait Milan Capital

Milan Capital est un **desk de volatilité actions, systématique et
automatisé**.

Son métier : être payé pour porter un risque que d'autres veulent assurer. En
moyenne, les options prévoient plus de mouvement que le marché n'en fait
réellement — c'est la **prime de variance**, documentée depuis des décennies.
Le desk vend cette assurance, avec une perte maximale connue à l'entrée de
chaque position, et se protège contre le jour où l'assurance doit payer.

On ne prétend pas être plus malin que le marché. On accepte un risque précis,
on le mesure, on le limite.

## 2. Ce que Milan Capital ne fait pas

- **Pas de pari directionnel intraday.** Le desk surveille son risque pendant
  la journée ; il ne devine pas la direction du marché minute par minute.
- **Pas d'options vendues nues.** Toute vente est couverte par un achat qui
  plafonne la perte (spread).
- **Pas de décision de trading par un modèle de langage.** Un LLM connaît la
  suite de l'histoire jusqu'à sa date de coupure : on ne peut pas le tester
  honnêtement sur le passé.
- **Pas de nouvelle stratégie sans test préalable.** Hypothèse → données →
  test hors échantillon → *ensuite seulement* le code
  (`docs/verdicts_agents.md`).
- **Pas de changement de cap avant le point d'étape** (section 7).

## 3. Organisation

```
 L'ÉQUIPE (agents Claude)        LE DESK (stratégies)
 analyste événements              1. vendeur de volatilité
 contrôleur des risques           2. couverture
 responsable de séance            3. événements (phase 2)
        │ freine / alerte                │ propose
        └──────────────┬─────────────────┘
                       ▼
                 LE MOTEUR  ── limites de la charte (section 5)
           décide, dimensionne, exécute
                       ▼
                     IBKR
```

| Qui | Ce que c'est | Son pouvoir |
|---|---|---|
| **Le desk** | Trois stratégies écrites en code, à règles fixes, testées sur le passé. | **Propose** des positions. |
| **Le moteur** | Le système qui lit les propositions, les freins et les limites. | **Seul à trader.** 100 % automatique. |
| **L'équipe** | Agents Claude (Anthropic Agent SDK), un par métier. | **Freine seulement** : réduire ou couper le risque, jamais en ajouter. |

Deux règles pour l'équipe :

- **Autorité asymétrique.** Un freinage à tort coûte un peu de gain ; une
  accélération à tort peut coûter le fonds. L'équipe n'a donc que le premier
  pouvoir.
- **Hors du chemin critique.** Si l'API d'Anthropic ne répond pas, le moteur
  tourne seul avec ses règles. Chaque freinage est enregistré et jugé au point
  d'étape : a-t-il fait gagner ou perdre ?

## 4. Capital et univers

- **Capital : tout le compte paper IBKR.** La valeur liquidative est lue chez
  le courtier à chaque séance (≈ 1,03 M$ le 2026-10-21). Toutes les limites
  sont exprimées en pourcentage de cette valeur.
- **Phase 1 — indice.** Options sur le S&P 500 (SPY) : vendeur de volatilité
  et couverture.
- **Phase 2 — grandes actions.** L'agent événements, sur les grandes
  capitalisations, une fois son test réussi.

## 5. Limites de risque

| Limite | Seuil | Effet | Statut |
|---|---|---|---|
| Perte depuis le plus haut | **−8 %** | Taille de toutes les positions divisée par deux | Décidé |
| Perte depuis le plus haut | **−15 %** | Arrêt du desk, revue complète avant toute reprise | Décidé |
| Perte maximale par position | **2 %** du capital | Refus de l'ordre au-delà | Décidé |
| Test de stress : S&P −20 % en une séance | perte **≤ 10 %** | Pas de nouvelle vente tant que le test échoue | Décidé |
| Exposition au marché (delta), à la volatilité (vega), à l'accélération (gamma) | à calibrer sur le backtest | Réduction automatique | *À fixer* |

Surveillance pendant la séance : toutes les 15 minutes, le moteur recalcule
les grecques et le test de stress, et réduit le risque si une limite saute.

## 6. Mise en service

1. **Tester** — vente de puts et iron condors sur les indices du CBOE (PUT,
   CNDR), plus de 30 ans avec les krachs ; rejeu d'avril 2025 (droits de
   douane) sur les trois stratégies.
2. **Construire** — couche options : chaîne IBKR, grecques, ordres combinés,
   risque en grecques, dashboard.
3. **Observer** — 3 mois de paper trading en direct, comparés au backtest.
4. **Point d'étape.**

Prérequis hors code : autorisation de négociation d'options sur le compte
paper IBKR, demandée par Nathan.

## 7. Point d'étape

À la fin des 3 mois d'observation. Verdict écrit et daté, sur ces critères
(*proposés, à valider avant le début de l'observation*) :

- le direct est-il cohérent avec le backtest, aux frais près ?
- les limites de la section 5 ont-elles tenu, y compris un jour de choc ?
- rendement par unité de risque (Sharpe) après frais — objectif honnête
  0,8 à 1 ; **jugé avec la pire séance et la pire baisse**, car le Sharpe d'un
  vendeur de volatilité flatte avant le krach ;
- les freinages de l'équipe ont-ils fait gagner ou perdre ?

Issues possibles : augmenter la taille, corriger, ou arrêter. Le levier se
décide ici, jamais avant : il augmente le rendement et le risque, pas le
Sharpe.

---

## Amendement 1 — 2026-10-23 : trois pods (décision du CIO)

*Décidé par Nathan, CIO, le 2026-10-23 : « c'est un compte de paper trading,
c'est une expérience, avant tout un projet qui permet d'apprendre ; ça ne veut
pas dire qu'on doit faire n'importe quoi ». Ajouté sous la charte d'origine,
qui reste lisible telle qu'elle a été commitée (46a1654).*

Milan Capital devient un **desk hybride** de trois pods, chacun avec son
budget de risque, son registre et **sa propre mesure de résultat** :

| Pod | Métier | Statut |
|---|---|---|
| **Vendeur de volatilité** | Iron butterflies XSP (`docs/desk/phase2_observation.md`) | Simulation jusqu'à l'armement de janvier |
| **Acheteur de volatilité** | Long straddles avant les résultats des grandes sociétés, quand les options sous-estiment le mouvement habituel | Armé en paper dès sa mise en service |
| **Prop trader** | Actions du S&P 500, à l'achat et à la vente à découvert, décidées chaque jour par un agent Claude | Armé en paper dès sa mise en service |

Règles détaillées : `docs/desk/pods.md`.

**Ce qui change dans la section 2.** « Pas de décision de trading par un
modèle de langage » ne vaut plus pour le **seul pod Prop trader**, et
seulement en paper trading. Les raisons de la règle d'origine restent vraies
(un LLM ne se teste pas sur le passé, il est convaincant même quand il a tort) ;
le CIO choisit d'en faire une expérience mesurée **vers l'avenir**, la seule
mesure honnête d'un LLM. Trois garde-fous ne bougent pas :
1. **Le système passe l'ordre**, jamais l'agent : ses propositions sont
   vérifiées par le code (limites ci-dessous), relues par le Risk Manager,
   exécutées par le code.
2. **Chaque trade a un stop** posé chez le courtier à l'entrée.
3. **Les limites du fonds priment** sur celles des pods : à −8 % depuis le plus
   haut, les tailles de tous les pods sont divisées par deux ; à −15 %, plus
   aucune ouverture, dans aucun pod.

**Budgets de risque** (choisis par le CIO) :

| Pod | Limites |
|---|---|
| Prop trader | 8 positions au plus · 8 % de la valeur liquidative par position · perte maximale 1 % par trade (entrée − stop) · pause du reste de la séance si le pod perd 2 % dans la journée |
| Acheteur | 0,5 % de la valeur liquidative de prime par straddle · 2 % au total en cours |
| Vendeur | Inchangé (sections 4 et 5) |

**Mesure.** Le compte étant partagé, le résultat de chaque pod est calculé
sur ses propres positions et exécutions, jamais sur la valeur du compte
entier. Le point d'étape juge chaque pod séparément.
