"""Source attribution is independent of semantic verification and native ticks."""
import json,re
LABEL='Floating signal · unknown'
def origin(provider,model,request_id,prompt_hash,reported_model=''):
 return validate_origin(dict(source_authority='unregistered_unknown',verification='unknown',provider=provider,requested_model=model,reported_model=reported_model,request_id=request_id,prompt_hash=prompt_hash))
def validate_origin(value):
 if not isinstance(value,dict) or set(value)!={'source_authority','verification','provider','requested_model','reported_model','request_id','prompt_hash'}:raise ValueError('invalid API origin')
 if value['source_authority']!='unregistered_unknown' or value['verification']!='unknown' or value['provider'] not in ('openrouter','gemini','custom','openai','anthropic','mist'):raise ValueError('invalid API authority')
 if not all(isinstance(v,str) for v in value.values()):raise ValueError('invalid API attribution')
 if not re.fullmatch('[0-9a-f]{32}',value['request_id']) or not re.fullmatch('[0-9a-f]{64}',value['prompt_hash']):raise ValueError('invalid API identifiers')
 for k in ('requested_model','reported_model'):
  if len(value[k].encode())>128 or any(ord(c)<32 for c in value[k]):raise ValueError('invalid model attribution')
 if len(json.dumps(value,ensure_ascii=False).encode())>768:raise ValueError('API attribution too large')
 return dict(value)
