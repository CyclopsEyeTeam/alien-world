"""Local provider settings and async request driver for the existing GTK window."""
from pathlib import Path
from gi.repository import Gtk,GLib
from api_config import Config,PRESETS,load_config,save_config
from api_feed import Feed
from async_quota import QuotaWorker
from api_process import RequestProcess
import json,os,tempfile
DIRECT_DEFAULTS={'mode':'both','openai_model':'gpt-6-luna','anthropic_model':'claude-haiku-5-5','prompt':Config().prompt,'mist_enabled':bool(os.environ.get('ALIEN_NANOFABLE_ROOT'))}
def direct_configs(settings):
 if settings['mode'] not in ('both','openai','anthropic','mist'):raise ValueError('invalid provider selection')
 enabled=settings.get('mist_enabled',True)
 if type(enabled) is not bool:raise ValueError('invalid mist selection')
 providers=('openai','anthropic') if settings['mode']=='both' else (() if settings['mode']=='mist' else (settings['mode'],))
 configs=[Config(provider=p,model=settings[p+'_model'],prompt=settings['prompt']).validate() for p in providers]
 if enabled or settings['mode']=='mist':
  from mist import mist_config
  configs.append(mist_config())
 return configs

def load_direct(path):
 p=Path(path)
 if not p.exists():return dict(DIRECT_DEFAULTS)
 if p.is_symlink() or not p.is_file() or p.stat().st_size>16384:raise ValueError('invalid provider settings')
 data=json.loads(p.read_text());legacy=set(DIRECT_DEFAULTS)-{'mist_enabled'}
 if not isinstance(data,dict) or set(data) not in (legacy,set(DIRECT_DEFAULTS)):raise ValueError('invalid provider settings')
 # Legacy owner files gain the opted-in source in RAM. Only Save writes settings.
 data=dict(data);data.setdefault('mist_enabled',True);direct_configs(data);return data
def save_direct(path,data):
 direct_configs(data);p=Path(path);p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 fd,temp=tempfile.mkstemp(prefix='direct-',dir=p.parent)
 try:
  with os.fdopen(fd,'w') as out:json.dump(data,out,ensure_ascii=False);out.flush();os.fsync(out.fileno())
  os.replace(temp,p)
 finally:
  if os.path.exists(temp):os.unlink(temp)

class GLibJob:
 def __init__(self,config,key,callback):
  self.process=RequestProcess(config,key);self.callback=callback
  # Poll only while this short-lived helper exists; zero polling when idle.
  self.timer=GLib.timeout_add(100,self.poll)
 def poll(self):
  answer=self.process.poll()
  if answer is None:return True
  self.timer=0;self.callback(answer);return False
 def cancel(self):self.process.cancel()
 def close(self):
  if self.timer:GLib.source_remove(self.timer);self.timer=0
  self.process.cancel()
  import subprocess
  try:self.process.process.wait(timeout=.5)
  except subprocess.TimeoutExpired:self.process.process.kill();self.process.process.wait(timeout=1)
  answer=self.process.poll();self.callback(answer)
class GLibDriver:
 def start(self,config,key,callback):return GLibJob(config,key,callback)
def later(delay,cb):
 def wake():cb();return False
 return GLib.timeout_add(max(1,int(delay*1000+1)),wake)

