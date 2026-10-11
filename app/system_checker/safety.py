"""
E-FLORA Database Safety Guard and Test Cleanup Tracker.

Strictly protects the production database (Railway PostgreSQL) from accidental
data mutations. Manages test-run IDs, tracks created records, and guarantees
reverse-dependency cleanup.
"""

import os
import re
import uuid
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse
from datetime import datetime

class DatabaseSafetyError(Exception):
    """Raised when an operation violates database safety rules."""
    pass


class DatabaseSafetyValidator:
    """Validates whether a database connection is safe for mutating tests."""

    @staticmethod
    def is_production_url(url: Optional[str]) -> bool:
        if not url:
            return False
        clean = str(url).strip().lower()
        # Railway PostgreSQL indicators
        if 'proxy.rlwy.net' in clean or 'railway.internal' in clean or 'roundhouse.proxy.rlwy.net' in clean:
            return True
        # Check hostname
        try:
            parsed = urlparse(clean)
            host = (parsed.hostname or '').lower()
            if 'rlwy.net' in host or 'railway' in host:
                return True
        except Exception:
            pass
        return False

    @classmethod
    def validate_test_environment(cls, db_url: Optional[str], allow_in_memory: bool = True) -> Tuple[bool, str]:
        """
        Returns (is_safe, reason).
        Fails closed: if it's production or unverified, mutating tests are blocked.
        """
        if not db_url:
            return False, "No database URL provided. Mutating tests are disabled."

        db_str = str(db_url).strip()

        # SQLite in-memory or local test file
        if db_str.startswith('sqlite:///:memory:') or 'test' in db_str.lower() and db_str.startswith('sqlite:///'):
            return True, "Safe: Isolated SQLite test database."

        # Production Railway check
        if cls.is_production_url(db_str):
            return False, (
                "BLOCKED (Production Safety): Connected database is the live Railway database. "
                "Mutating/destructive tests are strictly prevented on production data. "
                "Configure a dedicated TEST_DATABASE_URL to enable mutating tests."
            )

        # Check if TEST_DATABASE_URL was explicitly provided and differs from DATABASE_URL
        test_db_env = os.getenv('TEST_DATABASE_URL', '').strip()
        live_db_env = os.getenv('DATABASE_URL', '').strip()

        if test_db_env and test_db_env == db_str:
            if cls.is_production_url(test_db_env):
                return False, "BLOCKED: TEST_DATABASE_URL points to live Railway production database."
            return True, f"Safe: Dedicated test database ({urlparse(test_db_env).hostname or 'local'})."

        # If it's a PostgreSQL URL that isn't Railway and explicitly contains 'test'
        if 'test' in db_str.lower():
            return True, "Safe: Database name or URI explicitly indicates a test environment."

        return False, (
            "BLOCKED: Environment unverified. Database does not have explicit test designation. "
            "Fail-closed protection active."
        )

    @classmethod
    def is_safe_test_db(cls, db_url: Optional[str] = None) -> bool:
        url = db_url or os.getenv('TEST_DATABASE_URL') or os.getenv('DATABASE_URL')
        is_safe, _ = cls.validate_test_environment(url)
        return is_safe


class TestRecordTracker:
    """
    Tracks all records created during a test execution under a unique run ID.
    Performs guaranteed cleanup respecting foreign key dependencies.
    """

    def __init__(self, run_id: Optional[str] = None):
        self.run_id = run_id or f"test_{uuid.uuid4().hex[:12]}"
        self.created_records: List[Dict[str, any]] = []  # List of {'model': ModelClass, 'id': pk_value, 'label': str}
        self.cleanup_log: List[str] = []
        self.is_cleaned_up = False
        self.created_at = datetime.utcnow()
        self.safety_validator = DatabaseSafetyValidator()

    def is_safe_test_db(self, db_url: Optional[str] = None) -> bool:
        """Check if current environment is a verified safe isolated test DB."""
        url = db_url or os.getenv('TEST_DATABASE_URL') or os.getenv('DATABASE_URL')
        is_safe, _ = self.safety_validator.validate_test_environment(url)
        return is_safe

    def track(self, model_class, record_id, label: str = ""):
        """Register a newly created record for cleanup."""
        self.created_records.append({
            'model': model_class,
            'id': record_id,
            'label': label or f"{model_class.__name__}:{record_id}",
            'model_name': model_class.__name__
        })

    def cleanup(self, db_session) -> Tuple[int, List[str]]:
        """
        Delete all tracked records in reverse creation order (children before parents).
        Returns (deleted_count, log_messages).
        """
        if self.is_cleaned_up:
            return 0, ["Already cleaned up."]

        deleted_count = 0
        logs = []

        # Delete in reverse order to respect foreign key constraints
        for item in reversed(self.created_records):
            model = item['model']
            record_id = item['id']
            label = item['label']
            try:
                rec = db_session.query(model).get(record_id)
                if rec:
                    db_session.delete(rec)
                    db_session.commit()
                    deleted_count += 1
                    logs.append(f"Deleted {label}")
                else:
                    logs.append(f"Already removed or not found: {label}")
            except Exception as e:
                db_session.rollback()
                logs.append(f"Failed to delete {label}: {str(e)}")

        self.is_cleaned_up = True
        self.cleanup_log = logs
        return deleted_count, logs

    def verify_cleanup(self, db_session) -> Tuple[bool, List[str]]:
        """Verify that zero tracked records remain in the database."""
        orphans = []
        for item in self.created_records:
            model = item['model']
            record_id = item['id']
            try:
                rec = db_session.query(model).get(record_id)
                if rec:
                    orphans.append(f"Orphan record remained: {item['label']}")
            except Exception as e:
                orphans.append(f"Verification query error for {item['label']}: {e}")
        return len(orphans) == 0, orphans
