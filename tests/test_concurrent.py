"""Tests for concurrent database access safety.

Multiple processes (MCP server, git hooks) will access the database concurrently.
These tests validate that concurrent writes don't corrupt the database.
"""

import multiprocessing
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from waggle.database import init_schema


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


def worker_insert_keys(db_path: str, worker_id: int, num_keys: int) -> None:
    """Worker function that inserts keys into database.
    
    Args:
        db_path: Path to database file
        worker_id: Unique ID for this worker
        num_keys: Number of keys to insert
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    for i in range(num_keys):
        key = f"worker_{worker_id}_key_{i}"
        repo = f"/repo/path{worker_id}"
        status = "working"
        cursor.execute("INSERT OR REPLACE INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", (key, repo, status))
        conn.commit()
    
    conn.close()


def worker_update_key(db_path: str, key: str, worker_id: int, num_updates: int) -> None:
    """Worker function that repeatedly updates the same key.
    
    Args:
        db_path: Path to database file
        key: Key to update
        worker_id: Unique ID for this worker
        num_updates: Number of times to update the key
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    for i in range(num_updates):
        repo = f"/repo/path{worker_id}"
        status = f"update_{i}"
        cursor.execute("INSERT OR REPLACE INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", (key, repo, status))
        conn.commit()
    
    conn.close()


def worker_insert_with_namespace(db_path: str, namespace: str, num_keys: int) -> None:
    """Worker function that inserts keys with namespace prefix.
    
    Args:
        db_path: Path to database file
        namespace: Namespace (repo path) for keys
        num_keys: Number of keys to insert
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    for i in range(num_keys):
        # Make keys unique by including namespace in the key itself
        key = f"{namespace.replace('/', '_')}_session_{i}+{i:03d}"
        status = "working"
        cursor.execute("INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", (key, namespace, status))
        conn.commit()
    conn.close()


class TestConcurrentCreation:
    """Tests for concurrent ticket creation from multiple processes."""
    
    def test_multiple_processes_insert_without_corruption(self, temp_db):
        """Multiple processes inserting different keys don't corrupt database."""
        init_schema(temp_db)
        
        num_workers = 5
        keys_per_worker = 20
        
        # Spawn workers
        processes = []
        for worker_id in range(num_workers):
            p = multiprocessing.Process(
                target=worker_insert_keys,
                args=(temp_db, worker_id, keys_per_worker)
            )
            processes.append(p)
            p.start()
        
        # Wait for all workers to complete
        for p in processes:
            p.join(timeout=10)
            assert p.exitcode == 0, f"Worker process failed with exit code {p.exitcode}"
        
        # Verify all data was written correctly
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM state")
        count = cursor.fetchone()[0]
        expected_count = num_workers * keys_per_worker
        assert count == expected_count, f"Expected {expected_count} rows, got {count}"
        
        # Verify each worker's data is present
        for worker_id in range(num_workers):
            cursor.execute("SELECT COUNT(*) FROM state WHERE key LIKE ?", (f"worker_{worker_id}_%",))
            worker_count = cursor.fetchone()[0]
            assert worker_count == keys_per_worker
        
        conn.close()
    
    def test_concurrent_inserts_different_namespaces(self, temp_db):
        """Concurrent inserts with different namespaces maintain isolation."""
        init_schema(temp_db)
        
        namespaces = ["/repo/a", "/repo/b", "/repo/c"]
        keys_per_namespace = 15
        
        processes = []
        for ns in namespaces:
            p = multiprocessing.Process(
                target=worker_insert_with_namespace,
                args=(temp_db, ns, keys_per_namespace)
            )
            processes.append(p)
            p.start()
        
        for p in processes:
            p.join(timeout=10)
            assert p.exitcode == 0
        
        # Verify namespace isolation
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        for ns in namespaces:
            cursor.execute("SELECT COUNT(*) FROM state WHERE repo = ?", (ns,))
            count = cursor.fetchone()[0]
            assert count == keys_per_namespace
        
        conn.close()


