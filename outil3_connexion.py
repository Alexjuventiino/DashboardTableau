import re

from utils import parser_xml, serialiser_xml


def recuperer_catalogues(xml_content: bytes) -> list:
    """
    Retourne la liste des catalogues uniques détectés dans les connexions
    Databricks du fichier TWB.

    Dans le XML Tableau, le catalogue Databricks est stocké dans l'attribut
    'dbname' des éléments <connection class='databricks'> imbriqués dans
    les <named-connection>.

    Chaque entrée retournée contient :
      - catalog  : valeur de dbname (le catalogue Databricks)
      - schema   : valeur de schema (la base de données / schéma)
      - server   : le serveur Databricks
    """
    tree = parser_xml(xml_content)
    root = tree.getroot()

    vus = set()
    connexions = []

    for conn in root.iter("connection"):
        if conn.get("class") != "databricks":
            continue
        catalog = conn.get("dbname", "")
        if not catalog:
            continue
        cle = (catalog, conn.get("schema", ""), conn.get("server", ""))
        if cle in vus:
            continue
        vus.add(cle)
        connexions.append({
            "catalog":   catalog,
            "schema":    conn.get("schema", ""),
            "server":    conn.get("server", ""),
            "http_path": conn.get("v-http-path", "").strip(),
        })

    return connexions


def remplacer_catalogue(xml_content, catalogue_source: str,
                        catalogue_cible: str) -> tuple:
    """
    Remplace catalogue_source par catalogue_cible dans le fichier TWB.

    Stratégie en deux temps :
    1. Mise à jour XML-aware de l'attribut dbname (connexion Databricks).
    2. Remplacement textuel exhaustif sur le XML sérialisé pour couvrir
       tous les autres contextes : table=, object-id, id, caption, name…
       y compris les tags non-standards _.fcp... et les attributs object-id.

    Retourne (BytesIO, nb_connexions_modifiées).
    """
    if not catalogue_source or not catalogue_cible:
        raise ValueError("Le catalogue source et le catalogue cible ne peuvent pas être vides.")
    if catalogue_source == catalogue_cible:
        raise ValueError("Le catalogue source et le catalogue cible sont identiques.")

    # ── 1. Mise à jour XML du dbname ───────────────────────────────────────
    tree = parser_xml(xml_content)
    root = tree.getroot()
    nb = 0

    for conn in root.iter("connection"):
        if conn.get("class") != "databricks":
            continue
        if conn.get("dbname") == catalogue_source:
            conn.set("dbname", catalogue_cible)
            nb += 1

    if nb == 0:
        raise ValueError(
            f"Aucune connexion Databricks avec le catalogue « {catalogue_source} » "
            "trouvée dans ce fichier."
        )

    # ── 2. Remplacement textuel pour tout le reste ─────────────────────────
    # Les deux seuls contextes où le catalogue apparaît dans un TWB :
    #   [catalogue].[schema].[table]  →  préfixe entre crochets
    #   (catalogue.schema.table)_HASH →  entre parenthèse dans object-id / id
    # Couvre : <relation table=>, <_.fcp...relation>, <object id=>,
    #   <_.fcp...object id=>, <first/second-end-point object-id=>,
    #   <object-id> texte, <column name=>, <datasource caption=>, etc.
    texte = serialiser_xml(tree).getvalue().decode("utf-8")
    texte = texte.replace(f"[{catalogue_source}].", f"[{catalogue_cible}].")
    texte = texte.replace(f"({catalogue_source}.", f"({catalogue_cible}.")

    from io import BytesIO as _BytesIO
    return _BytesIO(texte.encode("utf-8")), nb



