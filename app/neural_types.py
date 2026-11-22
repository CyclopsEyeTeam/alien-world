"""Typed electrical measurements and expression receipts, not human meaning."""
import copy,hashlib,json,math,re
from world_clock import validate_stamp
UUID=re.compile(r'[0-9a-f]{32}\Z')
FEATURE_NAMES=('brightness','motion_energy','flicker_density','colour_dominance','hue_sin','hue_cos','saturation','persistence','attention_x','attention_y','attention_strength','dwell','change','density','edge','contrast')
def packed(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(value):return hashlib.sha256(packed(value)).hexdigest()
def uuid(value):
 if not isinstance(value,str) or UUID.fullmatch(value) is None:raise ValueError('invalid neural identity')
 return value
def number(value,low=0.,high=1.):
 if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:raise ValueError('invalid neural measurement')
 return float(value)
def counter(value):
 if type(value) is not int or not 0<=value<2**64:raise ValueError('invalid neural counter')
 return value
def validate_sensory(value,source):
 if source not in ('own_display','desktop','art'):raise ValueError('invalid sensory source')
 scope='mixed_unknown' if source=='desktop' else 'self'
 if value is None:value=dict(version=1,expression_ids=[],source_scope=scope,measurement='sampled_geometry_colour_change')
 if not isinstance(value,dict) or set(value)!={'version','expression_ids','source_scope','measurement'} or value['version']!=1 or type(value['version']) is not int or value['source_scope']!=scope or value['measurement']!='sampled_geometry_colour_change':raise ValueError('invalid sensory ancestry')
 ids=value['expression_ids']
 if not isinstance(ids,list) or len(ids)>8 or len(set(ids))!=len(ids):raise ValueError('invalid expression ancestry')
 for ident in ids:uuid(ident)
 return copy.deepcopy(value)
def validate_expression(value):
 fields={'event','version','output_id','runtime','world_id','stamp','expires_tick','kind','regions','marker','causal_spike_id','semantic_verification'}
 if not isinstance(value,dict) or set(value)!=fields or value['event']!='neural_expression' or value['version']!=1 or type(value['version']) is not int or value['semantic_verification']!='unknown':raise ValueError('invalid neural expression')
 for name in ('output_id','runtime','world_id'):uuid(value[name])
 stamp=validate_stamp(value['stamp'])
 if stamp is None or stamp['world_id']!=value['world_id'] or not stamp['tick']<counter(value['expires_tick'])<=stamp['tick']+32:raise ValueError('invalid neural expression lifetime')
 if value['kind'] not in ('weak','situated','mirror','approbation','root','dream'):raise ValueError('invalid neural expression kind')
 if value['causal_spike_id'] is not None:uuid(value['causal_spike_id'])
 if not isinstance(value['regions'],list) or not 1<=len(value['regions'])<=4:raise ValueError('invalid neural regions')
 for region in value['regions']:
  if not isinstance(region,dict) or set(region)!={'x','y','radius','strength','hue'}:raise ValueError('invalid neural region')
  for name in ('x','y','strength','hue'):number(region[name])
  number(region['radius'],.01,.3)
 marker=value['marker']
 if not isinstance(marker,dict) or set(marker)!={'tick_echo','chain_residue','continuity','grounding'}:raise ValueError('invalid grounding marker')
 if counter(marker['tick_echo'])!=stamp['slot']:raise ValueError('invalid tick echo')
 number(marker['chain_residue'])
 for name,limit in (('continuity',8),('grounding',16)):
  if not isinstance(marker[name],str) or len(marker[name])>limit or any(c not in '0123456789abcdef' for c in marker[name]):raise ValueError('invalid context marker')
 if len(packed(value))>4096:raise ValueError('expression exceeds allowance')
 return copy.deepcopy(value)
def validate_presented(value):
 required={'version','output_id','runtime','world_id','surface','stamp','render_tick','presented_ns'}
 if not isinstance(value,dict) or not required<=set(value) or set(value)-required-{'eye_runtime','display_sequence'} or value['version']!=1 or type(value['version']) is not int:raise ValueError('invalid presentation receipt')
 for name in ('output_id','runtime','world_id'):uuid(value[name])
 if value['surface'] not in ('field','eye'):raise ValueError('invalid presentation surface')
 stamp=validate_stamp(value['stamp'])
 if stamp is None or stamp['world_id']!=value['world_id'] or counter(value['render_tick'])<stamp['tick']:raise ValueError('invalid presentation clock')
 counter(value['presented_ns'])
 if 'display_sequence' in value:counter(value['display_sequence'])
 if 'eye_runtime' in value:uuid(value['eye_runtime'])
 if len(packed(value))>2048:raise ValueError('presentation exceeds allowance')
 return copy.deepcopy(value)
