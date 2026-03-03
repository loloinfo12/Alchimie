import streamlit as st
import sqlite3
import pandas as pd
import chardet
import unicodedata
import os

# -----------------------------
# Config fichiers
# -----------------------------
DB_NAME = "database.db"
CSV_FILE = "recettes_extraites.csv"

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
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT,
        contenu TEXT,
        but TEXT,
        ingredients TEXT,
        utilisation TEXT,
        enchantement TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS joueur_recettes (
        joueur_id INTEGER,
        recette_id INTEGER,
        FOREIGN KEY(joueur_id) REFERENCES joueurs(id),
        FOREIGN KEY(recette_id) REFERENCES recettes(id)
    )
    """)
    conn.commit()

init_db()

# -----------------------------
# Normalisation texte
# -----------------------------
def normalize_text(s):
    if not isinstance(s, str):
        s = str(s) if pd.notna(s) else ""
    return unicodedata.normalize("NFC", s)

# -----------------------------
# Chargement CSV
# -----------------------------
@st.cache_data
def load_csv(csv_file):
    with open(csv_file, 'rb') as f:
        raw = f.read()
        result = chardet.detect(raw)
        encoding = result['encoding'] if result['encoding'] else 'utf-8'

    df = pd.read_csv(csv_file, sep=";", encoding=encoding)

    # Normaliser toutes les colonnes texte
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(normalize_text)

    return df

# -----------------------------
# Import CSV vers SQLite
# -----------------------------
def import_csv():
    count = cursor.execute("SELECT COUNT(*) FROM recettes").fetchone()[0]
    if count > 0:
        return  # déjà importé

    if not os.path.exists(CSV_FILE):
        st.error(f"Fichier {CSV_FILE} introuvable.")
        return

    df = load_csv(CSV_FILE)

    # Mapping colonnes CSV -> colonnes DB
    col_map = {
        "Nom recette": "nom",
        "Contenu": "contenu",
        "But": "but",
        "Ingrédients": "ingredients",
        "Utilisation": "utilisation",
        "Enchantement": "enchantement",
    }

    for _, row in df.iterrows():
        cursor.execute("""
            INSERT INTO recettes (nom, contenu, but, ingredients, utilisation, enchantement)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            normalize_text(row.get("Nom recette", "")),
            normalize_text(row.get("Contenu", "")),
            normalize_text(row.get("But", "")),
            normalize_text(row.get("Ingrédients", "")),
            normalize_text(row.get("Utilisation", "")),
            normalize_text(row.get("Enchantement", "")),
        ))
    conn.commit()
    st.success(f"✅ CSV importé avec succès ({len(df)} recettes) !")

# -----------------------------
# Fonctions utilitaires
# -----------------------------
def get_joueurs():
    return cursor.execute("SELECT id, nom, niveau FROM joueurs").fetchall()

def get_recettes():
    return cursor.execute("SELECT id, nom, but FROM recettes").fetchall()

def get_recette_detail(recette_id):
    return cursor.execute(
        "SELECT nom, contenu, but, ingredients, utilisation, enchantement FROM recettes WHERE id=?",
        (recette_id,)
    ).fetchone()

def get_recettes_joueur(joueur_id):
    return cursor.execute("""
        SELECT r.id, r.nom, r.but, r.ingredients, r.utilisation, r.enchantement
        FROM recettes r
        JOIN joueur_recettes jr ON r.id = jr.recette_id
        WHERE jr.joueur_id = ?
    """, (joueur_id,)).fetchall()

# -----------------------------
# Import initial CSV
# -----------------------------
import_csv()

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
                cursor.execute("INSERT INTO joueurs (nom, niveau) VALUES (?, ?)", (nom.strip(), niveau))
                conn.commit()
                st.success(f"Joueur '{nom}' ajouté !")
            else:
                st.error("Nom du joueur vide !")

        joueurs = get_joueurs()
        if joueurs:
            st.subheader("Supprimer un joueur")
            joueur = st.selectbox("Choisir joueur à supprimer", joueurs, format_func=lambda x: x[1])
            if st.button("Supprimer"):
                cursor.execute("DELETE FROM joueur_recettes WHERE joueur_id=?", (joueur[0],))
                cursor.execute("DELETE FROM joueurs WHERE id=?", (joueur[0],))
                conn.commit()
                st.success(f"Joueur '{joueur[1]}' supprimé !")
        else:
            st.info("Aucun joueur enregistré.")

    elif menu == "Attribuer Recettes":
        st.header("📜 Attribution des recettes")
        joueurs = get_joueurs()
        recettes = get_recettes()
        if joueurs and recettes:
            joueur = st.selectbox("Choisir joueur", joueurs, format_func=lambda x: x[1])
            recette = st.selectbox("Choisir recette", recettes, format_func=lambda x: x[1])

            # Afficher détail de la recette sélectionnée
            detail = get_recette_detail(recette[0])
            if detail:
                with st.expander("📖 Aperçu de la recette"):
                    st.markdown(f"**But :** {detail[2]}")
                    st.markdown(f"**Ingrédients :** {detail[3]}")
                    st.markdown(f"**Utilisation :** {detail[4]}")
                    if detail[5]:
                        st.markdown(f"**Enchantement :** {detail[5]}")

            if st.button("Attribuer"):
                # Vérifier si déjà attribuée
                exists = cursor.execute(
                    "SELECT 1 FROM joueur_recettes WHERE joueur_id=? AND recette_id=?",
                    (joueur[0], recette[0])
                ).fetchone()
                if exists:
                    st.warning(f"'{recette[1]}' est déjà attribuée à {joueur[1]}.")
                else:
                    cursor.execute(
                        "INSERT INTO joueur_recettes (joueur_id, recette_id) VALUES (?, ?)",
                        (joueur[0], recette[0])
                    )
                    conn.commit()
                    st.success(f"Recette '{recette[1]}' attribuée à {joueur[1]} !")
        else:
            st.warning("Il faut au moins un joueur et une recette.")

    elif menu == "Mettre à jour Recettes":
        st.header("🔄 Mise à jour des recettes depuis le CSV")
        st.info(f"Source : `{CSV_FILE}`")
        if st.button("Réimporter le CSV (efface et recharge)"):
            cursor.execute("DELETE FROM recettes")
            cursor.execute("DELETE FROM joueur_recettes")
            conn.commit()
            load_csv.clear()
            import_csv()

# -----------------------------
# Joueur
# -----------------------------
elif role == "Joueur":
    st.title("🧪 Mes Recettes Alchimiques")
    joueurs = get_joueurs()
    if not joueurs:
        st.info("Aucun joueur enregistré. Contactez l'administrateur.")
    else:
        joueur_nom = st.selectbox("Sélectionnez votre nom", [j[1] for j in joueurs])
        joueur_id = next(j[0] for j in joueurs if j[1] == joueur_nom)
        recettes = get_recettes_joueur(joueur_id)

        if recettes:
            st.markdown(f"**{len(recettes)} recette(s) disponible(s)**")
            for r in recettes:
                with st.expander(f"📜 {r[1]}"):
                    if r[2]:
                        st.markdown(f"**🎯 But :** {r[2]}")
                    if r[3]:
                        st.markdown(f"**🌿 Ingrédients :** {r[3]}")
                    if r[4]:
                        st.markdown(f"**⚗️ Utilisation :** {r[4]}")
                    if r[5]:
                        st.markdown(f"**✨ Enchantement :** {r[5]}")
        else:
            st.info("Aucune recette attribuée pour le moment.")
