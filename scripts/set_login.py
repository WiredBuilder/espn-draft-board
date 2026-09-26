"""Save ESPN login cookies into .env without showing them on screen.
Run on your Mac:  python3 scripts/set_login.py
"""
import getpass
from pathlib import Path

env = Path(__file__).resolve().parent.parent / ".env"
lines = env.read_text().splitlines() if env.exists() else []
vals = {
    "ESPN_S2": getpass.getpass("Paste espn_s2 value (hidden), then Enter: ").strip(),
    "ESPN_SWID": getpass.getpass("Paste SWID value (hidden, include the { }), then Enter: ").strip(),
}
for k, v in vals.items():
    if not v:
        raise SystemExit(f"{k} was empty, nothing saved.")
    lines = [l for l in lines if not l.startswith(k + "=")] + [f"{k}={v}"]
env.touch(mode=0o600, exist_ok=True)
env.chmod(0o600)
env.write_text("\n".join(lines) + "\n")
print(f"Saved. espn_s2 length {len(vals['ESPN_S2'])}, SWID looks {'OK' if vals['ESPN_SWID'].startswith('{') and vals['ESPN_SWID'].endswith('}') else 'WRONG (should be wrapped in { })'}.")
