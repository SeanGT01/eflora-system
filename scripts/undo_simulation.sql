-- =========================================================
-- STANDBY UNDO SCRIPT FOR ONLINE ORDER SIMULATION V2
-- Run this in psql or Railway database query console if needed
-- =========================================================

BEGIN;

-- 1. Delete ratings
DELETE FROM product_ratings WHERE order_id IN (808, 809, 810, 811, 812, 813, 814, 815, 816, 817, 818);
DELETE FROM store_ratings WHERE order_id IN (808, 809, 810, 811, 812, 813, 814, 815, 816, 817, 818);

-- 2. Delete order items & orders
DELETE FROM order_items WHERE order_id IN (808, 809, 810, 811, 812, 813, 814, 815, 816, 817, 818);
DELETE FROM orders WHERE id IN (808, 809, 810, 811, 812, 813, 814, 815, 816, 817, 818);

-- 3. Delete stock reduction audit records
DELETE FROM stock_reductions WHERE id IN (864, 865, 866, 867, 868, 869, 870, 871, 872, 873, 874, 875, 876, 877, 878, 879, 880);

UPDATE products SET stock_quantity = 120 WHERE id = 352;
UPDATE products SET stock_quantity = 420 WHERE id = 384;
UPDATE products SET stock_quantity = 160 WHERE id = 386;
UPDATE products SET stock_quantity = 101 WHERE id = 388;
UPDATE products SET stock_quantity = 120 WHERE id = 362;
UPDATE products SET stock_quantity = 120 WHERE id = 303;
UPDATE products SET stock_quantity = 50 WHERE id = 368;
UPDATE products SET stock_quantity = 101 WHERE id = 273;
UPDATE products SET stock_quantity = 101 WHERE id = 305;
UPDATE products SET stock_quantity = 101 WHERE id = 277;
UPDATE products SET stock_quantity = 120 WHERE id = 375;
UPDATE products SET stock_quantity = 120 WHERE id = 347;
UPDATE products SET stock_quantity = 120 WHERE id = 380;
UPDATE products SET stock_quantity = 140 WHERE id = 349;
UPDATE products SET stock_quantity = 11000 WHERE id = 382;
UPDATE products SET stock_quantity = 101 WHERE id = 286;

-- 4. Delete simulated riders and customers




COMMIT;
-- End of undo script