"""Fichiers Excel de liens — lecture seule, jamais modifiés.

Deux usages :
- ``read_links``       : le fichier de référence (E:\\groupe fb\\…) de l'import
                         automatique Facebook.
- ``extract_links_from_bytes`` : un fichier Excel CHOISI par l'utilisateur
  dans l'interface (bouton « + Fichier Excel ») → ses liens sont copiés dans
  sa liste. Toutes les feuilles, toutes les cellules, sans limite de nombre.

Format de la feuille « Groupes de VENTE » :
    A = numéro · B = nom · C = lien (hyperlien) · D…H = informations
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from . import config

# un lien dans une cellule : http(s)://…, www.… ou facebook.com/…
_URL_RE = re.compile(r"(?<![\w./])(https?://[^\s\"'<>]+|www\.[^\s\"'<>]+|"
                     r"(?:facebook|fb)\.com/[^\s\"'<>]+)", re.IGNORECASE)

# formats lisibles par openpyxl
_XLSX_EXTS = {".xlsx", ".xlsm", ".xltx", ".xltm"}

# colonne du lien dans la feuille
LINK_COL = 3          # C
HEADER_ROWS = 1       # la ligne 1 contient les en-têtes


def blacklist_export_xlsx(entries: list[dict]) -> bytes:
    """Génère un classeur Excel (.xlsx) listant les liens bannis.

    Colonnes : « Lien » · « Banni le » (date). Retourne les octets du
    fichier, prêts à être envoyés en téléchargement à l'utilisateur.
    """
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Liens bannis"
    ws.append(["Lien", "Banni le"])
    for e in entries or []:
        ws.append([e.get("url", ""), e.get("ts", "")])
    ws.column_dimensions["A"].width = 70
    ws.column_dimensions["B"].width = 20
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _sheet(wb):
    """Feuille des groupes : nom exact, sinon la première feuille."""
    for name in ("Groupes de VENTE",):
        if name in wb.sheetnames:
            return wb[name]
    return wb.active


def read_links(path: Path | None = None) -> list[str]:
    """Liens déjà présents dans le fichier (colonne C, sous les en-têtes)."""
    path = path or config.EXCEL_LINKS_FILE
    try:
        from openpyxl import load_workbook
    except ImportError:
        return []
    if not Path(path).exists():
        return []
    try:
        wb = load_workbook(path, read_only=True)
    except Exception:
        return []
    out: list[str] = []
    try:
        ws = _sheet(wb)
        for row in ws.iter_rows(min_row=HEADER_ROWS + 1,
                                min_col=LINK_COL, max_col=LINK_COL,
                                values_only=True):
            v = row[0]
            if isinstance(v, str) and v.strip().startswith("http"):
                out.append(v.strip())
    finally:
        try:
            wb.close()
        except Exception:
            pass
    return out


def extract_links_from_bytes(data: bytes, filename: str = "") -> list[str]:
    """Tous les liens d'un fichier Excel envoyé par l'utilisateur.

    Parcourt TOUTES les feuilles et TOUTES les cellules (texte et
    hyperliens) : aucun nombre limite de liens — 10, 100 ou 10 000 liens
    sont lus à l'identique. Le fichier n'est jamais réécrit.

    Lève ``ValueError`` avec un message clair si le format est illisible.
    """
    if not data:
        raise ValueError("Le fichier est vide")
    name = Path((filename or "").replace("\\", "/")).name
    ext = Path(name).suffix.lower()
    if ext == ".xls":
        raise ValueError("Format .xls non pris en charge — réenregistrez le "
                         "fichier en .xlsx (Fichier → Enregistrer sous → "
                         "Classeur Excel), puis réessayez")
    if ext and ext not in _XLSX_EXTS:
        raise ValueError(f"Format {ext} non pris en charge — attendu "
                         ".xlsx ou .xlsm")
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise ValueError("Module openpyxl absent — pip install openpyxl")
    try:
        wb = load_workbook(io.BytesIO(data), data_only=True)
    except Exception:
        raise ValueError("Fichier illisible — vérifiez qu'il s'agit bien "
                         "d'un classeur Excel (.xlsx)")

    out: list[str] = []
    seen: set[str] = set()
    try:
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    cands: list[str] = []
                    if isinstance(cell.value, str):
                        cands += _URL_RE.findall(cell.value)
                    link = getattr(cell, "hyperlink", None)
                    target = getattr(link, "target", None) if link else None
                    if isinstance(target, str) and target.strip():
                        cands.append(target.strip())
                    for url in cands:
                        url = url.rstrip(".,;:!?)]}")
                        if url and url not in seen:
                            seen.add(url)
                            out.append(url)
    finally:
        try:
            wb.close()
        except Exception:
            pass
    return out


# NB : les fichiers ne sont JAMAIS écrits — lecture seule.
