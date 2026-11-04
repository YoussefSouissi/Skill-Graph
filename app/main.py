"""Web service REST de SkillGraph TN : 6 endpoints qui renvoient en JSON les résultats des requêtes SPARQL.

Commande : uvicorn app.main:app --reload   puis ouvrir http://127.0.0.1:8000/docs
Réponses : {"inference": bool, "nombre": int, "resultats": [...]} ; paramètre inference=true|false partout.
"""

from typing import Literal as Choix

from fastapi import FastAPI, HTTPException, Query
from rdflib import Namespace
from rdflib.namespace import RDF

from app.requetes import executer, graphe
from scripts.csv_vers_rdf import slug

SG = Namespace("http://skillgraph-tn.org/vocab#")
SGD = Namespace("http://skillgraph-tn.org/donnees/")
TYPES = {"pfe": SG.StagePFE, "stage": SG.Stage, "emploi": SG.Emploi}
INFERENCE = Query(True, description="true : graphe avec les triplets déduits par R1 et R2 ; false : données brutes")

app = FastAPI(title="SkillGraph TN",
              description="Graphe de connaissances des offres tech en Tunisie, interrogé en SPARQL.")
graphe(True), graphe(False)  # chargés au démarrage : chaque appel est ensuite instantané


def reponse(inference: bool, resultats: list) -> dict:
    return {"inference": inference, "nombre": len(resultats), "resultats": resultats}


@app.get("/offres", summary="Offres filtrées par ville, compétence et type (Q2)")
def offres(ville: str | None = Query(None, description="ex. tunis"),
           competence: str | None = Query(None, description="slug, ex. python"),
           type: Choix["pfe", "stage", "emploi"] | None = None,
           inference: bool = INFERENCE):
    parametres = {
        "ville": SGD[f"ville-{slug(ville)}"] if ville else None,
        "competence": SGD[f"competence-{slug(competence)}"] if competence else None,
        "type": TYPES[type] if type else None,
    }
    return reponse(inference, executer("q2", parametres, inference))


@app.get("/offres/avec-sans", summary="Offres qui exigent une compétence mais pas une autre (Q3)")
def offres_avec_sans(avec: str = Query(..., description="compétence voulue, ex. python"),
                     sans: str = Query(..., description="compétence à éviter, ex. sql"),
                     inference: bool = INFERENCE):
    parametres = {"avec": SGD[f"competence-{slug(avec)}"], "sans": SGD[f"competence-{slug(sans)}"]}
    return reponse(inference, executer("q3", parametres, inference))


@app.get("/competences/top", summary="Compétences les plus demandées (Q1)")
def competences_top(limite: int = Query(10, ge=1, le=100, description="nombre de compétences (1 à 100)"),
                    inference: bool = INFERENCE):
    # LIMIT n'accepte pas de variable en SPARQL : on coupe ici
    return reponse(inference, executer("q1", {}, inference)[:limite])


@app.get("/candidats/{identifiant}/correspondances", summary="Offres qui correspondent à un candidat, avec un score (Q5)")
def correspondances(identifiant: str, inference: bool = INFERENCE):
    candidat = SGD[f"candidat-{identifiant}"]
    # Q5 renvoie 50 offres à 0 pour un candidat inconnu : on vérifie qu'il existe avant
    if (candidat, RDF.type, SG.Candidat) not in graphe(inference):
        raise HTTPException(404, f"Candidat inconnu : {identifiant}")
    resultats = executer("q5", {"candidat": candidat}, inference)
    for r in resultats:
        r["score"] = round(100 * r["nbPossedees"] / r["nbRequises"])
    resultats.sort(key=lambda r: (-r["score"], -r["nbPossedees"], r["titre"]))
    return reponse(inference, resultats)


@app.get("/entreprises/actives", summary="Entreprises qui publient plusieurs offres (Q4)")
def entreprises_actives(inference: bool = INFERENCE):
    return reponse(inference, executer("q4", {}, inference))


@app.get("/statistiques/inference", summary="Ce que l'inférence ajoute (Q0 et taille du graphe)")
def statistiques(inference: bool = INFERENCE):
    resultats = [
        {"indicateur": "offres de type sg:Offre (Q0)", "valeur": executer("q0", {}, inference)[0]["nbOffres"]},
        {"indicateur": "triplets dans le graphe", "valeur": len(graphe(inference))},
    ]
    if inference:
        resultats.append({"indicateur": "triplets déduits par R1 et R2",
                          "valeur": len(graphe(True)) - len(graphe(False))})
    return reponse(inference, resultats)
