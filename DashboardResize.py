import streamlit as st
import xml.etree.ElementTree as ET
from io import BytesIO

def recuperer_noms_dashboards(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    return [dashboard.get("name") for dashboard in root.findall(".//dashboard")]

def calculer_nouvelles_valeurs(x, w, y, h, maxwidth, maxheight, nouvelle_largeur, nouvelle_hauteur):
    nouveau_x = x / (100000 / maxwidth) * (100000 / nouvelle_largeur)
    nouveau_w = w / (100000 / maxwidth) * (100000 / nouvelle_largeur)
    nouveau_y = y / (100000 / maxheight) * (100000 / nouvelle_hauteur)
    nouveau_h = h / (100000 / maxheight) * (100000 / nouvelle_hauteur)
    return int(nouveau_x), int(nouveau_w), int(nouveau_y), int(nouveau_h)

def modifier_tableau_de_bord(xml_path, nouvelle_largeur, nouvelle_hauteur, dashboard_name):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    for dashboard in root.findall(".//dashboard[@name='"+dashboard_name+"']"):
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
    dashboard_name = st.sidebar.text_input("Nom du Tableau de Bord", placeholder="Ex: Overview")
    nouvelle_largeur = st.sidebar.number_input("Nouvelle largeur du Tableau de Bord",placeholder="Ex:1600",min_value=1, max_value=3000, value=None, step=1)
    nouvelle_hauteur = st.sidebar.number_input("Nouvelle hauteur du Tableau de Bord",placeholder="Ex:1800",min_value=1, max_value=6000, value=None, step=1)
    xml_path = st.sidebar.file_uploader("Uploader le fichier .twb", type=["twb"])
    dashboards = recuperer_noms_dashboards(xml_path)
    st.write(ET.parse(xml_path))

    if xml_path:
        if st.sidebar.button("Modifier"):
            fichier_modifie = modifier_tableau_de_bord(xml_path, nouvelle_largeur, nouvelle_hauteur, dashboard_name)

            # Télécharger le fichier modifié
            st.download_button(
                label="Télécharger le fichier modifié",
                data=BytesIO(open(fichier_modifie, 'rb').read()),
                file_name=fichier_modifie,
                key="download_button"
            )

if __name__ == "__main__":
    main()
