"""Start a disposable manual/browser verification event; never uses instance/database.db."""
from pathlib import Path
import argparse, ipaddress, sys, tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from website import create_app
from conftest import populate
from waitress import serve
def preview(database, initialize=False, port=5059, lan_ip=None):
    app=create_app({'SECRET_KEY':'browser-test-only',
                    'SQLALCHEMY_DATABASE_URI':f'sqlite:///{database.as_posix()}',
                    'TEMPLATES_AUTO_RELOAD':True, 'SEND_FILE_MAX_AGE_DEFAULT':0,
                    'QUIZ_PORT':port, 'QUIZ_DIRECT_IP':lan_ip})
    if initialize:
        populate(app,schools=15,questions=30)
    print(f'Browser fixture: {database}; test-password for admin1 / tab1..tab15',flush=True)
    print(f'Preview: http://{lan_ip or "127.0.0.1"}:{port}',flush=True)
    serve(app,host='0.0.0.0' if lan_ip else '127.0.0.1',port=port,threads=8)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,help='Resume an existing demo database without reseeding it.')
    parser.add_argument('--port',type=int,default=5059,help='Preview HTTP port (default: 5059).')
    parser.add_argument('--lan-ip',help='This computer\'s LAN IPv4 address; enables access from other devices.')
    args=parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Port must be 1024..65535.')
    if args.lan_ip:
        try:
            address=ipaddress.IPv4Address(args.lan_ip)
            if address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast:
                raise ValueError()
        except ValueError:
            parser.error('Use this computer\'s LAN IPv4 address, not a loopback or link-local address.')
    if args.database:
        database=args.database.resolve()
        if not database.is_file() or database == Path('instance/database.db').resolve():
            parser.error('Choose an existing demo database, not instance/database.db.')
        preview(database,port=args.port,lan_ip=args.lan_ip)
    else:
        with tempfile.TemporaryDirectory(prefix='quiz-browser-') as folder:
            preview(Path(folder)/'fixture.db',initialize=True,port=args.port,lan_ip=args.lan_ip)
