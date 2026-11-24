import os
import secrets
from .write_gate import WriteGate
from flask import Flask, jsonify, request, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError

db = SQLAlchemy()
DB_NAME = 'database.db'
login_manager = LoginManager()
login_manager.login_view = 'auth.login'

def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get('QUIZ_SECRET_KEY') or secrets.token_hex(32),
        SQLALCHEMY_DATABASE_URI=os.environ.get('QUIZ_DATABASE_URI', f'sqlite:///{DB_NAME}'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={'connect_args': {'timeout': 5}},
        SQLITE_BUSY_TIMEOUT_MS=5000,
        QUIZ_HOSTNAME=os.environ.get('QUIZ_HOSTNAME', 'jpcs-quiz.local'),
        QUIZ_PORT=int(os.environ.get('QUIZ_PORT', '5000')),
        QUIZ_NETWORK_FILE=os.environ.get('QUIZ_NETWORK_FILE', ''),
        MAX_CONTENT_LENGTH=1024*1024,
    )
    if config:
        app.config.update(config)
    db.init_app(app)
    with app.app_context():
        if db.engine.dialect.name == 'sqlite':
            @event.listens_for(db.engine, 'connect')
            def configure_sqlite(conn, _):
                conn.execute(f"PRAGMA busy_timeout={int(app.config['SQLITE_BUSY_TIMEOUT_MS'])}")
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA synchronous=FULL')
                conn.execute('PRAGMA foreign_keys=ON')
    mutation_lock = WriteGate()

    @app.before_request
    def serialize_mutations():
        # One SQLite writer; acquire before reads so saves and round controls cannot race.
        if request.method == 'POST' and request.blueprint == 'views':
            mutation_lock.acquire()
            g.quiz_mutation_lock = True

    @app.teardown_request
    def release_mutation_lock(error):
        if g.pop('quiz_mutation_lock', False):
            db.session.remove()
            mutation_lock.release()

    from .models import User
    from .views import views
    from .auth import auth
    app.register_blueprint(views)
    app.register_blueprint(auth)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(id):
        return db.session.get(User, int(id))

    @app.get('/healthz')
    def healthz():
        db.session.execute(text('SELECT 1 FROM "user" LIMIT 1'))
        response=jsonify(status='ok')
        response.headers['Cache-Control']='no-store'
        return response

    @app.errorhandler(OperationalError)
    def database_busy(error):
        db.session.rollback()
        app.logger.error('Database operation failed: %s', error)
        return jsonify(error='Database temporarily unavailable. Retry this save.'), 503, {'Retry-After':'1'}

    return app
