import re
import pandas as pd
from utils import parser_xml, serialiser_xml


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
    vus = set()

    for dashboard in root.findall(".//dashboard"):
        if dashboard.get("type"):
            continue

        dashboard_name = dashboard.get("name")
        for zone in dashboard.findall(".//zone[@type-v2='filter']"):
            zone_id = zone.get("id")
            cle = (dashboard_name, zone_id)

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
            "Nouveau mode":     f["mode_actuel"],
            "Bouton Appliquer": f["show_apply"],
        }
        for f in filtres
    ])


def appliquer_modifications_filtres(xml_content: bytes, df_edited: pd.DataFrame,
                                    filtres_source: list):
    tree = parser_xml(xml_content)
    root = tree.getroot()

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

            if mode_xml == "":
                zone.attrib.pop("mode", None)
            else:
                zone.set("mode", mode_xml)

            if show_apply:
                zone.set("show-apply", "true")
            else:
                zone.attrib.pop("show-apply", None)

    return serialiser_xml(tree)
