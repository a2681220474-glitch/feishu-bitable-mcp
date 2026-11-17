"""Durable request receipts and resource leases, without token or content storage."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .config import BitableError


class ChangeStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        os.close(fd)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS receipts (
                    owner TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    resource TEXT NOT NULL, state TEXT NOT NULL, receipt TEXT,
                    updated REAL NOT NULL, PRIMARY KEY(owner, request_id));
                CREATE TABLE IF NOT EXISTS leases (
                    resource TEXT PRIMARY KEY, owner TEXT NOT NULL, request_id TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=2)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, owner: str, request_id: str):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM receipts WHERE owner=? AND request_id=?", (owner, request_id)
            ).fetchone()
        if not row:
            return None
        return dict(row) | {"receipt": json.loads(row["receipt"]) if row["receipt"] else None}

    def reserve(self, owner: str, request_id: str, fingerprint: str, resource: str):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT fingerprint FROM receipts WHERE owner=? AND request_id=?",
                (owner, request_id),
            ).fetchone()
            if row:
                if row["fingerprint"] != fingerprint:
                    raise BitableError("request_id is already bound to different content.")
                return False
            if db.execute("SELECT 1 FROM leases WHERE resource=?", (resource,)).fetchone():
                raise BitableError("Another operation or uncertain outcome holds this resource.")
            db.execute("INSERT INTO leases VALUES (?,?,?)", (resource, owner, request_id))
            db.execute(
                "INSERT INTO receipts VALUES (?,?,?,?,?,?,?)",
                (
                    owner,
                    request_id,
                    fingerprint,
                    resource,
                    "started",
                    None,
                    time.time(),
                ),
            )
            return True

    def finish(self, owner: str, request_id: str, state: str, receipt: dict):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE receipts SET state=?,receipt=?,updated=? WHERE owner=? AND request_id=?",
                (state, json.dumps(receipt), time.time(), owner, request_id),
            )
            # Uncertain outcomes retain the lease. Never silently expire and duplicate a create.
            if state != "unknown":
                db.execute("DELETE FROM leases WHERE owner=? AND request_id=?", (owner, request_id))

    def pending(self):
        """Operator-only, credential-free incident inventory; not an MCP tool."""
        with self.connect() as db:
            rows = db.execute(
                "SELECT owner,request_id,resource,state,updated FROM receipts "
                "WHERE state IN ('started','unknown') ORDER BY updated"
            ).fetchall()
            return [dict(row) for row in rows]

    def reconcile(self, owner: str, request_id: str, outcome: str, evidence_hash: str):
        """Offline operator reconciliation; never turns a receipt back into a retryable request."""
        if outcome not in {"verified_applied", "verified_not_applied"}:
            raise BitableError("Reconciliation requires a verified remote outcome.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT state FROM receipts WHERE owner=? AND request_id=?", (owner, request_id)
            ).fetchone()
            if not row or row["state"] not in {"started", "unknown"}:
                raise BitableError("Only uncertain receipts can be reconciled.")
            receipt = {"operator_verified_outcome": outcome, "evidence_sha256": evidence_hash}
            db.execute(
                "UPDATE receipts SET state=?,receipt=?,updated=? WHERE owner=? AND request_id=?",
                (outcome, json.dumps(receipt), time.time(), owner, request_id),
            )
            db.execute("DELETE FROM leases WHERE owner=? AND request_id=?", (owner, request_id))


def main():
    """Local-only incident tool. The operator must stop all workers and inspect Feishu first."""
    import argparse
    import re

    parser = argparse.ArgumentParser(
        description="Inspect/reconcile a private change ledger offline."
    )
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--owner")
    parser.add_argument("--request-id")
    parser.add_argument("--outcome", choices=["verified_applied", "verified_not_applied"])
    parser.add_argument("--evidence-sha256")
    parser.add_argument("--confirm-all-workers-stopped", action="store_true")
    args = parser.parse_args()
    if not Path(args.ledger).is_file():
        parser.error("Ledger must already exist.")
    store = ChangeStore(args.ledger)
    if args.outcome:
        if not (
            args.confirm_all_workers_stopped
            and args.owner
            and args.request_id
            and re.fullmatch(r"[a-f0-9]{64}", args.evidence_sha256 or "")
        ):
            parser.error(
                "Stop all workers, inspect Feishu, and supply owner/request/evidence SHA256."
            )
        try:
            store.reconcile(args.owner, args.request_id, args.outcome, args.evidence_sha256)
        except BitableError as exc:
            parser.exit(2, str(exc) + "\n")
        print(json.dumps({"request_id": args.request_id, "status": args.outcome}))
    else:
        print(json.dumps(store.pending()))


if __name__ == "__main__":
    main()
