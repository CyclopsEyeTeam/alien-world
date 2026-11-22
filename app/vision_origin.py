"""Typed local Eye evidence, separate from API source registration and truth."""
import json,math,re
SOURCES=('own_display','desktop','art')
REQUIRED={'kind','source','eye_runtime','runtime','world_id','sequence','epoch','perception_hash','measurement','semantic_verification'}
OPTIONAL={'display_sequence','render_tick'}
def validate_vision(value):
 if not isinstance(value,dict) or not REQUIRED<=set(value) or set(value)-REQUIRED-OPTIONAL:raise ValueError('invalid Eye source metadata')
 if value['kind']!='cyclops_eye' or value['source'] not in SOURCES or value['measurement']!='local_geometry_colour_change' or value['semantic_verification']!='unknown':raise ValueError('invalid Eye measurement status')
 for field in ('eye_runtime','runtime','world_id'):
  if not isinstance(value[field],str) or not re.fullmatch('[0-9a-f]{32}',value[field]):raise ValueError('invalid Eye source identity')
 for field in ('sequence','epoch',*OPTIONAL.intersection(value)):
  number=value[field]
  if type(number) is not int or not (1 if field in ('sequence','epoch') else 0)<=number<2**64:raise ValueError('invalid Eye source counter')
 if not isinstance(value['perception_hash'],str) or not re.fullmatch('[0-9a-f]{64}',value['perception_hash']):raise ValueError('invalid Eye perception hash')
 if len(json.dumps(value,ensure_ascii=False,allow_nan=False).encode())>2048:raise ValueError('Eye source metadata too large')
 return dict(value)

def validate_summary(text):
 if not isinstance(text,str) or not 1<=len(text.encode('utf-8'))<=4096:raise ValueError('Eye summary must be 1..4096 UTF-8 bytes')
 try:parsed=json.loads(text)
 except (ValueError,RecursionError):raise ValueError('Eye summary must be numeric JSON') from None
 if not isinstance(parsed,dict):raise ValueError('Eye summary must be a numeric JSON object')
 remaining=512
 def visit(value,depth):
  nonlocal remaining
  remaining-=1
  if depth>8 or remaining<0:raise ValueError('Eye summary structure exceeds bounds')
  if type(value) is int:return
  if type(value) is float:
   if not math.isfinite(value):raise ValueError('Eye summary numbers must be finite')
   return
  if isinstance(value,list):
   for child in value:visit(child,depth+1)
   return
  if isinstance(value,dict):
   for key,child in value.items():
    if not isinstance(key,str) or not 1<=len(key)<=64 or any(not 32<=ord(c)<127 for c in key):raise ValueError('Eye summary keys must be bounded ASCII')
    visit(child,depth+1)
   return
  raise ValueError('Eye summary values must be numbers, lists or objects')
 visit(parsed,0)
 return text

def label(source):
 if source not in SOURCES:raise ValueError('invalid Eye source')
 return 'Cyclops Eye · '+source

numeric_summary=validate_summary
