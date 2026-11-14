# Design

These documents are the authoritative reference for what the `parkingradio` command-line tool does. This one has the
conventions every command follows, and the index of the commands, each of which has a document of its own. The code
implements these documents, and has to match them: when they disagree, including with comments in the code, the
documents win.

The tool acts on Parking Radio's site, whose own design, in
[parkingradio/website](https://github.com/parkingradio/website/blob/main/docs/design/README.md), says what the site
does. These documents link to it rather than saying it again.

## Conventions

- **Commands.** `parkingradio` is one command, whose subcommands do the work: `parkingradio <command>`.
- **Help.** `--help`, on `parkingradio` and on every command, shows how to use it, on stdout, and exits with 0.
- **Version.** `parkingradio --version` shows the tool's version, on stdout, and exits with 0. Commands don't take
  `--version`.
- **Usage errors.** `parkingradio` without a command shows its help, on stderr, and exits with 2. A command line the
  tool can't take (e.g. an unknown command or option) is a usage error too: it shows how to use the tool and what's
  wrong, on stderr, and exits with 2.
- **Output.** A command's output goes to stdout. Errors go to stderr, and a command that fails exits with 1, unless
  it's a usage error. Warnings go to stderr too, and so does what a command asks the user to do while it waits, e.g. a
  link to open.
- **Language.** The tool's messages are in English.
- **Site.** Commands act on one site, e.g. production, the test environment or a development server: the one
  `--site <address>` gives, before the command (`parkingradio --site <address> <command>`), or else the
  `PARKINGRADIO_SITE` environment variable. There's no default: without either, a command that acts on a site is a
  usage error, which names both, while `--help` and `--version` don't need a site. The address is the site's origin:
  `https://` and a host, or `http://localhost`, for a development server, either one maybe with a port, and without a
  path, except for a trailing `/`, which is dropped. Scheme and host are taken in any case, and lowercased. Any other
  address is a usage error. It has to be the site's own address, the one its deployment gives it (see
  [OAuth](https://github.com/parkingradio/website/blob/main/docs/design/server/oauth.md)), e.g. `http://localhost:5173`
  for a development server, not `http://127.0.0.1:5173`.
- **Credentials.** The tool acts on a site as an admin who connected it (see [Auth](auth.md)). The connection's tokens
  are kept in the operating system's credential store (the Windows Credential Manager, the macOS Keychain, or the Secret
  Service on Linux), in an entry of the service `parkingradio` for each site, whose user name is the site's address.
  When there's no credential store the tool can use, a command that needs it fails, and says so. When the tool can't
  read what it kept for a site, it's as if it wasn't connected to it. Commands that change a
  site's credentials, or could, do so one at a time, even in several `parkingradio` processes, with a lock file,
  `credentials.lock`, in the tool's directory: `$XDG_CONFIG_HOME/parkingradio` when `XDG_CONFIG_HOME` is set to an
  absolute path, or else `%APPDATA%\parkingradio` on Windows, and `~/.config/parkingradio` elsewhere.

## Commands

| Document | Commands |
|---|---|
| [Auth](auth.md) | `auth login`, `auth status` and `auth logout`: connecting the tool to a site, and how commands use the connection |