def remplacer_serveur(xml_content, serveur_source: str, serveur_cible: str,
                      http_path_source: str, http_path_cible: str) -> tuple:
    """
    Remplace le nom d'hôte du serveur et/ou le chemin HTTP dans tout le fichier TWB.
    Seules les valeurs qui diffèrent de la source sont appliquées.
    Retourne (BytesIO, nb_remplacements).
    """
    if hasattr(xml_content, "read"):
        xml_content.seek(0)
        texte = xml_content.read().decode("utf-8")
    else:
        texte = xml_content.decode("utf-8")

    nb = 0
    sc = serveur_cible.strip()
    hc = http_path_cible.strip()

    if sc and sc != serveur_source:
        nb += texte.count(serveur_source)
        texte = texte.replace(serveur_source, sc)

    if hc and hc != http_path_source:
        nb += texte.count(http_path_source)
        texte = texte.replace(http_path_source, hc)

    if nb == 0:
        raise ValueError("Serveur et chemin HTTP inchangés.")

    from io import BytesIO as _BytesIO
    return _BytesIO(texte.encode("utf-8")), nb


# ─────────────────────────────────────────────────────────────
# TABLES — détection et remplacement de suffixes dbt
# ─────────────────────────────────────────────────────────────

# Pattern pour les requêtes SQL custom : FROM/JOIN schema.table
_RE_SQL_TABLE = re.compile(
    r'(?:FROM|JOIN)\s+([\w]+)\.([\w]+)',
    re.IGNORECASE,
)

# Pattern pour l'attribut table='[catalog].[schema].[table]' ou '[schema].[table]'
_RE_ATTR_TABLE = re.compile(
    r'^(?:\[([^\]]+)\]\.)?\[([^\]]+)\]\.\[([^\]]+)\]$'
)


def recuperer_tables_sql(xml_content: bytes) -> list:
    """
    Extrait toutes les références de table uniques depuis :
    - les requêtes SQL custom (<relation type='text'>) via FROM/JOIN
    - les relations directes (<relation type='table'>) via l'attribut table='[cat].[schema].[table]'

    Retourne une liste de dicts {"source", "catalog", "schema", "table"} triée par table.
    """
    tree = parser_xml(xml_content)
    root = tree.getroot()

    vues = set()
    tables = []

    for rel in root.iter("relation"):
        rel_type = rel.get("type")

        if rel_type == "text":
            sql = rel.text or ""
            for m in _RE_SQL_TABLE.finditer(sql):
                schema, table = m.group(1), m.group(2)
                cle = ("sql", schema, table)
                if cle not in vues:
                    vues.add(cle)
                    tables.append({"source": "SQL", "catalog": "", "schema": schema, "table": table})

        elif rel_type == "table":
            attr = rel.get("table", "")
            # Ignore les relations de l'extrait Hyper : table='[Extract].[...]'
            if attr.startswith("[Extract]."):
                continue
            m = _RE_ATTR_TABLE.match(attr)
            if m:
                catalog = m.group(1) or ""
                schema  = m.group(2)
                table   = m.group(3)
                cle = ("attr", catalog, schema, table)
                if cle not in vues:
                    vues.add(cle)
                    tables.append({"source": "Table directe", "catalog": catalog, "schema": schema, "table": table})

    tables.sort(key=lambda x: (x["schema"], x["table"]))
    return tables


def init_df_tables(tables: list):
    import pandas as pd
    return pd.DataFrame([
        {
            "Modifier":       False,
            "Type":           t["source"],
            "Catalogue":      t["catalog"],
            "Schéma":         t["schema"],
            "Table actuelle": t["table"],
            "Table cible":    t["table"],
        }
        for t in tables
    ])


