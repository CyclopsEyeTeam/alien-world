"""A latest-only local sight entrance. It never creates an Alien tick."""
import json,time,hashlib,sqlite3
from collections import OrderedDict
from vision_origin import validate_vision,numeric_summary
from neural_types import validate_sensory,validate_expression,validate_presented
from world_clock import validate_stamp

class EyeLink:
 def __init__(self,process,runtime,world,eye_runtime,control,later,cancel_timer,now_ns=time.monotonic_ns,content_cache=None):
  self.process=process;self.runtime=runtime;self.world=world;self.eye_runtime=eye_runtime;self.control=control;self.later=later;self.cancel_timer=cancel_timer;self.now_ns=now_ns
  self.ready=False;self.closed=False;self.latest={};self.pending=None;self.last_seen={};self.last_capture=0;self.frame_epoch=0;self.frame_geometry=None;self.retry=None;self.notice='Starting private Eye';self.admitted=0;self.source_counts={};self.colour_backend='';self.colour_pid=None
  self.expression_latest=None;self.expression_last=None;self.last_frame_tick=None
  self.clock_latest=None;self.clock_stamp=None;self.clock_sequence=0;self.retired_clock_segments=OrderedDict()
  self.cancel_requested=False;self.cancel_ack=False;self.cancel_retry=None;self.cancel_abandoned=False;self.helper_reaped=False;self.on_retired=lambda:None
  self.content_cache=content_cache
 @property
 def can_reconnect(self):return self.closed and self.helper_reaped and self.cancel_ack and not self.cancel_abandoned
 def fields(self):return dict(runtime=self.runtime,world_id=self.world,eye_runtime=self.eye_runtime)
 def observe_clock(self,stamp,sequence):
  if self.closed:return False
  value=validate_stamp(stamp)
  if value is None or value['world_id']!=self.world or type(sequence) is not int or not 1<=sequence<2**64:raise ValueError('invalid Eye clock observation')
  if sequence<=self.clock_sequence:self._flush_outbound();return False
  self.clock_sequence=sequence
  if value['segment_id'] in self.retired_clock_segments:self._flush_outbound();return False
  previous=self.clock_stamp
  if previous is not None and previous['segment_id']==value['segment_id'] and value['tick']<=previous['tick']:self._flush_outbound();return False
  if previous is not None and previous['segment_id']!=value['segment_id']:
   self.latest.clear()
   self.retired_clock_segments[previous['segment_id']]=None
   while len(self.retired_clock_segments)>64:self.retired_clock_segments.popitem(last=False)
   if self.expression_latest is not None and self.expression_latest['stamp']['segment_id']!=value['segment_id']:self.expression_latest=None
  self.clock_stamp=value;self.clock_latest=dict(op='world_clock',runtime=self.runtime,world=self.world,eye_runtime=self.eye_runtime,seq=sequence,stamp=value)
  return self._flush_outbound()
 def _flush_outbound(self):
  if not self._send_clock():return False
  self._send_expression();return True
 def _send_clock(self):
  if self.closed or not self.ready:return False
  if self.clock_latest is None:return True
  if self.process.send(self.clock_latest):self.clock_latest=None;return True
  return False
 def expression(self,record):
  if self.closed:return False
  value=validate_expression(record)
  if value['runtime']!=self.runtime or value['world_id']!=self.world:raise ValueError('stale expression world')
  if self.clock_stamp is not None and value['stamp']['segment_id']!=self.clock_stamp['segment_id']:return False
  if value['output_id']==self.expression_last and self.expression_latest is None:return False
  self.expression_latest=value;return self._send_expression()
 def _send_expression(self):
  if not self.ready or self.closed or self.expression_latest is None:return False
  if not self._send_clock():return False
  if self.process.send(dict(op='neural_expression',record=self.expression_latest)):
   self.expression_last=self.expression_latest['output_id'];self.expression_latest=None;return True
  return False
 def presented(self,message):
  if self.closed or message.get('runtime')!=self.runtime or message.get('world')!=self.world or message.get('eye_runtime')!=self.eye_runtime:return None
  value=validate_presented(message.get('record'))
  if value['runtime']!=self.runtime or value['world_id']!=self.world or value['surface']!='eye' or value.get('eye_runtime')!=self.eye_runtime:return None
  return value
 def capture_due(self):
  now=self.now_ns()
  if self.closed or not self.ready or now-self.last_capture<2_000_000_000:return False
  self.last_capture=now;return True
 def frame(self,png,meta):
  if self.closed or not self.ready:return False
  geometry=(meta['width'],meta['height'])
  if geometry!=self.frame_geometry or (self.clock_stamp is None and self.last_frame_tick is not None and meta['tick']<self.last_frame_tick):self.frame_geometry=geometry;self.frame_epoch+=1
  self.last_frame_tick=meta['tick']
  record=dict(op='frame',runtime=self.runtime,world=self.world,seq=meta['sequence'],tick=meta['tick'],epoch=self.frame_epoch,width=meta['width'],height=meta['height'],sent_ns=meta.get('captured_ns',self.now_ns()))
  record['sensory']=validate_sensory(meta.get('neural_context',meta.get('sensory')),'own_display')
  self._flush_outbound()
  return self.process.send(record,png)
 def art(self,message):
  if self.closed or not self.ready or message.get('runtime')!=self.runtime or message.get('world_id')!=self.world:return False
  if self.content_cache is None or 'svg' in message or 'path' in message:return False
  ref=message.get('cache_ref')
  try:
   from content_cache import read_reference
   value=read_reference(self.content_cache.path,ref,self.world,kind='art.png',max_bytes=8*1024*1024)
  except (ValueError,OSError,sqlite3.Error):self.notice='Eye art cache unavailable';return False
  if value is None or not value.startswith(b'\x89PNG\r\n\x1a\n'):return False
  self.art_sequence=getattr(self,'art_sequence',0)+1
  stamp=message.get('stamp') or {}
  record=dict(op='art',runtime=self.runtime,world=self.world,seq=self.art_sequence,epoch=1,cache_ref=ref,sent_ns=self.now_ns())
  if type(stamp.get('tick')) is int:record['tick']=stamp['tick']
  return self.process.send(record,value)
 def event(self,message):
  if self.closed or message.get('runtime')!=self.runtime or message.get('world')!=self.world or message.get('eye_runtime')!=self.eye_runtime:return
  if message.get('event')=='ready':
   self.ready=True;self.colour_backend=message.get('colour_backend','');self.colour_pid=message.get('colour_pid');self.notice='Private Eye connected';self._flush_outbound();return
  if message.get('event') in ('closed','error'):self.notice='Private Eye disconnected';return
  if message.get('event')!='observation':return
  now=self.now_ns();captured=message.get('captured_ns')
  if type(captured) is not int or not 0<=now-captured<=2_500_000_000:self.notice='Stale sight omitted';return
  source=message.get('origin');seq=message.get('seq')
  if source not in ('own_display','desktop','art') or type(seq) is not int or seq<=self.last_seen.get(source,0):return
  summary=message.get('summary');text=json.dumps(summary,allow_nan=False,separators=(',',':'));numeric_summary(text)
  sensory=validate_sensory(message.get('sensory'),source)
  cache_refs={}
  if self.content_cache is not None:
   try:
    from content_cache import read_reference
    archived={}
    for key,kind in (('perception_ref','eye.perception'),('drawing_ref','eye.drawing'),('observation_ref','eye.observation')):
     ref=message.get(key);raw=read_reference(self.content_cache.path,ref,self.world,kind=kind,max_bytes=4*1024*1024)
     if raw is None:raise ValueError('missing Eye archive')
     archived[key]=json.loads(raw);cache_refs[key]=ref
    expected=dict(runtime=self.runtime,world=self.world,eye_runtime=self.eye_runtime,origin=source,seq=seq,epoch=message.get('epoch'),captured_ns=captured)
    for key in ('display_sequence','render_tick'):
     if key in message:expected[key]=message[key]
    for archived_record in archived.values():
     provenance=archived_record['provenance']
     if not isinstance(provenance,dict) or any(k not in provenance or provenance[k]!=v for k,v in expected.items()):raise ValueError('Eye archive provenance mismatch')
    observation=archived['observation_ref']
    if observation['perception_ref']!=cache_refs['perception_ref'] or observation['drawing_ref']!=cache_refs['drawing_ref'] or observation['summary']!=summary:raise ValueError('Eye archive identity mismatch')
    if validate_sensory(observation.get('sensory'),source)!=sensory:raise ValueError('Eye sensory archive mismatch')
    perception=archived['perception_ref']['perception']
   except (KeyError,TypeError,ValueError,OSError,sqlite3.Error):self.notice='Eye cache record unavailable; look omitted';return
  else:perception=message.get('perception',summary)
  digest=hashlib.sha256(json.dumps(perception,sort_keys=True,allow_nan=False,separators=(',',':')).encode()).hexdigest()
  if self.content_cache is not None and digest!=message.get('perception_hash'):self.notice='Eye archive digest mismatch';return
  metadata=dict(kind='cyclops_eye',source=source,eye_runtime=self.eye_runtime,runtime=self.runtime,world_id=self.world,sequence=seq,epoch=message.get('epoch'),perception_hash=digest,measurement='local_geometry_colour_change',semantic_verification='unknown')
  for key in ('display_sequence','render_tick'):
   if message.get(key) is not None:metadata[key]=message[key]
  vision=validate_vision(metadata)
  self.last_seen[source]=seq;self.latest[source]=dict(text=text,vision=vision,sensory=sensory,captured_ns=captured,cache_refs=cache_refs)
  self.try_submit()
 def try_submit(self):
  if self.closed or self.pending:return
  if self.retry is not None:self.cancel_timer(self.retry);self.retry=None
  now=self.now_ns()
  self.latest={s:x for s,x in self.latest.items() if 0<=now-x['captured_ns']<=2_500_000_000}
  if not self.latest:return
  source,item=min(self.latest.items(),key=lambda pair:pair[1]['captured_ns']);self.pending=item
  def result(reply):
   if self.closed:
    if reply.get('ok'):self._cancel(reply['result'].get('id'))
    return
   if reply.get('ok'):
    item['id']=reply['result']['id']
    if self.latest.get(source) is item:self.latest.pop(source,None)
    self.notice='Eye reading waiting • admission tick unknown'
   else:
    self.pending=None;self.notice='Eye buffer busy • latest unaccepted look retained';self._retry()
  try:sent=self.control('submit_eye',result,text=item['text'],vision=item['vision'],sensory=item['sensory'],runtime=self.runtime,world_id=self.world)
  except (OSError,ValueError):sent=None
  if not sent:self.pending=None;self._retry()
 def _retry(self):
  if self.closed or self.retry is not None:return
  def wake():self.retry=None;self.try_submit()
  self.retry=self.later(.5,wake)
 def receipt(self,message):
  if self.closed or not self.pending or message.get('runtime')!=self.runtime or message.get('world_id')!=self.world or message.get('eye_runtime')!=self.eye_runtime:return
  receipt=message.get('result',{});vision=self.pending['vision']
  if message.get('sequence')!=vision['sequence'] or message.get('source')!=vision['source']:return
  if receipt.get('state')=='consumed':
   self.admitted+=1;self.source_counts[vision['source']]=self.source_counts.get(vision['source'],0)+1;stamp=receipt.get('admitted_stamp') or {};self.notice='Eye reading entered at tick '+str(stamp.get('tick','unknown'))
  if self.content_cache is not None and self.pending.get('cache_refs'):
   try:
    self.content_cache.append('eye.admission',dict(schema='ALIEN_EYE_ADMISSION_ARCHIVE_V1',runtime=self.runtime,world_id=self.world,eye_runtime=self.eye_runtime,source=vision['source'],sequence=vision['sequence'],vision=vision,sensory=self.pending['sensory'],cache_refs=self.pending['cache_refs'],receipt=receipt))
    self.content_cache.flush_if_due()
   except (ValueError,OSError,sqlite3.Error):self.notice='Eye admission archive unavailable'
  self.pending=None;self.try_submit()
 def _cancel(self,ident=None):
  if self.cancel_abandoned or self.cancel_requested:return self.cancel_requested
  def acknowledged(reply):
   self.cancel_ack=bool(reply.get('ok'))
   if self.cancel_ack:
    if self.cancel_retry is not None:self.cancel_timer(self.cancel_retry);self.cancel_retry=None
    if self.can_reconnect:self.on_retired()
   else:self.cancel_requested=False;self._retry_cancel()
  try:sent=self.control('cancel_eye',acknowledged,id=None,**self.fields())
  except (OSError,ValueError):sent=None
  self.cancel_requested=bool(sent)
  if not sent:self._retry_cancel()
  return sent
 def _retry_cancel(self):
  if self.cancel_abandoned or self.cancel_ack or self.cancel_retry is not None:return
  def retry():self.cancel_retry=None;self._cancel()
  self.cancel_retry=self.later(.2,retry)
 def abandon_cancel(self):
  self.cancel_abandoned=True
  if self.cancel_retry is not None:self.cancel_timer(self.cancel_retry);self.cancel_retry=None
 def close(self,cancel_buffer=True):
  if self.closed:return
  self.closed=True;self.ready=False
  if self.retry is not None:self.cancel_timer(self.retry);self.retry=None
  self.latest.clear()
  self.expression_latest=None
  self.clock_latest=None
  if cancel_buffer:self._cancel()
  else:self.abandon_cancel()
  self.process.stop();self.helper_reaped=True
  receipt=getattr(self.process,'close_receipt',None)
  self.notice='Eye disconnected • content cache did not flush' if receipt and receipt.get('cache_flushed') is False else 'Eye disconnected'
  if self.can_reconnect:self.on_retired()
