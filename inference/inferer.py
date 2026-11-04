"""Moteur d'inférence : applique nos règles SPARQL (inference/regles/) au graphe (contrat 3 de PLAN.md).

Utilisation : from inference.inferer import appliquer_inference
"""

from pathlib import Path

from rdflib import Graph

DOSSIER_REGLES = Path(__file__).resolve().parent / "regles"
REGLES = [DOSSIER_REGLES / "r1_sous_classe.rq", DOSSIER_REGLES / "r2_sous_propriete.rq"]


def appliquer_inference(g: Graph) -> int:
    """Ajoute au graphe les triplets inférés par R1 et R2, renvoie le nombre de triplets ajoutés.

    En boucle jusqu'à ce que rien de nouveau n'apparaisse : StagePFE -> Stage -> Offre -> JobPosting
    demande plusieurs tours de R1.
    """
    regles = [r.read_text(encoding="utf-8") for r in REGLES]
    avant = len(g)
    while True:
        taille = len(g)
        for regle in regles:
            for triplet in list(g.query(regle)):  # list() : on ne modifie pas le graphe pendant qu'on le lit
                g.add(triplet)
        if len(g) == taille:
            return len(g) - avant
