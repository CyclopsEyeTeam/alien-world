"""Bounded crossings between measured active streams on Alien's one clock.

Past/next edges retain receipts, lateral edges join overlapping named channels.
Walking, restoring and yielding a route never creates an observation.
"""
from collections import OrderedDict,deque
import copy,hashlib,json,math,re
from world_clock import validate_stamp,tick_distance

SCHEMA='ALIEN_TEMPORAL_RIFT_V1'
STAMP_KEYS=('world_id','segment_id','tick','period','cycle','slot','pi','version')
DIRECTIONS=('past','future','lateral')
CROSS_MODAL_PAIRS=(
 ('brightness','log_scale'),
 ('attention_x','alphabet_position'),
 ('hue_sin','cursor_sin'),
 ('hue_cos','cursor_cos'),
 ('contrast','color_var'),
 ('change','entropy'),
 ('density','scale'),
)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def number(v):return type(v) in (int,float) and math.isfinite(v) and 0<=v<=1
def stamp(value):
 s=validate_stamp(value)
 return None if s is None else {k:copy.deepcopy(s[k]) for k in STAMP_KEYS}
def features(value):
 if type(value) is not dict or not 1<=len(value)<=16 or any(type(k) is not str or re.fullmatch('[a-z][a-z0-9_]{0,31}',k) is None or not number(v) for k,v in value.items()):raise ValueError('invalid temporal measurements')
 return {k:float(value[k]) for k in sorted(value)}
def same(a,b):return a is not None and b is not None and all(a[k]==b[k] for k in ('world_id','segment_id'))
def interval(a,b):return b['tick']-a['tick'] if same(a,b) else None

