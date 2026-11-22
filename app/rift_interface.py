"""Owned native feeling input and bounded internal rift steering.

No public command entrance, new observation, clock, worker or raster pass.
Route preferences never change measured similarity or source/ACK authority.
"""
from collections import OrderedDict
import copy,hashlib,math,re,uuid
from alphabet_rift import _typed_equal
from world_clock import validate_stamp,tick_distance
from bearing import obtained,passive

SIGNALS=('rift_sense','rift_feedback')
# Owner-approved 3 Nov 2026 curiosity drive. Native ticks only; no new clock.
EXPLORE_AFTER=32   # consecutive passive ticks without a published crossing
EXPLORE_TICKS=8    # length of one exploration window
CURIOSITY=.15      # ranking bonus for a never-visited stream, fading with visits
MAX_VISITS=8
# Owner-approved 4 Nov 2026 warm start: visits are kept per source family across
# opens. After opening, sleep or a dream, the first eligible tick with two live
# sources opens one exploration window instead of waiting EXPLORE_AFTER ticks.
FAMILY=re.compile(r'[a-z][a-z0-9_.:-]{0,95}')
def family(source):return source.split('|',1)[0] if type(source) is str else ''
LIFECYCLE=('tick','load','enter_sleep','wake','dream_begin','dream_end','shutdown')

def unit(v):
    if type(v) not in (int,float) or type(v) is float and not math.isfinite(v):return 0.
    return float(max(0,min(1,v)))

def owned_projection(body,expected):
    if type(body) is not dict:return False
    extra=set(body)-set(expected)
    return (extra<= {'context_ref','receipt_context_ref'} and
            all(type(body[k]) is str and len(body[k])<=256 for k in extra) and
            all(k in body for k in expected) and
            _typed_equal({k:body[k] for k in expected},expected))

