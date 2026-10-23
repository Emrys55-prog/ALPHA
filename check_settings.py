"""
Check an alpha's actual settings (neutralization, truncation, decay, etc)
as BRAIN recorded them — useful when we need to replicate a specific
result exactly and don't have it saved locally.

Usage:
    python check_settings.py <alpha_id>
"""

import sys
from auth import WQSession

BRAIN_API_BASE = "https://api.worldquantbrain.com"

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python check_settings.py <alpha_id>")
        sys.exit(1)

    alpha_id = sys.argv[1]

    session = WQSession()
    session.login()

    resp = session.session.get(f"{BRAIN_API_BASE}/alphas/{alpha_id}")
    data = resp.json()

    settings = data.get("settings", {})
    print(f"Settings for {alpha_id}:")
    for k, v in settings.items():
        print(f"  {k}: {v}")