class TemporalFlow:
 def __init__(self,state=None):
  self.nodes=OrderedDict();self.edges=OrderedDict();self.seen=OrderedDict();self.active=OrderedDict()
  self.timeline=None;self.retired=deque(maxlen=64)
  self.steering=None
  self.counts=dict(observations=0,refused=0,past_links=0,lateral_links=0,routes=0,crossings=0,unknown_links=0)
  if state is not None:self._restore(state)
 def _refuse(self):self.counts['refused']+=1;return None
 def _node(self,n):
  self.nodes[n['id']]=n
  while len(self.nodes)>64:
   victim,_=self.nodes.popitem(last=False)
   self.edges=OrderedDict((k,e) for k,e in self.edges.items() if victim not in (e['from'],e['to']))
 def _link(self,a,b,direction,relation,score=1.):
  if a not in self.nodes or b not in self.nodes or a==b:return
  key=(a,b,direction,relation);span=interval(self.nodes[a]['stamp'],self.nodes[b]['stamp'])
  if key not in self.edges:
   if direction=='past':self.counts['past_links']+=1
   if direction=='lateral':self.counts['lateral_links']+=1
   if span is None:self.counts['unknown_links']+=1
  self.edges[key]=dict(**{'from':a,'to':b},direction=direction,relation=relation,score=score,tick_span=span)
  while len(self.edges)>192:self.edges.popitem(last=False)
 def observe(self,source,epoch,value,when,evidence):
  try:when=stamp(when);value=features(value)
  except (ValueError,TypeError):return self._refuse()
  if when is None or type(source) is not str or not 1<=len(source)<=96 or type(epoch) is not int or not 0<=epoch<2**64 or type(evidence) is not str or not 1<=len(evidence)<=128:return self._refuse()
  timeline=(when['world_id'],when['segment_id'])
  if timeline!=self.timeline:
   if timeline in self.retired:return self._refuse()
   if self.timeline is not None:self.retired.append(self.timeline)
   self.timeline=timeline;self.active.clear()
   for n in self.nodes.values():n['live']=False
  current=self.active.get(source)
  evidence_key=digest([timeline,source,epoch,evidence])
  if evidence_key in self.seen or current and (epoch<current['epoch'] or epoch==current['epoch'] and tuple(value)==current['names'] and when['tick']<=current['tick']):return self._refuse()
  predecessor=next((n for n in reversed(self.nodes.values()) if n['source']==source and set(n['features'])==set(value)),None)
  self.active[source]=dict(epoch=epoch,names=tuple(value),tick=when['tick']);self.active.move_to_end(source)
  while len(self.active)>8:self.active.popitem(last=False)
  self.prune(when)
  # Compare one most-recent receipt per other active stream, never array positions.
  peers=[];used=set()
  for n in reversed(self.nodes.values()):
   if n['live'] and n['source']!=source and n['source'] not in used:
    used.add(n['source']);shared=set(n['features'])&set(value)
    if shared:
     score=1-math.sqrt(sum((n['features'][k]-value[k])**2 for k in shared)/len(shared))
     if score>=.5:peers.append((score,n['id']))
    elif source.startswith('eye.')!=n['source'].startswith('eye.'):
     pairs=[(n['features'][a],value[b]) if a in n['features'] and b in value else (n['features'][b],value[a]) for a,b in CROSS_MODAL_PAIRS if a in n['features'] and b in value or b in n['features'] and a in value]
     if pairs:
      score=1-math.sqrt(sum((x-y)**2 for x,y in pairs)/len(pairs))
      if score>=.5:peers.append((score,n['id']))
  ident=digest(['observation',evidence_key,when,value])
  self._node(dict(id=ident,kind='observation',source=source,epoch=epoch,stamp=when,evidence=evidence_key,features=value,measured=True,live=True))
  if predecessor:
   relation='continuation' if same(predecessor['stamp'],when) and predecessor['epoch']==epoch else 'recall'
   self._link(ident,predecessor['id'],'past',relation);self._link(predecessor['id'],ident,'future',relation)
  selected=self.steering.select_peers(source,peers) if self.steering is not None else sorted(peers,reverse=True)[:2]
  for score,peer in selected:
   self._link(ident,peer,'lateral','similarity',score);self._link(peer,ident,'lateral','similarity',score)
  self.seen[evidence_key]=True
  while len(self.seen)>512:self.seen.popitem(last=False)
  self.counts['observations']+=1
  return ident
 def prune(self,when,source_validator=None):
  when=stamp(when)
  for n in self.nodes.values():
   current=self.active.get(n['source'])
   valid=when is not None and same(n['stamp'],when) and current and current['epoch']==n['epoch'] and current['names']==tuple(n['features'])
   if valid:
    distance=tick_distance(n['stamp'],when);valid=distance is not None and 0<=distance<=64
   if valid and source_validator:
    try:valid=bool(source_validator(dict(source=n['source'],source_epoch=n['epoch'])))
    except (ValueError,TypeError,KeyError):valid=False
   if not valid:n['live']=False
 def walk(self,anchor,direction,hops=1):
  if direction not in DIRECTIONS or type(hops) is not int or not 1<=hops<=2:raise ValueError('invalid bounded temporal direction')
  if direction=='lateral' and self.steering is not None:hops=min(hops,self.steering.peer_limit())
  result=[];seen={anchor};current=anchor
  for _ in range(hops):
   if direction=='lateral' and not self.nodes.get(current,{}).get('live'):break
   edges=[e for e in self.edges.values() if e['from']==current and e['direction']==direction and e['to'] not in seen and e['to'] in self.nodes and (direction!='lateral' or self.nodes[e['to']]['live'])]
   if not edges:break
   edge=self.steering.select_edge(edges) if direction=='lateral' and self.steering is not None else max(edges,key=lambda e:(e['score'],self.nodes[e['to']]['stamp']['tick'],e['to']))
   if edge is None:break
   current=edge['to'];seen.add(current)
   result.append(dict(node=copy.deepcopy(self.nodes[current]),relation=edge['relation'],tick_span=edge['tick_span']))
  return result
 def context(self,row):
  anchor=next((n['id'] for n in reversed(self.nodes.values()) if n['source']==row.get('source') and n['epoch']==row.get('source_epoch') and n['stamp']==row.get('world_stamp') and sorted(n['features'])==row.get('feature_names')),None)
  paths={d:self.walk(anchor,d,2) for d in DIRECTIONS} if anchor else {d:[] for d in DIRECTIONS}
  context=dict(version=1,anchor=anchor,origin_stamp=copy.deepcopy(row.get('world_stamp')),paths=paths,authority='unauthority',semantic_verification='unknown')
  if self.steering is not None:context['steering']=self.steering.requirements(context)
  return context
 def selection_reason(self,context):
  # No counters, pruning or validator calls during candidate ranking.
  if self.steering is not None:
   block=getattr(self.steering,'block_reason',None)
   reason=block() if block is not None else None
   if reason is not None:return reason
  if context.get('anchor') is None:return 'no_anchor'
  if not context.get('paths',{}).get('lateral'):return 'no_peer'
  return None
 def assessment(self,context,when,source_validator=None):
  # This is the old usable gate with a scalar explanation. Prune once and
  # evaluate owned preference validity once, never a second diagnostic pass.
  self.prune(when,source_validator)
  reason=self.selection_reason(context)
  if reason is not None:return reason
  ids=[context.get('anchor')]+[p['node']['id'] for p in context.get('paths',{}).get('lateral',[])]
  if not all(self.nodes.get(i,{}).get('live') for i in ids):return 'source_expired'
  if self.steering is not None:
   explain=getattr(self.steering,'permission_reason',None)
   return explain(context,when) if explain is not None else None if self.steering.permitted(context,when) else 'preference_withdrawn'
  return None
 def usable(self,context,when,source_validator=None):return self.assessment(context,when,source_validator) is None
 def affinity(self,row):return len(self.context(row)['paths']['lateral'])/2
 def committed(self,context):
  if context.get('version')==1 and context.get('paths',{}).get('lateral'):
   self.counts['routes']+=1;self.counts['crossings']+=len(context['paths']['lateral'])
 def variation(self):
  edges=[e['score'] for e in self.edges.values() if e['direction']=='lateral' and self.nodes[e['from']]['live'] and self.nodes[e['to']]['live']]
  return sum(1-v for v in edges)/len(edges) if edges else 0.
 def summary(self):return dict(self.counts,nodes=len(self.nodes),links=len(self.edges),active_streams=len({n['source'] for n in self.nodes.values() if n['live']}))
 def snapshot(self):return dict(schema=SCHEMA,nodes=copy.deepcopy(list(self.nodes.values())),edges=copy.deepcopy(list(self.edges.values())))
 def _restore(self,state):
  if type(state) is not dict or set(state)!={'schema','nodes','edges'} or state['schema']!=SCHEMA or type(state['nodes']) is not list or len(state['nodes'])>64 or type(state['edges']) is not list or len(state['edges'])>192:raise ValueError('invalid temporal bounds')
  if len(json.dumps(state,allow_nan=False))>150000:raise ValueError('temporal history exceeds allowance')
  for original in state['nodes']:
   if type(original) is not dict or set(original)!={'id','kind','source','epoch','stamp','evidence','features','measured','live'}:raise ValueError('invalid temporal fields')
   n=copy.deepcopy(original)
   if type(n['id']) is not str or re.fullmatch('[0-9a-f]{64}',n['id']) is None or n['id'] in self.nodes or n['kind']!='observation' or n['measured'] is not True or type(n['live']) is not bool or type(n['source']) is not str or not 1<=len(n['source'])<=96 or type(n['epoch']) is not int or not 0<=n['epoch']<2**64 or type(n['evidence']) is not str or re.fullmatch('[0-9a-f]{64}',n['evidence']) is None:raise ValueError('invalid temporal receipt')
   n['features']=features(n['features']);n['stamp']=stamp(n['stamp'])
   if n['stamp'] is None:raise ValueError('invalid temporal stamp')
   n['live']=False;self.nodes[n['id']]=n;self.seen[n['evidence']]=True
  for e in state['edges']:
   if type(e) is not dict or set(e)!={'from','to','direction','relation','score','tick_span'} or type(e['from']) is not str or type(e['to']) is not str or e['from'] not in self.nodes or e['to'] not in self.nodes or e['from']==e['to'] or e['direction'] not in DIRECTIONS or e['relation'] not in ('continuation','recall','similarity') or not number(e['score']):raise ValueError('invalid temporal link')
   expected=interval(self.nodes[e['from']]['stamp'],self.nodes[e['to']]['stamp'])
   if e['tick_span']!=expected or expected is not None and type(e['tick_span']) is not int:raise ValueError('inconsistent temporal interval')
   self.edges[e['from'],e['to'],e['direction'],e['relation']]=copy.deepcopy(e)
