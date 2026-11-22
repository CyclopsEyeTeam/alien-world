"""GTK event watches around the private, owned Eye connection."""
import uuid
from gi.repository import GLib
from eye_process import EyeProcess
from eye_link import EyeLink
from api_ui import later

class EyeCompanion:
 def __init__(self,owner,eye_root):
  self.owner=owner;self.watch=0;self.stopping=False
  runtime=owner.world['runtime'];world=owner.world['clock']['world_id'];nonce=uuid.uuid4().hex
  cache=owner.content_cache
  self.process=EyeProcess(eye_root,owner.worker.directory/'eye',runtime,world,nonce,cache.path if cache is not None else None)
  self.link=EyeLink(self.process,runtime,world,nonce,owner.control_request,later,GLib.source_remove,content_cache=cache)
  self.link.on_retired=lambda:owner.eye_retired(self)
  self.observe_clock(owner.world['clock'],getattr(owner,'world_clock_sequence',getattr(owner,'control_seq',1)))
  self.watch=GLib.io_add_watch(self.process.socket.fileno(),GLib.IO_IN|GLib.IO_HUP|GLib.IO_ERR,self.incoming)
 def incoming(self,_fd,condition):
  try:
   for _ in range(8):
    result=self.process.receive()
    if result is None:break
    record,blob=result
    if blob is not None:raise ValueError('Eye returned unexpected image data')
    self.link.event(record)
    if record.get('event')=='neural_presented':
     receipt=self.link.presented(record)
     if receipt is not None:self.owner.neural_presented(receipt)
    if record.get('event')=='ready':
     self.observe_clock(self.owner.world['clock'],getattr(self.owner,'world_clock_sequence',getattr(self.owner,'control_seq',1)))
     self.owner.control_request('register_eye',runtime=self.link.runtime,world_id=self.link.world,eye_runtime=self.link.eye_runtime)
     self.owner.control_request('get_art',callback=self.art_reply)
    if record.get('event') in ('closed','error'):
     self.watch=0;self.owner.eye_disconnected('Private Eye closed');return False
   if condition&(GLib.IO_HUP|GLib.IO_ERR):raise EOFError()
  except (EOFError,OSError,ValueError,TypeError,KeyError):
   self.watch=0;self.owner.eye_disconnected('Private Eye disconnected');return False
  colour='Infinite Colour' if self.link.colour_backend=='infinite' else 'native ink fallback' if self.link.colour_backend=='ink' else 'colour starting'
  self.owner.eye_button.set_tooltip_text(self.link.notice+' · '+colour);return True
 def art_reply(self,reply):
  if reply.get('ok') and reply.get('result'):self.link.art(reply['result'])
 def expression(self,record):return self.link.expression(record)
 def observe_clock(self,stamp,sequence):return self.link.observe_clock(stamp,sequence)
 def stop(self,cancel_buffer=True):
  if self.stopping:return
  self.stopping=True
  if self.watch:GLib.source_remove(self.watch);self.watch=0
  self.link.close(cancel_buffer=cancel_buffer)
