"""
End-to-End Verification Test for:
1. Seller Order Limiting per Time Slot (Optional/Configurable)
2. Off-the-shelf / Botanical Garden Unlimited Capacity Mode
3. Slot Fullness Calculation and Checkout Validation
4. Rider Simultaneous Active Delivery Safeguard (Max 2 Deliveries)
"""
import sys
import os
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import create_app, db
from app.models import User, Store, Order, Rider
from app.utils.store_schedule import (
    sanitize_store_schedule,
    build_store_time_slots,
    validate_delivery_slot,
    DEFAULT_MAX_ORDERS_PER_SLOT
)
from app.rider import MAX_RIDER_ACTIVE_DELIVERIES

app = create_app('default')

ALL_DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

def run_tests():
    with app.app_context():
        print("=== TEST 1: Schedule Sanitization & Opt-in Config ===")
        # Case A: Off-the-shelf store (e.g. Botanical Garden) - limit disabled
        botanical_sched = {
            'schedules': [{'days': ALL_DAYS, 'open': '08:00', 'close': '18:00'}],
            'slot_duration': 2,
            'limit_orders_per_slot': False,
            'max_orders_per_slot': 5,
        }
        sanitized_botanical = sanitize_store_schedule(botanical_sched)
        assert sanitized_botanical['limit_orders_per_slot'] is False, "limit_orders_per_slot must be False"
        assert sanitized_botanical['max_orders_per_slot'] is None, "max_orders_per_slot must be None when disabled"
        print(" [PASS] Botanical garden / off-the-shelf store schedule correctly keeps limit disabled (unlimited).")

        # Case B: Florist store - limit enabled with custom capacity
        florist_sched = {
            'schedules': [{'days': ALL_DAYS, 'open': '08:00', 'close': '18:00'}],
            'slot_duration': 2,
            'limit_orders_per_slot': True,
            'max_orders_per_slot': 3,
        }
        sanitized_florist = sanitize_store_schedule(florist_sched)
        assert sanitized_florist['limit_orders_per_slot'] is True, "limit_orders_per_slot must be True"
        assert sanitized_florist['max_orders_per_slot'] == 3, "max_orders_per_slot must be 3"
        print(" [PASS] Florist store schedule correctly saves limit_orders_per_slot=True and max_orders_per_slot=3.")

        # Case C: Limit enabled without explicit number falls back to DEFAULT_MAX_ORDERS_PER_SLOT
        fallback_sched = {
            'schedules': [{'days': ALL_DAYS, 'open': '08:00', 'close': '18:00'}],
            'limit_orders_per_slot': True,
            'max_orders_per_slot': None,
        }
        sanitized_fallback = sanitize_store_schedule(fallback_sched)
        assert sanitized_fallback['max_orders_per_slot'] == DEFAULT_MAX_ORDERS_PER_SLOT
        print(f" [PASS] Fallback logic assigns DEFAULT_MAX_ORDERS_PER_SLOT ({DEFAULT_MAX_ORDERS_PER_SLOT}).")

        print("\n=== TEST 2: Slot Fullness & Capacity Calculation ===")
        test_store = Store.query.first()
        if not test_store:
            print(" [SKIP] No store found in test database.")
            return

        future_date = date.today() + timedelta(days=3)
        future_date_str = future_date.strftime('%Y-%m-%d')

        # Set store schedule with limit = 2
        test_store.store_schedule = {
            'schedules': [{'days': ALL_DAYS, 'open': '08:00', 'close': '18:00'}],
            'slot_duration': 2,
            'limit_orders_per_slot': True,
            'max_orders_per_slot': 2,
        }
        db.session.commit()

        # Step 2.1: Initial check - 0 orders booked
        slots_info = build_store_time_slots(test_store, future_date)
        assert slots_info['has_schedule'] is True, f"has_schedule was False: {slots_info}"
        assert len(slots_info['time_slots']) > 0, "Should have time slots"
        for s in slots_info['time_slots']:
            assert s['is_full'] is False, f"Slot {s['value']} should not be full"
            assert s['booked_count'] == 0, f"Slot {s['value']} booked_count should be 0"
            assert s['max_orders'] == 2, f"Slot {s['value']} max_orders should be 2"
        print(f" [PASS] Zero orders: slots open with max_orders=2 and booked_count=0.")

        # Step 2.2: Add 1 mock active order for the first slot
        slot_val = slots_info['time_slots'][0]['value']
        cust = User.query.filter_by(role='customer').first()
        test_order1 = Order(
            customer_id=cust.id if cust else 1,
            store_id=test_store.id,
            status='accepted',
            total_amount=100.0,
            requested_delivery_date=future_date,
            requested_delivery_time=slot_val
        )
        db.session.add(test_order1)
        db.session.commit()

        slots_info = build_store_time_slots(test_store, future_date)
        matching = [s for s in slots_info['time_slots'] if s['value'] == slot_val][0]
        assert matching['booked_count'] == 1, f"Expected booked_count=1, got {matching['booked_count']}"
        assert matching['is_full'] is False, "1/2 capacity should not be full"
        print(f" [PASS] 1 order: booked_count=1, is_full=False.")

        # Step 2.3: Add 2nd mock active order -> fills capacity
        test_order2 = Order(
            customer_id=cust.id if cust else 1,
            store_id=test_store.id,
            status='preparing',
            total_amount=120.0,
            requested_delivery_date=future_date,
            requested_delivery_time=slot_val
        )
        db.session.add(test_order2)
        db.session.commit()

        slots_info = build_store_time_slots(test_store, future_date)
        matching = [s for s in slots_info['time_slots'] if s['value'] == slot_val][0]
        assert matching['booked_count'] == 2, f"Expected booked_count=2, got {matching['booked_count']}"
        assert matching['is_full'] is True, "2/2 capacity must be flagged as full"
        print(f" [PASS] 2 orders (at capacity): booked_count=2, is_full=True.")

        # Step 2.4: Validation rejection
        val_err = validate_delivery_slot(test_store, future_date_str, slot_val)
        assert val_err is not None, "Validation must reject fully booked slot"
        assert 'fully booked' in val_err.lower(), f"Error message must mention fully booked, got: {val_err}"
        print(f" [PASS] validate_delivery_slot correctly blocks checkout: '{val_err}'")

        # Step 2.5: Cancel an order -> capacity freed up
        test_order2.status = 'cancelled'
        db.session.commit()

        slots_info = build_store_time_slots(test_store, future_date)
        matching = [s for s in slots_info['time_slots'] if s['value'] == slot_val][0]
        assert matching['booked_count'] == 1, f"Cancelled order must not count, got {matching['booked_count']}"
        assert matching['is_full'] is False, "Slot should reopen when order is cancelled"
        print(f" [PASS] Order cancellation immediately frees up slot capacity (booked_count=1, is_full=False).")

        # Cleanup test orders
        db.session.delete(test_order1)
        db.session.delete(test_order2)
        db.session.commit()

        print("\n=== TEST 3: Botanical Garden Unlimited Mode ===")
        # Reconfigure store with limit_orders_per_slot = False
        test_store.store_schedule = {
            'schedules': [{'days': ALL_DAYS, 'open': '08:00', 'close': '18:00'}],
            'slot_duration': 2,
            'limit_orders_per_slot': False,
        }
        db.session.commit()

        # Add 5 orders
        orders_batch = []
        for i in range(5):
            o = Order(
                customer_id=cust.id if cust else 1,
                store_id=test_store.id,
                status='accepted',
                total_amount=50.0,
                requested_delivery_date=future_date,
                requested_delivery_time=slot_val
            )
            orders_batch.append(o)
            db.session.add(o)
        db.session.commit()

        slots_info = build_store_time_slots(test_store, future_date)
        matching = [s for s in slots_info['time_slots'] if s['value'] == slot_val][0]
        assert matching['is_full'] is False, "Botanical garden store must never flag slot as full"
        assert matching['max_orders'] is None, "max_orders must be None when unlimited"
        val_err = validate_delivery_slot(test_store, future_date_str, slot_val)
        assert val_err is None, f"Validation must allow order for botanical garden, got error: {val_err}"
        print(f" [PASS] Botanical garden with 5 orders remains unlimited (is_full=False, valid=True).")

        for o in orders_batch:
            db.session.delete(o)
        db.session.commit()

        print("\n=== TEST 4: Rider Active Delivery Safeguard ===")
        assert MAX_RIDER_ACTIVE_DELIVERIES == 2, "MAX_RIDER_ACTIVE_DELIVERIES must be 2"
        print(f" [PASS] MAX_RIDER_ACTIVE_DELIVERIES is set to {MAX_RIDER_ACTIVE_DELIVERIES}.")

        rider = Rider.query.first()
        if rider:
            active_count = Order.query.filter(
                Order.rider_id == rider.id,
                Order.status == 'on_delivery'
            ).count()
            print(f" [INFO] Current rider #{rider.id} active on_delivery orders: {active_count}")

            client = app.test_client()
            mock_order = Order(
                customer_id=cust.id if cust else 1,
                store_id=rider.store_id,
                status='done_preparing',
                total_amount=200.0,
                fulfillment_type='delivery'
            )
            db.session.add(mock_order)
            db.session.commit()

            fake_active1 = Order(
                customer_id=cust.id if cust else 1,
                store_id=rider.store_id,
                rider_id=rider.id,
                status='on_delivery',
                total_amount=150.0
            )
            fake_active2 = Order(
                customer_id=cust.id if cust else 1,
                store_id=rider.store_id,
                rider_id=rider.id,
                status='on_delivery',
                total_amount=180.0
            )
            db.session.add(fake_active1)
            db.session.add(fake_active2)
            db.session.commit()

            try:
                active_now = Order.query.filter(
                    Order.rider_id == rider.id,
                    Order.status == 'on_delivery'
                ).count()
                assert active_now >= 2

                from flask_jwt_extended import create_access_token
                access_token = create_access_token(identity=str(rider.user_id))
                res = client.post(
                    f'/api/v1/rider/orders/{mock_order.id}/accept',
                    headers={'Authorization': f'Bearer {access_token}'}
                )
                assert res.status_code == 400, f"Expected 400 when rider at limit, got {res.status_code} - {res.get_json()}"
                data = res.get_json()
                assert 'limit reached' in data.get('error', '').lower(), f"Expected limit reached error, got: {data}"
                print(f" [PASS] Rider endpoint blocked 3rd active delivery: {data['error']}")
            finally:
                # Guaranteed Cleanup
                db.session.delete(mock_order)
                db.session.delete(fake_active1)
                db.session.delete(fake_active2)
                db.session.commit()
            print(" [PASS] Rider workload safeguard verified.")

        print("\n==================================================")
        print(" ALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
        print("==================================================")

if __name__ == '__main__':
    run_tests()