class TestConcurrentUpdates:
    """Tests for concurrent ticket updates from multiple processes."""
    
    def test_multiple_processes_update_different_keys_safely(self, temp_db):
        """Multiple processes updating different keys don't interfere."""
        init_schema(temp_db)
        
        # Pre-populate database with keys
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        num_keys = 5
        for i in range(num_keys):
            cursor.execute("INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", (f"key_{i}", "/repo/initial", "initial"))
        conn.commit()
        conn.close()
        
        # Spawn processes to update different keys
        num_updates = 20
        processes = []
        for key_id in range(num_keys):
            p = multiprocessing.Process(
                target=worker_update_key,
                args=(temp_db, f"key_{key_id}", key_id, num_updates)
            )
            processes.append(p)
            p.start()
        
        for p in processes:
            p.join(timeout=10)
            assert p.exitcode == 0
        
        # Verify all keys were updated
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        for key_id in range(num_keys):
            cursor.execute("SELECT status FROM state WHERE key = ?", (f"key_{key_id}",))
            result = cursor.fetchone()
            assert result is not None
            # Status should be from this worker's last update
            assert result[0] == f"update_{num_updates-1}"
        
        conn.close()
    
    def test_concurrent_updates_same_key_maintains_integrity(self, temp_db):
        """Multiple processes updating same key don't corrupt database."""
        init_schema(temp_db)
        
        shared_key = "shared_key"
        
        # Insert initial value
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", (shared_key, "/repo/initial", "initial"))
        conn.commit()
        conn.close()
        
        # Spawn multiple processes to update the same key
        num_workers = 5
        num_updates = 10
        processes = []
        for worker_id in range(num_workers):
            p = multiprocessing.Process(
                target=worker_update_key,
                args=(temp_db, shared_key, worker_id, num_updates)
            )
            processes.append(p)
            p.start()
        
        for p in processes:
            p.join(timeout=10)
            assert p.exitcode == 0
        
        # Verify database integrity
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Should have exactly one row for the shared key
        cursor.execute("SELECT COUNT(*) FROM state WHERE key = ?", (shared_key,))
        count = cursor.fetchone()[0]
        assert count == 1, f"Expected 1 row for shared key, got {count}"
        
        # Status should be from one of the workers
        cursor.execute("SELECT status FROM state WHERE key = ?", (shared_key,))
        result = cursor.fetchone()
        assert result is not None
        assert result[0].startswith("update_")
        
        conn.close()


class TestDatabaseIntegrity:
    """Tests for overall database integrity after concurrent operations."""
    
    def test_database_not_corrupted_after_concurrent_writes(self, temp_db):
        """Database remains valid after heavy concurrent access."""
        init_schema(temp_db)
        
        num_workers = 10
        keys_per_worker = 50
        
        # Heavy concurrent write load
        processes = []
        for worker_id in range(num_workers):
            p = multiprocessing.Process(
                target=worker_insert_keys,
                args=(temp_db, worker_id, keys_per_worker)
            )
            processes.append(p)
            p.start()
        
        for p in processes:
            p.join(timeout=20)
            assert p.exitcode == 0
        
        # Run PRAGMA integrity_check
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        assert result[0] == "ok", f"Database integrity check failed: {result[0]}"
        
        # Verify expected data count
        cursor.execute("SELECT COUNT(*) FROM state")
        count = cursor.fetchone()[0]
        expected = num_workers * keys_per_worker
        assert count == expected
        
        conn.close()
    
    def test_no_data_loss_after_concurrent_operations(self, temp_db):
        """All writes complete successfully or fail gracefully."""
        init_schema(temp_db)
        
        num_workers = 8
        keys_per_worker = 30
        
        processes = []
        for worker_id in range(num_workers):
            p = multiprocessing.Process(
                target=worker_insert_keys,
                args=(temp_db, worker_id, keys_per_worker)
            )
            processes.append(p)
            p.start()
        
        # Wait for completion
        for p in processes:
            p.join(timeout=15)
            # All processes should complete successfully (exit code 0)
            assert p.exitcode == 0, "Worker process failed"
        
        # Verify all data present
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        for worker_id in range(num_workers):
            for key_id in range(keys_per_worker):
                key = f"worker_{worker_id}_key_{key_id}"
                cursor.execute("SELECT status FROM state WHERE key = ?", (key,))
                result = cursor.fetchone()
                assert result is not None, f"Key {key} is missing"
                # Status should be "working"
                assert result[0] == "working", f"Status mismatch for {key}"
        
        conn.close()


class TestSubprocessConcurrency:
    """Tests using subprocess instead of multiprocessing for realistic simulation."""
    
    def test_subprocess_writes_dont_conflict(self, temp_db):
        """Real subprocess writes simulate hook script concurrent access."""
        init_schema(temp_db)
        
        # Create a simple Python script that writes to database
        script = f"""
import sqlite3
import sys

db_path = sys.argv[1]
worker_id = sys.argv[2]
num_keys = int(sys.argv[3])

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

for i in range(num_keys):
    key = f"subprocess_{{worker_id}}_{{i}}"
    repo = f"/repo/path{{worker_id}}"
    status = "working"
    cursor.execute("INSERT OR REPLACE INTO state (key, repo, status, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", (key, repo, status))
    conn.commit()

conn.close()
"""
        
        # Write script to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            script_path = f.name
            f.write(script)
        
        try:
            # Launch multiple subprocesses
            num_workers = 4
            keys_per_worker = 25
            processes = []
            
            for worker_id in range(num_workers):
                p = subprocess.Popen([
                    sys.executable,
                    script_path,
                    temp_db,
                    str(worker_id),
                    str(keys_per_worker)
                ])
                processes.append(p)
            
            # Wait for all to complete
            for p in processes:
                p.wait(timeout=15)
                assert p.returncode == 0
            
            # Verify all data present
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM state")
            count = cursor.fetchone()[0]
            expected = num_workers * keys_per_worker
            assert count == expected
            
            conn.close()
            
        finally:
            Path(script_path).unlink(missing_ok=True)