class LegacyPanel(Gtk.Dialog):
 def __init__(self,window,feed,path):
  super().__init__(title='API material',transient_for=window,flags=0)
  self.feed=feed;self.path=Path(path);self.loading=True;self.set_default_size(700,580)
  self.connect('delete-event',lambda *_:(self.hide(),True)[1]);self.connect('destroy',self.cleanup)
  grid=Gtk.Grid(column_spacing=12,row_spacing=10);grid.set_border_width(16);self.get_content_area().add(grid)
  label=Gtk.Label(label='Floating signal · unknown');label.set_xalign(0);grid.attach(label,0,0,2,1)
  explain=Gtk.Label(label='Off at each new world. 33 attempts per rolling hour, shared across providers.\nFailed and cancelled calls count. Your provider may charge for requests.');explain.set_xalign(0);explain.set_line_wrap(True);grid.attach(explain,0,1,2,1)
  self.provider=Gtk.ComboBoxText()
  for value,name in (('openrouter','OpenRouter'),('gemini','Gemini'),('custom','Custom OpenAI-compatible')):self.provider.append(value,name)
  self.endpoint=Gtk.Entry();self.endpoint.set_max_length(512);self.model=Gtk.Entry();self.model.set_max_length(128)
  self.local=Gtk.CheckButton(label='Allow HTTP for a literal loopback address')
  self.tokens=Gtk.ComboBoxText();self.tokens.append('max_completion_tokens','max_completion_tokens');self.tokens.append('max_tokens','max_tokens')
  self.key=Gtk.Entry();self.key.set_visibility(False);self.key.set_input_purpose(Gtk.InputPurpose.PASSWORD);self.key.set_max_length(4096);self.key.set_placeholder_text('New key • stored only in the system keyring')
  for row,title,widget in ((2,'Provider',self.provider),(3,'Endpoint',self.endpoint),(4,'Model ID',self.model),(5,'Custom token field',self.tokens),(7,'Key',self.key)):
   text=Gtk.Label(label=title);text.set_xalign(0);grid.attach(text,0,row,1,1);grid.attach(widget,1,row,1,1)
  grid.attach(self.local,1,6,1,1)
  self.save_key=Gtk.Button(label='Save key in system keyring');self.save_key.connect('clicked',self.store_key);grid.attach(self.save_key,1,8,1,1)
  self.prompt=Gtk.TextView();self.prompt.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
  scroll=Gtk.ScrolledWindow();scroll.set_min_content_height(150);scroll.add(self.prompt);grid.attach(scroll,0,9,2,1)
  buttons=Gtk.Box(spacing=8)
  self.save=Gtk.Button(label='Save settings');self.save.connect('clicked',lambda *_:self.apply())
  self.toggle=Gtk.Button(label='Enable feed');self.toggle.connect('clicked',self.toggle_feed)
  self.once=Gtk.Button(label='Request one');self.once.connect('clicked',lambda *_:(self.feed.request(),self.refresh()))
  self.reset=Gtk.Button(label='Reset allowance');self.reset.connect('clicked',lambda *_:(self.feed.reset_allowance(),self.refresh()))
  for b in (self.save,self.toggle,self.once,self.reset):buttons.pack_start(b,False,False,0)
  grid.attach(buttons,0,10,2,1);self.status=Gtk.Label();self.status.set_xalign(0);self.status.set_line_wrap(True);grid.attach(self.status,0,11,2,1)
  c=feed.config;self.provider.set_active_id(c.provider);self.endpoint.set_text(c.endpoint);self.model.set_text(c.model);self.tokens.set_active_id(c.token_field);self.local.set_active(c.allow_local_http);self.prompt.get_buffer().set_text(c.prompt)
  self.provider.connect('changed',self.provider_changed)
  for w in (self.endpoint,self.model,self.tokens,self.local,self.key):w.connect('toggled' if w is self.local else 'changed',self.edited)
  self.prompt.get_buffer().connect('changed',self.edited);self.loading=False;self.refresh()
 def cleanup(self,*_):self.key.set_text('')
 def edited(self,*_):
  if not self.loading:self.feed.disable();self.feed.message='Settings edited • save before enabling';self.refresh()
 def provider_changed(self,*_):
  self.endpoint.set_text('');self.edited()
 def config(self):
  b=self.prompt.get_buffer();text=b.get_text(b.get_start_iter(),b.get_end_iter(),False)
  return Config(provider=self.provider.get_active_id(),endpoint=self.endpoint.get_text().strip(),model=self.model.get_text().strip(),prompt=text,allow_local_http=self.local.get_active(),token_field=self.tokens.get_active_id()).validate(require_model=False)
 def apply(self):
  try:
   c=self.config();key=self.key.get_text()
   if key and (key in c.prompt or key in c.model or key in c.url()):raise ValueError('Key overlaps settings; remove it from the prompt or endpoint')
   save_config(self.path,c);self.feed.configure(c);self.feed.message='Settings saved • feed off';self.refresh();return True
  except (ValueError,OSError):self.feed.message='Settings not saved • check endpoint, prompt and model';self.refresh();return False
 def toggle_feed(self,*_):
  if self.feed.enabled:self.feed.disable()
  elif self.apply():self.feed.enable()
  self.refresh()
 def store_key(self,*_):
  key=self.key.get_text()
  if not key or len(key.encode())>4096 or any(ord(c)<33 for c in key):self.feed.message='Enter a valid key to save';self.refresh();return
  if not self.apply():return
  self.save_key.set_sensitive(False);self.feed.message='Saving key in system keyring…';self.refresh()
  def done(error):
   self.key.set_text('');self.save_key.set_sensitive(True);self.feed.message=error or 'Key saved • feed off';self.refresh()
  try:self.feed.keys.save(self.feed.config,key,done)
  except Exception:done('Keyring unavailable; key was not saved')
 def refresh(self):
  self.status.set_text(self.feed.status_text());self.toggle.set_label('Disable feed' if self.feed.enabled else 'Enable feed');self.toggle.set_sensitive(not self.feed.closed);self.once.set_sensitive(self.feed.enabled and self.feed.active is None and not self.feed.quota_pending and not self.feed.reset_pending);self.reset.set_sensitive(not self.feed.closed and self.feed.active is None and not self.feed.quota_pending and not self.feed.reset_pending);self.endpoint.set_placeholder_text(PRESETS.get(self.provider.get_active_id(),'https://…/v1/chat/completions'))

