"""Start an ASTRA server.

    python run.py                          # standalone prototype (all roles), http://127.0.0.1:8000
    python run.py --side onboard           # Crew Side: onboard spacecraft server, http://127.0.0.1:8000
    python run.py --side earth             # Earth Side: ground operations server,  http://127.0.0.1:8100
    python run.py --side onboard --host 0.0.0.0   # reachable from other devices on the spacecraft network

`--side` selects defaults for ONE machine running both servers (demonstration): separate ports, separate data
directories/databases (backend/data/onboard, backend/data/earth) and a shared generated demo sync key
(backend/data/demo-sync.key). Every default can be overridden with the ASTRA_* environment variables (see
docs/CREW_EARTH_SYNC.md). The first start creates the database and seeds the SYNTHETIC demo mission and crew.
"""
import argparse
import os
import secrets
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

SIDE_DEFAULTS = {
    "onboard": {"port": 8000, "data": BACKEND / "data" / "onboard", "node": "ONBOARD-ARES-T1"},
    "earth": {"port": 8100, "data": BACKEND / "data" / "earth", "node": "EARTH-MCC-1"},
}


def _configure_side(side: str, port: int | None, earth_url: str | None) -> int:
    d = SIDE_DEFAULTS[side]
    os.environ["ASTRA_DEPLOYMENT"] = side
    os.environ.setdefault("ASTRA_DATA_DIR", str(d["data"]))
    os.environ.setdefault("ASTRA_NODE_ID", d["node"])
    if not os.environ.get("ASTRA_SYNC_KEY") and not os.environ.get("ASTRA_SYNC_KEY_FILE"):
        key_file = BACKEND / "data" / "demo-sync.key"  # shared by both local demo servers; never sent anywhere
        key_file.parent.mkdir(parents=True, exist_ok=True)
        if not key_file.exists():
            key_file.write_text(secrets.token_urlsafe(48))
        os.environ["ASTRA_SYNC_KEY_FILE"] = str(key_file)
    if side == "onboard":
        os.environ.setdefault("ASTRA_EARTH_URL", earth_url or f"http://127.0.0.1:{SIDE_DEFAULTS['earth']['port']}")
    else:
        os.environ.setdefault("ASTRA_SYNC_PEER_ID", SIDE_DEFAULTS["onboard"]["node"])
        from astra.seed import MISSION_ID
        os.environ.setdefault("ASTRA_SYNC_PEER_MISSION", MISSION_ID)
    return port or d["port"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--side", choices=["standalone", "onboard", "earth"], default=None,
                    help="deployment side (default: ASTRA_DEPLOYMENT or standalone)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--earth-url", default=None, help="onboard: base URL of the Earth server")
    ap.add_argument("--allow-link-simulation", action="store_true",
                    help="DEMONSTRATION: enable the CMO 'Simulate Earth Connection Loss' control (onboard)")
    ap.add_argument("--ssl-certfile", default=None, help="serve HTTPS with this certificate (PEM)")
    ap.add_argument("--ssl-keyfile", default=None, help="private key for --ssl-certfile")
    ap.add_argument("--reset-db", action="store_true", help="delete this server's database and re-seed the demo data")
    args = ap.parse_args()
    side = args.side or os.environ.get("ASTRA_DEPLOYMENT") or "standalone"
    port = args.port or 8000
    if side in SIDE_DEFAULTS:
        port = _configure_side(side, args.port, args.earth_url)
    else:
        os.environ["ASTRA_DEPLOYMENT"] = "standalone"
    if args.allow_link_simulation:
        os.environ["ASTRA_ALLOW_LINK_SIMULATION"] = "1"
    from astra import config
    if args.reset_db:
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(config.db_path()) + suffix)
            if p.exists():
                p.unlink()
        print(f"[astra] database reset ({config.db_path()})")
    import uvicorn
    scheme = "https" if args.ssl_certfile else "http"
    print(f"[astra] {side}: open {scheme}://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{port}  "
          f"(API docs: /api/docs) · database {config.db_path()}")
    uvicorn.run("astra.app:app", host=args.host, port=port, log_level="info", ws="auto",
                proxy_headers=True, forwarded_allow_ips="127.0.0.1", server_header=False,
                ssl_certfile=args.ssl_certfile, ssl_keyfile=args.ssl_keyfile)


if __name__ == "__main__":
    main()
