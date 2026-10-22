"""S01 CLI shell; no future import/CAD/training commands are advertised."""
import argparse
import json
import os
import socket
import sys
from urdftools.core import runtime_status


def main():
    parser = argparse.ArgumentParser(prog="urdftools")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--json", action="store_true")
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    if args.command == "doctor":
        print(json.dumps(runtime_status(), ensure_ascii=False))
        return 0
    token = os.environ.get("URDFTOOLS_SESSION_TOKEN", "")
    if len(token) < 32:
        print(json.dumps({"code": "missing_session_token", "remediation":
              "Set URDFTOOLS_SESSION_TOKEN to a random value of at least 32 characters"}), file=sys.stderr)
        return 2
    import uvicorn
    from urdftools.api import create_app
    try:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", args.port))
            listener.listen(128)
            print(json.dumps({"event": "listening", "host": "127.0.0.1", "port": listener.getsockname()[1]}), flush=True)
            uvicorn.Server(uvicorn.Config(create_app(token), log_level="warning")).run(sockets=[listener])
    except OSError as exc:
        print(json.dumps({"code": "local_service_unavailable", "message": str(exc),
              "remediation": "Allow local loopback sockets and select an available port; do not expose this service externally"}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
