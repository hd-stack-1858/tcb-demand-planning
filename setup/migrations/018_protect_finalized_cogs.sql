-- Migration 018: DB-level guard — once lot_cogs_finalized=TRUE, cogs/lot_id/lot_cogs_finalized
-- can never be overwritten. Belt-and-suspenders alongside the application-level guard
-- in load_amazon_sales.py. Protects against any future code path that might reset
-- finalized COGS.

CREATE OR REPLACE FUNCTION orders_protect_finalized_cogs()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.lot_cogs_finalized = TRUE THEN
        NEW.cogs               := OLD.cogs;
        NEW.lot_cogs_finalized := OLD.lot_cogs_finalized;
        NEW.lot_id             := OLD.lot_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_protect_finalized_cogs
BEFORE UPDATE ON orders
FOR EACH ROW
EXECUTE FUNCTION orders_protect_finalized_cogs();
