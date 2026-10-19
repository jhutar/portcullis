# portcullis

Allows running user-selected commands in user session where the server runs
(with all its permissions and secrets) by a client (e.g. AI agent running in
container isolation) via HTTP.

- **Deny-by-default endpoints** configured in TOML
- **Bearer token auth** session file generated fresh at every server start
- **Strict param typing** with helper types (e.g. `local_readable_file`
  validates the path stays inside the server's project directory, with
  client-root path translation)
- **NDJSON streaming** for long-running commands: `output` events while
  running, final `done` event carries the exit code

## Install

Directly from upstream:

    uv tool install git+ssh://git@github.com/jhutar/portcullis.git

Or editable installation from your local clone:

    uv tool install -e .

Two commands are installed: `portcullis-server` (server intended to be started
in user session) and `portcullis` (client, intended to be used from inside the
container).

## Server config

`~/.config/portcullis/config.toml`, overridden key-by-key by local
`./.portcullis.toml`:

    [endpoints]
    podman = true

    [client]
    root_base = "/home/jhutar"   # client root = root_base + basename(server cwd)

Run:

    portcullis-server

Writes `./.portcullis-client.toml` (token + port, mode 0600). Mount that
file into the container as `$HOME/.portcullis-client.toml`.

## Client

Loads config from `$HOME/.portcullis-client.toml` to learn server token and
port. Then you can use the CLI:

    portcullis -h                       # list enabled groups
    portcullis podman -h                # list commands in a group
    portcullis podman build -h          # command docs (params, types)
    portcullis podman build --file Containerfile

Client exit code equals the command's exit code. Flags are converted to
typed JSON using the types from the server's GET docs (strict, no coercion).
