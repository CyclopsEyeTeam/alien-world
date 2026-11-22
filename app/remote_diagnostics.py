"""Fixed scalar adapter observations, separate from native clocks and content."""
import math

REMOTE_COUNTS=('field_requests','field_successes','fallback_entries','fallback_frames',
 'handshake_failures','request_failures','validation_failures','notification_failures')
REMOTE_TIMES=('elapsed_ms','field_call_wall_ms','field_call_max_wall_ms')

def remote_field_fields(value):
 if (type(value) is not dict or type(value.get('schema')) is not int or value['schema']!=1 or
     value.get('scope')!='current_process' or type(value.get('token')) is not int or
     not 0<=value['token']<2**64):return {}
 result=dict(schema=1,scope='current_process',token=value['token'])
 for key in REMOTE_COUNTS:
  v=value.get(key)
  if type(v) is not int or not 0<=v<=1e24:return {}
  result[key]=v
 for key in REMOTE_TIMES:
  v=value.get(key)
  if type(v) not in (int,float) or not 0<=v<=1e24 or not math.isfinite(v):return {}
  result[key]=v
 if type(value.get('failed')) is not bool:return {}
 result['failed']=value['failed']
 return result

def snapshot(hook):
 if not callable(hook):return {}
 try:return remote_field_fields(hook())
 except Exception:return {}
