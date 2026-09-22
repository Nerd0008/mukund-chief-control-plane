#!/usr/bin/env python3
"""E3 Capability Registry — worker capability state management."""

import sqlite3
from datetime import datetime

CAPABILITY_ROLES = [
    'planner', 'researcher', 'scout', 'architect', 'builder',
    'debugger', 'critic', 'verifier', 'integrator', 'writer',
    'classifier', 'vision', 'data-analyst', 'context-compressor', 'router'
]

WORKER_STATES = ['UNPROVEN', 'EVALUATING', 'QUALIFIED', 'SUSPENDED']


class CapabilityRegistry:
    """Manages worker capability qualification state."""

    def __init__(self, con):
        self.con = con

    def register_worker(self, worker_id, provider, model,
                        roles=None, state='UNPROVEN'):
        """Register a worker in the capability registry."""
        ts = datetime.utcnow().isoformat()
        if roles is None:
            roles = []
        for role in roles:
            self.con.execute(
                """INSERT OR REPLACE INTO capability_registry
                   (worker_id, task_family, capability_role, state,
                    last_qualified_at)
                   VALUES (?, 'general', ?, ?, ?)""",
                (worker_id, role, state, ts if state == 'QUALIFIED' else None)
            )
        self.con.commit()

    def update_capability_state(self, worker_id, task_family, capability_role,
                                new_state, failure_severity=None):
        """Update capability state (UNPROVEN/EVALUATING/QUALIFIED/SUSPENDED)."""
        ts = datetime.utcnow().isoformat()
        if new_state == 'QUALIFIED':
            self.con.execute(
                """UPDATE capability_registry SET state=?,
                   last_qualified_at=?, evidence_count=evidence_count+1
                   WHERE worker_id=? AND task_family=? AND capability_role=?""",
                (new_state, ts, worker_id, task_family, capability_role)
            )
        elif new_state == 'SUSPENDED':
            self.con.execute(
                """UPDATE capability_registry SET state=?,
                   last_failure_at=?, failure_severity=?
                   WHERE worker_id=? AND task_family=? AND capability_role=?""",
                (new_state, ts, failure_severity, worker_id, task_family, capability_role)
            )
        else:
            self.con.execute(
                """UPDATE capability_registry SET state=?
                   WHERE worker_id=? AND task_family=? AND capability_role=?""",
                (new_state, worker_id, task_family, capability_role)
            )
        self.con.commit()

    def get_capability(self, worker_id, task_family, capability_role):
        """Get capability state for a worker."""
        row = self.con.execute(
            """SELECT state, evidence_count,
                      last_qualified_at, last_failure_at, failure_severity
               FROM capability_registry
               WHERE worker_id=? AND task_family=? AND capability_role=?""",
            (worker_id, task_family, capability_role)
        ).fetchone()
        if row:
            return {
                'worker_id': worker_id,
                'task_family': task_family,
                'capability_role': capability_role,
                'state': row[0],
                'evidence_count': row[1],
                'last_qualified_at': row[2],
                'last_failure_at': row[3],
                'failure_severity': row[4]
            }
        return {
            'worker_id': worker_id,
            'task_family': task_family,
            'capability_role': capability_role,
            'state': 'UNPROVEN',
            'evidence_count': 0,
            'first_pass_success_rate': None,
            'last_qualified_at': None,
            'last_failure_at': None,
            'failure_severity': None
        }

    def find_qualified_workers(self, task_family, capability_role):
        """Find all qualified workers for a given task family and role."""
        rows = self.con.execute(
            """SELECT worker_id FROM capability_registry
               WHERE task_family=? AND capability_role=? AND state='QUALIFIED'""",
            (task_family, capability_role)
        ).fetchall()
        return [r[0] for r in rows]

    def find_eligible_workers(self, task_family, capability_role, risk_class='R0'):
        """Find eligible workers (qualified or evaluating for low-risk tasks)."""
        if risk_class in ('R0', 'R1'):
            states = ('QUALIFIED', 'EVALUATING')
        else:
            states = ('QUALIFIED',)
        placeholders = ','.join('?' * len(states))
        query = f"""SELECT worker_id, state FROM capability_registry
                    WHERE task_family=? AND capability_role=?
                    AND state IN ({placeholders})"""
        params = (task_family, capability_role) + states
        rows = self.con.execute(query, params).fetchall()
        return [{'worker_id': r[0], 'state': r[1]} for r in rows]
