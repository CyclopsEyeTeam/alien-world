"""Fresh, source-separated native Eye perception. No files, model calls or commands."""
from dataclasses import replace,is_dataclass,fields
import hashlib,io,json,math,re,sqlite3,struct,time,xml.etree.ElementTree as ET
from collections import OrderedDict
import cairo
from cyclops_eye import CyclopsEye
from cyclops_eye.third_eye import ThirdEyeMind
from cyclops_eye.bend import Bend
from zilo_outside_look import SightAnalyser,ZiloOutsideLook
from eye_raster import RasterGlimpser
from neural_surface import ExpressionLayer,SensoryMetrics,retained_ancestry
from neural_types import validate_sensory,validate_expression
from world_clock import validate_stamp
MAX_PIXELS=8_388_608
MAX_AGE_NS=2_500_000_000
def native_data(value):
 """Explicit non-executable dataclass projection; this is never a resume loader."""
 remaining=[250000]
 def visit(item,depth=0):
  remaining[0]-=1
  if remaining[0]<0 or depth>32:raise ValueError('Eye drawing exceeds serialization allowance')
  if item is None or type(item) in (str,bool,int):return item
  if type(item) is float:
   if not math.isfinite(item):raise ValueError('nonfinite Eye drawing value')
   return item
  if is_dataclass(item):return {'type':type(item).__module__+'.'+type(item).__qualname__,'fields':{f.name:visit(getattr(item,f.name),depth+1) for f in fields(item)}}
  if isinstance(item,(list,tuple)):return [visit(x,depth+1) for x in item]
  if isinstance(item,dict) and all(isinstance(k,str) for k in item):return {k:visit(v,depth+1) for k,v in item.items()}
  raise ValueError('unsupported native Eye drawing value')
 return visit(value)
def encoded(value):
 raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
 if len(raw)>4*1024*1024:raise ValueError('Eye archive record exceeds allowance')
 return raw
def wipe(surface):
 if surface is not None:
  cr=cairo.Context(surface);cr.set_operator(cairo.OPERATOR_SOURCE);cr.set_source_rgba(0,0,0,0);cr.paint();surface.flush()
def decode_png(raw):
 if not isinstance(raw,bytes) or not 24<=len(raw)<=8*1024*1024 or raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR':raise ValueError('invalid image packet')
 width,height=struct.unpack('!II',raw[16:24])
 if not 2<=width<=8192 or not 2<=height<=8192 or width*height>MAX_PIXELS:raise ValueError('image dimensions exceed allowance')
 try:surface=cairo.ImageSurface.create_from_png(io.BytesIO(raw))
 except Exception:raise ValueError('image could not be decoded') from None
 if (surface.get_width(),surface.get_height())!=(width,height):raise ValueError('inconsistent image dimensions')
 return surface
def render_svg(svg):
 if not isinstance(svg,str) or not 1<=len(svg.encode())<=65536:raise ValueError('art exceeds allowance')
 if re.search(r'<!\s*(?:DOCTYPE|ENTITY)|<\?xml-stylesheet',svg,re.I):raise ValueError('external SVG declarations are not accepted')
 try:root=ET.fromstring(svg)
 except ET.ParseError:raise ValueError('invalid SVG') from None
 allowed={'svg','g','title','desc','defs','linearGradient','radialGradient','stop','clipPath','rect','circle','ellipse','line','polyline','polygon','path','text','tspan','filter','feTurbulence','feDisplacementMap'}
 if root.tag.rsplit('}',1)[-1]!='svg':raise ValueError('expected native SVG')
 for element in root.iter():
  if element.tag.rsplit('}',1)[-1] not in allowed:raise ValueError('unsupported SVG element')
  for key,value in element.attrib.items():
   if key.rsplit('}',1)[-1].lower() in ('href','src') or re.search(r'@import|(?:https?|file|data):',value,re.I):raise ValueError('external SVG references are not accepted')
   for match in re.finditer(r'url\s*\(([^)]*)\)',value,re.I):
    if not re.fullmatch(r'\s*[\'"]?#[A-Za-z_][\w.-]*[\'"]?\s*',match[1]):raise ValueError('external SVG references are not accepted')
 try:
  import gi
  gi.require_foreign('cairo');gi.require_version('GdkPixbuf','2.0');gi.require_version('Gdk','3.0')
  from gi.repository import GdkPixbuf,Gdk
  # The installed SVG pixbuf loader uses librsvg; its GI namespace is optional.
  loader=GdkPixbuf.PixbufLoader.new_with_type('svg');loader.set_size(960,540);loader.write(svg.encode());loader.close();pixbuf=loader.get_pixbuf()
  if pixbuf is None:raise ValueError()
  surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,960,540);cr=cairo.Context(surface);Gdk.cairo_set_source_pixbuf(cr,pixbuf,0,0);cr.paint()
  surface.flush();return surface
 except Exception:raise ValueError('native art could not be rendered') from None
