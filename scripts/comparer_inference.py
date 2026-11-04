"""Compare les mêmes requêtes sans et avec inférence (étape 3 du sujet).

Commande : python scripts/comparer_inference.py
Sorties  : resultats/comparaison_inference.md (tableau commenté)
           resultats/triplets_inferes.ttl (seulement les triplets ajoutés par R1 et R2)
"""

import sys
from pathlib import Path

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDF

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from inference.inferer import appliquer_inference  # noqa: E402

SG = Namespace("http://skillgraph-tn.org/vocab#")
SGD = Namespace("http://skillgraph-tn.org/donnees/")
SCHEMA = Namespace("https://schema.org/")
PREFIXES = """PREFIX sg: <http://skillgraph-tn.org/vocab#>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
"""

Q0 = PREFIXES + "SELECT (COUNT(DISTINCT ?offre) AS ?n) WHERE { ?offre a sg:Offre }"
Q2 = PREFIXES + "SELECT (COUNT(DISTINCT ?offre) AS ?n) WHERE { ?offre sg:exigeCompetence ?competence }"
Q1 = PREFIXES + """SELECT ?nom (COUNT(DISTINCT ?offre) AS ?n)
WHERE { ?offre sg:exigeCompetence ?c . ?c foaf:name ?nom }
GROUP BY ?nom ORDER BY DESC(?n) ?nom LIMIT 5"""


def charger() -> Graph:
    g = Graph()
    for fichier in ("ontologie/vocabulaire.ttl", "donnees/offres.ttl", "donnees/candidats.ttl"):
        g.parse(RACINE / fichier)
    return g


def nombre(g: Graph, requete: str, **parametres) -> int:
    return int(next(iter(g.query(requete, initBindings=parametres)))[0])


def top(g: Graph) -> str:
    lignes = [f"{nom} ({n})" for nom, n in g.query(Q1)]
    return ", ".join(lignes) if lignes else "aucun résultat"


def main():
    sans = charger()
    avec = charger()
    ajoutes = appliquer_inference(avec)

    # vérification : une offre StagePFE devient aussi Stage, Offre et JobPosting (R1 en boucle)
    pfe = next(sans.subjects(RDF.type, SG.StagePFE))
    for classe in (SG.Stage, SG.Offre, SCHEMA.JobPosting):
        assert (pfe, RDF.type, classe) in avec, f"{pfe} n'est pas {classe}"

    inferes = avec - sans
    inferes.namespace_manager = sans.namespace_manager
    (RACINE / "resultats").mkdir(exist_ok=True)
    inferes.serialize(RACINE / "resultats" / "triplets_inferes.ttl", format="turtle")

    par_type = len(list(inferes.triples((None, RDF.type, None))))
    par_exige = len(list(inferes.triples((None, SG.exigeCompetence, None))))
    python = SGD["competence-python"]
    lignes = [
        ("Q0 · Nombre d'offres (`?offre a sg:Offre`)", nombre(sans, Q0), nombre(avec, Q0), "R1",
         "Les offres ne sont écrites que `sg:StagePFE`, `sg:Stage` ou `sg:Emploi` (règle d'écriture 1). "
         "R1 en boucle remonte la hiérarchie jusqu'à `sg:Offre`."),
        ("Q2 · Offres qui exigent Python (`sg:exigeCompetence`, `?competence = python`)",
         nombre(sans, Q2, competence=python),
         nombre(avec, Q2, competence=python), "R2",
         "Les offres n'utilisent que `sg:competenceRequise` / `sg:competenceSouhaitee` (règle d'écriture 2). "
         "R2 en déduit `sg:exigeCompetence` : les offres où Python est requis **et** celles où il est souhaité."),
        ("Q1 · Top 5 des compétences exigées", top(sans), top(avec), "R2",
         "Même cause que Q2 : sans inférence, aucune offre n'« exige » de compétence. "
         "Avec R2, le classement compte compétences requises et souhaitées ensemble."),
    ]

    md = ["# Comparaison sans / avec inférence", "",
          "Généré par `python scripts/comparer_inference.py` (ne pas modifier à la main).", "",
          f"- Graphe sans inférence : {len(sans)} triplets (vocabulaire + offres + candidats).",
          f"- Graphe avec inférence : {len(avec)} triplets, soit **{ajoutes} triplets inférés** "
          f"({par_type} `rdf:type` par R1, {par_exige} `sg:exigeCompetence` par R2).",
          "- Les triplets inférés sont dans `resultats/triplets_inferes.ttl`.", "",
          "| Requête | Sans inférence | Avec inférence | Règle |", "|---|---|---|---|"]
    md += [f"| {q} | {s} | {a} | {r} |" for q, s, a, r, _ in lignes]
    md += ["", "## Commentaires", ""] + [f"- **{q.split(' · ')[0]}** : {c}" for q, _, _, _, c in lignes]
    (RACINE / "resultats" / "comparaison_inference.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"{len(sans)} triplets sans inférence, {len(avec)} avec : {ajoutes} triplets inférés "
          f"({par_type} rdf:type, {par_exige} sg:exigeCompetence)")
    for q, s, a, r, _ in lignes:
        print(f"{q.split(' · ')[0]} : sans = {s} | avec = {a} ({r})")
    print("-> resultats/comparaison_inference.md, resultats/triplets_inferes.ttl")


if __name__ == "__main__":
    main()
