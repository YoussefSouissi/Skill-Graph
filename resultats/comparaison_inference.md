# Comparaison sans / avec inférence

Généré par `python scripts/comparer_inference.py` (ne pas modifier à la main).

- Graphe sans inférence : 849 triplets (vocabulaire + offres + candidats).
- Graphe avec inférence : 1208 triplets, soit **359 triplets inférés** (146 `rdf:type` par R1, 213 `sg:exigeCompetence` par R2).
- Les triplets inférés sont dans `resultats/triplets_inferes.ttl`.

| Requête | Sans inférence | Avec inférence | Règle |
|---|---|---|---|
| Q0 · Nombre d'offres (`?offre a sg:Offre`) | 0 | 50 | R1 |
| Q2 · Offres qui exigent Python (`sg:exigeCompetence`, `?competence = python`) | 0 | 20 | R2 |
| Q1 · Top 5 des compétences exigées | aucun résultat | SQL (22), Python (20), Git (17), JavaScript (14), Linux (13) | R2 |

## Commentaires

- **Q0** : Les offres ne sont écrites que `sg:StagePFE`, `sg:Stage` ou `sg:Emploi` (règle d'écriture 1). R1 en boucle remonte la hiérarchie jusqu'à `sg:Offre`.
- **Q2** : Les offres n'utilisent que `sg:competenceRequise` / `sg:competenceSouhaitee` (règle d'écriture 2). R2 en déduit `sg:exigeCompetence` : les offres où Python est requis **et** celles où il est souhaité.
- **Q1** : Même cause que Q2 : sans inférence, aucune offre n'« exige » de compétence. Avec R2, le classement compte compétences requises et souhaitées ensemble.
