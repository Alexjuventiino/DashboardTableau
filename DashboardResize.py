import streamlit as st
import streamlit_antd_components as sac
import xml.etree.ElementTree as ET
from io import BytesIO
import pandas as pd
import zipfile
import tempfile
import os


# ─────────────────────────────────────────────
# #9 — Extraction .twbx (ZIP → .twb)
# ─────────────────────────────────────────────

def extraire_twb_depuis_twbx(file_bytes: bytes) -> bytes:
    """Extrait le fichier .twb contenu dans un .twbx (archive ZIP)."""
    with zipfile.ZipFile(BytesIO(file_bytes)) as z:
        twb_names = [n for n in z.namelist() if n.endswith(".twb")]
        if not twb_names:
            raise ValueError("Aucun fichier .twb trouvé dans l'archive .twbx.")
        with z.open(twb_names[0]) as f:
            return f.read()


def charger_contenu_xml(uploaded_file) -> bytes:
    """
    Charge le contenu XML depuis un .twb ou .twbx.
    Lève une ValueError si le format n'est pas reconnu.
    """
    raw = uploaded_file.read()
    if uploaded_file.name.endswith(".twbx"):
        return extraire_twb_depuis_twbx(raw)
    return raw


# ─────────────────────────────────────────────
# #10 — Parsing avec validation XML
# ─────────────────────────────────────────────

def recuperer_dashboards_avec_tailles(xml_content: bytes):
    """
    Parse le XML et retourne une liste de dicts {name, width, height}.
    Lève une ValueError explicite si le XML est malformé.
    """
    try:
        tree = ET.parse(BytesIO(xml_content))
    except ET.ParseError as e:
        raise ValueError(f"Le fichier XML est malformé et ne peut pas être lu : {e}")

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


# ─────────────────────────────────────────────
# Calcul des nouvelles coordonnées
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# Modification (batch)
# ─────────────────────────────────────────────

def modifier_tableaux_de_bord(xml_content: bytes, modifications: dict,
                               deplacer_droite: bool, deplacer_bas: bool) -> BytesIO:
    """
    modifications: {dashboard_name: (nouvelle_largeur, nouvelle_hauteur)}
    Traite tous les dashboards sélectionnés en une seule passe XML.
    """
    try:
        tree = ET.parse(BytesIO(xml_content))
    except ET.ParseError as e:
        raise ValueError(f"Erreur de lecture XML lors de la modification : {e}")

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

    output = BytesIO()
    tree.write(output, encoding="utf-8", xml_declaration=False)
    output.seek(0)
    return output


# ─────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────

