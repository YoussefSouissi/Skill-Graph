"""Collecte des offres tech de Keejob et Tanitjobs avec ScrapeGraphAI (contrat 2 de PLAN.md).

Commande : python scripts/scraper.py
Sortie   : donnees/brut/offres.csv (une ligne par offre)

Ollama doit tourner avec le modèle qwen2.5:7b (ollama pull qwen2.5:7b).
Les robots.txt de Keejob et Tanitjobs autorisent les pages utilisées ici (pas la recherche par
mot-clé de Tanitjobs, interdite) ; on attend 2 s entre deux pages.
"""

import csv
import re
import time
import unicodedata
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel
from scrapegraphai.graphs import SmartScraperGraph

RACINE = Path(__file__).resolve().parent.parent
FICHIER_CSV = RACINE / "donnees" / "brut" / "offres.csv"
FICHIER_COMPETENCES = RACINE / "donnees" / "competences.csv"
KEEJOB = "https://www.keejob.com"
TANITJOBS = "https://www.tanitjobs.com"
PAGES_DE_LISTE = [KEEJOB + chemin for chemin in [
    "/offres-emploi/secteur/informatique-telecoms/?page=1",
    "/offres-emploi/secteur/informatique-telecoms/?page=2",
    "/offres-emploi/secteur/informatique-telecoms/?page=3",
    "/offres-emploi/?keywords=developpeur",
    "/offres-emploi/?keywords=data",
    "/offres-emploi/?keywords=python",
    "/offres-emploi/?keywords=java",
    "/offres-emploi/?keywords=stage+informatique",
    "/offres-emploi/?keywords=ingenieur+informatique",
    "/offres-emploi/?keywords=devops",
    "/offres-emploi/?keywords=full+stack",
    "/offres-emploi/?keywords=web",
    "/offres-emploi/?keywords=sql",
]] + [TANITJOBS + f"/categories/705/informatique-jobs/?page={n}" for n in range(1, 5)] \
  + [TANITJOBS + f"/categories/381/technologie-de-l-information-jobs/?page={n}" for n in range(1, 3)]
NOMBRE_VOULU = 50
PAUSE = 2
ENTETE = {"User-Agent": "Mozilla/5.0 (projet etudiant SkillGraph TN)"}
COLONNES = ["id", "titre", "entreprise", "ville", "type_contrat", "date_publication", "url",
            "competences_requises", "competences_souhaitees", "experience_min", "mode_travail"]

CONFIG = {"llm": {"model": "ollama/qwen2.5:7b", "model_tokens": 8192,
                  "format": "json", "temperature": 0}}


class Offre(BaseModel):
    """Les colonnes demandées au modèle (les noms et e-mails de recruteurs ne sont pas demandés)."""
    titre: str
    entreprise: str
    ville: str
    type_contrat: str
    date_publication: str
    competences_requises: list[str]
    competences_souhaitees: list[str]
    experience_min: int | None = None
    mode_travail: str | None = None


def lire_competences() -> dict[str, str]:
    """Renvoie le dictionnaire slug -> nom de donnees/competences.csv."""
    with open(FICHIER_COMPETENCES, encoding="utf-8") as f:
        return {ligne["slug"]: ligne["nom"] for ligne in csv.DictReader(f)}


def competences_citees(texte: str, competences: dict[str, str]) -> list[str]:
    """Slugs dont le nom (ou le slug) apparaît vraiment dans le texte : garde-fou contre les inventions du modèle."""
    return [slug for slug, nom in competences.items()
            if any(re.search(rf"(?<!\w){re.escape(mot)}(?!\w)", texte, re.IGNORECASE) for mot in (nom, slug))]


def telecharger(url: str) -> str:
    time.sleep(PAUSE)
    reponse = requests.get(url, headers=ENTETE, timeout=30)
    reponse.raise_for_status()
    return reponse.text


