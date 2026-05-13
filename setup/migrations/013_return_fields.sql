-- Migration 013 — Add structured return reason fields to orders
-- return_reason already exists (free-text from payout loaders)
-- Adding return_responsible and return_customer_verbatim for richer return analytics.
-- All three fields are populated by setup/_populate_az_return_reasons.py from the
-- Az Reco List & Status Google Sheet.

ALTER TABLE orders ADD COLUMN IF NOT EXISTS return_responsible      TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS return_customer_verbatim TEXT;
