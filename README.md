# portcullis

Guarded HTTP bridge: run commands on the host (with its permissions and
secrets) and let a container-side agent call only the whitelisted ones.

- **Deny-by-default endpoints** configured in TOML
- **Bearer token auth**, session file generated fresh at every server start
- **Strict param typing** with helper types (e.g. `local_readable_file`
  validates the path stays inside the server's project directory, with
  client-root path translation)
- **NDJSON streaming** for long-running commands: `output` events while
  running, final `done` event carries the exit code

## Install

    uv tool install .

Two commands are installed: `portcullis-server` (host) and `portcullis`
(client, also usable inside the container).

## Server config

`~/.config/portcullis/config.toml`, overridden key-by-key by
`./.portcullis.toml`:

    [endpoints]
    podman = true

    [client]
    root_base = "/home/jhutar"   # client root = root_base + basename(server cwd)

Run:

    portcullis-server

Writes `./.portcullis-client.toml` (token + port, mode 0600). Mount that
file into the container.

## Client

    portcullis -h                       # list enabled groups
    portcullis podman -h                # list commands in a group
    portcullis podman build -h          # command docs (params, types)
    portcullis podman build --file Containerfile

Client exit code equals the command's exit code. Flags are converted to
typed JSON using the types from the server's GET docs (strict, no coercion).
