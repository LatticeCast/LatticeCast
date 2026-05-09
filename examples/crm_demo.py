#!/usr/bin/env python3
"""
CRM demo — create a `crm-demo` table, seed 30 deals, install 2 extra
LatticeQL dashboards on top of the template-provided "Sales Dashboard".

Stdlib only. Run against a live LatticeCast instance:
    python3 examples/crm_demo.py
    python3 examples/crm_demo.py --base-url http://localhost:13491 --user lattice

End state: open http://localhost:13491/{workspace_id}/crm-demo and click
through Pipeline / Sales Dashboard / Win Loss Analysis / Forecast.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request


# ── HTTP helpers ────────────────────────────────────────────────────────────

def http(method, url, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            txt = r.read().decode()
            return json.loads(txt) if txt else None
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {url} → {e.code}\n{e.read().decode()}")


def login(base_url, user_name):
    r = http("POST", f"{base_url}/api/v1/login/password",
             body={"user_name": user_name, "password": ""})
    return r["access_token"]


# ── LatticeQL widget builders ───────────────────────────────────────────────

TBL = "crm-demo"
OPEN_STAGES = '@["lead","qualified","proposal"]'


def num(title, lql, field, fmt=",.0f"):
    return {"kind": "number", "title": title, "lql": lql, "field": field, "format": fmt}


def bar(title, lql, y_field):
    return {
        "kind": "chart", "title": title, "lql": lql,
        "echarts": {
            "dataset": [{"$inject": "rows"}],
            "xAxis": {"type": "category"},
            "yAxis": {"type": "value"},
            "series": [{"type": "bar", "encode": {"x": "dim_0", "y": y_field}}],
        },
    }


def donut(title, lql, value_field):
    return {
        "kind": "chart", "title": title, "lql": lql,
        "echarts": {
            "dataset": [{"$inject": "rows"}],
            "series": [{
                "type": "pie", "radius": ["40%", "70%"],
                "encode": {"itemName": "dim_0", "value": value_field},
            }],
        },
    }


# ── Sample deals ────────────────────────────────────────────────────────────

DEALS = [
    ("Acme Corp Annual License",  "won",       120000, "Alice", "2026-04-12", ["enterprise","saas"]),
    ("BetaSoft POC",              "qualified",  45000, "Alice", "2026-06-15", ["smb","trial"]),
    ("Cyclone Logistics",         "proposal",   85000, "Bob",   "2026-05-30", ["enterprise","fleet"]),
    ("Delta Industries",          "lead",       30000, "Bob",   "2026-07-10", ["smb"]),
    ("Echo Systems Renewal",      "won",        95000, "Carol", "2026-04-25", ["enterprise","renewal"]),
    ("Falcon Robotics",           "lost",       60000, "Carol", "2026-04-05", ["startup","manufacturing"]),
    ("Gamma Health",              "qualified",  72000, "Alice", "2026-06-20", ["enterprise","healthcare"]),
    ("Helix Bio",                 "proposal",  140000, "Bob",   "2026-05-18", ["enterprise","biotech"]),
    ("Iris Marketing",            "won",        18000, "David", "2026-04-28", ["smb","marketing"]),
    ("Jove Capital",              "lead",      210000, "Carol", "2026-08-01", ["enterprise","finance"]),
    ("Kestrel Aero",              "lost",       55000, "Alice", "2026-03-22", ["enterprise","aviation"]),
    ("Luna Education",            "qualified",  22000, "David", "2026-06-05", ["smb","edtech"]),
    ("Mercury Retail",            "proposal",   38000, "Bob",   "2026-05-25", ["smb","retail"]),
    ("Nova Telecom",              "won",       180000, "Alice", "2026-04-30", ["enterprise","telecom"]),
    ("Orbit Foods",               "lead",       12000, "David", "2026-07-25", ["smb","foodservice"]),
    ("Pinnacle Hotels",           "qualified",  95000, "Carol", "2026-06-12", ["enterprise","hospitality"]),
    ("Quantum Logistics",         "lost",       70000, "Bob",   "2026-04-08", ["enterprise","logistics"]),
    ("Raven Studios",             "won",        25000, "David", "2026-05-02", ["smb","media"]),
    ("Solstice Energy",           "proposal",  220000, "Alice", "2026-06-30", ["enterprise","energy"]),
    ("Tundra Fitness",            "lead",        8000, "David", "2026-08-10", ["smb","fitness"]),
    ("Umbra Security",            "qualified",  68000, "Carol", "2026-06-22", ["enterprise","security"]),
    ("Vanta Cloud",               "won",       145000, "Alice", "2026-05-04", ["enterprise","cloud"]),
    ("Whirl Couriers",            "lost",       42000, "Bob",   "2026-03-18", ["smb","delivery"]),
    ("Xen Labs",                  "proposal",  110000, "Carol", "2026-06-18", ["enterprise","research"]),
    ("Yarrow Botanicals",         "lead",        9500, "David", "2026-07-30", ["smb","retail"]),
    ("Zephyr Travel",             "qualified",  35000, "Bob",   "2026-06-08", ["smb","travel"]),
    ("Apex Manufacturing",        "won",        88000, "Alice", "2026-05-09", ["enterprise","manufacturing"]),
    ("Boreal Forestry",           "lost",       28000, "David", "2026-04-02", ["smb","agriculture"]),
    ("Crescent Banking",          "proposal",  195000, "Carol", "2026-07-05", ["enterprise","finance"]),
    ("Drift Apparel",             "lead",       15000, "Bob",   "2026-08-15", ["smb","retail"]),
]


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:13491")
    ap.add_argument("--user", default="lattice", help="LatticeCast user_name")
    args = ap.parse_args()

    token = login(args.base_url, args.user)
    workspaces = http("GET", f"{args.base_url}/api/v1/workspaces", token)
    if not workspaces:
        sys.exit("No workspace for user. Create one first.")
    ws_id = workspaces[0]["workspace_id"]

    table = http("POST", f"{args.base_url}/api/v1/tables/template/crm", token,
                 {"table_id": TBL, "workspace_id": ws_id})
    cols = {c["name"]: c["column_id"] for c in table["columns"]}
    print(f"Created table {TBL}")

    inserted = 0
    for title, stage, value, owner, close_date, tags in DEALS:
        row = {
            cols["Title"]: title, cols["Stage"]: stage, cols["Value"]: value,
            cols["Owner"]: owner, cols["Close Date"]: close_date, cols["Tags"]: tags,
        }
        http("POST", f"{args.base_url}/api/v1/tables/{TBL}/rows", token, {"row_data": row})
        inserted += 1
    print(f"Inserted {inserted} deals")

    win_loss = {
        "name": "Win Loss Analysis", "type": "dashboard",
        "config": {
            "layout": [
                {"id": "won_count",        "x": 0, "y": 0, "w": 3, "h": 2},
                {"id": "lost_count",       "x": 3, "y": 0, "w": 3, "h": 2},
                {"id": "won_value_total",  "x": 6, "y": 0, "w": 3, "h": 2},
                {"id": "lost_value_total", "x": 9, "y": 0, "w": 3, "h": 2},
                {"id": "outcome_pie",      "x": 0, "y": 2, "w": 6, "h": 5},
                {"id": "won_by_owner",     "x": 6, "y": 2, "w": 6, "h": 5},
            ],
            "blocks": {
                "won_count":        num("Deals Won",  f'table("{TBL}") | filter((r)->{{r.stage=="won"}})  | aggregate(@{{"count": count()}})',     "count"),
                "lost_count":       num("Deals Lost", f'table("{TBL}") | filter((r)->{{r.stage=="lost"}}) | aggregate(@{{"count": count()}})',     "count"),
                "won_value_total":  num("Won Revenue",  f'table("{TBL}") | filter((r)->{{r.stage=="won"}})  | aggregate(@{{"value": sum(r.value)}})', "value", "$,.0f"),
                "lost_value_total": num("Lost Revenue", f'table("{TBL}") | filter((r)->{{r.stage=="lost"}}) | aggregate(@{{"value": sum(r.value)}})', "value", "$,.0f"),
                "outcome_pie":      donut("Won vs Lost (count)",  f'table("{TBL}") | filter((r)->{{r.stage in @["won","lost"]}}) | group_by((r)->{{r.stage}}) | aggregate(@{{"count": count()}})', "count"),
                "won_by_owner":     bar(  "Won Revenue by Owner", f'table("{TBL}") | filter((r)->{{r.stage=="won"}}) | group_by((r)->{{r.owner}}) | aggregate(@{{"value": sum(r.value)}})', "value"),
            },
        },
    }

    forecast = {
        "name": "Forecast", "type": "dashboard",
        "config": {
            "layout": [
                {"id": "open_total", "x": 0, "y": 0, "w": 4, "h": 2},
                {"id": "deal_count", "x": 4, "y": 0, "w": 4, "h": 2},
                {"id": "avg_value",  "x": 8, "y": 0, "w": 4, "h": 2},
                {"id": "top_owners", "x": 0, "y": 2, "w": 6, "h": 5},
                {"id": "open_pie",   "x": 6, "y": 2, "w": 6, "h": 5},
            ],
            "blocks": {
                "open_total": num("Open Pipeline ($)", f'table("{TBL}") | filter((r)->{{r.stage in {OPEN_STAGES}}}) | aggregate(@{{"value": sum(r.value)}})', "value", "$,.0f"),
                "deal_count": num("Open Deals",        f'table("{TBL}") | filter((r)->{{r.stage in {OPEN_STAGES}}}) | aggregate(@{{"count": count()}})',     "count"),
                "avg_value":  num("Avg Deal Size",     f'table("{TBL}") | aggregate(@{{"avg": avg(r.value)}})',                                              "avg",   "$,.0f"),
                "top_owners": bar("Open Pipeline by Owner", f'table("{TBL}") | filter((r)->{{r.stage in {OPEN_STAGES}}}) | group_by((r)->{{r.owner}}) | aggregate(@{{"value": sum(r.value)}})', "value"),
                "open_pie":   donut("Open Deals by Stage",  f'table("{TBL}") | filter((r)->{{r.stage in {OPEN_STAGES}}}) | group_by((r)->{{r.stage}}) | aggregate(@{{"count": count()}})', "count"),
            },
        },
    }

    for v in (win_loss, forecast):
        http("POST", f"{args.base_url}/api/v1/tables/{TBL}/views", token, v)
        print(f"Added view: {v['name']}")

    print(f"\nDone. Open: {args.base_url}/{ws_id}/{TBL}")


if __name__ == "__main__":
    main()
