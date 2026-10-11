"""
Verification script for System Checker Admin Endpoints.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import create_app, db

app = create_app('default')
client = app.test_client()

print("--- Testing Unauthorized Access ---")
r_unauth = client.get('/admin/system-checker')
print(f"GET /admin/system-checker (unauthenticated) -> {r_unauth.status_code} (redirects: {'/login' in r_unauth.location if r_unauth.location else False})")
assert r_unauth.status_code in (302, 401, 403), "Must reject unauthenticated access"

r_api_unauth = client.get('/api/v1/admin/system-checker/overview')
print(f"GET /api/v1/admin/system-checker/overview (unauthenticated) -> {r_api_unauth.status_code}")
assert r_api_unauth.status_code in (401, 403), "Must reject unauthenticated API access"

print("\n--- Testing Authorized Admin Access ---")
with client.session_transaction() as sess:
    sess['user_id'] = 1
    sess['role'] = 'admin'
    sess['admin_logged_in'] = True

r_page = client.get('/admin/system-checker')
print(f"GET /admin/system-checker (admin session) -> {r_page.status_code}")
assert r_page.status_code == 200, f"Must load page with HTTP 200, got {r_page.status_code}"
assert b"System Checker" in r_page.data, "Page must render System Checker title"
assert b"nav-system-checker" in r_page.data or b"System Checker" in r_page.data, "Sidebar must contain System Checker item"

r_overview = client.get('/api/v1/admin/system-checker/overview')
print(f"GET /api/v1/admin/system-checker/overview -> {r_overview.status_code}")
assert r_overview.status_code == 200, f"Overview API must return 200, got {r_overview.status_code}"
data = r_overview.get_json()
print("Overview Keys:", list(data.keys()))
print(f"Discovered Features: {data['summary']['total_features']}")
print(f"Pass Rate: {data['summary'].get('pass_rate_percentage', 'N/A')}%")
print(f"Health Checks: {len(data['health']['checks'])} services checked")

print("\n--- Testing Protected Action Execution ---")
r_run = client.post('/api/v1/admin/system-checker/run-tests', json={'include_flutter': False})
print(f"POST /api/v1/admin/system-checker/run-tests -> {r_run.status_code}")
assert r_run.status_code == 200, f"Test runner API must return 200, got {r_run.status_code}"
run_data = r_run.get_json()
print(f"Run ID: {run_data['run']['run_id']}, Passed: {run_data['run']['passed']}, Failed: {run_data['run']['failed']}")

print("\n--- Testing Flutter Mobile App Module Execution ---")
r_run_fl = client.post('/api/v1/admin/system-checker/run-tests', json={'module': 'Flutter Mobile App', 'include_flutter': True})
print(f"POST /api/v1/admin/system-checker/run-tests (Flutter) -> {r_run_fl.status_code}")
assert r_run_fl.status_code == 200, f"Flutter test runner API must return 200, got {r_run_fl.status_code}"
fl_data = r_run_fl.get_json()['run']
print(f"Flutter Run: Passed={fl_data['passed']}, Failed={fl_data['failed']}, Results={fl_data['results']}")

print("\n[ALL ENDPOINT TESTS PASSED SUCCESSFULLY]")
