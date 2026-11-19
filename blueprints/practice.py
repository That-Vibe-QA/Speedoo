from flask import Blueprint, render_template, request, jsonify, abort
from datetime import datetime, timezone, timedelta
from flask_login import current_user
from models import db, Passage, Attempt, utcnow
from scoring import ScoringService

practice_bp = Blueprint('practice', __name__)

@practice_bp.route('/')
def index():
    """Home and practice typing screen."""
    return render_template('practice/index.html')


@practice_bp.route('/api/practice/passages', methods=['GET'])
def get_passages():
    """Returns available passages grouped or filtered by difficulty."""
    difficulty = request.args.get('difficulty', '').lower()
    query = Passage.query.filter_by(is_active=True)
    if difficulty in ('easy', 'medium', 'hard'):
        query = query.filter_by(difficulty=difficulty)
    passages = query.order_by(Passage.id.asc()).all()

    return jsonify({
        'passages': [{
            'id': p.id,
            'title': p.title,
            'difficulty': p.difficulty,
            'content': p.content,
            'char_count': p.character_count,
            'word_count': p.word_count
        } for p in passages]
    })


@practice_bp.route('/api/practice/start', methods=['POST'])
def start_practice():
    """
    Initializes a verified practice session on the server.
    Parameters:
    - passage_id (int)
    - mode: 'timed' | 'completion'
    - duration: int (30, 60, 120, 300) for timed mode
    """
    data = request.get_json() or {}
    passage_id = data.get('passage_id')
    mode = data.get('mode', 'timed')
    duration = data.get('duration', 60)

    passage = Passage.query.get(passage_id)
    if not passage:
        return jsonify({'error': 'Passage not found'}), 404

    now = utcnow()
    deadline = None
    if mode == 'timed':
        try:
            duration = int(duration)
            if duration not in (30, 60, 120, 300):
                duration = 60
        except (ValueError, TypeError):
            duration = 60
        deadline = now + timedelta(seconds=duration)
    else:
        duration = None

    user_id = current_user.id if current_user.is_authenticated else None

    attempt = Attempt(
        user_id=user_id,
        passage_id=passage.id,
        test_type='timed_practice' if mode == 'timed' else 'completion_practice',
        duration_seconds=duration,
        status='in_progress',
        server_start_time=now,
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
    db.session.commit()

    return jsonify({
        'attempt_id': attempt.id,
        'passage': {
            'id': passage.id,
            'title': passage.title,
            'content': passage.content,
            'difficulty': passage.difficulty
        },
        'server_time': now.isoformat(),
        'server_deadline': deadline.isoformat() if deadline else None,
        'duration_seconds': duration,
        'mode': mode
    })


@practice_bp.route('/api/practice/<int:attempt_id>/events', methods=['POST'])
def submit_events(attempt_id):
    """
    Processes ordered typing events from browser, updates server-validated state.
    """
    attempt = Attempt.query.get(attempt_id)
    if not attempt:
        return jsonify({'error': 'Attempt not found'}), 404

    if attempt.status != 'in_progress':
        return jsonify({
            'status': attempt.status,
            'is_finished': True,
            'wpm': attempt.wpm,
            'accuracy': attempt.accuracy,
            'elapsed_seconds': attempt.elapsed_seconds,
            'message': 'This attempt has already been concluded.'
        })

    data = request.get_json() or {}
    events = data.get('events', [])
    now = utcnow()

    # Calculate real elapsed time strictly on server
    start_time = attempt.server_start_time
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    elapsed = max(0.001, (now - start_time).total_seconds())

    # Check if timed test has expired
    is_timed = attempt.test_type.startswith('timed')
    time_expired = False
    if is_timed and attempt.server_deadline:
        deadline = attempt.server_deadline
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        # Give a small 1.5s grace period for network transit
        if now > (deadline + timedelta(seconds=1.5)):
            time_expired = True
            elapsed = float(attempt.duration_seconds)

    passage_text = attempt.passage.content

    # Validate and replay events if any
    if events:
        replay = ScoringService.apply_events(
            target_text=passage_text,
            events=events,
            existing_typed_text=attempt.current_typed_text,
            existing_correct_keystrokes=attempt.correct_chars,
            existing_total_scored_keystrokes=attempt.total_scored_keystrokes,
            existing_incorrect_attempts=attempt.incorrect_attempts,
            existing_backspace_count=attempt.backspace_count,
            expected_seq_start=attempt.last_event_seq + 1
        )

        if not replay['success']:
            return jsonify({'error': replay['error']}), 400

        attempt.current_typed_text = replay['resulting_text']
        attempt.last_event_seq = replay['last_seq']
        attempt.correct_chars = replay['correct_prefix_length']
        attempt.total_scored_keystrokes = replay['total_scored_keystrokes']
        attempt.incorrect_attempts = replay['incorrect_attempts']
        attempt.backspace_count = replay['backspace_count']

        if replay['suspicious']:
            attempt.suspicious_flag = True
            attempt.suspicious_reason = "; ".join(replay['suspicious_reasons'])

        if replay['is_exact_match']:
            attempt.is_completed = True

    # Calculate live metrics
    attempt.elapsed_seconds = elapsed
    attempt.wpm = ScoringService.calculate_wpm(attempt.correct_chars, elapsed)
    attempt.accuracy = ScoringService.calculate_accuracy(
        attempt.total_scored_keystrokes - attempt.incorrect_attempts,
        attempt.total_scored_keystrokes
    )

    should_finish = False
    if attempt.is_completed:
        # Passage finished! Stop timer and finalize attempt immediately
        should_finish = True
        attempt.elapsed_seconds = elapsed
        attempt.wpm = ScoringService.calculate_wpm(attempt.correct_chars, attempt.elapsed_seconds)
    elif is_timed and (time_expired or elapsed >= (attempt.duration_seconds or 60)):
        should_finish = True
        attempt.elapsed_seconds = float(attempt.duration_seconds)
        # Recalculate WPM with exact duration
        attempt.wpm = ScoringService.calculate_wpm(attempt.correct_chars, attempt.elapsed_seconds)

    if should_finish:
        attempt.status = 'completed'
        attempt.server_end_time = now

    db.session.commit()

    return jsonify({
        'status': attempt.status,
        'is_finished': attempt.status == 'completed',
        'wpm': attempt.wpm,
        'accuracy': attempt.accuracy,
        'correct_chars': attempt.correct_chars,
        'incorrect_attempts': attempt.incorrect_attempts,
        'backspace_count': attempt.backspace_count,
        'elapsed_seconds': round(attempt.elapsed_seconds, 1),
        'is_completed': attempt.is_completed,
        'typed_length': len(attempt.current_typed_text),
        'target_length': len(passage_text)
    })


@practice_bp.route('/api/practice/<int:attempt_id>/finish', methods=['POST'])
def finish_practice(attempt_id):
    """Explicit endpoint to wrap up practice attempt."""
    attempt = Attempt.query.get(attempt_id)
    if not attempt:
        return jsonify({'error': 'Attempt not found'}), 404

    now = utcnow()
    if attempt.status == 'in_progress':
        start_time = attempt.server_start_time
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        elapsed = max(0.001, (now - start_time).total_seconds())
        if attempt.duration_seconds and elapsed > attempt.duration_seconds:
            elapsed = float(attempt.duration_seconds)
        attempt.elapsed_seconds = elapsed
        attempt.server_end_time = now
        attempt.status = 'completed'
        attempt.wpm = ScoringService.calculate_wpm(attempt.correct_chars, elapsed)
        attempt.accuracy = ScoringService.calculate_accuracy(
            attempt.total_scored_keystrokes - attempt.incorrect_attempts,
            attempt.total_scored_keystrokes
        )
        db.session.commit()

    return jsonify({
        'status': attempt.status,
        'wpm': attempt.wpm,
        'accuracy': attempt.accuracy,
        'correct_chars': attempt.correct_chars,
        'incorrect_attempts': attempt.incorrect_attempts,
        'backspace_count': attempt.backspace_count,
        'elapsed_seconds': round(attempt.elapsed_seconds, 1),
        'is_completed': attempt.is_completed
    })
