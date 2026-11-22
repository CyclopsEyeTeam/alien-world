"""One native integer timeline; π is an exact, lazily rendered representation."""
import uuid,math

def integer(value,low=0,high=2**64-1):
    if type(value) is not int or not low<=value<=high:raise ValueError('invalid clock integer')
    return value

def validate_stamp(s):
    if s is None:return None
    if not isinstance(s,dict):raise ValueError('invalid clock stamp')
    for key in ('world_id','segment_id'):
        if not isinstance(s.get(key),str) or not 1<=len(s[key])<=64:raise ValueError('invalid clock identity')
    n=integer(s.get('tick'));p=integer(s.get('period'),1,2**31-1);cycle,slot=divmod(n,p)
    integer(s.get('cycle'));integer(s.get('slot'))
    if not isinstance(s.get('pi'),list) or len(s['pi'])!=2:raise ValueError('invalid π coefficient')
    integer(s['pi'][0]);integer(s['pi'][1],1,2**31-1)
    if s.get('version')!=1 or type(s['version']) is not int or s.get('cycle')!=cycle or s.get('slot')!=slot or s.get('pi')!=[2*slot,p]:raise ValueError('inconsistent π stamp')
    return dict(s)

def tick_distance(a,b):
    a=validate_stamp(a);b=validate_stamp(b)
    if a is None or b is None or any(a[k]!=b[k] for k in ('world_id','segment_id')):return None
    return abs(a['tick']-b['tick'])

class WorldClock:
    def __init__(self,world_id=None,period=256):
        self.world_id=world_id or uuid.uuid4().hex;self.segment_id=uuid.uuid4().hex
        self.period=integer(period,1,2**31-1);self.tick=None
    def observe(self,n,resumed=False):
        integer(n)
        if n==self.tick:return False
        if self.tick is not None and n<self.tick:self.segment_id=uuid.uuid4().hex
        self.tick=n;return True
    def stamp(self):
        if self.tick is None:return None
        cycle,slot=divmod(self.tick,self.period)
        return dict(world_id=self.world_id,segment_id=self.segment_id,tick=self.tick,period=self.period,cycle=cycle,slot=slot,pi=[2*slot,self.period],version=1)

def phase_radians(stamp):
    s=validate_stamp(stamp)
    return None if s is None else math.pi*(s['pi'][0]/s['pi'][1])
