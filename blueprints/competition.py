from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timezone, timedelta
from models import db, Competition, CompetitionParticipant, Attempt, Passage, utcnow
from scoring import ScoringService

competition_bp = Blueprint('competition', __name__, url_prefix='/competitions')

@competition_bp.route('/')
def list_competitions():
    """List scheduled, active, and recently completed public competitions."""
    scheduled = Competition.query.filter_by(status='scheduled').order_by(Competition.scheduled_start_time.asc()).all()
    in_progress = Competition.query.filter_by(status='in_progress').order_by(Competition.actual_start_time.desc()).all()
    completed = Competition.query.filter_by(status='completed').order_by(Competition.completed_at.desc()).limit(10).all()

    return render_template(
        'competitions/list.html',
        scheduled=scheduled,
        in_progress=in_progress,
        completed=completed
    )


@competition_bp.route('/join', methods=['GET', 'POST'])
@login_required
def join():
    """Join competition via code."""
    if request.method == 'POST':
        code = request.form.get('join_code', '').strip().upper()
        if not code:
            flash('Please enter a competition join code.', 'danger')
            return render_template('competitions/join.html')

        comp = Competition.query.filter_by(join_code=code).first()
        if not comp:
            flash(f'No competition found with code "{code}". Please check and try again.', 'danger')
            return render_template('competitions/join.html', join_code=code)

        if comp.status == 'cancelled':
            flash('This competition was cancelled.', 'warning')
            return render_template('competitions/join.html')

        if comp.status == 'completed':
            return redirect(url_for('competition.leaderboard', comp_id=comp.id))

        # Check participant limit
        current_count = CompetitionParticipant.query.filter_by(competition_id=comp.id).count()
        is_already_participant = CompetitionParticipant.query.filter_by(
            competition_id=comp.id, user_id=current_user.id
        ).first()

        if not is_already_participant:
            if comp.participant_limit and current_count >= comp.participant_limit:
                flash(f'This competition has reached its limit of {comp.participant_limit} participants.', 'danger')
                return render_template('competitions/join.html')

            # Add participant
            participant = CompetitionParticipant(competition_id=comp.id, user_id=current_user.id)
            db.session.add(participant)
            db.session.commit()

        return redirect(url_for('competition.room', comp_id=comp.id))

    code = request.args.get('code', '').strip().upper()
    return render_template('competitions/join.html', join_code=code)


@competition_bp.route('/<int:comp_id>')
@login_required
def room(comp_id):
    """Competition arena / lobby / typing area depending on state."""
    comp = Competition.query.get_or_404(comp_id)

    # Ensure user is a registered participant
    participant = CompetitionParticipant.query.filter_by(
        competition_id=comp.id, user_id=current_user.id
    ).first()
    if not participant:
        flash('You must join this competition first.', 'warning')
        return redirect(url_for('competition.join', code=comp.join_code))

    # Check for existing attempt
    attempt = Attempt.query.filter_by(
        competition_id=comp.id, user_id=current_user.id
    ).first()

    return render_template(
        'competitions/room.html',
        competition=comp,
        participant=participant,
        existing_attempt=attempt
    )


@competition_bp.route('/<int:comp_id>/state', methods=['GET'])
@login_required
def get_state(comp_id):
    """
    Polling endpoint for synchronized competition state and lobby countdown.
    Security: The passage text is strictly HIDDEN until competition status is 'in_progress'.
    """
    comp = Competition.query.get_or_404(comp_id)
    now = utcnow()

    # Auto-start check if scheduled time reached
    if comp.status == 'scheduled' and comp.scheduled_start_time:
        sched_time = comp.scheduled_start_time
        if sched_time.tzinfo is None:
            sched_time = sched_time.replace(tzinfo=timezone.utc)
        if now >= sched_time:
            comp.status = 'in_progress'
            comp.actual_start_time = sched_time
            db.session.commit()

    participant_count = CompetitionParticipant.query.filter_by(competition_id=comp.id).count()

    # User's attempt status
    attempt = Attempt.query.filter_by(competition_id=comp.id, user_id=current_user.id).first()

    response = {
        'status': comp.status,
        'format': comp.format,
        'duration_seconds': comp.duration_seconds,
        'min_accuracy': comp.min_accuracy,
        'participant_count': participant_count,
        'server_time': now.isoformat(),
        'scheduled_start_time': comp.scheduled_start_time.isoformat() if comp.scheduled_start_time else None,
        'actual_start_time': comp.actual_start_time.isoformat() if comp.actual_start_time else None,
        'has_attempt': attempt is not None,
        'attempt_status': attempt.status if attempt else None,
        'attempt_id': attempt.id if attempt else None
    }

    # Only reveal passage when competition has actually started!
    if comp.status in ('in_progress', 'completed'):
        response['passage'] = {
            'title': comp.passage.title,
            'content': comp.passage.content,
            'difficulty': comp.passage.difficulty
        }
    else:
        response['passage'] = None

    return jsonify(response)


