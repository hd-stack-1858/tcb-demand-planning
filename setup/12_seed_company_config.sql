-- Insert account_name key if not exists
INSERT INTO company_config (key, notes)
VALUES ('account_name', 'Bank account name as registered')
ON CONFLICT (key) DO NOTHING;

-- Populate all company config values
UPDATE company_config SET value = 'Goodsense Trading India Private Limited'                                          WHERE key = 'company_name';
UPDATE company_config SET value = '29AALCG8970F1Z0'                                                                  WHERE key = 'gstin';
UPDATE company_config SET value = 'AALCG8970F'                                                                       WHERE key = 'pan';
UPDATE company_config SET value = 'No. 2731, First Floor, HAL 3rd Stage, New Thippasandra, Bengaluru, Karnataka - 560075' WHERE key = 'registered_address';
UPDATE company_config SET value = 'HDFC Bank Ltd.'                                                                   WHERE key = 'bank_name';
UPDATE company_config SET value = 'GOODSENSE TRADING INDIA PRIVATE LIMITED'                                          WHERE key = 'account_name';
UPDATE company_config SET value = '50200107154878'                                                                    WHERE key = 'bank_account';
UPDATE company_config SET value = 'HDFC0000075'                                                                      WHERE key = 'bank_ifsc';
UPDATE company_config SET value = 'GT_26-27_'                                                                        WHERE key = 'invoice_prefix';
UPDATE company_config SET value = '0'                                                                                 WHERE key = 'invoice_counter';
