from contextlib import contextmanager
from flask import template_rendered
import pytest
from website import db
from website.models import Event, Round, Score, School, User
from conftest import client_for

@contextmanager
def rendered(app):
    contexts=[]
    def record(sender, template, context, **kw): contexts.append(context)
    template_rendered.connect(record, app)
    try: yield contexts
    finally: template_rendered.disconnect(record, app)

@pytest.mark.parametrize('name,target', [('admin1','/admin/dashboard'),('tab1','/tabulator/dashboard')])
def test_login(app,name,target):
    c=app.test_client()
    assert c.post('/login',data={'username':name,'password':'bad'}).status_code==200
    assert c.post('/login',data={'username':name,'password':'test-password'}).location.endswith(target)
    assert c.get('/logout').status_code==302
    assert c.get(target).status_code==302

@pytest.mark.parametrize('path', ['/admin/dashboard','/admin/round-control','/admin/register-user','/admin/event-registration','/admin/final-results/1','/admin/final-results/pdf/1'])
def test_roles(app,tab,path):
    assert app.test_client().get(path).status_code==302
    assert tab.get(path).status_code==403
    assert client_for(app).get('/tabulator/dashboard').status_code==403

def test_answers_and_access(app,tab,admin):
    url='/tabulator/scoring/1/save'
    assert tab.post(url,json={'question':1,'status':'correct'}).json=={'ok':True}
    assert tab.post(url,json={'question':1,'status':'wrong'}).json=={'ok':True}
    assert tab.post(url,json={'question':1,'status':'wrong'}).status_code==200
    for payload in [{'question':0,'status':'correct'},{'question':4,'status':'wrong'},{'question':1,'status':'invalid'}]:
        assert tab.post(url,json=payload).status_code==400
    with app.app_context():
        assert Score.query.count()==1
        assert Score.query.one().is_correct is False
        db.session.get(Round,1).participating_school_ids='2,3'
        db.session.commit()
    assert tab.post(url,json={'question':2,'status':'correct'}).status_code==409
    assert admin.post(url,json={'question':1,'status':'correct'}).status_code==403

def test_form_lock_markup_and_round_transitions(app,tab,admin):
    html=tab.get('/tabulator/scoring/1').text
    assert 'lock-all' in html and 'lock-btn' in html and 'localStorage' in html
    assert tab.post('/tabulator/scoring/1',data={'question_1':'correct','question_2':'wrong'}).status_code==302
    assert admin.post('/admin/round/stop/1').status_code==302
    assert tab.get('/tabulator/scoring/1/status').json['open'] is False
    assert tab.post('/tabulator/scoring/1/save',json={'question':1,'status':'wrong'}).status_code==409
    assert admin.post('/admin/round/activate/2').status_code==302
    assert admin.post('/admin/round/add-question/2').status_code==302
    assert tab.get('/tabulator/scoring/2/status').json=={'open':True,'message':None,'total_questions':4}
    with app.app_context(): assert Round.query.filter_by(is_active=True).one().id==2

def test_management(app,admin):
    assert admin.post('/admin/event-registration',data={'action':'create_event','name':'Second','scoring_type':'hybrid'}).status_code==302
    assert admin.post('/admin/event/edit/2',data={'name':'Renamed'}).status_code==302
    assert admin.post('/admin/school-registration/2',data={'school_name':'School 01','tabulator_id':2}).status_code==302
    admin.post('/admin/school-registration/2',data={'school_name':'Duplicate assignment','tabulator_id':2})
    with app.app_context(): assert School.query.filter_by(event_id=2).count()==1
    admin.post('/admin/school/edit/4',data={'school_name':'Renamed school','tabulator_id':3})
    admin.post('/admin/register-user',data={'username':'new','password':'secret','role':'tabulator','first_name':'New User'})
    admin.post('/admin/user/edit/5',data={'first_name':'Updated'})
    admin.post('/admin/round-setup/2',data={'round_number':1,'difficulty':'Easy','points':1,'total_questions':5})
    admin.post('/admin/round-setup/2',data={'round_number':3,'difficulty':'Bad','points':0,'total_questions':0})
    with app.app_context():
        assert db.session.get(Event,2).name=='Renamed'
        assert db.session.get(School,4).user_id==3
        assert User.query.filter_by(username='new').one().first_name=='Updated'
        assert Round.query.filter_by(event_id=2).count()==1
    admin.post('/admin/event/delete/1')
    with app.app_context(): assert db.session.get(Event,1) is not None
    admin.post('/admin/event/delete/2')
    with app.app_context(): assert db.session.get(Event,2) is None

