"""
Secure CLI command to create an administrator user.
Usage:
  python create_admin.py --username admin --email admin@example.com
Or interactive:
  python create_admin.py
"""
import sys
import getpass
import argparse
from app import create_app
from models import db, User
from security import sanitize_username, validate_email

def create_admin():
    parser = argparse.ArgumentParser(description="Create a secure administrator for Speedoo.")
    parser.add_argument('--username', help="Admin username")
    parser.add_argument('--email', help="Admin email")
    parser.add_argument('--password', help="Admin password (optional; will prompt securely if omitted)")

    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        db.create_all()

        username = args.username
        if not username:
            username = input("Enter admin username: ").strip()

        clean_username = sanitize_username(username)
        if not clean_username:
            print("Error: Username must be 3-30 characters with alphanumeric characters and underscores.")
            sys.exit(1)

        email = args.email
        if not email:
            email = input("Enter admin email: ").strip()

        if not validate_email(email):
            print("Error: Invalid email address format.")
            sys.exit(1)

        # Check existence
        existing = User.query.filter((User.username == clean_username) | (User.email == email)).first()
        if existing:
            if existing.username == clean_username:
                print(f"User '{clean_username}' already exists. Promoting to administrator...")
                existing.is_admin = True
                db.session.commit()
                print("User successfully updated to administrator role.")
                return
            else:
                print(f"Error: An account with email '{email}' already exists.")
                sys.exit(1)

        password = args.password
        if not password:
            password = getpass.getpass("Enter admin password: ")
            confirm = getpass.getpass("Confirm admin password: ")
            if password != confirm:
                print("Error: Passwords do not match.")
                sys.exit(1)

        if len(password) < 8:
            print("Error: Admin password must be at least 8 characters long.")
            sys.exit(1)

        admin = User(
            username=clean_username,
            email=email.lower(),
            is_admin=True
        )
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()

        print(f"Success! Administrator '{clean_username}' created successfully.")

if __name__ == '__main__':
    create_admin()

