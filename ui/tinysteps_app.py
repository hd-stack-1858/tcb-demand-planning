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
    record_dropship_sale, record_outright_transfer,
)

st.set_page_config(page_title="Tiny Steps WMS", page_icon="📦", layout="centered")

# ── Header ─────────────────────────────────────────────────────────────────────
import base64
logo_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'logo.png')
if os.path.exists(logo_path):
    with open(logo_path, "rb") as _f:
        _logo_b64 = base64.b64encode(_f.read()).decode()
    st.markdown(
        f"""<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
            <img src="data:image/png;base64,{_logo_b64}" width="70"/>
            <h2 style="margin:0;padding:0;">Tiny Steps WMS</h2>
        </div>""",
        unsafe_allow_html=True,
    )
else:
    st.markdown("## Tiny Steps WMS")

db = get_client()

# ── Session state init ─────────────────────────────────────────────────────────
for _k, _v in [
    ("assemble_key",     0),
    ("assemble_success", None),
    ("assemble_error",   None),
    ("assembling",       False),
    ("pending_assembly", None),
    ("ship_key",         0),
    ("ship_success",     None),
    ("ship_error",       None),
    ("shipping",         False),
    ("pending_ship",     None),
    ("wo_key",           0),
    ("wo_success",       None),
    ("wo_error",         None),
    ("writing_off",      False),
    ("pending_wo",       None),
    ("ret_key",          0),
    ("ret_success",      None),
    ("returning",        False),
    ("pending_ret",      None),
    ("recv_form_key",    0),
    ("recv_item_prev",   None),
    ("receiving",        False),
    ("pending_receipt",  None),
    ("recv_success",     None),
    ("recv_error",       None),
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

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

@st.cache_data(ttl=300)
def load_sku_prices():
    """Latest selling price per SKU from sku_pricing (most recent effective_date)."""
    rows = db.table("sku_pricing").select("sku_id, sp, effective_date")\
             .order("effective_date", desc=True).execute().data
    prices = {}
    for r in rows:
        if r["sku_id"] not in prices:
            prices[r["sku_id"]] = float(r["sp"] or 0)
    return prices  # sku_id → sp

@st.cache_data(ttl=60)
def load_sor_whs(channel_id: int):
    """Return active WH-type locations for any SOR channel from the unified table."""
    return db.table("partner_locations")\
             .select("location_id, name, code, city")\
             .eq("channel_id", channel_id)\
             .eq("location_type", "WH")\
             .eq("is_active", True)\
             .order("name").execute().data

@st.cache_data(ttl=300)
def load_bom():
    """Returns {item_id: [sku_id, ...]} — which SKUs use each item."""
    rows = db.table("bom").select("sku_id, item_id").execute().data
    mapping = {}
    for r in rows:
        mapping.setdefault(r["item_id"], []).append(r["sku_id"])
    return mapping

@st.cache_data(ttl=60)
def load_reorder_alerts():
    own_wh = db.table("channels").select("channel_id").eq("code", "OWN_WH").single().execute().data
    own_wh_id = own_wh["channel_id"]
    all_items = (db.table("items")
                   .select("item_id, item_code, name, unit, reorder_point, moq, lead_time_days, suppliers(name)")
                   .gt("reorder_point", 0)
                   .eq("is_active", True)
                   .execute().data)
    inv_rows = (db.table("inventory")
                  .select("item_id, quantity_on_hand")
                  .eq("channel_id", own_wh_id)
                  .execute().data)
    stock_map = {}
    for r in inv_rows:
        stock_map[r["item_id"]] = stock_map.get(r["item_id"], 0) + r["quantity_on_hand"]
    alerts = []
    for it in all_items:
        qty = stock_map.get(it["item_id"], 0)
        rop = it["reorder_point"] or 0
        if qty < rop:
            alerts.append({
                "name":           it["name"],
                "qty":            qty,
                "reorder_point":  rop,
                "moq":            it["moq"] or 1,
                "lead_time_days": it["lead_time_days"] or 7,
                "supplier":       (it.get("suppliers") or {}).get("name", ""),
            })
    return alerts


# ── Tabs ───────────────────────────────────────────────────────────────────────

tab_stock, tab_reorder, tab_assemble, tab_ship, tab_receive, tab_returns, tab_shipments = st.tabs(
    ["📊 Stock", "🔔 Reorder", "🔧 Assemble", "🚚 Ship Out", "📥 Receive Stock", "↩️ Returns", "📦 Blinkit Shipments"]
)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — STOCK
# ══════════════════════════════════════════════════════════════════════════════
with tab_stock:
    if st.button("🔄 Refresh", key="refresh_stock"):
        st.cache_data.clear()

    item_stock = get_item_stock()
    alerts     = load_reorder_alerts()

    if alerts:
        n_critical = sum(1 for s in alerts if s["qty"] == 0)
        n_low      = len(alerts) - n_critical
        parts = []
        if n_critical:
            parts.append(f"🔴 {n_critical} out of stock")
        if n_low:
            parts.append(f"🟡 {n_low} below ROP")
        st.warning(f"**Reorder needed** — {', '.join(parts)}. See **🔔 Reorder** tab.")
        st.divider()

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
            "SKU":      sid,
            "Name":     sku["name"],
            "Packed":   on_hand,
            "Can Pack": can_make,
            "Total":    on_hand + can_make,
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    st.divider()

    st.subheader("Loose Item Stock")
    if item_stock:
        bom_map   = load_bom()        # item_id → [sku_id, ...]
        sku_labels = {s["sku_id"]: f"{s['sku_id']} — {s['name']}" for s in skus}

        sku_filter = st.multiselect(
            "Filter by SKU",
            options=sorted(sku_labels.keys()),
            format_func=lambda sid: sku_labels.get(sid, sid),
            placeholder="Show all items (select a SKU to filter)",
            key="loose_item_sku_filter",
        )

        if sku_filter:
            filtered_items = [
                s for iid, s in item_stock.items()
                if any(sid in sku_filter for sid in bom_map.get(iid, []))
            ]
        else:
            filtered_items = list(item_stock.values())

        rows = []
        for s in sorted(filtered_items, key=lambda x: x["name"]):
            status = (
                "🔴 OUT" if s["qty"] == 0 else
                "🟡 LOW" if s["qty"] <= s["reorder_point"] and s["reorder_point"] > 0 else
                "🟢"
            )
            rows.append({
                "Item":   s["name"],
                "Qty":    s["qty"],
                "Unit":   s["unit"],
                "ROP":    s["reorder_point"] if s["reorder_point"] > 0 else "—",
                "Status": status,
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        elif sku_filter:
            st.info("No items found for the selected SKU(s).")
    else:
        st.info("No item stock found.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — REORDER
# ══════════════════════════════════════════════════════════════════════════════
with tab_reorder:
    if st.button("🔄 Refresh", key="refresh_reorder"):
        st.cache_data.clear()

    ro_alerts = load_reorder_alerts()

    if not ro_alerts:
        st.success("All items are above reorder point. Nothing to order.")
    else:
        n_crit = sum(1 for s in ro_alerts if s["qty"] == 0)
        n_low  = len(ro_alerts) - n_crit
        st.caption(f"{len(ro_alerts)} items below reorder point — {n_crit} out of stock, {n_low} running low")

        rows = []
        for s in sorted(ro_alerts, key=lambda x: (x["qty"] > 0, -x["lead_time_days"])):
            rows.append({
                "Status":      "🔴 OUT" if s["qty"] == 0 else "🟡 LOW",
                "Item":        s["name"],
                "Supplier":    s["supplier"] or "—",
                "Stock":       s["qty"],
                "Reorder At":  s["reorder_point"],
                "Min Order":   s["moq"],
                "Lead Time":   f"{s['lead_time_days']}d",
            })

        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            use_container_width=True,
            column_config={
                "Status":     st.column_config.TextColumn(width="small"),
                "Item":       st.column_config.TextColumn(width="large"),
                "Supplier":   st.column_config.TextColumn(width="medium"),
                "Stock":      st.column_config.NumberColumn(width="small"),
                "Reorder At": st.column_config.NumberColumn(width="small"),
                "Min Order":  st.column_config.NumberColumn(width="small"),
                "Lead Time":  st.column_config.TextColumn(width="small"),
            },
        )
        st.caption("Sorted: out-of-stock first, then by lead time (longest first). Min Order = supplier MOQ.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — ASSEMBLE
# ══════════════════════════════════════════════════════════════════════════════
with tab_assemble:
    st.subheader("Pack / Assemble SKUs")

    # ── Assembling state: form hidden, assembly running ───────────────────────
    if st.session_state.assembling:
        pending = st.session_state.pending_assembly
        with st.status(
            f"Assembling {pending['qty']}× {pending['sku_id']}...", expanded=True
        ) as status:
            st.write("Consuming loose stock (FIFO)...")
            try:
                assemble_sku(pending["sku_id"], pending["qty"],
                             notes=pending["notes"], created_by="app")
                status.update(
                    label=f"Packed {pending['qty']}× {pending['sku_id']}",
                    state="complete", expanded=False,
                )
                st.session_state.assemble_success = (
                    f"✅ Packed **{pending['qty']}× {pending['sku_id']}**"
                )
            except Exception as e:
                status.update(label="Assembly failed", state="error", expanded=True)
                st.session_state.assemble_error = str(e)

        st.session_state.assembling       = False
        st.session_state.pending_assembly = None
        st.session_state.assemble_key    += 1
        st.cache_data.clear()
        st.rerun()

    # ── Normal state ──────────────────────────────────────────────────────────
    if st.session_state.assemble_success:
        st.success(st.session_state.assemble_success)
        if st.button("Dismiss ✕", key="dismiss_assemble"):
            pass
        st.session_state.assemble_success = None

    if st.session_state.assemble_error:
        st.error(f"Assembly failed: {st.session_state.assemble_error}")
        st.session_state.assemble_error = None

    skus     = load_skus()
    sku_opts = {f"{s['sku_id']} — {s['name']}": s["sku_id"] for s in skus}

    with st.form(f"assemble_form_{st.session_state.assemble_key}"):
        sku_label = st.selectbox("SKU to pack", list(sku_opts.keys()))
        qty       = st.number_input("Quantity to pack", min_value=1, value=1, step=1)
        notes     = st.text_input("Notes (optional)")
        submitted = st.form_submit_button("Check & Pack ✅")

    if submitted:
        sku_id = sku_opts[sku_label]
        with st.spinner("Checking stock..."):
            feasible, detail = check_assembly_feasibility(sku_id, qty)

        st.write("**BOM Check:**")
        check_rows = [
            {"Item": d["name"], "Unit": d["unit"], "Need": d["needed"],
             "Available": d["available"], "✓": "✅" if d["ok"] else "❌"}
            for d in detail
        ]
        st.dataframe(pd.DataFrame(check_rows), width="stretch", hide_index=True)

        if feasible:
            st.session_state.assembling       = True
            st.session_state.pending_assembly = {"sku_id": sku_id, "qty": qty, "notes": notes}
            st.rerun()
        else:
            st.error("❌ Cannot pack — insufficient stock for highlighted items.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — SHIP OUT
# ══════════════════════════════════════════════════════════════════════════════
with tab_ship:
    st.subheader("Ship Out")

    # ── Shipping (dispatch) state ─────────────────────────────────────────────
    if st.session_state.shipping:
        p = st.session_state.pending_ship
        errors = []
        with st.status(f"Dispatching to {p['ch_label']}...", expanded=True) as status:
            for row in p["to_ship"]:
                try:
                    if p.get("is_dropship"):
                        record_dropship_sale(
                            sku_id=row["sku"], qty=row["qty"],
                            channel_id=p["channel_id"],
                            selling_price=row["selling_price"],
                            platform_order_id=p["ref_str"] or None,
                            order_date=p.get("order_date"),
                            city=p.get("city") or None,
                            notes=p["notes"], created_by="app",
                        )
                    elif p.get("is_outright"):
                        record_outright_transfer(
                            sku_id=row["sku"], qty=row["qty"],
                            channel_id=p["channel_id"],
                            reference=p["ref_str"],
                            notes=p["notes"], created_by="app",
                        )
                    else:
                        dispatch_sku(row["sku"], row["qty"], p["channel_id"],
                                     reference=p["ref_str"], notes=p["notes"], created_by="app",
                                     partner_location_id=p.get("partner_location_id"))
                    st.write(f"Dispatched {row['qty']}× {row['sku']}")
                except Exception as e:
                    errors.append(f"❌ {row['sku']}: {e}")
            status.update(
                label="Shipment recorded" if not errors else "Completed with errors",
                state="complete" if not errors else "error",
            )
        if errors:
            st.session_state.ship_error = "\n".join(errors)
        if len(errors) < len(p["to_ship"]):
            skus_str = ", ".join(f"{r['qty']}× {r['sku']}" for r in p["to_ship"])
            st.session_state.ship_success = f"✅ Dispatched to **{p['ch_label']}** — {skus_str}"
        st.session_state.shipping     = False
        st.session_state.pending_ship = None
        st.session_state.ship_key    += 1
        st.cache_data.clear()
        st.rerun()

    # ── Write-off state ───────────────────────────────────────────────────────
    if st.session_state.writing_off:
        p = st.session_state.pending_wo
        errors = []
        with st.status("Processing write-off...", expanded=True) as status:
            for row in p["to_wo"]:
                try:
                    if p["level"] == "sku":
                        writeoff_sku(row["sku"], row["qty"],
                                     reason=p["reason"], notes=p["wo_notes"], created_by="app")
                        st.write(f"Written off {row['qty']}x {row['sku']}")
                    else:
                        writeoff_item(row["item_id"], row["qty"],
                                      reason=p["reason"], notes=p["wo_notes"], created_by="app")
                        st.write(f"Written off {row['qty']}x {row['item_name']}")
                except Exception as e:
                    name = row.get("sku", row.get("item_name", "?"))
                    errors.append(f"{name}: {e}")
            status.update(
                label="Done" if not errors else "Completed with errors",
                state="complete" if not errors else "error",
            )
        if not errors:
            if p["level"] == "sku":
                wo_str = ", ".join(f"{r['qty']}x {r['sku']}" for r in p["to_wo"])
            else:
                wo_str = ", ".join(f"{r['qty']}x {r['item_name']}" for r in p["to_wo"])
            st.session_state.wo_success = f"Written off [{p['reason']}] -- {wo_str}"
        else:
            st.session_state.wo_error = "Write-off failed:\n" + "\n".join(errors)
        st.session_state.writing_off = False
        st.session_state.pending_wo  = None
        st.session_state.wo_key     += 1
        st.cache_data.clear()
        st.rerun()

    # ── Success banners ───────────────────────────────────────────────────────
    if st.session_state.ship_success:
        st.success(st.session_state.ship_success)
        if st.button("Dismiss ✕", key="dismiss_ship"):
            pass
        st.session_state.ship_success = None

    if st.session_state.ship_error:
        st.error(st.session_state.ship_error)
        if st.button("Dismiss ✕", key="dismiss_ship_err"):
            pass
        st.session_state.ship_error = None

    if st.session_state.wo_success:
        st.success(st.session_state.wo_success)
        if st.button("Dismiss", key="dismiss_wo"):
            pass
        st.session_state.wo_success = None

    if st.session_state.wo_error:
        st.error(st.session_state.wo_error)
        if st.button("Dismiss", key="dismiss_wo_err"):
            pass
        st.session_state.wo_error = None

    # ── Load data ─────────────────────────────────────────────────────────────
    all_channels = load_channels()
    sku_stock    = {r["sku_id"]: r["qty_on_hand"] for r in get_sku_stock()}
    skus         = load_skus()
    sku_prices   = load_sku_prices()

    DROPSHIP_MODELS = {"DROP_SHIP", "DIRECT"}
    BULK_MODELS     = {"FBA", "SOR", "OUTRIGHT"}

    dropship_channels = [c for c in all_channels if c["business_model"] in DROPSHIP_MODELS]
    bulk_channels     = [c for c in all_channels if c["business_model"] in BULK_MODELS]

    # ── Step 1: shipment type ─────────────────────────────────────────────────
    ship_type = st.radio(
        "Shipment type",
        ["🛍️ Drop-ship (end customer order)", "📦 Bulk to partner", "🗑️ Write-off (Lost / Damaged / QC)"],
        horizontal=True,
        key=f"ship_type_{st.session_state.ship_key}",
    )
    is_bulk     = ship_type.startswith("📦")
    is_writeoff = ship_type.startswith("🗑️")

    # ── Write-off form ────────────────────────────────────────────────────────
    if is_writeoff:
        writeoff_level = st.radio(
            "What are you writing off?",
            ["📦 Assembled SKU", "🧺 Loose Item / Packaging"],
            horizontal=True,
        )
        reason   = st.selectbox("Reason", ["Lost", "Damaged", "QC Reject"])
        wo_notes = st.text_input("Notes (optional)", key=f"wo_notes_{st.session_state.wo_key}")

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
                    hide_index=True, width="stretch",
                    key=f"wo_sku_table_{st.session_state.wo_key}",
                )
                if st.button("Write Off ✅", type="primary", key="wo_sku_btn"):
                    to_wo = wo_edited[wo_edited["Write-off Qty"] > 0]
                    if len(to_wo) == 0:
                        st.error("Enter at least one quantity.")
                    else:
                        st.session_state.writing_off = True
                        st.session_state.pending_wo  = {
                            "level":    "sku",
                            "reason":   reason,
                            "wo_notes": wo_notes,
                            "to_wo":    [{"sku": r["SKU"], "qty": int(r["Write-off Qty"])}
                                         for _, r in to_wo.iterrows()],
                        }
                        st.rerun()
        else:
            sku_wo_opts = {f"{s['sku_id']} — {s['name']}": s["sku_id"] for s in load_skus()}
            sku_wo_sel  = st.selectbox("Which SKU do these items belong to?",
                                        list(sku_wo_opts.keys()), key="wo_item_sku")
            sku_wo_id   = sku_wo_opts[sku_wo_sel]

            bom_wo        = (db.table("bom")
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
                    "Code": b["items"]["item_code"], "Item": b["items"]["name"],
                    "Unit": b["items"]["unit"], "In Stock": stock,
                    "Write-off Qty": 0, "_item_id": item_id,
                })

            if not wo_item_rows:
                st.info("No stock found for items in this SKU.")
            else:
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
                    hide_index=True, width="stretch",
                    key=f"wo_item_table_{st.session_state.wo_key}",
                    column_order=["Code", "Item", "Unit", "In Stock", "Write-off Qty"],
                )
                if st.button("Write Off ✅", type="primary", key="wo_item_btn"):
                    to_wo = wo_item_edited[wo_item_edited["Write-off Qty"] > 0]
                    if len(to_wo) == 0:
                        st.error("Enter at least one quantity.")
                    else:
                        st.session_state.writing_off = True
                        st.session_state.pending_wo  = {
                            "level":    "item",
                            "reason":   reason,
                            "wo_notes": wo_notes,
                            "to_wo":    [{"item_id": int(r["_item_id"]), "item_name": r["Item"],
                                          "qty": int(r["Write-off Qty"])}
                                         for _, r in to_wo.iterrows()],
                        }
                        st.rerun()
        st.stop()

    # ── Step 2: channel ───────────────────────────────────────────────────────
    ch_list  = bulk_channels if is_bulk else dropship_channels
    ch_opts  = {c["name"]: c for c in ch_list}
    ch_label = st.selectbox(
        "Partner / Channel", list(ch_opts.keys()),
        key=f"ship_channel_{st.session_state.ship_key}",
    )
    ch_data = ch_opts[ch_label]

    # ── Step 3: Partner WH (all SOR channels) ────────────────────────────────
    partner_location_id = None
    if ch_data["business_model"] == "SOR":
        sor_whs = load_sor_whs(ch_data["channel_id"])
        if sor_whs:
            wh_opts = {f"{w['name']} ({w['city']})": w for w in sor_whs}
            wh_label = st.selectbox(
                f"{ch_data['name']} Warehouse",
                list(wh_opts.keys()),
                key=f"ship_sor_wh_{st.session_state.ship_key}",
            )
            partner_location_id = wh_opts[wh_label]["location_id"]
        else:
            st.warning(f"No active warehouses found for {ch_data['name']}. Add one in partner_locations.")

    # ── Step 4: reference doc ─────────────────────────────────────────────────
    if is_bulk:
        ref_label    = "Delivery Challan #" if ch_data["code"] == "AZ" else "Invoice #"
        ref_required = True
    else:
        ref_label    = "Order # (optional — can reconcile later)"
        ref_required = False

    reference = st.text_input(ref_label,          key=f"ship_ref_{st.session_state.ship_key}")
    city      = st.text_input("City (optional)",  key=f"ship_city_{st.session_state.ship_key}") if not is_bulk else None

    if not is_bulk:
        order_date = st.date_input(
            "Order Date",
            value=date.today(),
            help="Use the actual order date if you're entering this late. Defaults to today.",
            key=f"ship_order_date_{st.session_state.ship_key}",
        )
    else:
        order_date = None

    notes     = st.text_input("Notes (optional)", key=f"ship_notes_{st.session_state.ship_key}")

    # ── Step 5: SKU qty table ─────────────────────────────────────────────────
    st.markdown("**Enter quantities to ship:**")

    if not is_bulk:
        sku_rows = [
            {"SKU": s["sku_id"], "Name": s["name"],
             "In Stock": sku_stock.get(s["sku_id"], 0),
             "Selling Price (₹)": sku_prices.get(s["sku_id"], 0.0),
             "Ship Qty": 0}
            for s in skus if sku_stock.get(s["sku_id"], 0) > 0
        ]
    else:
        sku_rows = [
            {"SKU": s["sku_id"], "Name": s["name"],
             "In Stock": sku_stock.get(s["sku_id"], 0), "Ship Qty": 0}
            for s in skus if sku_stock.get(s["sku_id"], 0) > 0
        ]

    if not sku_rows:
        st.info("No SKUs currently in stock at Own WH.")
        st.stop()

    if not is_bulk:
        edited = st.data_editor(
            pd.DataFrame(sku_rows),
            column_config={
                "SKU":                st.column_config.TextColumn(disabled=True),
                "Name":               st.column_config.TextColumn(disabled=True),
                "In Stock":           st.column_config.NumberColumn(disabled=True),
                "Selling Price (₹)":  st.column_config.NumberColumn(min_value=0.0, step=0.5, format="%.2f"),
                "Ship Qty":           st.column_config.NumberColumn(min_value=0, step=1),
            },
            hide_index=True, width="stretch",
            key=f"ship_table_{ch_label}_{st.session_state.ship_key}",
        )
    else:
        edited = st.data_editor(
            pd.DataFrame(sku_rows),
            column_config={
                "SKU":      st.column_config.TextColumn(disabled=True),
                "Name":     st.column_config.TextColumn(disabled=True),
                "In Stock": st.column_config.NumberColumn(disabled=True),
                "Ship Qty": st.column_config.NumberColumn(min_value=0, step=1),
            },
            hide_index=True, width="stretch",
            key=f"ship_table_{ch_label}_{st.session_state.ship_key}",
        )

    to_ship = edited[edited["Ship Qty"] > 0]

    if st.button("Ship Out ✅", type="primary"):
        if ref_required and not reference.strip():
            st.error(f"❌ {ref_label} is required for bulk shipments.")
        elif not is_bulk and len(to_ship) > 0 and (to_ship["Selling Price (₹)"] == 0).any():
            st.error("❌ Selling price cannot be 0 for drop-ship orders. Check highlighted rows.")
        elif len(to_ship) == 0:
            st.error("❌ Enter at least one quantity to ship.")
        else:
            ref_str   = reference.strip()
            ship_rows = []
            for _, r in to_ship.iterrows():
                row = {"sku": r["SKU"], "qty": int(r["Ship Qty"]), "in_stock": int(r["In Stock"])}
                if not is_bulk:
                    row["selling_price"] = float(r["Selling Price (₹)"])
                ship_rows.append(row)
            st.session_state.shipping     = True
            st.session_state.pending_ship = {
                "ch_label":    ch_label,
                "channel_id":  ch_data["channel_id"],
                "ref_str":     ref_str,
                "notes":       notes,
                "is_dropship": not is_bulk,
                "is_outright":        is_bulk and ch_data["business_model"] == "OUTRIGHT",
                "city":               city,
                "order_date":         order_date,
                "partner_location_id": partner_location_id,
                "to_ship":            ship_rows,
            }
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — RECEIVE STOCK
# ══════════════════════════════════════════════════════════════════════════════
with tab_receive:
    st.subheader("Receive Inward Stock")
    st.caption("A new batch is auto-created for each inward date. Same-day inwards for the same item are merged.")

    # ── Receiving state: form hidden, DB write running ────────────────────────
    if st.session_state.receiving:
        p = st.session_state.pending_receipt
        with st.status(
            f"Recording {p['qty']}× {p['item_name']}...", expanded=True
        ) as status:
            st.write(f"Creating batch for {p['item_name']}...")
            try:
                batch_id = receive_item(
                    item_id       = p["item_id"],
                    qty           = p["qty"],
                    cost_per_unit = p["cost"],
                    supplier_id   = p["supplier_id"],
                    receipt_date  = p["receipt_date"],
                    notes         = p["notes"],
                    created_by    = "app",
                )
                status.update(label="Receipt recorded", state="complete", expanded=False)
                st.session_state.recv_success = (
                    f"✅ Received **{p['qty']}× {p['item_name']}** "
                    f"@ ₹{p['cost']:.2f}/unit (Batch #{batch_id})"
                )
            except Exception as e:
                status.update(label="Failed", state="error", expanded=True)
                st.session_state.recv_error = str(e)

        st.session_state.receiving       = False
        st.session_state.pending_receipt = None
        st.session_state.recv_form_key  += 1
        st.cache_data.clear()
        st.rerun()

    # ── Normal state ─────────────────────────────────────────────────────────
    if st.session_state.recv_success:
        st.success(st.session_state.recv_success)
        if st.button("Dismiss ✕", key="dismiss_recv"):
            pass
        st.session_state.recv_success = None
    if st.session_state.recv_error:
        st.error(f"Error: {st.session_state.recv_error}")
        st.session_state.recv_error = None

    items     = load_items()
    suppliers = load_suppliers()

    item_opts     = {f"{i['item_code']} — {i['name']}": i for i in items}
    supplier_opts = {"— (not known yet)": None} | {s["name"]: s["supplier_id"] for s in suppliers}

    item_label = st.selectbox("Item received", list(item_opts.keys()), key="recv_item_sel")
    item_data  = item_opts[item_label]

    if st.session_state.recv_item_prev is not None and item_label != st.session_state.recv_item_prev:
        st.session_state.recv_form_key += 1
    st.session_state.recv_item_prev = item_label

    latest_batch = (db.table("item_batches")
                      .select("cost_per_unit, received_date")
                      .eq("item_id", item_data["item_id"])
                      .gt("cost_per_unit", 0)
                      .order("received_date", desc=True)
                      .limit(1).execute().data)
    latest_cost = float(latest_batch[0]["cost_per_unit"]) if latest_batch else 0.0
    if latest_cost > 0:
        st.caption(f"Last recorded cost: ₹{latest_cost:.2f}/unit — edit below if price has changed")

    with st.form(f"receive_form_{st.session_state.recv_form_key}", enter_to_submit=False):
        qty           = st.number_input("Quantity received", min_value=1, value=1, step=1)
        cost          = st.number_input("Cost per unit (₹)", min_value=0.0, value=latest_cost,
                                        step=0.5, format="%.2f")
        supplier_name = st.selectbox("Supplier", list(supplier_opts.keys()))
        recv_date     = st.date_input("Inward date", value=date.today())
        notes         = st.text_input("Notes (optional)")
        submitted     = st.form_submit_button("Record Receipt ✅")

    if submitted:
        supplier_id = supplier_opts[supplier_name]
        st.session_state.receiving = True
        st.session_state.pending_receipt = {
            "item_id":      item_data["item_id"],
            "item_name":    item_data["name"],
            "qty":          qty,
            "cost":         cost,
            "supplier_id":  supplier_id,
            "receipt_date": recv_date,
            "notes":        notes,
        }
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — RETURNS
# ══════════════════════════════════════════════════════════════════════════════
with tab_returns:
    st.subheader("Inward Returns")
    st.caption("Record stock coming back from any partner. Only inward what is reusable/in good condition.")

    # ── Returning state ───────────────────────────────────────────────────────
    if st.session_state.returning:
        p = st.session_state.pending_ret
        errors = []
        with st.status(f"Processing return from {p['ch_ret_label']}...", expanded=True) as status:
            for row in p["to_ret"]:
                try:
                    if p["level"] == "sku":
                        return_sku(
                            sku_id          = row["sku"],
                            qty             = row["qty"],
                            from_channel_id = p["ch_ret_channel_id"],
                            notes           = p["full_notes"],
                            created_by      = "app",
                        )
                        st.write(f"Returned {row['qty']}× {row['sku']}")
                    else:
                        return_item(
                            item_id         = row["item_id"],
                            qty             = row["qty"],
                            from_channel_id = p["ch_ret_channel_id"],
                            notes           = p["full_notes"],
                            created_by      = "app",
                        )
                        st.write(f"Returned {row['qty']}× {row['item_name']}")
                except Exception as e:
                    name = row.get("sku", row.get("item_name", "?"))
                    errors.append(f"❌ {name}: {e}")
            status.update(
                label="Return recorded" if not errors else "Completed with errors",
                state="complete" if not errors else "error",
            )
        for msg in errors:
            st.error(msg)
        if not errors:
            if p["level"] == "sku":
                ret_str = ", ".join(f"{r['qty']}× {r['sku']}" for r in p["to_ret"])
            else:
                ret_str = ", ".join(f"{r['qty']}× {r['item_name']}" for r in p["to_ret"])
            st.session_state.ret_success = f"✅ Returned from **{p['ch_ret_label']}** — {ret_str}"
        st.session_state.returning    = False
        st.session_state.pending_ret  = None
        st.session_state.ret_key     += 1
        st.cache_data.clear()
        st.rerun()

    # ── Normal state ─────────────────────────────────────────────────────────
    if st.session_state.ret_success:
        st.success(st.session_state.ret_success)
        if st.button("Dismiss ✕", key="dismiss_ret"):
            pass
        st.session_state.ret_success = None

    # ── Form ─────────────────────────────────────────────────────────────────
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

    ret_reference = st.text_input("Reference (optional)", key=f"ret_ref_{st.session_state.ret_key}")
    ret_notes     = st.text_input("Notes (optional)",     key=f"ret_notes_{st.session_state.ret_key}")

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
            hide_index=True, width="stretch",
            key=f"ret_sku_table_{st.session_state.ret_key}",
        )
        if st.button("Inward Return ✅", type="primary", key="ret_sku_btn"):
            to_ret = ret_sku_edited[ret_sku_edited["Return Qty"] > 0]
            if len(to_ret) == 0:
                st.error("Enter at least one quantity.")
            else:
                full_notes = f"Return from {ch_ret_label} | {ret_reference} | {ret_notes}".strip(" |")
                st.session_state.returning   = True
                st.session_state.pending_ret = {
                    "level":             "sku",
                    "ch_ret_label":      ch_ret_label,
                    "ch_ret_channel_id": ch_ret["channel_id"],
                    "full_notes":        full_notes,
                    "to_ret":            [{"sku": r["SKU"], "qty": int(r["Return Qty"])}
                                          for _, r in to_ret.iterrows()],
                }
                st.rerun()
    else:
        sku_ret_opts = {f"{s['sku_id']} — {s['name']}": s["sku_id"] for s in load_skus()}
        sku_ret_sel  = st.selectbox("Which SKU is this return from?",
                                     list(sku_ret_opts.keys()), key="ret_item_sku")
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
            hide_index=True, width="stretch",
            key=f"ret_item_table_{st.session_state.ret_key}",
            column_order=["Code", "Item", "Unit", "Return Qty"],
        )
        if st.button("Inward Return ✅", type="primary", key="ret_item_btn"):
            to_ret = ret_item_edited[ret_item_edited["Return Qty"] > 0]
            if len(to_ret) == 0:
                st.error("Enter at least one quantity.")
            else:
                full_notes = (
                    f"Return from {ch_ret_label} ({sku_ret_id}) | {ret_reference} | {ret_notes}"
                ).strip(" |")
                st.session_state.returning   = True
                st.session_state.pending_ret = {
                    "level":             "item",
                    "ch_ret_label":      ch_ret_label,
                    "ch_ret_channel_id": ch_ret["channel_id"],
                    "full_notes":        full_notes,
                    "to_ret":            [{"item_id": int(r["_item_id"]), "item_name": r["Item"],
                                           "qty": int(r["Return Qty"])}
                                          for _, r in to_ret.iterrows()],
                }
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 — BLINKIT SHIPMENTS (Invoice Generator)
# ══════════════════════════════════════════════════════════════════════════════
with tab_shipments:
    from datetime import timedelta
    import os
    from tcb.blinkit_invoice import (
        parse_ro_excel, parse_ro_pdf,
        check_deviations,
        generate_invoice_excel,
        DELIVERY_PARTNER_GSTIN,
        WH_CONSIGNEE, CONSIGNEE_NAME, wh_key_from_pdf_name,
    )

    st.subheader("Blinkit Invoice Generator")

    col_xl, col_pdf = st.columns(2)
    with col_xl:
        ro_excel_file = st.file_uploader(
            "Upload RO Excel (.xlsx) — line items",
            type=["xlsx"], key="ro_excel_upload"
        )
    with col_pdf:
        ro_pdf_file = st.file_uploader(
            "Upload RO PDF (.pdf) — Bill To / Ship To address",
            type=["pdf"], key="ro_pdf_upload"
        )

    if ro_excel_file:
        try:
            ro_data   = parse_ro_excel(ro_excel_file.getvalue())
        except Exception as e:
            st.error(f"Failed to parse RO Excel: {e}")
            st.stop()

        line_items = ro_data["line_items"]
        if not line_items:
            try:
                import io as _io
                _df = pd.read_excel(_io.BytesIO(ro_excel_file.getvalue()), header=0, dtype=str)
                st.error(
                    f"No line items found in the RO Excel. "
                    f"Columns detected: {list(_df.columns[:10])}. "
                    f"First row: {_df.iloc[0].tolist()[:6] if len(_df) > 0 else '(empty)'}"
                )
            except Exception as _e:
                st.error(f"No line items found — also failed to read columns: {_e}")
            st.stop()

        # RO number from filename
        ro_number = os.path.splitext(ro_excel_file.name)[0]

        # ── WH Selection — primary source for consignee address/GSTIN ─────────
        # PDF (if uploaded) is used ONLY to auto-select the WH dropdown.
        # Address and GSTIN always come from the hardcoded WH_CONSIGNEE dict —
        # never from PDF parsing — so layout differences between PDFs don't matter.
        _detected_wh_key = ""
        if ro_pdf_file:
            try:
                pdf_data = parse_ro_pdf(ro_pdf_file.getvalue())
                if pdf_data.get("ro_number") and pdf_data["ro_number"] != ro_number:
                    st.warning(f"RO number in PDF ({pdf_data['ro_number']}) differs from Excel filename ({ro_number}).")
                _detected_wh_key = wh_key_from_pdf_name(pdf_data.get("wh_name", ""))
            except Exception:
                pass  # PDF parse failure is OK — user selects WH manually

        _wh_options = list(WH_CONSIGNEE.keys()) + ["Other (enter manually)"]
        _file_sig = f"{ro_excel_file.name}|{ro_pdf_file.name if ro_pdf_file else ''}"
        if st.session_state.get("_inv_file_sig") != _file_sig:
            st.session_state["_inv_file_sig"] = _file_sig
            if _detected_wh_key:
                st.session_state["_inv_wh_key"] = _detected_wh_key
            else:
                st.session_state["_inv_wh_key"] = _wh_options[0]

        _cur_wh = st.session_state.get("_inv_wh_key", _wh_options[0])
        _wh_idx = _wh_options.index(_cur_wh) if _cur_wh in _wh_options else 0

        st.divider()

        selected_wh = st.selectbox(
            "Destination Warehouse", _wh_options, index=_wh_idx, key="inv_wh_sel"
        )
        st.session_state["_inv_wh_key"] = selected_wh
        # Clear cached consignee inputs when WH dropdown changes so new dict values take effect
        if st.session_state.get("_inv_wh_rendered") != selected_wh:
            st.session_state["_inv_wh_rendered"] = selected_wh
            for _k in ("inv_cname", "inv_caddr", "inv_cgstin"):
                st.session_state.pop(_k, None)

        if selected_wh != "Other (enter manually)":
            wh_info = WH_CONSIGNEE[selected_wh]
            consignee_name    = CONSIGNEE_NAME
            consignee_gstin   = wh_info["gstin"]
            consignee_address = wh_info["address"]
            wh_label = selected_wh
            gstin_missing = not bool(consignee_gstin)
            if gstin_missing:
                st.warning(f"GSTIN not yet recorded for **{selected_wh}**. Enter it below — once confirmed, tell me and I'll hardcode it.")
                tax_type = "IGST"   # safe default until GSTIN is known
            else:
                tax_type  = "CGST_SGST" if consignee_gstin.startswith("29") else "IGST"
                tax_label = "CGST 2.5% + SGST 2.5% (Karnataka — intra-state)" if tax_type == "CGST_SGST" \
                            else "IGST 5% (inter-state)"
                st.caption(f"GSTIN: **{consignee_gstin}** | Tax: **{tax_label}**")
            with st.expander(
                "Consignee details — enter GSTIN" if gstin_missing else "Consignee details (click to view/override)",
                expanded=gstin_missing,
            ):
                consignee_name    = st.text_input("Consignee Name",    value=consignee_name,    key="inv_cname")
                consignee_address = st.text_area ("Consignee Address", value=consignee_address, key="inv_caddr", height=80)
                consignee_gstin   = st.text_input("Consignee GSTIN",   value=consignee_gstin,   key="inv_cgstin")
                if consignee_gstin:
                    tax_type  = "CGST_SGST" if consignee_gstin.startswith("29") else "IGST"
                    tax_label = "CGST 2.5% + SGST 2.5% (Karnataka — intra-state)" if tax_type == "CGST_SGST" \
                                else "IGST 5% (inter-state)"
                    st.caption(f"Tax: **{tax_label}** (from GSTIN)")
        else:
            wh_label = "Manual"
            st.info("Select a known WH above, or enter consignee details manually here.")
            consignee_name    = st.text_input("Consignee Name",    value=CONSIGNEE_NAME, key="inv_cname")
            consignee_address = st.text_area ("Consignee Address", key="inv_caddr", height=80)
            consignee_gstin   = st.text_input("Consignee GSTIN",   key="inv_cgstin")
            if consignee_gstin:
                tax_type  = "CGST_SGST" if consignee_gstin.startswith("29") else "IGST"
                tax_label = "CGST 2.5% + SGST 2.5% (Karnataka — intra-state)" if tax_type == "CGST_SGST" \
                            else "IGST 5% (inter-state)"
                st.caption(f"Tax type: **{tax_label}** (auto from GSTIN)")
            else:
                tax_choice = st.radio(
                    "Tax type",
                    ["IGST 5% — Inter-state", "CGST 2.5% + SGST 2.5% — Karnataka (intra-state)"],
                    key="inv_tax_manual"
                )
                tax_type = "CGST_SGST" if "Karnataka" in tax_choice else "IGST"

        # ── Inputs ─────────────────────────────────────────────────────────────
        c1, c2 = st.columns(2)
        with c1:
            delivery_partner = st.selectbox(
                "Delivery Partner", list(DELIVERY_PARTNER_GSTIN.keys()), key="inv_dp"
            )
        with c2:
            invoice_no = st.text_input("Invoice Number", placeholder="e.g. GT/26-27/015", key="inv_no")

        c3, c4 = st.columns(2)
        with c3:
            invoice_date = st.date_input("Invoice Date", value=date.today(), key="inv_date")
        with c4:
            delivery_date = st.date_input(
                "Delivery Date", value=date.today() + timedelta(days=8), key="inv_del_date"
            )

        # ── Parsed Line Items Preview ──────────────────────────────────────────
        st.subheader("Parsed Line Items")
        preview_rows = []
        for li in line_items:
            preview_rows.append({
                "Item ID":     li["item_code"],
                "Description": li["description"],
                "Qty":         li["quantity"],
                "MRP":         li["mrp"],
                "Landing Rate": li["landing_rate"],
                "Total (₹)":   li["total_amount"],
            })
        preview_df = pd.DataFrame(preview_rows)
        # Totals row
        totals = pd.DataFrame([{
            "Item ID": "TOTAL", "Description": "",
            "Qty": ro_data["total_qty"], "MRP": "",
            "Landing Rate": "", "Total (₹)": ro_data["net_amount"],
        }])
        st.dataframe(pd.concat([preview_df, totals], ignore_index=True),
                     use_container_width=True, hide_index=True)

        # ── Deviation Alerts ───────────────────────────────────────────────────
        try:
            deviations = check_deviations(db, line_items)
            for d in deviations:
                msgs = []
                if d["db_mrp"] and abs(d["ro_mrp"] - d["db_mrp"]) > 0.01:
                    msgs.append(f"MRP: RO=₹{d['ro_mrp']:,.0f} vs DB=₹{d['db_mrp']:,.0f}")
                if d["db_landing"] and abs(d["ro_landing"] - d["db_landing"]) > 0.01:
                    msgs.append(f"Landing: RO=₹{d['ro_landing']:,.0f} vs DB=₹{d['db_landing']:,.0f}")
                if msgs:
                    st.warning(f"⚠️ {d['item_code']} ({d['description'][:30]}): {' | '.join(msgs)} — verify before generating")

        except Exception:
            pass   # deviation check is advisory — never block invoice generation

        # ── Generate Invoice ───────────────────────────────────────────────────
        st.divider()
        if st.button("Generate Invoice", type="primary", key="gen_invoice"):
            if not invoice_no.strip():
                st.error("Please enter an Invoice Number before generating.")
            elif not consignee_name.strip():
                st.error("Consignee name is required — upload PDF or type manually.")
            else:
                try:
                    xlsx_bytes = generate_invoice_excel(
                        line_items       = line_items,
                        ro_number        = ro_number,
                        invoice_no       = invoice_no.strip(),
                        invoice_date     = invoice_date,
                        delivery_date    = delivery_date,
                        delivery_partner = delivery_partner,
                        consignee_name   = consignee_name.strip(),
                        consignee_address= consignee_address.strip(),
                        consignee_gstin  = consignee_gstin.strip(),
                        total_qty        = ro_data["total_qty"],
                        item_count       = ro_data["item_count"],
                        tax_type         = tax_type,
                    )

                    # Build folder name: YYYYMM_RO#_WH Name
                    month_tag  = invoice_date.strftime("%Y%m")
                    wh_suffix  = wh_label.replace(" - ", " ").replace("/", "-") \
                                         .replace("\\", "-").strip()
                    folder_name = f"{month_tag}_{ro_number}_{wh_suffix}"
                    folder = os.path.join(
                        os.path.dirname(__file__), "..", "data", "blinkit",
                        "auto", "shipments", folder_name
                    )
                    os.makedirs(folder, exist_ok=True)

                    # Invoice filename: "Blinkit Invoice GT_26-27_017 (RO 43886110036715).xlsx"
                    safe_inv   = invoice_no.strip().replace("/", "_")
                    inv_fname  = f"Blinkit Invoice {safe_inv} (RO {ro_number}).xlsx"
                    save_path  = os.path.join(folder, inv_fname)
                    with open(save_path, "wb") as f:
                        f.write(xlsx_bytes)

                    # Save RO Excel
                    with open(os.path.join(folder, f"{ro_number}.xlsx"), "wb") as f:
                        f.write(ro_excel_file.getvalue())

                    # Save RO PDF if uploaded
                    if ro_pdf_file:
                        with open(os.path.join(folder, f"{ro_number}.pdf"), "wb") as f:
                            f.write(ro_pdf_file.getvalue())

                    st.success(f"Invoice generated — {invoice_no}")
                    st.caption(f"Saved to: data/blinkit/auto/shipments/{folder_name}/")

                    st.download_button(
                        label    = f"⬇ Download Invoice Excel — {invoice_no}",
                        data     = xlsx_bytes,
                        file_name= inv_fname,
                        mime     = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key      = "dl_invoice",
                    )
                except Exception as e:
                    st.error(f"Invoice generation failed: {e}")
    else:
        st.info("Upload a Blinkit RO Excel file to get started.")
