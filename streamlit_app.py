import streamlit as st
import pandas as pd
import psycopg2
import psycopg2.extras
import chardet
import unicodedata
import os
import bcrypt

CSV_FILE = "recettes_extraites.csv"

# Patch anti-None
_original_write = st.write
st.write = lambda *a, **kw: None if (len(a)==1 and a[0] is None) else _original_write(*a, **kw)

@st.cache_resource
def get_connection():
    return psycopg2.connect(st.secrets["supabase"]["url"])

def get_cursor():
    try:
        st.session_state.conn.isolation_level
    except Exception:
        st.session_state.conn = get_connection()
    return st.session_state.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

def init_db():
    cur = get_cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS joueurs (
            id SERIAL PRIMARY KEY,
            nom TEXT,
            niveau INTEGER,
            mot_de_passe TEXT
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
    # Ajouter colonne mot_de_passe si elle n'existe pas (migration)
    cur.execute("""
        ALTER TABLE joueurs ADD COLUMN IF NOT EXISTS mot_de_passe TEXT
    """)
    st.session_state.conn.commit()
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
    st.session_state.conn.commit()
    cur.close()
    if not silent:
        st.success(f"✅ CSV importé avec succès ({len(df)} recettes) !")

def get_joueurs():
    cur = get_cursor()
    cur.execute("SELECT id, nom, niveau, mot_de_passe FROM joueurs ORDER BY nom")
    rows = cur.fetchall()
    cur.close()
    return [(r["id"], r["nom"], r["niveau"], r["mot_de_passe"]) for r in rows]

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

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    if not hashed:
        return False
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def setup():
    if "conn" not in st.session_state:
        st.session_state.conn = get_connection()
    if "initialized" not in st.session_state:
        init_db()
        import_csv(silent=True)
        st.session_state["initialized"] = True
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "role" not in st.session_state:
        st.session_state.role = None
    if "joueur_id" not in st.session_state:
        st.session_state.joueur_id = None
    if "joueur_nom" not in st.session_state:
        st.session_state.joueur_nom = None

setup()

# -----------------------------
# Page de connexion
# -----------------------------
def page_connexion():
    st.title("🔐 Connexion")
    role_choix = st.radio("Je suis :", ["Joueur", "Administrateur"], key="role_choix")

    if role_choix == "Administrateur":
        with st.form("form_login_admin"):
            mdp = st.text_input("Mot de passe administrateur", type="password")
            submitted = st.form_submit_button("Se connecter")
            if submitted:
                if mdp == st.secrets["admin"]["password"]:
                    st.session_state.logged_in = True
                    st.session_state.role = "admin"
                    st.rerun()
                else:
                    st.error("Mot de passe incorrect.")

    else:
        joueurs = get_joueurs()
        if not joueurs:
            st.info("Aucun joueur enregistré. Contactez l'administrateur.")
        else:
            with st.form("form_login_joueur"):
                joueur_choix = st.selectbox("Votre nom", joueurs, format_func=lambda x: x[1])
                mdp = st.text_input("Mot de passe", type="password")
                submitted = st.form_submit_button("Se connecter")
                if submitted:
                    if check_password(mdp, joueur_choix[3]):
                        st.session_state.logged_in = True
                        st.session_state.role = "joueur"
                        st.session_state.joueur_id = joueur_choix[0]
                        st.session_state.joueur_nom = joueur_choix[1]
                        st.rerun()
                    else:
                        st.error("Mot de passe incorrect.")

# -----------------------------
# Page Admin
# -----------------------------
def page_admin():
    st.sidebar.title("🛠 Admin")
    if st.sidebar.button("Se déconnecter"):
        st.session_state.logged_in = False
        st.session_state.role = None
        st.rerun()

    menu = st.sidebar.selectbox("Menu", ["Gérer Joueurs", "Attribuer Recettes", "Mettre à jour Recettes"], key="menu")

    if menu == "Gérer Joueurs":
        st.title("👤 Gestion des joueurs")
        with st.form("form_ajout"):
            nom = st.text_input("Nom du joueur")
            niveau = st.number_input("Niveau", 1, 20)
            mdp = st.text_input("Mot de passe du joueur", type="password")
            submitted = st.form_submit_button("Ajouter")
            if submitted:
                if nom.strip() and mdp.strip():
                    cur = get_cursor()
                    cur.execute(
                        "INSERT INTO joueurs (nom, niveau, mot_de_passe) VALUES (%s, %s, %s)",
                        (nom.strip(), niveau, hash_password(mdp))
                    )
                    st.session_state.conn.commit()
                    cur.close()
                    st.success(f"Joueur '{nom}' ajouté !")
                    st.rerun()
                else:
                    st.error("Nom et mot de passe obligatoires.")

        joueurs = get_joueurs()
        if joueurs:
            st.subheader("Modifier le mot de passe d'un joueur")
            with st.form("form_mdp"):
                joueur = st.selectbox("Choisir joueur", joueurs, format_func=lambda x: x[1])
                nouveau_mdp = st.text_input("Nouveau mot de passe", type="password")
                submitted_mdp = st.form_submit_button("Modifier")
                if submitted_mdp:
                    if nouveau_mdp.strip():
                        cur = get_cursor()
                        cur.execute(
                            "UPDATE joueurs SET mot_de_passe=%s WHERE id=%s",
                            (hash_password(nouveau_mdp), joueur[0])
                        )
                        st.session_state.conn.commit()
                        cur.close()
                        st.success(f"Mot de passe de '{joueur[1]}' modifié !")
                    else:
                        st.error("Mot de passe vide.")

            st.subheader("Supprimer un joueur")
            with st.form("form_suppression"):
                joueur_suppr = st.selectbox("Choisir joueur à supprimer", joueurs, format_func=lambda x: x[1])
                submitted_suppr = st.form_submit_button("Supprimer")
                if submitted_suppr:
                    cur = get_cursor()
                    cur.execute("DELETE FROM joueur_recettes WHERE joueur_id=%s", (joueur_suppr[0],))
                    cur.execute("DELETE FROM joueurs WHERE id=%s", (joueur_suppr[0],))
                    st.session_state.conn.commit()
                    cur.close()
                    st.success(f"Joueur '{joueur_suppr[1]}' supprimé !")
                    st.rerun()
        else:
            st.info("Aucun joueur enregistré.")

    elif menu == "Attribuer Recettes":
        st.title("📜 Attribution des recettes")
        joueurs = get_joueurs()
        recettes = get_recettes()
        if joueurs and recettes:
            joueur = st.selectbox("Choisir joueur", joueurs, format_func=lambda x: x[1])
            recette = st.selectbox("Choisir recette", recettes, format_func=lambda x: x[1])

            detail = get_recette_detail(recette[0])
            if detail:
                with st.expander("📖 Aperçu de la recette", expanded=True):
                    st.markdown(f"**But :** {detail[2]}")
                    st.markdown(f"**Ingrédients :** {detail[3]}")
                    st.markdown(f"**Utilisation :** {detail[4]}")
                    if detail[5]:
                        st.markdown(f"**Enchantement :** {detail[5]}")

            if st.button("Attribuer"):
                cur = get_cursor()
                try:
                    cur.execute(
                        "INSERT INTO joueur_recettes (joueur_id, recette_id) VALUES (%s, %s)",
                        (joueur[0], recette[0])
                    )
                    st.session_state.conn.commit()
                    st.success(f"Recette '{recette[1]}' attribuée à {joueur[1]} !")
                except psycopg2.errors.UniqueViolation:
                    st.session_state.conn.rollback()
                    st.warning(f"'{recette[1]}' est déjà attribuée à {joueur[1]}.")
                finally:
                    cur.close()
        else:
            st.warning("Il faut au moins un joueur et une recette.")

    elif menu == "Mettre à jour Recettes":
        st.title("🔄 Mise à jour des recettes")
        st.info(f"Source : {CSV_FILE}")
        with st.form("form_reimport"):
            submitted_reimport = st.form_submit_button("Réimporter le CSV (efface et recharge)")
            if submitted_reimport:
                cur = get_cursor()
                cur.execute("DELETE FROM joueur_recettes")
                cur.execute("DELETE FROM recettes")
                st.session_state.conn.commit()
                cur.close()
                load_csv.clear()
                import_csv(silent=False)
                st.rerun()

# -----------------------------
# Page Joueur
# -----------------------------
def page_joueur():
    st.sidebar.title(f"👤 {st.session_state.joueur_nom}")
    if st.sidebar.button("Se déconnecter"):
        st.session_state.logged_in = False
        st.session_state.role = None
        st.session_state.joueur_id = None
        st.session_state.joueur_nom = None
        st.rerun()

    st.title("🧪 Mes Recettes Alchimiques")
    recettes = get_recettes_joueur(st.session_state.joueur_id)
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

# -----------------------------
# Routage
# -----------------------------
if not st.session_state.logged_in:
    page_connexion()
elif st.session_state.role == "admin":
    page_admin()
elif st.session_state.role == "joueur":
    page_joueur()
