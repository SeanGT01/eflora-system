import os, sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from app import create_app, db
    from app.models import Store, User, POSOrder

    app = create_app()
    with app.app_context():
        s = Store.query.get(21)
        if s:
            print(f"STORE FOUND: id={s.id}, name={s.name}, user_id={s.user_id}")
            u = User.query.get(s.user_id)
            if u:
                print(f"USER FOUND: id={u.id}, name={u.full_name}, email={u.email}, role={u.role}")
        else:
            print("STORE 21 NOT FOUND")

        last_pos = POSOrder.query.order_by(POSOrder.id.desc()).first()
        if last_pos:
            print(f"LAST POS ORDER: id={last_pos.id}, created_at={last_pos.created_at}")
        else:
            print("NO POS ORDERS")
except Exception as e:
    import traceback
    print("EXCEPTION OCCURRED:")
    traceback.print_exc()
