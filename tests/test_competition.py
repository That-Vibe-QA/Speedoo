import unittest
from datetime import datetime, timezone, timedelta
from app import create_app
from models import db, User, Passage, Competition, CompetitionParticipant, Attempt
from config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    SECRET_KEY = 'test-secret-key'

class TestCompetitionAndSecurity(unittest.TestCase):

    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Create Admin
        self.admin = User(username='admin', email='admin@test.local', is_admin=True)
        self.admin.set_password('AdminPass123!')
        db.session.add(self.admin)

        # Create Normal User
        self.user = User(username='player1', email='player1@test.local', is_admin=False)
        self.user.set_password('PlayerPass123!')
        db.session.add(self.user)

        # Create Passage
        self.passage = Passage(
            title="Fast Rivers",
            content="Water flows rapidly down the mountain.",
            difficulty="easy"
        )
        db.session.add(self.passage)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def login(self, username, password):
        return self.client.post('/auth/login', data={
            'identifier': username,
            'password': password
        }, follow_redirects=True)

    def test_anonymous_user_registration_cannot_become_admin(self):
        # Public registration creates standard user (is_admin=False)
        res = self.client.post('/auth/register', data={
            'username': 'normalguy',
            'email': 'guy@test.local',
            'password': 'Password123!',
            'confirm_password': 'Password123!',
            'is_admin': '1'  # Attempt to elevate
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        created = User.query.filter_by(username='normalguy').first()
        self.assertIsNotNone(created)
        self.assertFalse(created.is_admin)

    def test_admin_route_protection(self):
        # Anonymous access redirected to login (302) or 401
        res = self.client.get('/admin/')
        self.assertIn(res.status_code, (302, 401))

        # Normal user access forbidden (403)
        self.login('player1', 'PlayerPass123!')
        res = self.client.get('/admin/')
        self.assertEqual(res.status_code, 403)

        # Log out first
        self.client.get('/auth/logout')

        # Admin access granted (200)
        self.login('admin', 'AdminPass123!')
        res = self.client.get('/admin/')
        self.assertEqual(res.status_code, 200)

    def test_competition_passage_hidden_before_start(self):
        # Create scheduled competition
        comp = Competition(
            title="Hidden Passage Cup",
            format="timed",
            duration_seconds=60,
            passage_id=self.passage.id,
            join_code="SECRET",
            min_accuracy=80.0,
            status="scheduled",
            created_by_id=self.admin.id
        )
        db.session.add(comp)
        db.session.commit()

        self.login('player1', 'PlayerPass123!')

        # Join competition
        self.client.post('/competitions/join', data={'join_code': 'SECRET'}, follow_redirects=True)

        # Poll state while in scheduled status
        res = self.client.get(f'/competitions/{comp.id}/state')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'scheduled')
        # Crucial fairness check: passage text must be None while scheduled!
        self.assertIsNone(data['passage'])

        # Now start competition as admin
        comp.status = 'in_progress'
        comp.actual_start_time = datetime.now(timezone.utc)
        db.session.commit()

        # Poll state again as player: passage is now visible!
        res2 = self.client.get(f'/competitions/{comp.id}/state')
        data2 = res2.get_json()
        self.assertEqual(data2['status'], 'in_progress')
        self.assertIsNotNone(data2['passage'])
        self.assertEqual(data2['passage']['content'], self.passage.content)

    def test_single_attempt_and_reconnection_persistence(self):
        # Start competition
        comp = Competition(
            title="Single Attempt Duel",
            format="timed",
            duration_seconds=60,
            passage_id=self.passage.id,
            join_code="DUEL01",
            min_accuracy=80.0,
            status="in_progress",
            actual_start_time=datetime.now(timezone.utc),
            created_by_id=self.admin.id
        )
        db.session.add(comp)
        db.session.commit()

        self.login('player1', 'PlayerPass123!')

        # 1. Start attempt
        res = self.client.post(f'/competitions/{comp.id}/start_attempt')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        attempt_id = data['attempt_id']
        self.assertFalse(data['reconnected'])

        # 2. Type some characters: "Water"
        events = [
            {"seq": 1, "type": "insert", "char": "W"},
            {"seq": 2, "type": "insert", "char": "a"},
            {"seq": 3, "type": "insert", "char": "t"},
            {"seq": 4, "type": "insert", "char": "e"},
            {"seq": 5, "type": "insert", "char": "r"},
        ]
        ev_res = self.client.post(f'/api/practice/{attempt_id}/events', json={'events': events})
        self.assertEqual(ev_res.status_code, 200)

        # 3. Simulate page refresh / reconnect: call start_attempt again
        res_reconnect = self.client.post(f'/competitions/{comp.id}/start_attempt')
        self.assertEqual(res_reconnect.status_code, 200)
        reconnect_data = res_reconnect.get_json()

        # Verified: must return identical attempt, with reconnected flag and preserved text!
        self.assertEqual(reconnect_data['attempt_id'], attempt_id)
        self.assertTrue(reconnect_data['reconnected'])
        self.assertEqual(reconnect_data['typed_text'], "Water")
        self.assertEqual(reconnect_data['last_seq'], 5)

        # Database constraint test: total attempts for this user and comp must strictly be 1
        count = Attempt.query.filter_by(competition_id=comp.id, user_id=self.user.id).count()
        self.assertEqual(count, 1)

if __name__ == '__main__':
    unittest.main()
