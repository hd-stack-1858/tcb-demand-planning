"""
Populates suppliers table with real contact data from Item-supplier mapping.xlsx
and links items.supplier_id to the correct supplier.
Run from project root: python setup/load_suppliers.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tcb.db import get_client

db = get_client()

# ── Mapping: Excel supplier name → existing supplier_id in DB ────────────────
# "Baby Gallery" = King Enterprises (email babygalleryindia@gmail.com is the giveaway)
# "Showercaps-Supplier" = Ekta Oversees
# "Merothiya Business Pvt. Ltd." = Merothiya Business
# "NM Prints and Packs" = N M Prints
# "Craft India Inc" = Craft India
# Rest match exactly by name

SUPPLIER_UPDATES = [
    {
        "supplier_id": 23,   # Baby Gallery → rename + fill
        "name": "King Enterprises",
        "contact_name": "Vijay",
        "phone": "9898152761",
        "email": "babygalleryindia@gmail.com",
        "city": "Ahmedabad",
        "gstin": "24BPBPM4137F1Z8",
        "payment_terms": "50% Advance, 50% before Delivery",
        "lead_time_days": 90,
        "moq": 250,
    },
    {
        "supplier_id": 31,   # Showercaps-Supplier → rename + fill
        "name": "Ekta Oversees",
        "contact_name": "Ekta Jain",
        "phone": "9899224356",
        "email": "ektaoverseas9@gmail.com",
        "city": "Gurgaon",
        "gstin": "07AHJPJ8650K1ZW",
        "payment_terms": "100% before Delivery",
        "lead_time_days": 5,
        "moq": 100,
    },
    {
        "supplier_id": 27,   # Merothiya Business Pvt. Ltd. → fill
        "name": "Merothiya Business",
        "contact_name": "Archit",
        "phone": "6396997273",
        "email": "archit.mero@gmail.com",
        "city": "Noida",
        "gstin": "09AARCM3829R1ZD",
        "payment_terms": "30% Advance, 70% before Delivery",
        "lead_time_days": 45,
        "moq": 100,
    },
    {
        "supplier_id": 33,   # Sobhara → fill
        "name": "Sobhara",
        "contact_name": "Sonali Sugandha",
        "phone": "7411036465",
        "email": "sonali.s@sobhara.co.in",
        "city": "Bengaluru",
        "gstin": "29AEVFS3118Q1ZZ",
        "payment_terms": "30% Advance, Balance Net 7-18 (item-specific)",
        "lead_time_days": 60,
        "moq": 500,
    },
    {
        "supplier_id": 35,   # Svatanya → fill
        "name": "Svatanya",
        "contact_name": "Nimish Pant",
        "phone": "9312408496",
        "email": "svatanyaindiafoundation@gmail.com",
        "city": "Delhi",
        "gstin": "07AEOPD7161D1ZM",
        "payment_terms": "50% Advance, 50% before Delivery",
        "lead_time_days": 60,
        "moq": 500,
    },
    {
        "supplier_id": 26,   # Hollyhock → fill
        "name": "Hollyhock",
        "contact_name": "Nirnita",
        "phone": "8368107677",
        "email": "connect.hollyhock@gmail.com",
        "city": "Delhi",
        "gstin": "07AAMFH2506C1ZS",
        "payment_terms": "30% Advance, Balance Net 30",
        "lead_time_days": 60,
        "moq": 250,
    },
    {
        "supplier_id": 24,   # Craft India Inc → fill
        "name": "Craft India",
        "contact_name": "Shamoon",
        "phone": "9837142705",
        "email": "shamoon@craftindiainc.com",
        "city": "Sambhal, UP",
        "gstin": None,
        "payment_terms": "Net 30",
        "lead_time_days": 45,
        "moq": 100,
    },
    {
        "supplier_id": 28,   # NM Prints and Packs → fill
        "name": "N M Prints",
        "contact_name": "Ravi",
        "phone": "9844068865",
        "email": "ravi@nmprints.co.in",
        "city": "Bengaluru",
        "gstin": "29ABVPM0680N1ZR",
        "payment_terms": "Net 30",
        "lead_time_days": 15,
        "moq": 500,
    },
    {
        "supplier_id": 32,   # Smart Inc. → fill
        "name": "Smart Inc",
        "contact_name": "D'Souza",
        "phone": "9900015070",
        "email": "smartincorp@gmail.com",
        "city": "Bengaluru",
        "gstin": "29ADJPD2166Q1Z1",
        "payment_terms": "Net 30",
        "lead_time_days": 15,
        "moq": 500,
    },
    {
        "supplier_id": 25,   # G K Enterprises → fill
        "name": "G K Enterprises",
        "contact_name": "Priya",
        "phone": "8433828574",
        "email": "rkstk@yahoo.co.in",
        "city": "Mumbai",
        "gstin": "27ADXPN7508A1ZA",
        "payment_terms": "100% Advance",
        "lead_time_days": 5,
        "moq": 2500,
    },
]

# ── Step 1: Update all supplier rows ─────────────────────────────────────────
print("Updating suppliers table...")
for sup in SUPPLIER_UPDATES:
    sid = sup.pop("supplier_id")
    db.table("suppliers").update(sup).eq("supplier_id", sid).execute()
    print(f"  Updated supplier_id={sid}: {sup['name']}")

# ── Step 2: Build name → supplier_id lookup ───────────────────────────────────
sup_rows = db.table("suppliers").select("supplier_id, name").execute().data
name_to_id = {r["name"]: r["supplier_id"] for r in sup_rows}

# ── Step 3: item_code → supplier_id mapping (from Excel) ─────────────────────
ITEM_SUPPLIER = {
    # King Enterprises
    "TCBP00001": "King Enterprises",
    "TCBP00002": "King Enterprises",
    "TCBP00003": "King Enterprises",
    "TCBP00006": "King Enterprises",
    "TCBP00007": "King Enterprises",
    "TCBP00013": "King Enterprises",
    "TCBP00014": "King Enterprises",
    # Ekta Oversees
    "TCBP00004": "Ekta Oversees",
    "TCBP00008": "Ekta Oversees",
    # Merothiya Business
    "TCBP00005": "Merothiya Business",
    "TCBP00009": "Merothiya Business",
    # Sobhara
    "TCBP00010": "Sobhara",
    "TCBP00015": "Sobhara",
    "TCBP00017": "Sobhara",
    "TCBP00020": "Sobhara",
    "TCBP00021": "Sobhara",
    # Svatanya
    "TCBP00011": "Svatanya",
    "TCBP00012": "Svatanya",
    "TCBP00016": "Svatanya",
    # Hollyhock
    "TCBP00018": "Hollyhock",
    "TCBP00019": "Hollyhock",
    "TCBP00022": "Hollyhock",
    "TCBP00023": "Hollyhock",
    # Craft India
    "TCBP00024": "Craft India",
    # N M Prints
    "TCBP00025": "N M Prints",
    "TCBP00026": "N M Prints",
    "TCBP00027": "N M Prints",
    "TCBP00032": "N M Prints",
    "TCBP00033": "N M Prints",
    "TCBP00034": "N M Prints",
    "TCBP00035": "N M Prints",
    "TCBP00036": "N M Prints",
    "TCBP00037": "N M Prints",
    "TCBP00038": "N M Prints",
    "TCBP00039": "N M Prints",
    "TCBP00040": "N M Prints",
    # Smart Inc
    "TCBP00028": "Smart Inc",
    "TCBP00029": "Smart Inc",
    "TCBP00030": "Smart Inc",
    "TCBP00031": "Smart Inc",
    # G K Enterprises
    "TCBP00041": "G K Enterprises",
}

# ── Step 4: Pull item_code → item_id ─────────────────────────────────────────
items = db.table("items").select("item_id, item_code").execute().data
code_to_id = {r["item_code"]: r["item_id"] for r in items}

# ── Step 5: Update items.supplier_id ─────────────────────────────────────────
print("\nLinking items to suppliers...")
linked = 0
for item_code, sup_name in ITEM_SUPPLIER.items():
    item_id = code_to_id.get(item_code)
    supplier_id = name_to_id.get(sup_name)
    if item_id and supplier_id:
        db.table("items").update({"latest_supplier_id": supplier_id}).eq("item_id", item_id).execute()
        print(f"  {item_code} -> {sup_name} (supplier_id={supplier_id})")
        linked += 1
    else:
        print(f"  WARN: could not link {item_code} -> {sup_name} (item_id={item_id}, supplier_id={supplier_id})")

print(f"\nDone. {linked} items linked to suppliers.")

# ── Step 6: Verify ───────────────────────────────────────────────────────────
print("\nVerification — items with latest_supplier_id NULL:")
unlinked = db.table("items").select("item_code, name").is_("latest_supplier_id", "null").execute().data
if unlinked:
    for r in unlinked:
        print(f"  {r['item_code']} {r['name']}")
else:
    print("  None — all items linked.")