def main():
    st.title("Modification de Tableau de Bord")

    # #9 — Accepter .twb et .twbx
    xml_file = st.file_uploader("Uploader le fichier .twb ou .twbx", type=["twb", "twbx"])

    if xml_file is None:
        return

    # #10 — Validation à l'upload
    try:
        xml_content = charger_contenu_xml(xml_file)
        dashboards  = recuperer_dashboards_avec_tailles(xml_content)
    except ValueError as e:
        st.error(f"❌ Impossible de lire le fichier : {e}")
        return

    if not dashboards:
        st.warning("Aucun dashboard trouvé dans ce fichier.")
        return

    # ── #1 — Appliquer à tous ────────────────────────────────────────
    st.subheader("Appliquer à tous les dashboards cochés")
    col_a, col_b, col_c = st.columns([1, 1, 1])
    with col_a:
        largeur_globale = st.number_input(
            "Largeur commune", min_value=1, max_value=3000, value=None,
            step=1, placeholder="Ex : 1600", key="global_w"
        )
    with col_b:
        hauteur_globale = st.number_input(
            "Hauteur commune", min_value=1, max_value=6000, value=None,
            step=1, placeholder="Ex : 1050", key="global_h"
        )
    with col_c:
        st.write("")  # alignement vertical
        st.write("")
        appliquer_a_tous = st.button("↓ Appliquer à tous", use_container_width=True)

    # ── Tableau éditeur ──────────────────────────────────────────────
    st.subheader("Dashboards")
    st.caption("Cochez les dashboards à modifier et renseignez les nouvelles dimensions.")

    # Initialiser ou mettre à jour le dataframe en session_state
    if "df_dashboards" not in st.session_state or st.session_state.get("fichier_actuel") != xml_file.name:
        st.session_state["df_dashboards"] = pd.DataFrame([
            {
                "Modifier": False,
                "Dashboard": d["name"],
                "Largeur actuelle": d["width"],
                "Hauteur actuelle": d["height"],
                "Nouvelle largeur": None,
                "Nouvelle hauteur": None,
            }
            for d in dashboards
        ])
        st.session_state["fichier_actuel"] = xml_file.name

    df = st.session_state["df_dashboards"].copy()

    # Appliquer les dimensions globales aux lignes cochées
    if appliquer_a_tous:
        if largeur_globale is None and hauteur_globale is None:
            st.warning("Renseigne au moins une dimension commune avant d'appliquer.")
        else:
            mask_coches = df["Modifier"] == True
            if not mask_coches.any():
                # Si rien n'est coché, appliquer à tout le monde
                mask_coches = pd.Series([True] * len(df))
            if largeur_globale is not None:
                df.loc[mask_coches, "Nouvelle largeur"] = float(largeur_globale)
            if hauteur_globale is not None:
                df.loc[mask_coches, "Nouvelle hauteur"] = float(hauteur_globale)
            st.session_state["df_dashboards"] = df

    edited_df = st.data_editor(
        df,
        column_config={
            "Modifier": st.column_config.CheckboxColumn("Modifier", width="small"),
            "Dashboard": st.column_config.TextColumn("Dashboard", disabled=True),
            "Largeur actuelle": st.column_config.TextColumn("Largeur act.", disabled=True, width="small"),
            "Hauteur actuelle": st.column_config.TextColumn("Hauteur act.", disabled=True, width="small"),
            "Nouvelle largeur": st.column_config.NumberColumn(
                "Nouvelle largeur", min_value=1, max_value=3000, step=1, width="medium"
            ),
            "Nouvelle hauteur": st.column_config.NumberColumn(
                "Nouvelle hauteur", min_value=1, max_value=6000, step=1, width="medium"
            ),
        },
        hide_index=True,
        use_container_width=True,
        key="data_editor"
    )

    # Synchroniser les éditions manuelles dans session_state
    st.session_state["df_dashboards"] = edited_df

    # ── Options globales (toggles) ───────────────────────────────────
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

    # ── #8 — Bouton désactivé si aucune ligne cochée ─────────────────
    nb_coches = int(edited_df["Modifier"].sum())
    bouton_desactive = nb_coches == 0

    st.write("")
    if st.button(
        f"Modifier ({nb_coches} dashboard{'s' if nb_coches > 1 else ''} sélectionné{'s' if nb_coches > 1 else ''})",
        type="primary",
        disabled=bouton_desactive,
    ):
        selection = edited_df[edited_df["Modifier"]]

        # Validation : dimensions renseignées pour toutes les lignes cochées
        lignes_incompletes = selection[
            selection["Nouvelle largeur"].isna() | selection["Nouvelle hauteur"].isna()
        ]
        if not lignes_incompletes.empty:
            noms = ", ".join(lignes_incompletes["Dashboard"].tolist())
            st.error(f"Dimensions manquantes pour : **{noms}**")
            return

        modifications = {
            row["Dashboard"]: (int(row["Nouvelle largeur"]), int(row["Nouvelle hauteur"]))
            for _, row in selection.iterrows()
        }

        try:
            fichier_modifie = modifier_tableaux_de_bord(
                xml_content, modifications, deplacer_droite, deplacer_bas
            )
            st.success(f"✅ {nb_coches} dashboard(s) modifié(s) avec succès.")
            nom_base = xml_file.name.replace(".twbx", "").replace(".twb", "")
            st.download_button(
                label="⬇️ Télécharger le fichier modifié",
                data=fichier_modifie,
                file_name=f"{nom_base}_modifié.twb",
                mime="application/xml",
            )
        except ValueError as e:
            st.error(str(e))


if __name__ == "__main__":
    main()
