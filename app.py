import os
from datetime import datetime, timezone
from flask import Flask, render_template
from flask_login import LoginManager
from dotenv import load_dotenv

from config import Config
from models import db, User

# Load environment variables
load_dotenv()

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'warning'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)

    # Context processors
    @app.context_processor
    def inject_global_template_vars():
        return {
            'current_year': datetime.now(timezone.utc).year,
            'app_name': 'Speedoo',
            'app_tagline': 'Type fast. Compete. Win.',
            'company_name': 'PazhaTholi'
        }

    # Register blueprints
    from blueprints.auth import auth_bp
    from blueprints.practice import practice_bp
    from blueprints.competition import competition_bp
    from blueprints.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(practice_bp)
    app.register_blueprint(competition_bp)
    app.register_blueprint(admin_bp)

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    return app

if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    app.run(host=host, port=port, debug=True)

