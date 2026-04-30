from utils import parser_xml, serialiser_xml


def recuperer_catalogues(xml_content: bytes) -> list:
    """
    Retourne la liste des catalogues uniques détectés dans le fichier TWB.
    Chaque entrée contient le catalogue, le serveur et la base de données
    pour permettre à l'utilisateur d'identifier la connexion.
    """
    tree = parser_xml(xml_content)
    root = tree.getroot()

    vus = set()
    connexions = []

    for conn in root.iter("connection"):
        catalog = conn.get("catalog", "")
        if not catalog:
            continue
        cle = (catalog, conn.get("server", ""), conn.get("database", ""))
        if cle in vus:
            continue
        vus.add(cle)
        connexions.append({
            "catalog":  catalog,
            "server":   conn.get("server", ""),
            "database": conn.get("database", ""),
            "class":    conn.get("class", ""),
        })

    return connexions


def remplacer_catalogue(xml_content: bytes, catalogue_source: str,
                        catalogue_cible: str) -> tuple:
    """
    Remplace catalogue_source par catalogue_cible dans toutes les occurrences :
      - attribut 'catalog' des éléments <connection>
      - attribut 'catalog' des éléments <relation>
      - chemins de table de la forme [catalogue_source].[schema].[table]

    Retourne (BytesIO, nb_remplacements).
    Lève ValueError si aucune occurrence n'est trouvée.
    """
    if not catalogue_source or not catalogue_cible:
        raise ValueError("Le catalogue source et le catalogue cible ne peuvent pas être vides.")
    if catalogue_source == catalogue_cible:
        raise ValueError("Le catalogue source et le catalogue cible sont identiques.")

    tree = parser_xml(xml_content)
    root = tree.getroot()
    nb = 0

    # 1. Attribut 'catalog' dans <connection>
    for conn in root.iter("connection"):
        if conn.get("catalog") == catalogue_source:
            conn.set("catalog", catalogue_cible)
            nb += 1

    # 2. Attribut 'catalog' dans <relation>
    for rel in root.iter("relation"):
        if rel.get("catalog") == catalogue_source:
            rel.set("catalog", catalogue_cible)
            nb += 1
        # Chemin complet [catalogue].[schema].[table] dans l'attribut 'table'
        table_attr = rel.get("table", "")
        if f"[{catalogue_source}]" in table_attr:
            rel.set("table", table_attr.replace(f"[{catalogue_source}]", f"[{catalogue_cible}]"))
            nb += 1

    if nb == 0:
        raise ValueError(
            f"Aucune occurrence du catalogue « {catalogue_source} » trouvée dans ce fichier."
        )

    return serialiser_xml(tree), nb
