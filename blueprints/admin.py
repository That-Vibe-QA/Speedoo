import io
import csv
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response, abort
from flask_login import login_required, current_user
from models import db, Competition, CompetitionParticipant, Attempt, Passage, User, utcnow
from security import admin_required
from scoring import ScoringService

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.before_request
@login_required
@admin_required
def ensure_admin():
    """Ensure all admin routes require administrator role."""
    pass


@admin_bp.route('/')
def dashboard():
    """Admin dashboard overview."""
    total_users = User.query.count()
    total_competitions = Competition.query.count()
    total_attempts = Attempt.query.count()
    passages_count = Passage.query.count()

    competitions = Competition.query.order_by(Competition.created_at.desc()).all()
    passages = Passage.query.order_by(Passage.id.desc()).all()

    return render_template(
        'admin/dashboard.html',
        total_users=total_users,
        total_competitions=total_competitions,
        total_attempts=total_attempts,
        passages_count=passages_count,
        competitions=competitions,
        passages=passages
    )


@admin_bp.route('/competitions/create', methods=['GET', 'POST'])
def create_competition():
    """Create a new competition."""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        comp_format = request.form.get('format', 'timed')
        duration = request.form.get('duration_seconds')
        passage_id = request.form.get('passage_id')
        min_accuracy = request.form.get('min_accuracy', '0.0')
        participant_limit = request.form.get('participant_limit')
        scheduled_start = request.form.get('scheduled_start_time', '').strip()

        errors = []
        if not title:
            errors.append('Title is required.')
        if comp_format not in ('timed', 'first_to_complete'):
            errors.append('Invalid competition format.')

        duration_val = None
        if comp_format == 'timed':
            try:
                duration_val = int(duration)
                if duration_val <= 0:
                    errors.append('Duration must be greater than 0 seconds.')
            except (ValueError, TypeError):
                errors.append('Valid duration in seconds is required for timed format.')

        passage = Passage.query.get(passage_id)
        if not passage:
            errors.append('Please select a valid passage.')

        try:
            min_acc_val = float(min_accuracy)
            if min_acc_val < 0 or min_acc_val > 100:
                errors.append('Minimum accuracy must be between 0% and 100%.')
        except ValueError:
            min_acc_val = 0.0

        limit_val = None
        if participant_limit and participant_limit.strip():
            try:
                limit_val = int(participant_limit)
                if limit_val <= 0:
                    errors.append('Participant limit must be a positive integer.')
            except ValueError:
                errors.append('Participant limit must be an integer.')

        scheduled_dt = None
        if scheduled_start:
            try:
                # Expecting HTML5 datetime-local format: YYYY-MM-DDTHH:MM
                scheduled_dt = datetime.fromisoformat(scheduled_start)
                # Treat as UTC if naive
                if scheduled_dt.tzinfo is None:
                    scheduled_dt = scheduled_dt.replace(tzinfo=timezone.utc)
            except ValueError:
                errors.append('Invalid scheduled start time format.')

        if errors:
            for err in errors:
                flash(err, 'danger')
            passages = Passage.query.filter_by(is_active=True).all()
            return render_template('admin/competition_form.html', passages=passages, is_edit=False)

        join_code = Competition.generate_join_code()
        # Verify unique join code
        while Competition.query.filter_by(join_code=join_code).first():
            join_code = Competition.generate_join_code()

        comp = Competition(
            title=title,
            description=description,
            format=comp_format,
            duration_seconds=duration_val,
            passage_id=passage.id,
            join_code=join_code,
            min_accuracy=min_acc_val,
            participant_limit=limit_val,
            status='scheduled',
            scheduled_start_time=scheduled_dt,
            created_by_id=current_user.id
        )
        db.session.add(comp)
        db.session.commit()

        flash(f'Competition "{comp.title}" created with Join Code: {comp.join_code}', 'success')
        return redirect(url_for('admin.dashboard'))

    passages = Passage.query.filter_by(is_active=True).all()
    return render_template('admin/competition_form.html', passages=passages, is_edit=False)


