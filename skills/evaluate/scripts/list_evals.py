"""List all evaluation targets and their current status."""

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: uv pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def main():
    evals_dir = Path("docs/evaluations")
    index_path = evals_dir / "_index.yaml"

    if not index_path.exists():
        print("No evaluations found. Use `/evaluate @path` to start an evaluation.")
        return

    index = yaml.safe_load(index_path.read_text()) or {"targets": []}

    if not index["targets"]:
        print("No evaluation targets registered.")
        return

    # Header
    print(f"{'Slug':<30} {'Type':<8} {'Reports':<9} {'Synthesis':<10} {'Last Report'}")
    print("-" * 85)

    for entry in index["targets"]:
        slug = entry["slug"]
        doc_type = entry.get("type", "?")
        meta_path = evals_dir / slug / "meta.yaml"

        if meta_path.exists():
            meta = yaml.safe_load(meta_path.read_text()) or {}
            review_count = meta.get("review_count", 0)
            synthesis = "Yes" if meta.get("synthesis_done") else "No"
            last_review = meta.get("last_review_date", "-") or "-"
        else:
            # Count report files directly
            reports_dir = evals_dir / slug / "reports"
            report_files = list(reports_dir.glob("*.md")) if reports_dir.exists() else []
            review_count = len(report_files)
            synthesis = "Yes" if (evals_dir / slug / "synthesis.md").exists() else "No"
            last_review = "-"

        print(f"{slug:<30} {doc_type:<8} {review_count:<9} {synthesis:<10} {last_review}")

    print(f"\nTotal targets: {len(index['targets'])}")


if __name__ == "__main__":
    main()
