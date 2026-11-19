"""
Database initialization and seeding script for Speedoo.
Usage:
  python init_db.py
"""
import os
from datetime import datetime, timezone, timedelta
from app import create_app
from models import db, User, Passage, Competition, CompetitionParticipant, Attempt

SAMPLE_PASSAGES = [
    # EASY
    {
        "title": "The Morning Walk",
        "difficulty": "easy",
        "category": "lifestyle",
        "content": "The morning sun was warm and bright. Birds were singing high up in the green trees. A cool breeze gently moved the dry leaves along the quiet street."
    },
    {
        "title": "Simple Code",
        "difficulty": "easy",
        "category": "technology",
        "content": "Clean code is simple and direct. It reads like well written prose. Clean code never obscures the designer intent but is full of crisp clarity."
    },
    # MEDIUM
    {
        "title": "The Art of Typing",
        "difficulty": "medium",
        "category": "typing",
        "content": "Touch typing is an essential skill that transforms thoughts into digital words with rhythm and precision. By keeping your fingers anchored on the home row keys, you train muscle memory to instinctively reach every symbol across the keyboard without glancing down."
    },
    {
        "title": "The Digital River",
        "difficulty": "medium",
        "category": "nature",
        "content": "Rivers carve their pathways across rugged terrain, not through sheer strength, but through steady and relentless perseverance. In a similar way, deliberate daily practice builds unstoppable speed, endurance, and quiet confidence over time."
    },
    # HARD
    {
        "title": "Algorithmic Elegance",
        "difficulty": "hard",
        "category": "engineering",
        "content": "Distributed consensus protocols, such as Paxos and Raft, coordinate distributed state machines across asynchronous networks while tolerating arbitrary node crashes and message reordering. Ensuring safety invariants—such as linearizability and epoch consistency—demands mathematical rigor."
    },
    {
        "title": "Punctuation & Syntax Challenge",
        "difficulty": "hard",
        "category": "syntax",
        "content": "Did you know that fast typists balance speed (e.g., 90+ WPM) with surgical accuracy (~98%)? When complex symbols appear—such as { brackets, semicolons; hyphens-and-dashes, and \"double quotes\"!—their pace remains rhythmic and unhurried."
    }
]

def init_database():
    app = create_app()
    with app.app_context():
        print("Creating all database tables...")
        db.create_all()

        # Seed default passages if none exist
        if Passage.query.count() == 0:
            print("Seeding sample typing passages...")
            for p_data in SAMPLE_PASSAGES:
                passage = Passage(**p_data)
                db.session.add(passage)
            db.session.commit()
            print(f"Added {len(SAMPLE_PASSAGES)} sample passages.")
        else:
            print(f"Passages already exist ({Passage.query.count()} total).")

        # Seed demo admin if none exist
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            print("Creating default administrator (username: admin, password: AdminPassword123!)...")
            admin = User(
                username='admin',
                email='admin@speedoo.local',
                is_admin=True
            )
            admin.set_password('AdminPassword123!')
            db.session.add(admin)
            db.session.commit()
            print("Default admin created.")

        # Seed sample demo users
        demo_users = [
            ('alice', 'alice@speedoo.local', 'Password123!'),
            ('bob', 'bob@speedoo.local', 'Password123!'),
            ('charlie', 'charlie@speedoo.local', 'Password123!')
        ]
        created_users = []
        for uname, uemail, upass in demo_users:
            u = User.query.filter_by(username=uname).first()
            if not u:
                u = User(username=uname, email=uemail, is_admin=False)
                u.set_password(upass)
                db.session.add(u)
                db.session.commit()
                print(f"Created demo user: {uname}")
            created_users.append(u)

        # Seed demo competitions if none exist
        if Competition.query.count() == 0:
            print("Seeding sample competitions...")
            passage_timed = Passage.query.filter_by(difficulty='medium').first()
            passage_first = Passage.query.filter_by(difficulty='easy').first()

            # 1. Timed Competition (60 seconds)
            now = datetime.now(timezone.utc)
            comp1 = Competition(
                title="Weekly Speed Sprint (60s)",
                description="A fast 60-second dash testing rapid accuracy and rhythm. Show your best WPM!",
                format="timed",
                duration_seconds=60,
                passage_id=passage_timed.id,
                join_code="SPRINT",
                min_accuracy=85.0,
                participant_limit=50,
                status="scheduled",
                scheduled_start_time=now + timedelta(hours=2),
                created_by_id=admin.id
            )
            db.session.add(comp1)

            # 2. First-to-Complete Competition
            comp2 = Competition(
                title="Rapid Match: The Morning Walk",
                description="First typist to finish the entire passage with 100% exact match wins!",
                format="first_to_complete",
                duration_seconds=None,
                passage_id=passage_first.id,
                join_code="MORNING",
                min_accuracy=90.0,
                participant_limit=20,
                status="scheduled",
                scheduled_start_time=now + timedelta(days=1),
                created_by_id=admin.id
            )
            db.session.add(comp2)
            db.session.commit()
            print("Sample competitions created with join codes 'SPRINT' and 'MORNING'.")

        print("Database initialization complete!")

if __name__ == '__main__':
    init_database()

