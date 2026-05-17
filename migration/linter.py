#!/usr/bin/env python3
"""Custom SQL linter wrapper — runs sqlfluff, skips spacing/indent noise.

Filters out LT01 (layout.spacing) and LT02 (layout.indent) violations
from the output and exit code. All other rules are enforced normally.

Usage:
    python linter.py migration/V*.sql
    python linter.py  # defaults to all V*.sql in same directory
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SKIP_RULES = {"LT01", "LT02"}

VIOLATION_RE = re.compile(
    r"^L:\s*\d+\s*\|\s*P:\s*\d+\s*\|\s*(\w+)\s*\|"
)

FILE_HEADER_RE = re.compile(r"^== \[.*\] (FAIL|PASS)")


def main() -> int:
    if sys.argv[1:]:
        sql_files = sys.argv[1:]
    else:
        here = Path(__file__).parent
        sql_files = sorted(str(f) for f in here.glob("V*.sql"))

    if not sql_files:
        print("No SQL files to lint")
        return 0

    result = subprocess.run(
        ["sqlfluff", "lint"] + sql_files,
        capture_output=True, text=True,
    )

    real_violations = 0
    output_lines: list[str] = []
    current_file_has_real = False
    current_file_header = ""

    for line in result.stdout.splitlines():
        file_match = FILE_HEADER_RE.match(line)
        if file_match:
            if current_file_has_real and current_file_header:
                output_lines.insert(
                    next(
                        i for i, l in enumerate(output_lines)
                        if l == current_file_header
                    ),
                    "",
                )
            current_file_header = line
            current_file_has_real = False
            output_lines.append(line)
            continue

        viol_match = VIOLATION_RE.match(line)
        if viol_match:
            rule = viol_match.group(1)
            if rule in SKIP_RULES:
                continue
            real_violations += 1
            current_file_has_real = True

        output_lines.append(line)

    if real_violations > 0:
        print("\n".join(output_lines))
        print(f"\n{real_violations} violation(s) found (spacing/indent skipped)")
        return 1

    print(f"  ✓ lint passed ({len(sql_files)} files, spacing/indent skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
