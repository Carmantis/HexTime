"""Maintenance commands, run on the server.

    python -m app.cli setup --config-dir /config

    python -m app.cli create-admin --email anna@example.org --name "Anna Admin"
    python -m app.cli create-admin --email anna@example.org --name "Anna Admin" --send-link

By default the password is asked twice in the terminal, never given on the
command line (it would end up in the shell history); --password-stdin reads it
from standard input instead, for scripts. With --send-link nobody types a
password here at all: the administrator gets the same "set your password"
email as everyone else.
"""

import argparse
import getpass
import sys
from pathlib import Path

from app import installer
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.email import mailer_for
from app.core.errors import AppError
from app.services.accounts import invite_user
from app.services.users import make_admin


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Password (at least 12 characters): ")
    if getpass.getpass("Again: ") != first:
        sys.exit("The passwords did not match.")
    return first


def create_admin(args: argparse.Namespace) -> None:
    settings = get_settings()
    if not settings.is_server:
        sys.exit("create-admin is for server mode (APP_MODE=server).")

    with get_session_factory()() as db:
        try:
            if args.send_link:
                user = invite_user(
                    db,
                    email=args.email,
                    display_name=args.name,
                    settings=settings,
                    mailer=mailer_for(settings),
                )
                user.is_admin = True
                db.commit()
                print(f"{user.email} is an administrator; a link to set the password was sent.")
                return
            password = _read_password(args.password_stdin)
            user = make_admin(db, email=args.email, display_name=args.name, password=password)
        except AppError as error:
            sys.exit(f"Not created: {error.message}")
    print(f"{user.email} is an administrator and can sign in.")


def setup(args: argparse.Namespace) -> None:
    """The installation questions; see app/installer.py."""
    try:
        installer.run(
            Path(args.config_dir),
            host_addresses=args.host_address,
            host_time_zone=args.host_time_zone,
        )
    except (installer.SetupCancelledError, KeyboardInterrupt, EOFError):
        sys.exit("\nSetup stopped; nothing was changed.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="hextime", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    admin = commands.add_parser("create-admin", help="create or promote an administrator")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", default="", help="display name (defaults to the email)")
    how = admin.add_mutually_exclusive_group()
    how.add_argument(
        "--password-stdin", action="store_true", help="read the password from standard input"
    )
    how.add_argument(
        "--send-link", action="store_true", help="email a link to set the password instead"
    )
    admin.set_defaults(handler=create_admin)

    wizard = commands.add_parser(
        "setup", help="ask the installation questions and write the server's settings"
    )
    wizard.add_argument(
        "--config-dir", default="/config", help="where to write the settings (default /config)"
    )
    wizard.add_argument(
        "--host-address",
        action="append",
        default=[],
        help="an address of this server, to check the DNS record against (repeatable)",
    )
    wizard.add_argument("--host-time-zone", help="this server's time zone, the default answer")
    wizard.set_defaults(handler=setup)

    args = parser.parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
