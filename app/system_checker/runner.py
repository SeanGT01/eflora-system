"""
E-FLORA Central Test Runner.

Executes:
- All available test suites or specific selected modules
- Non-destructive System Health Checks
- End-to-End Order Lifecycle simulation
- Flutter unit/widget tests
- Produces structured execution reports and execution history.
"""

import os
import sys
import time
import json
import uuid
import subprocess
import shutil
from datetime import datetime
from typing import Dict, Any, List, Optional

from app.system_checker.safety import DatabaseSafetyValidator, TestRecordTracker
from app.system_checker.health import check_system_health
from app.system_checker.inventory import get_feature_inventory, get_inventory_summary

# Import test suites
import app.system_checker.suites.test_auth_security as suite_auth
import app.system_checker.suites.test_customer_storefront as suite_customer
import app.system_checker.suites.test_seller_store as suite_seller
import app.system_checker.suites.test_rider_delivery as suite_rider
import app.system_checker.suites.test_orders_inventory as suite_orders
import app.system_checker.suites.test_payments_financials as suite_payments
import app.system_checker.suites.test_chat_messaging as suite_chat
import app.system_checker.suites.test_admin_module as suite_admin
import app.system_checker.suites.test_integrations as suite_integrations
import app.system_checker.suites.test_lifecycle as suite_lifecycle

# In-memory execution history (keeps last 50 runs)
EXECUTION_HISTORY: List[Dict[str, Any]] = []

SUITE_MAPPING = {
    "test_auth_security": suite_auth,
    "test_customer_storefront": suite_customer,
    "test_seller_store": suite_seller,
    "test_rider_delivery": suite_rider,
    "test_orders_inventory": suite_orders,
    "test_payments_financials": suite_payments,
    "test_chat_messaging": suite_chat,
    "test_admin_module": suite_admin,
    "test_integrations": suite_integrations,
}


def run_flutter_test_suite() -> Dict[str, Any]:
    """Execute Flutter test suite in eflowers_app if flutter CLI is available."""
    # Check custom path or default adjacent workspace directory
    custom_path = os.environ.get("FLUTTER_APP_PATH")
    if custom_path and os.path.isdir(custom_path):
        app_dir = custom_path
    else:
        app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "eflowers_app"))

    if not os.path.isdir(app_dir):
        return {
            "status": "skipped",
            "reason": (
                "Client-side mobile suite: 'eflowers_app' is a separate mobile repository and is not deployed "
                "inside Railway's backend container. Run 'flutter test' in your local development workspace or mobile CI/CD."
            )
        }

    if not shutil.which("flutter"):
        return {
            "status": "skipped",
            "reason": (
                "Flutter CLI is not installed on this host environment. "
                "Run 'flutter test' locally inside the 'eflowers_app' directory."
            )
        }

    t0 = time.time()
    try:
        proc = subprocess.run(
            ["flutter", "test"],
            cwd=app_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
            shell=True
        )
        duration = round(time.time() - t0, 2)
        if proc.returncode == 0:
            return {
                "status": "passed",
                "duration_seconds": duration,
                "stdout": proc.stdout.strip(),
                "details": "All Flutter unit & widget tests passed."
            }
        else:
            return {
                "status": "failed",
                "duration_seconds": duration,
                "stderr": proc.stderr.strip() or proc.stdout.strip(),
                "details": "Flutter tests encountered failures."
            }
    except Exception as e:
        return {
            "status": "blocked",
            "duration_seconds": round(time.time() - t0, 2),
            "reason": f"Could not execute flutter test: {str(e)}"
        }


