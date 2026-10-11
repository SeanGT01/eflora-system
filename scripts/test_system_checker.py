"""
Command-line test runner script for E-FLORA System Checker.
"""

import sys
import os
import json

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.system_checker.health import check_system_health
from app.system_checker.runner import execute_tests, execute_order_lifecycle
from app.system_checker.inventory import get_inventory_summary, get_feature_inventory

def main():
    print("==================================================")
    print("   E-FLORA AUTOMATED SYSTEM CHECKER RUNNER")
    print("==================================================")

    app = create_app('default')

    with app.app_context():
        # 1. Feature inventory summary
        summary = get_inventory_summary()
        print(f"\n[INVENTORY] Total Discovered Features: {summary['total_features']}")
        print(f"[INVENTORY] Features With Automated Tests: {summary['features_with_tests']}")
        print(f"[INVENTORY] Features Without Automated Tests: {summary['features_without_tests']}")
        print(f"[INVENTORY] Feature Test Coverage: {summary['coverage_percentage']}%")

        # 2. Health checks
        print("\n[HEALTH CHECKS]")
        health = check_system_health()
        print(f"Overall Status: {health['overall_status'].upper()}")
        for c in health['checks']:
            print(f"  - [{c['status'].upper()}] {c['name']}: {c['details']}")

        # 3. Execute all automated tests
        print("\n[TEST EXECUTION]")
        test_run = execute_tests(app, db, include_flutter=False)
        print(f"Run ID: {test_run['run_id']}")
        print(f"Duration: {test_run['duration_seconds']}s")
        print(f"Passed: {test_run['passed']} / {test_run['total_executed']}")
        print(f"Failed: {test_run['failed']}")
        print(f"Blocked: {test_run['blocked']}")
        print(f"Skipped: {test_run['skipped']}")
        print(f"Pass Rate: {test_run['pass_rate_percentage']}%")
        print(f"Cleanup Status: {test_run['cleanup_status']}")
        for t in test_run['results']:
            if t['status'] == 'failed':
                print(f"  [FAIL] [{t['module']}] {t['feature_name']} -> {t.get('details')}")

        # 4. Execute order lifecycle simulation
        print("\n[ORDER LIFECYCLE SIMULATION]")
        lc = execute_order_lifecycle(app, db)
        print(f"Lifecycle Status: {lc['status'].upper()} ({lc.get('safety_status')})")
        print(f"Details: {lc.get('details') or lc.get('reason')}")
        if 'steps' in lc:
            for s in lc['steps']:
                print(f"  Step {s['step']}: {s['name']} -> {s['status'].upper()}")

        print("\n==================================================")
        print("   SYSTEM CHECKER EXECUTION COMPLETE")
        print("==================================================")

if __name__ == '__main__':
    main()
