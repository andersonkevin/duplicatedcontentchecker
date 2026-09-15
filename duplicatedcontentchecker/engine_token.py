"""A per-machine secret that lets saved HTML reports talk to the local engine.

Browsers will not let a page opened from disk run a crawler, but they will let
it call ``http://127.0.0.1:8765`` if the server allows it. Allowing that for
any page would let a random website drive your crawler, so every API call
must carry this token. The engine embeds it in the dashboards it serves and in
the HTML reports the tool writes on this machine, and nowhere else.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

ENV_VAR = "DUPCHECK_TOKEN_FILE"


def token_path() -> Path:
    override = os.environ.get(ENV_VAR)
    return Path(override) if override else Path.home() / ".dupcheck" / "token"


def get_or_create_token() -> str:
    path = token_path()
    try:
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_hex(24)
    path.write_text(value + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return value