@competition_bp.route('/<int:comp_id>/start_attempt', methods=['POST'])
@login_required
def start_attempt(comp_id):
    """
    Initializes the participant's single scored attempt.
    Enforces:
    - Competition must be in_progress.
    - Exactly one attempt allowed per user.
    - Reconnection returns existing attempt without resetting.
    """
    comp = Competition.query.get_or_404(comp_id)
    if comp.status != 'in_progress':
        return jsonify({'error': 'Competition is not active yet.'}), 400

    now = utcnow()

    # Check existing attempt
    existing = Attempt.query.filter_by(competition_id=comp.id, user_id=current_user.id).first()
    if existing:
        # User is reconnecting/refreshing! Return their ongoing attempt without reset!
        return jsonify({
            'attempt_id': existing.id,
            'status': existing.status,
            'typed_text': existing.current_typed_text,
            'last_seq': existing.last_event_seq,
            'wpm': existing.wpm,
            'accuracy': existing.accuracy,
            'elapsed_seconds': existing.elapsed_seconds,
            'passage': {
                'title': comp.passage.title,
                'content': comp.passage.content
            },
            'server_deadline': existing.server_deadline.isoformat() if existing.server_deadline else None,
            'reconnected': True
        })

    # Calculate deadline for timed competition
    deadline = None
    if comp.format == 'timed' and comp.duration_seconds:
        # Deadline relative to competition start or attempt start
        # Use competition actual_start_time + duration to sync end time for all participants
        base_start = comp.actual_start_time or now
        deadline = base_start + timedelta(seconds=comp.duration_seconds)

    attempt = Attempt(
        user_id=current_user.id,
        competition_id=comp.id,
        passage_id=comp.passage_id,
        test_type='timed_competition' if comp.format == 'timed' else 'completion_competition',
        duration_seconds=comp.duration_seconds,
        status='in_progress',
        server_start_time=comp.actual_start_time or now,
        server_deadline=deadline,
        elapsed_seconds=0.0,
        correct_chars=0,
        total_scored_keystrokes=0,
        incorrect_attempts=0,
        backspace_count=0,
        wpm=0.0,
        accuracy=100.0,
        is_completed=False,
        current_typed_text='',
        last_event_seq=0
    )
    db.session.add(attempt)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        # In case of concurrent request race, fetch the created attempt
        attempt = Attempt.query.filter_by(competition_id=comp.id, user_id=current_user.id).first()

    return jsonify({
        'attempt_id': attempt.id,
        'status': attempt.status,
        'typed_text': attempt.current_typed_text,
        'last_seq': attempt.last_event_seq,
        'wpm': attempt.wpm,
        'accuracy': attempt.accuracy,
        'elapsed_seconds': 0.0,
        'passage': {
            'title': comp.passage.title,
            'content': comp.passage.content
        },
        'server_deadline': attempt.server_deadline.isoformat() if attempt.server_deadline else None,
        'reconnected': False
    })


@competition_bp.route('/<int:comp_id>/leaderboard')
def leaderboard(comp_id):
    """View leaderboard and winners for a competition."""
    comp = Competition.query.get_or_404(comp_id)
    return render_template('competitions/leaderboard.html', competition=comp)


@competition_bp.route('/<int:comp_id>/leaderboard_data')
def leaderboard_data(comp_id):
    """API endpoint providing real-time provisional or final rankings."""
    comp = Competition.query.get_or_404(comp_id)
    attempts = Attempt.query.filter_by(competition_id=comp.id).all()

    ranked = ScoringService.rank_participants(
        attempts=attempts,
        competition_format=comp.format,
        min_accuracy=comp.min_accuracy
    )

    data = []
    for item in ranked:
        att = item['attempt']
        user = att.user
        data.append({
            'rank': item['rank'],
            'is_winner': item['is_winner'],
            'is_eligible': item['is_eligible'],
            'username': user.username if user else 'Anonymous',
            'wpm': att.wpm,
            'accuracy': att.accuracy,
            'elapsed_seconds': round(att.elapsed_seconds, 2),
            'incorrect_attempts': att.incorrect_attempts,
            'status': att.status,
            'is_completed': att.is_completed,
            'suspicious': att.suspicious_flag
        })

    is_final = (comp.status == 'completed')
    return jsonify({
        'competition_id': comp.id,
        'title': comp.title,
        'status': comp.status,
        'format': comp.format,
        'is_final': is_final,
        'min_accuracy': comp.min_accuracy,
        'rankings': data
    })
