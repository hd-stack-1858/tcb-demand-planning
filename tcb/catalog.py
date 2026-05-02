# Historical baseline COGS per SKU — used for dev seeding and synthetic lots.
# These are pre-app values (before new item batches / price changes in Apr 2026).
# Authoritative source: Himanshu (May 2026). Do not derive from BOM — item batch
# costs drift over time; this dict captures what the stock was actually worth.
CATALOG_COGS = {
    "TCB001": 441.3, "TCB002": 441.3,
    "TCB003": 700.8, "TCB004": 700.8,
    "TCB005": 472.7, "TCB006": 472.7,
    "TCB007": 609.2,
    "TCB008": 276.3,
    "TCB009": 334.2, "TCB009_1": 334.2,
    "TCB010": 840.2,
    "TCB011": 297.3,
    "TCB012": 305.5,
}
