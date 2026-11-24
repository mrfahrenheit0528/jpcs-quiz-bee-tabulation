"""Disposable-volume production-container checks. Requires a built jpcs-quiz:local image."""
from pathlib import Path
import sys, subprocess, tempfile, json, time, hashlib, os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import requests
from website import create_app, db
from website.migrate import backup
from conftest import populate

ROOT=Path(__file__).resolve().parents[1]
def run(*args): return subprocess.check_output(['docker',*args],text=True).strip()

def verify():
    tag=str(os.getpid()); volume='jpcs-verify-'+tag; name=volume+'-app'; restored=volume+'-restored'
    results={}
    original=hashlib.sha256((ROOT/'instance/database.db').read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='quiz-container-') as folder:
        folder=Path(folder); source=folder/'database.db'
        app=create_app({'SECRET_KEY':'fixture','SQLALCHEMY_DATABASE_URI':f'sqlite:///{folder / "live.db"}'})
        populate(app)
        with app.app_context(): db.engine.dispose()
        backup(folder/'live.db',source)
        source.chmod(0o644); folder.chmod(0o755)
        run('volume','create',volume);run('volume','create',restored)
        def manage(*args,vol=volume):
            return run('run','--rm','-v',vol+':/data','-v',str(folder)+':/fixture:ro','jpcs-quiz:local','python','-m','website.manage',*args)
        def start():
            run('run','-d','--init','--name',name,'--read-only','--tmpfs','/tmp','--cap-drop','ALL','--security-opt','no-new-privileges','-p','127.0.0.1::5000','-v',volume+':/data','jpcs-quiz:local')
            port=run('port',name,'5000/tcp').rsplit(':',1)[1]
            base='http://127.0.0.1:'+port
            for _ in range(90):
                try:
                    if requests.get(base+'/healthz',timeout=1).status_code==200: return base
                except requests.RequestException: pass
                time.sleep(.3)
            raise RuntimeError(run('logs',name))
        try:
            results['first_import']=manage('import','/fixture/database.db')
            secret=run('run','--rm','-v',volume+':/data','jpcs-quiz:local','python','-c',"from pathlib import Path; import hashlib; print(hashlib.sha256(Path('/data/session.key').read_bytes()).hexdigest())")
            results['repeat_import']=manage('import','/fixture/database.db')
            base=start(); session=requests.Session()
            response=session.post(base+'/login',data={'username':'tab1','password':'test-password'})
            assert '/tabulator/dashboard' in response.url
            assert session.post(base+'/tabulator/scoring/1/save',json={'question':1,'status':'correct'}).json()=={'ok':True}
            results['sqlite_version']=run('exec',name,'python','-c','import sqlite3; print(sqlite3.sqlite_version)')
            assert tuple(map(int,results['sqlite_version'].split('.')))>=(3,51,3)
            results['non_root_uid']=run('exec',name,'id','-u'); assert results['non_root_uid']=='10001'
            run('exec',name,'python','-m','website.manage','backup','/data/backups/verified.db')
            run('cp',name+':/data/backups/verified.db',str(folder/'verified.db'))
            run('cp',name+':/data/session.key',str(folder/'verified.session.key'))
            (folder/'verified.db').chmod(0o644); (folder/'verified.session.key').chmod(0o644)
            run('stop',name);run('rm',name)
            base=start()
            assert session.get(base+'/tabulator/dashboard',allow_redirects=False).status_code==200
            assert 'id="q1_correct" value="correct"\n                                checked' in session.get(base+'/tabulator/scoring/1').text
            new_secret=run('exec',name,'python','-c',"from pathlib import Path; import hashlib; print(hashlib.sha256(Path('/data/session.key').read_bytes()).hexdigest())")
            assert secret==new_secret
            results['recreation_preserves_answers_and_session']=True
            run('restart',name)
            base='http://127.0.0.1:'+run('port',name,'5000/tcp').rsplit(':',1)[1]
            for _ in range(30):
                try:
                    if session.get(base+'/tabulator/dashboard',allow_redirects=False,timeout=1).status_code==200: break
                except requests.RequestException: pass
                time.sleep(.3)
            else: raise AssertionError('Restart did not preserve session: '+run('logs',name))
            results['restart_preserves_session']=True
            results['restore']=manage('restore','/fixture/verified.db','--secret','/fixture/verified.session.key',vol=restored)
            restored_answer=run('run','--rm','-v',restored+':/data','jpcs-quiz:local','python','-c',"import sqlite3; print(sqlite3.connect('/data/database.db').execute('select is_correct from score where school_id=1 and question_number=1').fetchone()[0])")
            assert restored_answer=='1'
            assert hashlib.sha256((ROOT/'instance/database.db').read_bytes()).hexdigest()==original
            results['original_sha256']=original
            (ROOT/'output/verification/container.json').write_text(json.dumps(results,indent=2)+'\n')
            print(json.dumps(results,indent=2))
        finally:
            subprocess.run(['docker','rm','-f',name],capture_output=True)
            for v in [volume,restored]: subprocess.run(['docker','volume','rm',v],capture_output=True)
if __name__=='__main__': verify()
