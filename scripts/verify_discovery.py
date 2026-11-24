"""Host-local Avahi registration/collision/withdrawal smoke test; no firewall changes."""
from pathlib import Path
import json, os, subprocess, tempfile, time
from lan import select_lan, ROOT

results={}
with tempfile.TemporaryDirectory(prefix='quiz-mdns-') as folder:
    folder=Path(folder); lan=select_lan(); prefix=f'jpcs-verify-{os.getpid()}'
    hostname=prefix+'.local'; collision=prefix+'-collision.local'
    def start(host):
        return subprocess.Popen(['python3',str(ROOT/'scripts/discovery_linux.py')],env={**os.environ,'QUIZ_HOSTNAME':host,'QUIZ_STATE_DIR':str(folder)})
    def status(expected):
        for _ in range(40):
            try:
                state=json.loads((folder/'network.json').read_text())
                if state['status']==expected: return state
            except (OSError,ValueError): pass
            time.sleep(.25)
        raise AssertionError('No expected state '+expected+': '+(folder/'network.json').read_text())
    def stop(process):
        process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: process.kill(); process.wait()
    process=start(hostname)
    try:
        ready=status('ready')
        response=subprocess.check_output(['avahi-resolve','-4','-n',hostname],text=True,timeout=5)
        assert lan['ip'] in response
        services=subprocess.check_output(['avahi-browse','-rt','_http._tcp'],text=True,timeout=10)
        assert hostname in services
        results['address_record']=response.strip();results['http_service_present']=True
    finally: stop(process)
    status('stopped')
    time.sleep(2)  # mDNS goodbye TTL permits a brief cache-expiry grace period.
    resolved=subprocess.run(['avahi-resolve','-4','-n',hostname],text=True,capture_output=True,timeout=8)
    check=subprocess.run(['busctl','--system','call','org.freedesktop.Avahi',ready['group_path'],'org.freedesktop.Avahi.EntryGroup','GetState'],capture_output=True)
    assert check.returncode!=0, 'Avahi entry group still exists after stop'
    results['withdrawn_on_stop']=True
    results['resolver_cache_retained_after_stop']=resolved.returncode==0
    occupant=subprocess.Popen(['avahi-publish','-a','-R',collision,'192.0.2.123'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    time.sleep(1)
    process=start(collision)
    try:
        state=status('error')
        assert 'collision' in state['message'].lower()
        assert state['ip']==lan['ip']
        results['collision_detected_with_direct_ip']=True
    finally: stop(process);stop(occupant)
(ROOT/'output/verification/discovery.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
