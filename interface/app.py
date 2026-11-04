"""Interface SkillGraph TN : appelle les endpoints du web service et affiche les réponses (au lieu de Postman).

Commande : streamlit run interface/app.py   (le web service doit tourner : uvicorn app.main:app)
Format des réponses : {"inference", "nombre", "resultats"}, paramètre inference=true|false.
"""

import csv
import sys
from pathlib import Path
from urllib.parse import quote

import httpx
import pandas as pd
import streamlit as st
from rdflib import Graph, Namespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from candidats import lire_candidats  # noqa: E402

SGD = Namespace("http://skillgraph-tn.org/donnees/")
TYPES = {"Tous": None, "Stage PFE": "pfe", "Stage": "stage", "Emploi": "emploi"}
EXEMPLE = "offre-kj-249246"  # un Stage PFE : montre bien R1 (StagePFE -> Stage -> Offre -> JobPosting)

# Noms lisibles des colonnes renvoyées par le web service
LIBELLES = {"titre": "Titre", "entreprise": "Entreprise", "nomVille": "Ville", "nom": "Nom", "offre": "Identifiant",
            "competence": "Identifiant", "nbOffres": "Nombre d'offres", "villes": "Villes", "score": "Score",
            "nbRequises": "Requises", "nbPossedees": "Possédées", "indicateur": "Indicateur", "valeur": "Valeur"}

# Ce que fait chaque page : affiché en haut de la page
PAGES = {
    "Offres": {
        "icone": "🔎", "chemin": "/offres", "requete": "q2", "colonnes": ["titre", "entreprise", "nomVille", "offre"],
        "question": "Quelles offres correspondent à mes critères (ville, compétence, type) ?",
        "comment": "Q2 relie chaque offre à son titre, son entreprise, sa ville et ses compétences. Chaque filtre "
                   "rempli est passé à la requête par `initBindings` ; un filtre vide accepte toutes les valeurs.",
        "notion": "Motifs de triplets, variables liées par `initBindings`, `DISTINCT`",
        "inference": "Indispensable : Q2 passe par `sg:exigeCompetence`, que seule R2 ajoute. Sans inférence : 0 offre. "
                     "Avec : le type « Stage » trouve aussi les Stage PFE (R1).",
    },
    "Avec / sans compétence": {
        "icone": "➖", "chemin": "/offres/avec-sans", "requete": "q3", "colonnes": ["titre", "offre"],
        "question": "Quelles offres demandent une compétence que j'ai, mais pas une que je n'ai pas ?",
        "comment": "Q3 garde les offres qui exigent la première compétence, puis retire celles qui exigent "
                   "aussi la seconde.",
        "notion": "`FILTER NOT EXISTS` (la négation)",
        "inference": "Indispensable : Q3 passe par `sg:exigeCompetence` (R2). Sans inférence : 0 offre.",
    },
    "Top compétences": {
        "icone": "📊", "chemin": "/competences/top", "requete": "q1", "colonnes": ["nom", "nbOffres", "competence"],
        "question": "Quelles compétences le marché demande-t-il le plus ?",
        "comment": "Q1 fait un groupe par compétence, compte les offres de chaque groupe, puis trie du plus grand "
                   "au plus petit.",
        "notion": "`COUNT`, `GROUP BY`, `ORDER BY`",
        "inference": "Indispensable : avec R2, une compétence requise ou souhaitée devient « exigée ». "
                     "Sans inférence : aucun résultat.",
    },
    "Correspondances candidat": {
        "icone": "🎯", "chemin": "/candidats/{id}/correspondances", "requete": "q5",
        "colonnes": ["score", "titre", "nbPossedees", "nbRequises", "offre"],
        "question": "Quelles offres correspondent à ce candidat, et à quel point ?",
        "comment": "Q5 compte, pour chaque offre, ses compétences requises et celles que le candidat possède "
                   "(`OPTIONAL` garde les offres où il n'en a aucune). Le web service calcule le score en %.",
        "notion": "`OPTIONAL`, `COUNT`, `GROUP BY`, `initBindings`",
        "inference": "Sans effet : Q5 utilise `sg:competenceRequise`, écrit directement dans les données.",
    },
    "Entreprises actives": {
        "icone": "🏢", "chemin": "/entreprises/actives", "requete": "q4", "colonnes": ["nom", "nbOffres", "villes"],
        "question": "Quelles entreprises publient plusieurs offres, et dans quelles villes ?",
        "comment": "Q4 compte les offres de chaque entreprise et ne garde que celles qui en ont plus d'une "
                   "(`HAVING` filtre après le comptage, `GROUP_CONCAT` colle les villes).",
        "notion": "`COUNT`, `GROUP BY`, `HAVING`, `GROUP_CONCAT`",
        "inference": "Sans effet : `sg:publieePar` et `sg:situeeA` sont écrits directement dans les données.",
    },
    "Inférence": {
        "icone": "🧠", "chemin": "/statistiques/inference", "requete": "q0", "colonnes": ["indicateur", "valeur"],
        "question": "Qu'apporte l'inférence ?",
        "comment": "Compare le graphe sans et avec les triplets déduits par les règles R1 et R2.",
        "notion": "Règles R1 (sous-classe) et R2 (sous-propriété), `COUNT` (Q0)",
        "inference": "C'est le sujet de la page : les deux versions sont affichées côte à côte.",
    },
}

