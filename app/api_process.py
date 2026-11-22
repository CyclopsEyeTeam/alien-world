"""Own one physical helper until it exits and is reaped, even after cancellation."""
import json,socket,subprocess,sys,time,os,shutil
from dataclasses import asdict
from pathlib import Path
class RequestProcess:
 def __init__(self,config,key,deadline=None):
  self.socket,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
  self.deadline=time.monotonic()+((130 if config.provider=='mist' else 30) if deadline is None else deadline);self.killed_at=None;self.cancelled=False;self.answer=None;self.finished=False
  try:
   env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'}
   if config.provider=='mist':
    node=shutil.which(os.environ.get('CYCLOPS_NODE') or 'node') or shutil.which('node',path=str(Path.home()/'.local/bin'))
    if node:env['ALIEN_MIST_NODE']=str(Path(node).resolve())
   self.process=subprocess.Popen([sys.executable,'-I','-B',str(Path(__file__).with_name('api_helper.py')),str(child.fileno()),'mist' if config.provider=='mist' else 'network'],pass_fds=(child.fileno(),),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env)
   # Isolated Python does not import a script's siblings; helper adds its own dir.
   self.socket.send(json.dumps({'config':asdict(config),'key':key},ensure_ascii=False).encode());self.socket.setblocking(False)
  except BaseException:
   self.socket.close()
   if hasattr(self,'process'):self.process.kill();self.process.wait()
   raise
  finally:child.close()
 def cancel(self):
  self.cancelled=True
  if self.process.poll() is None and self.killed_at is None:self.process.terminate();self.killed_at=time.monotonic()
 def poll(self):
  if self.finished:return self.answer
  if time.monotonic()>=self.deadline:self.cancel()
  if self.killed_at is not None and time.monotonic()-self.killed_at>.5 and self.process.poll() is None:self.process.kill()
  if self.answer is None:
   try:
    raw=self.socket.recv(8193)
    if raw and len(raw)<=8192:self.answer=json.loads(raw)
   except (BlockingIOError,OSError,ValueError):pass
  if self.process.poll() is None:return None
  self.finished=True;self.socket.close()
  if self.cancelled or self.process.returncode or not isinstance(self.answer,dict):self.answer={'ok':False,'error':'Request cancelled or worker failed'}
  return self.answer
