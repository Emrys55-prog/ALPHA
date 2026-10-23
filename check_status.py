"""
Check-only status poll — does NOT submit anything. Use this when a
previous submit.py run timed out waiting for ACTIVE status, so you
don't accidentally send a second submit request on top of a pending one.

Usage:
    python check_status.py <alpha_id>
"""

import sys
from auth import WQSession

BRAIN_API_BASE = "https://api.worldquantbrain.com"

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python check_status.py <alpha_id>")
        sys.exit(1)

    alpha_id = sys.argv[1]

    session = WQSession()
    session.login()

    resp = session.session.get(f"{BRAIN_API_BASE}/alphas/{alpha_id}")
    data = resp.json()

    print(f"Status: {data.get('status')}")
    checks = data.get("is", {}).get("checks", [])
    for c in checks:
        print(f"  [{c.get('result')}] {c.get('name')}  {c.get('value', '')}")