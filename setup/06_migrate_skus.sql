-- Remove redundant is_active column from skus (is_discontinued serves the same purpose)
ALTER TABLE skus DROP COLUMN IF EXISTS is_active;
