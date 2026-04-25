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
    return_sku, return_item, writeoff_sku, writeoff_item,
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

tab_stock, tab_assemble, tab_ship, tab_receive, tab_returns = st.tabs(
    ["📊 Stock", "🔧 Assemble", "🚚 Ship Out", "📥 Receive Stock", "↩️ Returns"]
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
        ["🛍️ Drop-ship (end customer order)", "📦 Bulk to partner", "🗑️ Write-off (Lost / Damaged / QC)"],
        horizontal=True,
    )
    is_bulk     = ship_type.startswith("📦")
    is_writeoff = ship_type.startswith("🗑️")

    # ── Write-off branch (no channel needed) ─────────────────
    if is_writeoff:
        writeoff_level = st.radio(
            "What are you writing off?",
            ["📦 Assembled SKU", "🧺 Loose Item / Packaging"],
            horizontal=True,
        )
        reason = st.selectbox("Reason", ["Lost", "Damaged", "QC Reject"])
        wo_notes = st.text_input("Notes (optional)", key="wo_notes")

        if writeoff_level.startswith("📦"):
            st.markdown("**Enter quantities to write off:**")
            sku_stock_wo = {r["sku_id"]: r["qty_on_hand"] for r in get_sku_stock()}
            wo_rows = [
                {"SKU": s["sku_id"], "Name": s["name"],
                 "In Stock": sku_stock_wo.get(s["sku_id"], 0), "Write-off Qty": 0}
                for s in load_skus() if sku_stock_wo.get(s["sku_id"], 0) > 0
            ]
            if not wo_rows:
                st.info("No assembled SKU stock to write off.")
            else:
                wo_edited = st.data_editor(
                    pd.DataFrame(wo_rows),
                    column_config={
                        "SKU":           st.column_config.TextColumn(disabled=True),
                        "Name":          st.column_config.TextColumn(disabled=True),
                        "In Stock":      st.column_config.NumberColumn(disabled=True),
                        "Write-off Qty": st.column_config.NumberColumn(min_value=0, step=1),
                    },
                    hide_index=True, use_container_width=True, key="wo_sku_table",
                )
                if st.button("Write Off ✅", type="primary", key="wo_sku_btn"):
                    to_wo = wo_edited[wo_edited["Write-off Qty"] > 0]
                    if len(to_wo) == 0:
                        st.error("Enter at least one quantity.")
                    else:
                        for _, row in to_wo.iterrows():
                            try:
                                writeoff_sku(row["SKU"], int(row["Write-off Qty"]),
                                             reason=reason, notes=wo_notes, created_by="app")
                                st.success(f"✅ Written off {int(row['Write-off Qty'])}× {row['SKU']} [{reason}]")
                            except Exception as e:
                                st.error(f"❌ {row['SKU']}: {e}")
                        st.cache_data.clear()
        else:
            skus_wo     = load_skus()
            sku_wo_opts = {f"{s['sku_id']} — {s['name']}": s["sku_id"] for s in skus_wo}
            sku_wo_sel  = st.selectbox("Which SKU do these items belong to?", list(sku_wo_opts.keys()), key="wo_item_sku")
            sku_wo_id   = sku_wo_opts[sku_wo_sel]

            bom_wo       = (db.table("bom")
                              .select("item_id, items(item_code, name, unit)")
                              .eq("sku_id", sku_wo_id).execute().data)
            item_stock_wo = get_item_stock()

            wo_item_rows = []
            for b in bom_wo:
                item_id = b["item_id"]
                stock   = item_stock_wo.get(item_id, {}).get("qty", 0)
                if stock == 0:
                    continue
                wo_item_rows.append({
                    "Code":          b["items"]["item_code"],
                    "Item":          b["items"]["name"],
                    "Unit":          b["items"]["unit"],
                    "In Stock":      stock,
                    "Write-off Qty": 0,
                    "_item_id":      item_id,
                })

            if not wo_item_rows:
                st.info("No stock found for items in this SKU.")
            else:
                display_cols = ["Code", "Item", "Unit", "In Stock", "Write-off Qty"]
                wo_item_edited = st.data_editor(
                    pd.DataFrame(wo_item_rows),
                    column_config={
                        "Code":          st.column_config.TextColumn(disabled=True),
                        "Item":          st.column_config.TextColumn(disabled=True),
                        "Unit":          st.column_config.TextColumn(disabled=True),
                        "In Stock":      st.column_config.NumberColumn(disabled=True),
                        "Write-off Qty": st.column_config.NumberColumn(min_value=0, step=1),
                        "_item_id":      st.column_config.NumberColumn(disabled=True),
                    },
                    hide_index=True, use_container_width=True, key="wo_item_table",
                    column_order=display_cols,
                )
                if st.button("Write Off ✅", type="primary", key="wo_item_btn"):
                    to_wo = wo_item_edited[wo_item_edited["Write-off Qty"] > 0]
                    if len(to_wo) == 0:
                        st.error("Enter at least one quantity.")
                    else:
                        for _, row in to_wo.iterrows():
                            try:
                                writeoff_item(int(row["_item_id"]), int(row["Write-off Qty"]),
                                              reason=reason, notes=wo_notes, created_by="app")
                                st.success(f"✅ Written off {int(row['Write-off Qty'])}× {row['Item']} [{reason}]")
                            except Exception as e:
                                st.error(f"❌ {row['Item']}: {e}")
                        st.cache_data.clear()
        st.stop()

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


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — RETURNS
# ══════════════════════════════════════════════════════════════════════════════
with tab_returns:
    st.subheader("Inward Returns")
    st.caption("Record stock coming back from any partner. Only inward what is reusable/in good condition.")

    all_channels_ret = load_channels()
    ch_ret_opts      = {c["name"]: c for c in all_channels_ret}
    ch_ret_label     = st.selectbox("Returning partner", list(ch_ret_opts.keys()), key="ret_channel")
    ch_ret           = ch_ret_opts[ch_ret_label]

    return_type = st.radio(
        "What is being returned?",
        ["📦 Full SKU (assembled hamper)", "🧺 Individual items / components only"],
        horizontal=True,
        key="ret_type",
    )

    ret_reference = st.text_input("Reference (optional)", key="ret_ref")
    ret_notes     = st.text_input("Notes (optional)", key="ret_notes")

    # ── Full SKU return — table of all SKUs ──────────────────
    if return_type.startswith("📦"):
        st.markdown("**Enter return qty for each SKU:**")
        skus_ret = load_skus()
        ret_sku_rows = [
            {"SKU": s["sku_id"], "Name": s["name"], "Return Qty": 0}
            for s in skus_ret
        ]
        ret_sku_edited = st.data_editor(
            pd.DataFrame(ret_sku_rows),
            column_config={
                "SKU":        st.column_config.TextColumn(disabled=True),
                "Name":       st.column_config.TextColumn(disabled=True),
                "Return Qty": st.column_config.NumberColumn(min_value=0, step=1),
            },
            hide_index=True, use_container_width=True, key="ret_sku_table",
        )
        if st.button("Inward Return ✅", type="primary", key="ret_sku_btn"):
            to_ret = ret_sku_edited[ret_sku_edited["Return Qty"] > 0]
            if len(to_ret) == 0:
                st.error("Enter at least one quantity.")
            else:
                full_notes = f"Return from {ch_ret_label} | {ret_reference} | {ret_notes}".strip(" |")
                for _, row in to_ret.iterrows():
                    try:
                        return_sku(
                            sku_id          = row["SKU"],
                            qty             = int(row["Return Qty"]),
                            from_channel_id = ch_ret["channel_id"],
                            notes           = full_notes,
                            created_by      = "app",
                        )
                        st.success(f"✅ {int(row['Return Qty'])}× {row['SKU']} returned to OWN_WH from {ch_ret_label}")
                    except Exception as e:
                        st.error(f"❌ {row['SKU']}: {e}")
                st.cache_data.clear()

    # ── Individual item / component return ────────────────────
    else:
        skus_ret     = load_skus()
        sku_ret_opts = {f"{s['sku_id']} — {s['name']}": s["sku_id"] for s in skus_ret}
        sku_ret_sel  = st.selectbox("Which SKU is this return from?", list(sku_ret_opts.keys()), key="ret_item_sku")
        sku_ret_id   = sku_ret_opts[sku_ret_sel]

        bom_ret = (db.table("bom")
                     .select("item_id, items(item_code, name, unit)")
                     .eq("sku_id", sku_ret_id).execute().data)

        st.markdown("**Enter qty for each reusable component being returned:**")
        ret_item_rows = [
            {"Code": b["items"]["item_code"], "Item": b["items"]["name"],
             "Unit": b["items"]["unit"], "Return Qty": 0, "_item_id": b["item_id"]}
            for b in bom_ret
        ]
        ret_item_edited = st.data_editor(
            pd.DataFrame(ret_item_rows),
            column_config={
                "Code":       st.column_config.TextColumn(disabled=True),
                "Item":       st.column_config.TextColumn(disabled=True),
                "Unit":       st.column_config.TextColumn(disabled=True),
                "Return Qty": st.column_config.NumberColumn(min_value=0, step=1),
                "_item_id":   st.column_config.NumberColumn(disabled=True),
            },
            hide_index=True, use_container_width=True, key="ret_item_table",
            column_order=["Code", "Item", "Unit", "Return Qty"],
        )
        if st.button("Inward Return ✅", type="primary", key="ret_item_btn"):
            to_ret = ret_item_edited[ret_item_edited["Return Qty"] > 0]
            if len(to_ret) == 0:
                st.error("Enter at least one quantity.")
            else:
                full_notes = f"Return from {ch_ret_label} ({sku_ret_id}) | {ret_reference} | {ret_notes}".strip(" |")
                for _, row in to_ret.iterrows():
                    try:
                        return_item(
                            item_id    = int(row["_item_id"]),
                            qty        = int(row["Return Qty"]),
                            notes      = full_notes,
                            created_by = "app",
                        )
                        st.success(f"✅ {int(row['Return Qty'])}× {row['Item']} returned to stock")
                    except Exception as e:
                        st.error(f"❌ {row['Item']}: {e}")
                st.cache_data.clear()
