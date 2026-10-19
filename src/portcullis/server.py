"""Flask server exposing whitelisted CLI commands over authenticated HTTP."""

import argparse
import json
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

from flask import Flask, Response, jsonify, request, stream_with_context

from . import config as config_mod
from .commands import REGISTRY
from .params import ParamError

NDJSON_MIME = "application/x-ndjson"


def ndjson_line(event):
    """Serialize one event dict as a single NDJSON line."""
    return json.dumps(event) + "\n"


def ndjson_error(status, code, message, **extra):
    """Return an HTTP error response whose body is one NDJSON error line."""
    event = {"type": "error", "code": code, "message": message}
    event.update(extra)
    return Response(ndjson_line(event), status=status, mimetype=NDJSON_MIME)


def stream_command(argv):
    """Run argv in the server cwd, streaming merged output as NDJSON."""

    def generate():
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout:
            yield ndjson_line({"type": "output", "data": line})
        proc.wait()
        yield ndjson_line({"type": "done", "exit_code": proc.returncode})

    return Response(stream_with_context(generate()), mimetype=NDJSON_MIME)


def create_app(cfg, token, client_root):
    """Build the Flask app with routes for enabled command groups.

    Endpoints are deny-by-default: only groups explicitly set to true in
    the [endpoints] table are served; everything else 404s.
    """
    endpoints_cfg = cfg.get("endpoints", {})
    groups = {}
    for name, factory in REGISTRY.items():
        if name not in endpoints_cfg:
            print(
                f"portcullis: warning: endpoint group {name!r} is not mentioned"
                f" in the config and is therefore disabled",
                file=sys.stderr,
            )
        if endpoints_cfg.get(name) is not True:
            continue
        groups[name] = factory(client_root)

    app = Flask(__name__)
    app.config["PORTCULLIS_GROUPS"] = list(groups.values())

    @app.before_request
    def check_token():
        """Reject every request without the correct bearer token."""
        if request.headers.get("Authorization") != f"Bearer {token}":
            return ndjson_error(401, "unauthorized", "missing or invalid token")
        return None

    @app.get("/")
    def list_groups():
        """List enabled endpoint groups."""
        return jsonify(
            groups=[
                {"path": f"/{g.name}", "description": g.description}
                for g in groups.values()
            ]
        )

    @app.get("/<group_name>")
    def group_docs(group_name):
        """List child endpoints of an enabled group."""
        group = groups.get(group_name)
        if group is None:
            return ndjson_error(
                404, "not_found", f"unknown or disabled endpoint: /{group_name}"
            )
        return jsonify(group.describe())

    @app.get("/<group_name>/<command_name>")
    def command_docs(group_name, command_name):
        """Return docs for one command: description, method, params."""
        group = groups.get(group_name)
        command = group.commands.get(command_name) if group else None
        if command is None:
            return ndjson_error(
                404,
                "not_found",
                f"unknown or disabled endpoint: /{group_name}/{command_name}",
            )
        doc = command.describe()
        doc["path"] = f"/{group_name}/{command_name}"
        return jsonify(doc)

    @app.post("/<group_name>/<command_name>")
    def run_command(group_name, command_name):
        """Validate params strictly, then stream command output as NDJSON."""
        group = groups.get(group_name)
        command = group.commands.get(command_name) if group else None
        if command is None:
            return ndjson_error(
                404,
                "not_found",
                f"unknown or disabled endpoint: /{group_name}/{command_name}",
            )
        payload = request.get_json(silent=True)
        try:
            cleaned = command.validate(payload)
        except ParamError as exc:
            return ndjson_error(400, "invalid_param", str(exc))
        argv = command.build_argv(cleaned)
        if shutil.which(argv[0]) is None:
            return ndjson_error(
                400, "binary_not_found", f"{argv[0]!r} binary not found on server PATH"
            )
        return stream_command(argv)

    return app


def write_session_file(path, port, token):
    """Write the client session file (token + port) with 0600 permissions."""
    path = Path(path)
    path.write_text(f'port = {port}\ntoken = "{token}"\n')
    path.chmod(0o600)


def main(argv=None):
    """Entry point for the portcullis-server command."""
    parser = argparse.ArgumentParser(
        prog="portcullis-server",
        description="Serve whitelisted CLI commands over authenticated HTTP.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="path to the main config TOML"
        f" (default: {config_mod.DEFAULT_USER_CONFIG})",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="interface to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=8931, help="port to listen on (default: 8931)"
    )
    parser.add_argument(
        "--session-file",
        type=Path,
        default=Path.cwd() / ".portcullis-client.toml",
        help="where to write the client session file (token + port)",
    )
    args = parser.parse_args(argv)

    cfg = config_mod.load_config(user_path=args.config)
    token = secrets.token_urlsafe(32)
    write_session_file(args.session_file, args.port, token)
    client_root = config_mod.compute_client_root(cfg)

    app = create_app(cfg, token, client_root)
    enabled = [g.name for g in app.config["PORTCULLIS_GROUPS"]]
    print(f"portcullis: listening on http://{args.host}:{args.port}")
    print(f"portcullis: session file written to {args.session_file}")
    print(f"portcullis: client root: {client_root}")
    print(f"portcullis: enabled groups: {', '.join(enabled) or '(none)'}")
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
