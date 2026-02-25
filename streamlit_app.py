import streamlit as st
import sqlite3
import pandas as pd
import pdfplumber
import os

# -----------------------------
# Config fichiers
# -----------------------------
DB_NAME = "database.db"
CSV_FILE = "Recettes alchimiques.csv"
PDF_FILE = "recettes alchimiques.pdf"

# -----------------------------
# Connexion DB
# -----------------------------
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = conn.cursor()

# -----------------------------
# Initialisation DB
# -----------------------------
def init_db():
    # Table joueurs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS joueurs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT,
        niveau INTEGER
    )
    """)
    
    # Table recettes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recettes (
        rowid INTEGER PRIMARY KEY AUTOINCREMENT,
        `Nom recette` TEXT,
        Type TEXT,
        But TEXT
    )
    """)
    
    # Table relation
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS joueur_recettes (
        joueur_id INTEGER,
        recette_id INTEGER,
        FOREIGN KEY(joueur_id) REFERENCES joueurs(id),
        FOREIGN KEY(recette_id) REFERENCES recettes(rowid)
    )
    """)
    
    conn.commit()

# -----------------------------
# Vérifier colonne description
# -----------------------------
def ensure_description_column():
    cursor.execute("PRAGMA table_info(recettes)")
    cols = [col[1] for col in cursor.fetchall()]
    if "description" not in cols:
        cursor.execute("ALTER TABLE recettes ADD COLUMN description TEXT")
        conn.commit()

# -----------------------------
# Import CSV si table vide
# -----------------------------
def import_csv():
    tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='recettes';").fetchone()
    if tables:
        existing = cursor.execute("SELECT COUNT(*) FROM recettes").fetchone()[0]
        if existing > 0:
            return  # déjà importé
    
    df = pd.read_csv(CSV_FILE, sep=";", encoding="latin1")
    df.to_sql("recettes", conn, if_exists="append", index=False)
    conn.commit()

# -----------------------------
# Extraire descriptions PDF
# -----------------------------
def extract_descriptions():
    ensure_description_column()  # Vérifie/crée la colonne
    
    df_recettes = pd.read_sql("SELECT `Nom recette` FROM recettes", conn)
    
    if not os.path.exists(PDF_FILE):
        st.warning(f"PDF {PDF_FILE} non trouvé, les descriptions ne seront pas extraites.")
        return
    
    pdf_text = ""
    with pdfplumber.open(PDF_FILE) as pdf:
        for page in pdf.pages:
            pdf_text += page.extract_text() + "\n"
    
    descriptions = {}
    for nom in df_recettes["Nom recette"]:
        start_idx = pdf_text.find(nom)
        if start_idx != -1:
            rest_text = pdf_text[start_idx + len(nom):]
            next_idx = len(rest_text)
            for other_nom in df_recettes["Nom recette"]:
                if other_nom != nom:
                    idx = rest_text.find(other_nom)
                    if idx != -1 and idx < next_idx:
                        next_idx = idx
            desc = rest_text[:next_idx].strip().replace("\n", " ")
            descriptions[nom] = desc
        else:
            descriptions[nom] = ""
    
    for nom, desc in descriptions.items():
        cursor.execute("UPDATE recettes SET description=? WHERE `Nom recette`=?", (desc, nom))
    conn.commit()

# -----------------------------
# Initialisation
# -----------------------------
init_db()
import_csv()
extract_descriptions()

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
# Interface Streamlit
# -----------------------------
st.sidebar.title("🔐 Connexion")
role = st.sidebar.radio("Je suis :", ["Administrateur", "Joueur"])

# -----------------------------
# Interface Administrateur
# -----------------------------
if role == "Administrateur":
    st.title("🛠 Interface Administrateur")
    menu = st.sidebar.selectbox("Menu Admin", ["Gérer Joueurs", "Attribuer Recettes"])
    
    if menu == "Gérer Joueurs":
        st.header("👤 Gestion des joueurs")
        
        # Ajouter
        st.subheader("Ajouter un joueur")
        nom = st.text_input("Nom du joueur")
        niveau = st.number_input("Niveau", 1, 20)
        if st.button("Ajouter"):
            if nom.strip():
                cursor.execute("INSERT INTO joueurs (nom, niveau) VALUES (?, ?)", (nom, niveau))
                conn.commit()
                st.success("Joueur ajouté !")
            else:
                st.error("Nom du joueur vide !")
        
        # Supprimer
        st.subheader("Supprimer un joueur")
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
                cursor.execute("""
                    INSERT OR IGNORE INTO joueur_recettes (joueur_id, recette_id) VALUES (?, ?)
                """, (joueur[0], recette[0]))
                conn.commit()
                st.success(f"Recette '{recette[1]}' attribuée à {joueur[1]} !")
        else:
            st.warning("Il faut au moins un joueur et une recette.")

# -----------------------------
# Interface Joueur
# -----------------------------
elif role == "Joueur":
    st.title("🧪 Mes Recettes")
    
    joueurs = get_joueurs()
    if not joueurs:
        st.info("Aucun joueur enregistré. Contactez l'administrateur.")
    else:
        joueur_nom = st.selectbox("Sélectionnez votre nom", [j[1] for j in joueurs])
        joueur_id = [j[0] for j in joueurs if j[1]==joueur_nom][0]
        
        recettes = get_recettes_joueur(joueur_id)
        if recettes:
            for r in recettes:
                st.subheader(r[0])
                st.write("Type :", r[1])
                st.write("But :", r[2])
                st.write("Description :", r[3])
        else:
            st.info("Aucune recette attribuée pour le moment.")
