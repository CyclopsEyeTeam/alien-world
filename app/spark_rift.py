"""Electrical rift: open text windows that fill only from real incoming charge.

Owner-requested 5 November 2026. Every place the rift writes on the field is an
open window. Nothing is scripted: no word bank, template, thought, dream or
private line reaches the field. A window takes form only from charge that
actually arrived — typed characters, Eye text, maths numerals, mist/API and
observer replies — cut and mixed at random. With no charge, windows stay empty.

The internal register, archives, timing, clocks and the save format are left
as they are; this layer only replaces the text a window carries on the bus.
"""
import random,re
from collections import deque

# Field text windows: fragments, the running line, discharge cycles, internal
# charge flicker, the mirror echo, continuation lines and returning (ghost)
# lines. Residue that arrived from outside is the charge itself and keeps it.
WINDOWS={'fragment_ready':36,'thought':56,'dream_scene':56,'private_thought':48,'self_continuation':56,'mirror_truth':32,
         'math_dream_seed':48,'residue':56}
POOL=64
BIT=48
WORD=24
NUMERAL=re.compile(r'[0-9][0-9.:/]*')
ACTIVE=None
MATH=('pi_chunk','scale_observation','scale_shift','numeric_pattern','constant_resonance','math_dream_seed')

def clean(text,limit=BIT):return ' '.join(str(text or '').split())[:limit]

def outside(name,body):
 """Charge that came from outside the rift, never from its own output."""
 if body.get('derived_learning') or body.get('replayed') or body.get('dreamed') or body.get('echo'):return False
 if name=='eye_sensory':return True
 if name=='residue':
  source=str(body.get('source') or '')
  return source=='api-residue' or source.startswith('eye:') or bool(body.get('dialogue'))
 return False

class SparkPool:
 def __init__(self,rng=None):
  self.rng=rng or random.Random();self.bits=deque(maxlen=POOL);self.typing='';self.counts=dict(charged=0,sparked=0,empty=0)
 def charge(self,text):
  text=clean(text)
  if text:self.bits.append(text);self.counts['charged']+=1
 def key(self,ch):
  ch=str(ch or '')[:1]
  if not ch or ch.isspace() or not ch.isprintable():self._flush()
  else:
   self.typing+=ch
   if len(self.typing)>=WORD:self._flush()
 def _flush(self):
  if self.typing:self.charge(self.typing);self.typing=''
 def feed(self,name,body):
  if name=='keystroke':self.key(body.get('ch'));return
  if name in MATH:
   digits=body.get('digits')
   if isinstance(digits,str) and NUMERAL.fullmatch(digits):self.charge(digits)
   for token in NUMERAL.findall(str(body.get('text') or ''))[:2]:self.charge(token)
   return
  if outside(name,body):self.charge(body.get('text'))
 def spark(self,limit):
  bits=list(self.bits)+([self.typing] if self.typing else [])
  if not bits:self.counts['empty']+=1;return ''
  rng=self.rng;parts=[]
  for bit in rng.sample(bits,min(len(bits),rng.choice((1,1,2,2,3)))):
   if len(bit)>3 and rng.random()<.5:
    size=rng.randint(3,len(bit));start=rng.randint(0,len(bit)-size);bit=bit[start:start+size]
   parts.append(bit.strip())
  text=clean(' '.join(part for part in parts if part),limit)
  self.counts['sparked' if text else 'empty']+=1
  return text
 def summary(self):return dict(self.counts,bits=len(self.bits))
 def window(self,name,body):
  """Replace one window's text with sparked charge, or leave it open."""
  # An empty source line stays an empty window. Outside residue is the charge
  # itself, and learned conclusions are computed readouts, not scripted words.
  if name not in WINDOWS or not body.get('text'):return body
  if name=='residue' and (outside(name,body) or body.get('derived_learning')):return body
  body=dict(body);body['text']=self.spark(WINDOWS[name]);body.pop('private_fragment',None)
  if 'token' in body:body['token']=self.spark(16)
  return body

def install(ns,pool=None):
 """Bind inside the language layer, so its register never re-voices a window."""
 if ns.get('SPARK_POOL') is not None:return ns['SPARK_POOL']
 global ACTIVE
 pool=pool or SparkPool();ns['SPARK_POOL']=pool;ACTIVE=pool;Base=ns['EventBus']
 class SparkBus(Base):
  def _emit(self,name,body):
   # A private fingerprint names internal charge for reactivation; it stays.
   body=pool.window(name,body)
   result=super()._emit(name,body);pool.feed(name,body);return result
 ns['EventBus']=SparkBus
 return pool
