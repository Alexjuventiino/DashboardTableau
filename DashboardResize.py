import streamlit as st
import streamlit_antd_components as sac
import xml.etree.ElementTree as ET
from io import BytesIO
import pandas as pd
import zipfile
import re


# ═══════════════════════════════════════════════════════════════
# UTILITAIRES COMMUNS
# ═══════════════════════════════════════════════════════════════

def extraire_twb_depuis_twbx(file_bytes: bytes) -> bytes:
    with zipfile.ZipFile(BytesIO(file_bytes)) as z:
        twb_names = [n for n in z.namelist() if n.endswith(".twb")]
        if not twb_names:
            raise ValueError("Aucun fichier .twb trouvé dans l'archive .twbx.")
        with z.open(twb_names[0]) as f:
            return f.read()


def charger_contenu_xml(uploaded_file) -> bytes:
    raw = uploaded_file.read()
    if uploaded_file.name.endswith(".twbx"):
        return extraire_twb_depuis_twbx(raw)
    return raw


def parser_xml(xml_content: bytes) -> ET.ElementTree:
    try:
        return ET.parse(BytesIO(xml_content))
    except ET.ParseError as e:
        raise ValueError(f"Le fichier XML est malformé : {e}")


def serialiser_xml(tree: ET.ElementTree) -> BytesIO:
    output = BytesIO()
    tree.write(output, encoding="utf-8", xml_declaration=False)
    output.seek(0)
    return output


# ═══════════════════════════════════════════════════════════════
# OUTIL 1 — REDIMENSIONNER
# ═══════════════════════════════════════════════════════════════

def recuperer_dashboards_avec_tailles(xml_content: bytes):
    tree = parser_xml(xml_content)
    root = tree.getroot()
    dashboards = []
    for dashboard in root.findall(".//dashboard"):
        name = dashboard.get("name")
        size = dashboard.find("./size")
        if size is not None:
            w = size.get("maxwidth", "?")
            h = size.get("maxheight", "?")
        else:
            w, h = "?", "?"
        dashboards.append({"name": name, "width": w, "height": h})
    return dashboards


def calculer_nouvelles_valeurs(x, w, y, h, maxwidth, maxheight,
                               nouvelle_largeur, nouvelle_hauteur,
                               deplacer_droite, deplacer_bas):
    if maxwidth == 0 or maxheight == 0 or nouvelle_largeur == 0 or nouvelle_hauteur == 0:
        raise ValueError("Les dimensions ne peuvent pas être nulles.")

    if deplacer_droite and not deplacer_bas:
        nouveau_x = (x / (100000 / maxwidth) + (nouvelle_largeur - maxwidth)) * (100000 / nouvelle_largeur)
        nouveau_w = w / (100000 / maxwidth) * (100000 / nouvelle_largeur)
        nouveau_y, nouveau_h = y, h
    elif deplacer_bas and not deplacer_droite:
        nouveau_x, nouveau_w = x, w
        nouveau_y = (y / (100000 / maxheight) + (nouvelle_hauteur - maxheight)) * (100000 / nouvelle_hauteur)
        nouveau_h = h / (100000 / maxheight) * (100000 / nouvelle_hauteur)
    elif deplacer_bas and deplacer_droite:
        nouveau_x = (x / (100000 / maxwidth) + (nouvelle_largeur - maxwidth)) * (100000 / nouvelle_largeur)
        nouveau_w = w / (100000 / maxwidth) * (100000 / nouvelle_largeur)
        nouveau_y = (y / (100000 / maxheight) + (nouvelle_hauteur - maxheight)) * (100000 / nouvelle_hauteur)
        nouveau_h = h / (100000 / maxheight) * (100000 / nouvelle_hauteur)
    else:
        nouveau_x = x / (100000 / maxwidth) * (100000 / nouvelle_largeur)
        nouveau_w = w / (100000 / maxwidth) * (100000 / nouvelle_largeur)
        nouveau_y = y / (100000 / maxheight) * (100000 / nouvelle_hauteur)
        nouveau_h = h / (100000 / maxheight) * (100000 / nouvelle_hauteur)

    return int(nouveau_x), int(nouveau_w), int(nouveau_y), int(nouveau_h)


def modifier_tableaux_de_bord(xml_content: bytes, modifications: dict,
                               deplacer_droite: bool, deplacer_bas: bool) -> BytesIO:
    tree = parser_xml(xml_content)
    root = tree.getroot()

    for dashboard in root.findall(".//dashboard"):
        name = dashboard.get("name")
        if name not in modifications:
            continue
        nouvelle_largeur, nouvelle_hauteur = modifications[name]
        maxwidth, maxheight = float(nouvelle_largeur), float(nouvelle_hauteur)

        for size in dashboard.findall("./size"):
            maxwidth  = float(size.get("maxwidth")  or 1.0)
            maxheight = float(size.get("maxheight") or 1.0)
            size.set("maxwidth",  str(nouvelle_largeur))
            size.set("minwidth",  str(nouvelle_largeur))
            size.set("maxheight", str(nouvelle_hauteur))
            size.set("minheight", str(nouvelle_hauteur))

        for zone in dashboard.findall(".//zone"):
            x = int(zone.get("x", 0))
            w = int(zone.get("w", 0))
            y = int(zone.get("y", 0))
            h = int(zone.get("h", 0))
            nx, nw, ny, nh = calculer_nouvelles_valeurs(
                x, w, y, h, maxwidth, maxheight,
                nouvelle_largeur, nouvelle_hauteur,
                deplacer_droite, deplacer_bas
            )
            zone.set("x", str(nx))
            zone.set("w", str(nw))
            zone.set("y", str(ny))
            zone.set("h", str(nh))

    return serialiser_xml(tree)


