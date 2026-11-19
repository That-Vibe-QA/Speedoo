import functools
import re
from flask import session, abort, request, jsonify
from flask_login import current_user

def admin_required(view_func):
    """Decorator ensuring current user is authenticated and is an admin."""
    @functools.wraps(view_func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Authentication required'}), 401
            abort(401)
        if not current_user.is_admin:
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Administrator privileges required'}), 403
            abort(403)
        return view_func(*args, **kwargs)
    return decorated_view

def sanitize_username(username: str) -> str:
    """Validate and clean username: letters, numbers, underscores only, 3-30 chars."""
    if not username:
        return ""
    clean = username.strip()
    if not re.match(r'^[a-zA-Z0-9_]{3,30}$', clean):
        return ""
    return clean

def validate_email(email: str) -> bool:
    if not email:
        return False
    return bool(re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email.strip()))

