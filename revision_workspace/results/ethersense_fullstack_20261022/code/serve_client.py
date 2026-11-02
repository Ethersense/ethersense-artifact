"""LAN reference client plus loopback-only control; self-closes after 30 minutes."""
import argparse, json, subprocess, threading, time, sys
from http.server import ThreadingHTTPServer
from pathlib import Path
from probe_server import create_server, Handler

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True,type=Path)
    p.add_argument("--client-ip",required=True)
    p.add_argument("--ttl",type=int,default=1800)
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    sys.stdout=(args.out/"server_stdout.txt").open("a",encoding="utf-8",buffering=1)
    sys.stderr=(args.out/"server_stderr.txt").open("a",encoding="utf-8",buffering=1)
    lan=create_server("192.168.8.170",8766,args.out,args.client_ip)
    control=ThreadingHTTPServer(("127.0.0.1",8767),Handler)
    control.daemon_threads=True;control.state=lan.state
    thread=threading.Thread(target=control.serve_forever,kwargs={"poll_interval":.25},daemon=True)
    thread.start()
    timer=threading.Timer(args.ttl,lan.shutdown);timer.daemon=True;timer.start()
    lan.state.record("interfaces_ready",{"lan_bind":"192.168.8.170:8766","control_bind":"127.0.0.1:8767",
                                      "expires_after_seconds":args.ttl,"physical_load_started":False})
    try:lan.serve_forever(poll_interval=.25)
    finally:
        timer.cancel();lan.state.stop_requested=True;lan.state.command=None
        control.shutdown();control.server_close();lan.server_close()
        lan.state.record("server_closed",{})
        subprocess.run(["powershell.exe","-NoLogo","-NoProfile","-NonInteractive","-Command",
                        "Remove-NetFirewallRule -Name EtherSense_Fullstack_20261022 -ErrorAction SilentlyContinue"],
                       check=False,capture_output=True)
if __name__=="__main__":main()
