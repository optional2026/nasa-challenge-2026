"""Start the ASTRA onboard server.

    python run.py                 # http://127.0.0.1:8000
    python run.py --host 0.0.0.0  # reachable from other devices on the habitat network

The first start creates backend/data/astra.sqlite3 and seeds the SYNTHETIC demo crew.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reset-db", action="store_true", help="delete the local database and re-seed the demo data")
    args = ap.parse_args()
    from astra import config
    if args.reset_db:
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(config.db_path()) + suffix)
            if p.exists():
                p.unlink()
        print("[astra] database reset")
    import uvicorn
    print(f"[astra] open http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}  (API docs: /api/docs)")
    uvicorn.run("astra.app:app", host=args.host, port=args.port, log_level="info", ws="auto")


if __name__ == "__main__":
    main()