def execute_tests(
    app,
    db,
    module_filter: Optional[str] = None,
    include_flutter: bool = False
) -> Dict[str, Any]:
    """Execute backend and client tests, calculate metrics, and save to history."""
    run_id = f"run_{uuid.uuid4().hex[:8]}_{int(time.time())}"
    started_at = datetime.utcnow()
    t0 = time.time()

    tracker = TestRecordTracker(run_id=run_id)
    features = get_feature_inventory()

    results: List[Dict[str, Any]] = []
    total_passed = 0
    total_failed = 0
    total_blocked = 0
    total_skipped = 0

    for feat in features:
        if module_filter and feat["module"].lower() != module_filter.lower():
            continue

        feat_id = feat["id"]
        suite_name = feat.get("test_suite")
        func_name = feat.get("test_function")

        # Flutter test dispatch
        if suite_name == "flutter_tests":
            if include_flutter:
                fl_res = run_flutter_test_suite()
                st = fl_res["status"]
                if st == "passed":
                    total_passed += 1
                elif st == "failed":
                    total_failed += 1
                elif st == "blocked":
                    total_blocked += 1
                else:
                    total_skipped += 1
                results.append({
                    "feature_id": feat_id,
                    "feature_name": feat["name"],
                    "module": feat["module"],
                    "status": st,
                    "details": fl_res.get("details") or fl_res.get("reason", ""),
                    "duration_ms": int(fl_res.get("duration_seconds", 0) * 1000)
                })
            else:
                total_skipped += 1
                results.append({
                    "feature_id": feat_id,
                    "feature_name": feat["name"],
                    "module": feat["module"],
                    "status": "skipped",
                    "details": "Flutter tests skipped by filter. Run with include_flutter=true to execute."
                })
            continue

        if not suite_name or suite_name not in SUITE_MAPPING:
            total_skipped += 1
            results.append({
                "feature_id": feat_id,
                "feature_name": feat["name"],
                "module": feat["module"],
                "status": "not_tested",
                "details": "No automated test suite mapped."
            })
            continue

        suite_mod = SUITE_MAPPING[suite_name]
        test_fn = getattr(suite_mod, func_name, None)

        if not test_fn:
            total_blocked += 1
            results.append({
                "feature_id": feat_id,
                "feature_name": feat["name"],
                "module": feat["module"],
                "status": "blocked",
                "details": f"Test function {func_name} not found in {suite_name}."
            })
            continue

        # Execute test function
        sub_t0 = time.time()
        try:
            res = test_fn(app, db, tracker)
            duration_ms = int((time.time() - sub_t0) * 1000)
            status = res.get("status", "passed")
            if status == "passed":
                total_passed += 1
            elif status == "failed":
                total_failed += 1
            elif status == "blocked":
                total_blocked += 1
            else:
                total_skipped += 1

            results.append({
                "feature_id": feat_id,
                "feature_name": feat["name"],
                "module": feat["module"],
                "status": status,
                "details": res.get("details", ""),
                "assertions": res.get("assertions", 1),
                "duration_ms": duration_ms
            })
        except AssertionError as ae:
            total_failed += 1
            results.append({
                "feature_id": feat_id,
                "feature_name": feat["name"],
                "module": feat["module"],
                "status": "failed",
                "details": f"Assertion failed: {str(ae)}",
                "duration_ms": int((time.time() - sub_t0) * 1000)
            })
        except Exception as e:
            total_failed += 1
            results.append({
                "feature_id": feat_id,
                "feature_name": feat["name"],
                "module": feat["module"],
                "status": "failed",
                "details": f"Execution error: {str(e)}",
                "duration_ms": int((time.time() - sub_t0) * 1000)
            })

    # Cleanup any tracked records
    deleted_count, cleanup_logs = tracker.cleanup(db.session)
    is_clean, orphan_logs = tracker.verify_cleanup(db.session)

    completed_at = datetime.utcnow()
    total_executed = total_passed + total_failed
    pass_rate = round((total_passed / total_executed * 100), 1) if total_executed > 0 else 0.0

    summary = {
        "run_id": run_id,
        "started_at": started_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "completed_at": completed_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "duration_seconds": round(time.time() - t0, 2),
        "module_filter": module_filter or "all",
        "total_discovered": len(features),
        "total_executed": total_executed,
        "passed": total_passed,
        "failed": total_failed,
        "blocked": total_blocked,
        "skipped": total_skipped,
        "pass_rate_percentage": pass_rate,
        "cleanup_status": "verified_clean" if is_clean else "cleanup_warning",
        "deleted_records_count": deleted_count,
        "results": results
    }

    # Store in history
    EXECUTION_HISTORY.insert(0, summary)
    if len(EXECUTION_HISTORY) > 50:
        EXECUTION_HISTORY.pop()

    return summary


def execute_order_lifecycle(app, db) -> Dict[str, Any]:
    """Execute dedicated order lifecycle test with safety verification and logging."""
    run_id = f"lifecycle_{uuid.uuid4().hex[:8]}"
    tracker = TestRecordTracker(run_id=run_id)

    res = suite_lifecycle.run_order_lifecycle_test(app, db, tracker)
    res["run_id"] = run_id
    res["executed_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    # Store in history
    EXECUTION_HISTORY.insert(0, {
        "run_id": run_id,
        "started_at": res["executed_at"],
        "completed_at": res["executed_at"],
        "duration_seconds": 0.1,
        "module_filter": "Order Lifecycle E2E",
        "total_discovered": 1,
        "total_executed": 1,
        "passed": 1 if res.get("status") == "passed" else 0,
        "failed": 1 if res.get("status") == "failed" else 0,
        "blocked": 1 if res.get("status") == "blocked" else 0,
        "skipped": 0,
        "pass_rate_percentage": 100.0 if res.get("status") == "passed" else 0.0,
        "cleanup_status": res.get("cleanup_status", "verified_clean"),
        "results": [{
            "feature_id": "order_lifecycle_e2e",
            "feature_name": "End-to-End Order Lifecycle Simulation",
            "module": "Orders & Inventory",
            "status": res.get("status"),
            "details": res.get("details") or res.get("reason", "")
        }]
    })

    return res


def get_execution_history(limit: int = 15) -> List[Dict[str, Any]]:
    return EXECUTION_HISTORY[:limit]
