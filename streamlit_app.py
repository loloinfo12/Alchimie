import streamlit as st
import pandas as pd
import psycopg2
import psycopg2.extras
import chardet
import unicodedata
import os
import bcrypt

CSV_FILE = "recettes_extraites.csv"
CSV_COMPOSANTS = "Composants_globaux.csv"

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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS composants (
            id SERIAL PRIMARY KEY,
            nom TEXT UNIQUE,
            type TEXT,
            jet_connaissance TEXT,
            information TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recette_composant (
            recette_id INTEGER REFERENCES recettes(id),
            composant_id INTEGER REFERENCES composants(id),
            PRIMARY KEY (recette_id, composant_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS joueur_composants (
            joueur_id INTEGER REFERENCES joueurs(id),
            composant_id INTEGER REFERENCES composants(id),
            recette_id INTEGER REFERENCES recettes(id),
            quantite INTEGER DEFAULT 0,
            PRIMARY KEY (joueur_id, composant_id, recette_id)
        )
    """)
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
        st.success(f"✅ CSV recettes importé avec succès ({len(df)} recettes) !")

def import_composants(silent=True):
    cur = get_cursor()
    cur.execute("SELECT COUNT(*) FROM composants")
    count = cur.fetchone()["count"]
    cur.close()
    if count > 0:
        return
    if not os.path.exists(CSV_COMPOSANTS):
        st.warning(f"Fichier {CSV_COMPOSANTS} introuvable, composants non importés.")
        return
    df = load_csv(CSV_COMPOSANTS)
    cur = get_cursor()
    for _, row in df.iterrows():
        nom = normalize_text(row.get("Composants", ""))
        if not nom:
            continue
        cur.execute("""
            INSERT INTO composants (nom, type, jet_connaissance, information)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (nom) DO NOTHING
        """, (
            nom,
            normalize_text(row.get("Type", "")),
            normalize_text(row.get("Jet de connaissance", "")),
            normalize_text(row.get("information", "")),
        ))
    st.session_state.conn.commit()
    cur.close()
    if not silent:
        st.success(f"✅ Composants importés avec succès ({len(df)} composants) !")

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

def get_composants():
    cur = get_cursor()
    cur.execute("SELECT id, nom, type FROM composants ORDER BY nom")
    rows = cur.fetchall()
    cur.close()
    return [(r["id"], r["nom"], r["type"]) for r in rows]

def get_composant_principal(recette_id):
    cur = get_cursor()
    cur.execute("""
        SELECT c.id, c.nom, c.type, c.jet_connaissance, c.information
        FROM composants c
        JOIN recette_composant rc ON c.id = rc.composant_id
        WHERE rc.recette_id = %s
        LIMIT 1
    """, (recette_id,))
    row = cur.fetchone()
    cur.close()
    if row:
        return (row["id"], row["nom"], row["type"], row["jet_connaissance"], row["information"])
    return None

def set_composant_principal(recette_id, composant_id):
    cur = get_cursor()
    cur.execute("DELETE FROM recette_composant WHERE recette_id=%s", (recette_id,))
    cur.execute(
        "INSERT INTO recette_composant (recette_id, composant_id) VALUES (%s, %s)",
        (recette_id, composant_id)
    )
    st.session_state.conn.commit()
    cur.close()

def get_quantite_composant(joueur_id, composant_id, recette_id):
    cur = get_cursor()
    cur.execute("""
        SELECT quantite FROM joueur_composants
        WHERE joueur_id=%s AND composant_id=%s AND recette_id=%s
    """, (joueur_id, composant_id, recette_id))
    row = cur.fetchone()
    cur.close()
    return row["quantite"] if row else 0

def set_quantite_composant(joueur_id, composant_id, recette_id, quantite):
    cur = get_cursor()
    cur.execute("""
        INSERT INTO joueur_composants (joueur_id, composant_id, recette_id, quantite)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (joueur_id, composant_id, recette_id)
        DO UPDATE SET quantite = EXCLUDED.quantite
    """, (joueur_id, composant_id, recette_id, quantite))
    st.session_state.conn.commit()
    cur.close()

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
        import_composants(silent=True)
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

    menu = st.sidebar.selectbox(
        "Menu",
        ["Gérer Joueurs", "Attribuer Recettes", "Gérer Composants", "Mettre à jour Recettes"],
        key="menu"
    )

    # ── Gérer Joueurs ──────────────────────────────────────────
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
                    cur.execute("DELETE FROM joueur_composants WHERE joueur_id=%s", (joueur_suppr[0],))
                    cur.execute("DELETE FROM joueur_recettes WHERE joueur_id=%s", (joueur_suppr[0],))
                    cur.execute("DELETE FROM joueurs WHERE id=%s", (joueur_suppr[0],))
                    st.session_state.conn.commit()
                    cur.close()
                    st.success(f"Joueur '{joueur_suppr[1]}' supprimé !")
                    st.rerun()
        else:
            st.info("Aucun joueur enregistré.")

    # ── Attribuer Recettes ─────────────────────────────────────
    elif menu == "Attribuer Recettes":
        st.title("📜 Attribution des recettes")
        joueurs = get_joueurs()
        recettes = get_recettes()
        if joueurs and recettes:
            joueur = st.selectbox("Choisir joueur", joueurs, format_func=lambda x: x[1])
            recette = st.selectbox("Choisir recette", recettes, format_func=lambda x: x[1])

            detail = get_recette_detail(recette[0])
            composant = get_composant_principal(recette[0])
            if detail:
                with st.expander("📖 Aperçu de la recette", expanded=True):
                    st.markdown(f"**But :** {detail[2]}")
                    st.markdown(f"**Ingrédients :** {detail[3]}")
                    st.markdown(f"**Utilisation :** {detail[4]}")
                    if detail[5]:
                        st.markdown(f"**Enchantement :** {detail[5]}")
                    if composant:
                        st.markdown(f"**🧪 Composant principal :** {composant[1]} *(type : {composant[2]})*")
                    else:
                        st.caption("⚠️ Aucun composant principal défini pour cette recette.")

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

    # ── Gérer Composants ───────────────────────────────────────
    elif menu == "Gérer Composants":
        st.title("🧪 Gestion des composants principaux")

        tab1, tab2, tab3 = st.tabs(["🔗 Associer à une recette", "➕ Ajouter un composant", "📋 Vue d'ensemble"])

        composants = get_composants()
        recettes = get_recettes()

        # ── Tab 1 : Associer composant à recette ──
        with tab1:
            if not recettes:
                st.warning("Aucune recette disponible.")
            elif not composants:
                st.warning("Aucun composant disponible. Ajoutez-en via l'onglet '➕ Ajouter un composant'.")
            else:
                st.markdown("Associez un **composant principal** à chaque recette.")

                recette = st.selectbox(
                    "Choisir une recette",
                    recettes,
                    format_func=lambda x: x[1],
                    key="sel_recette_comp"
                )

                detail = get_recette_detail(recette[0])
                if detail:
                    with st.expander("📖 Détail de la recette"):
                        st.markdown(f"**But :** {detail[2]}")
                        st.markdown(f"**Ingrédients :** {detail[3]}")
                        if detail[4]:
                            st.markdown(f"**Utilisation :** {detail[4]}")
                        if detail[5]:
                            st.markdown(f"**Enchantement :** {detail[5]}")
                        
                composant_actuel = get_composant_principal(recette[0])
                if composant_actuel:
                    st.info(f"Composant principal actuel : **{composant_actuel[1]}** *(type : {composant_actuel[2]})*")
                else:
                    st.caption("Aucun composant principal défini pour cette recette.")

                types = sorted(set(c[2] for c in composants))
                type_filtre = st.selectbox("Filtrer par type", ["Tous"] + types, key="filtre_type")
                composants_filtres = composants if type_filtre == "Tous" else [c for c in composants if c[2] == type_filtre]

                nouveau_composant = st.selectbox(
                    "Choisir le composant principal",
                    composants_filtres,
                    format_func=lambda x: f"{x[1]} ({x[2]})",
                    key="sel_composant"
                )

                if st.button("💾 Enregistrer le composant principal"):
                    set_composant_principal(recette[0], nouveau_composant[0])
                    st.success(f"Composant principal de '{recette[1]}' défini : **{nouveau_composant[1]}**")
                    st.rerun()

        # ── Tab 2 : Ajouter un composant manuellement ──
        with tab2:
            st.subheader("Ajouter un composant à la base")
            TYPES_COMPOSANTS = [
                "Animaux et créatures et morceaux",
                "Plantes, champignons, fruits, baies",
                "Sels, Poudres et minéraux",
                "Autre"
            ]
            with st.form("form_ajout_composant"):
                new_nom = st.text_input("Nom du composant *")
                new_type = st.selectbox("Type *", TYPES_COMPOSANTS)
                new_jet = st.text_input("Jet de connaissance (optionnel)")
                new_info = st.text_area("Information (optionnel)")
                submitted_comp = st.form_submit_button("➕ Ajouter")
                if submitted_comp:
                    if new_nom.strip():
                        cur = get_cursor()
                        try:
                            cur.execute("""
                                INSERT INTO composants (nom, type, jet_connaissance, information)
                                VALUES (%s, %s, %s, %s)
                            """, (
                                normalize_text(new_nom),
                                new_type,
                                normalize_text(new_jet),
                                normalize_text(new_info),
                            ))
                            st.session_state.conn.commit()
                            st.success(f"Composant **{new_nom}** ajouté avec succès !")
                            st.rerun()
                        except psycopg2.errors.UniqueViolation:
                            st.session_state.conn.rollback()
                            st.error(f"Un composant nommé '{new_nom}' existe déjà.")
                        finally:
                            cur.close()
                    else:
                        st.error("Le nom est obligatoire.")

            # Liste des composants ajoutés manuellement (ceux hors CSV)
            st.divider()
            st.subheader("🗑️ Supprimer un composant")
            if composants:
                with st.form("form_suppr_composant"):
                    comp_suppr = st.selectbox(
                        "Choisir un composant à supprimer",
                        composants,
                        format_func=lambda x: f"{x[1]} ({x[2]})"
                    )
                    submitted_suppr_c = st.form_submit_button("Supprimer")
                    if submitted_suppr_c:
                        cur = get_cursor()
                        cur.execute("DELETE FROM joueur_composants WHERE composant_id=%s", (comp_suppr[0],))
                        cur.execute("DELETE FROM recette_composant WHERE composant_id=%s", (comp_suppr[0],))
                        cur.execute("DELETE FROM composants WHERE id=%s", (comp_suppr[0],))
                        st.session_state.conn.commit()
                        cur.close()
                        st.success(f"Composant '{comp_suppr[1]}' supprimé.")
                        st.rerun()
            else:
                st.info("Aucun composant disponible.")

        # ── Tab 3 : Vue d'ensemble ──
        with tab3:
            cur = get_cursor()
            cur.execute("""
                SELECT r.nom AS recette, c.nom AS composant, c.type AS type
                FROM recettes r
                LEFT JOIN recette_composant rc ON r.id = rc.recette_id
                LEFT JOIN composants c ON rc.composant_id = c.id
                ORDER BY r.nom
            """)
            rows = cur.fetchall()
            cur.close()
            if rows:
                df_view = pd.DataFrame([dict(r) for r in rows])
                df_view.columns = ["Recette", "Composant principal", "Type"]
                df_view["Composant principal"] = df_view["Composant principal"].fillna("⚠️ Non défini")
                df_view["Type"] = df_view["Type"].fillna("")
                st.dataframe(df_view, use_container_width=True, hide_index=True)
            else:
                st.info("Aucune recette trouvée.")

    # ── Mettre à jour Recettes ─────────────────────────────────
    elif menu == "Mettre à jour Recettes":
        st.title("🔄 Mise à jour des recettes")
        st.info(f"Source recettes : {CSV_FILE}  |  Source composants : {CSV_COMPOSANTS}")

        col1, col2 = st.columns(2)
        with col1:
            with st.form("form_reimport_recettes"):
                submitted_r = st.form_submit_button("♻️ Réimporter les recettes")
                if submitted_r:
                    cur = get_cursor()
                    cur.execute("DELETE FROM joueur_composants")
                    cur.execute("DELETE FROM recette_composant")
                    cur.execute("DELETE FROM joueur_recettes")
                    cur.execute("DELETE FROM recettes")
                    st.session_state.conn.commit()
                    cur.close()
                    load_csv.clear()
                    import_csv(silent=False)
                    st.rerun()
        with col2:
            with st.form("form_reimport_composants"):
                submitted_c = st.form_submit_button("♻️ Réimporter les composants")
                if submitted_c:
                    cur = get_cursor()
                    cur.execute("DELETE FROM joueur_composants")
                    cur.execute("DELETE FROM recette_composant")
                    cur.execute("DELETE FROM composants")
                    st.session_state.conn.commit()
                    cur.close()
                    load_csv.clear()
                    import_composants(silent=False)
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

    if not recettes:
        st.info("Aucune recette attribuée pour le moment.")
        return

    st.markdown(f"**{len(recettes)} recette(s) disponible(s)**")

    for r in recettes:
        recette_id = r[0]
        composant = get_composant_principal(recette_id)
        quantite_actuelle = 0
        if composant:
            quantite_actuelle = get_quantite_composant(
                st.session_state.joueur_id, composant[0], recette_id
            )

        label = f"📜 {r[1]}"
        if composant:
            label += f"  —  🧪 {composant[1]} : {quantite_actuelle}"

        with st.expander(label):
            if r[2]:
                st.markdown(f"**🎯 But :** {r[2]}")
            if r[3]:
                st.markdown(f"**🌿 Ingrédients :** {r[3]}")
            if r[4]:
                st.markdown(f"**⚗️ Utilisation :** {r[4]}")
            if r[5]:
                st.markdown(f"**✨ Enchantement :** {r[5]}")

            if composant:
                st.divider()
                st.markdown(f"**🧪 Composant principal : {composant[1]}**")
                st.caption(f"Type : {composant[2]}" + (f"  |  Jet : {composant[3]}" if composant[3] else ""))
                if composant[4]:
                    st.caption(f"ℹ️ {composant[4]}")

                col1, col2, col3 = st.columns([1, 2, 1])
                with col1:
                    if st.button("➖", key=f"minus_{recette_id}"):
                        nouvelle_qte = max(0, quantite_actuelle - 1)
                        set_quantite_composant(
                            st.session_state.joueur_id, composant[0], recette_id, nouvelle_qte
                        )
                        st.rerun()
                with col2:
                    st.markdown(
                        f"<div style='text-align:center; font-size:1.4em; font-weight:bold'>{quantite_actuelle}</div>",
                        unsafe_allow_html=True
                    )
                with col3:
                    if st.button("➕", key=f"plus_{recette_id}"):
                        set_quantite_composant(
                            st.session_state.joueur_id, composant[0], recette_id, quantite_actuelle + 1
                        )
                        st.rerun()
            else:
                st.caption("⚠️ Aucun composant principal défini pour cette recette.")

# -----------------------------
# Routage
# -----------------------------
if not st.session_state.logged_in:
    page_connexion()
elif st.session_state.role == "admin":
    page_admin()
elif st.session_state.role == "joueur":
    page_joueur()
