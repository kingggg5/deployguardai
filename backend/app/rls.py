"""PostgreSQL row-level-security request context.

The database policies introduced by migration 0009 read a transaction-local
custom setting.  Keeping the value transaction-local prevents a pooled
connection from leaking one workspace into the next request.  SQLite remains
the supported local/test database and deliberately treats this module as a
no-op at the SQL layer.

Production must connect the API with a non-owner, non-superuser role that does
not have BYPASSRLS.  Schema migrations should continue to use a separate owner
role.  This module never changes roles and never accepts a role name from
configuration.
"""

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session
from sqlalchemy.orm.session import SessionTransaction


TENANT_SETTING = "deployguard.workspace_id"
TENANT_SESSION_INFO_KEY = "deployguard_workspace_id"

# These are user-facing, workspace-owned data-plane tables.  Authentication,
# invitation claims, provider callback/delivery mapping, user-wide notification
# feeds, and cross-tenant worker queues are deliberately control-plane concerns
# and are not included.
DIRECT_TENANT_TABLES = (
    "repositories",
    "scenarios",
    "changes",
    "incidents",
    "audit_events",
    "services",
    "workspace_risk_policies",
    "operational_events",
    "deployments",
)
INDIRECT_TENANT_TABLES = ("incident_feedback",)


def _validate_workspace_id(workspace_id: str) -> str:
    value = workspace_id.strip()
    if not value or len(value) > 36:
        raise ValueError("workspace_id must contain between 1 and 36 characters")
    return value


def _set_postgresql_context(
    connection: Connection, workspace_id: str
) -> None:
    connection.execute(
        text(
            "SELECT set_config('deployguard.workspace_id', "
            ":workspace_id, true)"
        ),
        {"workspace_id": workspace_id},
    )


@event.listens_for(Session, "after_begin")
def _restore_tenant_context(
    session: Session,
    _transaction: SessionTransaction,
    connection: Connection,
) -> None:
    """Re-apply the context whenever a commit starts a new transaction."""

    workspace_id = session.info.get(TENANT_SESSION_INFO_KEY)
    if connection.dialect.name == "postgresql" and workspace_id:
        _set_postgresql_context(connection, str(workspace_id))


def set_tenant_context(session: Session, workspace_id: str) -> None:
    """Bind a workspace to this session and its current/future transactions.

    Authorization must happen before this function is called.  The setting is
    not authorization by itself; PostgreSQL policies use it as the scope that
    an already-authenticated request is allowed to access.
    """

    value = _validate_workspace_id(workspace_id)
    session.info[TENANT_SESSION_INFO_KEY] = value
    bind = session.get_bind()
    if bind.dialect.name == "postgresql" and session.in_transaction():
        _set_postgresql_context(session.connection(), value)
