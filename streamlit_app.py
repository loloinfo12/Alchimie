import streamlit as st
import pandas as pd
import psycopg2
import psycopg2.extras
import chardet
import unicodedata
import os

CSV_FILE = "recettes_extraites.csv"

@st.cache_resource
def get_connection():
    return psycopg2.connect(st.secrets["supabase"]["url"])

if "conn" not in st.session_state:
    st.session_state.conn = get_connection()
conn = st.session_state.conn

def get_cursor():
    global conn
    try:
        conn.isolation_level
    except Exception:
        st.session_state.conn = get_connection()
        conn = st.session_state.conn
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

def init_db():
    cur = get_cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS joueurs (
            id SERIAL PRIMARY KEY,
            nom TEXT,
            niveau INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recettes (
            id SERIAL PRIMARY KEY,
            nom TEXT,
            contenu TEXT,
            but TEXT,
            ingredients TEXT,
            utilisation TEXT,
            enchantement TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS joueur_recettes (
            joueur_id INTEGER REFERENCES joueurs(id),
            recette_id INTEGER REFERENCES recettes(id),
            UNIQUE(joueur_id, recette_id)
        )
    """)
    conn.commit()
    cur.close()

def normalize_text(s):
    if not isinstance(s, str):
        s = str(s) if pd.notna(s) else ""
    return unicodedata.normalize("NFC", s).strip()

@st.cache_data
def load_csv(csv_file):
    with open(csv_file, 'rb') as f:
        raw = f.read()
        result = chardet.detect(raw)
        encoding = result['encoding'] if result['encoding'] else 'utf-8'
    df = pd.read_csv(csv_file, sep=";", encoding=encoding)
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(normalize_text)
    return df

def import_csv(silent=True):
    cur = get_cursor()
    cur.execute("SELECT COUNT(*) FROM recettes")
    count = cur.fetchone()["count"]
    cur.close()
    if count > 0:
        return
    if not os.path.exists(CSV_FILE):
        st.error(f"Fichier {CSV_FILE} introuvable.")
        return
    df = load_csv(CSV_FILE)
    cur = get_cursor()
    for _, row in df.iterrows():
        cur.execute("""
            INSERT INTO recettes (nom, contenu, but, ingredients, utilisation, enchantement)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            normalize_text(row.get("Nom recette", "")),
            normalize_text(row.get("Contenu", "")),
            normalize_text(row.get("But", "")),
            normalize_text(row.get("Ingrédients", "")),
            normalize_text(row.get("Utilisation", "")),
            normalize_text(row.get("Enchantement", "")),
        ))
    conn.commit()
    cur.close()
    if not silent:
        st.success(f"✅ CSV importé avec succès ({len(df)} recettes) !")

def get_joueurs():
    cur = get_cursor()
    cur.execute("SELECT id, nom, niveau FROM joueurs ORDER BY nom")
    rows = cur.fetchall()
    cur.close()
    return [(r["id"], r["nom"], r["niveau"]) for r in rows]

def get_recettes():
    cur = get_cursor()
    cur.execute("SELECT id, nom, but FROM recettes ORDER BY nom")
    rows = cur.fetchall()
    cur.close()
    return [(r["id"], r["nom"], r["but"]) for r in rows]

def get_recette_detail(recette_id):
    cur = get_cursor()
    cur.execute(
        "SELECT nom, contenu, but, ingredients, utilisation, enchantement FROM recettes WHERE id=%s",
        (recette_id,)
    )
    row = cur.fetchone()
    cur.close()
    if row:
        return (row["nom"], row["contenu"], row["but"], row["ingredients"], row["utilisation"], row["enchantement"])
    return None

def get_recettes_joueur(joueur_id):
    cur = get_cursor()
    cur.execute("""
        SELECT r.id, r.nom, r.but, r.ingredients, r.utilisation, r.enchantement
        FROM recettes r
        JOIN joueur_recettes jr ON r.id = jr.recette_id
        WHERE jr.joueur_id = %s
        ORDER BY r.nom
    """, (joueur_id,))
    rows = cur.fetchall()
    cur.close()
    return [(r["id"], r["nom"], r["but"], r["ingredients"], r["utilisation"], r["enchantement"]) for r in rows]

if "initialized" not in st.session_state:
    init_db()
    import_csv(silent=True)
    st.session_state["initialized"] = True

