"""Disposable HTTP benchmark: 15 scorers, one admin, five viewers, concurrent PDF."""
from pathlib import Path
import sys, os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
if os.environ.get('QUIZ_BENCH_APP_ROOT'): sys.path.insert(0,os.environ['QUIZ_BENCH_APP_ROOT'])
import argparse, json, tempfile, threading, time, re, multiprocessing
from concurrent.futures import ThreadPoolExecutor
import requests
from waitress import create_server
from sqlalchemy import event as sa_event
from website import create_app, db
from website.models import Score
from conftest import populate, client_for


def serve_benchmark(config, pipe):
    app=create_app(config)
    server=create_server(app,host='127.0.0.1',port=0,threads=8)
    pipe.send(server.effective_port); pipe.close()
    server.run()

def run(out):
    out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='quiz-benchmark-') as folder:
        config={'SECRET_KEY':'benchmark-only','SQLALCHEMY_DATABASE_URI':f'sqlite:///{folder}/bench.db'}
        app=create_app(config)
        populate(app,schools=15,questions=30)
        query_counts={}
        for path in ['/leaderboard','/admin/round-control','/tabulator/dashboard']:
            count=[]
            def record(*args): count.append(1)
            with app.app_context():
                sa_event.listen(db.engine,'before_cursor_execute',record)
                c=client_for(app,2 if 'tabulator' in path else 1)
                response=c.get(path)
                sa_event.remove(db.engine,'before_cursor_execute',record)
            query_counts[path]={'queries':len(count),'bytes':len(response.data)}
        context=multiprocessing.get_context('spawn')
        receiving,sending=context.Pipe(duplex=False)
        process=context.Process(target=serve_benchmark,args=(config,sending),daemon=True)
        process.start(); sending.close()
        if not receiving.poll(30): raise RuntimeError('Benchmark server did not start')
        base=f'http://127.0.0.1:{receiving.recv()}'
        receiving.close()
        clients=[]
        for uid in range(1,17):
            session=requests.Session()
            with client_for(app,uid) as c: session.cookies.set('session',c.get_cookie('session').value)
            clients.append(session)
        done=threading.Event(); barrier=threading.Barrier(15); latencies=[]; polls=[]; errors=[]
        fragment='/leaderboard/fragment' if any(r.rule=='/leaderboard/fragment' for r in app.url_map.iter_rules()) else '/leaderboard'
        def reader(admin=False):
            session=clients[0] if admin else requests.Session()
            path=('/admin/round-control/fragment' if fragment.endswith('fragment') else '/admin/round-control') if admin else fragment
            etag=None
            while not done.is_set():
                t=time.perf_counter()
                try:
                    res=session.get(base+path,headers={'If-None-Match':etag} if etag else {},timeout=30)
                    if res.status_code not in (200,304): errors.append(f'poll:{res.status_code}')
                    etag=res.headers.get('ETag'); polls.append(time.perf_counter()-t)
                except Exception as e: errors.append(str(e))
                done.wait(1)
        def scorer(index):
            session=clients[index+1]; barrier.wait()
            for q in range(1,31):
                t=time.perf_counter()
                res=session.post(base+'/tabulator/scoring/1/save',json={'question':q,'status':'correct' if (index+q)%3 else 'wrong'},timeout=60)
                latencies.append(time.perf_counter()-t)
                if res.status_code!=200: errors.append(f'save:{res.status_code}:{res.text[:120]}')
            # An edit and idempotent retry exercise the same natural key.
            for status in ['wrong','correct','correct']:
                res=session.post(base+'/tabulator/scoring/1/save',json={'question':1,'status':status},timeout=60)
                if res.status_code!=200: errors.append(f'edit:{res.status_code}')
        def pdf():
            time.sleep(.15); t=time.perf_counter()
            response=clients[0].get(base+'/admin/final-results/pdf/1',timeout=180)
            elapsed=time.perf_counter()-t
            if response.status_code!=200: errors.append(f'pdf:{response.status_code}')
            (out/'report-under-load.pdf').write_bytes(response.content)
            return elapsed
        start=time.perf_counter()
        with ThreadPoolExecutor(max_workers=22) as pool:
            readers=[pool.submit(reader,i==0) for i in range(6)]
            pdf_job=pool.submit(pdf)
            writers=[pool.submit(scorer,i) for i in range(15)]
            try:
                for job in writers: job.result()
                pdf_time=pdf_job.result()
            finally:
                done.set()
            for job in readers: job.result()
        t=time.perf_counter()
        final=clients[0].get(base+'/admin/final-results/pdf/1',timeout=180)
        final_time=time.perf_counter()-t
        (out/'report-final.pdf').write_bytes(final.content)
        with app.app_context():
            scores=Score.query.all()
            assert len(scores)==450
            assert all(s.is_correct==(True if s.question_number==1 else ((s.school_id-1+s.question_number)%3!=0)) for s in scores)
            db.session.remove()
        board=requests.get(base+'/leaderboard',timeout=10).text
        rows=re.findall(r'<tr[^>]+data-flip-key="(School \d+)"[^>]*>(.*?)</tr>',board,re.S)
        actual=[(name,int(re.search(r'class="score-value">(\d+)',html).group(1))) for name,html in rows]
        expected=[(f'School {sid:02}',sum(1 if q==1 else (sid-1+q)%3!=0 for q in range(1,31))) for sid in range(1,16)]
        expected.sort(key=lambda row:row[1],reverse=True)
        assert actual==expected, (actual,expected)
        p95=lambda items:round(sorted(items)[int(.95*(len(items)-1))]*1000,2)
        result={'separate_production_server_process':True,'scorers':15,'viewers':5,'admins':1,'saves':450,'edits_and_retries':45,'save_p95_ms':p95(latencies),'save_max_ms':round(max(latencies)*1000,2),'poll_p95_ms':p95(polls),'pdf_under_load_s':round(pdf_time,3),'pdf_after_s':round(final_time,3),'elapsed_s':round(time.perf_counter()-start,2),'query_counts':query_counts,'persisted_answers_verified':450,'standings_verified':True,'errors':errors}
        (out/'results.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result,indent=2),flush=True)
        process.terminate(); process.join(10)
        with app.app_context(): db.engine.dispose()
        assert not errors
if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,default=Path('output/verification/benchmark'))
    run(parser.parse_args().output)
