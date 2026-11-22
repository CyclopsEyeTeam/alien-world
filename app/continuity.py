"""One cache-owned world identity, with an exclusive engine lease.

Only committed canonical native heads select the initial owner world. Once
selected, the descriptor is binding. Closed time never supplies tick counts.
"""
import copy,fcntl,math,os,re,uuid
from pathlib import Path
from content_cache import ContentCache
from world_clock import WorldClock,validate_stamp,integer
ZERO='0'*32
ABSENT=object()
SCHEMA='ALIEN_CONTINUOUS_WORLD_V1'

def identity(value):
 if type(value) is not str or re.fullmatch('[0-9a-f]{32}',value) is None or value==ZERO:raise ValueError('Invalid continuing world identity')
 return value

class WorldLease:
 def __init__(self,path):self.path=Path(path);self.fd=None;self.world_id=None;self.stamp=None
 def __enter__(self):
  self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
  self.fd=os.open(self.path.with_name(self.path.name+'.world.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
  try:
   fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
   self._resolve();return self
  except BaseException:self.__exit__(None,None,None);raise
 def __exit__(self,*_):
  if self.fd is not None:os.close(self.fd);self.fd=None
 def _resolve(self):
  with ContentCache(self.path,ZERO) as index:
   active=index.get_json('world.continuity','active',ABSENT)
   if active is not ABSENT:
    if type(active) is not dict or set(active)!={'schema','world_id','phase'} or active['schema']!=SCHEMA or active['phase'] not in ('initialising','ready'):raise ValueError('Continuing world descriptor is damaged; no replacement was created')
    world=identity(active['world_id']);new=False
   else:
    row=index.db.execute("SELECT r.world FROM heads h JOIN records r ON r.id=h.id AND r.world=h.world WHERE h.kind='native.state' AND h.world<>? ORDER BY r.seq DESC LIMIT 1",(ZERO,)).fetchone()
    if row is None and index.db.execute('SELECT 1 FROM records LIMIT 1').fetchone():raise ValueError('Existing archive has no canonical world; no replacement was created')
    world=identity(row[0]) if row else uuid.uuid4().hex;new=row is None
  with ContentCache(self.path,world) as cache:
   saved=cache.get_json('native.state','world-clock.json',ABSENT)
   if saved is ABSENT and new:
    clock=WorldClock(world);clock.observe(0);saved={'stamp':clock.stamp()}
   if type(saved) is not dict or set(saved)!={'stamp'}:raise ValueError('Saved world clock unavailable; no older world was substituted')
   stamp=validate_stamp(saved['stamp'])
   if stamp is None or stamp['world_id']!=world:raise ValueError('Saved world clock identity mismatch')
   memory=cache.get_json('native.state','aura_memory.json',ABSENT)
   if memory is ABSENT:
    if stamp['tick']!=0 or not (new or active is not ABSENT and active['phase']=='initialising'):raise ValueError('Saved native memory unavailable; no reset was performed')
   else:
    if type(memory) is not dict or type(memory.get('current')) is not dict or type(memory.get('ticks')) is not dict:raise ValueError('Saved native memory is damaged')
    genes=memory['current'].get('genes');tick=integer(memory['ticks'].get('current_tick'));integer(memory['current'].get('generation',0))
    if type(genes) is not list or not 1<=len(genes)<=512 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in genes):raise ValueError('Saved native genome is damaged')
    if tick>stamp['tick']:
     clock=WorldClock(world,stamp['period']);clock.segment_id=stamp['segment_id'];clock.observe(tick);stamp=clock.stamp()
   for key in ('aura_vectors.json','aura_cache.json','aura_private.json','root_truth.json','temporal.json','alien_register.json'):
    value=cache.get_json('native.state',key,ABSENT)
    if value is not ABSENT and type(value) is not dict:raise ValueError('Saved native state is damaged: '+key)
   cache.set_json('native.state','world-clock.json',{'stamp':stamp});cache.flush()
  descriptor={'schema':SCHEMA,'world_id':world,'phase':'initialising' if memory is ABSENT else 'ready'}
  if active!=descriptor:
   with ContentCache(self.path,ZERO) as index:index.set_json('world.continuity','active',descriptor);index.flush()
  self.world_id=world;self.stamp=copy.deepcopy(stamp)

def install_ticks(ns,hub):
 """Align native restarts/respawns to saved electrical time, not host time."""
 Base=ns['TickAgent']
 class ContinuingTick(Base):
  def __init__(self,*args,**kw):
   super().__init__(*args,**kw)
   if hub.clock.tick is not None:
    self.current_tick=max(self.current_tick,hub.clock.tick);self.session_start=self.current_tick;self.pending_resume=self.current_tick>0
 ns['TickAgent']=ContinuingTick

def wake_state(cache,stamp):
 previous=cache.get_json('world.lifecycle','v1')
 interruptions=0;interrupted=False
 if previous is not None:
  if type(previous) is not dict or previous.get('state') not in ('awake','asleep'):raise ValueError('Saved world lifecycle is damaged')
  interruptions=integer(previous.get('interruptions',0));interrupted=previous['state']=='awake'
 state=dict(state='awake',stamp=copy.deepcopy(stamp),interruptions=interruptions+int(interrupted),interrupted=interrupted,closed_duration='unknown')
 cache.set_json('world.lifecycle','v1',state);return state

def bootstrap_world(ns,cache,world):
 # Establish the initial genome before any electrical observation. Ready is
 # written after native memory in the same physical archive prefix.
 if cache.get_json('native.state','aura_memory.json') is None:
  ns['save_memory'](ns['MEMORY_PATH'],ns['Genome'](),[],0,None,[],ticks=ns['empty_ticks']())
 with cache.namespace(ZERO) as index:
  index.set_json('world.continuity','active',{'schema':SCHEMA,'world_id':world,'phase':'ready'});index.flush()
