"""Conversion des offres CSV en triplets RDF.

Commande : python scripts/csv_vers_rdf.py
Entrées  : donnees/brut/offres.csv, donnees/competences.csv, donnees/entreprises.csv
Sortie   : donnees/offres.ttl
"""

import csv
import re
import unicodedata
from pathlib import Path

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import DCTERMS, FOAF, RDF, XSD

RACINE = Path(__file__).resolve().parent.parent
SG = Namespace("http://skillgraph-tn.org/vocab#")
SGD = Namespace("http://skillgraph-tn.org/donnees/")
SCHEMA = Namespace("https://schema.org/")

TYPES = {"Stage PFE": SG.StagePFE, "Stage": SG.Stage, "CDI": SG.Emploi, "CDD": SG.Emploi}


def lire_offres() -> list[dict]:
    with open(RACINE / "donnees" / "brut" / "offres.csv", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def slug(texte: str) -> str:
    """« Ben Arous » -> « ben-arous » : minuscules, sans accents, avec des tirets."""
    texte = unicodedata.normalize("NFKD", texte.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", texte).strip("-")


def detecter_type(type_contrat: str):
    """La classe la plus précise : jamais sg:Offre (l'inférence ajoute le reste)."""
    return TYPES[type_contrat]


def offre_vers_triplets(g: Graph, ligne: dict):
    offre = SGD[f"offre-{ligne['id']}"]
    entreprise = SGD[f"entreprise-{slug(ligne['entreprise'])}"]
    ville = SGD[f"ville-{slug(ligne['ville'])}"]

    g.add((offre, RDF.type, detecter_type(ligne["type_contrat"])))
    g.add((offre, DCTERMS.title, Literal(ligne["titre"])))
    g.add((offre, SCHEMA.url, Literal(ligne["url"], datatype=XSD.anyURI)))
    g.add((offre, SG.datePublication, Literal(ligne["date_publication"], datatype=XSD.date)))
    g.add((offre, SG.publieePar, entreprise))
    g.add((offre, SG.situeeA, ville))
    # règle 2 : seulement competenceRequise / competenceSouhaitee, jamais exigeCompetence
    for colonne, propriete in (("competences_requises", SG.competenceRequise),
                               ("competences_souhaitees", SG.competenceSouhaitee)):
        for c in filter(None, ligne[colonne].split(";")):
            g.add((offre, propriete, SGD[f"competence-{c}"]))
    if ligne["experience_min"]:
        g.add((offre, SG.experienceMin, Literal(int(ligne["experience_min"]), datatype=XSD.integer)))
    if ligne["mode_travail"]:
        g.add((offre, SG.modeTravail, Literal(ligne["mode_travail"])))

    # règle 4 : villes non typées ; entreprises typées seulement plus bas, si le secteur est connu
    g.add((entreprise, FOAF.name, Literal(ligne["entreprise"])))
    g.add((ville, FOAF.name, Literal(ligne["ville"])))


def main():
    g = Graph()
    for prefixe, ns in (("sg", SG), ("sgd", SGD), ("schema", SCHEMA), ("dcterms", DCTERMS), ("foaf", FOAF), ("xsd", XSD)):
        g.bind(prefixe, ns)

    offres = lire_offres()
    for ligne in offres:
        offre_vers_triplets(g, ligne)

    # règle 3 : une compétence est typée par sa catégorie, jamais par sg:Competence
    with open(RACINE / "donnees" / "competences.csv", encoding="utf-8") as f:
        for c in csv.DictReader(f):
            g.add((SGD[f"competence-{c['slug']}"], RDF.type, SG[c["categorie"]]))
            g.add((SGD[f"competence-{c['slug']}"], FOAF.name, Literal(c["nom"])))

    with open(RACINE / "donnees" / "entreprises.csv", encoding="utf-8") as f:
        for e in csv.DictReader(f):
            g.add((SGD[f"entreprise-{slug(e['nom'])}"], RDF.type, SG[e["secteur"]]))

    g.serialize(RACINE / "donnees" / "offres.ttl", format="turtle")
    nb_offres = len(set(g.subjects(SG.situeeA, None)))
    assert nb_offres == len(offres), f"{nb_offres} offres dans le graphe pour {len(offres)} lignes du CSV"
    print(f"{len(offres)} lignes CSV -> {nb_offres} offres, {len(g)} triplets dans donnees/offres.ttl")


if __name__ == "__main__":
    main()
