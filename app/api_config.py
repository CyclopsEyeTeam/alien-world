"""Nonsecret provider preferences; request construction has explicit byte bounds."""
from dataclasses import dataclass,asdict,fields
from pathlib import Path
import hashlib,json,os,ipaddress,urllib.parse,tempfile,math,re
from world_clock import validate_stamp
PROMPT=Path(__file__).with_name('residue_prompt.txt').read_text(encoding='utf-8')
PRESETS={'openrouter':'https://openrouter.ai/api/v1/chat/completions','gemini':'https://generativelanguage.googleapis.com/v1beta/models/','openai':'https://api.openai.com/v1/chat/completions','anthropic':'https://api.anthropic.com/v1/messages','mist':'http://127.0.0.1/nanofable/v1/chat/completions'}
@dataclass(frozen=True)
class Config:
 provider:str='openrouter'
 endpoint:str=''
 model:str=''
 prompt:str=PROMPT
 allow_local_http:bool=False
 token_field:str='max_completion_tokens'
 utterance:str=''
 def url(self):
  return self.endpoint or PRESETS.get(self.provider,'')
 def validate(self,require_model=True):
  if self.provider not in (*PRESETS,'custom'):raise ValueError('unsupported provider')
  if type(self.allow_local_http) is not bool:raise ValueError('invalid local endpoint choice')
  if not all(isinstance(x,str) for x in (self.endpoint,self.model,self.prompt,self.token_field,self.utterance)):raise ValueError('invalid settings')
  u=urllib.parse.urlsplit(self.url())
  if not u.hostname or u.username is not None or u.password is not None or u.query or u.fragment or any(ch.isspace() for ch in self.url()) or len(self.url())>512:raise ValueError('invalid API endpoint')
  try:
   if u.port is not None and not 1<=u.port<=65535:raise ValueError('invalid port')
  except ValueError:raise ValueError('invalid API endpoint port') from None
  if u.scheme!='https':
   try:local=ipaddress.ip_address(u.hostname).is_loopback
   except ValueError:local=False
   if not (u.scheme=='http' and self.allow_local_http and local):raise ValueError('HTTPS required; local HTTP must be explicitly enabled')
  if (require_model and not self.model.strip()) or len(self.model.encode('utf-8'))>128 or any(ord(x)<32 for x in self.model):raise ValueError('choose a valid model ID')
  if self.provider=='gemini' and '/' in self.model.removeprefix('models/'):raise ValueError('use a Gemini model name, not a path')
  prompt_size=len(self.prompt.encode('utf-8'))
  if not 1<=prompt_size<=4096:raise ValueError('prompt must be 1..4096 bytes')
  if len(self.utterance.encode('utf-8'))>768 or any(ord(ch)<32 and ch not in '\n\t' for ch in self.utterance):raise ValueError('invalid runtime register utterance')
  if self.token_field not in ('max_tokens','max_completion_tokens'):raise ValueError('invalid token limit field')
  if self.provider=='mist':
   from mist import validate_mist_config
   validate_mist_config(self)
  return self
 def key_origin(self):
  self.validate(require_model=False);u=urllib.parse.urlsplit(self.url());return f'{u.scheme}://{u.hostname}:{u.port or (443 if u.scheme=="https" else 80)}'
 def key_binding(self):return hashlib.sha256((self.provider+'\n'+self.key_origin()).encode()).hexdigest()
 def prompt_hash(self):
  material=self.prompt if not self.utterance else json.dumps(dict(prompt=self.prompt,utterance=self.utterance),ensure_ascii=False,sort_keys=True,separators=(',',':'))
  return hashlib.sha256(material.encode()).hexdigest()

