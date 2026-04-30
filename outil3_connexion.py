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

    if nb == 0:
        raise ValueError(
            f"Aucune connexion Databricks avec le catalogue « {catalogue_source} » "
            "trouvée dans ce fichier."
        )

    return serialiser_xml(tree), nb


# ─────────────────────────────────────────────────────────────
# TABLES — détection et remplacement de suffixes dbt
# ─────────────────────────────────────────────────────────────

_RE_TABLE = re.compile(
    r'(?:FROM|JOIN)\s+([\w]+)\.([\w]+)',
    re.IGNORECASE,
)


def recuperer_tables_sql(xml_content: bytes) -> list:
    """
    Extrait toutes les références schema.table uniques depuis les requêtes SQL
    custom (éléments <relation type='text'>) des connexions Databricks.

    Retourne une liste de dicts {"schema": ..., "table": ...} triée par table.
    """
    tree = parser_xml(xml_content)
    root = tree.getroot()

    vues = set()
    tables = []

    for rel in root.iter("relation"):
        if rel.get("type") != "text":
            continue
        sql = rel.text or ""
        for m in _RE_TABLE.finditer(sql):
            schema, table = m.group(1), m.group(2)
            cle = (schema, table)
            if cle not in vues:
                vues.add(cle)
                tables.append({"schema": schema, "table": table})

    tables.sort(key=lambda x: (x["schema"], x["table"]))
    return tables


def apercu_remplacement_suffixe(tables: list, suffixe: str) -> list:
    """
    Retourne la liste des tables dont le nom se termine par suffixe,
    avec leur nom cible (sans le suffixe).
    Chaque entrée : {"schema", "table_actuelle", "table_cible"}.
    """
    if not suffixe:
        return []
    return [
        {
            "schema":        t["schema"],
            "table_actuelle": t["table"],
            "table_cible":   t["table"][: -len(suffixe)],
        }
        for t in tables
        if t["table"].endswith(suffixe)
    ]


def remplacer_suffixe_tables(xml_content: bytes, suffixe: str) -> tuple:
    """
    Dans toutes les requêtes SQL custom (relation type='text'), remplace
    chaque occurrence de « schema.table<suffixe> » par « schema.table ».

    Retourne (BytesIO, nb_remplacements).
    Lève ValueError si aucune occurrence n'est trouvée.
    """
    if not suffixe:
        raise ValueError("Le suffixe ne peut pas être vide.")

    tree = parser_xml(xml_content)
    root = tree.getroot()
    nb = 0

    # Regex qui capture schema.table suivi exactement du suffixe,
    # sans prolongement (word boundary ou fin de token SQL)
    pattern = re.compile(
        r'((?:FROM|JOIN)\s+\w+\.\w+)' + re.escape(suffixe) + r'(?=\s|$|;|\))',
        re.IGNORECASE,
    )

    for rel in root.iter("relation"):
        if rel.get("type") != "text" or not rel.text:
            continue
        nouveau_sql, n = pattern.subn(r'\1', rel.text)
        if n:
            rel.text = nouveau_sql
            nb += n

    if nb == 0:
        raise ValueError(
            f"Aucune table avec le suffixe « {suffixe} » trouvée dans les requêtes SQL."
        )

    return serialiser_xml(tree), nb

