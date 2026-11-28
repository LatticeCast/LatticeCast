"""Verify convert_column_type.py against the freshly migrated throwaway database."""

import contextlib
import io
import json
from types import SimpleNamespace

import convert_column_type
import psycopg2

_WORKSPACE = "33333333-3333-3333-3333-333333333333"
_COLUMN = "44444444-4444-4444-4444-444444444444"

# name, old type, stored values, target, display, flags, exit code, values afterwards
CASES = [
    ("text true stays text in tags", "select", ["true", "x"], "strings", None, {}, 0, [["true"], ["x"]]),
    ("checkbox", "checkbox", [True, "false", ""], "strings", "checkbox", {}, 0, [["T"], ["F"], None]),
    ("non-string array stops", "tags", [["a"], [1]], "strings", None, {}, 1, [["a"], [1]]),
    ("blank becomes null in double", "number", ["", 1.5], "double", None, {}, 0, [None, 1.5]),
    (
        "out of range parsed integer is cleared",
        "number",
        ["12", "99999999999999999999"],
        "int",
        None,
        {"parse_strings": True, "clear_invalid": True},
        0,
        [12, None],
    ),
    ("a fraction stops int", "number", [1.5], "int", None, {}, 1, [1.5]),
]


def verify(psql_fn, dsn: str) -> list[str]:
    errors: list[str] = []
    psql_fn(f"INSERT INTO public.workspaces (workspace_id, workspace_name) VALUES ('{_WORKSPACE}', 'convert-probe');")
    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        with conn.cursor() as cur:
            for name, old_type, values, target, display, flags, code, expected in CASES:
                config = {"columns": [{"column_id": _COLUMN, "name": "c", "type": old_type, "options": {}}]}
                cur.execute(
                    "INSERT INTO public.tables (workspace_id, table_name, config) "
                    "VALUES (%s, %s, %s) RETURNING table_id",
                    (_WORKSPACE, name, json.dumps(config)),
                )
                table_id = cur.fetchone()[0]
                for value in values:
                    cur.execute(
                        "INSERT INTO public.rows (table_id, row_data) VALUES (%s, %s)",
                        (table_id, json.dumps({_COLUMN: value})),
                    )
                args = SimpleNamespace(
                    table_id=table_id,
                    column_id=_COLUMN,
                    type=target,
                    display=display,
                    parse_strings=flags.get("parse_strings", False),
                    clear_invalid=flags.get("clear_invalid", False),
                    apply=True,
                    dsn=dsn,
                )
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    got_code = convert_column_type.cmd_convert(args)
                cur.execute("SELECT row_data -> %s FROM public.rows WHERE table_id = %s ORDER BY row_id", (_COLUMN, table_id))
                got = [row[0] for row in cur.fetchall()]
                if got_code != code or got != expected:
                    errors.append(f"CONVERT {name!r}: exit {got_code} (want {code}), cells {got} (want {expected})")
        conn.close()
    except Exception as exc:  # report like every other probe instead of aborting the run
        errors.append(f"CONVERT PROBE: {exc}")
    finally:
        psql_fn(f"DELETE FROM public.workspaces WHERE workspace_id = '{_WORKSPACE}';")
    return errors
