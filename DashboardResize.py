import streamlit as st
import streamlit_antd_components as sac
import pandas as pd

from utils import charger_contenu_xml, parser_xml
from outil1_resize import recuperer_dashboards_avec_tailles, modifier_tableaux_de_bord, init_df_resize
from outil2_filtres import MODES_LABELS, recuperer_filtres, init_df_filtres, appliquer_modifications_filtres
from outil3_connexion import (
    recuperer_catalogues, remplacer_catalogue,
    recuperer_tables_sql, init_df_tables, remplacer_tables,
)


# ═══════════════════════════════════════════════════════════════
# UI PRINCIPALE
# ═══════════════════════════════════════════════════════════════

def main():
    st.title("🧰 Boîte à outils Tableau")

    # Upload unique partagé entre les onglets
    xml_file = st.file_uploader("Uploader le fichier .twb ou .twbx", type=["twb", "twbx"])

    if xml_file is None:
        return

    try:
        xml_content = charger_contenu_xml(xml_file)
        parser_xml(xml_content)  # validation
    except ValueError as e:
        st.error(f"❌ Impossible de lire le fichier : {e}")
        return

    # Réinitialiser si le fichier change
    if st.session_state.get("fichier_actuel") != xml_file.name:
        for key in ["df_resize", "df_filtres", "filtres_source", "catalogues", "tables_sql", "df_tables"]:
            st.session_state.pop(key, None)
        st.session_state["fichier_actuel"] = xml_file.name

    st.divider()
    tab_resize, tab_filtres, tab_connexion = st.tabs(["📐 Redimensionner", "🔽 Formater les filtres", "🔌 Changer la connexion"])


    # ════════════════════════════════════════════════════
    # ONGLET 1 — REDIMENSIONNER
    # ════════════════════════════════════════════════════
    with tab_resize:
        dashboards = recuperer_dashboards_avec_tailles(xml_content)
        if not dashboards:
            st.warning("Aucun dashboard trouvé dans ce fichier.")
        else:
            if "df_resize" not in st.session_state:
                st.session_state["df_resize"] = init_df_resize(dashboards)

            # Appliquer à tous
            st.subheader("Appliquer à tous les dashboards cochés")
            col_a, col_b, col_c = st.columns([1, 1, 1])
            with col_a:
                largeur_globale = st.number_input(
                    "Largeur commune", min_value=1, max_value=3000, value=None,
                    step=1, placeholder="Ex : 1600", key="resize_global_w"
                )
            with col_b:
                hauteur_globale = st.number_input(
                    "Hauteur commune", min_value=1, max_value=6000, value=None,
                    step=1, placeholder="Ex : 1050", key="resize_global_h"
                )
            with col_c:
                st.write("")
                st.write("")
                if st.button("↓ Appliquer à tous", use_container_width=True, key="resize_apply_all"):
                    if largeur_globale is None and hauteur_globale is None:
                        st.warning("Renseigne au moins une dimension commune.")
                    else:
                        df = st.session_state["df_resize"].copy()
                        mask = df["Modifier"] == True
                        if not mask.any():
                            mask = pd.Series([True] * len(df), index=df.index)
                        if largeur_globale is not None:
                            df.loc[mask, "Nouvelle largeur"] = float(largeur_globale)
                        if hauteur_globale is not None:
                            df.loc[mask, "Nouvelle hauteur"] = float(hauteur_globale)
                        st.session_state["df_resize"] = df
                        st.rerun()

            # Tableau
            st.subheader("Dashboards")
            st.caption("Cochez les dashboards à modifier et renseignez les nouvelles dimensions.")
            edited_resize = st.data_editor(
                st.session_state["df_resize"],
                column_config={
                    "Modifier":         st.column_config.CheckboxColumn("Modifier", width="small"),
                    "Dashboard":        st.column_config.TextColumn("Dashboard", disabled=True),
                    "Largeur actuelle": st.column_config.TextColumn("Largeur act.", disabled=True, width="small"),
                    "Hauteur actuelle": st.column_config.TextColumn("Hauteur act.", disabled=True, width="small"),
                    "Nouvelle largeur": st.column_config.NumberColumn("Nouvelle largeur", min_value=1, max_value=3000, step=1),
                    "Nouvelle hauteur": st.column_config.NumberColumn("Nouvelle hauteur", min_value=1, max_value=6000, step=1),
                },
                hide_index=True,
                use_container_width=True,
                key="editor_resize",
            )

            # Toggles
            st.divider()
            col_l, col_r = st.columns(2)
            with col_l:
                deplacer_droite = sac.switch(
                    label="Déplacer vers la droite",
                    description="Repositionne les objets lors d'un agrandissement horizontal",
                    value=False, align="start", size="xs", position="left", key="toggle_droite"
                )
            with col_r:
                deplacer_bas = sac.switch(
                    label="Déplacer vers le bas",
                    description="Repositionne les objets lors d'un agrandissement vertical",
                    value=False, align="start", size="xs", position="left", key="toggle_bas"
                )

            nb_coches_resize = int(edited_resize["Modifier"].sum())
            st.write("")
            if st.button(
                f"Modifier ({nb_coches_resize} dashboard{'s' if nb_coches_resize > 1 else ''} sélectionné{'s' if nb_coches_resize > 1 else ''})",
                type="primary",
                disabled=nb_coches_resize == 0,
                key="btn_resize",
            ):
                selection = edited_resize[edited_resize["Modifier"]]
                lignes_ko = selection[
                    selection["Nouvelle largeur"].isna() | selection["Nouvelle hauteur"].isna()
                ]
                if not lignes_ko.empty:
                    st.error(f"Dimensions manquantes pour : **{', '.join(lignes_ko['Dashboard'].tolist())}**")
                else:
                    modifications = {
                        row["Dashboard"]: (int(row["Nouvelle largeur"]), int(row["Nouvelle hauteur"]))
                        for _, row in selection.iterrows()
                    }
                    try:
                        fichier = modifier_tableaux_de_bord(xml_content, modifications, deplacer_droite, deplacer_bas)
                        st.success(f"✅ {nb_coches_resize} dashboard(s) modifié(s).")
                        nom_base = xml_file.name.replace(".twbx", "").replace(".twb", "")
                        st.download_button(
                            label="⬇️ Télécharger le fichier modifié",
                            data=fichier,
                            file_name=f"{nom_base}_redimensionné.twb",
                            mime="application/xml",
                            key="dl_resize",
                        )
                    except ValueError as e:
                        st.error(str(e))


    # ════════════════════════════════════════════════════
    # ONGLET 2 — FORMATER LES FILTRES
    # ════════════════════════════════════════════════════
    with tab_filtres:

        if "filtres_source" not in st.session_state:
            filtres = recuperer_filtres(xml_content)
            st.session_state["filtres_source"] = filtres
            st.session_state["df_filtres"]     = init_df_filtres(filtres)

        filtres_source = st.session_state["filtres_source"]

        if not filtres_source:
            st.warning("Aucun filtre de dashboard trouvé dans ce fichier.")
        else:
            nb_filtres = len(filtres_source)
            st.caption(f"{nb_filtres} filtre{'s' if nb_filtres > 1 else ''} détecté{'s' if nb_filtres > 1 else ''} dans le fichier.")

            # Appliquer à tous
            st.subheader("Appliquer à tous les filtres cochés")
            col_a, col_b, col_c = st.columns([2, 1, 1])
            with col_a:
                mode_global = st.selectbox(
                    "Mode commun",
                    options=MODES_LABELS,
                    index=None,
                    placeholder="Choisir un mode...",
                    key="filtres_global_mode",
                )
            with col_b:
                st.write("")
                apply_global = st.checkbox("Bouton Appliquer", value=True, key="filtres_global_apply")
            with col_c:
                st.write("")
                st.write("")
                if st.button("↓ Appliquer à tous", use_container_width=True, key="filtres_apply_all"):
                    if mode_global is None:
                        st.warning("Sélectionne un mode commun avant d'appliquer.")
                    else:
                        df = st.session_state["df_filtres"].copy()
                        mask = df["Modifier"] == True
                        if not mask.any():
                            mask = pd.Series([True] * len(df), index=df.index)
                        df.loc[mask, "Nouveau mode"]      = mode_global
                        df.loc[mask, "Bouton Appliquer"]  = apply_global
                        st.session_state["df_filtres"] = df
                        st.rerun()

            # Tableau
            st.subheader("Filtres")
            st.caption("Cochez les filtres à modifier, choisissez le nouveau mode et activez le bouton Appliquer si besoin.")

            edited_filtres = st.data_editor(
                st.session_state["df_filtres"],
                column_config={
                    "Modifier":         st.column_config.CheckboxColumn("Modifier", width="small"),
                    "Dashboard":        st.column_config.TextColumn("Dashboard", disabled=True, width="medium"),
                    "Champ":            st.column_config.TextColumn("Champ", disabled=True, width="medium"),
                    "Mode actuel":      st.column_config.TextColumn("Mode actuel", disabled=True, width="large"),
                    "Nouveau mode":     st.column_config.SelectboxColumn(
                        "Nouveau mode",
                        options=MODES_LABELS,
                        width="large",
                    ),
                    "Bouton Appliquer": st.column_config.CheckboxColumn("Bouton Appliquer", width="small"),
                },
                hide_index=True,
                use_container_width=True,
                key="editor_filtres",
            )

            nb_coches_filtres = int(edited_filtres["Modifier"].sum())
            st.write("")
            if st.button(
                f"Modifier ({nb_coches_filtres} filtre{'s' if nb_coches_filtres > 1 else ''} sélectionné{'s' if nb_coches_filtres > 1 else ''})",
                type="primary",
                disabled=nb_coches_filtres == 0,
                key="btn_filtres",
            ):
                try:
                    fichier = appliquer_modifications_filtres(xml_content, edited_filtres, filtres_source)
                    st.success(f"✅ {nb_coches_filtres} filtre(s) modifié(s).")
                    nom_base = xml_file.name.replace(".twbx", "").replace(".twb", "")
                    st.download_button(
                        label="⬇️ Télécharger le fichier modifié",
                        data=fichier,
                        file_name=f"{nom_base}_filtres.twb",
                        mime="application/xml",
                        key="dl_filtres",
                    )
                except ValueError as e:
                    st.error(str(e))


    # ════════════════════════════════════════════════════
    # ONGLET 3 — CHANGER LA CONNEXION
    # ════════════════════════════════════════════════════
    with tab_connexion:

        if "catalogues" not in st.session_state:
            st.session_state["catalogues"] = recuperer_catalogues(xml_content)
            st.session_state["tables_sql"] = recuperer_tables_sql(xml_content)
            st.session_state["df_tables"]  = init_df_tables(st.session_state["tables_sql"])

        catalogues = st.session_state["catalogues"]

        if not catalogues:
            st.warning("Aucune connexion avec un catalogue Databricks détectée dans ce fichier.")
        else:
            # Afficher les connexions détectées
            st.subheader("Connexions détectées")
            for c in catalogues:
                st.markdown(
                    f"- **Catalogue :** `{c['catalog']}`"
                    + (f"  |  **Serveur :** `{c['server']}`" if c['server'] else "")
                    + (f"  |  **Schéma :** `{c['schema']}`" if c['schema'] else "")
                )

            st.divider()
            st.subheader("Remplacer le catalogue")

            catalogues_uniques = [c["catalog"] for c in catalogues]
            catalogue_source = st.selectbox(
                "Catalogue à remplacer",
                options=catalogues_uniques,
                key="conn_source",
            )
            catalogue_cible = st.text_input(
                "Nouveau catalogue cible",
                placeholder="Ex : datalake_insight_analytics",
                key="conn_cible",
            )

            st.write("")
            if st.button("🔄 Remplacer", type="primary", key="btn_connexion"):
                if not catalogue_cible or not catalogue_cible.strip():
                    st.error("Le catalogue cible ne peut pas être vide.")
                else:
                    try:
                        fichier, nb = remplacer_catalogue(
                            xml_content,
                            catalogue_source,
                            catalogue_cible.strip(),
                        )
                        st.success(
                            f"✅ Catalogue remplacé ({nb} occurrence{'s' if nb > 1 else ''} modifiée{'s' if nb > 1 else ''})."
                        )
                        nom_base = xml_file.name.replace(".twbx", "").replace(".twb", "")
                        st.download_button(
                            label="⬇️ Télécharger le fichier modifié",
                            data=fichier,
                            file_name=f"{nom_base}_connexion.twb",
                            mime="application/xml",
                            key="dl_connexion",
                        )
                    except ValueError as e:
                        st.error(str(e))

            # ── Section tables dbt ──────────────────────────────
            st.divider()
            st.subheader("Tables — renommer")
            st.caption(
                "Cochez les tables à renommer et éditez le nom cible. "
                "Le champ suffixe permet de pré-remplir automatiquement toutes les lignes correspondantes."
            )

            tables_sql = st.session_state.get("tables_sql", [])
            if not tables_sql:
                st.info("Aucune table détectée dans le fichier.")
            else:
                # Pré-remplissage par suffixe
                col_suf, col_btn = st.columns([2, 1])
                with col_suf:
                    suffixe = st.text_input(
                        "Pré-remplir depuis un suffixe",
                        placeholder="Ex : _idir",
                        key="conn_suffixe",
                    )
                with col_btn:
                    st.write("")
                    st.write("")
                    if st.button("↓ Pré-remplir", use_container_width=True, key="btn_prefill",
                                 disabled=not (suffixe and suffixe.strip())):
                        suf = suffixe.strip()
                        df = st.session_state["df_tables"].copy()
                        mask = df["Table actuelle"].str.endswith(suf)
                        if not mask.any():
                            st.warning(f"Aucune table ne se termine par « {suf} ».")
                        else:
                            df.loc[mask, "Table cible"] = df.loc[mask, "Table actuelle"].str[:-len(suf)]
                            df.loc[mask, "Modifier"] = True
                            st.session_state["df_tables"] = df
                            st.rerun()

                # Data editor
                edited_tables = st.data_editor(
                    st.session_state["df_tables"],
                    column_config={
                        "Modifier":       st.column_config.CheckboxColumn("Modifier", width="small"),
                        "Type":           st.column_config.TextColumn("Type", disabled=True, width="small"),
                        "Catalogue":      st.column_config.TextColumn("Catalogue", disabled=True),
                        "Schéma":         st.column_config.TextColumn("Schéma", disabled=True),
                        "Table actuelle": st.column_config.TextColumn("Table actuelle", disabled=True),
                        "Table cible":    st.column_config.TextColumn("Table cible"),
                    },
                    hide_index=True,
                    use_container_width=True,
                    key="editor_tables",
                )

                nb_coches_tables = int(edited_tables["Modifier"].sum())
                st.write("")
                if st.button(
                    f"Renommer ({nb_coches_tables} table{'s' if nb_coches_tables > 1 else ''} sélectionnée{'s' if nb_coches_tables > 1 else ''})",
                    type="primary",
                    disabled=nb_coches_tables == 0,
                    key="btn_tables",
                ):
                    selection = edited_tables[edited_tables["Modifier"]].to_dict("records")
                    try:
                        fichier, nb = remplacer_tables(xml_content, selection)
                        st.success(
                            f"✅ {nb} occurrence{'s' if nb > 1 else ''} modifiée{'s' if nb > 1 else ''}."
                        )
                        nom_base = xml_file.name.replace(".twbx", "").replace(".twb", "")
                        st.download_button(
                            label="⬇️ Télécharger le fichier modifié",
                            data=fichier,
                            file_name=f"{nom_base}_tables.twb",
                            mime="application/xml",
                            key="dl_tables",
                        )
                    except ValueError as e:
                        st.error(str(e))


if __name__ == "__main__":
    main()
