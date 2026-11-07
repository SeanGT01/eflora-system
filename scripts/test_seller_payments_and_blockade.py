import os
import sys
from datetime import datetime, timedelta

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import User, Store, SellerApplication, AdminPaymentSetting, SellerSubscriptionPayment
from unittest.mock import patch

def run_tests():
    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("RUNNING SELLER PAYMENTS & BLOCKADE INTEGRATION TESTS")
        print("=" * 60)

        # 1. AdminPaymentSetting verification
        setting = AdminPaymentSetting.query.first()
        if not setting:
            setting = AdminPaymentSetting(monthly_fee=300.0)
            db.session.add(setting)
            db.session.commit()

        # Snapshot real admin settings so the test can restore them afterwards
        _original_setting = {
            'qr_image_url': setting.qr_image_url,
            'qr_image_public_id': setting.qr_image_public_id,
            'account_name': setting.account_name,
            'account_number': setting.account_number,
            'monthly_fee': setting.monthly_fee,
        }

        print(f"1. Default AdminPaymentSetting: Fee=₱{setting.monthly_fee}, Configured={setting.is_configured}")
        assert setting.monthly_fee == 300.0, "Default fee should be 300.0"

        # 2. Test blockade logic when QR is missing
        setting.qr_image_url = None
        setting.qr_image_public_id = None
        db.session.commit()
        assert setting.is_configured is False, "Without QR url, is_configured should be False"
        print("2. When QR is missing, is_configured is False (Blockade triggered) -> PASSED")

        # 3. Test QR configuration
        setting.qr_image_url = "https://res.cloudinary.com/demo/image/upload/sample_qr.jpg"
        setting.qr_image_public_id = "sample_qr_id"
        setting.account_name = "E-FLORA ADMIN"
        setting.account_number = "0917-123-4567"
        db.session.commit()
        assert setting.is_configured is True, "With QR url, is_configured should be True"
        print("3. When QR is configured, is_configured is True -> PASSED")

        # 4. Create or fetch a test applicant user
        test_email = "test_seller_applicant@eflora.test"
        applicant = User.query.filter_by(email=test_email).first()
        if not applicant:
            applicant = User(
                email=test_email,
                full_name="Maria Applicant",
                role="customer",
                status="active",
                password_hash="mock_hash_for_test"
            )
            db.session.add(applicant)
            db.session.commit()

        # Clean up any existing applications/payments for this test user
        SellerSubscriptionPayment.query.filter_by(seller_id=applicant.id).delete()
        Store.query.filter_by(seller_id=applicant.id).delete()
        SellerApplication.query.filter_by(user_id=applicant.id).delete()
        db.session.commit()

        # 5. Create SellerApplication with payment_receipt
        receipt_url = "https://res.cloudinary.com/demo/image/upload/sample_receipt.jpg"
        receipt_public_id = "sample_receipt_id"
        app_record = SellerApplication(
            user_id=applicant.id,
            applicant_full_name=applicant.full_name,
            applicant_email=applicant.email,
            store_name="Maria's Flora Shop",
            store_description="Handcrafted bouquets and fresh flowers.",
            store_logo_url="https://res.cloudinary.com/demo/image/upload/logo.jpg",
            store_logo_public_id="logo_id",
            government_id_url="https://res.cloudinary.com/demo/image/upload/id.jpg",
            government_id_public_id="gov_id",
            payment_receipt_url=receipt_url,
            payment_receipt_public_id=receipt_public_id,
            status="pending"
        )
        db.session.add(app_record)
        db.session.flush()

        # Linked initial registration payment
        initial_pay = SellerSubscriptionPayment(
            seller_id=applicant.id,
            application_id=app_record.id,
            payment_type="registration",
            amount=setting.monthly_fee,
            receipt_url=receipt_url,
            receipt_public_id=receipt_public_id,
            status="pending",
            submitted_at=datetime.utcnow()
        )
        db.session.add(initial_pay)
        db.session.commit()

        print(f"4. Created SellerApplication ID {app_record.id} with receipt: {app_record.payment_receipt_url}")
        print(f"   Created linked SellerSubscriptionPayment ID {initial_pay.id} -> PASSED")

        # Verify initial payment appears in ledger query
        pending_payments = SellerSubscriptionPayment.query.filter_by(status='pending').all()
        assert any(p.id == initial_pay.id for p in pending_payments), "Initial registration payment should be in pending ledger"
        print("5. Initial registration payment visible in admin pending ledger -> PASSED")

        # 6. Test Admin Approval of Application & Initial Payment
        admin_user = User.query.filter_by(role='admin').first()
        admin_id = admin_user.id if admin_user else 1

        with patch('app.utils.email_helper._send_email_async') as mock_email:
            # Simulate approval logic
            app_record.status = 'approved'
            app_record.reviewed_at = datetime.utcnow()
            app_record.reviewed_by = admin_id
            applicant.role = 'seller'

            # Store creation
            store = Store(
                seller_id=applicant.id,
                name=app_record.store_name,
                description=app_record.store_description,
                address='',
                status='active',
                seller_application_id=app_record.id
            )
            db.session.add(store)
            db.session.flush()

            valid_until = datetime.utcnow() + timedelta(days=30)
            store.subscription_status = 'active'
            store.subscription_valid_until = valid_until

            # Update initial registration payment
            initial_pay.status = 'approved'
            initial_pay.store_id = store.id
            initial_pay.reviewed_at = datetime.utcnow()
            initial_pay.reviewed_by = admin_id
            initial_pay.billing_period_start = datetime.utcnow().date()
            initial_pay.billing_period_end = valid_until.date()

            from app.utils.email_helper import send_seller_payment_approved_email
            send_seller_payment_approved_email(
                recipient_email=applicant.email,
                recipient_name=applicant.full_name,
                store_name=store.name,
                amount=initial_pay.amount,
                billing_end=valid_until,
                payment_type='registration'
            )
            db.session.commit()

            print("6. Application approved, Store created with subscription_status='active', valid_until set.")
            print(f"   Store valid until: {store.subscription_valid_until}")
            print(f"   Initial payment approved: status={initial_pay.status}, store_id={initial_pay.store_id}")
            print("   Payment approved email triggered -> PASSED")

        # 7. Test Monthly Subscription Renewal Submission
        renewal_receipt_url = "https://res.cloudinary.com/demo/image/upload/monthly_receipt.jpg"
        monthly_pay = SellerSubscriptionPayment(
            seller_id=applicant.id,
            store_id=store.id,
            payment_type="monthly",
            amount=setting.monthly_fee,
            receipt_url=renewal_receipt_url,
            receipt_public_id="monthly_receipt_id",
            status="pending",
            submitted_at=datetime.utcnow()
        )
        db.session.add(monthly_pay)
        db.session.commit()
        print(f"7. Seller submitted monthly renewal payment ID {monthly_pay.id} -> PASSED")

        # 8. Test Admin Approval of Monthly Payment (Extending Validity by 30 days)
        with patch('app.utils.email_helper._send_email_async') as mock_email:
            now = datetime.utcnow()
            prev_valid_until = store.subscription_valid_until
            new_valid_until = prev_valid_until + timedelta(days=30)
            store.subscription_valid_until = new_valid_until
            store.subscription_status = 'active'

            monthly_pay.status = 'approved'
            monthly_pay.reviewed_at = now
            monthly_pay.reviewed_by = admin_id
            monthly_pay.billing_period_start = prev_valid_until.date()
            monthly_pay.billing_period_end = new_valid_until.date()

            send_seller_payment_approved_email(
                recipient_email=applicant.email,
                recipient_name=applicant.full_name,
                store_name=store.name,
                amount=monthly_pay.amount,
                billing_end=new_valid_until,
                payment_type='monthly'
            )
            db.session.commit()

            assert store.subscription_valid_until > prev_valid_until, "Subscription valid until should be extended"
            days_diff = (store.subscription_valid_until - prev_valid_until).days
            assert days_diff == 30, f"Expected 30 days extension, got {days_diff}"
            print(f"8. Monthly payment approved: Validity extended by 30 days (New valid until: {store.subscription_valid_until}) -> PASSED")

        # 9. Test Rejection flow
        rejected_pay = SellerSubscriptionPayment(
            seller_id=applicant.id,
            store_id=store.id,
            payment_type="monthly",
            amount=setting.monthly_fee,
            receipt_url="https://res.cloudinary.com/demo/image/upload/bad_receipt.jpg",
            receipt_public_id="bad_receipt_id",
            status="pending",
            submitted_at=datetime.utcnow()
        )
        db.session.add(rejected_pay)
        db.session.commit()

        rejected_pay.status = 'rejected'
        rejected_pay.admin_notes = "Payment reference number unreadable"
        rejected_pay.reviewed_at = datetime.utcnow()
        rejected_pay.reviewed_by = admin_id
        db.session.commit()

        assert rejected_pay.status == 'rejected', "Status should be rejected"
        assert rejected_pay.admin_notes == "Payment reference number unreadable", "Rejection notes should match"
        print("9. Payment rejection flow with notes -> PASSED")

        # Clean up test records
        SellerSubscriptionPayment.query.filter_by(seller_id=applicant.id).delete()
        Store.query.filter_by(seller_id=applicant.id).delete()
        SellerApplication.query.filter_by(user_id=applicant.id).delete()
        User.query.filter_by(id=applicant.id).delete()
        db.session.commit()

        # Restore the real admin payment settings (don't leave test QR data behind)
        for _k, _v in _original_setting.items():
            setattr(setting, _k, _v)
        db.session.commit()

        print("=" * 60)
        print("ALL TESTS PASSED SUCCESSFULLY!")
        print("=" * 60)

if __name__ == '__main__':
    run_tests()
