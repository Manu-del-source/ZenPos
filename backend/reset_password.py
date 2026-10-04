"""One-time operator command for resetting an existing SQLite user password.

Provide RESET_USERNAME and RESET_PASSWORD through the environment, then run
``python -m backend.reset_password``. The command never prints the password.
"""
import os

import database as db


def main() -> None:
    username = os.getenv("RESET_USERNAME", "").strip()
    password = os.getenv("RESET_PASSWORD", "")
    if not username or not password:
        raise SystemExit("RESET_USERNAME and RESET_PASSWORD are required")
    if len(password) < 12:
        raise SystemExit("RESET_PASSWORD must contain at least 12 characters")
    if not db.reset_user_password(username, password):
        raise SystemExit("Password reset was not applied")
    print("Password reset completed.")


if __name__ == "__main__":
    main()
