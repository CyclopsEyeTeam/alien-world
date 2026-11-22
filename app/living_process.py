"""Bounded, optional Living Buffer receiver. All byte work stays off the GUI.

The host supplies structural native-field format labels. Retention diagnostics
describe private receiving memory; they confer no source/time/semantic authority.
"""
import json,math,os,shutil,socket,struct,subprocess,threading,time
from pathlib import Path
from stage_metrics import StageMetrics
from protocol import Message,PacketError,source_packet,MAX_PACKET

_WORD=struct.Struct('!I')
_MAX_META=64*1024
_MAX_REPLY=MAX_PACKET+_MAX_META+4
_MAX_ORDER=2**53-1

def _resolve_node(node_path=None):
 if node_path:return str(Path(node_path).resolve())
 found=shutil.which(os.environ.get('CYCLOPS_NODE') or 'node') or shutil.which('node',path=str(Path.home()/'.local/bin'))
 return str(Path(found).resolve()) if found else 'node'

class LivingReceiver:
 def __init__(self,dispatch,on_frame,on_error,*,node_path=None,timeout=2.0):
  if not all(callable(f) for f in (dispatch,on_frame,on_error)):raise TypeError('receiver callbacks must be callable')
  if type(timeout) not in (int,float) or not math.isfinite(timeout) or not .05<=timeout<=2:raise ValueError('receiver timeout must be between .05 and 2 seconds')
  self.dispatch,self.on_frame,self.on_error=dispatch,on_frame,on_error
  self.node_path=_resolve_node(node_path);self.timeout=float(timeout)
  self.profile=StageMetrics()
  self.process=None;self.close_error=None;self._socket=None;self._thread=None;self._condition=threading.Condition()
  self._closed=False;self._started=False;self._failed=False;self._pending=None;self._inflight=False
  self._delivery=None;self._error=None;self._scheduled=False;self._last_offered=0;self._order=0
  self._stats=dict(status='not_started',offers=0,coalesced=0,processed=0,delivered=0,delivery_coalesced=0,refused=0,source_sequence=0,source_tick=0,source_generation=0,library_revision='',library_accepted_revision='',library={},error='')
 @property
 def pid(self):
  with self._condition:return self.process.pid if self.process else None
 def start(self):
  with self._condition:
   if self._closed or self._started:return False
   self._started=True;self._stats['status']='starting';self._thread=threading.Thread(target=self._run,name='alien-living-receiver',daemon=True);self._thread.start();return True
 def offer(self,message):
  """O(1) replacement of one pending immutable native Message; never socket I/O."""
  with self._condition:
   if self._closed or self._failed or not self._started:return False
   if not isinstance(message,Message) or type(message.sequence) is not int or not self._last_offered<message.sequence<2**64:
    self._stats['refused']+=1;return False
   self._last_offered=message.sequence;self._stats['offers']+=1
   if self._pending is not None:self._stats['coalesced']+=1
   self._pending=message;self._condition.notify();return True
 def statistics(self):
  with self._condition:
   # JSON diagnostics are bounded plain values; return an owned deep copy.
   result=json.loads(json.dumps(self._stats));result.update(pending=int(self._pending is not None),inflight=int(self._inflight),thread_alive=bool(self._thread and self._thread.is_alive()),child_pid=self.process.pid if self.process else 0,closed=self._closed)
   result['receiver_profile']=self.profile.snapshot();return result
 def _read(self,length,deadline):
  result=bytearray()
  while len(result)<length:
   remaining=deadline-time.monotonic()
   if remaining<=0:raise TimeoutError('Living Buffer receiver stalled')
   self._socket.settimeout(remaining);chunk=self._socket.recv(length-len(result))
   if not chunk:raise EOFError('Living Buffer receiver disconnected')
   result.extend(chunk)
  return bytes(result)
 def _reply(self,deadline):
  length=_WORD.unpack(self._read(4,deadline))[0]
  if not 4<=length<=_MAX_REPLY:raise PacketError('invalid receiver reply size')
  data=self._read(length,deadline);meta_length=_WORD.unpack_from(data)[0]
  if not 2<=meta_length<=_MAX_META or 4+meta_length>len(data):raise PacketError('invalid receiver metadata size')
  meta=json.loads(data[4:4+meta_length]);raw=data[4+meta_length:]
  if not isinstance(meta,dict) or meta.get('ok') is not True or not isinstance(meta.get('library'),dict) or not isinstance(meta.get('library_revision'),str):raise PacketError('invalid receiver acknowledgement')
  return meta,raw
 def _exchange(self,body,deadline):
  self._socket.settimeout(self.timeout);self._socket.sendall(_WORD.pack(len(body))+body)
  return self._reply(deadline)
 def _run(self):
  child_socket=None
  try:
   with self._condition:
    if self._closed:return
   parent,child_socket=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
   with self._condition:self._socket=parent
   process=subprocess.Popen([self.node_path,'--jitless','--max-old-space-size=64','--max-semi-space-size=1','--disable-wasm-trap-handler',str(Path(__file__).with_name('living_receiver.mjs')),'--fd',str(child_socket.fileno())],pass_fds=(child_socket.fileno(),),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
   with self._condition:self.process=process
   child_socket.close();child_socket=None
   ready,raw=self._reply(time.monotonic()+self.timeout)
   if ready.get('ready') is not True or ready.get('order')!=0 or raw:raise PacketError('invalid receiver startup')
   with self._condition:
    if self._closed:return
    self._stats.update(status='active',library=ready['library'],library_revision=ready['library_revision'],library_accepted_revision=ready.get('library_accepted_revision',''))
   while True:
    with self._condition:
     while self._pending is None and not self._closed and not self._failed:self._condition.wait()
     if self._closed or self._failed:return
     message=self._pending;self._pending=None;self._inflight=True;self._order+=1;order=self._order
    if order>_MAX_ORDER:raise PacketError('receiver progress counter exhausted')
    raw=source_packet(message)
    metadata=json.dumps(dict(order=order,category='native.field',pattern='AFL1:grid'),separators=(',',':')).encode('utf8')
    body=_WORD.pack(len(metadata))+metadata+raw;deadline=time.monotonic()+self.timeout
    reply,result=self.profile.call('buffer_roundtrip',self._exchange,body,deadline)
    if reply.get('order')!=order or result!=raw:raise PacketError('receiver changed native frame bytes/order')
    # Exact byte equality permits reusing the already-decoded immutable native
    # Message. Do not allocate/rasterise the cell field a second time.
    received=message
    with self._condition:
     self._inflight=False
     if self._closed:return
     self._stats.update(status='active',processed=self._stats['processed']+1,source_sequence=received.sequence,source_tick=received.tick,source_generation=received.generation,library=reply['library'],library_revision=reply['library_revision'])
    self._publish(received)
  except Exception as error:
   with self._condition:
    if not self._closed:self._failed=True;self._pending=None;self._inflight=False;self._stats.update(status='native_fallback',error=type(error).__name__)
   self._publish(error='Living Buffer unavailable; native display retained')
  finally:
   if child_socket:child_socket.close()
   with self._condition:connection=self._socket;self._socket=None;process=self.process
   if connection:connection.close()
   if process:
    if process.poll() is None:process.terminate()
    try:process.wait(timeout=.5)
    except subprocess.TimeoutExpired:
     process.kill();process.wait(timeout=.5)
 def _publish(self,message=None,error=None):
  with self._condition:
   if self._closed:return
   if error:self._error=error;self._delivery=None
   elif not self._failed:
    if self._delivery is not None:self._stats['delivery_coalesced']+=1
    self._delivery=message
   if self._scheduled:return
   self._scheduled=True
  try:self.dispatch(self._deliver)
  except Exception:
   with self._condition:self._scheduled=False;self._failed=True;self._pending=None;self._delivery=None;self._stats.update(status='native_fallback',error='DispatcherError');self._condition.notify_all()
 def _deliver(self):
  with self._condition:
   self._scheduled=False
   if self._closed:return False
   message,error=self._delivery,self._error;self._delivery=None;self._error=None
   if message is not None:self._stats['delivered']+=1
  if error:self.on_error(error)
  elif message is not None:self.on_frame(message)
  return False
 def close(self):
  with self._condition:
   if self._closed:return
   self._closed=True;self._pending=None;self._inflight=False;self._delivery=None;self._error=None;self._condition.notify_all();connection=self._socket;process=self.process;thread=self._thread
   self._stats['status']='closed'
  if connection:
   try:connection.shutdown(socket.SHUT_RDWR)
   except OSError:pass
  if process and process.poll() is None:
   try:process.terminate()
   except ProcessLookupError:pass
  if thread and thread is not threading.current_thread():
   thread.join(timeout=3)
   if thread.is_alive():self.close_error='Living Buffer receiver did not stop within three seconds'
