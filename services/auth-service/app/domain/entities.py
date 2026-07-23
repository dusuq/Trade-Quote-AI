"""Domain entities & value objects (framework-free, pure Python)."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


class PlanTier(str, enum.Enum):
    STARTER = "starter"
    PROFESSIONAL = "professional"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class UserStatus(str, enum.Enum):
    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class RoleKey(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    ESTIMATOR = "estimator"
    TECHNICIAN = "technician"
    SALESPERSON = "salesperson"
    OFFICE = "office"
    ACCOUNTANT = "accountant"
    VIEWER = "viewer"


@dataclass(slots=True)
class Tenant:
    id: UUID
    name: str
    slug: str
    plan: PlanTier = PlanTier.STARTER
    country: str = "US"
    is_active: bool = True


@dataclass(slots=True)
class User:
    id: UUID
    tenant_id: UUID
    email: str
    full_name: str | None = None
    status: UserStatus = UserStatus.INVITED
    external_idp: str | None = None
    roles: list[RoleKey] = field(default_factory=list)
    last_login_at: datetime | None = None

    def has_role(self, role: RoleKey) -> bool:
        return role in self.roles

    @property
    def is_owner_or_admin(self) -> bool:
        return self.has_role(RoleKey.OWNER) or self.has_role(RoleKey.ADMIN)