# Interface
st.sidebar.title("🔐 Connexion")
role = st.sidebar.radio("Je suis :", ["Administrateur", "Joueur"], key="role")

if role == "Administrateur":
    st.title("🛠 Interface Administrateur")
    menu = st.sidebar.selectbox("Menu Admin", ["Gérer Joueurs", "Attribuer Recettes", "Mettre à jour Recettes"], key="menu")

    if menu == "Gérer Joueurs":
        st.header("👤 Gestion des joueurs")
        with st.form("form_ajout"):
            nom = st.text_input("Nom du joueur")
            niveau = st.number_input("Niveau", 1, 20)
            submitted = st.form_submit_button("Ajouter")
            if submitted:
                if nom.strip():
                    cur = get_cursor()
                    cur.execute("INSERT INTO joueurs (nom, niveau) VALUES (%s, %s)", (nom.strip(), niveau))
                    conn.commit()
                    cur.close()
                    st.success(f"Joueur '{nom}' ajouté !")
                    st.rerun()
                else:
                    st.error("Nom du joueur vide !")

        joueurs = get_joueurs()
        if joueurs:
            st.subheader("Supprimer un joueur")
            with st.form("form_suppression"):
                joueur = st.selectbox("Choisir joueur à supprimer", joueurs, format_func=lambda x: x[1])
                submitted_suppr = st.form_submit_button("Supprimer")
                if submitted_suppr:
                    cur = get_cursor()
                    cur.execute("DELETE FROM joueur_recettes WHERE joueur_id=%s", (joueur[0],))
                    cur.execute("DELETE FROM joueurs WHERE id=%s", (joueur[0],))
                    conn.commit()
                    cur.close()
                    st.success(f"Joueur '{joueur[1]}' supprimé !")
                    st.rerun()
        else:
            st.info("Aucun joueur enregistré.")

    elif menu == "Attribuer Recettes":
        st.header("📜 Attribution des recettes")
        joueurs = get_joueurs()
        recettes = get_recettes()
        if joueurs and recettes:
            with st.form("form_attribution"):
                joueur = st.selectbox("Choisir joueur", joueurs, format_func=lambda x: x[1])
                recette = st.selectbox("Choisir recette", recettes, format_func=lambda x: x[1])
                submitted_attr = st.form_submit_button("Attribuer")

            detail = get_recette_detail(recette[0])
            if detail:
                with st.expander("📖 Aperçu de la recette"):
                    st.markdown(f"**But :** {detail[2]}")
                    st.markdown(f"**Ingrédients :** {detail[3]}")
                    st.markdown(f"**Utilisation :** {detail[4]}")
                    if detail[5]:
                        st.markdown(f"**Enchantement :** {detail[5]}")

            if submitted_attr:
                cur = get_cursor()
                try:
                    cur.execute(
                        "INSERT INTO joueur_recettes (joueur_id, recette_id) VALUES (%s, %s)",
                        (joueur[0], recette[0])
                    )
                    conn.commit()
                    st.success(f"Recette '{recette[1]}' attribuée à {joueur[1]} !")
                except psycopg2.errors.UniqueViolation:
                    conn.rollback()
                    st.warning(f"'{recette[1]}' est déjà attribuée à {joueur[1]}.")
                finally:
                    cur.close()
        else:
            st.warning("Il faut au moins un joueur et une recette.")

    elif menu == "Mettre à jour Recettes":
        st.header("🔄 Mise à jour des recettes")
        st.info(f"Source : {CSV_FILE}")
        with st.form("form_reimport"):
            submitted_reimport = st.form_submit_button("Réimporter le CSV (efface et recharge)")
            if submitted_reimport:
                cur = get_cursor()
                cur.execute("DELETE FROM joueur_recettes")
                cur.execute("DELETE FROM recettes")
                conn.commit()
                cur.close()
                load_csv.clear()
                import_csv(silent=False)
                st.rerun()

elif role == "Joueur":
    st.title("🧪 Mes Recettes Alchimiques")
    joueurs = get_joueurs()
    if not joueurs:
        st.info("Aucun joueur enregistré. Contactez l'administrateur.")
    else:
        joueur_nom = st.selectbox("Sélectionnez votre nom", [j[1] for j in joueurs], key="joueur_select")
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
