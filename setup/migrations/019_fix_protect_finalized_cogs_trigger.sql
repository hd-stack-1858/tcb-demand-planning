-- Migration 019: Fix trigger to allow backfilling cogs when it was never set.
-- The original trigger (018) protected ALL finalized rows unconditionally, which
-- permanently locked in the broken state: lot_cogs_finalized=TRUE but cogs=NULL.
-- Only protect rows where cogs was actually set (IS NOT NULL).

CREATE OR REPLACE FUNCTION orders_protect_finalized_cogs()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.lot_cogs_finalized = TRUE AND OLD.cogs IS NOT NULL THEN
        NEW.cogs               := OLD.cogs;
        NEW.lot_cogs_finalized := OLD.lot_cogs_finalized;
        NEW.lot_id             := OLD.lot_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
