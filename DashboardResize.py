import streamlit as st
import streamlit_antd_components as sac
import xml.etree.ElementTree as ET
from io import BytesIO
import pandas as pd


# ─────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────

def recuperer_dashboards_avec_tailles(xml_content):
    """Retourne une liste de dicts {name, width, height} pour chaque dashboard."""
    tree = ET.parse(xml_content)
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

def modifier_tableaux_de_bord(xml_content, modifications: dict,
                               deplacer_droite: bool, deplacer_bas: bool):
    """
    modifications: {dashboard_name: (nouvelle_largeur, nouvelle_hauteur)}
    Traite tous les dashboards sélectionnés en une seule passe XML.
    """
    tree = ET.parse(xml_content)
    root = tree.getroot()

    for dashboard in root.findall(".//dashboard"):
        name = dashboard.get("name")
        if name not in modifications:
            continue

        nouvelle_largeur, nouvelle_hauteur = modifications[name]

        # Mettre à jour la taille du dashboard
        for size in dashboard.findall("./size"):
            maxwidth  = float(size.get("maxwidth")  or 1.0)
            maxheight = float(size.get("maxheight") or 1.0)
            size.set("maxwidth",  str(nouvelle_largeur))
            size.set("minwidth",  str(nouvelle_largeur))
            size.set("maxheight", str(nouvelle_hauteur))
            size.set("minheight", str(nouvelle_hauteur))

        # Recalculer les zones
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
    tree.write(output, encoding="unicode", xml_declaration=False)
    output.seek(0)
    return output


# ─────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────

def main():
    st.title("Modification de Tableau de Bord")

    xml_file = st.file_uploader("Uploader le fichier .twb", type=["twb"])

    if xml_file is None or not xml_file.name.endswith(".twb"):
        return

    xml_content = xml_file.read()
    dashboards = recuperer_dashboards_avec_tailles(BytesIO(xml_content))

    if not dashboards:
        st.warning("Aucun dashboard trouvé dans ce fichier.")
        return

    # ── Tableau éditeur ──────────────────────────────────────────────
    st.subheader("Dashboards à modifier")
    st.caption("Cochez les dashboards à modifier et renseignez les nouvelles dimensions.")

    df = pd.DataFrame([
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
    )

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

    # ── Action ──────────────────────────────────────────────────────
    if st.button("Modifier", type="primary"):
        selection = edited_df[edited_df["Modifier"] == True]

        if selection.empty:
            st.warning("Sélectionne au moins un dashboard.")
            return

        # Validation : toutes les lignes sélectionnées ont des dimensions
        lignes_incompletes = selection[
            selection["Nouvelle largeur"].isna() | selection["Nouvelle hauteur"].isna()
        ]
        if not lignes_incompletes.empty:
            noms = ", ".join(lignes_incompletes["Dashboard"].tolist())
            st.error(f"Dimensions manquantes pour : {noms}")
            return

        modifications = {
            row["Dashboard"]: (int(row["Nouvelle largeur"]), int(row["Nouvelle hauteur"]))
            for _, row in selection.iterrows()
        }

        try:
            fichier_modifie = modifier_tableaux_de_bord(
                BytesIO(xml_content), modifications, deplacer_droite, deplacer_bas
            )
            nb = len(modifications)
            st.success(f"{nb} dashboard(s) modifié(s) avec succès.")
            st.download_button(
                label="⬇️ Télécharger le fichier modifié",
                data=fichier_modifie,
                file_name=f"{xml_file.name.replace('.twb', '')}_modifié.twb",
                mime="application/xml",
            )
        except ValueError as e:
            st.error(str(e))


if __name__ == "__main__":
    main()