def _remplacer_table_dans_texte(texte: str, table_act: str, table_cib: str) -> tuple:
    """
    Remplace table_act par table_cib dans un XML sérialisé en chaîne.
    Couvre tous les contextes connus dans les fichiers Tableau TWB :
      [table]  (table)  .table)  table (  ="table"  ='table'  (TitleCased)
    Retourne (nouveau_texte, nb_remplacements).
    """
    esc = re.escape(table_act)
    total = 0

    # Patterns ordonnés du plus spécifique au moins spécifique
    subs = [
        # [table_name] — champs, parent-name, object-id…
        (r'\[' + esc + r'\]',             f'[{table_cib}]'),
        # (table_name) — champs qualifiés [champ (table)]
        (r'\(' + esc + r'\)',             f'({table_cib})'),
        # .table_name) — chemin catalog.schema.table dans object-id
        (r'\.' + esc + r'\)',             f'.{table_cib})'),
        # table_name ( — début des object-id "table (cat.schema.table)_HASH"
        (re.escape(table_act) + r' \(',   f'{table_cib} ('),
        # ="table_name" et ='table_name' — attributs name= caption=
        (r'="' + esc + r'"',              f'="{table_cib}"'),
        (r"='" + esc + r"'",              f"='{table_cib}'"),
    ]
    for pattern, repl in subs:
        texte, n = re.subn(pattern, repl, texte)
        total += n

    # Caption title-cased : "Champ (Table Name Vkho)" → "Champ (Table Name)"
    title_act = table_act.replace("_", " ").title()
    title_cib = table_cib.replace("_", " ").title()
    if title_act != title_cib and title_act in texte:
        texte = texte.replace(title_act, title_cib)

    return texte, total


def remplacer_tables(xml_content, modifications: list) -> tuple:
    """
    Renomme les tables selon la liste de modifications.
    Chaque élément doit avoir les clés : Type, Catalogue, Schéma,
    Table actuelle, Table cible.
    Seules les lignes où Table actuelle != Table cible sont traitées.

    Retourne (BytesIO, nb_occurrences_modifiées).
    """
    modifs = [
        m for m in modifications
        if m["Table actuelle"] != m["Table cible"] and m["Table cible"].strip()
    ]
    if not modifs:
        raise ValueError("Aucune table modifiée (noms source et cible identiques ou cible vide).")

    nb = 0

    # ── Requêtes SQL (type='text') : traitement XML-aware ──────────────────
    sql_modifs = [m for m in modifs if m["Type"] == "SQL"]
    if sql_modifs:
        tree = parser_xml(xml_content)
        root = tree.getroot()
        sql_map = {(m["Schéma"], m["Table actuelle"]): m["Table cible"] for m in sql_modifs}
        for elem in root.iter():
            if elem.get("type") == "text" and elem.text:
                sql = elem.text
                for (schema, table_act), table_cib in sql_map.items():
                    pattern = re.compile(
                        r'((?:FROM|JOIN)\s+' + re.escape(schema) + r'\.)'
                        + re.escape(table_act)
                        + r'(?=\s|$|;|\))',
                        re.IGNORECASE,
                    )
                    sql, n = pattern.subn(r'\g<1>' + table_cib, sql)
                    nb += n
                elem.text = sql
        buf = serialiser_xml(tree)
        xml_bytes = buf.getvalue()
    else:
        if hasattr(xml_content, "read"):
            xml_content.seek(0)
            xml_bytes = xml_content.read()
        else:
            xml_bytes = xml_content

    # ── Tables directes : remplacement textuel exhaustif ───────────────────
    # Cette approche couvre tous les éléments XML Tableau sans les énumérer :
    # <relation>, <_.fcp...relation>, <map>, <local-name>, <column>,
    # <object>, <object-id>, <parent-name>, <expression>, <first/second-end-point>,
    # <column-instance>, <filter>, <field>, <datasource caption>, etc.
    texte = xml_bytes.decode("utf-8")
    for modif in [m for m in modifs if m["Type"] == "Table directe"]:
        texte, n = _remplacer_table_dans_texte(texte, modif["Table actuelle"], modif["Table cible"])
        nb += n

    if nb == 0:
        raise ValueError("Aucune occurrence trouvée dans le fichier.")

    from io import BytesIO as _BytesIO
    return _BytesIO(texte.encode("utf-8")), nb


