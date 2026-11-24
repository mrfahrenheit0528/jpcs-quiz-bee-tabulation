#!/usr/bin/env python3
import hashlib, json, os, shutil, socket, subprocess, sys, time, urllib.request
from pathlib import Path
from lan import ROOT, config, select_lan

UNIT='jpcs-quiz-discovery.service'

def run(args, capture=False, check=True, **kwargs):
    result=subprocess.run(args,cwd=ROOT,text=True,capture_output=capture,check=check,**kwargs)
    return result.stdout.strip() if capture else result.returncode

def elevated(args):
    if os.geteuid()==0: return run(args)
    return run((['sudo'] if sys.stdin.isatty() else ['pkexec'])+args)

def digest():
    paths=[ROOT/'Dockerfile',ROOT/'requirements.txt',ROOT/'main.py']+sorted((ROOT/'website').rglob('*'))
    h=hashlib.sha256()
    for path in paths:
        if path.is_file() and '__pycache__' not in path.parts:
            h.update(str(path.relative_to(ROOT)).encode()); h.update(path.read_bytes())
    return h.hexdigest()

def main():
    command=sys.argv[1] if len(sys.argv)>1 else 'help'
    if command not in ['start','stop','status','doctor','logs','backup']:
        print('Usage: ./quiz {start|stop|status|doctor|logs|backup}\nConfiguration: copy quiz.env.example to quiz.env. See OPERATIONS.md.'); return
    cfg=config(); os.environ.update(cfg)
    if not shutil.which('docker'): raise RuntimeError('Docker is required. Install Docker and Compose before launch.')
    run(['docker','compose','version'],capture=True)
    info=subprocess.run(['docker','info'],text=True,capture_output=True)
    if info.returncode: raise RuntimeError('Docker daemon is unavailable to this user. Start Docker and check socket/group access.\n'+info.stderr)
    # Native Linux engine only; Desktop/remote engines cannot share this host's network.
    endpoint=run(['docker','context','inspect','--format','{{.Endpoints.docker.Host}}'],capture=True)
    if command=='start' and (not endpoint.startswith('unix://') or os.environ.get('DOCKER_HOST','').startswith(('tcp:','ssh:'))):
        raise RuntimeError('Linux launcher requires a local native Docker engine, not a remote context.')
    if command=='start' and any(value in info.stdout.lower() for value in ('rootless','docker desktop')):
        raise RuntimeError('Use a local rootful native Docker Engine for Linux host networking.')
    compose=['docker','compose','-f','compose.yaml','-f','compose.linux.yaml']
    (ROOT/'.quiz').mkdir(exist_ok=True)
    if command=='stop':
        run(['systemctl','--user','stop',UNIT],check=False)
        run(compose+['stop']); return
    if command=='logs': run(compose+['logs','--tail','100','-f']); return
    if command=='backup':
        stamp=time.strftime('%Y%m%dT%H%M%S'); name=f'jpcs-quiz-backup-{stamp}'
        destination=ROOT/'backups'/f'quiz-{stamp}.db'; destination.parent.mkdir(exist_ok=True)
        try:
            run(compose+['run','--name',name,'--no-deps','app','python','-m','website.manage','backup',f'/data/backups/{destination.name}'])
            run(['docker','cp',f'{name}:/data/backups/{destination.name}',str(destination)])
            run(['docker','cp',f'{name}:/data/session.key',str(destination.with_suffix('.session.key'))])
            os.chmod(destination,0o600); os.chmod(destination.with_suffix('.session.key'),0o600)
            print(f'Backup and session secret: {destination}')
        finally: run(['docker','rm','-f',name],check=False)
        return
    if command in ['status','doctor']:
        run(compose+['ps']); run(['systemctl','--user','status',UNIT,'--no-pager'],check=False)
        lan=select_lan(cfg['QUIZ_INTERFACE']); print(json.dumps(lan,indent=2))
        for host in ['127.0.0.1',lan['ip'],cfg['QUIZ_HOSTNAME']]:
            url=f'http://{host}:{cfg["QUIZ_PORT"]}/healthz'
            try:
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                print(url,opener.open(url,timeout=4).status)
            except Exception as e: print(url,str(e))
        if command=='doctor':
            run(['ss','-ltnp',f'sport = :{cfg["QUIZ_PORT"]}'])
            print('Local HTTP checks do not prove remote access. On another device test the direct IP first, then hostname. Check router client isolation if IP fails; multicast/mDNS if only hostname fails.')
            file=ROOT/'.quiz'/'network.json'
            if file.exists(): print(file.read_text())
            run(['ufw','status'],check=False) if shutil.which('ufw') else None
        return
    lan=select_lan(cfg['QUIZ_INTERFACE'])
    existing=run(compose+['ps','-q','app'],capture=True)
    current_port=None
    if existing:
        entries=json.loads(run(['docker','inspect','--format','{{json .Config.Env}}',existing],capture=True))
        current_port=next((v.split('=',1)[1] for v in entries if v.startswith('QUIZ_PORT=')),None)
    if not existing or current_port!=cfg['QUIZ_PORT']:
        with socket.socket() as sock:
            try: sock.bind(('0.0.0.0',int(cfg['QUIZ_PORT'])))
            except OSError: raise RuntimeError(f'Port {cfg["QUIZ_PORT"]} is already owned by another process. Use quiz doctor or choose QUIZ_PORT.')
    fingerprint=digest(); image=run(['docker','image','ls','-q','jpcs-quiz:local'],capture=True)
    cache=ROOT/'.quiz'/'image.sha256'
    if not image or not cache.exists() or cache.read_text()!=fingerprint:
        run(compose+['build']); cache.write_text(fingerprint)
    # One-shot import is guarded inside the volume. Original is mounted read-only.
    source=ROOT/'instance'
    run(compose+['run','--rm','--no-deps','-v',f'{source}:/import:ro','app','python','-m','website.manage','import','/import/database.db']) if not existing else None
    firewall=ROOT/'.quiz'/'firewall.json'
    desired={'interface':lan['interface'],'subnet':lan['subnet'],'port':cfg['QUIZ_PORT']}
    configured=json.loads(firewall.read_text()) if firewall.exists() else {}
    # Saved configuration survives reboot; start Avahi each launch without enabling boot startup.
    if configured!=desired or run(['systemctl','is-active','avahi-daemon'],capture=True,check=False)!='active' or subprocess.run(['/usr/bin/python3','-c','import dbus'],capture_output=True).returncode:
        elevated(['bash',str(ROOT/'scripts'/'setup_linux.sh'),lan['interface'],lan['subnet'],cfg['QUIZ_PORT']])
        firewall.write_text(json.dumps(desired))
    run(compose+['up','-d','--no-build','--wait','--wait-timeout','90'])
    # A transient user unit survives terminal closure and is never enabled at boot.
    run(['systemctl','--user','stop',UNIT],check=False)
    run(['systemctl','--user','reset-failed',UNIT],check=False)
    started=time.time()
    run(['systemd-run','--user','--unit',UNIT,'--collect','--property=Restart=on-failure',
         '--property=RestartSec=3',f'--working-directory={ROOT}',
         *[f'--setenv={k}={v}' for k,v in cfg.items()],'/usr/bin/python3',str(ROOT/'scripts'/'discovery_linux.py')])
    discovery='Discovery has not reported readiness; run ./quiz doctor.'
    for _ in range(24):
        try:
            state=json.loads((ROOT/'.quiz'/'network.json').read_text())
            if state.get('updated_at',0)>=started and state.get('status') in ('ready','error','warning'):
                discovery=state['message']; break
        except (OSError,ValueError): pass
        time.sleep(.5)
    print(f'HTTP server is healthy.\nHostname: http://{cfg["QUIZ_HOSTNAME"]}:{cfg["QUIZ_PORT"]}\nDirect IP: http://{lan["ip"]}:{cfg["QUIZ_PORT"]}\nDiscovery: {discovery}\nTerminal can close; run start again after reboot.')

if __name__=='__main__':
    try: main()
    except (RuntimeError,subprocess.CalledProcessError,OSError) as e: print(f'quiz: {e}',file=sys.stderr); sys.exit(1)
