#!/usr/bin/env python3
"""Native Avahi D-Bus companion, scoped to the selected physical LAN interface."""
import json, os, signal, socket, time
from pathlib import Path
import dbus
from lan import ROOT, config, select_lan

STATE=Path(os.environ.get('QUIZ_STATE_DIR', ROOT/'.quiz'))
STATE.mkdir(parents=True,exist_ok=True)
running=True

def stop(*_):
    global running
    running=False

def write(state):
    state['updated_at']=time.time()
    path=STATE/'network.json'; temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(state)); os.replace(temp,path)

signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
cfg=config(); previous=None; state={}; retry=0; group=None; bus=None; group_path=None
owned_ips=set()
try:
    old=json.loads((STATE/'network.json').read_text())
    if old.get('hostname')==cfg['QUIZ_HOSTNAME'] and old.get('ip'): owned_ips.add(old['ip'])
except (OSError,ValueError): pass
try:
    while running:
        try:
            lan=select_lan(cfg['QUIZ_INTERFACE'])
            if group is None:
                bus=dbus.SystemBus()
                server=dbus.Interface(bus.get_object('org.freedesktop.Avahi','/'),'org.freedesktop.Avahi.Server')
                if int(server.GetState())!=2: raise RuntimeError('Avahi is not ready; check its hostname and service status.')
                group_path=str(server.EntryGroupNew())
                group=dbus.Interface(bus.get_object('org.freedesktop.Avahi',group_path),'org.freedesktop.Avahi.EntryGroup')
                previous=None
            group_state=int(group.GetState())
            if lan!=previous or (group_state in (0,3,4) and time.time()>=retry):
                group.Reset()  # Withdraw the old A/SRV/TXT/PTR records before changing address.
                previous=lan
                state={**lan,'hostname':cfg['QUIZ_HOSTNAME'],'group_path':group_path,'status':'starting','message':'Registering hostname and HTTP service.'}
                write(state)
                index=socket.if_nametoindex(lan['interface'])
                # Avahi permits multiple local A records for a host; explicitly reject
                # an already-resolving name owned by a different address as well as probe conflicts.
                try:
                    resolved=server.ResolveHostName(dbus.Int32(index),dbus.Int32(0),cfg['QUIZ_HOSTNAME'],dbus.Int32(0),dbus.UInt32(2),timeout=2)
                    existing=str(resolved[3])
                    if existing!=lan['ip'] and existing not in owned_ips:
                        raise RuntimeError(f"Hostname collision: {cfg['QUIZ_HOSTNAME']} already resolves to {existing}.")
                except dbus.DBusException:
                    pass  # Unresolved names are normal before initial registration.
                group.AddAddress(dbus.Int32(index),dbus.Int32(0),dbus.UInt32(16),cfg['QUIZ_HOSTNAME'],lan['ip'])
                group.AddService(dbus.Int32(index),dbus.Int32(0),dbus.UInt32(0),
                    f'JPCS Quiz ({cfg["QUIZ_HOSTNAME"]})','_http._tcp','local',cfg['QUIZ_HOSTNAME'],
                    dbus.UInt16(int(cfg['QUIZ_PORT'])),dbus.Array([dbus.ByteArray(b'path=/')],signature='ay'))
                group.Commit()
                owned_ips.add(lan['ip'])
                retry=time.time()+15
                time.sleep(1)
                group_state=int(group.GetState())
            if group_state==2:
                state.update(status='ready',message='Hostname and HTTP service advertised. Test access from another device.')
            elif group_state in (3,4):
                state.update(status='error',message='Hostname/service collision or Avahi registration failure. Use direct IP; choose another hostname if this persists.')
            firewall_file=STATE/'firewall.json'
            if firewall_file.exists():
                firewall=json.loads(firewall_file.read_text())
                if firewall.get('subnet')!=lan['subnet'] or firewall.get('interface')!=lan['interface']:
                    state.update(status='warning',message='LAN interface/subnet changed. Run quiz start again to update the scoped firewall rules. Direct-IP URL has been refreshed.')
        except Exception as error:
            if group is not None:
                try: group.Reset(); group.Free()
                except dbus.DBusException: pass
            group=None; previous=None
            state={**state,'status':'error','message':'Hostname collision or discovery failure; use direct IP. '+str(error)}
            # Clear stale addresses if the LAN itself is unavailable.
            try: state.update(select_lan(cfg['QUIZ_INTERFACE']))
            except RuntimeError: state.pop('ip',None)
            (STATE/'discovery.log').write_text(state['message']+'\n')
        write(state)
        for _ in range(10):
            if not running: break
            time.sleep(.5)
finally:
    if group is not None:
        try: group.Reset(); group.Free()
        except dbus.DBusException: pass
    write({**state,'status':'stopped','message':'Discovery stopped; local resolver caches may retain records briefly.'})
