#!/usr/bin/env python3
"""E3 Permission Compiler — per-role permission scoping."""

from typing import Any, Dict, List, Optional
from enum import Enum


class PermissionLevel(Enum):
    NONE = 0
    READ_ONLY = 1
    CONTROLLED_WRITE = 2
    FULL = 3


ROLE_PERMISSIONS: Dict[str, Dict[str, PermissionLevel]] = {
    "researcher": {
        "worktree_access": PermissionLevel.NONE,
        "file_read": PermissionLevel.READ_ONLY,
        "file_write": PermissionLevel.NONE,
        "terminal": PermissionLevel.NONE,
        "network": PermissionLevel.READ_ONLY,
        "test_execution": PermissionLevel.NONE,
    },
    "architect": {
        "worktree_access": PermissionLevel.NONE,
        "file_read": PermissionLevel.READ_ONLY,
        "file_write": PermissionLevel.NONE,
        "terminal": PermissionLevel.NONE,
        "network": PermissionLevel.READ_ONLY,
        "test_execution": PermissionLevel.NONE,
    },
    "builder": {
        "worktree_access": PermissionLevel.CONTROLLED_WRITE,
        "file_read": PermissionLevel.READ_ONLY,
        "file_write": PermissionLevel.CONTROLLED_WRITE,
        "terminal": PermissionLevel.CONTROLLED_WRITE,
        "network": PermissionLevel.READ_ONLY,
        "test_execution": PermissionLevel.CONTROLLED_WRITE,
    },
    "debugger": {
        "worktree_access": PermissionLevel.CONTROLLED_WRITE,
        "file_read": PermissionLevel.READ_ONLY,
        "file_write": PermissionLevel.CONTROLLED_WRITE,
        "terminal": PermissionLevel.CONTROLLED_WRITE,
        "network": PermissionLevel.NONE,
        "test_execution": PermissionLevel.CONTROLLED_WRITE,
    },
    "critic": {
        "worktree_access": PermissionLevel.NONE,
        "file_read": PermissionLevel.READ_ONLY,
        "file_write": PermissionLevel.NONE,
        "terminal": PermissionLevel.NONE,
        "network": PermissionLevel.NONE,
        "test_execution": PermissionLevel.NONE,
    },
    "verifier": {
        "worktree_access": PermissionLevel.NONE,
        "file_read": PermissionLevel.READ_ONLY,
        "file_write": PermissionLevel.NONE,
        "terminal": PermissionLevel.CONTROLLED_WRITE,
        "network": PermissionLevel.NONE,
        "test_execution": PermissionLevel.CONTROLLED_WRITE,
    },
    "integrator": {
        "worktree_access": PermissionLevel.CONTROLLED_WRITE,
        "file_read": PermissionLevel.READ_ONLY,
        "file_write": PermissionLevel.CONTROLLED_WRITE,
        "terminal": PermissionLevel.CONTROLLED_WRITE,
        "network": PermissionLevel.READ_ONLY,
        "test_execution": PermissionLevel.READ_ONLY,
    },
    "writer": {
        "worktree_access": PermissionLevel.NONE,
        "file_read": PermissionLevel.READ_ONLY,
        "file_write": PermissionLevel.CONTROLLED_WRITE,
        "terminal": PermissionLevel.NONE,
        "network": PermissionLevel.READ_ONLY,
        "test_execution": PermissionLevel.NONE,
    },
}


class PermissionCompiler:
    """Compile permissions for a worker based on its role."""

    def __init__(self, role_permissions: Optional[Dict[str, Dict[str, PermissionLevel]]] = None):
        self.role_permissions = role_permissions if role_permissions is not None else ROLE_PERMISSIONS

    def compile_permissions(self, roles: List[str],
                            allowed_tools: Optional[List[str]] = None,
                            custom_overrides: Optional[Dict[str, PermissionLevel]] = None) -> Dict[str, Any]:
        """Build permission set for a worker with given roles."""
        permissions: Dict[str, Any] = {
            "roles": roles,
            "file_read": PermissionLevel.NONE,
            "file_write": PermissionLevel.NONE,
            "terminal": PermissionLevel.NONE,
            "network": PermissionLevel.NONE,
            "test_execution": PermissionLevel.NONE,
            "worktree_access": PermissionLevel.NONE,
            "allowed_tools": allowed_tools if allowed_tools is not None else [],
        }

        for role in roles:
            role_perms = self.role_permissions.get(role, {})
            for key, level in role_perms.items():
                if key in permissions and isinstance(permissions[key], PermissionLevel):
                    if level.value > permissions[key].value:
                        permissions[key] = level

        if custom_overrides is not None:
            for key, level in custom_overrides.items():
                if key in permissions:
                    permissions[key] = level

        return permissions

    def validate_permission_request(self, requested: Dict[str, Any],
                                    allowed: Dict[str, Any]) -> List[str]:
        """Check if requested permissions exceed allowed scope."""
        violations: List[str] = []
        for key in ["file_read", "file_write", "terminal", "network", "test_execution", "worktree_access"]:
            req_level = requested.get(key, PermissionLevel.NONE)
            allowed_level = allowed.get(key, PermissionLevel.NONE)
            if isinstance(req_level, PermissionLevel) and isinstance(allowed_level, PermissionLevel):
                if req_level.value > allowed_level.value:
                    violations.append(f"Permission {key}: requested {req_level.value} exceeds allowed {allowed_level.value}")
        return violations
