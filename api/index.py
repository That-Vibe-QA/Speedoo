import os
import sys

# Ensure root directory is in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app import create_app
from models import db, Passage, User, Competition
from init_db import SAMPLE_PASSAGES
from datetime import datetime, timezone, timedelta

app = create_app()

# Automatic table creation & seeding if database is empty on cold start
with app.app_context():
    try:
        db.create_all()
        if Passage.query.count() == 0:
            for p_data in SAMPLE_PASSAGES:
                db.session.add(Passage(**p_data))
            
            # Seed default admin
            admin = User(username='admin', email='admin@speedoo.local', is_admin=True)
            admin.set_password('AdminPassword123!')
            db.session.add(admin)

            # Seed demo competitors
            for uname, uemail in [('alice', 'alice@speedoo.local'), ('bob', 'bob@speedoo.local'), ('charlie', 'charlie@speedoo.local')]:
                u = User(username=uname, email=uemail, is_admin=False)
                u.set_password('Password123!')
                db.session.add(u)
            
            db.session.commit()

            # Seed default competitions
            p_timed = Passage.query.filter_by(difficulty='medium').first()
            p_first = Passage.query.filter_by(difficulty='easy').first()
            now = datetime.now(timezone.utc)

            c1 = Competition(
                title="Weekly Speed Sprint (60s)",
                description="Fast 60-second dash testing rapid accuracy and rhythm.",
                format="timed",
                duration_seconds=60,
                passage_id=p_timed.id,
                join_code="SPRINT",
                min_accuracy=85.0,
                status="scheduled",
                scheduled_start_time=now + timedelta(hours=2),
                created_by_id=admin.id
            )
            c2 = Competition(
                title="Rapid Match: The Morning Walk",
                description="First typist to finish the entire passage with exact match wins!",
                format="first_to_complete",
                duration_seconds=None,
                passage_id=p_first.id,
                join_code="MORNING",
                min_accuracy=90.0,
                status="scheduled",
                scheduled_start_time=now + timedelta(days=1),
                created_by_id=admin.id
            )
            db.session.add_all([c1, c2])
            db.session.commit()
    except Exception as e:
        print(f"Startup initialization notice: {e}")

# Vercel WSGI entry point & PATH_INFO Normalizer Middleware
class VercelPathFixMiddleware:
    """
    Vercel serverless rewrites (e.g. source: /(.*) -> destination: /api/index.py)
    often deliver PATH_INFO containing the destination function name (/api/index.py or /api/index).
    This middleware reconstructs the true requested client URL from Vercel's edge headers
    (x-matched-path, x-forwarded-uri) or strips the internal destination prefix so Flask's router
    matches routes (/ -> practice.index, /competitions/ -> competition.list_competitions, etc.).
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        matched_path = (
            environ.get('HTTP_X_MATCHED_PATH') or
            environ.get('HTTP_X_FORWARDED_URI') or
            environ.get('HTTP_X_ORIGINAL_URL') or
            environ.get('PATH_INFO', '')
        )
        if matched_path.startswith('/api/index.py'):
            matched_path = matched_path[len('/api/index.py'):] or '/'
        elif matched_path.startswith('/api/index'):
            matched_path = matched_path[len('/api/index'):] or '/'
        elif not matched_path:
            matched_path = '/'

        environ['PATH_INFO'] = matched_path
        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathFixMiddleware(app.wsgi_app)

