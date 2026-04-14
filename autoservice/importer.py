"""Backward-compatible shim — re-exports from socialware.importer."""
from socialware.importer import (  # noqa: F401
    extract_from_docx, extract_from_xlsx, extract_from_pdf,
    import_file, import_to_domain, save_item,
)
