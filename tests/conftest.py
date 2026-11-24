from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from website import create_app, db
from website.models import User, Event, School, Round, Score
from werkzeug.security import generate_password_hash


def populate(app, schools=3, questions=3, mode='per_round'):
    with app.app_context():
        db.create_all()
        password = generate_password_hash('test-password')
        db.session.add(User(id=1, username='admin1', password=password, role='admin', first_name='Test Administrator'))
        db.session.add(Event(id=1, name='Synthetic Quiz Bee', is_active=True, scoring_type=mode))
        for i in range(schools):
            db.session.add(User(id=i+2, username=f'tab{i+1}', password=password, role='tabulator', first_name=f'Tabulator {i+1:02}'))
            db.session.add(School(id=i+1, name=f'School {i+1:02}', event_id=1, user_id=i+2))
        for i, name in enumerate(['Easy', 'Average', 'Final']):
            db.session.add(Round(id=i+1, event_id=1, number=i+1, difficulty=name, points=i+1,
                                 total_questions=questions, is_active=i==0, is_final=i==2, qualifying_count=2))
        db.session.commit()


@pytest.fixture
def app(tmp_path):
    app = create_app({'TESTING': True, 'SECRET_KEY': 'test-only', 'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path}/test.db'})
    populate(app)
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


def client_for(app, user=1):
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = str(user)
        session['_fresh'] = True
    return client

@pytest.fixture
def admin(app):
    return client_for(app)

@pytest.fixture
def tab(app):
    return client_for(app, 2)
