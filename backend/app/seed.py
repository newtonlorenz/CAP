"""Seed script to create initial admin user.

Usage:
    python -m app.seed --email admin@example.com --name "Admin User" --password secretpass
"""

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.database import async_session
from app.models.user import User
from app.services.auth import hash_password


async def create_admin(email: str, name: str, password: str) -> None:
    async with async_session() as session:
        existing = await session.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            print(f"Error: User with email {email} already exists")
            sys.exit(1)

        user = User(
            email=email,
            full_name=name,
            password_hash=hash_password(password),
            role="admin",
            active=True,
        )
        session.add(user)
        await session.commit()
        print(f"Admin user created: {email}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create initial admin user")
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument("--name", required=True, help="Admin full name")
    parser.add_argument("--password", required=True, help="Admin password")

    args = parser.parse_args()

    if len(args.password) < 8:
        print("Error: Password must be at least 8 characters")
        sys.exit(1)

    asyncio.run(create_admin(args.email, args.name, args.password))


if __name__ == "__main__":
    main()
