"""Controle de permissões e papéis de usuários (RBAC) e políticas operacionais."""

from enum import Enum
from typing import Set


class Role(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    ANALYST = "analyst"
    VIEWER = "viewer"


class Permission(str, Enum):
    MANAGE_PRODUCTS = "manage_products"
    MANAGE_CAMPAIGNS = "manage_campaigns"
    MANAGE_CONTENT = "manage_content"
    PUBLISH_CONTENT = "publish_content"
    VIEW_FINANCE = "view_finance"
    MANAGE_FINANCE = "manage_finance"
    MANAGE_SETTINGS = "manage_settings"
    RUN_AUTOMATION = "run_automation"


ROLE_PERMISSIONS: dict[Role, Set[Permission]] = {
    Role.ADMIN: set(Permission),
    Role.OPERATOR: {
        Permission.MANAGE_PRODUCTS,
        Permission.MANAGE_CAMPAIGNS,
        Permission.MANAGE_CONTENT,
        Permission.PUBLISH_CONTENT,
        Permission.VIEW_FINANCE,
        Permission.RUN_AUTOMATION,
    },
    Role.ANALYST: {
        Permission.VIEW_FINANCE,
    },
    Role.VIEWER: set(),
}


def has_permission(role_name: str, permission: Permission) -> bool:
    """Verifica se o papel possui a permissão solicitada."""
    try:
        role = Role(role_name)
    except ValueError:
        return False
    return permission in ROLE_PERMISSIONS.get(role, set())