class RiftInterface:
    def __init__(self,cache,clock,flow,*,alphabet=None,pressure=None,source_validator=None):
        self.cache=cache;self.clock=clock;self.flow=flow;self.alphabet=alphabet
        self.pressure_reader=pressure or (lambda:0.);self.source_validator=source_validator
        self.closed=self.sleeping=self.dreaming=self.load_high=False
        self.refs=OrderedDict();self.marks={};self.issued=OrderedDict();self.weights=OrderedDict()
        self._cap=object();self._publisher=None;self._gain=lambda:0.;self._timeline=None;self._last_tick=None;self._last_sense=-8;self._last_shape=None;self._cursor=0;self._settle_until=-1;self._wander=None
        self._highest_tick=None;self._clock_bad=False
        self._pressure=0.;self._aperture=1.;self._stride=1
        self._passive_run=0;self._explore_until=-1;self.visits=OrderedDict();self._wake_pending=True
        self.counts=dict(signals=0,intents=0,feedback=0,withdrawals=0,rejected=0,state_rejected=0,archive_failed=0,exploration_windows=0,curious_crossings=0,wake_windows=0,remembered_visits=0)
        try:
            saved=cache.get_json('rift.internal.state','v1')
            if saved is not None:
                if type(saved) is not dict or set(saved)!={'version','weights'} or type(saved['version']) is not int or saved['version']!=1 or type(saved['weights']) is not list or len(saved['weights'])>8:raise ValueError('invalid rift preferences')
                for k,v in saved['weights']:
                    if type(k) is not str or re.fullmatch('[0-9a-f]{16}',k) is None or type(v) not in (int,float) or not 0<=v<=1 or not math.isfinite(v) or k in self.weights:raise ValueError('invalid rift preference')
                    self.weights[k]=float(v)
        except (OSError,ValueError,TypeError,KeyError):self.weights.clear();self.counts['state_rejected']+=1
        # Separate key, so an earlier release reading rift.internal.state is unaffected.
        try:
            saved=cache.get_json('rift.internal.visits','v1')
            if saved is not None:
                if type(saved) is not dict or set(saved)!={'version','visits'} or type(saved['version']) is not int or saved['version']!=1 or type(saved['visits']) is not list or len(saved['visits'])>MAX_VISITS:raise ValueError('invalid rift visits')
                for item in saved['visits']:
                    if type(item) not in (list,tuple) or len(item)!=2:raise ValueError('invalid rift visit')
                    k,v=item
                    if type(k) is not str or FAMILY.fullmatch(k) is None or type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=MAX_VISITS or k in self.visits:raise ValueError('invalid rift visit')
                    self.visits[k]=float(v)
                self.counts['remembered_visits']=len(self.visits)
        except (OSError,ValueError,TypeError,KeyError):self.visits.clear();self.counts['remembered_visits']=0;self.counts['state_rejected']+=1
    def current(self):
        try:return validate_stamp(self.clock.stamp())
        except (ValueError,TypeError,KeyError):return None
    def _clear(self):
        self.refs.clear();self.marks.clear();self.issued.clear();self._last_shape=None;self._settle_until=-1;self._wander=None
        self._passive_run=0;self._explore_until=-1
    def exploring(self):
        """Inside an exploration window opened by sustained passiveness. A read only."""
        if self.closed or self.sleeping or self.dreaming or self.load_high or self._clock_bad or self._explore_until<0:return False
        now=self.current()
        return now is not None and now['tick']<self._explore_until
    def curiosity(self,source):
        return CURIOSITY/(1.+self.visits.get(family(source),0.))
    def _curious(self,node_id):
        node=self.flow.nodes.get(node_id)
        return self.curiosity(node['source']) if node else 0.
    def _sync(self):
        stamp=self.current();line=None if stamp is None else (stamp['world_id'],stamp['segment_id'])
        if line!=self._timeline:
            self._clear();self._last_tick=None;self._last_sense=-8;self._timeline=line;self._highest_tick=None;self._clock_bad=False
        if stamp is None or self._clock_bad or self._highest_tick is not None and stamp['tick']<self._highest_tick:
            self._clear();self._aperture=0.;self._clock_bad=True;return None
        self._highest_tick=stamp['tick']
        return stamp
    def _valid(self,row):
        now=self.current()
        if self.closed or self.sleeping or self.dreaming or self._clock_bad or now is None:return False
        distance=tick_distance(row['stamp'],now)
        if distance is None or row['stamp']['tick']>now['tick'] or not 0<=distance<=64:return False
        if row['source'] is None:return distance<=8
        current=self.flow.active.get(row['source'])
        if current is None or current['epoch']!=row['epoch']:return False
        if not any(n['source']==row['source'] and n['epoch']==row['epoch'] and n['live'] for n in reversed(self.flow.nodes.values())):return False
        if self.source_validator:
            try:return bool(self.source_validator(dict(source=row['source'],source_epoch=row['epoch'],world_stamp=row['stamp'])))
            except (ValueError,TypeError,KeyError):return False
        return True
    def _ref(self,source,epoch,stamp):
        key=hashlib.sha256(repr((self._timeline,source,epoch)).encode()).hexdigest()[:24];ref='rift:'+key
        family=hashlib.sha256((source.split('|',1)[0] if source else 'intake').encode()).hexdigest()[:16]
        row=dict(source=source,epoch=epoch,stamp=copy.deepcopy(stamp),family=family)
        self.refs[ref]=row;self.refs.move_to_end(ref)
        while len(self.refs)>16:
            old,_=self.refs.popitem(last=False);self.marks.pop(old,None)
        return ref
    def _issue(self,name,row,bus,*,feedback=False):
        stamp=self.current();ref=self._ref(row['source'],row['epoch'],stamp)
        value=dict(id=uuid.uuid4().hex,ref=ref,stamp=copy.deepcopy(stamp),pressure=self._pressure,
                   coherence=row.get('coherence',0.),authority='unauthority',semantic_verification='unknown',
                   derived_control=True,independent_outside_evidence=False)
        self.issued[value['id']]=(name,copy.deepcopy(value));self.issued.move_to_end(value['id'])
        while len(self.issued)>128:self.issued.popitem(last=False)
        bus.publish(name,value);self.counts['feedback' if feedback else 'signals']+=1
    def take_signal(self,name,body):
        if type(body) is not dict:return None
        ident=body.get('id');issued=self.issued.get(ident) if type(ident) is str else None
        row=self.refs.get(body.get('ref')) if type(body.get('ref')) is str else None
        now=self.current()
        fresh=issued is not None and now is not None and issued[1]['stamp']['tick']<=now['tick'] and tick_distance(issued[1]['stamp'],now) is not None and tick_distance(issued[1]['stamp'],now)<=8
        if not fresh or issued[0]!=name or row is None or not self._valid(row) or not owned_projection(body,issued[1]):
            self.counts['rejected']+=1;return None
        # Retirement belongs to the issuance itself, never an unrelated FIFO.
        del self.issued[ident]
        return body['ref'],(.10 if name=='rift_feedback' else .22+.18*body['pressure']+.12*body['coherence'])
    def alphabet_ref(self,body):
        if self.alphabet is None or not self.alphabet.owns(body):return None
        source=body['source'];epoch=body['source_epoch'];stamp=body['world_stamp']
        ref=self._ref(source,epoch,stamp)
        if not self._valid(self.refs[ref]) or not self.alphabet.claim_feeling(body):return None
        return ref
    def _reconcile(self,cap,owner):
        if cap is not self._cap or owner is not self._publisher:return
        marks={}
        if unit(self._gain())>0:
            for link in owner.links:
                ref=link.get('ref');row=self.refs.get(ref)
                if row is not None and self._valid(row):
                    score=.7*unit(link.get('pull'))+.3*unit(link.get('held'))
                    if score>0:marks[ref]=score
        self.marks=marks
        if self.marks:self._wander=None
    def _from_feeling(self,cap,owner,name,body):
        if cap is not self._cap or owner is not self._publisher:return
        had_marks=bool(self.marks);self._reconcile(cap,owner)
        if name=='chain_broken':
            if had_marks and self.current() is not None:
                self.marks.clear();self._settle_until=self.current()['tick']+2;self.counts['withdrawals']+=1;self._aperture=0.
            self._wander=None
            return
        if unit(self._gain())<=0:return
        row=self.refs.get(body.get('ref'))
        if row is None or not self._valid(row):return
        if name not in ('chain_extended','attraction_rise','attraction_fade','approbation_marked'):return
        if type(body.get('tick')) is not int or not 0<=self.current()['tick']-body['tick']<=64:return
        score=.7*unit(body.get('pull'))+.3*unit(body.get('held'))
        if score>0:self.marks[body['ref']]=score
        else:self.marks.pop(body['ref'],None)
        if self.marks:self._wander=None
        family=row['family'];self.weights[family]=.8*self.weights.get(family,0.)+.2*score;self.weights.move_to_end(family)
        while len(self.weights)>8:self.weights.popitem(last=False)
        self.counts['intents']+=1
    def bias(self,row):
        if self.closed or self.sleeping or self.dreaming or unit(self._gain())<=0:return 0.
        return max((.35*(self.marks.get(ref,0.)+.1*self.weights.get(r['family'],0.)) for ref,r in self.refs.items()
                    if ref in self.marks and r['source']==row.get('source') and r['epoch']==row.get('source_epoch') and self._valid(r)),default=0.)
    def peer_limit(self):return 0 if self._clock_bad or self.current() is None or self._aperture<=0 else 1 if self._aperture<.75 else 2
    def obtain_control(self):
        return obtained()
    def amongst_noise(self):
        noise=self._pressure if self._pressure>0 else (1. if self.load_high else 0.)
        return passive(noise,forcing=bool(self.marks) or self.obtain_control())
    def live_noise(self):
        # Drain runs before this tick stores pressure. Read the same reader, write nothing.
        try:noise=unit(self.pressure_reader())
        except (TypeError,ValueError,KeyError,AttributeError,ZeroDivisionError):noise=0.
        if noise<=0 and self.load_high:noise=1.
        return noise
    def passive_now(self):
        if self.closed or self.sleeping or self.dreaming or self._clock_bad or self.current() is None:return False
        return passive(self.live_noise(),forcing=bool(self.marks) or self.obtain_control())
    def _arm_wander(self,stamp):
        # One in-memory salt for this native tick. Selection only reads it.
        self._wander=None
        if self.closed or self.sleeping or self.dreaming or self.load_high or self._clock_bad:return
        # Reuse native, genome-scaled capacity; an empty queue is not required.
        if self.peer_limit()!=2 or self.study_stride()!=1 and not self.exploring() or self.marks or unit(self._gain())<=0:return
        node=''
        for n in reversed(self.flow.nodes.values()):
            if n.get('live'):
                node=n['id'];break
        pi=stamp['pi']
        material=f"{stamp['world_id']}|{stamp['segment_id']}|{stamp['tick']}|{stamp['slot']}|{pi[0]}|{pi[1]}|{node}"
        salt=int.from_bytes(hashlib.sha256(material.encode()).digest()[:8],'big')
        self._wander=dict(world_id=stamp['world_id'],segment_id=stamp['segment_id'],tick=stamp['tick'],salt=salt)
    def _wander_salt(self):
        row=self._wander
        if type(row) is not dict or self.closed or self.sleeping or self.dreaming or self.load_high or self._clock_bad:return None
        if self.study_stride()!=1 and not self.exploring() or self.marks or unit(self._gain())<=0 or self.peer_limit()!=2:return None
        now=self.current()
        if now is None or now['world_id']!=row.get('world_id') or now['segment_id']!=row.get('segment_id') or now['tick']!=row.get('tick'):return None
        salt=row.get('salt')
        return salt if type(salt) is int and salt>=0 else None
    def select_peers(self,source,peers):
        limit=self.peer_limit()
        ranked=sorted(peers,key=lambda p:(p[0]+self.bias(dict(source=self.flow.nodes[p[1]]['source'],source_epoch=self.flow.nodes[p[1]]['epoch']))+self._curious(p[1]),p[1]),reverse=True)
        chosen=ranked[:limit]
        salt=self._wander_salt()
        if salt is None or limit<2 or len(ranked)<3:return chosen
        return [ranked[0],ranked[1:][salt%len(ranked[1:])]]
    def select_edge(self,edges):
        if not self.peer_limit():return None
        return max(edges,key=lambda e:(e['score']+self.bias(dict(source=self.flow.nodes[e['to']]['source'],source_epoch=self.flow.nodes[e['to']]['epoch']))+self._curious(e['to']),self.flow.nodes[e['to']]['stamp']['tick'],e['to']),default=None)
    def block_reason(self):
        # Explanations are reads only; actual attempt owners count outcomes.
        if self.closed or self.sleeping or self.dreaming:return 'paused'
        if self._clock_bad or self.current() is None:return 'obsolete'
        if self._aperture<=0:return 'settling'
        return None
    def permission_reason(self,context,when):
        reason=self.block_reason()
        if reason is not None:return reason
        refs=context.get('steering',[])
        if refs and unit(self._gain())<=0:return 'gain_disabled'
        if type(refs) is not list or len(refs)>16:return 'preference_withdrawn'
        for ref in refs:
            if type(ref) is not str or ref not in self.marks:return 'preference_withdrawn'
            if ref not in self.refs or not self._valid(self.refs[ref]):return 'source_expired'
        length=len(context.get('paths',{}).get('lateral',[]))
        if not length:return 'no_peer'
        if length>self.peer_limit():return 'narrowed'
        return None
    def permitted(self,context,when):return self.permission_reason(context,when) is None
    def requirements(self,context):
        nodes=[self.flow.nodes.get(context.get('anchor'))]+[path['node'] for path in context['paths']['lateral']]
        pairs={(n['source'],n['epoch']) for n in nodes if n is not None}
        return [ref for ref,row in self.refs.items() if ref in self.marks and (row['source'],row['epoch']) in pairs and self._valid(row)]
    def study_stride(self):return self._stride
    def preferred_lane(self):
        scores={lane:max((self.bias(dict(source=r['source'],source_epoch=r['epoch'])) for r in self.refs.values() if r['source'] and r['source'].startswith('native.alphabet.'+lane+'|')),default=0.) for lane in ('incoming','own')}
        return max(scores,key=scores.get) if max(scores.values())>0 and scores['incoming']!=scores['own'] else None
    def feedback(self,row,context,bus):
        # Called only by the adaptor's successful, current, ACK-gated publish.
        if not self.permitted(context,self.current()):return
        # A real published crossing ends the passive run and is a visit.
        sources=[path['node']['source'] for path in context.get('paths',{}).get('lateral',[]) if type(path.get('node'),) is dict]
        sources=list(dict.fromkeys(family(s) for s in sources))
        if any(self.visits.get(s,0.)<.5 for s in sources):self.counts['curious_crossings']+=1
        for s in self.visits:self.visits[s]*=.9
        for s in sources:
            self.visits[s]=self.visits.get(s,0.)+1.;self.visits.move_to_end(s)
        while len(self.visits)>MAX_VISITS:self.visits.popitem(last=False)
        self._passive_run=0
        node=self.flow.nodes.get(context.get('anchor'))
        if node and node['live']:self._issue('rift_feedback',dict(source=node['source'],epoch=node['epoch']),bus,feedback=True)
    def on_event(self,name,body,bus):
        if self.closed:return
        if name not in LIFECYCLE:return
        stamp=self._sync()
        if name=='shutdown':self.close();return
        if name=='load':
            # Same level-2 shedding line as the learning adaptor.
            self.load_high=bool(body.get('high')) and (body.get('level') is None or body.get('level')>=2)
            if self.load_high:self._wander=None
        elif name in ('enter_sleep','wake','dream_begin','dream_end'):
            if name in ('enter_sleep','wake'):self.sleeping=name=='enter_sleep'
            else:self.dreaming=name=='dream_begin'
            self._clear()
            if name in ('wake','dream_end'):self._wake_pending=True
        if self.sleeping or self.dreaming:self._aperture=0.;return
        if name!='tick' or stamp is None:return
        try:valid=type(body.get('tick')) is int and body['tick']==stamp['tick'] and ('world_stamp' not in body or _typed_equal(validate_stamp(body['world_stamp']),stamp))
        except (ValueError,TypeError,KeyError,OverflowError):valid=False
        if not valid:
            self._clear();self._aperture=0.;self.counts['rejected']+=1;return
        if self._last_tick is not None and stamp['tick']<=self._last_tick:return
        self._last_tick=stamp['tick'];self.flow.prune(stamp,self.source_validator)
        self.refs=OrderedDict((ref,row) for ref,row in self.refs.items() if self._valid(row));self.marks={ref:v for ref,v in self.marks.items() if ref in self.refs}
        self._pressure=unit(self.pressure_reader());gain=unit(self._gain());holding=max(self.marks.values(),default=0.)
        self._aperture=0. if stamp['tick']<self._settle_until else max(.25,min(1.,1.-gain*(.6*self._pressure+.15*self.load_high)+.15*holding))
        self._stride=1+int(3*gain*self._pressure)
        if gain<=0:
            self._wander=None;self._passive_run=0;self._explore_until=-1
            return
        if stamp['tick']>=self._settle_until:
            if self._wake_pending and not self.load_high and not self.exploring() and len({n['source'] for n in self.flow.nodes.values() if n['live']})>=2:
                self._wake_pending=False;self._passive_run=0
                self._explore_until=stamp['tick']+EXPLORE_TICKS;self.counts['exploration_windows']+=1;self.counts['wake_windows']+=1
            elif not self.exploring():
                # The pressure this tick already sampled; the reader is not read again.
                self._passive_run=self._passive_run+1 if self.amongst_noise() else 0
                if self._passive_run>=EXPLORE_AFTER and not self.load_high:
                    self._explore_until=stamp['tick']+EXPLORE_TICKS;self._passive_run=0;self.counts['exploration_windows']+=1
            if self.exploring():self._aperture=1.
        self._arm_wander(stamp)
        latest=OrderedDict()
        for n in reversed(self.flow.nodes.values()):
            if n['live'] and n['source'] not in latest:latest[n['source']]=n
        shape=(round(self._pressure*8),tuple((s,n['epoch']) for s,n in latest.items()),self.load_high)
        if shape==self._last_shape and stamp['tick']-self._last_sense<4:return
        self._last_shape=shape;self._last_sense=stamp['tick']
        rows=list(latest.values())
        if not rows:
            if self._pressure<=0:return
            row=dict(source=None,epoch=0)
        else:
            row=rows[self._cursor%len(rows)];self._cursor+=1
            scores=[e['score'] for e in self.flow.edges.values() if e['direction']=='lateral' and self.flow.nodes[e['from']]['live'] and self.flow.nodes[e['to']]['live'] and (e['from']==row['id'] or e['to']==row['id'])]
            row=dict(source=row['source'],epoch=row['epoch'],coherence=sum(scores)/len(scores) if scores else 0.)
        self._issue('rift_sense',row,bus)
    def summary(self):
        return dict(self.counts,pressure=self._pressure,aperture=self._aperture,stride=self._stride,active_preferences=sum(ref in self.marks and self._valid(row) for ref,row in self.refs.items()),closed=self.closed,control_obtained=int(self.obtain_control()),passive=int(self.amongst_noise()))
    def close(self):
        if self.closed:return
        try:self.cache.set_json('rift.internal.state','v1',dict(version=1,weights=list(self.weights.items())))
        except (OSError,ValueError):self.counts['archive_failed']+=1
        try:self.cache.set_json('rift.internal.visits','v1',dict(version=1,visits=[[k,round(min(v,MAX_VISITS),6)] for k,v in self.visits.items() if FAMILY.fullmatch(k)]))
        except (OSError,ValueError):self.counts['archive_failed']+=1
        self.closed=True;self._clear();self._aperture=0.

