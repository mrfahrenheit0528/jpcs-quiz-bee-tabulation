"""Start a disposable manual/browser verification event; never uses instance/database.db."""
from pathlib import Path
import argparse, sys, tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from website import create_app
from conftest import populate
from waitress import serve
def preview(database, initialize=False):
    app=create_app({'SECRET_KEY':'browser-test-only',
                    'SQLALCHEMY_DATABASE_URI':f'sqlite:///{database.as_posix()}',
                    'TEMPLATES_AUTO_RELOAD':True, 'SEND_FILE_MAX_AGE_DEFAULT':0})
    if initialize:
        populate(app,schools=15,questions=30)
    print(f'Browser fixture: {database}; test-password for admin1 / tab1..tab15',flush=True)
    serve(app,host='127.0.0.1',port=5059,threads=8)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,help='Resume an existing demo database without reseeding it.')
    args=parser.parse_args()
    if args.database:
        database=args.database.resolve()
        if not database.is_file() or database == Path('instance/database.db').resolve():
            parser.error('Choose an existing demo database, not instance/database.db.')
        preview(database)
    else:
        with tempfile.TemporaryDirectory(prefix='quiz-browser-') as folder:
            preview(Path(folder)/'fixture.db', initialize=True)
