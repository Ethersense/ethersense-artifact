"""LAN client-service and notification instrumentation; contains no classifier results.

Run on HUGO only after connection/readiness checks. Default binding is loopback.
The browser is a reference notification client, not the project's native App.
"""
import argparse
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import ipaddress,json
from pathlib import Path
import re,threading,time
from urllib.parse import parse_qs,urlsplit
import uuid

HTML=r'''<!doctype html><meta charset="utf-8"><title>EtherSense实验客户端</title>
<h2>EtherSense实验客户端</h2>
<p>手机或电脑应已连接被测路由器Wi-Fi；测试时保持本页前台。当前页面是参考客户端。</p>
<label>目标名称 <input id="target" placeholder="填写现场真实设备"></label>
<label>外置LNA <select id="lna"><option value="unknown">未确认</option><option value="on" selected>已通电</option><option value="off">未通电</option></select></label>
<p><button onclick="labelState('off')">确认目标已关闭</button> <button onclick="labelState('on')">确认目标已开启</button></p>
<p id="status">等待编排，尚未运行负载。</p><p id="alert">尚无告警</p>
<script>
let lastCommand='',seenAlerts=new Set(),busy=false,phaseAbort=null;
const post=(path,data)=>fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}).then(async r=>{let x=await r.json();if(!r.ok)throw Error(x.error);return x});
async function labelState(state){try{let r=await post('/label',{target:document.getElementById('target').value,state:state,lna:document.getElementById('lna').value});document.getElementById('status').textContent='已记录现场状态 '+state+'，标签版本 '+r.epoch;}catch(e){document.getElementById('status').textContent=e.message}}
async function runPhase(c){busy=true;phaseAbort=new AbortController();let cutoff=setTimeout(()=>phaseAbort.abort(),c.duration_s*1000+2000);let begin=performance.now(),bytes=0,errors=0,rtts=[],hidden=document.hidden,stop=false;
 const pinger=(async()=>{while(!stop){let t=performance.now();try{let r=await fetch('/ping?nonce='+t,{cache:'no-store',signal:phaseAbort.signal});await r.text();if(!r.ok)errors++;else rtts.push(performance.now()-t);}catch(e){errors++}await new Promise(r=>setTimeout(r,200));}})();
 try{while(performance.now()-begin<c.duration_s*1000&&!phaseAbort.signal.aborted){hidden=hidden||document.hidden;if(c.offered_mbps===0){await new Promise(r=>setTimeout(r,100));continue;}try{let r=await fetch('/payload?bytes=262144&mbps='+c.offered_mbps,{cache:'no-store',signal:phaseAbort.signal});if(!r.ok)throw Error('payload');let data=await r.arrayBuffer();bytes+=data.byteLength;}catch(e){errors++;break;}}}
 finally{stop=true;await pinger;clearTimeout(cutoff);let elapsed=(performance.now()-begin)/1000;await post('/result',{command_id:c.command_id,trial_id:c.trial_id,phase:c.phase,label_epoch:c.label_epoch,payload_bytes:bytes,elapsed_s:elapsed,goodput_mbps:bytes*8/elapsed/1e6,rtt_ms:rtts,errors:errors,backgrounded:hidden});busy=false;phaseAbort=null;}}
async function poll(){try{let r=await fetch('/state',{cache:'no-store'}),s=await r.json();for(let a of s.alerts){if(seenAlerts.has(a.alert_id))continue;seenAlerts.add(a.alert_id);document.getElementById('alert').textContent=a.message;requestAnimationFrame(()=>post('/ack',{alert_id:a.alert_id,client_visibility:document.visibilityState}));}
 let c=s.command;if(!c&&busy&&phaseAbort)phaseAbort.abort();if(c&&c.command_id!==lastCommand&&!busy){lastCommand=c.command_id;document.getElementById('status').textContent=c.trial_id+' / '+c.phase+' / '+c.offered_mbps+' Mbit/s';runPhase(c).catch(e=>{busy=false;document.getElementById('status').textContent=e.message;});}}
 catch(e){document.getElementById('status').textContent='连接中断：'+e.message;}setTimeout(poll,300);}
post('/ready',{client_type:'reference_browser',visibility:document.visibilityState}).then(poll);
</script>'''

