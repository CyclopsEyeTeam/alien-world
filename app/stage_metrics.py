"""Bounded diagnostic spans; no hive events, content or clock authority."""
import functools,math,secrets,threading,time
STAGES=('frame','layers','ripples','encode','send','event_bus','math','vector_search','learning','neural','receive','texture','buffer_roundtrip','cache_read','progression','language','tick_checkpoint','art_read','field_prepare','rift','text_learning')
COUNTS=('send_ok','send_busy','staging_allocations','staging_reuses','staging_bytes','packed_frames','legacy_frames')
FIELDS=('elapsed_ms','token')+COUNTS+tuple(stage+'_'+suffix for stage in STAGES for suffix in ('calls','errors','wall_ms','cpu_ms','max_wall_ms','max_cpu_ms'))
def profile_fields(value):
 if type(value) is not dict or value.get('scope')!='current_process':return {}
 return dict(scope='current_process',**{k:v for k in FIELDS if type(v:=value.get(k)) in (int,float) and math.isfinite(v) and 0<=v<=1e24})
class StageMetrics:
 def __init__(self):self.started=time.monotonic();self.token=secrets.randbits(48);self.lock=threading.Lock();self.local=threading.local();self.values={}
 def call(self,stage,callback,*args,**kwargs):
  if stage not in STAGES:raise ValueError('unknown diagnostic stage')
  active=getattr(self.local,'active',None)
  if active is None:active=set();self.local.active=active
  if stage in active:return callback(*args,**kwargs)
  active.add(stage);wall=time.perf_counter_ns();cpu=time.thread_time_ns();failed=0
  try:return callback(*args,**kwargs)
  except BaseException:failed=1;raise
  finally:
   elapsed=max(0,time.perf_counter_ns()-wall)/1e6;used=max(0,time.thread_time_ns()-cpu)/1e6;active.remove(stage)
   with self.lock:
    row=self.values.setdefault(stage,dict(calls=0,errors=0,wall_ms=0.,cpu_ms=0.,max_wall_ms=0.,max_cpu_ms=0.))
    row['calls']+=1;row['errors']+=failed;row['wall_ms']+=elapsed;row['cpu_ms']+=used;row['max_wall_ms']=max(row['max_wall_ms'],elapsed);row['max_cpu_ms']=max(row['max_cpu_ms'],used)
 def snapshot(self):
  with self.lock:return dict(scope='current_process',token=self.token,elapsed_ms=max(0.,time.monotonic()-self.started)*1000,**{stage+'_'+k:v for stage,row in self.values.items() for k,v in row.items()})
 def bind(self,obj,names,stage):
  for name in names:
   original=getattr(obj,name,None)
   if original is None:continue
   @functools.wraps(original)
   def wrapped(*args,_original=original,**kw):return self.call(stage,_original,*args,**kw)
   setattr(obj,name,wrapped)
PAINT_METHODS=('_paint_ripples','_paint_motes','_paint_turbulence','_paint_motifs','_paint_recall','_paint_flicker','_paint_tick_echo','_paint_feeling_trace','_paint_mirror_echo','_paint_sleep','_paint_dream_motes')
def profile_renderer(Base,profile):
 class Profiled(Base):
  def _frame(self,*args,**kw):return profile.call('frame',super()._frame,*args,**kw)
 for name in PAINT_METHODS:
  method=getattr(Base,name,None)
  if method is None:continue
  def paint(self,*args,_method=method,_name=name,**kw):
   if _name=='_paint_ripples':return profile.call('layers',profile.call,'ripples',_method,self,*args,**kw)
   return profile.call('layers',_method,self,*args,**kw)
  setattr(Profiled,name,paint)
 return Profiled

def profile_agents(ns,profile):
 # Never time an async run across await: other agents share that CPU thread.
 for name,methods,stage in (('MathAgent',('study',),'math'),('VectorAgent',('_near',),'vector_search')):
  Base=ns.get(name)
  if Base is None:continue
  class Timed(Base):pass
  for method in methods:
   original=getattr(Base,method)
   @functools.wraps(original)
   def wrapped(self,*args,_original=original,_stage=stage,**kw):return profile.call(_stage,_original,self,*args,**kw)
   setattr(Timed,method,wrapped)
  ns[name]=Timed
