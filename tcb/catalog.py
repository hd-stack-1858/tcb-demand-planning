# Approximate catalog COGS per SKU — used only for dev seeding when no
# ASSEMBLY transaction history exists. Values sourced from CLAUDE.md.
# Update here when COGS changes; setup/07 and tests/conftest both import this.
CATALOG_COGS = {
    "TCB001": 477.0, "TCB002": 477.0,
    "TCB003": 774.0, "TCB004": 774.0,
    "TCB005": 518.0, "TCB006": 518.0,
    "TCB008": 306.0, "TCB009_1": 372.0,
    "TCB010": 931.0, "TCB011": 330.0,
    "TCB012": 339.0,
}
