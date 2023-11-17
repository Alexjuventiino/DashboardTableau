import streamlit as st
import xml.etree.ElementTree as ET

def calculer_nouvelles_valeurs(x, w, maxwidth, nouvelle_largeur):
    nouveau_x = x * (100000 / maxwidth) / (100000 / nouvelle_largeur)
    nouveau_w = w * (100000 / maxwidth) / (100000 / nouvelle_largeur)
    return int(nouveau_x), int(nouveau_w)

def modifier_tableau_de_bord(xml_path, nouvelle_largeur, dashboard_name):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    for dashboard in root.findall(".//dashboard[@name='"+dashboard_name+"']"):
        for size in dashboard.findall(".//size"):
            maxwidth = float(size.get("maxwidth", 1.0))
            size.set("maxwidth", str(nouvelle_largeur))
            size.set("minwidth", str(nouvelle_largeur))

        for zone in dashboard.findall(".//zone"):
            x = int(zone.get("x", 0))
            w = int(zone.get("w", 0))
            nouveau_x, nouveau_w = calculer_nouvelles_valeurs(x, w, maxwidth, nouvelle_largeur)
            zone.set("x", str(nouveau_x))
            zone.set("w", str(nouveau_w))

    nouveau_nom_fichier = "nouveau_fichier.twb"
    tree.write(nouveau_nom_fichier)
    return nouveau_nom_fichier

def main():
    st.title("Modification de Tableau de Bord")

    # Sidebar
    nouvelle_largeur = st.sidebar.slider("Nouvelle Largeur du Tableau de Bord", 500, 5000, 2000)
    dashboard_name = st.sidebar.text_input("Nom du Tableau de Bord", "Tableau de bord 2")
    xml_path = st.sidebar.file_uploader("Uploader le fichier .twb", type=["twb"])

    if xml_path:
        st.sidebar.button("Modifier", on_click=lambda: modifier_tableau_de_bord(xml_path, nouvelle_largeur, dashboard_name))

if __name__ == "__main__":
    main()