def lister_offres() -> list[tuple[str, str]]:
    """Renvoie les (id, url) des offres trouvées sur les pages de liste, sans doublon (kj- Keejob, tj- Tanitjobs)."""
    offres = {}
    for page in PAGES_DE_LISTE:
        try:
            html = telecharger(page)
        except requests.RequestException as erreur:  # une page de liste en panne ne doit pas tout arrêter
            print(f"page sautée : {page} ({erreur.__class__.__name__})")
            continue
        for chemin, ref in re.findall(r'href="(/offres-emploi/(\d+)/[^"?]+/)', html):
            offres.setdefault(f"kj-{ref}", KEEJOB + chemin)
        for url, ref in re.findall(r'href="(https://www\.tanitjobs\.com/job/(\d+)/[^"?]+/)', html):
            offres.setdefault(f"tj-{ref}", url)
    return list(offres.items())


def texte_offre(id_offre: str, url: str) -> str:
    """Texte de l'offre : la version Markdown chez Keejob, le bloc de l'annonce chez Tanitjobs."""
    if id_offre.startswith("kj-"):
        return telecharger(url[:-1] + ".md")
    html = telecharger(url)
    date = re.search(r'"datePosted":"(\d{4}-\d{2}-\d{2})', html)
    annonce = BeautifulSoup(html, "html.parser").select_one(".page-detail-annonce")
    texte = " ".join(annonce.get_text(" ").split())
    texte = texte.split("Mots clés")[0]  # après viennent les offres voisines : leurs compétences seraient comptées
    return f"Date de publication : {date.group(1) if date else ''}\n{texte}"


def extraire_offre(texte: str, slugs: list[str]) -> dict:
    """ScrapeGraphAI lit le texte de l'offre et remplit les colonnes du contrat 2."""
    prompt = (
        "Extrais les informations de cette offre d'emploi. "
        "type_contrat : le premier type de contrat cité. "
        "experience_min : nombre minimal d'années d'expérience, ou null. "
        "mode_travail : presentiel, hybride ou teletravail. "
        f"competences_requises et competences_souhaitees : uniquement des éléments de cette liste : {', '.join(slugs)}. "
        "N'ajoute une compétence que si l'offre la cite. "
        "Une compétence est souhaitée si l'offre la présente comme un atout, un plus, appréciée ou souhaitée ; "
        "sinon elle est requise. Une compétence ne peut pas être dans les deux listes."
    )
    return SmartScraperGraph(prompt=prompt, source=texte, config=CONFIG, schema=Offre).run()


def normaliser_contrat(titre: str, contrat: str) -> str:
    texte = f"{titre} {contrat}".lower()
    if "pfe" in texte or "fin d'études" in texte or "fin d’études" in texte:
        return "Stage PFE"
    if "stage" in texte:
        return "Stage"
    if "cdd" in texte:
        return "CDD"
    return "CDI"  # shortcut: SIVP, freelance et intérim sont comptés comme CDI, à revoir si on veut les distinguer


def lire_date(texte: str) -> str:
    """La date est écrite telle quelle dans la page : on la lit au lieu de la demander au modèle."""
    date = re.search(r"Date de publication\W*(\d{4}-\d{2}-\d{2})", texte)
    return date.group(1) if date else ""


def lire_ville(id_offre: str, texte: str) -> str:
    """Keejob : « Lieu : quartier, Ville, Tunisie » ; Tanitjobs : « Offres d'emploi à Ville » ."""
    if id_offre.startswith("kj-"):
        lieu = re.search(r"\*\*Lieu\*\* : (.+)", texte)
        parties = [p.strip() for p in lieu.group(1).split(",") if p.strip() != "Tunisie"] if lieu else []
        return parties[-1] if parties else ""
    ville = re.search(r"Offres d'emploi à (.+?) »", texte)
    return ville.group(1).strip() if ville else ""


