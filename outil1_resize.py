import pandas as pd
from utils import parser_xml, serialiser_xml


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
                               deplacer_droite: bool, deplacer_bas: bool):
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