@admin_bp.route('/competitions/<int:comp_id>/edit', methods=['GET', 'POST'])
def edit_competition(comp_id):
    """Edit competition details before it starts."""
    comp = Competition.query.get_or_404(comp_id)

    if comp.status != 'scheduled':
        flash('Only scheduled competitions can be edited.', 'danger')
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        comp_format = request.form.get('format', 'timed')
        duration = request.form.get('duration_seconds')
        passage_id = request.form.get('passage_id')
        min_accuracy = request.form.get('min_accuracy', '0.0')
        participant_limit = request.form.get('participant_limit')
        scheduled_start = request.form.get('scheduled_start_time', '').strip()

        errors = []
        if not title:
            errors.append('Title is required.')

        duration_val = None
        if comp_format == 'timed':
            try:
                duration_val = int(duration)
            except (ValueError, TypeError):
                errors.append('Valid duration in seconds is required for timed format.')

        passage = Passage.query.get(passage_id)
        if not passage:
            errors.append('Please select a valid passage.')

        try:
            min_acc_val = float(min_accuracy)
        except ValueError:
            min_acc_val = 0.0

        limit_val = None
        if participant_limit and participant_limit.strip():
            try:
                limit_val = int(participant_limit)
            except ValueError:
                errors.append('Participant limit must be an integer.')

        scheduled_dt = None
        if scheduled_start:
            try:
                scheduled_dt = datetime.fromisoformat(scheduled_start)
                if scheduled_dt.tzinfo is None:
                    scheduled_dt = scheduled_dt.replace(tzinfo=timezone.utc)
            except ValueError:
                errors.append('Invalid scheduled start time.')

        if errors:
            for err in errors:
                flash(err, 'danger')
            passages = Passage.query.filter_by(is_active=True).all()
            return render_template('admin/competition_form.html', competition=comp, passages=passages, is_edit=True)

        comp.title = title
        comp.description = description
        comp.format = comp_format
        comp.duration_seconds = duration_val
        comp.passage_id = passage.id
        comp.min_accuracy = min_acc_val
        comp.participant_limit = limit_val
        comp.scheduled_start_time = scheduled_dt
        db.session.commit()

        flash('Competition updated successfully.', 'success')
        return redirect(url_for('admin.dashboard'))

    passages = Passage.query.filter_by(is_active=True).all()
    return render_template('admin/competition_form.html', competition=comp, passages=passages, is_edit=True)


@admin_bp.route('/competitions/<int:comp_id>/start', methods=['POST'])
def start_competition_manually(comp_id):
    """Manually trigger start of competition."""
    comp = Competition.query.get_or_404(comp_id)
    if comp.status != 'scheduled':
        flash('Competition cannot be started because it is not in scheduled state.', 'warning')
        return redirect(url_for('admin.dashboard'))

    comp.status = 'in_progress'
    comp.actual_start_time = utcnow()
    db.session.commit()
    flash(f'Competition "{comp.title}" has officially started!', 'success')
    return redirect(url_for('admin.view_competition', comp_id=comp.id))


@admin_bp.route('/competitions/<int:comp_id>/finalize', methods=['POST'])
def finalize_competition(comp_id):
    """Finalize competition and mark rankings as official."""
    comp = Competition.query.get_or_404(comp_id)
    if comp.status != 'in_progress':
        flash('Only in-progress competitions can be finalized.', 'warning')
        return redirect(url_for('admin.dashboard'))

    now = utcnow()
    comp.status = 'completed'
    comp.completed_at = now

    # Finish any open attempts
    attempts = Attempt.query.filter_by(competition_id=comp.id).all()
    for att in attempts:
        if att.status == 'in_progress':
            att.status = 'completed'
            att.server_end_time = now
            start_time = att.server_start_time
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            if not att.elapsed_seconds:
                att.elapsed_seconds = max(1.0, (now - start_time).total_seconds())

    # Rank and store ranks
    ranked = ScoringService.rank_participants(
        attempts=attempts,
        competition_format=comp.format,
        min_accuracy=comp.min_accuracy
    )
    for item in ranked:
        item['attempt'].rank = item['rank']
        item['attempt'].is_eligible_winner = item['is_eligible']

    db.session.commit()
    flash(f'Competition "{comp.title}" has been completed and finalized!', 'success')
    return redirect(url_for('competition.leaderboard', comp_id=comp.id))


