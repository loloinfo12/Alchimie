import streamlit as st
import sqlite3
import pandas as pd
import pdfplumber
import os
import chardet
import unicodedata

# -----------------------------
# Config fichiers
# -----------------------------
DB_NAME = "database.db"
CSV_FILE = "Recettes alchimiques.csv"   # ton CSV corrigé
PDF_FILE = "recettes_alchimiques.pdf"   # PDF contenant descriptions

# -----------------------------
# Connexion DB
# -----------------------------
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = conn.cursor()

# -----------------------------
# Initialisation DB
# -----------------------------
def init_db():
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS joueurs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT,
        niveau INTEGER
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recettes (
        rowid INTEGER PRIMARY KEY AUTOINCREMENT,
        `Nom recette` TEXT,
        Type TEXT,
        But TEXT,
        description TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS joueur_recettes (
        joueur_id INTEGER,
        recette_id INTEGER,
        FOREIGN KEY(joueur_id) REFERENCES joueurs(id),
        FOREIGN KEY(recette_id) REFERENCES recettes(rowid)
    )
    """)
    conn.commit()

init_db()

# -----------------------------
# Fonction pour normaliser texte
# -----------------------------
def normalize_text(s):
    if not isinstance(s, str):
        s = str(s)
    return unicodedata.normalize("NFC", s)

# -----------------------------
# Chargement CSV sécurisé
# -----------------------------
@st.cache_data
def load_csv(csv_file):
    # Détection automatique de l'encodage
    with open(csv_file, 'rb') as f:
        raw = f.read()
        result = chardet.detect(raw)
        encoding = result['encoding'] if result['encoding'] else 'utf-8'

    # Lire CSV avec encodage détecté
    df = pd.read_csv(csv_file, sep=";", encoding=encoding)

    # Normaliser toutes les colonnes texte
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda x: normalize_text(x))

    return df

# -----------------------------
# Import CSV vers SQLite
# -----------------------------
def import_csv():
    count = cursor.execute("SELECT COUNT(*) FROM recettes").fetchone()[0]
    if count > 0:
        return  # déjà importé

    df = load_csv(CSV_FILE)

    # Ne garder que les colonnes existantes dans la table
    cursor.execute("PRAGMA table_info(recettes)")
    cols = [col[1] for col in cursor.fetchall()]
    df = df[[c for c in df.columns if c in cols]]

    # Insérer dans la base SQLite
    df.to_sql("recettes", conn, if_exists="append", index=False)
    conn.commit()
    st.success("CSV importé et normalisé !")

# -----------------------------
# Extraction PDF sécurisée (ligne par ligne)
# -----------------------------
def extract_descriptions(force=False):
    cursor.execute("PRAGMA table_info(recettes)")
    cols = [col[1] for col in cursor.fetchall()]
    if "description" not in cols:
        cursor.execute("ALTER TABLE recettes ADD COLUMN description TEXT")
        conn.commit()

    if not force:
        count = cursor.execute(
            "SELECT COUNT(*) FROM recettes WHERE description IS NOT NULL AND description != ''"
        ).fetchone()[0]
        if count > 0:
            return

    if not os.path.exists(PDF_FILE):
        st.warning(f"PDF {PDF_FILE} non trouvé, les descriptions ne seront pas extraites.")
        return

    df_recettes = pd.read_sql("SELECT `Nom recette` FROM recettes", conn)
    noms_recettes = list(df_recettes["Nom recette"])

    # Extraire texte ligne par ligne
    lines = []
    with pdfplumber.open(PDF_FILE) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                lines += page_text.split("\n")

    # Affichage diagnostic
    st.text_area("Extrait PDF (diagnostic)", "\n".join(lines[:50]), height=200)

    # Capture des descriptions
    descriptions = {}
    for nom in noms_recettes:
        desc = ""
        capture = False
        for line in lines:
            if normalize_text(nom).lower() in normalize_text(line).lower():
                capture = True
                continue
            if capture:
                if any(normalize_text(other_nom).lower() in normalize_text(line).lower() for other_nom in noms_recettes if other_nom != nom):
                    break
                desc += line.strip() + " "
        descriptions[nom] = desc.strip()

    for nom, desc in descriptions.items():
        cursor.execute(
            "UPDATE recettes SET description=? WHERE `Nom recette`=?", (desc, nom)
        )
    conn.commit()
    st.success("Descriptions extraites depuis le PDF !")

# -----------------------------
# Fonctions utilitaires
# -----------------------------
def get_joueurs():
    return cursor.execute("SELECT id, nom, niveau FROM joueurs").fetchall()

def get_recettes():
    return cursor.execute("SELECT rowid, `Nom recette`, Type, But, description FROM recettes").fetchall()

def get_recettes_joueur(joueur_id):
    return cursor.execute("""
        SELECT r.`Nom recette`, r.Type, r.But, r.description
        FROM recettes r
        JOIN joueur_recettes jr ON r.rowid = jr.recette_id
        WHERE jr.joueur_id = ?
    """, (joueur_id,)).fetchall()

# -----------------------------
# Import initial CSV + PDF
# -----------------------------
import_csv()
extract_descriptions()

# -----------------------------
# Interface Streamlit
# -----------------------------
st.sidebar.title("🔐 Connexion")
role = st.sidebar.radio("Je suis :", ["Administrateur", "Joueur"])

# -----------------------------
# Admin
# -----------------------------
if role == "Administrateur":
    st.title("🛠 Interface Administrateur")
    menu = st.sidebar.selectbox("Menu Admin", ["Gérer Joueurs", "Attribuer Recettes", "Mettre à jour Recettes"])

    if menu == "Gérer Joueurs":
        st.header("👤 Gestion des joueurs")
        nom = st.text_input("Nom du joueur")
        niveau = st.number_input("Niveau", 1, 20)
        if st.button("Ajouter"):
            if nom.strip():
                cursor.execute("INSERT INTO joueurs (nom, niveau) VALUES (?, ?)", (nom, niveau))
                conn.commit()
                st.success("Joueur ajouté !")
            else:
                st.error("Nom du joueur vide !")

        joueurs = get_joueurs()
        if joueurs:
            joueur = st.selectbox("Choisir joueur à supprimer", joueurs, format_func=lambda x: x[1])
            if st.button("Supprimer"):
                cursor.execute("DELETE FROM joueur_recettes WHERE joueur_id=?", (joueur[0],))
                cursor.execute("DELETE FROM joueurs WHERE id=?", (joueur[0],))
                conn.commit()
                st.success("Joueur supprimé !")
        else:
            st.info("Aucun joueur à supprimer.")

    elif menu == "Attribuer Recettes":
        st.header("📜 Attribution des recettes")
        joueurs = get_joueurs()
        recettes = get_recettes()
        if joueurs and recettes:
            joueur = st.selectbox("Choisir joueur", joueurs, format_func=lambda x: x[1])
            recette = st.selectbox("Choisir recette", recettes, format_func=lambda x: x[1])
            if st.button("Attribuer"):
                cursor.execute("INSERT OR IGNORE INTO joueur_recettes (joueur_id, recette_id) VALUES (?, ?)", (joueur[0], recette[0]))
                conn.commit()
                st.success(f"Recette '{recette[1]}' attribuée à {joueur[1]} !")
        else:
            st.warning("Il faut au moins un joueur et une recette.")

    elif menu == "Mettre à jour Recettes":
        st.header("🔄 Mise à jour des recettes depuis CSV et PDF")
        if st.button("Mettre à jour maintenant"):
            import_csv()
            extract_descriptions(force=True)
            st.success("Recettes et descriptions mises à jour !")

# -----------------------------
# Joueur
# -----------------------------
elif role == "Joueur":
    st.title("🧪 Mes Recettes")
    joueurs = get_joueurs()
    if not joueurs:
        st.info("Aucun joueur enregistré. Contactez l'administrateur.")
    else:
        joueur_nom = st.selectbox("Sélectionnez votre nom", [j[1] for j in joueurs])
        joueur_id = [j[0] for j in joueurs if j[1] == joueur_nom][0]
        recettes = get_recettes_joueur(joueur_id)
        if recettes:
            for r in recettes:
                st.subheader(r[0])
                st.write("Type :", r[1])
                st.write("But :", r[2])
                st.write("Description :", r[3])
        else:
            st.info("Aucune recette attribuée pour le moment.")
