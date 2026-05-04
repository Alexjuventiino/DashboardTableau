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
            "catalog": catalog,
            "schema":  conn.get("schema", ""),
            "server":  conn.get("server", ""),
        })

    return connexions


def remplacer_catalogue(xml_content: bytes, catalogue_source: str,
                        catalogue_cible: str) -> tuple:
    """
    Remplace catalogue_source par catalogue_cible dans l'attribut 'dbname'
    de tous les éléments <connection class='databricks'> du fichier TWB.

    Retourne (BytesIO, nb_remplacements).
    Lève ValueError si aucune occurrence n'est trouvée ou si les arguments
    sont invalides.
    """
    if not catalogue_source or not catalogue_cible:
        raise ValueError("Le catalogue source et le catalogue cible ne peuvent pas être vides.")
    if catalogue_source == catalogue_cible:
        raise ValueError("Le catalogue source et le catalogue cible sont identiques.")

    tree = parser_xml(xml_content)
    root = tree.getroot()
    nb = 0

    for conn in root.iter("connection"):
        if conn.get("class") != "databricks":
            continue
        if conn.get("dbname") == catalogue_source:
            conn.set("dbname", catalogue_cible)
            nb += 1

    # Met à jour le catalogue dans les <object-id> des metadata-records.
    # Format : [table (catalog.schema.table)_HASH]
    for oid in root.iter("object-id"):
        if oid.text and catalogue_source in oid.text:
            oid.text = oid.text.replace(
                f"({catalogue_source}.",
                f"({catalogue_cible}.",
            )

    # Met à jour le catalogue dans l'attribut table='[catalog].[schema].[table]'
    # de tous les <relation type='table'> (y compris dans <object-graph>).
    old_prefix = f"[{catalogue_source}]."
    new_prefix = f"[{catalogue_cible}]."
    for rel in root.iter("relation"):
        if rel.get("type") != "table":
            continue
        attr = rel.get("table", "")
        if attr.startswith(old_prefix):
            rel.set("table", new_prefix + attr[len(old_prefix):])

    # Met à jour le caption des datasources qui contiennent le catalogue.
    for ds in root.iter("datasource"):
        caption = ds.get("caption", "")
        if catalogue_source in caption:
            ds.set("caption", caption.replace(catalogue_source, catalogue_cible))

    if nb == 0:
        raise ValueError(
            f"Aucune connexion Databricks avec le catalogue « {catalogue_source} » "
            "trouvée dans ce fichier."
        )

    return serialiser_xml(tree), nb


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


def remplacer_tables(xml_content: bytes, modifications: list) -> tuple:
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

    tree = parser_xml(xml_content)
    root = tree.getroot()
    nb = 0

    # Deux maps selon le type de relation
    sql_map  = {}   # (schema, table_actuelle) → table_cible
    attr_map = {}   # (catalog, schema, table_actuelle) → table_cible

    for m in modifs:
        if m["Type"] == "SQL":
            sql_map[(m["Schéma"], m["Table actuelle"])] = m["Table cible"]
        else:
            attr_map[(m["Catalogue"], m["Schéma"], m["Table actuelle"])] = m["Table cible"]

    for rel in root.iter("relation"):
        rel_type = rel.get("type")

        if rel_type == "text" and rel.text and sql_map:
            sql = rel.text
            for (schema, table_act), table_cib in sql_map.items():
                pattern = re.compile(
                    r'((?:FROM|JOIN)\s+' + re.escape(schema) + r'\.)'
                    + re.escape(table_act)
                    + r'(?=\s|$|;|\))',
                    re.IGNORECASE,
                )
                nouveau_sql, n = pattern.subn(r'\g<1>' + table_cib, sql)
                if n:
                    sql = nouveau_sql
                    nb += n
            rel.text = sql

        elif rel_type == "table" and attr_map:
            attr = rel.get("table", "")
            m_re = _RE_ATTR_TABLE.match(attr)
            if m_re:
                catalog = m_re.group(1) or ""
                schema  = m_re.group(2)
                table   = m_re.group(3)
                key = (catalog, schema, table)
                if key in attr_map:
                    table_cib = attr_map[key]
                    if catalog:
                        rel.set("table", f"[{catalog}].[{schema}].[{table_cib}]")
                    else:
                        rel.set("table", f"[{schema}].[{table_cib}]")
                    nb += 1

            name = rel.get("name", "")
            for modif in modifs:
                if modif["Type"] == "Table directe" and name == modif["Table actuelle"]:
                    rel.set("name", modif["Table cible"])
                    nb += 1
                    break

    # Pour les tables directes : met à jour <parent-name> et <object-id>
    # dans les metadata-records.
    for modif in [m for m in modifs if m["Type"] == "Table directe"]:
        table_act = modif["Table actuelle"]
        table_cib = modif["Table cible"]

        # <parent-name>[table_actuelle]</parent-name>
        for pn in root.iter("parent-name"):
            if pn.text == f"[{table_act}]":
                pn.text = f"[{table_cib}]"

        # <object-id>[table_actuelle (catalog.schema.table_actuelle)_HASH]</object-id>
        for oid in root.iter("object-id"):
            if not oid.text:
                continue
            new_text = oid.text
            # Remplace le nom au début : [old_table (
            new_text = new_text.replace(f"[{table_act} (", f"[{table_cib} (")
            # Remplace le nom dans le chemin : .old_table)
            new_text = re.sub(
                r'\.' + re.escape(table_act) + r'\)',
                '.' + table_cib + ')',
                new_text,
            )
            oid.text = new_text

        # <datasource caption='table_actuelle (...)'>
        for ds in root.iter("datasource"):
            caption = ds.get("caption", "")
            if table_act in caption:
                ds.set("caption", caption.replace(table_act, table_cib))

    if nb == 0:
        raise ValueError("Aucune occurrence trouvée dans le fichier.")

    return serialiser_xml(tree), nb

