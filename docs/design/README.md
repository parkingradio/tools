# Design

These documents are the authoritative reference for what the `parkingradio` command-line tool does. This one has the
conventions every command follows, and the index of the commands, each of which has a document of its own. The code
implements these documents, and has to match them: when they disagree, including with comments in the code, the
documents win.

## Conventions

- **Commands.** `parkingradio` is one command, whose subcommands do the work: `parkingradio <command>`.
- **Help.** `--help`, on `parkingradio` and on every command, shows how to use it, on stdout, and exits with 0.
- **Version.** `parkingradio --version` shows the tool's version, on stdout, and exits with 0. Commands don't take
  `--version`.
- **Usage errors.** `parkingradio` without a command shows its help, on stderr, and exits with 2. A command line the
  tool can't take (e.g. an unknown command or option) is a usage error too: it shows how to use the tool and what's
  wrong, on stderr, and exits with 2.
- **Output.** A command's output goes to stdout. Errors go to stderr, and a command that fails exits with 1, unless
  it's a usage error.
- **Language.** The tool's messages are in English.

## Commands

None yet.