class Source:
 def __init__(self,origin,epoch,dimensions,neural_enabled=False,evidence_epoch=None):
  self.origin=origin;self.epoch=epoch;self.dimensions=dimensions;self.neural_enabled=neural_enabled
  self.evidence_epoch=epoch if evidence_epoch is None else evidence_epoch;self.percept_sequence=0
  self.eye=CyclopsEye(ThirdEyeMind(bend=Bend()));self.scene=None;self.last_ms=-1
  self.retained_expression_ids=[];self.measurement_expression_ids=[];self._reset_measurement()
 def _reset_measurement(self):
  # Acquisition history may restart without erasing any Eye-authored drawing.
  self.sight=SightAnalyser(generation=6);self.look=ZiloOutsideLook(origin='alien.eye.'+self.origin+'.e'+str(self.epoch));self.raster=None
  self.metrics=SensoryMetrics() if self.neural_enabled else None;self.neural=None;self.measurement_expression_ids=[]
 def measure(self,surface,glimpse,captured_ns,started_ns,sensory=None):
  if sensory is not None:
   incoming=sensory['expression_ids']
   if self.measurement_expression_ids and not incoming:
    if self.evidence_epoch>=2**64-1:raise ValueError('Eye evidence epoch exhausted')
    self.evidence_epoch+=1;self._reset_measurement()
   self.measurement_expression_ids=retained_ancestry(self.measurement_expression_ids,incoming)
   self.retained_expression_ids=retained_ancestry(self.retained_expression_ids,incoming)
  ms=max(self.last_ms+1,max(0,(captured_ns-started_ns)//1_000_000));self.last_ms=ms
  if surface is not None:
   if self.raster is None:self.raster=RasterGlimpser(*self.dimensions)
   glimpse=self.raster.look(surface,ms)
  else:glimpse=replace(glimpse,time_ms=ms)
  percept=self.look.perceive(self.sight.analyse(glimpse))
  if self.neural_enabled:
   # A single bounded native producer, with monotonic sequence and epoch-qualified
   # regions, prevents stale refusal or false region continuity after a reset.
   self.percept_sequence+=1
   percept=replace(percept,sequence=self.percept_sequence,regions=tuple(replace(region,id='e'+str(self.evidence_epoch)+':'+region.id) for region in percept.regions))
  self.scene=self.eye.step(percept)
  if self.metrics is not None:self.neural=self.metrics.measure(glimpse,percept,self.sight,captured_ns)
  return percept
class EyeRuntime:
 def __init__(self,runtime,world,eye_runtime,clock=time.monotonic_ns,cache=None,neural_enabled=False,on_observation=None,on_archive_error=None):
  for value in (runtime,world,eye_runtime):
   if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{32}',value):raise ValueError('invalid Eye world identity')
  self.runtime=runtime;self.world=world;self.eye_runtime=eye_runtime;self.clock=clock;self.started_ns=clock();self.sources={};self.latest={};self.inputs={};self.sequences={};self.last_scene=None;self.last_source=None
  if cache is not None and cache.world_id!=world:raise ValueError('Eye content cache belongs to another world')
  self.cache=cache;self.cache_flushed=True
  self.on_observation=on_observation;self.on_archive_error=on_archive_error;self._pending_observation=None;self._closed=False
  self.neural_enabled=neural_enabled;self.expressions=ExpressionLayer(runtime,world);self.current_tick=0;self.field_expression_ids=[];self.expression_ancestry=OrderedDict()
  self.visible_expression_ids=[];self.evidence_epochs={}
  self.known_clock=None;self.last_clock_sequence=0;self.retired_clock_segments=OrderedDict();self.last_frame_tick=None
 @property
 def observation_pending(self):return self._pending_observation is not None
 def observe_clock(self,record):
  if not isinstance(record,dict) or set(record)!={'op','runtime','world','eye_runtime','seq','stamp'} or record['op']!='world_clock' or record['runtime']!=self.runtime or record['world']!=self.world or record['eye_runtime']!=self.eye_runtime:raise ValueError('invalid Eye clock scope')
  sequence=record['seq'];stamp=validate_stamp(record['stamp'])
  if type(sequence) is not int or not 1<=sequence<2**64 or stamp is None or stamp['world_id']!=self.world:raise ValueError('invalid Eye native clock')
  if sequence<=self.last_clock_sequence:return False
  self.last_clock_sequence=sequence
  if stamp['segment_id'] in self.retired_clock_segments:return False
  previous=self.known_clock
  if previous is not None and previous['segment_id']==stamp['segment_id'] and stamp['tick']<=self.current_tick:return False
  if previous is not None and previous['segment_id']!=stamp['segment_id']:
   self.retired_clock_segments[previous['segment_id']]=None
   while len(self.retired_clock_segments)>64:self.retired_clock_segments.popitem(last=False)
   self.expressions.current=None;self.expression_ancestry.clear()
   for _surface,pending in self.latest.values():pending['_measured']=True
   # A segment boundary resets acquisition before any intervening desktop
   # look, while preserving the Eye's own drawing and sticky ancestry.
   for origin,source in self.sources.items():
    if source.evidence_epoch>=2**64-1:raise ValueError('Eye evidence epoch exhausted')
    source.evidence_epoch+=1;source._reset_measurement();self.evidence_epochs[origin]=source.evidence_epoch
  self.known_clock=stamp;self.current_tick=stamp['tick'];return True
 def expression(self,record):
  if not self.neural_enabled:return False
  value=validate_expression(record)
  if value['runtime']!=self.runtime or value['world_id']!=self.world:raise ValueError('stale Eye expression world')
  stamp=value['stamp']
  if self.known_clock is not None and stamp['segment_id']!=self.known_clock['segment_id']:return False
  if self.known_clock is None or stamp['tick']>self.current_tick:self.known_clock=stamp;self.current_tick=stamp['tick']
  if self.current_tick>value['expires_tick']:return False
  accepted=self.expressions.offer(value)
  if accepted:
   self.expression_ancestry[record['output_id']]=record['expires_tick']
   while len(self.expression_ancestry)>8:self.expression_ancestry.popitem(last=False)
  if accepted and self.cache is not None:self.cache.append('eye.expression',dict(schema='ALIEN_EYE_EXPRESSION_LAYER_V1',record=record,eye_runtime=self.eye_runtime,phase='received'))
  return accepted
 def desktop_sensory(self):
  self.expression_ancestry=OrderedDict((key,end) for key,end in self.expression_ancestry.items() if self.current_tick<=end)
  sticky=retained_ancestry(*(source.retained_expression_ids for source in self.sources.values()))
  ids=retained_ancestry(sticky,self.visible_expression_ids,self.field_expression_ids,self.expressions.presented_ids,list(reversed(self.expression_ancestry)))
  return validate_sensory(dict(version=1,expression_ids=ids,source_scope='mixed_unknown',measurement='sampled_geometry_colour_change'),'desktop')
 def native_presented(self):
  source=self.sources.get(self.last_source)
  self.visible_expression_ids=retained_ancestry(source.retained_expression_ids if source is not None else [],self.expressions.presented_ids)
 def projection_presented(self,origin):
  item=self.latest.get(origin)
  self.visible_expression_ids=validate_sensory(item[1].get('sensory') if item is not None else None,origin)['expression_ids']
 def presented(self,record):
  if self.cache is not None:
   self.cache.append('eye.expression.presented',dict(schema='ALIEN_EYE_PRESENTED_V1',record=record));self.cache.flush_if_due()
 def _meta(self,record,origin):
  if not isinstance(record,dict) or record.get('runtime')!=self.runtime or record.get('world')!=self.world:raise ValueError('stale Eye world')
  for key in ('seq','epoch','sent_ns'):
   if type(record.get(key)) is not int or not 0<=record[key]<2**64:raise ValueError('invalid Eye sequence')
  if record['seq']<1 or not 0<=self.clock()-record['sent_ns']<=MAX_AGE_NS:raise ValueError('stale Eye capture')
  stamp=record['epoch'],record['seq']
  if origin in self.inputs and stamp<=self.inputs[origin]:raise ValueError('duplicate or old Eye capture')
  if 'tick' in record and (type(record['tick']) is not int or not 0<=record['tick']<2**64):raise ValueError('invalid render tick')
  return stamp
 def offer(self,record,blob=None):
  if not isinstance(record,dict):raise ValueError('unsupported Eye input')
  origin={'frame':'own_display','art':'art'}.get(record.get('op'))
  if not origin:raise ValueError('unsupported Eye input')
  stamp=self._meta(record,origin)
  sensory=validate_sensory(record.get('sensory'),origin)
  if origin=='art':
   from content_cache import reference_identity
   if 'svg' in record or 'path' in record:raise ValueError('art content must come from a binary cache reference')
   world,_ident,digest=reference_identity(record.get('cache_ref'))
   if world!=self.world or not isinstance(blob,bytes) or hashlib.sha256(blob).hexdigest()!=digest:raise ValueError('art pixels do not match their cache identity')
  surface=decode_png(blob)
  dimensions=surface.get_width(),surface.get_height()
  if origin=='own_display' and dimensions!=(record.get('width'),record.get('height')):wipe(surface);raise ValueError('capture geometry mismatch')
  old=self.latest.get(origin)
  if old and record['epoch']==old[1]['epoch'] and dimensions!=(old[0].get_width(),old[0].get_height()):wipe(surface);raise ValueError('geometry changed without a fresh epoch')
  saved=dict(record)
  if self.neural_enabled:saved['sensory']=sensory
  self.latest[origin]=(surface,saved);self.inputs[origin]=stamp
  if origin=='own_display':
   tick=record.get('tick',self.last_frame_tick)
   if self.known_clock is None and tick is not None and self.last_frame_tick is not None and tick<self.last_frame_tick:
    self.sources.clear();self.last_source=None;self.last_scene=None;self.expressions.current=None;self.expression_ancestry.clear()
   self.last_frame_tick=tick
   if self.known_clock is None and tick is not None:self.current_tick=tick
   self.field_expression_ids=sensory['expression_ids']
  if old:wipe(old[0])
  return origin
 def _source(self,origin,epoch,dimensions):
  source=self.sources.get(origin)
  if source is None or source.epoch!=epoch or source.dimensions!=dimensions:
   evidence=max(epoch,self.evidence_epochs.get(origin,0)+1) if self.neural_enabled else epoch
   if evidence>=2**64:raise ValueError('Eye evidence epoch exhausted')
   source=self.sources[origin]=Source(origin,epoch,dimensions,self.neural_enabled,evidence)
  self.evidence_epochs[origin]=source.evidence_epoch
  return source
 def _result(self,origin,percept,record,captured_ns,dimensions):
  self.sequences[origin]=self.sequences.get(origin,0)+1;self.last_source=origin;self.last_scene=self.sources[origin].scene
  summary={'dimensions':list(dimensions),'field':percept.field.to_dict(),'region_count':len(percept.regions),'regions':[]}
  for region in percept.regions[:4]:
   row=region.to_dict();row.pop('id');summary['regions'].append(row)
  if percept.attention is not None:summary['attention']=percept.attention.to_dict()
  if self.neural_enabled:summary['neural']=self.sources[origin].neural or {}
  native=percept.to_dict();percept_bytes=json.dumps(native,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
  if len(percept_bytes)>65536 or len(json.dumps(summary,allow_nan=False).encode())>4096:raise ValueError('Eye output exceeds allowance')
  source=self.sources[origin];self.evidence_epochs[origin]=source.evidence_epoch
  result=dict(event='observation',runtime=self.runtime,world=self.world,eye_runtime=self.eye_runtime,origin=origin,seq=self.sequences[origin],epoch=source.evidence_epoch if self.neural_enabled else record['epoch'],captured_ns=captured_ns,summary=summary,perception=native,perception_hash=hashlib.sha256(percept_bytes).hexdigest())
  if 'seq' in record:result['display_sequence']=record['seq']
  if 'tick' in record:result['render_tick']=record['tick']
  if self.neural_enabled:
   result['sensory']=validate_sensory(record.get('sensory'),origin)
   result['sensory']['expression_ids']=retained_ancestry(source.measurement_expression_ids,result['sensory']['expression_ids'])
  if self.cache is not None:
   source=self.sources[origin];key=self.eye_runtime+':'+origin
   metadata=dict(runtime=self.runtime,eye_runtime=self.eye_runtime,source=origin,sequence=result['seq'],epoch=result['epoch'],captured_ns=captured_ns)
   provenance={k:result[k] for k in ('runtime','world','eye_runtime','origin','seq','epoch','captured_ns','display_sequence','render_tick') if k in result}
   if self.neural_enabled:provenance.update(retained_expression_ids=list(source.retained_expression_ids),input_epoch=source.epoch,evidence_epoch=source.evidence_epoch)
   if record.get('cache_ref'):provenance['art_cache_ref']=record['cache_ref']
   percept_ref=self.cache.put('eye.perception',key,encoded(dict(schema='ALIEN_EYE_PERCEPTION_ARCHIVE_V1',provenance=provenance,perception=native,perception_hash=result['perception_hash'])),metadata)
   drawing_ref=self.cache.put('eye.drawing',key,encoded(self.drawing_snapshot(origin,provenance)),metadata)
   observation=dict(schema='ALIEN_EYE_OBSERVATION_ARCHIVE_V1',provenance=provenance,summary=summary,perception_hash=result['perception_hash'],perception_ref=percept_ref,drawing_ref=drawing_ref,admission_tick=None)
   if self.neural_enabled:observation['sensory']=result['sensory']
   observation_ref=self.cache.put('eye.observation',key,encoded(observation),metadata)
   result.pop('perception');result.update(perception_ref=percept_ref,drawing_ref=drawing_ref,observation_ref=observation_ref)
   if getattr(self.cache,'background_writer',False):
    # One unresolved look bounds callback state. Native drawing, presentation and
    # clock updates can continue while its immutable ancestry is committed.
    pending=dict(result=result,source=source,epoch=source.evidence_epoch,segment=self.known_clock['segment_id'] if self.known_clock else None)
    self._pending_observation=pending
    def committed():
     if self._closed or self._pending_observation is not pending:return
     self._pending_observation=None
     if self.sources.get(origin) is not source or source.evidence_epoch!=pending['epoch']:return
     # Offers keep arriving while fresh measurement waits for the writer. A
     # newer input epoch retires this look even before _source is rebuilt;
     # ordinary newer frames in the same epoch do not replace its provenance.
     if origin in self.inputs and self.inputs[origin][0]!=source.epoch:return
     if pending['segment'] is not None and (self.known_clock is None or self.known_clock['segment_id']!=pending['segment']):return
     if not 0<=self.clock()-captured_ns<=MAX_AGE_NS:return
     if self.on_observation:self.on_observation(result)
    def failed(error):
     if self._closed or self._pending_observation is not pending:return
     self._pending_observation=None
     if self.on_archive_error:self.on_archive_error(error)
    try:self.cache.after_flush(committed,failed)
    except BaseException:
     if self._pending_observation is pending:self._pending_observation=None
     raise
    return None
   self.cache.flush() # The other process must never receive an uncommitted reference.
  return result
 def drawing_snapshot(self,origin,provenance=None):
  source=self.sources[origin];state=source.eye.state
  provenance=dict(provenance or dict(runtime=self.runtime,world=self.world,eye_runtime=self.eye_runtime,origin=origin,epoch=source.evidence_epoch),input_epoch=source.epoch,evidence_epoch=source.evidence_epoch,retained_expression_ids=list(source.retained_expression_ids),drawing_scope='self')
  return dict(schema='ALIEN_EYE_NATIVE_DRAWING_ARCHIVE_V1',resume='snapshot_only_not_full_resume',provenance=provenance,source_scope='self',retained_expression_ids=list(source.retained_expression_ids),eye_tick=state.tick,scene=native_data(source.scene),retained={name:native_data(getattr(state,name,None)) for name in ('marks','backing','body','bend')})
 def look_source(self,origin):
  if self._closed or self.observation_pending:return None
  item=self.latest.get(origin)
  if item is None:return None
  surface,record=item
  if record.get('_measured'):return None
  record['_measured']=True
  if not 0<=self.clock()-record['sent_ns']<=MAX_AGE_NS:return None
  dimensions=surface.get_width(),surface.get_height();source=self._source(origin,record['epoch'],dimensions)
  captured_ns=record['sent_ns'] if origin=='own_display' else self.clock();percept=source.measure(surface,None,captured_ns,self.started_ns,validate_sensory(record.get('sensory'),origin) if self.neural_enabled else None)
  return self._result(origin,percept,record,captured_ns,dimensions)
 def look_desktop(self,glimpse,captured_ns,epoch=0,sensory=None):
  if self._closed or self.observation_pending:return None
  dimensions=glimpse.width,glimpse.height;source=self._source('desktop',epoch,dimensions)
  record=dict(epoch=epoch)
  if self.neural_enabled:record['sensory']=validate_sensory(sensory if sensory is not None else self.desktop_sensory(),'desktop')
  percept=source.measure(None,glimpse,captured_ns,self.started_ns,record.get('sensory'))
  return self._result('desktop',percept,record,captured_ns,dimensions)
 def close(self):
  if self._closed:return self.cache_flushed
  self._closed=True;self._pending_observation=None
  self.cache_flushed=True
  try:
   if self.cache is not None:
    for origin,source in self.sources.items():
     if source.scene is not None:self.cache.put('eye.drawing',self.eye_runtime+':'+origin,encoded(self.drawing_snapshot(origin)),dict(phase='close',runtime=self.runtime,eye_runtime=self.eye_runtime,source=origin,epoch=source.evidence_epoch,input_epoch=source.epoch))
    self.cache.flush()
  except (ValueError,OSError,sqlite3.Error):self.cache_flushed=False
  finally:
   for surface,_record in self.latest.values():wipe(surface)
   self.latest.clear();self.sources.clear();self.last_scene=None
  return self.cache_flushed
