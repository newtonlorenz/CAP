"""Local first-run installation command. Run only inside the trusted backend host.

Example: python -m app.setup --email operator@example.com --name "Operator" \
    --jurisdiction-code dk --jurisdiction-name "Denmark"
"""

import argparse
import asyncio
import getpass
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create the first installation operator and jurisdiction."
    )
    parser.add_argument(
        "--email", required=True, help="Email of the first operator or an existing admin"
    )
    parser.add_argument("--name", help="Full name when creating a new admin")
    parser.add_argument(
        "--jurisdiction-code", required=True, help="Unique code, 2-20 letters/digits/_/-"
    )
    parser.add_argument("--jurisdiction-name", required=True, help="Name shown in CAP")
    parser.add_argument(
        "--existing-admin",
        action="store_true",
        help="Explicitly designate the named active admin as an installation operator",
    )
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read a new admin password from stdin; never pass it as an argument",
    )
    parser.add_argument(
        "--example",
        action="store_true",
        help="Add a separate unapproved synthetic training set (development and test only)",
    )
    return parser


async def run_setup(args: argparse.Namespace, password: str | None):
    from app.database import async_session
    from app.services.bootstrap import setup_installation

    async with async_session() as db:
        return await setup_installation(
            db,
            email=args.email,
            name=args.name,
            password=password,
            jurisdiction_code=args.jurisdiction_code,
            jurisdiction_name=args.jurisdiction_name,
            existing_admin=args.existing_admin,
            example=args.example,
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.existing_admin:
        if args.password_stdin or args.name:
            print("--existing-admin does not accept --name or --password-stdin.", file=sys.stderr)
            return 2
        password = None
    else:
        if not args.name:
            print("--name is required for a new admin.", file=sys.stderr)
            return 2
        if args.password_stdin:
            password = sys.stdin.readline().rstrip("\r\n")
        elif sys.stdin.isatty():
            password = getpass.getpass("New admin password: ")
            if password != getpass.getpass("Confirm password: "):
                print("Passwords do not match. Setup changed nothing.", file=sys.stderr)
                return 2
        else:
            print("Use a terminal password prompt or --password-stdin.", file=sys.stderr)
            return 2

    try:
        result = asyncio.run(run_setup(args, password))
    except ValueError as exc:
        print(f"Setup stopped: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - CLI boundary must not print connection credentials
        # Keep database credentials and connection details out of terminal output.
        print(
            f"Setup failed ({type(exc).__name__}). Check migration and database access.",
            file=sys.stderr,
        )
        return 1

    print(f"Operator ready: {result.email}")
    print(f"Jurisdiction ready: {result.jurisdiction_code}")
    if args.example:
        print("Synthetic EXAMPLE scope ready as an unapproved draft; it is not regulatory text.")
    print(
        "Next: sign in, add requirements, approve the baseline, then open a review."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
