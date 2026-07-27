import xml.etree.ElementTree as ET
from io import BytesIO
import zipfile
import os

# Préserver le préfixe 'user:' natif de Tableau lors de la re-sérialisation.
# Sans ça, Python ET remplace xmlns:user par xmlns:ns0, ce qui casse les
# attributs Tableau (user:ui-marker, user:ui-manual-selection, etc.).
ET.register_namespace('user', 'http://www.tableausoftware.com/xml/user')


def extraire_twb_depuis_twbx(file_bytes: bytes) -> tuple[bytes, dict]:
    """
    Extrait le .twb et les ressources (images, etc.) d'un .twbx.
    
    Returns:
        (twb_content, ressources_dict) où ressources_dict = {chemin_original: bytes}
    """
    ressources = {}
    twb_content = None
    
    with zipfile.ZipFile(BytesIO(file_bytes)) as z:
        twb_names = [n for n in z.namelist() if n.endswith(".twb")]
        if not twb_names:
            raise ValueError("Aucun fichier .twb trouvé dans l'archive .twbx.")
        
        # Extraire le .twb
        with z.open(twb_names[0]) as f:
            twb_content = f.read()
        
        # Extraire les ressources (Data/, Images/, etc.) - tout sauf le .twb
        for name in z.namelist():
            if not name.endswith(".twb") and not name.startswith("_rels/") and name != "[Content_Types].xml":
                try:
                    ressources[name] = z.read(name)
                except KeyError:
                    pass
    
    return twb_content, ressources


def charger_contenu_xml(uploaded_file) -> tuple[bytes, str, dict]:
    """
    Charge le contenu XML et détecte le format d'entrée.
    
    Returns:
        (twb_content, format, ressources)
        - twb_content: le XML à modifier
        - format: "twb" ou "twbx"
        - ressources: dict des fichiers supplémentaires (vide si .twb)
    """
    raw = uploaded_file.read()
    
    if uploaded_file.name.endswith(".twbx"):
        twb_content, ressources = extraire_twb_depuis_twbx(raw)
        return twb_content, "twbx", ressources
    else:
        return raw, "twb", {}


def parser_xml(xml_content) -> ET.ElementTree:
    try:
        if hasattr(xml_content, "read"):
            xml_content.seek(0)
            return ET.parse(xml_content)
        return ET.parse(BytesIO(xml_content))
    except ET.ParseError as e:
        raise ValueError(f"Le fichier XML est malformé : {e}")


def serialiser_xml(tree: ET.ElementTree) -> BytesIO:
    output = BytesIO()
    tree.write(output, encoding="utf-8", xml_declaration=True)
    output.seek(0)
    return output


def remballer_twbx(twb_content, ressources: dict, 
                    nom_twb: str = "Workbook.twb") -> BytesIO:
    """
    Crée un fichier .twbx à partir du .twb modifié et des ressources.
    
    Args:
        twb_content: Contenu XML du .twb modifié (bytes ou BytesIO)
        ressources: dict {chemin_original: bytes}
        nom_twb: Nom du fichier .twb dans l'archive
    
    Returns:
        BytesIO contenant le .twbx
    """
    # Convertir en bytes si c'est un BytesIO
    if hasattr(twb_content, 'read'):
        twb_content.seek(0)
        twb_content = twb_content.read()
    
    output = BytesIO()
    
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        # Ajouter le .twb modifié
        z.writestr(nom_twb, twb_content)
        
        # Ajouter toutes les ressources
        for ressource_path, ressource_content in ressources.items():
            z.writestr(ressource_path, ressource_content)
    
    output.seek(0)
    return output
