"""Convert ONE column to a storage type. A tool for whoever judges the column, not a fix-all.

V80 reduced column types to text / int / double / strings / blob. Columns created
before it still carry an old type (number, date, datetime, select, checkbox,
url, string, tags). What each should become depends on its data and its meaning, so
that is decided per column by an operator (a person or an LLM) who looks at it
first. This script only shows the facts and carries out one decision.

    # 1. see what is left and what each column holds
    docker compose --profile migration run --rm --entrypoint python migration \
        convert_column_type.py list

    # 2. convert one column (prints the plan; add --apply to write it)
    docker compose --profile migration run --rm --entrypoint python migration \
        convert_column_type.py convert --table-id 12 --column-id <uuid> \
        --type int --display date --apply

--display is how the client reads the column (url, select for text; date,
datetime for int; checkbox for strings, which is otherwise read as tags); the
database stores it in the column's options and never reads it.

Stored values change only where the stored form must:
    text     a boolean or number becomes its text ('true', '3')
    int      3.0 becomes 3 and an empty string becomes null
    strings  true becomes ["T"], false becomes ["F"], and a lone string its
             one-element array
A value that does not fit the target type stops the conversion. Look at it,
then pick another type, pass --parse-strings if it is a number written as
text ("12"), or pass --clear-invalid to null those cells.

Take a dump first on a real database: migrate.py --dump.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import psycopg2

STORAGE_TYPES = ("text", "int", "double", "strings", "blob")
BIGINT_MIN, BIGINT_MAX = -(2**63), 2**63 - 1

FACTS_SQL = """
SELECT
    count(*) FILTER (WHERE kind <> 'null')                                   AS non_null,
    count(*) FILTER (WHERE kind = 'number' AND is_integer)                   AS integers,
    count(*) FILTER (WHERE kind = 'number' AND NOT is_integer)               AS fractions,
    count(*) FILTER (WHERE kind = 'number' AND NOT fits_bigint)              AS beyond_bigint,
    count(*) FILTER (WHERE kind = 'string' AND btrim(cell #>> '{}') = '')    AS empty_strings,
    count(*) FILTER (WHERE kind = 'string' AND btrim(cell #>> '{}') <> '')   AS strings,
    count(*) FILTER (WHERE kind = 'boolean')                                 AS booleans,
    count(*) FILTER (WHERE kind = 'array')                                   AS arrays,
    count(*) FILTER (WHERE kind = 'object')                                  AS objects
FROM (
    SELECT
        cell,
        kind,
        CASE WHEN kind = 'number' THEN (cell #>> '{}')::NUMERIC %% 1 = 0 ELSE FALSE END AS is_integer,
        CASE WHEN kind = 'number'
             THEN (cell #>> '{}')::NUMERIC BETWEEN %(lo)s AND %(hi)s ELSE TRUE END    AS fits_bigint
    FROM (
        SELECT row_data -> %(col)s AS cell, jsonb_typeof(row_data -> %(col)s) AS kind
        FROM public.rows
        WHERE table_id = %(tid)s AND row_data ? %(col)s
    ) AS cells
) AS classified
"""

SAMPLES_SQL = """
SELECT DISTINCT (row_data -> %(col)s)::TEXT
FROM public.rows
WHERE table_id = %(tid)s AND row_data ? %(col)s AND jsonb_typeof(row_data -> %(col)s) <> 'null'
LIMIT 5
"""

# Cells that cannot be stored as the target type, per target.
INVALID_WHERE = {
    "text": "jsonb_typeof(row_data -> %(col)s) IN ('array', 'object')",
    "int": (
        "CASE jsonb_typeof(row_data -> %(col)s) "
        "WHEN 'null' THEN FALSE "
        "WHEN 'string' THEN btrim(row_data ->> %(col)s) <> '' "
        "WHEN 'number' THEN (row_data ->> %(col)s)::NUMERIC %% 1 <> 0 "
        "     OR (row_data ->> %(col)s)::NUMERIC NOT BETWEEN %(lo)s AND %(hi)s "
        "ELSE TRUE END"
    ),
    "double": "jsonb_typeof(row_data -> %(col)s) NOT IN ('null', 'number')",
    "strings": "jsonb_typeof(row_data -> %(col)s) NOT IN ('null', 'array', 'boolean', 'string')",
}

# Cells that are valid for the target but stored in another form, and their new form.
REWRITE = {
    "text": (
        "jsonb_typeof(row_data -> %(col)s) IN ('boolean', 'number')",
        "to_jsonb(row_data ->> %(col)s)",
    ),
    "double": (
        "jsonb_typeof(row_data -> %(col)s) = 'string' AND btrim(row_data ->> %(col)s) = ''",
        "'null'::JSONB",
    ),
    "int": (
        "jsonb_typeof(row_data -> %(col)s) <> 'null' AND (row_data ->> %(col)s) !~ '^-?[0-9]+$'",
        "CASE jsonb_typeof(row_data -> %(col)s) WHEN 'number' "
        "THEN to_jsonb((row_data ->> %(col)s)::NUMERIC::BIGINT) ELSE 'null'::JSONB END",
    ),
    "strings": (
        "jsonb_typeof(row_data -> %(col)s) IN ('boolean', 'string')",
        "CASE WHEN row_data -> %(col)s IN ('true'::JSONB, '\"true\"'::JSONB) THEN '[\"T\"]'::JSONB "
        "WHEN row_data -> %(col)s IN ('false'::JSONB, '\"false\"'::JSONB) THEN '[\"F\"]'::JSONB "
        "WHEN btrim(row_data ->> %(col)s) = '' THEN 'null'::JSONB "
        "ELSE jsonb_build_array(row_data ->> %(col)s) END",
    ),
}


def connect():
    conn = psycopg2.connect(os.environ.get("DATABASE_URL", "postgresql://dba_user:dba_pws@db:5432/db"))
    conn.autocommit = False
    return conn


def facts(cur, table_id: int, column_id: str) -> dict:
    params = {"tid": table_id, "col": column_id, "lo": BIGINT_MIN, "hi": BIGINT_MAX}
    cur.execute(FACTS_SQL, params)
    names = [d[0] for d in cur.description]
    out = dict(zip(names, cur.fetchone(), strict=True))
    cur.execute(SAMPLES_SQL, params)
    out["samples"] = [r[0] for r in cur.fetchall()]
    return out


def cmd_list(args) -> int:
    conn = connect()
    with conn, conn.cursor() as cur:
        cur.execute(
            "SELECT t.table_id, t.workspace_id::TEXT, t.table_name, c "
            "FROM public.tables AS t, jsonb_array_elements(t.config -> 'columns') AS c "
            "WHERE jsonb_typeof(t.config -> 'columns') = 'array' "
            "ORDER BY t.table_id"
        )
        columns = cur.fetchall()
        shown = 0
        for table_id, workspace_id, table_name, column in columns:
            old_type = column.get("type")
            if old_type in STORAGE_TYPES and not args.all:
                continue
            if args.table_id is not None and table_id != args.table_id:
                continue
            shown += 1
            record = {
                "table_id": table_id,
                "workspace_id": workspace_id,
                "table_name": table_name,
                "column_id": column.get("column_id"),
                "name": column.get("name"),
                "type": old_type,
                "options": column.get("options"),
                "data": facts(cur, table_id, column.get("column_id")),
            }
            print(json.dumps(record, ensure_ascii=False))
        print(f"{shown} column(s) listed", file=sys.stderr)
    conn.close()
    return 0


def cmd_convert(args) -> int:
    params = {"tid": args.table_id, "col": args.column_id, "lo": BIGINT_MIN, "hi": BIGINT_MAX}
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT config -> 'columns' FROM public.tables WHERE table_id = %s FOR UPDATE", (args.table_id,))
            row = cur.fetchone()
            if row is None or not isinstance(row[0], list):
                print(f"table {args.table_id} not found", file=sys.stderr)
                return 2
            columns = row[0]
            column = next((c for c in columns if c.get("column_id") == args.column_id), None)
            if column is None:
                print(f"column {args.column_id} not found in table {args.table_id}", file=sys.stderr)
                return 2
            if column.get("type") == "blob" or args.type == "blob":
                print("blob columns are not converted: their cells are stored files", file=sys.stderr)
                return 2

            print(f"column  {column.get('name')!r}  {column.get('type')} -> {args.type}  display={args.display}")
            print(f"data    {json.dumps(facts(cur, args.table_id, args.column_id), ensure_ascii=False)}")

            # The column takes its new type first: the rows trigger checks every cell
            # written below against it.
            options = column.get("options")
            if not isinstance(options, dict):
                options = {}
            if args.display:
                options = {**options, "display": args.display}
            else:
                options = {k: v for k, v in options.items() if k != "display"}
            new_columns = [
                {**c, "type": args.type, "options": options} if c.get("column_id") == args.column_id else c
                for c in columns
            ]
            cur.execute(
                "UPDATE public.tables SET config = jsonb_set(config, '{columns}', %s::JSONB) "
                "WHERE table_id = %s RETURNING workspace_id::TEXT",
                (json.dumps(new_columns), args.table_id),
            )
            workspace_id = cur.fetchone()[0]

            if args.parse_strings and args.type in ("int", "double"):
                cur.execute(
                    "UPDATE public.rows "
                    "SET row_data = jsonb_set(row_data, ARRAY[%(col)s], to_jsonb(btrim(row_data ->> %(col)s)::NUMERIC)) "
                    "WHERE table_id = %(tid)s AND jsonb_typeof(row_data -> %(col)s) = 'string' "
                    "AND btrim(row_data ->> %(col)s) ~ %(number)s",
                    {**params, "number": "^-?[0-9]+$" if args.type == "int" else "^-?[0-9]+([.][0-9]+)?$"},
                )
                print(f"parsed  {cur.rowcount} numeric string(s) into numbers")

            cur.execute(
                f"SELECT count(*) FROM public.rows WHERE table_id = %(tid)s AND row_data ? %(col)s "
                f"AND {INVALID_WHERE[args.type]}",
                params,
            )
            invalid = cur.fetchone()[0]
            if invalid and not args.clear_invalid:
                print(f"STOP    {invalid} cell(s) cannot be stored as {args.type}; nothing changed.", file=sys.stderr)
                print("        Pick another type, or pass --clear-invalid to null them.", file=sys.stderr)
                conn.rollback()
                return 1
            if invalid:
                cur.execute(
                    f"UPDATE public.rows SET row_data = jsonb_set(row_data, ARRAY[%(col)s], 'null'::JSONB) "
                    f"WHERE table_id = %(tid)s AND row_data ? %(col)s AND {INVALID_WHERE[args.type]}",
                    params,
                )
                print(f"cleared {cur.rowcount} invalid cell(s) to null")

            if args.type in REWRITE:
                where, value = REWRITE[args.type]
                cur.execute(
                    f"UPDATE public.rows SET row_data = jsonb_set(row_data, ARRAY[%(col)s], {value}) "
                    f"WHERE table_id = %(tid)s AND row_data ? %(col)s AND {where}",
                    params,
                )
                print(f"rewrote {cur.rowcount} cell(s) into {args.type} form")

            # LatticeQL caches the workspace schema; it still names the old type.
            cur.execute("DELETE FROM private.cache WHERE cache_key = %s", (f"lql:schema:{workspace_id}",))

        if args.apply:
            conn.commit()
            print("applied")
        else:
            conn.rollback()
            print("dry run: nothing written (pass --apply)")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list", help="columns that still have an old type, with what they hold")
    listing.add_argument("--table-id", type=int, help="only this table")
    listing.add_argument("--all", action="store_true", help="include columns already on a storage type")
    listing.set_defaults(run=cmd_list)

    convert = commands.add_parser("convert", help="convert one column")
    convert.add_argument("--table-id", type=int, required=True)
    convert.add_argument("--column-id", required=True)
    convert.add_argument("--type", required=True, choices=[t for t in STORAGE_TYPES if t != "blob"])
    convert.add_argument("--display", default=None, help="how the client reads it: url, select, checkbox, date, ...")
    convert.add_argument("--parse-strings", action="store_true", help='int/double: read "12" as the number 12')
    convert.add_argument("--clear-invalid", action="store_true", help="null the cells that do not fit the type")
    convert.add_argument("--apply", action="store_true", help="write the change (default is a dry run)")
    convert.set_defaults(run=cmd_convert)

    args = parser.parse_args()
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