@pytest.mark.parametrize('mode,expected', [('per_round',[2,1,3]),('cumulative',[1,2,3]),('hybrid',[1,2,3])])
def test_round_mode_and_qualification(app,admin,mode,expected):
    with app.app_context():
        db.session.get(Event,1).scoring_type=mode
        db.session.get(Round,1).is_active=False
        db.session.get(Round,2).is_active=True
        for sid, rid, count in [(1,1,3),(2,1,0),(3,1,0),(1,2,1),(2,2,2),(3,2,0)]:
            for q in range(1,4): db.session.add(Score(school_id=sid,round_id=rid,question_number=q,is_correct=q<=count))
        db.session.commit()
    with rendered(app) as ctx: assert admin.get('/admin/round-control').status_code==200
    assert [r['school_id'] for r in ctx[-1]['live_scores']]==expected
    assert ctx[-1]['round_fully_completed']
    admin.post('/admin/round/evaluate/2')
    with app.app_context(): assert set(db.session.get(Round,3).participating_school_ids.split(','))=={'1','2'}

def test_cutoff_tie(app,admin):
    with app.app_context():
        for sid,count in [(1,3),(2,1),(3,1)]:
            for q in range(1,4): db.session.add(Score(school_id=sid,round_id=1,question_number=q,is_correct=q<=count))
        db.session.commit()
    admin.post('/admin/round/evaluate/1')
    with app.app_context():
        tb=Round.query.filter(Round.difficulty.like('Tie Breaker%')).one()
        assert tb.qualifying_count==1 and tb.participating_school_ids=='2,3'
        assert tb.number==1 and not tb.is_active

def test_hybrid_clean_slate_clincher_and_rankings(app,admin):
    with app.app_context():
        db.session.get(Event,1).scoring_type='hybrid'
        db.session.get(Round,1).is_active=False
        r=db.session.get(Round,3); r.is_active=True; r.participating_school_ids='1,2'
        for sid in [1,2]: db.session.add(Score(school_id=sid,round_id=3,question_number=1,is_correct=True))
        db.session.add(Score(school_id=3,round_id=1,question_number=1,is_correct=True))
        db.session.commit()
    admin.post('/admin/round/evaluate/3')
    with app.app_context():
        r=Round.query.filter_by(difficulty='Clincher 1').one()
        rid=r.id
        assert r.participating_school_ids=='1,2'
    admin.post(f'/admin/round/activate/{rid}')
    for user,status in [(2,'wrong'),(3,'correct')]:
        client_for(app,user).post(f'/tabulator/scoring/{rid}/save',json={'question':1,'status':status})
    assert '/final-results/1' in admin.post(f'/admin/round/evaluate/{rid}').location
    with rendered(app) as ctx: assert admin.get('/admin/final-results/1').status_code==200
    assert [r['name'] for r in ctx[-1]['rankings']]==['School 02','School 01','School 03']
    with rendered(app) as ctx: assert app.test_client().get('/leaderboard').status_code==200
    assert ctx[-1]['is_hybrid_final'] is True
    assert [r['total'] for r in ctx[-1]['rankings']]==[3,3,0]

@pytest.mark.parametrize('mode', ['per_round','cumulative','hybrid'])
def test_reports(app,admin,mode,tmp_path):
    with app.app_context(): db.session.get(Event,1).scoring_type=mode; db.session.commit()
    assert admin.get('/admin/final-results/1').status_code==200
    pdf=admin.get('/admin/final-results/pdf/1')
    assert pdf.status_code==200 and pdf.data.startswith(b'%PDF')
    import pymupdf
    doc=pymupdf.open(stream=pdf.data,filetype='pdf')
    text=''.join(p.get_text() for p in doc)
    assert len(doc)==2
    for value in ['Synthetic Quiz Bee','School 01','Certified Correct','TEST ADMINISTRATOR','TABULATOR 01','Junior Philippine Computer Society']:
        assert value in text