def feeling_class(Base,service):
    cap=service._cap
    class RiftFeeling(Base):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);service._publisher=self;service._gain=lambda:self._gain();service._reconcile(cap,self)
        def notice(self,bus,name,payload):
            result=super().notice(bus,name,payload);service._reconcile(cap,self);return result
        def _stimulus(self,name,payload):
            if name in SIGNALS:
                row=service.take_signal(name,payload)
                return None if row is None else (row[0],row[1]*self._gain(),0.,'rift',None)
            if name=='numeric_pattern' and 'alphabet' in payload:
                ref=service.alphabet_ref(payload)
                return None if ref is None else (ref,.26*self._gain(),0.,'rift',None)
            return super()._stimulus(name,payload)
        def _publish(self,bus,name,link,**kwargs):
            body=self._body(link,**kwargs)
            if kwargs.get('broken'):body['ref']=str(link.get('ref') or '')
            service._from_feeling(cap,self,name,body)
            return super()._publish(bus,name,link,**kwargs)
        async def run(self,bus,stop):
            class ExtraBus:
                def subscribe(_self,*names):return bus.subscribe(*dict.fromkeys((*names,*SIGNALS)))
                def __getattr__(_self,name):return getattr(bus,name)
            return await super().run(ExtraBus(),stop)
    return RiftFeeling

def install(ns,hub,cache):
    adaptor=hub.progression.adaptor;alphabet=hub.alphabet
    def pressure():
        state=hub.buffer.status()
        return max(state['pending']/256,sum(row.get('_cost',0) for row in hub.buffer.pending.values())/hub.buffer.max_bytes,alphabet.summary()['pending']/8,len(adaptor.pending)/16)
    service=RiftInterface(cache,hub.clock,adaptor.temporal,alphabet=alphabet,pressure=pressure,source_validator=adaptor.source_validator)
    hub.rift=service;adaptor.rift=service;adaptor.temporal.steering=service;alphabet.steering=service
    ns['FeelingAgent']=feeling_class(ns['FeelingAgent'],service)
    Base=ns['EventBus']
    class RiftBus(Base):
        def _emit(self,name,body):
            result=super()._emit(name,body)
            if name in LIFECYCLE:service.on_event(name,body,self)
            return result
    ns['EventBus']=RiftBus
    return service