st.set_page_config(page_title="SkillGraph TN", page_icon="🎓", layout="wide")


@st.cache_data
def competences() -> dict[str, str]:
    """slug -> nom, pour les listes déroulantes (donnees/competences.csv)."""
    with open(RACINE / "donnees" / "competences.csv", encoding="utf-8") as f:
        return {c["slug"]: c["nom"] for c in csv.DictReader(f)}


@st.cache_data
def exemple_inference() -> list[str]:
    """Turtle des triplets écrits (offres.ttl) puis déduits (resultats/triplets_inferes.ttl) pour l'offre EXEMPLE."""
    textes = []
    for fichier in ("donnees/offres.ttl", "resultats/triplets_inferes.ttl"):
        source = Graph().parse(RACINE / fichier)
        extrait = Graph(namespace_manager=source.namespace_manager)
        for triplet in source.triples((SGD[EXEMPLE], None, None)):
            extrait.add(triplet)
        turtle = extrait.serialize(format="turtle")
        textes.append("\n".join(l for l in turtle.splitlines() if l and not l.startswith("@prefix")))
    return textes


def expliquer(infos: dict):
    """Le bloc « ce que fait cette page » : question, requête, notion, effet de l'inférence."""
    st.info(f"**{infos['question']}**\n\n{infos['comment']}")
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**Endpoint**  \n`GET {infos['chemin']}`")
    c2.markdown(f"**Notions SPARQL**  \n{infos['notion']}")
    c3.markdown(f"**Effet de l'inférence**  \n{infos['inference']}")
    fichiers = sorted((RACINE / "requetes").glob(f"{infos['requete']}_*.rq"))
    if fichiers:
        with st.expander(f"Voir la requête SPARQL ({infos['requete'].upper()} · requetes/{fichiers[0].name})"):
            st.code(fichiers[0].read_text(encoding="utf-8"), language="sparql")
    st.divider()


def appeler(chemin: str, inference: bool | None = None, **parametres) -> dict | None:
    """GET sur le web service ; affiche l'URL appelée, l'erreur éventuelle et le JSON brut."""
    parametres = {k: v for k, v in parametres.items() if v not in (None, "")}
    parametres["inference"] = str(st.session_state.inference if inference is None else inference).lower()
    try:
        reponse = httpx.get(st.session_state.base + chemin, params=parametres, timeout=30)
    except httpx.HTTPError:
        st.error(f"Le web service ne répond pas à {st.session_state.base}.  \n"
                 "Lance-le dans un terminal : `uvicorn app.main:app --reload`")
        return None
    try:
        contenu = reponse.json()
    except ValueError:
        st.error(f"Réponse qui n'est pas du JSON ({reponse.status_code}).")
        return None
    with st.expander(f"Requête HTTP : GET {reponse.request.url} → {reponse.status_code}"):
        st.json(contenu)
    if reponse.status_code != 200:
        detail = contenu.get("detail")
        if isinstance(detail, list):  # erreur 422 de FastAPI : liste des paramètres invalides
            detail = " ; ".join(f"{e['loc'][-1]} : {e['msg']}" for e in detail)
        st.error(f"Erreur {reponse.status_code} : {detail}")
        return None
    return contenu


def tableau(contenu: dict | None, colonnes: list[str]) -> pd.DataFrame | None:
    """Affiche les résultats en tableau lisible (colonnes choisies et renommées)."""
    if not contenu:
        return None
    resultats = contenu.get("resultats", [])
    if not resultats:
        st.warning("Aucun résultat." + ("" if contenu.get("inference") else
                                        " Essaie avec l'inférence (barre de gauche)."))
        return None
    donnees = pd.DataFrame(resultats)
    donnees = donnees[[c for c in colonnes if c in donnees] or list(donnees)]
    st.dataframe(donnees.rename(columns=LIBELLES), hide_index=True, width="stretch", column_config={
        "Score": st.column_config.ProgressColumn("Score", format="%d %%", min_value=0, max_value=100)})
    return donnees


