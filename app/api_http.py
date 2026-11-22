"""One bounded text-only HTTP attempt. No retries, redirects or environment proxy."""
import json,ssl,urllib.request,urllib.parse
from api_config import build_body
from mist_local import nanofable_complete
class ApiError(ValueError):pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*a,**kw):return None
def generate(config,key):
 if config.provider!='mist':return _generate(config,key)
 try:
  from mist import LOCAL_MIST_TOKEN
  if key!=LOCAL_MIST_TOKEN:raise ApiError('mist does not accept provider credentials')
  return _generate(config,key,lambda body:nanofable_complete(config,body))
 except ApiError:raise
 except Exception:raise ApiError('Local NanoFable mist unavailable') from None
def _generate(config,key,local=None):
 try:
  if not isinstance(key,str) or not 1<=len(key.encode())<=4096 or any(ord(c)<33 for c in key):raise ApiError('invalid key')
  body=build_body(config);url=config.url()
  if config.provider=='gemini':url=url.rstrip('/')+'/'+urllib.parse.quote(config.model.removeprefix('models/'),safe='')+':generateContent'
  if any(key in value for value in (config.prompt,config.utterance,config.model,url)):raise ApiError('key overlaps request material')
  headers={'Content-Type':'application/json','Accept':'application/json'}
  if config.provider=='mist':
   from mist import LOCAL_MIST_TOKEN
   if key!=LOCAL_MIST_TOKEN:raise ApiError('mist does not accept provider credentials')
  else:headers['x-goog-api-key' if config.provider=='gemini' else 'Authorization']=key if config.provider=='gemini' else 'Bearer '+key
  if config.provider=='anthropic':headers['anthropic-version']='2026-10-21'
  if config.provider=='mist':
   # Local NanoFable runs in a request-owned child; no HTTP request is made.
   raw=local(body)
   if len(raw)>65536:raise ApiError('provider response exceeds 64KiB')
  else:
   request=urllib.request.Request(url,json.dumps(body,ensure_ascii=False,separators=(',',':')).encode(),headers,method='POST')
   opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
   try:
    with opener.open(request,timeout=25) as response:
     raw=response.read(65537)
     if len(raw)>65536:raise ApiError('provider response exceeds 64KiB')
   except urllib.error.HTTPError as error:
    error.close();raise ApiError('provider rejected request') from None
  data=json.loads(raw)
  if config.provider=='gemini':
   candidates=data.get('candidates',[])
   if len(candidates)!=1:raise ApiError('expected one text response')
   parts=candidates[0]['content']['parts']
   if not parts or any(set(p)-{'text','thought'} or not isinstance(p.get('text'),str) or p.get('thought') for p in parts):raise ApiError('unsupported provider content')
   text=''.join(p['text'] for p in parts);model=data.get('modelVersion','')
  elif config.provider=='anthropic':
   parts=data.get('content')
   if data.get('type')!='message' or data.get('role')!='assistant' or data.get('stop_reason')=='tool_use' or not isinstance(parts,list) or not parts:raise ApiError('unsupported provider content')
   if any(not isinstance(p,dict) or p.get('type')!='text' or not isinstance(p.get('text'),str) or set(p)-{'type','text','citations'} for p in parts):raise ApiError('only plain text provider content is accepted')
   text=''.join(p['text'] for p in parts);model=data.get('model','')
  else:
   choices=data.get('choices',[])
   if len(choices)!=1:raise ApiError('expected one text response')
   message=choices[0]['message']
   if message.get('tool_calls') or message.get('function_call'):raise ApiError('tool responses are not accepted')
   text=message.get('content');model=data.get('model','')
  if not isinstance(text,str) or not 1<=len(text.strip().encode())<=4096:raise ApiError('provider text is empty or exceeds 4KiB')
  if not isinstance(model,str) or len(model.encode())>128 or any(ord(c)<32 for c in model):raise ApiError('invalid reported model')
  result={'text':text.strip(),'reported_model':model}
  if key in text or key in model:raise ApiError('provider reflected credential')
  return result
 except ApiError:raise
 except Exception:raise ApiError('request failed or unsupported response') from None
