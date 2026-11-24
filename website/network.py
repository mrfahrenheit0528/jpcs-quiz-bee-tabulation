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
    preview_ip=current_app.config.get('QUIZ_DIRECT_IP')
    ip=preview_ip or state.get('ip')
    stale=time.time()-state.get('updated_at',0)>20
    return {'hostname_url':f'http://{hostname}:{port}',
            'direct_url':f'http://{ip}:{port}' if ip else None,
            'discovery':('LAN preview: use the direct-IP address. Hostname discovery is not running.' if preview_ip else
                         'Host discovery status unavailable; run quiz doctor.' if stale else state.get('message','Starting discovery.')),
            'hostname_ready':not preview_ip and not stale and state.get('status')=='ready',
            'ip':ip,'interface':state.get('interface')}
