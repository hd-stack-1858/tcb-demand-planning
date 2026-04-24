"""
The Cradle Box — Warehouse Operations App
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import streamlit as st
import pandas as pd
from datetime import date
from tcb.db import get_client
from tcb.inventory import (
    get_item_stock, get_sku_stock, get_assemblable,
    check_assembly_feasibility, assemble_sku, dispatch_sku, receive_item,
)

st.set_page_config(page_title="TCB Warehouse", page_icon="📦", layout="centered")

# ── Header ─────────────────────────────────────────────────────────────────────
logo_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'logo.png')
if os.path.exists(logo_path):
    col_logo, col_title = st.columns([1, 4])
    with col_logo:
        st.image(logo_path, width=80)
    with col_title:
        st.markdown("## Warehouse Management")
else:
    st.markdown("## Warehouse Management")

db = get_client()

# ── Cached lookups ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_items():
    return db.table("items").select("item_id, item_code, name, unit")\
             .eq("is_active", True).order("name").execute().data

@st.cache_data(ttl=60)
def load_skus():
    return db.table("skus").select("sku_id, name")\
             .eq("is_discontinued", False).order("sku_id").execute().data

@st.cache_data(ttl=60)
def load_channels():
    return db.table("channels").select("channel_id, name, code, business_model")\
             .eq("is_active", True).neq("code", "OWN_WH").order("name").execute().data

@st.cache_data(ttl=60)
def load_suppliers():
    return db.table("suppliers").select("supplier_id, name").order("name").execute().data

@st.cache_data(ttl=60)
def load_blinkit_whs():
    return db.table("blinkit_locations")\
             .select("location_id, name, code")\
             .eq("location_type", "WH")\
             .eq("stock_sent", True)\
             .order("name").execute().data


def clear_cache():
    load_items.clear()
    load_skus.clear()
    load_channels.clear()
    load_suppliers.clear()
    load_blinkit_whs.clear()


# ── Tabs ───────────────────────────────────────────────────────────────────────

tab_stock, tab_assemble, tab_ship, tab_receive = st.tabs(
    ["📊 Stock", "🔧 Assemble", "🚚 Ship Out", "📥 Receive Stock"]
)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — STOCK
# ══════════════════════════════════════════════════════════════════════════════
with tab_stock:
    if st.button("🔄 Refresh", key="refresh_stock"):
        st.cache_data.clear()

    item_stock = get_item_stock()

    # ── Low stock alerts (show at top so visible immediately on mobile) ────────
    alerts = [
        (item_id, s) for item_id, s in item_stock.items()
        if s["reorder_point"] > 0 and s["qty"] <= s["reorder_point"]
    ]
    if alerts:
        st.subheader("⚠️ Reorder Alerts")
        for _, s in sorted(alerts, key=lambda x: x[1]["qty"]):
            icon = "🔴" if s["qty"] == 0 else "🟡"
            st.warning(f"{icon} **{s['name']}** — {s['qty']} {s['unit']}s left (reorder at {s['reorder_point']})")
        st.divider()

    # ── SKU stock + assemblable ───────────────────────────────
    st.subheader("Assembled SKU Stock")
    sku_stock   = {r["sku_id"]: r for r in get_sku_stock()}
    assemblable = {r["sku_id"]: r["assemblable"] for r in get_assemblable()}
    skus        = load_skus()

    rows = []
    for sku in skus:
        sid      = sku["sku_id"]
        s        = sku_stock.get(sid, {})
        on_hand  = s.get("qty_on_hand", 0)
        can_make = assemblable.get(sid, 0)
        rows.append({
            "SKU":       sid,
            "Name":      sku["name"],
            "Packed":    on_hand,
            "Can Pack":  can_make,
            "Total":     on_hand + can_make,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.divider()

    # ── Item stock ────────────────────────────────────────────
    st.subheader("Loose Item Stock")
    if item_stock:
        rows = []
        for item_id, s in sorted(item_stock.items(), key=lambda x: x[1]["name"]):
            status = (
                "🔴 OUT" if s["qty"] == 0 else
                "🟡 LOW" if s["qty"] <= s["reorder_point"] and s["reorder_point"] > 0 else
                "🟢"
            )
            rows.append({
                "Item":   s["name"],
                "Qty":    s["qty"],
                "Unit":   s["unit"],
                "Status": status,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No item stock found.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — ASSEMBLE
# ══════════════════════════════════════════════════════════════════════════════
with tab_assemble:
    st.subheader("Pack / Assemble SKUs")

    skus   = load_skus()
    sku_opts = {f"{s['sku_id']} — {s['name']}": s["sku_id"] for s in skus}

    with st.form("assemble_form"):
        sku_label = st.selectbox("SKU to pack", list(sku_opts.keys()))
        qty       = st.number_input("Quantity to pack", min_value=1, value=1, step=1)
        notes     = st.text_input("Notes (optional)")
        submitted = st.form_submit_button("Check & Pack ✅")

    if submitted:
        sku_id = sku_opts[sku_label]
        feasible, detail = check_assembly_feasibility(sku_id, qty)

        st.write("**BOM Check:**")
        check_rows = []
        for d in detail:
            check_rows.append({
                "Item":      d["name"],
                "Unit":      d["unit"],
                "Need":      d["needed"],
                "Available": d["available"],
                "✓":         "✅" if d["ok"] else "❌",
            })
        st.dataframe(pd.DataFrame(check_rows), use_container_width=True, hide_index=True)

        if feasible:
            try:
                unit_cogs = assemble_sku(sku_id, qty, notes=notes, created_by="app")
                st.success(
                    f"✅ Packed **{qty}× {sku_id}** — Unit COGS: ₹{unit_cogs:,.2f}"
                )
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Error: {e}")
        else:
            st.error("❌ Cannot pack — insufficient stock for highlighted items.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — SHIP OUT
# ══════════════════════════════════════════════════════════════════════════════
with tab_ship:
    st.subheader("Ship Out")

    all_channels = load_channels()
    sku_stock    = {r["sku_id"]: r["qty_on_hand"] for r in get_sku_stock()}
    skus         = load_skus()
    blinkit_whs  = load_blinkit_whs()

    DROPSHIP_MODELS = {"DROP_SHIP", "DIRECT"}
    BULK_MODELS     = {"FBA", "SOR", "OUTRIGHT"}

    dropship_channels = [c for c in all_channels if c["business_model"] in DROPSHIP_MODELS]
    bulk_channels     = [c for c in all_channels if c["business_model"] in BULK_MODELS]

    # ── Step 1: shipment type ─────────────────────────────────
    ship_type = st.radio(
        "Shipment type",
        ["🛍️ Drop-ship (end customer order)", "📦 Bulk to partner"],
        horizontal=True,
    )
    is_bulk = ship_type.startswith("📦")

    # ── Step 2: channel ───────────────────────────────────────
    ch_list  = bulk_channels if is_bulk else dropship_channels
    ch_opts  = {c["name"]: c for c in ch_list}
    ch_label = st.selectbox("Partner / Channel", list(ch_opts.keys()))
    ch_data  = ch_opts[ch_label]

    # ── Step 3: Blinkit WH (only for BLK) ────────────────────
    blk_wh_label = None
    if ch_data["code"] == "BLK" and blinkit_whs:
        blk_opts     = {w["name"]: w for w in blinkit_whs}
        blk_wh_label = st.selectbox("Blinkit Warehouse", list(blk_opts.keys()))

    # ── Step 4: reference doc ─────────────────────────────────
    if is_bulk:
        ref_label    = "Delivery Challan #" if ch_data["code"] == "AZ_FBA" else "Invoice #"
        ref_required = True
    else:
        ref_label    = "Order # (optional — can reconcile later)"
        ref_required = False

    reference = st.text_input(ref_label)
    notes     = st.text_input("Notes (optional)")

    # ── Step 5: SKU qty table ─────────────────────────────────
    st.markdown("**Enter quantities to ship:**")

    sku_rows = []
    for s in skus:
        sid   = s["sku_id"]
        stock = sku_stock.get(sid, 0)
        if stock == 0:
            continue
        sku_rows.append({
            "SKU":      sid,
            "Name":     s["name"],
            "In Stock": stock,
            "Ship Qty": 0,
        })

    if not sku_rows:
        st.info("No SKUs currently in stock at Own WH.")
        st.stop()

    edited = st.data_editor(
        pd.DataFrame(sku_rows),
        column_config={
            "SKU":      st.column_config.TextColumn(disabled=True),
            "Name":     st.column_config.TextColumn(disabled=True),
            "In Stock": st.column_config.NumberColumn(disabled=True),
            "Ship Qty": st.column_config.NumberColumn(min_value=0, step=1),
        },
        hide_index=True,
        use_container_width=True,
        key=f"ship_table_{ch_label}",
    )

    to_ship = edited[edited["Ship Qty"] > 0]

    if st.button("Ship Out ✅", type="primary"):
        # Validation
        if ref_required and not reference.strip():
            st.error(f"❌ {ref_label} is required for bulk shipments.")
        elif len(to_ship) == 0:
            st.error("❌ Enter at least one quantity to ship.")
        else:
            ref_str = reference.strip()
            if blk_wh_label:
                ref_str = f"{ref_str} | WH: {blk_wh_label}".strip(" |")

            errors, successes = [], []
            for _, row in to_ship.iterrows():
                sid = row["SKU"]
                qty = int(row["Ship Qty"])
                if qty > row["In Stock"]:
                    errors.append(f"❌ {sid}: only {int(row['In Stock'])} in stock, cannot ship {qty}")
                    continue
                try:
                    txn_type = dispatch_sku(sid, qty, ch_data["channel_id"],
                                            reference=ref_str, notes=notes, created_by="app")
                    verb = "Transferred" if txn_type == "TRANSFER_OUT" else "Dispatched"
                    successes.append(f"✅ {verb} {qty}× {sid}")
                except Exception as e:
                    errors.append(f"❌ {sid}: {e}")

            for msg in successes:
                st.success(msg)
            for msg in errors:
                st.error(msg)

            if successes:
                st.cache_data.clear()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — RECEIVE STOCK
# ══════════════════════════════════════════════════════════════════════════════
with tab_receive:
    st.subheader("Receive Inward Stock")
    st.caption("A new batch is auto-created for each inward date. Same-day inwards for the same item are merged.")

    items     = load_items()
    suppliers = load_suppliers()

    item_opts     = {f"{i['item_code']} — {i['name']}": i for i in items}
    supplier_opts = {"— (not known yet)": None} | {s["name"]: s["supplier_id"] for s in suppliers}

    with st.form("receive_form"):
        item_label    = st.selectbox("Item received", list(item_opts.keys()))
        qty           = st.number_input("Quantity received", min_value=1, value=1, step=1)
        cost          = st.number_input("Cost per unit (₹)", min_value=0.0, value=0.0,
                                        step=0.5, format="%.2f")
        supplier_name = st.selectbox("Supplier", list(supplier_opts.keys()))
        recv_date     = st.date_input("Inward date", value=date.today())
        notes         = st.text_input("Notes (optional)")
        submitted     = st.form_submit_button("Record Receipt ✅")

    if submitted:
        item_data   = item_opts[item_label]
        supplier_id = supplier_opts[supplier_name]

        try:
            batch_id = receive_item(
                item_id      = item_data["item_id"],
                qty          = qty,
                cost_per_unit= cost,
                supplier_id  = supplier_id,
                receipt_date = recv_date,
                notes        = notes,
                created_by   = "app",
            )
            st.success(
                f"✅ Received **{qty}× {item_data['name']}** "
                f"@ ₹{cost:.2f}/unit on {recv_date.strftime('%d %b %Y')} "
                f"(Batch #{batch_id})"
            )
            st.cache_data.clear()
        except Exception as e:
            st.error(f"Error: {e}")