def titre_simple(titre: str) -> str:
    """Titre en minuscules, sans accents ni ponctuation : « Développeur Full-Stack » -> « developpeurfullstack »."""
    titre = unicodedata.normalize("NFKD", titre.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", titre)


def est_doublon(ligne: dict, vues: list[tuple[str, str]]) -> bool:
    """Même ville et un titre qui commence par l'autre : la même offre publiée sur les deux sites."""
    ville, titre = ligne["ville"].lower(), titre_simple(ligne["titre"])
    return any(v == ville and (t.startswith(titre) or titre.startswith(t)) for v, t in vues)


def nettoyer(brut: dict, id_offre: str, url: str, texte: str, citees: list[str]) -> dict:
    """Met les valeurs au format du contrat 2.

    Compétences : toutes celles citées dans le texte (citees) ; le modèle dit seulement lesquelles sont souhaitées.
    """
    souhaitees = [c.lower().strip() for c in brut.get("competences_souhaitees") or []]
    souhaitees = list(dict.fromkeys(c for c in souhaitees if c in citees))
    requises = [c for c in citees if c not in souhaitees]
    mode = (brut.get("mode_travail") or "").lower().replace("é", "e").replace("-", "")
    mode = next((m for m in ("hybride", "teletravail", "presentiel") if m in mode), "")
    if "site" in (brut.get("mode_travail") or "").lower():
        mode = "presentiel"
    return {
        "id": id_offre,
        "titre": " ".join(brut["titre"].split(" | ")[0].split()),  # Tanitjobs ajoute « | Ville » au titre
        "entreprise": " ".join(brut["entreprise"].split(" - ")[0].split()),  # et « - Ville, Tunisie » à l'entreprise
        "ville": lire_ville(id_offre, texte) or brut["ville"].split(",")[0].strip(),
        "type_contrat": normaliser_contrat(brut["titre"], brut["type_contrat"]),
        "date_publication": lire_date(texte) or brut["date_publication"][:10],
        "url": url,
        "competences_requises": ";".join(requises),
        "competences_souhaitees": ";".join(souhaitees),
        "experience_min": "" if brut.get("experience_min") is None else brut["experience_min"],
        "mode_travail": mode,
    }


def main():
    competences = lire_competences()
    FICHIER_CSV.parent.mkdir(parents=True, exist_ok=True)
    deja_faits, vues = set(), []
    if FICHIER_CSV.exists():
        with open(FICHIER_CSV, encoding="utf-8-sig") as f:
            for ligne in csv.DictReader(f):
                deja_faits.add(ligne["id"])
                vues.append((ligne["ville"].lower(), titre_simple(ligne["titre"])))
    else:
        with open(FICHIER_CSV, "w", newline="", encoding="utf-8-sig") as f:  # BOM : Excel et Numbers reconnaissent alors les accents
            csv.DictWriter(f, COLONNES).writeheader()

    offres = lister_offres()
    print(f"{len(offres)} offres trouvées (Keejob + Tanitjobs), {len(deja_faits)} déjà dans le CSV")
    for id_offre, url in offres:
        if len(deja_faits) >= NOMBRE_VOULU:
            break
        if id_offre in deja_faits:
            continue
        try:
            texte = texte_offre(id_offre, url)
            citees = competences_citees(texte, competences)
            if not citees:
                print(f"{id_offre} ignorée : aucune compétence de la liste citée")
                continue
            ligne = nettoyer(extraire_offre(texte, citees), id_offre, url, texte, citees)
        except Exception as erreur:  # une offre illisible ne doit pas arrêter la collecte
            print(f"{id_offre} ignorée : {erreur}")
            continue
        if not ligne["competences_requises"]:
            print(f"{id_offre} ignorée : aucune compétence tech ({ligne['titre']})")
            continue
        if not ligne["ville"] or ligne["ville"] == "Tunisie" or "," in ligne["ville"]:
            print(f"{id_offre} ignorée : pas de ville en Tunisie ({ligne['ville']})")
            continue
        if est_doublon(ligne, vues):
            print(f"{id_offre} ignorée : doublon probable ({ligne['titre']}, {ligne['ville']})")
            continue
        vues.append((ligne["ville"].lower(), titre_simple(ligne["titre"])))
        with open(FICHIER_CSV, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, COLONNES).writerow(ligne)
        deja_faits.add(ligne["id"])
        print(f"{len(deja_faits):>2}/{NOMBRE_VOULU} {ligne['id']} {ligne['titre']} -> {ligne['competences_requises']}")


if __name__ == "__main__":
    main()