with st.sidebar:
    st.title("🎓 SkillGraph TN")
    st.caption("Le marché de l'emploi tech en Tunisie, interrogé par le web service.")
    page = st.radio("Que veux-tu savoir ?", list(PAGES), format_func=lambda p: f"{PAGES[p]['icone']} {p}")
    st.divider()
    st.toggle("Avec inférence", True, key="inference",
              help="Envoie inference=true ou false : le web service répond sur le graphe avec ou sans "
                   "les triplets déduits par R1 et R2.")
    with st.expander("Réglages"):
        st.text_input("Adresse du web service", "http://127.0.0.1:8000", key="base")

noms = competences()
infos = PAGES[page]
st.header(f"{infos['icone']} {page}")
expliquer(infos)

if page == "Offres":
    c1, c2, c3 = st.columns(3)
    ville = c1.text_input("Ville", placeholder="ex. Tunis (vide = toutes)")
    competence = c2.selectbox("Compétence", [""] + list(noms), format_func=lambda s: noms.get(s, "Toutes"))
    type_offre = c3.selectbox("Type", list(TYPES))
    contenu = appeler("/offres", ville=ville.strip(), competence=competence, type=TYPES[type_offre])
    if contenu:
        st.metric("Offres trouvées", contenu["nombre"])
    tableau(contenu, infos["colonnes"])

elif page == "Avec / sans compétence":
    c1, c2 = st.columns(2)
    avec = c1.selectbox("Je sais faire", list(noms), index=list(noms).index("python"), format_func=noms.get)
    sans = c2.selectbox("Je ne sais pas faire", list(noms), index=list(noms).index("sql"), format_func=noms.get)
    contenu = appeler("/offres/avec-sans", avec=avec, sans=sans)
    if contenu:
        st.metric(f"Offres avec {noms[avec]} mais sans {noms[sans]}", contenu["nombre"])
    tableau(contenu, infos["colonnes"])

elif page == "Top compétences":
    limite = st.slider("Nombre de compétences", 1, len(noms), 10)
    contenu = appeler("/competences/top", limite=limite)
    donnees = tableau(contenu, infos["colonnes"])
    if donnees is not None:
        st.bar_chart(donnees.set_index("nom")["nbOffres"].rename("Nombre d'offres"), horizontal=True)

elif page == "Correspondances candidat":
    liste = lire_candidats()
    identifiant = st.selectbox("Candidat", list(liste), format_func=lambda i: f"{liste[i]} ({i})")
    contenu = appeler(f"/candidats/{quote(identifiant, safe='')}/correspondances")
    if contenu:
        resultats = contenu["resultats"]
        m1, m2, m3 = st.columns(3)
        m1.metric("Offres analysées", contenu["nombre"])
        m2.metric("Au moins une compétence en commun", sum(r["nbPossedees"] > 0 for r in resultats))
        m3.metric("Profil complet (100 %)", sum(r["score"] == 100 for r in resultats))
    tableau(contenu, infos["colonnes"])

elif page == "Entreprises actives":
    tableau(appeler("/entreprises/actives"), infos["colonnes"])

else:
    sans_inf = appeler("/statistiques/inference", inference=False)
    avec_inf = appeler("/statistiques/inference", inference=True)
    if sans_inf and avec_inf:
        valeurs = {r["indicateur"]: r["valeur"] for r in sans_inf["resultats"]}
        for colonne, r in zip(st.columns(len(avec_inf["resultats"])), avec_inf["resultats"]):
            avant = valeurs.get(r["indicateur"])
            colonne.metric(r["indicateur"], r["valeur"],
                           delta=None if avant is None else f"+{r['valeur'] - avant} (sans : {avant})")
    st.subheader(f"Exemple : ce que l'inférence ajoute à l'offre {EXEMPLE}")
    ecrits, deduits = exemple_inference()
    c1, c2 = st.columns(2)
    c1.markdown("**Écrit dans `donnees/offres.ttl`**")
    c1.code(ecrits, language="turtle")
    c2.markdown("**Déduit par R1 et R2** (`resultats/triplets_inferes.ttl`)")
    c2.code(deduits, language="turtle")
    st.caption("R1 : StagePFE ⊂ Stage ⊂ Offre ⊂ JobPosting ⇒ l'offre reçoit ces trois types. "
               "R2 : competenceRequise et competenceSouhaitee ⊂ exigeCompetence ⇒ chaque compétence devient « exigée ».")
