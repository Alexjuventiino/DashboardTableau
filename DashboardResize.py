import streamlit as st
import xml.etree.ElementTree as ET
from io import BytesIO

def calculer_nouvelles_valeurs(x, w, y, h, maxwidth, maxheight, nouvelle_largeur, nouvelle_hauteur):
    nouveau_x = x / (100000 / maxwidth) * (100000 / nouvelle_largeur)
    nouveau_w = w / (100000 / maxwidth) * (100000 / nouvelle_largeur)
    nouveau_y = y / (100000 / maxheight) * (100000 / nouvelle_hauteur)
    nouveau_h = h / (100000 / maxheight) * (100000 / nouvelle_hauteur)
    return int(nouveau_x), int(nouveau_w), int(nouveau_y), int(nouveau_h)

def recuperer_noms_dashboards(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    return [dashboard.get("name") for dashboard in root.findall(".//dashboard")]

def modifier_tableau_de_bord(xml_path, nouvelle_largeur, nouvelle_hauteur, dashboards_a_modifier):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    for dashboard in root.findall(".//dashboard[@name='"+dashboards_a_modifier+"']"):
        for size in dashboard.findall(".//size"):
            maxwidth = float(size.get("maxwidth", 1.0))
            size.set("maxwidth", str(nouvelle_largeur))
            size.set("minwidth", str(nouvelle_largeur))
            maxheight = float(size.get("maxheight", 1.0))
            size.set("maxheight", str(nouvelle_hauteur))
            size.set("minheight", str(nouvelle_hauteur))

        for zone in dashboard.findall(".//zone"):
            x = int(zone.get("x", 0))
            w = int(zone.get("w", 0))
            y = int(zone.get("y", 0))
            h = int(zone.get("h", 0))
            nouveau_x, nouveau_w, nouveau_y, nouveau_h = calculer_nouvelles_valeurs(x, w, y, h, maxwidth, maxheight, nouvelle_largeur, nouvelle_hauteur)
            zone.set("x", str(nouveau_x))
            zone.set("w", str(nouveau_w))
            zone.set("y", str(nouveau_y))
            zone.set("h", str(nouveau_h))

    nouveau_nom_fichier = "nouveau_fichier.twb"
    tree.write(nouveau_nom_fichier)
    return nouveau_nom_fichier

def main():
    st.title("Modification de Tableau de Bord")

    # Sidebar
    xml_path = st.sidebar.file_uploader("Uploader le fichier .twb", type=["twb"])
    if xml_path :
        dashboards = recuperer_noms_dashboards(xml_path)
        dashboard_a_modifier = st.sidebar.selectbox("Dashboards à modifier", dashboards)
        st.write('You selected:', dashboard_a_modifier)
        nouvelle_largeur = st.sidebar.number_input("Nouvelle largeur du Tableau de Bord", placeholder="Ex:1600", min_value=1, max_value=3000, value=None, step=1)
        nouvelle_hauteur = st.sidebar.number_input("Nouvelle hauteur du Tableau de Bord", placeholder="Ex:1800", min_value=1, max_value=6000, value=None, step=1)

        if st.sidebar.button("Modifier"):
            fichier_modifie = modifier_tableau_de_bord(xml_path, nouvelle_largeur, nouvelle_hauteur, dashboard_a_modifier)
            # Télécharger le fichier modifié
            st.download_button(
                label="Télécharger le fichier modifié",
                data=BytesIO(open(fichier_modifie, 'rb').read()),
                file_name=fichier_modifie,
                key="download_button"
            )

if __name__ == "__main__":
    main()