def language_authorization(value,world_id=None,segment_id=None):
 """Validate the engine's live grant; source authority is not a readiness proof."""
 fields={'mode','text','stamp','continuity','ready','score','threshold'}
 if not isinstance(value,dict) or set(value)!=fields:raise ValueError('language authorization unavailable')
 stamp=validate_stamp(value['stamp'])
 if stamp is None or (world_id is not None and stamp['world_id']!=world_id) or (segment_id is not None and stamp['segment_id']!=segment_id):raise ValueError('stale language authorization')
 if value['mode'] not in ('gift','dialogue','rehearsal') or type(value['ready']) is not bool:raise ValueError('invalid language mode')
 if not isinstance(value['text'],str) or len(value['text'].encode())>640 or any(ord(ch)<32 and ch not in '\n\t' for ch in value['text']):raise ValueError('invalid register speech')
 if not isinstance(value['continuity'],str) or re.fullmatch('[0-9a-f]{6}',value['continuity']) is None:raise ValueError('language continuity unavailable')
 for key in ('score','threshold'):
  if type(value[key]) not in (int,float) or not math.isfinite(value[key]) or not 0<=value[key]<=1:raise ValueError('invalid language sufficiency')
 if value['mode']=='dialogue' and (not value['ready'] or value['score']<=value['threshold'] or not value['text'].strip()):raise ValueError('alien language is not ready')
 if value['mode']=='gift' and value['ready']:raise ValueError('invalid gift authorization')
 return dict(value,stamp=stamp)

def build_body(c):
 c.validate()
 utterance=c.utterance if c.provider=='mist' else (c.utterance or 'Offer one new piece of material.')
 if c.provider=='mist':
  if not utterance.strip():raise ValueError('mist is waiting for Alien runtime speech')
  body={'model':c.model,'messages':[{'role':'system','content':c.prompt},{'role':'user','content':utterance}],'stream':False,'max_tokens':64,'chat_template_kwargs':{'enable_thinking':False}}
 elif c.provider=='gemini':
  body={'systemInstruction':{'parts':[{'text':c.prompt}]},'contents':[{'role':'user','parts':[{'text':utterance}]}],'generationConfig':{'maxOutputTokens':160}}
 elif c.provider=='anthropic':
  body={'model':c.model,'system':[{'type':'text','text':c.prompt}],'messages':[{'role':'user','content':utterance}],'stream':False,'max_tokens':160}
  # Haiku5.5 defaults to adaptive thinking; keep the small allowance for text.
  if c.model=='claude-haiku-5-5':body.update(thinking={'type':'disabled'},output_config={'effort':'low'})
 else:
  token_field='max_completion_tokens' if c.provider=='openai' else c.token_field
  body={'model':c.model,'messages':[{'role':'system','content':c.prompt},{'role':'user','content':utterance}],'stream':False,token_field:160}
  if c.provider=='openrouter':body['provider']={'allow_fallbacks':False}
  if c.provider=='openai' and c.model=='gpt-6-luna':body['reasoning_effort']='none'
 if len(json.dumps(body,ensure_ascii=False,separators=(',',':')).encode('utf-8'))>8192:raise ValueError('encoded request exceeds 8KiB')
 return body

def load_config(path):
 p=Path(path)
 if p.is_symlink():raise ValueError('settings must be a regular file')
 if not p.exists():return Config()
 if p.stat().st_size>16384:raise ValueError('settings file too large')
 raw=json.loads(p.read_text());allowed={f.name for f in fields(Config)}
 if not isinstance(raw,dict) or set(raw)-allowed:raise ValueError('unsupported settings fields; keys belong in keyring')
 if raw.get('utterance'):raise ValueError('runtime speech cannot be restored from settings')
 return Config(**raw).validate(require_model=False)

def save_config(path,c):
 c.validate(require_model=False);p=Path(path);p.parent.mkdir(parents=True,exist_ok=True,mode=0o700);p.parent.chmod(0o700)
 fd,temp=tempfile.mkstemp(prefix=p.name+'.',dir=p.parent)
 try:
  with os.fdopen(fd,'wb') as out:
   saved=asdict(c);saved.pop('utterance',None)
   out.write(json.dumps(saved,ensure_ascii=False).encode());out.flush();os.fsync(out.fileno())
  os.replace(temp,p)
 finally:
  if os.path.exists(temp):os.unlink(temp)
