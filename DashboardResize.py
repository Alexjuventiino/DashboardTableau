import streamlit as st
import streamlit_antd_components as sac
import pandas as pd

from utils import charger_contenu_xml, parser_xml
from outil1_resize import recuperer_dashboards_avec_tailles, modifier_tableaux_de_bord, init_df_resize
from outil2_filtres import (
    MODES_LABELS, recuperer_filtres, init_df_filtres, appliquer_modifications_filtres,
    recuperer_feuilles_par_dashboard, recuperer_champs_feuille, ajouter_filtres_dashboards,
)
from outil3_connexion import (
    recuperer_catalogues, remplacer_catalogue,
    recuperer_tables_sql, init_df_tables, remplacer_tables,
    remplacer_serveur,
)
from translations import TRANSLATIONS


# ═══════════════════════════════════════════════════════════════
# UI PRINCIPALE
# ═══════════════════════════════════════════════════════════════

def main():
    # ── Sélecteur de langue ────────────────────────────────────────
    _col_title, _col_lang = st.columns([5, 1])
    with _col_lang:
        st.write("")
        _choice = st.radio(
            "",
            options=["🇫🇷 FR", "🇬🇧 EN"],
            horizontal=True,
            key="lang_radio",
            label_visibility="collapsed",
        )
    lang = "en" if "EN" in _choice else "fr"
    T = TRANSLATIONS[lang]

    with _col_title:
        st.title(T["title"])

    # Upload unique partagé entre les onglets
    xml_file = st.file_uploader(T["upload_label"], type=["twb", "twbx", "tds"])
    _is_tds = xml_file is not None and xml_file.name.endswith(".tds")

    if xml_file is None:
        return

    try:
        xml_content = charger_contenu_xml(xml_file)
        parser_xml(xml_content)  # validation
    except ValueError as e:
        st.error(T["upload_error"].format(e))
        return

    # Réinitialiser si le fichier change
    if st.session_state.get("fichier_actuel") != xml_file.name:
        for key in ["df_resize", "df_filtres", "filtres_source", "feuilles_par_dashboard",
                    "catalogues", "tables_sql", "df_tables"]:
            st.session_state.pop(key, None)
        st.session_state["fichier_actuel"] = xml_file.name

    st.divider()
    tab_resize, tab_filtres, tab_connexion = st.tabs([T["tab_resize"], T["tab_filters"], T["tab_connexion"]])


    # ════════════════════════════════════════════════════
    # ONGLET 1 — REDIMENSIONNER
    # ════════════════════════════════════════════════════
    with tab_resize:
        if _is_tds:
            st.info(T["tds_not_applicable"])
        else:
            dashboards = recuperer_dashboards_avec_tailles(xml_content)
            if not dashboards:
                st.warning(T["resize_no_dashboard"])
            else:
                if "df_resize" not in st.session_state:
                    st.session_state["df_resize"] = init_df_resize(dashboards)

                # Appliquer à tous
                st.subheader(T["resize_apply_all_title"])
                col_a, col_b, col_c = st.columns([1, 1, 1])
                with col_a:
                    largeur_globale = st.number_input(
                        T["resize_common_width"], min_value=1, max_value=3000, value=None,
                        step=1, placeholder="Ex : 1600", key="resize_global_w"
                    )
                with col_b:
                    hauteur_globale = st.number_input(
                        T["resize_common_height"], min_value=1, max_value=6000, value=None,
                        step=1, placeholder="Ex : 1050", key="resize_global_h"
                    )
                with col_c:
                    st.write("")
                    st.write("")
                    if st.button(T["resize_btn_apply_all"], use_container_width=True, key="resize_apply_all"):
                        if largeur_globale is None and hauteur_globale is None:
                            st.warning(T["resize_warn_no_dim"])
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
                st.subheader(T["resize_dashboards_title"])
                st.caption(T["resize_dashboards_caption"])
                edited_resize = st.data_editor(
                    st.session_state["df_resize"],
                    column_config={
                        "Modifier":         st.column_config.CheckboxColumn(T["resize_col_check"], width="small"),
                        "Dashboard":        st.column_config.TextColumn(T["resize_col_dash"], disabled=True),
                        "Largeur actuelle": st.column_config.TextColumn(T["resize_col_cur_w"], disabled=True, width="small"),
                        "Hauteur actuelle": st.column_config.TextColumn(T["resize_col_cur_h"], disabled=True, width="small"),
                        "Nouvelle largeur": st.column_config.NumberColumn(T["resize_col_new_w"], min_value=1, max_value=3000, step=1),
                        "Nouvelle hauteur": st.column_config.NumberColumn(T["resize_col_new_h"], min_value=1, max_value=6000, step=1),
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
                        label=T["resize_toggle_right"],
                        description=T["resize_toggle_right_desc"],
                        value=False, align="start", size="xs", position="left", key="toggle_droite"
                    )
                with col_r:
                    deplacer_bas = sac.switch(
                        label=T["resize_toggle_down"],
                        description=T["resize_toggle_down_desc"],
                        value=False, align="start", size="xs", position="left", key="toggle_bas"
                    )

                nb_coches_resize = int(edited_resize["Modifier"].sum())
                s = "s" if nb_coches_resize > 1 else ""
                st.write("")
                if st.button(
                    T["resize_btn"].format(n=nb_coches_resize, s=s),
                    type="primary",
                    disabled=nb_coches_resize == 0,
                    key="btn_resize",
                ):
                    selection = edited_resize[edited_resize["Modifier"]]
                    lignes_ko = selection[
                        selection["Nouvelle largeur"].isna() | selection["Nouvelle hauteur"].isna()
                    ]
                    if not lignes_ko.empty:
                        st.error(T["resize_error_dims"].format(", ".join(lignes_ko["Dashboard"].tolist())))
                    else:
                        modifications = {
                            row["Dashboard"]: (int(row["Nouvelle largeur"]), int(row["Nouvelle hauteur"]))
                            for _, row in selection.iterrows()
                        }
                        try:
                            fichier = modifier_tableaux_de_bord(xml_content, modifications, deplacer_droite, deplacer_bas)
                            st.success(T["resize_success"].format(nb_coches_resize))
                            nom_base = xml_file.name.replace(".twbx", "").replace(".twb", "")
                            st.download_button(
                                label=T["resize_download"],
                                data=fichier,
                                file_name=f"{nom_base}{T['resize_suffix']}.twb",
                                mime="application/xml",
                                key="dl_resize",
                            )
                        except ValueError as e:
                            st.error(str(e))


    # ════════════════════════════════════════════════════
    # ONGLET 2 — FORMATER LES FILTRES
    # ════════════════════════════════════════════════════
    with tab_filtres:
        if _is_tds:
            st.info(T["tds_not_applicable"])
        else:
            if "filtres_source" not in st.session_state:
                filtres = recuperer_filtres(xml_content)
                st.session_state["filtres_source"]          = filtres
                st.session_state["df_filtres"]              = init_df_filtres(filtres)
                st.session_state["feuilles_par_dashboard"]  = recuperer_feuilles_par_dashboard(xml_content)

            filtres_source = st.session_state["filtres_source"]

            if not filtres_source:
                st.warning(T["filtres_no_filter"])
            else:
                nb_filtres = len(filtres_source)
                s = "s" if nb_filtres > 1 else ""
                st.caption(T["filtres_detected"].format(n=nb_filtres, s=s))

                # Appliquer à tous
                st.subheader(T["filtres_apply_all_title"])
                col_a, col_b, col_c = st.columns([2, 1, 1])
                with col_a:
                    mode_global = st.selectbox(
                        T["filtres_common_mode"],
                        options=MODES_LABELS,
                        index=None,
                        placeholder=T["filtres_common_mode_ph"],
                        key="filtres_global_mode",
                    )
                with col_b:
                    st.write("")
                    apply_global = st.checkbox(T["filtres_apply_btn_col"], value=True, key="filtres_global_apply")
                with col_c:
                    st.write("")
                    st.write("")
                    if st.button(T["filtres_btn_apply_all"], use_container_width=True, key="filtres_apply_all"):
                        if mode_global is None:
                            st.warning(T["filtres_warn_no_mode"])
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
                st.subheader(T["filtres_title"])
                st.caption(T["filtres_caption"])

                edited_filtres = st.data_editor(
                    st.session_state["df_filtres"],
                    column_config={
                        "Modifier":         st.column_config.CheckboxColumn(T["filtres_col_check"], width="small"),
                        "Dashboard":        st.column_config.TextColumn(T["filtres_col_dashboard"], disabled=True, width="medium"),
                        "Champ":            st.column_config.TextColumn(T["filtres_col_field"], disabled=True, width="medium"),
                        "Mode actuel":      st.column_config.TextColumn(T["filtres_col_cur_mode"], disabled=True, width="large"),
                        "Nouveau mode":     st.column_config.SelectboxColumn(
                            T["filtres_col_new_mode"],
                            options=MODES_LABELS,
                            width="large",
                        ),
                        "Bouton Appliquer": st.column_config.CheckboxColumn(T["filtres_col_apply_btn"], width="small"),
                    },
                    hide_index=True,
                    use_container_width=True,
                    key="editor_filtres",
                )

                nb_coches_filtres = int(edited_filtres["Modifier"].sum())
                s = "s" if nb_coches_filtres > 1 else ""
                st.write("")
                if st.button(
                    T["filtres_btn"].format(n=nb_coches_filtres, s=s),
                    type="primary",
                    disabled=nb_coches_filtres == 0,
                    key="btn_filtres",
                ):
                    try:
                        fichier = appliquer_modifications_filtres(xml_content, edited_filtres, filtres_source)
                        st.success(T["filtres_success"].format(nb_coches_filtres))
                        nom_base = xml_file.name.replace(".twbx", "").replace(".twb", "")
                        st.download_button(
                            label=T["filtres_download"],
                            data=fichier,
                            file_name=f"{nom_base}{T['filtres_suffix']}.twb",
                            mime="application/xml",
                            key="dl_filtres",
                        )
                    except ValueError as e:
                        st.error(str(e))

            # ── Ajouter des filtres aux dashboards ──────────────────
            st.divider()
            st.subheader(T["filtres_add_title"])
            st.caption(T["filtres_add_caption"])

            feuilles_par_dash = st.session_state.get("feuilles_par_dashboard", {})
            if not feuilles_par_dash:
                st.info(T["filtres_add_no_dashboards"])
            else:
                add_specs = []
                for dash_name, sheets in feuilles_par_dash.items():
                    with st.expander(dash_name):
                        sheet_key  = f"add_filter_sheet_{dash_name}"
                        fields_key = f"add_filter_fields_{dash_name}"

                        selected_sheet = st.selectbox(
                            T["filtres_add_sheet_label"],
                            options=sheets,
                            key=sheet_key,
                        )

                        champs_dispo = recuperer_champs_feuille(xml_content, selected_sheet)
                        if not champs_dispo:
                            st.info(T["filtres_add_no_fields"])
                        else:
                            # Dédoublonnage par instance_name, label = caption ou nom déduit
                            seen_inst: set = set()
                            labels:    list = []
                            instances: list = []
                            for fi in champs_dispo:
                                inst = fi['instance_name']
                                if inst in seen_inst:
                                    continue
                                seen_inst.add(inst)
                                labels.append(fi['display_name'])
                                instances.append(inst)

                            selected_labels = st.multiselect(
                                T["filtres_add_fields_label"],
                                options=labels,
                                key=fields_key,
                            )
                            selected_instances = [
                                instances[labels.index(lbl)]
                                for lbl in selected_labels
                            ]
                            if selected_instances:
                                add_specs.append({
                                    "dashboard": dash_name,
                                    "feuille":   selected_sheet,
                                    "champs":    selected_instances,
                                })

                st.write("")
                if st.button(
                    T["filtres_add_btn"],
                    type="primary",
                    disabled=not add_specs,
                    key="btn_add_filters",
                ):
                    try:
                        fichier_add, nb_add = ajouter_filtres_dashboards(xml_content, add_specs)
                        st.success(T["filtres_add_success"].format(nb_add))
                        nom_base = xml_file.name.replace(".twbx", "").replace(".twb", "").replace(".tds", "")
                        nom_ext  = ".tds" if _is_tds else ".twb"
                        st.download_button(
                            label=T["filtres_add_download"],
                            data=fichier_add,
                            file_name=f"{nom_base}{T['filtres_add_suffix']}{nom_ext}",
                            mime="application/xml",
                            key="dl_add_filters",
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

        # Nettoyage des lignes Extract éventuellement présentes dans un état
        # de session mis en cache par une ancienne version du code
        if "df_tables" in st.session_state:
            _df_chk = st.session_state["df_tables"]
            if "Schéma" in _df_chk.columns and _df_chk["Schéma"].str.lower().eq("extract").any():
                st.session_state["tables_sql"] = recuperer_tables_sql(xml_content)
                st.session_state["df_tables"]  = init_df_tables(st.session_state["tables_sql"])

        catalogues = st.session_state["catalogues"]

        if not catalogues:
            st.warning(T["conn_no_databricks"])
        else:
            conn_ref = catalogues[0]

            # ── Connexions détectées ────────────────────────────
            st.subheader(T["conn_detected_title"])
            for c in catalogues:
                st.markdown(
                    f"- **{T['conn_lbl_catalog']}** `{c['catalog']}`"
                    + (f"  |  **{T['conn_lbl_server']}** `{c['server']}`" if c['server'] else "")
                    + (f"  |  **{T['conn_lbl_schema']}** `{c['schema']}`" if c['schema'] else "")
                )

            # ── 1 — Serveur / chemin HTTP ───────────────────────
            st.divider()
            st.subheader(T["conn_server_title"])

            _ENV_KEYS = ["exploration", "indus", "custom"]
            _ENV_LABELS = {
                "exploration": T["conn_env_exploration"],
                "indus":       T["conn_env_indus"],
                "custom":      T["conn_env_custom"],
            }
            _ENV_DATA = {
                "exploration": {
                    "server":    "decathlon-dataplatform-exploration.cloud.databricks.com",
                    "http_path": "/sql/1.0/warehouses/e71fadc53501a3f1",
                },
                "indus": {
                    "server":    "decathlon-dataplatform-indus.cloud.databricks.com",
                    "http_path": "/sql/1.0/warehouses/a978e5a19876d1b6",
                },
                "custom": None,
            }

            preset = st.radio(
                T["conn_env_label"],
                options=_ENV_KEYS,
                format_func=lambda k: _ENV_LABELS[k],
                horizontal=True,
                key="conn_env_preset",
            )

            # Quand le preset change, on écrase les valeurs dans session_state
            # avant que les text_input soient rendus.
            if _ENV_DATA[preset] is not None:
                _default_srv  = _ENV_DATA[preset]["server"]
                _default_http = _ENV_DATA[preset]["http_path"]
            else:
                _default_srv  = conn_ref["server"]
                _default_http = conn_ref["http_path"]

            prev_preset_key = "conn_env_preset_prev"
            if st.session_state.get(prev_preset_key) != preset:
                st.session_state["conn_server_cible"] = _default_srv
                st.session_state["conn_http_cible"]   = _default_http
                st.session_state[prev_preset_key]     = preset

            col_srv, col_http = st.columns(2)
            with col_srv:
                serveur_cible = st.text_input(
                    T["conn_server_input"],
                    key="conn_server_cible",
                )
            with col_http:
                http_path_cible = st.text_input(
                    T["conn_http_input"],
                    key="conn_http_cible",
                )

            # ── 2 — Catalogue ──────────────────────────────────
            st.divider()
            st.subheader(T["conn_catalog_title"])

            catalogues_uniques = [c["catalog"] for c in catalogues]
            catalogue_source = st.selectbox(
                T["conn_catalog_source"],
                options=catalogues_uniques,
                key="conn_source",
            )
            catalogue_cible = st.text_input(
                T["conn_catalog_target"],
                placeholder=T["conn_catalog_ph"],
                key="conn_cible",
            )

            # ── 3 — Tables ─────────────────────────────────────
            st.divider()
            st.subheader(T["conn_tables_title"])
            st.caption(T["conn_tables_caption"])

            tables_sql = st.session_state.get("tables_sql", [])
            if not tables_sql:
                st.info(T["conn_no_tables"])
            else:
                col_suf, col_btn = st.columns([2, 1])
                with col_suf:
                    suffixe = st.text_input(
                        T["conn_suffix_label"],
                        placeholder=T["conn_suffix_ph"],
                        key="conn_suffixe",
                    )
                with col_btn:
                    st.write("")
                    st.write("")
                    if st.button(T["conn_prefill_btn"], use_container_width=True, key="btn_prefill",
                                 disabled=not (suffixe and suffixe.strip())):
                        suf = suffixe.strip()
                        df = st.session_state["df_tables"].copy()
                        mask = df["Table actuelle"].str.endswith(suf)
                        if not mask.any():
                            st.warning(T["conn_suffix_warn"].format(suf))
                        else:
                            df.loc[mask, "Table cible"] = df.loc[mask, "Table actuelle"].str[:-len(suf)]
                            df.loc[mask, "Modifier"] = True
                            st.session_state["df_tables"] = df
                            st.rerun()

                edited_tables = st.data_editor(
                    st.session_state["df_tables"],
                    column_config={
                        "Modifier":       st.column_config.CheckboxColumn(T["conn_col_check"], width="small"),
                        "Type":           st.column_config.TextColumn(T["conn_col_type"], disabled=True, width="small"),
                        "Catalogue":      st.column_config.TextColumn(T["conn_col_catalog"], disabled=True),
                        "Schéma":         st.column_config.TextColumn(T["conn_col_schema"], disabled=True),
                        "Table actuelle": st.column_config.TextColumn(T["conn_col_cur_table"], disabled=True),
                        "Table cible":    st.column_config.TextColumn(T["conn_col_target_table"]),
                    },
                    hide_index=True,
                    use_container_width=True,
                    key="editor_tables",
                )

            # ── Appliquer tout ─────────────────────────────────
            st.divider()
            nb_coches_tables = int(edited_tables["Modifier"].sum()) if tables_sql else 0
            catalogue_change = bool(catalogue_cible and catalogue_cible.strip() and catalogue_cible.strip() != catalogue_source)
            serveur_change   = serveur_cible.strip() != conn_ref["server"]
            http_change      = http_path_cible.strip() != conn_ref["http_path"]

            recap = []
            if catalogue_change:
                recap.append(T["conn_recap_catalog"].format(catalogue_source, catalogue_cible.strip()))
            if serveur_change:
                recap.append(T["conn_recap_server"].format(conn_ref['server'], serveur_cible.strip()))
            if http_change:
                recap.append(T["conn_recap_http"].format(conn_ref['http_path'], http_path_cible.strip()))
            if nb_coches_tables:
                s = "s" if nb_coches_tables > 1 else ""
                recap.append(T["conn_recap_tables"].format(n=nb_coches_tables, s=s))
            if recap:
                st.caption(T["conn_recap_title"].format("\n".join(recap)))

            if st.button(
                T["conn_apply_btn"],
                type="primary",
                disabled=not catalogue_change and not serveur_change and not http_change and nb_coches_tables == 0,
                key="btn_appliquer_tout",
            ):
                erreurs = []
                xml_modifie = xml_content

                if catalogue_change:
                    try:
                        xml_modifie, nb_cat = remplacer_catalogue(
                            xml_modifie, catalogue_source, catalogue_cible.strip()
                        )
                    except ValueError as e:
                        erreurs.append(T["conn_err_catalog"].format(e))

                if serveur_change or http_change:
                    try:
                        xml_modifie, nb_srv = remplacer_serveur(
                            xml_modifie,
                            conn_ref["server"], serveur_cible.strip(),
                            conn_ref["http_path"], http_path_cible.strip(),
                        )
                    except ValueError as e:
                        erreurs.append(T["conn_err_server"].format(e))

                if nb_coches_tables:
                    selection = edited_tables[edited_tables["Modifier"]].to_dict("records")
                    try:
                        xml_modifie, nb_tab = remplacer_tables(xml_modifie, selection)
                    except ValueError as e:
                        erreurs.append(T["conn_err_tables"].format(e))

                if erreurs:
                    for err in erreurs:
                        st.error(err)
                else:
                    msgs = []
                    if catalogue_change:
                        s = "s" if nb_cat > 1 else ""
                        msgs.append(T["conn_ok_catalog"].format(n=nb_cat, s=s))
                    if serveur_change or http_change:
                        msgs.append(T["conn_ok_server"])
                    if nb_coches_tables:
                        s = "s" if nb_tab > 1 else ""
                        msgs.append(T["conn_ok_tables"].format(n=nb_tab, s=s))
                    st.success("✅ " + " · ".join(msgs) + ".")
                    nom_base = xml_file.name.replace(".twbx", "").replace(".twb", "").replace(".tds", "")
                    nom_ext  = ".tds" if _is_tds else ".twb"
                    st.download_button(
                        label=T["conn_download"],
                        data=xml_modifie,
                        file_name=f"{nom_base}{T['conn_suffix']}{nom_ext}",
                        mime="application/xml",
                        key="dl_connexion",
                    )


if __name__ == "__main__":
    main()
