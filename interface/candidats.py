"""Liste des candidats de donnees/candidats.ttl (pour la liste déroulante de l'interface)."""

from pathlib import Path

from rdflib import Graph, Namespace
from rdflib.namespace import FOAF, RDF

FICHIER = Path(__file__).resolve().parent.parent / "donnees" / "candidats.ttl"
SG = Namespace("http://skillgraph-tn.org/vocab#")


def lire_candidats(fichier: Path = FICHIER) -> dict[str, str]:
    """identifiant (youssef, mohamed-amine…) -> nom affiché."""
    g = Graph().parse(fichier)
    return {str(c).rsplit("candidat-", 1)[1]: str(g.value(c, FOAF.name))
            for c in g.subjects(RDF.type, SG.Candidat)}