def init_df_resize(dashboards):
    return pd.DataFrame([
        {
            "Modifier":         False,
            "Dashboard":        d["name"],
            "Largeur actuelle": d["width"],
            "Hauteur actuelle": d["height"],
            "Nouvelle largeur": None,
            "Nouvelle hauteur": None,
        }
        for d in dashboards
    ])


# ═══════════════════════════════════════════════════════════════
# OUTIL 2 — FORMATER LES FILTRES
# ═══════════════════════════════════════════════════════════════

MODES = {
    "":              "Liste complète (défaut)",
    "dropdown":      "Liste déroulante — sélection unique",
    "checkdropdown": "Liste déroulante — multi-sélection",
    "typeinlist":    "Saisie texte",
    "multivalue":    "Liste à cocher",
    "singlevalue":   "Bouton radio",
}
MODES_LABELS  = list(MODES.values())
MODES_REVERSE = {v: k for k, v in MODES.items()}


def extraire_nom_champ(param: str) -> str:
    """Extrait le nom lisible depuis un param Tableau."""
    match = re.search(
        r'\[(?:none|sum|avg|count|min|max|attr|year|month|day|mdy|wk)?:?([^\]:]+):[^\]]*\]$',
        param
    )
    if match:
        return match.group(1)
    parts = re.findall(r'\[([^\]]+)\]', param)
    return parts[-1] if parts else param


def recuperer_filtres(xml_content: bytes) -> list:
    tree = parser_xml(xml_content)
    root = tree.getroot()
    filtres = []
    vus = set()  # (dashboard_name, zone_id) déjà traités

    for dashboard in root.findall(".//dashboard"):
        # Exclure les layouts alternatifs (phone, tablet...) générés par Tableau
        # Ces éléments ont un attribut "type" non vide ("phone", "tablet", etc.)
        if dashboard.get("type"):
            continue

        dashboard_name = dashboard.get("name")
        for zone in dashboard.findall(".//zone[@type-v2='filter']"):
            zone_id = zone.get("id")
            cle = (dashboard_name, zone_id)

            # Ignorer les zones déjà vues (duplications structurelles dans le XML)
            if cle in vus:
                continue
            vus.add(cle)

            param      = zone.get("param", "")
            mode_xml   = zone.get("mode", "")
            show_apply = zone.get("show-apply", "") == "true"
            champ      = extraire_nom_champ(param) if param else "(inconnu)"
            mode_label = MODES.get(mode_xml, mode_xml)

            filtres.append({
                "zone_id":     zone_id,
                "dashboard":   dashboard_name,
                "champ":       champ,
                "param":       param,
                "mode_actuel": mode_label,
                "mode_xml":    mode_xml,
                "show_apply":  show_apply,
            })

    return filtres


def init_df_filtres(filtres: list) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Modifier":         False,
            "Dashboard":        f["dashboard"],
            "Champ":            f["champ"],
            "Mode actuel":      f["mode_actuel"],
            "Nouveau mode":     f["mode_actuel"],  # pré-rempli avec valeur actuelle
            "Bouton Appliquer": f["show_apply"],
        }
        for f in filtres
    ])


def appliquer_modifications_filtres(xml_content: bytes, df_edited: pd.DataFrame,
                                    filtres_source: list) -> BytesIO:
    tree = parser_xml(xml_content)
    root = tree.getroot()

    # Index des modifications : (dashboard, param) → (mode_xml, show_apply)
    modifs = {}
    for i, row in df_edited[df_edited["Modifier"]].iterrows():
        source   = filtres_source[i]
        mode_xml = MODES_REVERSE.get(row["Nouveau mode"], "")
        modifs[(source["dashboard"], source["param"])] = (mode_xml, bool(row["Bouton Appliquer"]))

    if not modifs:
        return serialiser_xml(tree)

    for dashboard in root.findall(".//dashboard"):
        dashboard_name = dashboard.get("name")
        for zone in dashboard.findall(".//zone[@type-v2='filter']"):
            param = zone.get("param", "")
            key   = (dashboard_name, param)
            if key not in modifs:
                continue

            mode_xml, show_apply = modifs[key]

            # Mode : supprimer l'attribut si retour au défaut "liste complète"
            if mode_xml == "":
                zone.attrib.pop("mode", None)
            else:
                zone.set("mode", mode_xml)

            # Bouton Appliquer
            if show_apply:
                zone.set("show-apply", "true")
            else:
                zone.attrib.pop("show-apply", None)

    return serialiser_xml(tree)


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
        for key in ["df_resize", "df_filtres", "filtres_source"]:
            st.session_state.pop(key, None)
        st.session_state["fichier_actuel"] = xml_file.name

    st.divider()
    tab_resize, tab_filtres = st.tabs(["📐 Redimensionner", "🔽 Formater les filtres"])


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


if __name__ == "__main__":
    main()
