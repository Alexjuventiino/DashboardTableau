import re
import xml.etree.ElementTree as ET
import pandas as pd
from utils import parser_xml, serialiser_xml


MODES = {
    "":              "Liste complète (défaut)",
    "compact":       "Compact (plage numérique)",
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


# ─────────────────────────────────────────────────────────────
# AJOUTER DES FILTRES AUX DASHBOARDS
# ─────────────────────────────────────────────────────────────

def recuperer_feuilles_par_dashboard(xml_content) -> dict:
    """
    Retourne {dashboard_name: [sheet_name, ...]} — les feuilles utilisées dans
    chaque dashboard (hors feuilles utilitaires commençant par '_').
    """
    tree = parser_xml(xml_content)
    root = tree.getroot()
    result = {}
    for dash in root.iter('dashboard'):
        if dash.get('type'):
            continue
        dash_name = dash.get('name', '')
        sheets_seen = set()
        sheets = []
        for z in dash.iter('zone'):
            zname = z.get('name', '')
            tv2   = z.get('type-v2', '')
            if zname and tv2 == '' and not zname.startswith('_'):
                if zname not in sheets_seen:
                    sheets_seen.add(zname)
                    sheets.append(zname)
        if sheets:
            result[dash_name] = sheets
    return result


def recuperer_champs_feuille(xml_content, feuille: str) -> list:
    """
    Retourne la liste des champs disponibles dans une feuille pour être
    ajoutés comme filtres de dashboard.

    Chaque entrée :
      {"datasource", "instance_name", "field_name", "display_name",
       "datatype", "type", "column_attribs", "instance_attribs"}
    """
    tree = parser_xml(xml_content)
    root = tree.getroot()
    champs = []
    for ws in root.iter('worksheet'):
        if ws.get('name', '') != feuille:
            continue
        for dep in ws.iter('datasource-dependencies'):
            ds_name = dep.get('datasource', '')
            if ds_name == 'Parameters':
                continue
            col_lookup = {c.get('name', ''): dict(c.attrib) for c in dep.findall('column')}
            for ci in dep.findall('column-instance'):
                if ci.get('derivation', '') != 'None':
                    continue
                instance_name = ci.get('name', '')
                field_name    = ci.get('column', '')
                ci_type       = ci.get('type', 'nominal')
                col_attribs   = col_lookup.get(field_name, {})
                display       = col_attribs.get('caption', '') or extraire_nom_champ(instance_name)
                champs.append({
                    'datasource':       ds_name,
                    'instance_name':    instance_name,
                    'field_name':       field_name,
                    'display_name':     display,
                    'datatype':         col_attribs.get('datatype', 'string'),
                    'type':             ci_type,
                    'column_attribs':   col_attribs,
                    'instance_attribs': dict(ci.attrib),
                })
        break
    return champs


def _max_zone_id(root) -> int:
    max_id = 0
    for z in root.iter('zone'):
        try:
            id_val = int(z.get('id', '0'))
            if id_val > max_id:
                max_id = id_val
        except (ValueError, TypeError):
            pass
    return max_id


def _trouver_panneau_filtres(zones_elem):
    """
    Cherche le layout-flow vert pour les filtres dans <zones> uniquement
    (pas dans devicelayouts).
    Priorité : vert qui a déjà un enfant filter/paramctrl, sinon premier vert.
    """
    if zones_elem is None:
        return None
    for z in zones_elem.iter('zone'):
        if z.get('type-v2') == 'layout-flow' and z.get('param') == 'vert':
            for child in z:
                if child.get('type-v2') in ('filter', 'paramctrl'):
                    return z
    for z in zones_elem.iter('zone'):
        if z.get('type-v2') == 'layout-flow' and z.get('param') == 'vert':
            return z
    return None


def ajouter_filtres_dashboards(xml_content, spec_list: list) -> tuple:
    """
    spec_list : [{"dashboard": str, "feuille": str, "champs": [instance_name, ...]}]

    Pour chaque spécification :
    1. Ajoute column + column-instance dans les datasource-dependencies du dashboard.
    2. Ajoute une zone filter dans le panneau vertical gauche.

    Retourne (BytesIO, nb_filtres_ajoutés).
    """
    if not spec_list:
        raise ValueError("Aucune spécification fournie.")

    tree = parser_xml(xml_content)
    root = tree.getroot()

    # Pré-calcule les infos de champs par feuille
    ws_fields: dict = {}
    for ws in root.iter('worksheet'):
        ws_name = ws.get('name', '')
        ws_fields[ws_name] = {}
        for dep in ws.iter('datasource-dependencies'):
            ds_name = dep.get('datasource', '')
            if ds_name == 'Parameters':
                continue
            col_lookup = {c.get('name', ''): dict(c.attrib) for c in dep.findall('column')}
            for ci in dep.findall('column-instance'):
                inst  = ci.get('name', '')
                field = ci.get('column', '')
                ws_fields[ws_name][inst] = {
                    'datasource':       ds_name,
                    'instance_name':    inst,
                    'field_name':       field,
                    'type':             ci.get('type', 'nominal'),
                    'column_attribs':   col_lookup.get(field, {}),
                    'instance_attribs': dict(ci.attrib),
                }

    nb_total = 0
    next_id  = _max_zone_id(root) + 1

    for spec in spec_list:
        dash_name = spec['dashboard']
        feuille   = spec['feuille']
        champs    = spec.get('champs', [])
        if not champs:
            continue

        dash_elem = next(
            (d for d in root.iter('dashboard') if d.get('name', '') == dash_name),
            None,
        )
        if dash_elem is None:
            continue

        sheet_fi = ws_fields.get(feuille, {})

        # Trouve l'index d'insertion sûr pour datasource-dependencies
        # La dépendance ne peut être ajoutée que si <datasources> existe déjà
        # (le schéma exige : ...datasources, datasource-dependencies*, zones...)
        _has_datasources = dash_elem.find('datasources') is not None

        def _get_dep(ds_name: str):
            if not _has_datasources:
                return None  # pas de <datasources> → on ne peut pas ajouter de dep
            for dep in dash_elem.findall('datasource-dependencies'):
                if dep.get('datasource', '') == ds_name:
                    return dep
            # Insérer juste avant <zones>
            zones_idx = next(
                (i for i, c in enumerate(dash_elem) if c.tag == 'zones'),
                len(list(dash_elem)),
            )
            dep = ET.Element('datasource-dependencies')
            dep.set('datasource', ds_name)
            dash_elem.insert(zones_idx, dep)
            return dep

        zones_el = dash_elem.find('zones')
        panel = _trouver_panneau_filtres(zones_el)

        # Si aucun panneau filtres n'existe, on en crée un
        if panel is None and zones_el is not None:
            layout_basic = zones_el.find('zone')  # premier <zone> direct
            if layout_basic is not None:
                # Récupère les dimensions de la zone contenu originale
                orig_zone = next((c for c in layout_basic if c.tag == 'zone'), None)
                oz_x = orig_zone.get('x', '0')   if orig_zone is not None else '0'
                oz_y = orig_zone.get('y', '0')   if orig_zone is not None else '0'
                oz_w = orig_zone.get('w', '98000') if orig_zone is not None else '98000'
                oz_h = orig_zone.get('h', '98000') if orig_zone is not None else '98000'
                # Largeur du panneau filtres ≈ 15 % de la largeur totale
                filter_w = max(8000, int(int(oz_w) * 0.15))
                content_w = int(oz_w) - filter_w

                # 1. Vert filtre (le futur panel)
                filter_vert = ET.Element('zone')
                filter_vert.set('id', str(next_id)); next_id += 1
                filter_vert.set('h', oz_h)
                filter_vert.set('param', 'vert')
                filter_vert.set('type-v2', 'layout-flow')
                filter_vert.set('w', str(filter_w))
                filter_vert.set('x', '0')
                filter_vert.set('y', '0')
                ET.SubElement(filter_vert, 'zone-style')

                # 2. Vert contenu — récupère les zones existantes
                content_vert = ET.Element('zone')
                content_vert.set('id', str(next_id)); next_id += 1
                content_vert.set('h', oz_h)
                content_vert.set('param', 'vert')
                content_vert.set('type-v2', 'layout-flow')
                content_vert.set('w', str(content_w))
                content_vert.set('x', str(filter_w))
                content_vert.set('y', '0')
                for cz in [c for c in list(layout_basic) if c.tag == 'zone']:
                    layout_basic.remove(cz)
                    content_vert.append(cz)
                ET.SubElement(content_vert, 'zone-style')

                # 3. Conteneur horz : filtre_vert + content_vert
                horz = ET.Element('zone')
                horz.set('id', str(next_id)); next_id += 1
                horz.set('h', oz_h)
                horz.set('param', 'horz')
                horz.set('type-v2', 'layout-flow')
                horz.set('w', oz_w)
                horz.set('x', oz_x)
                horz.set('y', oz_y)
                horz.append(filter_vert)
                horz.append(content_vert)
                ET.SubElement(horz, 'zone-style')

                # 4. Insère le horz avant zone-style dans layout-basic
                zs_idx = next(
                    (i for i, c in enumerate(layout_basic) if c.tag == 'zone-style'),
                    len(list(layout_basic)),
                )
                layout_basic.insert(zs_idx, horz)
                panel = filter_vert

        if panel is None:
            continue

        existing_params = {
            child.get('param', '')
            for child in panel
            if child.get('type-v2') in ('filter', 'paramctrl')
        }

        for champ_spec in champs:
            # champ_spec peut être une str (instance_name) ou un dict de config
            if isinstance(champ_spec, dict):
                instance_name = champ_spec['instance_name']
            else:
                instance_name = champ_spec

            fi = sheet_fi.get(instance_name)
            if fi is None:
                continue

            ds_name   = fi['datasource']
            param_val = f"[{ds_name}].{instance_name}"

            if param_val in existing_params:
                continue

            dep      = _get_dep(ds_name)
            col_name = fi['field_name']

            if dep is not None:
                if col_name not in {c.get('name', '') for c in dep.findall('column')}:
                    col_el = ET.SubElement(dep, 'column')
                    for k, v in fi['column_attribs'].items():
                        col_el.set(k, v)

                if instance_name not in {c.get('name', '') for c in dep.findall('column-instance')}:
                    ci_el = ET.SubElement(dep, 'column-instance')
                    for k, v in fi['instance_attribs'].items():
                        ci_el.set(k, v)

            # Résolution de la config mode/show_apply/show_all
            if isinstance(champ_spec, dict):
                mode_xml   = champ_spec.get('mode_xml',   'compact' if fi['type'] == 'quantitative' else 'checkdropdown')
                show_apply = champ_spec.get('show_apply', fi['type'] == 'nominal')
                show_all   = champ_spec.get('show_all',   True)
            else:
                mode_xml   = 'compact' if fi['type'] == 'quantitative' else 'checkdropdown'
                show_apply = fi['type'] == 'nominal'
                show_all   = True

            # typeinlist = saisie texte libre → ne charge pas les valeurs depuis la DB
            values_attr = 'typed-value' if mode_xml == 'typeinlist' else 'database'
            # sélection unique → pas de "Tout" (show-all n'a pas de sens)
            if mode_xml in ('dropdown', 'singlevalue'):
                show_all = False

            # Insérer AVANT <zone-style> (doit rester le dernier enfant)
            zone_style_idx = next(
                (i for i, c in enumerate(panel) if c.tag == 'zone-style'),
                len(list(panel)),
            )
            z = ET.Element('zone')
            panel.insert(zone_style_idx, z)
            z.set('h', '6222')
            z.set('id', str(next_id))
            next_id += 1

            if mode_xml:
                z.set('mode', mode_xml)
            if show_all:
                z.set('show-all', 'true')
            if show_apply:
                z.set('show-apply', 'true')

            z.set('name', feuille)
            z.set('param', param_val)
            z.set('type-v2', 'filter')
            z.set('values', values_attr)
            z.set('w', '11716')
            z.set('x', '0')
            z.set('y', '0')
            ET.SubElement(z, 'zone-style')

            existing_params.add(param_val)
            nb_total += 1

    if nb_total == 0:
        raise ValueError(
            "Aucun filtre ajouté — les champs sélectionnés sont déjà présents "
            "ou introuvables dans la feuille source."
        )

    return serialiser_xml(tree), nb_total

