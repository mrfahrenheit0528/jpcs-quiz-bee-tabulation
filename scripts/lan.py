"""Linux physical-LAN selection shared by launcher and discovery companion."""
import ipaddress, json, os, re, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def config():
    result={'QUIZ_HOSTNAME':'jpcs-quiz.local','QUIZ_PORT':'5000','QUIZ_INTERFACE':'','QUIZ_VOLUME':'jpcs-quiz-data'}
    file=ROOT/'quiz.env'
    if file.exists():
        for line in file.read_text().splitlines():
            line=line.strip()
            if not line or line.startswith('#'): continue
            key,sep,value=line.partition('=')
            if not sep or key not in result: raise RuntimeError(f'Invalid quiz.env key: {key}')
            result[key]=value.strip()
    for key in result:
        if key in os.environ: result[key]=os.environ[key]
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.local',result['QUIZ_HOSTNAME']): raise RuntimeError('Hostname must be one lowercase DNS label ending in .local.')
    if not result['QUIZ_PORT'].isdigit() or not 1024<=int(result['QUIZ_PORT'])<=65535: raise RuntimeError('QUIZ_PORT must be 1024..65535.')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*',result['QUIZ_VOLUME']): raise RuntimeError('Invalid volume name.')
    if result['QUIZ_INTERFACE'] and not re.fullmatch(r'[a-zA-Z0-9_.:-]+',result['QUIZ_INTERFACE']): raise RuntimeError('Invalid interface name.')
    return result

def select_lan(interface=''):
    addresses=json.loads(subprocess.check_output(['ip','-j','-4','address'],text=True))
    routes=json.loads(subprocess.check_output(['ip','-j','-4','route','show','default'],text=True))
    preferred=[r['dev'] for r in sorted(routes,key=lambda r:r.get('metric',0))]
    candidates=[]
    for adapter in addresses:
        name=adapter['ifname']
        if interface and name!=interface: continue
        if not (Path('/sys/class/net')/name/'device').exists(): continue
        if adapter.get('operstate')!='UP': continue
        for a in adapter['addr_info']:
            ip=ipaddress.ip_address(a['local'])
            if a.get('scope')!='global' or ip.is_link_local or ip.is_loopback: continue
            candidates.append({'interface':name,'ip':str(ip),'subnet':str(ipaddress.ip_network(f'{ip}/{a["prefixlen"]}',strict=False))})
    if not candidates: raise RuntimeError('No active physical LAN IPv4 interface. Join the event router, or set QUIZ_INTERFACE.')
    candidates.sort(key=lambda c:preferred.index(c['interface']) if c['interface'] in preferred else 999)
    return candidates[0]
