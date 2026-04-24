-- Add unique constraint on suppliers.name so upsert on conflict works
ALTER TABLE suppliers ADD CONSTRAINT suppliers_name_key UNIQUE (name);
