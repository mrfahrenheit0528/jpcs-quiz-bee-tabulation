"""Start a disposable manual/browser verification event; never uses instance/database.db."""
from pathlib import Path
import sys, tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from website import create_app
from conftest import populate
from waitress import serve
if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='quiz-browser-') as folder:
        app=create_app({'SECRET_KEY':'browser-test-only','SQLALCHEMY_DATABASE_URI':f'sqlite:///{folder}/fixture.db'})
        populate(app,schools=15,questions=30)
        print(f'Disposable browser fixture: {folder}; test-password for admin1 / tab1..tab15',flush=True)
        serve(app,host='127.0.0.1',port=5059,threads=8)
