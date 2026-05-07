-- Add transfer_price column to orders for OUTRIGHT channel P&L
-- SP - transfer_price = channel commission (Peeko/Kiddo equivalent of platform fee)
ALTER TABLE orders ADD COLUMN IF NOT EXISTS transfer_price NUMERIC(12, 4);
