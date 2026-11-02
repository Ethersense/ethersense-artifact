"""Transport for the node chosen by pick_node in this K4 session.

Point ETHERSENSE_K4_HOST, ETHERSENSE_K4_KEY, ETHERSENSE_K4_PORT and
ETHERSENSE_K4_REMOTE at your own compute node before using the helpers.
"""
import argparse
import json
import os
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
WORKSPACE=ROOT.parent.parent
HOST=os.environ.get("ETHERSENSE_K4_HOST","user@cluster.example.invalid")
KEY=os.environ.get("ETHERSENSE_K4_KEY","~/.ssh/id_ed25519")
PORT=os.environ.get("ETHERSENSE_K4_PORT","22")
REMOTE=os.environ.get("ETHERSENSE_K4_REMOTE","/tmp/ethersense_k4_20261016")
TMPDIR=os.environ.get("ETHERSENSE_K4_TMPDIR","/tmp/ethersense_k4")
OPTIONS=["-o","BatchMode=yes","-o","ConnectTimeout=12","-o","ServerAliveInterval=20"]


def ssh(command):
    subprocess.run(["ssh","-i",KEY,"-p",PORT]+OPTIONS+[HOST,command],check=True)


def scp(source,destination,recursive=False):
    subprocess.run(["scp","-i",KEY,"-P",PORT]+OPTIONS+(["-r"] if recursive else [])+[str(source),str(destination)],check=True)


def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=("check","push","run","status","pull"));a=p.parse_args()
    if a.action=="check":
        ssh("python -c 'import sys,numpy,scipy;print(sys.version);print(numpy.__version__,scipy.__version__)'")
    elif a.action=="push":
        ssh("mkdir -p "+REMOTE+"/code "+REMOTE+"/archives "+REMOTE+"/output "+TMPDIR)
        manifest=json.loads((ROOT/"source_manifest.json").read_text(encoding="utf-8"))
        for s in manifest["sources"]:
            if s["role"]!="current_descriptive" and not s.get("history_merge_approved"): continue
            path=Path(s["archive"]);path=path if path.is_absolute() else WORKSPACE/path
            scp(path,HOST+":"+REMOTE+"/archives/"+s["source_id"]+".zip")
        scp(ROOT/"data_inventory.json",HOST+":"+REMOTE+"/data_inventory.json")
        for name in ("verified_welch.py","run_remote_k4.py"):
            scp(ROOT/"code"/name,HOST+":"+REMOTE+"/code/"+name)
    elif a.action=="run":
        ssh("cd "+REMOTE+" && (nohup env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 TMPDIR="+TMPDIR+" nice -n 10 python code/run_remote_k4.py --workers 4 > run.log 2>&1 < /dev/null &)")
    elif a.action=="status": ssh("tail -n 8 "+REMOTE+"/run.log")
    elif a.action=="pull":
        scp(HOST+":"+REMOTE+"/output",ROOT,True)
        scp(HOST+":"+REMOTE+"/run.log",ROOT/"remote_run.log")


if __name__=="__main__": main()