def create_feed(window,directory,keys=None,driver=None):
 directory=Path(directory)
 if keys is None:
  key_file=getattr(window.args,'keys_file',None)
  if key_file:
   from file_keys import FileKeys
   keys=FileKeys(key_file)
  else:
   from api_keys import Keyring
   keys=Keyring(directory)
 cache=getattr(window,'content_cache',None)
 if getattr(window.args,'content_cache',None) and cache is None:raise ValueError('content cache is not ready')
 # Validate local controls before creating the long-lived accounting worker.
 # A rejected settings file must not leave an orphan background thread.
 settings=load_direct(directory/'direct.json') if hasattr(keys,'source_label') else None
 configs=direct_configs(settings) if settings is not None else (load_config(directory/'config.json'),)
 def dispatch(callback):
  def once():callback();return False
  return GLib.idle_add(once,priority=GLib.PRIORITY_DEFAULT)
 quota=QuotaWorker(directory,dispatch=dispatch)
 feed=Feed(quota,keys,driver or GLibDriver(),window.control_request,later,GLib.source_remove,content_sink=cache.put if cache else None,content_flush=cache.flush if cache else None,on_admitted=getattr(window,'api_admitted',None),content_after_flush=cache.after_flush if cache and getattr(cache,'background_writer',False) else None)
 diagnostic=getattr(window,'diagnostics',None)
 if diagnostic:feed.on_diagnostic=diagnostic.note_api
 if settings is not None:feed.direct_settings=settings
 feed.configure_many(configs)
 if window.world:feed.observe(window.world)
 return feed

