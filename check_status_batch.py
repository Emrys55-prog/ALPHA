"""
Batch Status Check — read-only, checks multiple pending alphas at once.

Usage:
    python check_status_batch.py <alpha_id_1> <alpha_id_2> ...
"""

import sys
from auth import WQSession

BRAIN_API_BASE = "https://api.worldquantbrain.com"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_status_batch.py <alpha_id_1> <alpha_id_2> ...")
        sys.exit(1)

    session = WQSession()
    session.login()

    for alpha_id in sys.argv[1:]:
        resp = session.session.get(f"{BRAIN_API_BASE}/alphas/{alpha_id}")
        data = resp.json()
        status = data.get("status")
        checks = data.get("is", {}).get("checks", [])
        self_corr = next((c.get("result") for c in checks if c.get("name") == "SELF_CORRELATION"), "?")
        print(f"{alpha_id}: status={status}  self_correlation={self_corr}")