@admin_bp.route('/competitions/<int:comp_id>/cancel', methods=['POST'])
def cancel_competition(comp_id):
    """Cancel a competition."""
    comp = Competition.query.get_or_404(comp_id)
    if comp.status == 'completed':
        flash('Cannot cancel an already completed competition.', 'danger')
        return redirect(url_for('admin.dashboard'))

    comp.status = 'cancelled'
    db.session.commit()
    flash(f'Competition "{comp.title}" was cancelled.', 'info')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/competitions/<int:comp_id>')
def view_competition(comp_id):
    """Admin view of a specific competition."""
    comp = Competition.query.get_or_404(comp_id)
    participants = CompetitionParticipant.query.filter_by(competition_id=comp.id).all()
    attempts = Attempt.query.filter_by(competition_id=comp.id).all()

    ranked = ScoringService.rank_participants(
        attempts=attempts,
        competition_format=comp.format,
        min_accuracy=comp.min_accuracy
    )

    return render_template(
        'admin/competition_detail.html',
        competition=comp,
        participants=participants,
        ranked=ranked
    )


@admin_bp.route('/competitions/<int:comp_id>/export_csv')
def export_csv(comp_id):
    """Export competition leaderboard and attempt details as CSV."""
    comp = Competition.query.get_or_404(comp_id)
    attempts = Attempt.query.filter_by(competition_id=comp.id).all()

    ranked = ScoringService.rank_participants(
        attempts=attempts,
        competition_format=comp.format,
        min_accuracy=comp.min_accuracy
    )

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        'Rank',
        'Username',
        'Email',
        'WPM',
        'Accuracy (%)',
        'Elapsed Seconds',
        'Completed Passage',
        'Correct Keystrokes',
        'Total Scored Keystrokes',
        'Incorrect Attempts',
        'Backspaces',
        'Eligible Winner',
        'Winner',
        'Status',
        'Suspicious Flag',
        'Suspicious Reason'
    ])

    for item in ranked:
        att = item['attempt']
        user = att.user
        writer.writerow([
            item['rank'] if item['rank'] else 'N/A',
            user.username if user else 'Anonymous',
            user.email if user else 'N/A',
            att.wpm,
            att.accuracy,
            round(att.elapsed_seconds, 2),
            'Yes' if att.is_completed else 'No',
            att.correct_chars,
            att.total_scored_keystrokes,
            att.incorrect_attempts,
            att.backspace_count,
            'Yes' if item['is_eligible'] else 'No',
            'Yes' if item['is_winner'] else 'No',
            att.status,
            'Yes' if att.suspicious_flag else 'No',
            att.suspicious_reason or ''
        ])

    csv_data = output.getvalue()
    filename = f"speedoo_competition_{comp.id}_{comp.join_code}_results.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )


@admin_bp.route('/passages/create', methods=['GET', 'POST'])
def create_passage():
    """Create a new typing passage."""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        difficulty = request.form.get('difficulty', 'medium')
        category = request.form.get('category', 'general').strip()

        if not title or not content:
            flash('Title and content are required.', 'danger')
            return render_template('admin/passage_form.html')

        p = Passage(
            title=title,
            content=content,
            difficulty=difficulty,
            category=category,
            is_active=True
        )
        db.session.add(p)
        db.session.commit()
        flash('Passage added successfully.', 'success')
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/passage_form.html')
