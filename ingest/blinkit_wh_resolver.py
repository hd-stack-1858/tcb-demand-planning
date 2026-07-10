"""
Blinkit WH name/code resolution — shared by the performance loader, the SOH
loader, and the replenishment engine.

Replaces three independently hand-maintained dicts (WH_PERF_TO_CODE,
_PERF_WH_TO_CODE, WH_SOH_NAME_TO_CODE) that used to gate whether a warehouse
was recognized at all. The performance detail report is the "mother file" —
any Serving warehouse it mentions must be reflected into partner_locations,
not silently dropped because it isn't in a hardcoded allowlist.

WH_MANUAL_OVERRIDES is the only hand-maintained map left, and it is NOT a
gate: a WH name absent from it still gets a row, just with an auto-generated
code instead of a curated human-readable one.
"""

import hashlib
import re

_ES_RE = re.compile(r'\bES(\d+)\s*$', re.IGNORECASE)

# Aliases (name variant -> canonical name Blinkit actually uses in this file
# type) and preferred human-readable codes for the long-standing WHs.
# Never a gate — see module docstring.
WH_MANUAL_OVERRIDES: dict[str, str] = {
    'Ahmedabad A2 - Feeder':          'BLK_WH_2470',
    'Bengaluru B3 - Feeder':          'BLK_WH_1873',
    'Bengaluru B3':                   'BLK_WH_1873',
    'Bengaluru B5 - Feeder':          'BLK_WH_5397',
    'Chennai C5 - Feeder':            'BLK_WH_3262',
    'Coimbatore C1 - Feeder':         'BLK_WH_2681',
    'Faridabad - Feeder':             'BLK_WH_5096',
    'Farukhnagar - SR':               'BLK_WH_5096',   # closed — merged into Faridabad
    'Guwahati G1 - Feeder':           'BLK_WH_3213',
    'Guwahati G1 - Feeder Warehouse': 'BLK_WH_3213',
    'Hyderabad H3 - Feeder':          'BLK_WH_3201',
    'Jaipur J3 - Feeder':             'BLK_WH_3200',
    'Kolkata K4 - Feeder':            'BLK_WH_2015',
    'Kolkata K6 - Feeder':            'BLK_WH_4842',
    'Kolkata K6 - Feeder Warehouse':  'BLK_WH_4842',
    'Kundli - Feeder':                'BLK_WH_2010',
    'Kundli Feeder':                  'BLK_WH_2010',
    'Lucknow L4':                     'BLK_WH_1206',
    'Super Store Lucknow L4':         'BLK_WH_1206',
    'Mumbai M10 - Feeder':            'BLK_WH_2123',
    'Nagpur N1 - Feeder':             'BLK_WH_2468',
    'Noida N1 - Feeder':              'BLK_WH_2576',
    'Patna P1 - Feeder':              'BLK_WH_2960',
    'Pune P3 - Feeder':               'BLK_WH_4572',
    'Pune P3 - Feeder Warehouse':     'BLK_WH_4572',
    'Rajpura R2 - Feeder':            'BLK_WH_4571',
    'Rajpura R2 - Feeder Warehouse':  'BLK_WH_4571',
    'Visakhapatnam V1 - Feeder':      'BLK_WH_2670',
}


def _wh_code(name: str) -> str:
    """Generate a stable, globally unique partner_locations code from a WH name.
    Mirrors _ds_code() in blinkit_performance_loader.py."""
    h = hashlib.md5(name.strip().lower().encode()).hexdigest()[:8].upper()
    return f'BLK_WH_{h}'


def build_wh_name_lookup(sb) -> dict[str, str]:
    """name -> code for every existing Blinkit WH row, layered with manual overrides."""
    rows = (sb.table('partner_locations')
              .select('name, code')
              .eq('location_type', 'WH')
              .eq('channel_id', 4)
              .execute().data)
    lookup = {r['name']: r['code'] for r in rows if r.get('code')}
    lookup.update(WH_MANUAL_OVERRIDES)
    return lookup


def resolve_wh_code(name: str, name_lookup: dict[str, str]) -> str:
    """Resolve a raw 'Serving warehouse' / 'Warehouse Facility Name' string to a
    partner_locations code. Always returns a code — never None — so callers
    never need to silently skip a row because a WH name wasn't pre-seeded."""
    name = name.strip()
    if name in name_lookup:
        return name_lookup[name]
    return _wh_code(name)
