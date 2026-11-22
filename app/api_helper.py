"""Ephemeral request worker. Sensitive input arrives only on an inherited socket."""
import os,sys,socket,resource,signal,ctypes,json
def main():
 resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 # Local Mist's Node child needs a larger, still bounded address space
 # (V8 reserves about 768MiB); an inherited lower hard limit still applies.
 limit=(1024 if sys.argv[2:]==['mist'] else 128)*1024*1024
 hard=resource.getrlimit(resource.RLIMIT_AS)[1]
 if hard!=resource.RLIM_INFINITY:limit=min(limit,hard)
 resource.setrlimit(resource.RLIMIT_AS,(limit,limit))
 parent=os.getppid();ctypes.CDLL(None).prctl(1,signal.SIGTERM)
 if os.getppid()!=parent or parent==1:return
 # Reap a local Mist child before exiting on owner cancellation. That child
 # also has a parent-death guard if this process has to be killed instead.
 def cancelled(_number,_frame):raise SystemExit(0)
 signal.signal(signal.SIGTERM,cancelled);signal.signal(signal.SIGINT,cancelled)
 sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
 s=socket.socket(fileno=int(sys.argv[1]))
 try:
  from api_config import Config
  from api_http import generate
  raw=s.recv(16385)
  if len(raw)>16384:raise ValueError()
  record=json.loads(raw);config=Config(**record['config']);key=record.pop('key')
  answer=dict(ok=True,**generate(config,key));key=None
 except Exception:answer={'ok':False,'error':'Request failed; no material admitted'}
 try:s.send(json.dumps(answer,ensure_ascii=False).encode())
 except OSError:pass
 s.close()
if __name__=='__main__':main()
