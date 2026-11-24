import pytest
from website import db
from website.models import Event, Round, Score, School
from test_behavior import rendered


def board(app):
    with rendered(app) as contexts:
        response = app.test_client().get('/siklab')
    assert response.status_code == 200
    return response, contexts[-1]


def test_standalone_and_unlisted(app):
    response, _ = board(app)
    assert b'Synthetic Quiz Bee' in response.data
    assert b'<nav' not in response.data and b'<footer' not in response.data
    assert b'/siklab' not in app.test_client().get('/').data
    assert b'/siklab' not in app.test_client().get('/leaderboard').data
    with app.app_context():
        db.session.get(Event, 1).is_active = False
        db.session.commit()
    assert b'Waiting for an active event' in board(app)[0].data


@pytest.mark.parametrize('mode,expected', [('per_round', [2, 1, 3]),
                                         ('cumulative', [1, 2, 3]),
                                         ('hybrid', [1, 2, 3])])
def test_active_scores_before_evaluation(app, tab, mode, expected):
    with app.app_context():
        db.session.get(Event, 1).scoring_type = mode
        db.session.get(Round, 1).is_active = False
        db.session.get(Round, 2).is_active = True
        for q in range(1, 4):
            db.session.add(Score(school_id=1, round_id=1, question_number=q, is_correct=True))
        db.session.add(Score(school_id=2, round_id=2, question_number=1, is_correct=True))
        db.session.commit()
    _, context = board(app)
    assert [r['id'] for r in context['rankings']] == expected
    before = app.test_client().get('/siklab/fragment')
    assert app.test_client().get('/siklab/fragment', headers={'If-None-Match': before.headers['ETag']}).status_code == 304
    assert tab.post('/tabulator/scoring/2/save', json={'question': 1, 'status': 'correct'}).status_code == 200
    after = app.test_client().get('/siklab/fragment', headers={'If-None-Match': before.headers['ETag']})
    assert after.status_code == 200 and before.headers['ETag'] != after.headers['ETag']


def test_final_scores_and_shared_ranks(app):
    with app.app_context():
        db.session.get(Event, 1).scoring_type = 'hybrid'
        db.session.get(Round, 1).is_active = False
        final = db.session.get(Round, 3)
        final.is_active = True
        final.participating_school_ids = '1,2'
        db.session.add(Score(school_id=1, round_id=1, question_number=1, is_correct=True))
        for sid in (1, 2):
            db.session.add(Score(school_id=sid, round_id=3, question_number=1, is_correct=True))
        db.session.commit()
    _, context = board(app)
    assert [r['points'] for r in context['rankings']] == [3, 3, 0]
    assert [r['rank'] for r in context['rankings']] == [1, 1, 3]
    with app.app_context():
        db.session.get(Round, 3).is_active = False
        db.session.commit()
    assert board(app)[1]['stage'].id == 3


def test_repeated_clincher_names_and_seven_participants(app):
    with app.app_context():
        db.session.get(Event, 1).scoring_type = 'hybrid'
        db.session.get(Round, 1).is_active = False
        final = db.session.get(Round, 3)
        final.participating_school_ids = '1,2'
        for sid in (1, 2):
            db.session.add(Score(school_id=sid, round_id=3, question_number=1, is_correct=True))
        for rid, sid in ((4, 1), (5, 2)):
            db.session.add(Round(id=rid, event_id=1, number=3, difficulty='Clincher 1',
                                points=1, total_questions=1, is_active=rid == 5,
                                participating_school_ids=str(sid)))
            db.session.flush()
            db.session.add(Score(school_id=sid, round_id=rid, question_number=1, is_correct=True))
        for sid in range(4, 8):
            db.session.add(School(id=sid, name=f'College {sid}', event_id=1))
        db.session.commit()
    response, context = board(app)
    assert len(context['rankings']) == 7
    assert context['rankings'][0]['id'] == 1
    assert b'--teams: 7' in response.data
    assert context['rankings'][1]['round_points'] == 1


@pytest.mark.parametrize('mode', ['per_round', 'cumulative', 'hybrid'])
def test_columns_follow_round_progress_and_keep_history_in_final(app, admin, tab, mode):
    with app.app_context():
        db.session.get(Event, 1).scoring_type = mode
        db.session.commit()
    assert [r.id for r in board(app)[1]['rounds']] == [1]
    # A saved wrong answer still counts as a result, even though its points are zero.
    tab.post('/tabulator/scoring/1/save', json={'question': 1, 'status': 'wrong'})
    admin.post('/admin/round/stop/1')
    assert [r.id for r in board(app)[1]['rounds']] == [1]
    admin.post('/admin/round/activate/2')
    tab.post('/tabulator/scoring/2/save', json={'question': 1, 'status': 'correct'})
    assert [r.id for r in board(app)[1]['rounds']] == [1, 2]
    admin.post('/admin/round/activate/3')
    tab.post('/tabulator/scoring/3/save', json={'question': 1, 'status': 'correct'})
    response, context = board(app)
    assert [r.id for r in context['rounds']] == [1, 2, 3]
    first = next(row for row in context['rankings'] if row['id'] == 1)
    assert first['breakdown'] == {1: 0, 2: 2, 3: 3}
    assert first['points'] == (5 if mode == 'cumulative' else 3)
    before = app.test_client().get('/siklab/fragment')
    admin.post('/admin/round/stop/3')
    assert [r.id for r in board(app)[1]['rounds']] == [1, 2, 3]
    with app.app_context():
        db.session.add(Round(id=4, event_id=1, number=3, difficulty='Clincher 1',
                            points=1, total_questions=1, participating_school_ids='1,2'))
        db.session.commit()
    assert [r.id for r in board(app)[1]['rounds']] == [1, 2, 3]
    admin.post('/admin/round/activate/4')
    fragment = app.test_client().get('/siklab/fragment', headers={'If-None-Match': before.headers['ETag']})
    assert fragment.status_code == 200 and b'Clincher 1' in fragment.data
    assert [r.id for r in board(app)[1]['rounds']] == [1, 2, 3, 4]
