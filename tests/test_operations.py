import hashlib, json, sqlite3, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from sqlalchemy import event
from website import create_app, db
from website.migrate import backup, migrate
from website.models import School, Round, Score
from conftest import populate, client_for
from test_behavior import rendered


def test_migration_repeat_and_duplicate_guard(tmp_path):
    source=Path('instance/database.db').resolve()
    original=hashlib.sha256(source.read_bytes()).hexdigest()
    copy=backup(source,tmp_path/'copy.db')
    saved=migrate(copy)
    assert saved and saved.exists()
    first=hashlib.sha256(copy.read_bytes()).hexdigest()
    assert migrate(copy) is None
    assert hashlib.sha256(copy.read_bytes()).hexdigest()==first
    with sqlite3.connect(copy) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0]==1
        conn.execute('DROP INDEX uq_score_answer')
        conn.execute('PRAGMA user_version=0')
        conn.execute('INSERT INTO score(round_id,school_id,question_number,is_correct) VALUES(999,999,1,1),(999,999,1,0)')
    before=hashlib.sha256(copy.read_bytes()).hexdigest()
    with pytest.raises(RuntimeError,match='Duplicate score keys'): migrate(copy)
    assert hashlib.sha256(copy.read_bytes()).hexdigest()==before
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original


def test_online_backup_and_restore(app,tmp_path,tab):
    tab.post('/tabulator/scoring/1/save',json={'question':1,'status':'correct'})
    with app.app_context():
        source=Path(db.engine.url.database)
        with db.engine.connect() as connection:
            assert connection.exec_driver_sql('PRAGMA journal_mode').scalar()=='wal'
            assert connection.exec_driver_sql('PRAGMA synchronous').scalar()==2
            assert connection.exec_driver_sql('PRAGMA busy_timeout').scalar()==5000
        saved=backup(source,tmp_path/'backup.db')
    restored=create_app({'TESTING':True,'SECRET_KEY':'restore','SQLALCHEMY_DATABASE_URI':f'sqlite:///{saved}'})
    with restored.app_context():
        assert Score.query.one().is_correct
        db.engine.dispose()


def test_fragment_conditional_auth_and_invalidation(app,admin,tab):
    for path,client in [('/leaderboard/fragment',app.test_client()),('/admin/round-control/fragment',admin),('/tabulator/dashboard/fragment',tab)]:
        response=client.get(path)
        assert response.status_code==200 and b'<html' not in response.data
        assert response.headers['ETag']
        cached=client.get(path,headers={'If-None-Match':response.headers['ETag']})
        assert cached.status_code==304 and not cached.data
    assert tab.get('/admin/round-control/fragment').status_code==403
    assert app.test_client().get('/tabulator/dashboard/fragment').status_code==302
    response=admin.get('/admin/round-control/fragment')
    tab.post('/tabulator/scoring/1/save',json={'question':1,'status':'correct'})
    changed=admin.get('/admin/round-control/fragment',headers={'If-None-Match':response.headers['ETag']})
    assert changed.status_code==200 and changed.headers['ETag']!=response.headers['ETag']


def test_query_count_constant(tmp_path):
    counts=[]
    for schools in [3,15]:
        app=create_app({'TESTING':True,'SECRET_KEY':'query-test','SQLALCHEMY_DATABASE_URI':f'sqlite:///{tmp_path}/{schools}.db'})
        populate(app,schools=schools)
        totals={}
        with app.app_context():
            for route in ['/leaderboard','/admin/round-control','/admin/final-results/1']:
                statements=[]
                def record(*args): statements.append(args[2])
                event.listen(db.engine,'before_cursor_execute',record)
                assert client_for(app).get(route).status_code==200
                event.remove(db.engine,'before_cursor_execute',record)
                totals[route]=len(statements)
            db.engine.dispose()
        counts.append(totals)
    assert counts[0]==counts[1]
    assert max(counts[1].values())<=10


def test_concurrent_upsert_and_stop(app,admin):
    def save(index):
        return client_for(app,2).post('/tabulator/scoring/1/save',json={'question':1,'status':'correct' if index%2 else 'wrong'}).status_code
    with ThreadPoolExecutor(max_workers=15) as pool: assert set(pool.map(save,range(45)))=={200}
    with app.app_context(): assert Score.query.count()==1
    admin.post('/admin/round/stop/1')
    with ThreadPoolExecutor(max_workers=15) as pool: assert set(pool.map(save,range(15)))=={409}


def test_tie_breaker_clean_winners(app,admin):
    with app.app_context():
        for sid,count in [(1,3),(2,1),(3,1)]:
            for q in range(1,4): db.session.add(Score(school_id=sid,round_id=1,question_number=q,is_correct=q<=count))
        db.session.commit()
    admin.post('/admin/round/evaluate/1')
    with app.app_context(): rid=Round.query.filter(Round.difficulty.like('Tie Breaker%')).one().id
    admin.post(f'/admin/round/activate/{rid}')
    client_for(app,3).post(f'/tabulator/scoring/{rid}/save',json={'question':1,'status':'correct'})
    client_for(app,4).post(f'/tabulator/scoring/{rid}/save',json={'question':1,'status':'wrong'})
    assert admin.post(f'/admin/round/evaluate/{rid}').status_code==302
    with app.app_context(): assert db.session.get(Round,2).participating_school_ids=='1,2'


def test_clincher_still_tied_and_iterative(app,admin):
    with app.app_context():
        db.session.add(Round(id=4,event_id=1,number=3,difficulty='Clincher 1',points=1,total_questions=1,participating_school_ids='1,2,3',qualifying_count=0,is_active=True))
        db.session.commit()
    for user in [2,3,4]: client_for(app,user).post('/tabulator/scoring/4/save',json={'question':1,'status':'wrong'})
    admin.post('/admin/round/evaluate/4')
    with app.app_context(): assert Round.query.count()==4
    client_for(app,2).post('/tabulator/scoring/4/save',json={'question':1,'status':'correct'})
    admin.post('/admin/round/evaluate/4')
    with app.app_context():
        new=Round.query.filter_by(difficulty='Clincher 2').one()
        assert new.participating_school_ids=='2,3'


def test_offline_assets_and_network(app,admin,tmp_path):
    import re
    html=admin.get('/admin/dashboard').text
    assert '<title>Admin Dashboard</title>' in html
    assert html.count('js/connection.js')==1
    assert 'http://jpcs-quiz.local:5000' in html
    for url in re.findall(r'(?:src|href)="([^"]+)"',html):
        if url.startswith('/static/'):
            assert admin.get(url).status_code==200
        assert not url.startswith(('https://cdn','https://fonts'))
    info=admin.get('/admin/connection').json
    assert info['direct_url'] is None and not info['hostname_ready']
    import time
    state=tmp_path/'network.json';state.write_text(json.dumps({'ip':'192.168.10.12','status':'ready','updated_at':time.time(),'message':'Advertised'}))
    app.config['QUIZ_NETWORK_FILE']=str(state)
    assert admin.get('/admin/connection').json['direct_url']=='http://192.168.10.12:5000'
    assert admin.get('/admin/generate-qr?target=ip').mimetype=='image/png'
    assert app.test_client().get('/healthz').json=={'status':'ok'}
