"""API key lookup, matching congressional-tech's congress_shared.auth order:
--api-key flag, DATA_GOV_API_KEY, ~/.data.gov.api.key, ~/.data.gov.key, else DEMO_KEY."""
import os
from pathlib import Path

PLACEHOLDER = "PASTE_KEY_HERE"


def load_key(flag_value=None):
    if flag_value:
        return flag_value
    env = os.environ.get("DATA_GOV_API_KEY")
    if env:
        return env.strip()
    for name in (".data.gov.api.key", ".data.gov.key"):
        p = Path.home() / name
        if p.is_file():
            key = p.read_text().strip()
            if key and key != PLACEHOLDER:
                return key
    return "DEMO_KEY"
