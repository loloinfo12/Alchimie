import streamlit as st
import sqlite3
import pandas as pd
import os

DB_NAME = "database.db"
CSV_FILE = "Recettes alchimiques.csv"

# -----------------------------
# Connexion
# -----------------------------
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = conn.cursor()

# -----------------------------
# Initialisation
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

    # Table relation
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS joueur_recettes (
        joueur_id INTEGER,
        recette_id INTEGER,
        FOREIGN KEY(joueur_id) REFERENCES joueurs(id),
        FOREIGN KEY(recette_id) REFERENCES recettes(id)
    )
    """)

    conn.commit()


def import_csv():
    # Import seulement si la table n'existe pas encore
    tables = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='recettes';"
    ).fetchone()

    if not tables:
        df = pd.read_csv(CSV_FILE, sep=";", encoding="latin1")
        df.to_sql("recettes", conn, index=False)
        conn.commit()


init_db()
import_csv()

# -----------------------------
# Interface
# -----------------------------

st.title("🔮 Alchimie - Gestion des Recettes")

menu = st.sidebar.selectbox(
    "Menu",
    ["Ajouter Joueur", "Attribuer Recette", "Voir Fiches"]
)

# -----------------------------
# Ajouter joueur
# -----------------------------
if menu == "Ajouter Joueur":

    st.header("👤 Nouveau Joueur")
    nom = st.text_input("Nom du joueur")
    niveau = st.number_input("Niveau", 1, 20)

    if st.button("Ajouter"):
        cursor.execute(
            "INSERT INTO joueurs (nom, niveau) VALUES (?, ?)",
            (nom, niveau)
        )
        conn.commit()
        st.success("Joueur ajouté !")


# -----------------------------
# Attribution
# -----------------------------
elif menu == "Attribuer Recette":

    st.header("📜 Attribution")

    joueurs = cursor.execute("SELECT id, nom FROM joueurs").fetchall()
    recettes = cursor.execute(
        "SELECT rowid, `Nom recette` FROM recettes"
    ).fetchall()

    if joueurs and recettes:

        joueur = st.selectbox("Choisir joueur", joueurs, format_func=lambda x: x[1])
        recette = st.selectbox("Choisir recette", recettes, format_func=lambda x: x[1])

        if st.button("Attribuer"):
            cursor.execute(
                "INSERT INTO joueur_recettes (joueur_id, recette_id) VALUES (?, ?)",
                (joueur[0], recette[0])
            )
            conn.commit()
            st.success("Recette attribuée !")

    else:
        st.warning("Ajoute au moins un joueur.")


# -----------------------------
# Voir fiches
# -----------------------------
elif menu == "Voir Fiches":

    st.header("📖 Fiches Joueurs")

    joueurs = cursor.execute("SELECT id, nom, niveau FROM joueurs").fetchall()

    for joueur in joueurs:

        st.subheader(f"{joueur[1]} (Niveau {joueur[2]})")

        recettes = cursor.execute("""
            SELECT r.`Nom recette`
            FROM recettes r
            JOIN joueur_recettes jr
            ON r.rowid = jr.recette_id
            WHERE jr.joueur_id = ?
        """, (joueur[0],)).fetchall()

        if recettes:
            for r in recettes:
                st.write("🔹", r[0])
        else:
            st.write("Aucune recette connue.")
