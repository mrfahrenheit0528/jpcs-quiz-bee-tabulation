"""Container data operations. All copies use SQLite's online backup API."""
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
import argparse, os, secrets, shutil, fcntl
from .migrate import backup, migrate

DATA = Path(os.environ.get('QUIZ_DATA_DIR', '/data'))

def stamp(): return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')

@contextmanager
def exclusive():
    DATA.mkdir(parents=True,exist_ok=True)
    with (DATA/'app.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Application is running. Stop it before importing/restoring or starting a second server.')
        yield

def secret():
    path=DATA/'session.key'
    if not path.exists():
        try:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f: f.write(secrets.token_hex(32))
        except FileExistsError: pass
    value=path.read_text().strip()
    if len(value)<32: raise RuntimeError('Invalid session.key; restore the original secret.')
    return value

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['import','backup','restore','check'])
    parser.add_argument('path',nargs='?'); parser.add_argument('--secret')
    args=parser.parse_args(); target=DATA/'database.db'
    if args.command=='backup':
        print(backup(target,args.path)); return
    with exclusive():
        if args.command=='import':
            if not target.exists():
                backup(args.path,DATA/'import.tmp')
                os.replace(DATA/'import.tmp',target)
            secret()
        elif args.command=='restore':
            if not args.secret: raise RuntimeError('Restore requires --secret to preserve sessions.')
            value=Path(args.secret).read_text().strip()
            if len(value)<32: raise RuntimeError('Invalid backup session secret.')
            if target.exists():
                snapshot=DATA/'backups'/f'before-restore-{stamp()}.db'
                backup(target,snapshot)
                if (DATA/'session.key').exists():
                    shutil.copyfile(DATA/'session.key',snapshot.with_suffix('.session.key'))
                    os.chmod(snapshot.with_suffix('.session.key'),0o600)
            staged=DATA/f'restore-{stamp()}.db'
            backup(args.path,staged)
            migrate(staged)  # validate before replacing anything
            for suffix in ['-wal','-shm']: Path(str(target)+suffix).unlink(missing_ok=True)
            os.replace(staged,target)
            (DATA/'session.key').write_text(value); os.chmod(DATA/'session.key',0o600)
        saved=migrate(target)
        print(f'Database ready; migration backup: {saved or "already current"}')
if __name__=='__main__': main()
