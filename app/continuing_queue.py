"""Durable pending thoughts; dequeue follows the emitted-history barrier.

A crash can repeat a thought whose dequeue was not committed. It cannot commit
its dequeue ahead of its emitted history. No outside input is replayed here.
"""
import asyncio,re,uuid
from content_cache import CacheBusy
class ThoughtQueue:
 def __init__(self,cache):
  self.cache=cache;self.head=0;self.tail=0;self.prefix=uuid.uuid4().hex;self.held=None;self.waiting=False;self.loop=None;self.closed=False
  absent=object();s=cache.get_json('monologue.queue','v1',absent)
  if s is not absent:
   if type(s) is not dict or set(s)!={'prefix','head','tail'} or type(s['prefix']) is not str or re.fullmatch('[0-9a-f]{32}',s['prefix']) is None or type(s['head']) is not int or type(s['tail']) is not int or not 0<=s['head']<=s['tail']<2**64:raise ValueError('Saved thought queue is damaged')
   self.prefix=s['prefix'];self.head=s['head'];self.tail=s['tail']
  self._save(self.head,self.tail)
 def _save(self,head,tail):self.cache.set_json('monologue.queue','v1',dict(prefix=self.prefix,head=head,tail=tail))
 def __len__(self):return 0 if self.held is not None else self.tail-self.head
 def append(self,value):
  if self.closed:raise RuntimeError('Thought queue is closed')
  self.cache.set_json('monologue.pending',self.prefix+':'+str(self.tail),list(value))
  self._save(self.head,self.tail+1);self.tail+=1
 def pop(self,index=0):
  if self.closed or index!=0 or not self:raise IndexError('pending queue is unavailable')
  value=self.cache.get_json('monologue.pending',self.prefix+':'+str(self.head))
  if (type(value) is not list or len(value)!=6 or type(value[0]) is not str or not 1<=len(value[0])<=65536 or type(value[1]) is not str or not 1<=len(value[1])<=32 or value[2] not in ('authority','unauthority') or value[3] is not None and type(value[3]) is not bool or type(value[4]) is not bool or type(value[5]) is not int or not 0<=value[5]<2**64):raise RuntimeError('pending monologue cache unavailable or damaged')
  try:self.loop=asyncio.get_running_loop()
  except RuntimeError:self.loop=None
  self.held=dict(head=self.head,said=False,stage='reserved');return tuple(value)
 def abort(self):
  if self.held and not self.held['said']:self.held=None
 def _post(self,callback):
  if self.closed:return
  if self.loop:
   if not self.loop.is_closed():self.loop.call_soon_threadsafe(callback)
  else:callback()
 def _fence(self,callback):
  if self.waiting or self.closed:return
  self.waiting=True;held=self.held
  def done():
   def apply():
    self.waiting=False
    if self.held is held:callback()
   self._post(apply)
  def failed(_error):self._post(lambda:setattr(self,'waiting',False))
  try:
   if getattr(self.cache,'background_writer',False):self.cache.after_flush(done,failed)
   else:self.cache.flush();done()
  except (OSError,ValueError):self.waiting=False
 def finish(self):
  if self.held and not self.held['said']:
   self.held.update(said=True,stage='history');self.pump()
 def pump(self):
  if self.closed or self.waiting or not self.held or not self.held['said']:return
  self._fence(self._history_ready if self.held['stage']=='history' else self._cursor_ready)
 def _history_ready(self):
  if self.closed or not self.held:return
  try:self._save(self.held['head']+1,self.tail)
  except (OSError,ValueError):return
  self.head=self.held['head']+1;self.held['stage']='cursor';self.pump()
 def _cursor_ready(self):self.held=None
 def close(self):
  if self.closed:return
  self.closed=True
  # Shutdown may be blocking. Flush emitted history before the final cursor,
  # even if its loop callback was cancelled during native agent shutdown.
  self.cache.flush()
  if self.held and self.held['said']:
   self._save(self.held['head']+1,self.tail);self.head=self.held['head']+1
  self.cache.flush();self.held=None
