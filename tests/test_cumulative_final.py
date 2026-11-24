import re
import zlib
import pytest
from website import db
from website.models import Event, Round, School, Score
from conftest import client_for
from test_behavior import rendered


@pytest.mark.parametrize('cutoff', [0, 2])
def test_cumulative_final_tie_and_clincher_results(app, admin, cutoff):
    with app.app_context():
        db.session.get(Event, 1).scoring_type = 'cumulative'
        db.session.get(Round, 1).is_active = False
        final = db.session.get(Round, 3)
        final.is_active = True
        final.qualifying_count = cutoff
        # Equal totals (3) with different final scores (0 vs 3).
        for q in range(1, 4):
            db.session.add(Score(school_id=1, round_id=1, question_number=q, is_correct=True))
        db.session.add(Score(school_id=2, round_id=3, question_number=1, is_correct=True))
        db.session.commit()
    response = admin.post('/admin/round/evaluate/3')
    assert response.location.endswith('/admin/round-control')
    with app.app_context():
        clincher = Round.query.filter_by(difficulty='Clincher 1').one()
        rid = clincher.id
        assert set(clincher.participating_school_ids.split(',')) == {'1', '2'}
        assert clincher.number == 3 and clincher.points == 1
    admin.post('/admin/round/evaluate/3')
    with app.app_context():
        assert Round.query.filter_by(difficulty='Clincher 1').count() == 1
    admin.post(f'/admin/round/activate/{rid}')
    for user, status in [(2, 'correct'), (3, 'wrong')]:
        assert client_for(app, user).post(f'/tabulator/scoring/{rid}/save',
                                         json={'question': 1, 'status': status}).status_code == 200
    assert admin.post(f'/admin/round/evaluate/{rid}').location.endswith('/admin/final-results/1')
    for path in ['/siklab', '/leaderboard', '/admin/final-results/1']:
        with rendered(app) as contexts:
            assert admin.get(path).status_code == 200
        rows = contexts[-1]['rankings']
        assert [row['name'] for row in rows] == ['School 01', 'School 02', 'School 03']
        if 'ranking_score' in rows[0]:
            assert [row['ranking_score'] for row in rows] == [3, 3, 0]
        else:
            assert [row['total'] if 'total' in row else row['points'] for row in rows] == [3, 3, 0]
    pdf = admin.get('/admin/final-results/pdf/1')
    assert pdf.status_code == 200
    streams = re.findall(rb'stream\r?\n(.*?)\r?\nendstream', pdf.data, re.S)
    content = b''.join(zlib.decompress(stream) for stream in streams)
    assert b'TOTAL' in content
    assert content.index(b'School 01') < content.index(b'School 02')


def test_multiple_cumulative_final_ties_wait_for_all_clinchers(app, admin):
    with app.app_context():
        db.session.get(Event, 1).scoring_type = 'cumulative'
        db.session.get(Round, 1).is_active = False
        db.session.get(Round, 3).is_active = True
        db.session.add(School(id=4, name='School 04', event_id=1))
        for sid in (1, 2):
            db.session.add(Score(school_id=sid, round_id=3, question_number=1, is_correct=True))
        for sid in (3, 4):
            db.session.add(Score(school_id=sid, round_id=1, question_number=1, is_correct=True))
        db.session.commit()
    admin.post('/admin/round/evaluate/3')
    with app.app_context():
        clinchers = Round.query.filter_by(difficulty='Clincher 1').order_by(Round.id).all()
        ids = [r.id for r in clinchers]
        assert [set(r.participating_school_ids.split(',')) for r in clinchers] == [{'1', '2'}, {'3', '4'}]
    for i, rid in enumerate(ids):
        admin.post(f'/admin/round/activate/{rid}')
        with app.app_context():
            for sid in (1 + 2*i, 2 + 2*i):
                db.session.add(Score(school_id=sid, round_id=rid, question_number=1, is_correct=sid % 2 == 1))
            db.session.commit()
        response = admin.post(f'/admin/round/evaluate/{rid}')
        assert response.location.endswith('/admin/round-control' if i == 0 else '/admin/final-results/1')


def test_cumulative_no_tie_in_total_does_not_create_clincher(app, admin):
    with app.app_context():
        db.session.get(Event, 1).scoring_type = 'cumulative'
        db.session.get(Round, 1).is_active = False
        db.session.get(Round, 3).is_active = True
        # Same final scores, distinct cumulative totals.
        for sid, count in [(1, 2), (2, 1)]:
            for q in range(1, count + 1):
                db.session.add(Score(school_id=sid, round_id=1, question_number=q, is_correct=True))
        db.session.commit()
    assert admin.post('/admin/round/evaluate/3').location.endswith('/admin/final-results/1')
    with app.app_context():
        assert Round.query.count() == 3
        assert not db.session.get(Round, 3).is_active
