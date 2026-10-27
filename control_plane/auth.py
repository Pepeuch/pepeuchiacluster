"""Two local identities with separate credentials, no cookies or default password."""

import hmac
import re

from .contracts import Principal, Problem
from .storage import read_private


ADMIN = Principal("local-admin", "admin")
WORKER = Principal("fake-cpu", "worker")


class Authenticator:
    def __init__(self, root):
        self.credentials = []
        for role, principal in (("admin", ADMIN), ("worker", WORKER)):
            token = read_private(root / "secrets" / (role + ".token"), 256).strip()
            if re.fullmatch(rb"[A-Za-z0-9_-]{43}", token) is None:
                raise Problem("invalid_local_credential", 500)
            self.credentials.append((token, principal))

    def authenticate(self, authorization):
        if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
            raise Problem("authentication_required", 401)
        try:
            token = authorization[7:].encode("ascii")
        except UnicodeError:
            raise Problem("authentication_required", 401) from None
        found = None
        for expected, principal in self.credentials:
            if hmac.compare_digest(token, expected):
                found = principal
        if found is None:
            raise Problem("authentication_required", 401)
        return found


def require_role(principal, role):
    if not isinstance(principal, Principal) or principal.role != role:
        raise Problem("access_denied", 403)


def workspace_access(con, principal, workspace_id):
    require_role(principal, "admin")
    row = con.execute("SELECT * FROM workspaces WHERE id=? AND owner=?", (workspace_id, principal.identity)).fetchone()
    if row is None:
        raise Problem("not_found", 404)
    return row
