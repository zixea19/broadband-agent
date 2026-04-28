#!/usr/bin/env python3
"""
match_template.py — Trajectory template fast-path lookup.

Input (stdin JSON): {"question": "<user message>"}
Output (stdout JSON):
  hit  → {"status": "hit", "task_type": "...", "template": {...}}
  miss → {"status": "miss"}
"""

import json
import sys
from pathlib import Path


def load_templates() -> list:
    ref_dir = Path(__file__).parent.parent / "references"
    tpl_path = ref_dir / "trajectory_templates.json"
    with open(tpl_path, encoding="utf-8") as f:
        return json.load(f)


def match(question: str, templates: list) -> dict | None:
    for tpl in templates:
        for kw in tpl.get("keywords", []):
            if kw in question:
                return tpl
    return None


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "Usage: match_template.py '<question_json_string>'"}))
        sys.exit(1)
    raw = sys.argv[1]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "error", "message": f"Invalid JSON input: {e}"}))
        sys.exit(1)

    question = payload.get("question", "")
    templates = load_templates()
    hit = match(question, templates)

    if hit:
        print(json.dumps({"status": "hit", "task_type": hit["task_type"], "template": hit}, ensure_ascii=False))
    else:
        print(json.dumps({"status": "miss"}))


if __name__ == "__main__":
    main()
