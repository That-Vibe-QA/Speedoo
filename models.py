import secrets
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

def utcnow():
    return datetime.now(timezone.utc)

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    attempts = db.relationship('Attempt', back_populates='user', lazy='dynamic')
    participations = db.relationship('CompetitionParticipant', back_populates='user', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username}>"


class Passage(db.Model):
    __tablename__ = 'passages'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(20), nullable=False, default='en')  # 'en', 'ml', 'hi', 'es'
    difficulty = db.Column(db.String(20), nullable=False, default='medium')  # easy, medium, hard
    category = db.Column(db.String(50), default='general')
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    @property
    def character_count(self):
        return len(self.content) if self.content else 0

    @property
    def word_count(self):
        return len(self.content.split()) if self.content else 0

    def __repr__(self):
        return f"<Passage {self.title} ({self.difficulty})>"


class Competition(db.Model):
    __tablename__ = 'competitions'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    format = db.Column(db.String(30), nullable=False)  # 'timed' or 'first_to_complete'
    duration_seconds = db.Column(db.Integer, nullable=True)  # For timed competition (e.g. 60, 120, etc.)
    passage_id = db.Column(db.Integer, db.ForeignKey('passages.id'), nullable=False)
    join_code = db.Column(db.String(12), unique=True, nullable=False, index=True)
    min_accuracy = db.Column(db.Float, default=0.0, nullable=False)  # Minimum accuracy % for winner eligibility
    participant_limit = db.Column(db.Integer, nullable=True)  # Nullable for unlimited
    
    # Scheduling & Status: 'scheduled', 'in_progress', 'completed', 'cancelled'
    status = db.Column(db.String(20), default='scheduled', nullable=False, index=True)
    scheduled_start_time = db.Column(db.DateTime(timezone=True), nullable=True)
    actual_start_time = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    passage = db.relationship('Passage', foreign_keys=[passage_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    participants = db.relationship('CompetitionParticipant', back_populates='competition', cascade='all, delete-orphan')
    attempts = db.relationship('Attempt', back_populates='competition', cascade='all, delete-orphan')

    @staticmethod
    def generate_join_code():
        # Generate clean, unambiguous 6-character code
        alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
        return ''.join(secrets.choice(alphabet) for _ in range(6))

    def is_joinable(self):
        return self.status == 'scheduled'

    def is_active(self):
        return self.status == 'in_progress'

    def has_ended(self):
        return self.status in ('completed', 'cancelled')

    def __repr__(self):
        return f"<Competition {self.title} [{self.format}]>"


class CompetitionParticipant(db.Model):
    __tablename__ = 'competition_participants'

    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey('competitions.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    joined_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    competition = db.relationship('Competition', back_populates='participants')
    user = db.relationship('User', back_populates='participations')

    __table_args__ = (
        db.UniqueConstraint('competition_id', 'user_id', name='uq_competition_user'),
    )

    def __repr__(self):
        return f"<Participant user={self.user_id} comp={self.competition_id}>"


class Attempt(db.Model):
    __tablename__ = 'attempts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Nullable for anonymous practice
    competition_id = db.Column(db.Integer, db.ForeignKey('competitions.id'), nullable=True)  # Nullable for practice
    passage_id = db.Column(db.Integer, db.ForeignKey('passages.id'), nullable=False)
    
    test_type = db.Column(db.String(30), nullable=False)  # 'timed_practice', 'completion_practice', 'timed_competition', 'completion_competition'
    duration_seconds = db.Column(db.Integer, nullable=True)  # Target duration if timed

    # Status: 'in_progress', 'completed', 'disqualified', 'abandoned'
    status = db.Column(db.String(20), default='in_progress', nullable=False, index=True)

    # Server-measured timing
    server_start_time = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    server_end_time = db.Column(db.DateTime(timezone=True), nullable=True)
    server_deadline = db.Column(db.DateTime(timezone=True), nullable=True)  # Strict deadline for timed tests
    elapsed_seconds = db.Column(db.Float, default=0.0, nullable=False)

    # Verified typing metrics
    correct_chars = db.Column(db.Integer, default=0, nullable=False)
    total_scored_keystrokes = db.Column(db.Integer, default=0, nullable=False)
    incorrect_attempts = db.Column(db.Integer, default=0, nullable=False)
    backspace_count = db.Column(db.Integer, default=0, nullable=False)
    
    wpm = db.Column(db.Float, default=0.0, nullable=False)
    accuracy = db.Column(db.Float, default=0.0, nullable=False)
    is_completed = db.Column(db.Boolean, default=False, nullable=False)
    is_eligible_winner = db.Column(db.Boolean, default=True, nullable=False)
    suspicious_flag = db.Column(db.Boolean, default=False, nullable=False)
    suspicious_reason = db.Column(db.String(255), nullable=True)

    # Current verified state
    current_typed_text = db.Column(db.Text, default='', nullable=False)
    last_event_seq = db.Column(db.Integer, default=0, nullable=False)

    # Competition ranking (cached after finalization)
    rank = db.Column(db.Integer, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    user = db.relationship('User', back_populates='attempts')
    competition = db.relationship('Competition', back_populates='attempts')
    passage = db.relationship('Passage')

    __table_args__ = (
        # Ensure single attempt per participant per competition
        db.UniqueConstraint('competition_id', 'user_id', name='uq_attempt_competition_user'),
    )

    def __repr__(self):
        return f"<Attempt id={self.id} user={self.user_id} wpm={self.wpm} acc={self.accuracy}>"

