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
    schedule_constraint_error,
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

        print("\n=== TEST 5: Pickup vs Delivery Window & Cutoff Differentiation ===")
        # Configure store with operating hours 08:00-20:00, delivery window 10:00-16:00, cutoff 14:00
        test_store.store_schedule = {
            'schedules': [{'days': ALL_DAYS, 'open': '08:00', 'close': '20:00'}],
            'slot_duration': 2,
            'delivery_start': '10:00',
            'delivery_cutoff': '16:00',
            'order_cutoff': '14:00',
            'lead_time_hours': 1,
            'allow_same_day': True,
            'limit_orders_per_slot': True,
            'max_orders_per_slot': 2,
        }
        db.session.commit()

        # Step 5.1: Verify delivery slot window vs pickup slot window
        delivery_slots = build_store_time_slots(test_store, future_date, fulfillment_type='delivery')
        pickup_slots = build_store_time_slots(test_store, future_date, fulfillment_type='pickup')

        deliv_values = [s['value'] for s in delivery_slots['time_slots']]
        pickup_values = [s['value'] for s in pickup_slots['time_slots']]

        print(f" Delivery slots (clipped to 10:00-16:00): {deliv_values}")
        print(f" Pickup slots (full store hours 08:00-20:00): {pickup_values}")

        assert '08:00-10:00' not in deliv_values, "Delivery slots must not include 08:00-10:00 (before delivery_start)"
        assert '16:00-18:00' not in deliv_values, "Delivery slots must not include 16:00-18:00 (after delivery_cutoff)"
        assert '08:00-10:00' in pickup_values, "Pickup slots must include 08:00-10:00 (store opening)"
        assert '16:00-18:00' in pickup_values, "Pickup slots must include 16:00-18:00 (store operating hours)"
        assert '18:00-20:00' in pickup_values, "Pickup slots must include 18:00-20:00 (until store close)"
        print(" [PASS] Pickup slots use full store operating hours; delivery slots clipped to delivery window.")

        # Step 5.2: Verify API endpoint returns fulfillment_type parameter
        client = app.test_client()
        res_deliv = client.get(f'/api/store/{test_store.id}/time-slots?date={future_date_str}&fulfillment_type=delivery')
        data_deliv = res_deliv.get_json()
        assert data_deliv['fulfillment_type'] == 'delivery'
        assert len(data_deliv['time_slots']) == len(deliv_values)

        res_pickup = client.get(f'/api/store/{test_store.id}/time-slots?date={future_date_str}&fulfillment_type=pickup')
        data_pickup = res_pickup.get_json()
        assert data_pickup['fulfillment_type'] == 'pickup'
        assert len(data_pickup['time_slots']) == len(pickup_values)
        print(" [PASS] Web & mobile API endpoints correctly accept and process fulfillment_type.")

        # Step 5.3: Pickup slot capacity limiting
        # Add 2 pickup orders to the 18:00-20:00 slot
        pickup_slot_val = '18:00-20:00'
        pickup_order1 = Order(
            customer_id=cust.id if cust else 1,
            store_id=test_store.id,
            status='accepted',
            total_amount=90.0,
            requested_delivery_date=future_date,
            requested_delivery_time=pickup_slot_val,
            fulfillment_type='pickup'
        )
        pickup_order2 = Order(
            customer_id=cust.id if cust else 1,
            store_id=test_store.id,
            status='preparing',
            total_amount=110.0,
            requested_delivery_date=future_date,
            requested_delivery_time=pickup_slot_val,
            fulfillment_type='pickup'
        )
        db.session.add(pickup_order1)
        db.session.add(pickup_order2)
        db.session.commit()

        pickup_slots_check = build_store_time_slots(test_store, future_date, fulfillment_type='pickup')
        slot_18_20 = [s for s in pickup_slots_check['time_slots'] if s['value'] == pickup_slot_val][0]
        assert slot_18_20['is_full'] is True, "Pickup slot at capacity must be marked is_full=True"

        # Validate delivery slot should reject with pickup wording
        pickup_err = validate_delivery_slot(test_store, future_date_str, pickup_slot_val, fulfillment_type='pickup')
        assert pickup_err is not None
        assert 'pickup window' in pickup_err.lower() and 'fully booked' in pickup_err.lower(), f"Unexpected error: {pickup_err}"
        print(f" [PASS] Pickup capacity validation blocks checkout when full: '{pickup_err}'")

        # Cleanup
        db.session.delete(pickup_order1)
        db.session.delete(pickup_order2)
        db.session.commit()

        print("\n=== TEST 6: Pickup Payment Methods Safeguard ===")
        from app.checkout_routes import _store_allows_pickup
        from app.models import StorePaymentSetting, GCashQR

        # Ensure payment setting exists
        ps = StorePaymentSetting.query.filter_by(store_id=test_store.id).first()
        if not ps:
            ps = StorePaymentSetting(store_id=test_store.id, allow_cop=False, allow_cod=True, allow_gcash=True)
            db.session.add(ps)
            db.session.commit()

        # Temporarily clear QR codes and disable COP
        ps.allow_cop = False
        ps.allow_gcash = True
        test_store.allow_pickup = True
        existing_qrs = list(test_store.gcash_qr_images)
        for qr in existing_qrs:
            db.session.delete(qr)
        db.session.commit()

        db.session.refresh(test_store)
        assert _store_allows_pickup(test_store) is False, "Pickup must be False when no QR code and COP disabled"
        assert test_store.can_accept_pickup() is False
        assert test_store.to_dict()['allow_pickup'] is False
        print(" [PASS] In-store pickup correctly disabled when no GCash QR and COP is disabled.")

        # Enable COP
        ps.allow_cop = True
        db.session.commit()
        db.session.refresh(test_store)
        assert _store_allows_pickup(test_store) is True, "Pickup must be True when COP is enabled"
        assert test_store.can_accept_pickup() is True
        print(" [PASS] In-store pickup allowed when Cash on Pickup (COP) is enabled.")

        # Disable allow_pickup at store level
        test_store.allow_pickup = False
        db.session.commit()
        db.session.refresh(test_store)
        assert _store_allows_pickup(test_store) is False, "Pickup must be False when allow_pickup is False"
        print(" [PASS] In-store pickup disabled when store.allow_pickup is False.")

        # Restore
        test_store.allow_pickup = True
        ps.allow_cop = False
        # re-add dummy QR if needed or leave clean
        dummy_qr = GCashQR(store_id=test_store.id, filename="dummy.png", public_id="dummy_qr", cloudinary_url="https://res.cloudinary.com/dummy.png")
        db.session.add(dummy_qr)
        db.session.commit()
        db.session.refresh(test_store)
        assert _store_allows_pickup(test_store) is True
        # Cleanup dummy QR
        db.session.delete(dummy_qr)
        db.session.commit()

        print("\n=== TEST 7: Time-Interval Overlap Detection (e.g. 4pm-6pm vs 5pm-6pm) ===")
        from app.utils.store_schedule import parse_slot_interval_minutes, _compute_slot_booked_count, _get_active_order_intervals
        
        # Verify interval parsing
        assert parse_slot_interval_minutes("16:00-18:00") == (960, 1080)
        assert parse_slot_interval_minutes("4:00 PM - 6:00 PM") == (960, 1080)
        assert parse_slot_interval_minutes("5:00 PM - 6:00 PM") == (1020, 1080)
        print(" [PASS] parse_slot_interval_minutes correctly parses 12h and 24h slots into minutes.")

        # Set store limit to 1 order per slot
        test_store.store_schedule = {
            'schedules': [{'days': ALL_DAYS, 'open': '08:00', 'close': '20:00'}],
            'slot_duration': 1,  # 1-hour slots: 16:00-17:00, 17:00-18:00, 18:00-19:00
            'limit_orders_per_slot': True,
            'max_orders_per_slot': 1,
            'allow_same_day': True,
        }
        db.session.commit()

        # Add 1 order spanning 4:00 PM - 6:00 PM (16:00-18:00)
        overlap_order = Order(
            customer_id=cust.id if cust else 1,
            store_id=test_store.id,
            status='accepted',
            total_amount=150.0,
            requested_delivery_date=future_date,
            requested_delivery_time='16:00-18:00',
            fulfillment_type='pickup'
        )
        db.session.add(overlap_order)
        db.session.commit()

        try:
            # When customer checks slots with 1-hour intervals:
            slots_1h = build_store_time_slots(test_store, future_date, fulfillment_type='delivery')
            slot_map = {s['value']: s for s in slots_1h['time_slots']}

            # 16:00-17:00 (4pm-5pm) overlaps with 4pm-6pm -> MUST BE FULL
            assert '16:00-17:00' in slot_map
            assert slot_map['16:00-17:00']['is_full'] is True, "16:00-17:00 must be marked full due to 16:00-18:00 order"
            assert slot_map['16:00-17:00']['booked_count'] == 1

            # 17:00-18:00 (5pm-6pm) overlaps with 4pm-6pm -> MUST BE FULL
            assert '17:00-18:00' in slot_map
            assert slot_map['17:00-18:00']['is_full'] is True, "17:00-18:00 must be marked full due to 16:00-18:00 order"
            assert slot_map['17:00-18:00']['booked_count'] == 1
            print(" [PASS] Overlapping slots (16:00-17:00 and 17:00-18:00) correctly detected as fully booked!")

            # 18:00-19:00 (6pm-7pm) does NOT overlap -> MUST BE OPEN
            assert '18:00-19:00' in slot_map
            assert slot_map['18:00-19:00']['is_full'] is False, "18:00-19:00 must be open"
            assert slot_map['18:00-19:00']['booked_count'] == 0
            print(" [PASS] Non-overlapping slot (18:00-19:00) remains open for orders.")

            # Checkout validation must block 17:00-18:00
            val_err = validate_delivery_slot(test_store, future_date_str, '17:00-18:00', fulfillment_type='delivery')
            assert val_err is not None
            assert 'fully booked' in val_err.lower(), f"Expected fully booked error, got: {val_err}"
            print(f" [PASS] Checkout validation blocks overlapping order: '{val_err}'")
        finally:
            db.session.delete(overlap_order)
            db.session.commit()

        print("\n=== TEST 8: Configurable Pickup Cutoff & Dynamic Closing Notice ===")
        # Configure store open 08:00 - 20:00, 2h slots, no pickup cutoff initially
        test_store.store_schedule = {
            'schedules': [{'days': ALL_DAYS, 'open': '08:00', 'close': '20:00'}],
            'slot_duration': 2,
            'limit_orders_per_slot': False,
            'allow_same_day': True,
        }
        db.session.commit()

        # Step 8.1: Test default pickup slots and dynamic closing notice
        res_default = build_store_time_slots(test_store, future_date, fulfillment_type='pickup')
        default_vals = [s['value'] for s in res_default['time_slots']]
        assert '18:00-20:00' in default_vals, "Without cutoff, pickup should extend to store close 20:00"
        assert res_default['store_close'] == '8:00 PM'
        assert '8:00 PM' in res_default['pickup_notice']
        print(f" [PASS] Default pickup slots extend to store close: {default_vals[-1]}")
        print(f" [PASS] Dynamic closing notice generated: '{res_default['pickup_notice']}'")

        # Step 8.2: Set pickup_cutoff to 19:00 (7:00 PM) - 1 hour before store close
        test_store.store_schedule = {
            'schedules': [{'days': ALL_DAYS, 'open': '08:00', 'close': '20:00'}],
            'slot_duration': 2,
            'pickup_cutoff': '19:00',
            'limit_orders_per_slot': False,
            'allow_same_day': True,
        }
        db.session.commit()

        res_cutoff = build_store_time_slots(test_store, future_date, fulfillment_type='pickup')
        cutoff_vals = [s['value'] for s in res_cutoff['time_slots']]
        assert '18:00-20:00' not in cutoff_vals, "Slots past 19:00 must be clipped"
        assert any(s.endswith('19:00') for s in cutoff_vals), f"Last slot must end at pickup_cutoff 19:00, got: {cutoff_vals}"
        assert res_cutoff['pickup_cutoff'] == '19:00'
        assert res_cutoff['store_close'] == '8:00 PM'
        assert '8:00 PM' in res_cutoff['pickup_notice']
        print(f" [PASS] Pickup cutoff clipped final slot: {cutoff_vals[-1]} (store closes at 8:00 PM)")

        # Step 8.3: Verify API returns pickup_notice and pickup_cutoff
        client = app.test_client()
        api_res = client.get(f'/api/store/{test_store.id}/time-slots?date={future_date_str}&fulfillment_type=pickup')
        api_data = api_res.get_json()
        assert api_data['pickup_cutoff'] == '19:00'
        assert api_data['store_close'] == '8:00 PM'
        assert api_data['pickup_notice'] is not None
        print(" [PASS] API response includes pickup_cutoff, store_close, and pickup_notice.")

        # Step 8.4: Verify pickup_cutoff cannot exceed store closing time or precede opening
        sched_past_close = {
            'schedules': [{'days': ALL_DAYS, 'open': '08:00', 'close': '20:00'}],
            'pickup_cutoff': '20:30',
        }
        err_close = schedule_constraint_error(sanitize_store_schedule(sched_past_close))
        assert err_close is not None, "pickup_cutoff past closing must return constraint error"
        assert 'cannot be after store closing' in err_close
        print(f" [PASS] Blocked pickup_cutoff past closing: '{err_close}'")

        sched_before_open = {
            'schedules': [{'days': ALL_DAYS, 'open': '08:00', 'close': '20:00'}],
            'pickup_cutoff': '07:30',
        }
        err_open = schedule_constraint_error(sanitize_store_schedule(sched_before_open))
        assert err_open is not None, "pickup_cutoff before opening must return constraint error"
        assert 'must be at or after store opening' in err_open
        print(f" [PASS] Blocked pickup_cutoff before opening: '{err_open}'")

        # Step 8.5: Verify valid pickup_cutoff within store hours passes validation
        sched_valid = {
            'schedules': [{'days': ALL_DAYS, 'open': '08:00', 'close': '20:00'}],
            'pickup_cutoff': '19:30',
        }
        err_valid = schedule_constraint_error(sanitize_store_schedule(sched_valid))
        assert err_valid is None, f"Valid pickup_cutoff must pass validation, got: {err_valid}"
        print(" [PASS] Valid pickup_cutoff within hours passed validation without error.")

        print("\n==================================================")
        print(" ALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
        print("==================================================")

if __name__ == '__main__':
    run_tests()
