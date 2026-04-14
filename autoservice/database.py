"""Backward-compatible shim — re-exports from socialware.database."""
from socialware.database import (  # noqa: F401
    get_output_dir, save_record, list_records, get_record,
    update_record, delete_record, print_results,
)
