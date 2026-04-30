import xml.etree.ElementTree as ET
from io import BytesIO
import zipfile


def extraire_twb_depuis_twbx(file_bytes: bytes) -> bytes:
    with zipfile.ZipFile(BytesIO(file_bytes)) as z:
        twb_names = [n for n in z.namelist() if n.endswith(".twb")]
        if not twb_names:
            raise ValueError("Aucun fichier .twb trouvé dans l'archive .twbx.")
        with z.open(twb_names[0]) as f:
            return f.read()


def charger_contenu_xml(uploaded_file) -> bytes:
    raw = uploaded_file.read()
    if uploaded_file.name.endswith(".twbx"):
        return extraire_twb_depuis_twbx(raw)
    return raw


def parser_xml(xml_content: bytes) -> ET.ElementTree:
    try:
        return ET.parse(BytesIO(xml_content))
    except ET.ParseError as e:
        raise ValueError(f"Le fichier XML est malformé : {e}")


def serialiser_xml(tree: ET.ElementTree) -> BytesIO:
    output = BytesIO()
    tree.write(output, encoding="utf-8", xml_declaration=True)
    output.seek(0)
    return output
