"""Own the private Eye child and a credential-free, private runtime home."""
import os,json,hashlib,shutil,socket,subprocess,sys
from pathlib import Path
from eye_ipc import send,recv

def verify_source(root):
 root=Path(root).resolve();path=root/'source-manifest.json'
 if path.stat().st_size>512*1024:raise ValueError('Eye source manifest too large')
 record=json.loads(path.read_text());files=record.get('files')
 if not isinstance(files,dict) or not 1<=len(files)<=1000:raise ValueError('Invalid Eye source manifest')
 for name,digest in files.items():
  rel=Path(name)
  if rel.is_absolute() or '..' in rel.parts:raise ValueError('Invalid Eye source path')
  p=root/rel
  if p.is_symlink() or not p.is_file() or p.stat().st_size>2*1024*1024 or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise ValueError('Eye source verification failed')
 return root

class EyeProcess:
 def __init__(self,eye_root,runtime_root,runtime,world,eye_runtime,content_cache=None):
  self.identity=dict(runtime=runtime,world=world,eye_runtime=eye_runtime);self.close_receipt=None
  eye_root=verify_source(eye_root);directory=Path(runtime_root);directory.mkdir(parents=True,exist_ok=True,mode=0o700)
  for name in ('home','state','config','cache','data'): (directory/name).mkdir(mode=0o700,exist_ok=True)
  a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);a.setblocking(False);b.setblocking(False);self.socket=a;self.closed=False
  env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1','HOME':str(directory/'home'),'XDG_STATE_HOME':str(directory/'state'),'XDG_CONFIG_HOME':str(directory/'config'),'XDG_CACHE_HOME':str(directory/'cache'),'XDG_DATA_HOME':str(directory/'data'),'GSETTINGS_BACKEND':'memory','NO_AT_BRIDGE':'1'}
  node=shutil.which(os.environ.get('CYCLOPS_NODE') or 'node')
  if node:env['CYCLOPS_NODE']=str(Path(node).resolve())
  if os.environ.get('DISPLAY'):env['DISPLAY']=os.environ['DISPLAY']
  authority=os.environ.get('XAUTHORITY')
  if not authority:
   candidate=Path.home()/'.Xauthority'
   if candidate.is_file():authority=str(candidate)
  if authority:env['XAUTHORITY']=authority
  command=[sys.executable,'-I','-B',str(Path(__file__).with_name('eye_worker.py')),'--fd',str(b.fileno()),'--eye-root',str(eye_root),'--runtime-root',str(directory),'--runtime',runtime,'--world',world,'--eye-runtime',eye_runtime]
  if content_cache is not None:command+=['--content-cache',str(content_cache)]
  try:self.process=subprocess.Popen(command,pass_fds=(b.fileno(),),env=env,cwd=directory,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
  except BaseException:a.close();raise
  finally:b.close()
 def send(self,record,blob=None):return send(self.socket,record,blob)
 def _remember_close(self,record,blob=None):
  if blob is None and record.get('event')=='closed' and type(record.get('cache_flushed')) is bool and all(record.get(key)==value for key,value in self.identity.items()):
   self.close_receipt=dict(event='closed',**self.identity,cache_flushed=record['cache_flushed'])
 def receive(self):
  item=recv(self.socket)
  if item is not None:self._remember_close(*item)
  return item
 def stop(self):
  if self.closed:return
  self.closed=True
  if self.process.poll() is None:
   try:self.send({'op':'stop'})
   except (OSError,ValueError):pass
   # Stop capture first and allow the owned archive writer to drain. A missing
   # close receipt remains unknown; forced exit cannot claim a successful save.
   try:self.process.wait(timeout=15)
   except subprocess.TimeoutExpired:
    self.process.terminate()
    try:self.process.wait(timeout=2)
    except subprocess.TimeoutExpired:
     import signal
     os.killpg(self.process.pid,signal.SIGKILL);self.process.wait(timeout=2)
  try:
   # recv closes every received descriptor, including malformed/ignored packets.
   # Bound the drain even if a broken helper left unrelated messages queued.
   for _ in range(64):
    try:
     item=recv(self.socket)
     if item is None:break
     self._remember_close(*item)
    except (EOFError,OSError):break
    except (ValueError,TypeError):continue
  finally:self.socket.close()
