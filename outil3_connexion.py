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