class State:
    def __init__(self,directory,client_ip,router_ip):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.log=self.directory/'probe_events.jsonl';self.lock=threading.RLock()
        self.client_ip=client_ip;self.router_ip=router_ip
        self.command=None;self.completed=set();self.alerts={};self.label=None;self.epoch=0;self.stop_requested=False;self.client_ready=None;self.client_last_poll_ns=None
        self.record('session_started',{'client_ip':client_ip,'router_ip':router_ip,'notification_client_type':'reference_browser'})
    def record(self,event,data):
        row={'event':event,'utc':datetime.now(timezone.utc).isoformat(),'host_monotonic_ns':time.perf_counter_ns(),**data}
        with self.lock:
            with self.log.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        return row

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    @property
    def state(self):return self.server.state
    def respond(self,status,data,kind='application/json; charset=utf-8'):
        content=(json.dumps(data,ensure_ascii=False) if not isinstance(data,(str,bytes)) else data)
        content=content.encode('utf-8') if isinstance(content,str) else content
        self.send_response(status);self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(content)));self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(content)
    def allowed(self):
        ip=self.client_address[0]
        return ipaddress.ip_address(ip).is_loopback or ip in (self.state.client_ip,self.state.router_ip)
    def controller(self):return ipaddress.ip_address(self.client_address[0]).is_loopback
    def do_GET(self):
        if not self.allowed():self.respond(403,{'error':'Unregistered LAN peer'});return
        route=urlsplit(self.path)
        if route.path=='/':self.respond(200,HTML,'text/html; charset=utf-8')
        elif route.path=='/ping':self.respond(200,b'OK','text/plain')
        elif route.path=='/state':
            with self.state.lock:
                if self.client_address[0]==self.state.client_ip:self.state.client_last_poll_ns=time.perf_counter_ns()
                self.respond(200,{'command':self.state.command,'label':self.state.label,'alerts':list(self.state.alerts.values())[-30:],'completed_command_ids':sorted(self.state.completed),'client_ready':self.state.client_ready,'client_last_poll_ns':self.state.client_last_poll_ns,'server_now_ns':time.perf_counter_ns()})
        elif route.path=='/payload':
            q=parse_qs(route.query)
            try:count=int(q['bytes'][0]);mbps=float(q['mbps'][0])
            except (ValueError,KeyError):self.respond(400,{'error':'Invalid payload request'});return
            if count<1 or count>1_048_576 or mbps not in (5,25):self.respond(400,{'error':'Load limit exceeded'});return
            self.send_response(200);self.send_header('Content-Type','application/octet-stream')
            self.send_header('Content-Length',str(count));self.send_header('Cache-Control','no-store');self.end_headers()
            start=time.perf_counter();sent=0;reason=None
            try:
                while sent<count:
                    if self.state.stop_requested:reason='controller_stop';self.close_connection=True;break
                    chunk=min(32768,count-sent)
                    delay=(sent+chunk)/(mbps*1e6/8)-(time.perf_counter()-start)
                    if delay>0:time.sleep(delay)
                    self.wfile.write(bytes(chunk));self.wfile.flush();sent+=chunk
            except (BrokenPipeError,ConnectionResetError,TimeoutError):reason='client_disconnected'
            self.state.record('payload',{'peer':self.client_address[0],'requested_bytes':count,'server_written_bytes':sent,'offered_mbps':mbps,'server_elapsed_s':time.perf_counter()-start,'error':reason})
        else:self.respond(404,{'error':'Unknown endpoint'})
    def do_POST(self):
        if not self.allowed():self.close_connection=True;self.respond(403,{'error':'Unregistered LAN peer'});return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<1 or length>524288:raise ValueError('Invalid request length')
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict):raise ValueError('Expected JSON object')
            path=urlsplit(self.path).path
            with self.state.lock:
                if path=='/label':
                    if not isinstance(data.get('target'),str) or not data['target'].strip():raise ValueError('Target identity required')
                    if data.get('state') not in ('off','on') or data.get('lna') not in ('off','on','unknown'):raise ValueError('Physical state required')
                    self.state.epoch+=1;self.state.label={'target':data['target'].strip(),'state':data['state'],'lna':data['lna'],'epoch':self.state.epoch}
                    self.state.record('physical_label',{'peer':self.client_address[0],**self.state.label})
                    self.respond(200,self.state.label)
                elif path=='/ready':
                    self.state.client_ready={'peer':self.client_address[0],**data};self.state.record('client_ready',self.state.client_ready);self.respond(200,{'ok':True})
                elif path=='/control':
                    if not self.controller():self.respond(403,{'error':'Local controller required'});return
                    if self.state.command and self.state.command['command_id'] not in self.state.completed:
                        self.respond(409,{'error':'Previous command incomplete; stop on the first anomaly'});return
                    if data.get('phase')=='full_pipeline' and not self.state.label:raise ValueError('No independent physical label')
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',data.get('trial_id','')):raise ValueError('Invalid trial identity')
                    if data.get('phase') not in ('baseline','capture_psd','full_pipeline'):raise ValueError('Invalid service phase')
                    if data.get('offered_mbps') not in (0,5,25) or not 0<float(data.get('duration_s',0))<=20:raise ValueError('Invalid phase load or duration')
                    command={**data,'command_id':uuid.uuid4().hex,'label_epoch':self.state.epoch,'physical_label':dict(self.state.label) if self.state.label else None}
                    command['server_started_ns']=time.perf_counter_ns();self.state.command=command;self.state.stop_requested=False
                    self.state.record('command',command);self.respond(200,command)
                elif path=='/stop':
                    if not self.controller():self.respond(403,{'error':'Local controller required'});return
                    self.state.record('stopped',{'unfinished_command':self.state.command})
                    self.state.stop_requested=True;self.state.command=None;self.respond(200,{'ok':True})
                elif path=='/result':
                    command=self.state.command
                    if not command or data.get('command_id')!=command['command_id']:raise ValueError('Result does not match active command')
                    if float(data.get('elapsed_s',0))<=0 or int(data.get('payload_bytes',-1))<0:raise ValueError('Invalid byte/time measurement')
                    record={**data,'peer':self.client_address[0],'physical_label_at_start':command['physical_label'],
                            'label_changed_during_phase':self.state.epoch!=command['label_epoch'],
                            'recomputed_goodput_mbps':int(data['payload_bytes'])*8/float(data['elapsed_s'])/1e6}
                    self.state.record('service_result',record);self.state.completed.add(command['command_id']);self.respond(200,{'ok':True})
                elif path=='/alert':
                    if not isinstance(data.get('message'),str) or not data['message']:raise ValueError('Notification text required')
                    if data.get('source_kind') not in ('actual_pipeline_live','actual_pipeline_replay','fixture'):raise ValueError('Actual origin must be stated')
                    alert={**data,'alert_id':uuid.uuid4().hex,'alert_server_received_ns':time.perf_counter_ns()}
                    self.state.alerts[alert['alert_id']]=alert;self.state.record('alert_received',alert);self.respond(200,alert)
                elif path=='/ack':
                    alert=self.state.alerts.get(data.get('alert_id'))
                    if not alert:raise ValueError('Unknown notification')
                    now=time.perf_counter_ns()
                    record={**data,'peer':self.client_address[0],'source_kind':alert['source_kind'],
                            'alert_server_to_ack_ms':(now-alert['alert_server_received_ns'])/1e6,
                            'metric_scope':'reference-browser render ACK, not independently timed physical fault onset'}
                    self.state.record('notification_ack',record);self.respond(200,record)
                else:self.respond(404,{'error':'Unknown endpoint'})
        except (ValueError,TypeError,json.JSONDecodeError) as e:self.respond(400,{'error':str(e)})

def create_server(bind,port,out,client_ip,router_ip='192.168.8.1'):
    address=ipaddress.ip_address(bind)
    if not address.is_loopback and not bind.startswith('192.168.8.'):
        raise ValueError('Bind only to loopback or the verified router LAN; no public listener')
    server=ThreadingHTTPServer((bind,port),Handler);server.daemon_threads=True
    server.state=State(out,client_ip,router_ip);return server

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bind',default='127.0.0.1');p.add_argument('--port',type=int,default=8766)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--client-ip',required=True)
    p.add_argument('--router-ip',default='192.168.8.1')
    a=p.parse_args();server=create_server(a.bind,a.port,a.out,a.client_ip,a.router_ip)
    try:server.serve_forever(poll_interval=.25)
    finally:server.server_close();server.state.record('server_closed',{})

if __name__=='__main__':main()
