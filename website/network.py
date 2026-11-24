"""Host companion state; no internet dependency and no container-IP guessing."""
from pathlib import Path
import json, time
from flask import current_app

def connection_info():
    port=current_app.config['QUIZ_PORT']; hostname=current_app.config['QUIZ_HOSTNAME']
    state={}
    try:
        state=json.loads(Path(current_app.config['QUIZ_NETWORK_FILE']).read_text())
    except (OSError,ValueError): pass
    ip=state.get('ip')
    stale=time.time()-state.get('updated_at',0)>20
    return {'hostname_url':f'http://{hostname}:{port}',
            'direct_url':f'http://{ip}:{port}' if ip else None,
            'discovery':('Host discovery status unavailable; run quiz doctor.' if stale else state.get('message','Starting discovery.')),
            'hostname_ready':not stale and state.get('status')=='ready',
            'ip':ip,'interface':state.get('interface')}
