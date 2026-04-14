"""Initialize an evaluation target: create directory structure and register in _index.yaml."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: uv pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Initialize an evaluation target")
    parser.add_argument("--target", required=True, help="Path to the target document")
    parser.add_argument("--slug", required=True, help="Short slug for the target")
    parser.add_argument(
        "--type",
        required=True,
        choices=["plan", "prd", "design", "implementation", "e2e-test", "deploy", "other"],
        help="Document type",
    )
    parser.add_argument("--reviewer-name", required=True, help="Reviewer's name")
    parser.add_argument("--reviewer-email", required=True, help="Reviewer's email")
    args = parser.parse_args()

    evals_dir = Path("docs/evaluations")
    local_dir = Path(".autoservice/evaluations")
    target_dir = evals_dir / args.slug
    session_dir = local_dir / args.slug / "sessions"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Create directories
    (target_dir / "reports").mkdir(parents=True, exist_ok=True)
    session_dir.mkdir(parents=True, exist_ok=True)

    # Create or verify meta.yaml
    meta_path = target_dir / "meta.yaml"
    if not meta_path.exists():
        meta = {
            "target": args.target,
            "slug": args.slug,
            "type": args.type,
            "created_date": today,
            "review_count": 0,
            "last_review_date": None,
            "synthesis_done": False,
            "reviewers": [],
        }
        meta_path.write_text(yaml.dump(meta, allow_unicode=True, sort_keys=False))
        print(f"Created {meta_path}")
    else:
        print(f"Already exists: {meta_path}")

    # Update _index.yaml
    index_path = evals_dir / "_index.yaml"
    if index_path.exists():
        index = yaml.safe_load(index_path.read_text()) or {"targets": []}
    else:
        index = {"targets": []}

    # Check if target already registered
    existing_slugs = [t["slug"] for t in index["targets"]]
    if args.slug not in existing_slugs:
        index["targets"].append(
            {
                "slug": args.slug,
                "target": args.target,
                "type": args.type,
                "created_date": today,
            }
        )
        index_path.write_text(yaml.dump(index, allow_unicode=True, sort_keys=False))
        print(f"Registered in {index_path}")
    else:
        print(f"Already registered: {args.slug}")

    print(f"Evaluation target '{args.slug}' initialized.")
    print(f"  Reports dir:  {target_dir / 'reports'}")
    print(f"  Sessions dir: {session_dir}")


if __name__ == "__main__":
    main()
