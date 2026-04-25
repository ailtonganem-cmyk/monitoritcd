"""Storage: persistência via Firebase + audit log + abstração para testes."""

from __future__ import annotations

from monitoritcd.storage.audit_log import AuditLog, OwnershipError
from monitoritcd.storage.base import StorageProtocol
from monitoritcd.storage.in_memory import InMemoryStorage

__all__ = ["AuditLog", "InMemoryStorage", "OwnershipError", "StorageProtocol"]