class DirectPanel(Gtk.Dialog):
 def __init__(self,window,feed,path):
  super().__init__(title='API material',transient_for=window,flags=0)
  self.feed=feed;self.path=Path(path).with_name('direct.json');self.loading=True;self.set_default_size(680,480)
  self.connect('delete-event',lambda *_:(self.hide(),True)[1])
  grid=Gtk.Grid(column_spacing=12,row_spacing=10);grid.set_border_width(16);self.get_content_area().add(grid)
  info=Gtk.Label(label='Floating signal · unknown\n33 total attempts per rolling hour. Feed starts off in each new world.');info.set_line_wrap(True);info.set_xalign(0);grid.attach(info,0,0,2,1)
  key_label=Gtk.Label(label=feed.keys.source_label);key_label.set_xalign(0);key_label.set_line_wrap(True);grid.attach(key_label,0,1,2,1)
  self.mode=Gtk.ComboBoxText()
  for value,label in (('both','Alternate OpenAI and Anthropic'),('openai','OpenAI only'),('anthropic','Anthropic only'),('mist','Alien reaches local NanoFable only')):self.mode.append(value,label)
  self.openai_model=Gtk.Entry();self.anthropic_model=Gtk.Entry()
  for row,label,widget in ((2,'Sources',self.mode),(3,'OpenAI model',self.openai_model),(4,'Anthropic model',self.anthropic_model)):
   text=Gtk.Label(label=label);text.set_xalign(0);grid.attach(text,0,row,1,1);grid.attach(widget,1,row,1,1)
  self.openai_model.set_max_length(128);self.anthropic_model.set_max_length(128)
  self.prompt=Gtk.TextView();self.prompt.set_wrap_mode(Gtk.WrapMode.WORD_CHAR);scroll=Gtk.ScrolledWindow();scroll.set_min_content_height(170);scroll.add(self.prompt);grid.attach(scroll,0,5,2,1)
  self.mist=Gtk.CheckButton(label='Allow Alien to reach local NanoFable mist');self.mist.set_active(feed.direct_settings.get('mist_enabled',True));grid.attach(self.mist,0,6,2,1)
  row=Gtk.Box(spacing=8)
  self.save=Gtk.Button(label='Save settings');self.save.connect('clicked',lambda *_:self.apply())
  self.toggle=Gtk.Button(label='Enable feed');self.toggle.connect('clicked',self.toggle_feed)
  self.once=Gtk.Button(label='Request one');self.once.connect('clicked',lambda *_:(feed.request(),self.refresh()))
  self.reset=Gtk.Button(label='Reset allowance');self.reset.connect('clicked',lambda *_:(self.feed.reset_allowance(),self.refresh()))
  for b in (self.save,self.toggle,self.once,self.reset):row.pack_start(b,False,False,0)
  grid.attach(row,0,7,2,1);self.status=Gtk.Label();self.status.set_xalign(0);self.status.set_line_wrap(True);grid.attach(self.status,0,8,2,1)
  settings=feed.direct_settings;self.mode.set_active_id(settings['mode']);self.openai_model.set_text(settings['openai_model']);self.anthropic_model.set_text(settings['anthropic_model']);self.prompt.get_buffer().set_text(settings['prompt'])
  for w in (self.mode,self.openai_model,self.anthropic_model,self.prompt.get_buffer()):w.connect('changed',self.edited)
  self.mist.connect('toggled',self.edited)
  self.loading=False;self.refresh()
 def edited(self,*_):
  if not self.loading:
   if self.mode.get_active_id()=='mist' and not self.mist.get_active():
    self.loading=True;self.mist.set_active(True);self.loading=False
   self.feed.disable();self.feed.message='Settings edited • save before enabling';self.refresh()
 def apply(self):
  b=self.prompt.get_buffer();settings=dict(mode=self.mode.get_active_id(),openai_model=self.openai_model.get_text().strip(),anthropic_model=self.anthropic_model.get_text().strip(),prompt=b.get_text(b.get_start_iter(),b.get_end_iter(),False),mist_enabled=self.mist.get_active())
  try:
   configs=direct_configs(settings)
   # Do not accidentally persist a folder credential pasted into a prompt/model.
   if any(c.provider!='mist' for c in configs) and hasattr(self.feed.keys,'path'):
    from file_keys import read_keys
    secrets=read_keys(self.feed.keys.path).values()
    if any(secret in value for secret in secrets for value in settings.values() if isinstance(value,str)):raise ValueError()
   save_direct(self.path,settings);self.feed.configure_many(configs);self.feed.direct_settings=settings;self.feed.message='Settings saved • feed off';self.refresh();return True
  except (ValueError,OSError):self.feed.message='Settings not saved • check models, prompt and local key file';self.refresh();return False
 def toggle_feed(self,*_):
  if self.feed.enabled:self.feed.disable()
  elif self.apply():self.feed.enable()
  self.refresh()
 def refresh(self):
  self.status.set_text(self.feed.status_text());self.toggle.set_label('Disable feed' if self.feed.enabled else 'Enable feed');self.toggle.set_sensitive(not self.feed.closed and not self.feed.reset_pending);self.once.set_sensitive(self.feed.enabled and self.feed.active is None and not self.feed.quota_pending and not self.feed.reset_pending);self.reset.set_sensitive(not self.feed.closed and self.feed.active is None and not self.feed.quota_pending and not self.feed.reset_pending);self.mist.set_sensitive(self.mode.get_active_id()!='mist')

def Panel(window,feed,path):return DirectPanel(window,feed,path) if hasattr(feed.keys,'source_label') else LegacyPanel(window,feed,path)
