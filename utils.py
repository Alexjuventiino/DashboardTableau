import xml.etree.ElementTree as ET
from io import BytesIO
import zipfile
import os
import urllib.request

try:
    from lxml import etree
    LXML_AVAILABLE = True
except ImportError:
    LXML_AVAILABLE = False

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


# ═══════════════════════════════════════════════════════════════
# VALIDATION XSD
# ═══════════════════════════════════════════════════════════════

XSD_URL = "https://raw.githubusercontent.com/tableau/tableau-document-schemas/main/schemas/2026_2/twb_2026.2.0.xsd"

# Cache en mémoire pour éviter de re-télécharger à chaque validation
_xsd_schema_cache = None


def _charger_xsd_schema():
    """
    Charge le schéma XSD depuis GitHub (avec cache en mémoire).
    Fallback sur le fichier local si le téléchargement échoue.
    """
    global _xsd_schema_cache
    if _xsd_schema_cache is not None:
        return _xsd_schema_cache, None

    # 1. Essai depuis GitHub (raw)
    try:
        with urllib.request.urlopen(XSD_URL, timeout=5) as resp:
            xsd_bytes = resp.read()
        xsd_doc = etree.parse(BytesIO(xsd_bytes))
        _xsd_schema_cache = etree.XMLSchema(xsd_doc)
        return _xsd_schema_cache, None
    except Exception:
        pass

    # 2. Fallback : chercher localement
    chemins_locaux = [
        r"c:\Users\Idir\Downloads\tableau-document-schemas-main\tableau-document-schemas-main\schemas\2026_2\twb_2026.2.0.xsd",
        r".\schemas\twb_2026.2.0.xsd",
        r"./schemas/twb_2026.2.0.xsd",
    ]
    for cp in chemins_locaux:
        if os.path.exists(cp):
            try:
                xsd_doc = etree.parse(cp)
                _xsd_schema_cache = etree.XMLSchema(xsd_doc)
                return _xsd_schema_cache, None
            except Exception:
                pass

    return None, "⚠️ Schéma XSD non disponible (GitHub inaccessible et aucun fichier local trouvé)"


def valider_twb_contre_xsd(twb_content: bytes, chemin_xsd: str = None) -> tuple[bool, list]:
    """
    Valide le contenu TWB contre le schéma XSD Tableau (GitHub ou local).

    Args:
        twb_content: Contenu XML du .twb (bytes)
        chemin_xsd: Chemin local vers un .xsd (optionnel, prioritaire si fourni)

    Returns:
        (est_valide, erreurs) où erreurs est une liste de messages d'erreur
    """
    if not LXML_AVAILABLE:
        return True, ["⚠️ lxml non disponible - validation XSD ignorée"]

    try:
        # Si un chemin local explicite est fourni, l'utiliser directement
        if chemin_xsd and os.path.exists(chemin_xsd):
            xsd_doc = etree.parse(chemin_xsd)
            schema = etree.XMLSchema(xsd_doc)
        else:
            schema, erreur_chargement = _charger_xsd_schema()
            if schema is None:
                return True, [erreur_chargement]

        twb_doc = etree.parse(BytesIO(twb_content))
        est_valide = schema.validate(twb_doc)

        if not est_valide:
            return False, [str(e) for e in schema.error_log]
        return True, []

    except etree.XMLSyntaxError as e:
        return False, [f"Erreur syntaxe XML: {str(e)}"]
    except Exception as e:
        return False, [f"Erreur validation: {str(e)}"]


def obtenir_infos_validation(twb_content: bytes) -> dict:
    """
    Retourne des infos de validation pour affichage dans l'UI.
    
    Returns:
        {
            "valide": bool,
            "messages": [str],  # Messages d'erreur/avertissement
            "nb_erreurs": int,
            "resume": str  # Résumé court pour affichage
        }
    """
    est_valide, erreurs = valider_twb_contre_xsd(twb_content)
    
    return {
        "valide": est_valide,
        "messages": erreurs,
        "nb_erreurs": len(erreurs),
        "resume": "✅ Validé" if est_valide else f"❌ {len(erreurs)} erreur(s)"
    }
