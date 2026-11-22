#!/usr/bin/python3
"""Owned Alien Eye companion. It observes and draws; it has no action or model API."""
import argparse,ctypes,os,resource,signal,socket,sqlite3,sys,time
from pathlib import Path

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 for name in ('fd','eye-root','runtime-root','runtime','world','eye-runtime'):
  parser.add_argument('--'+name,required=True,type=int if name=='fd' else Path if name in ('eye-root','runtime-root') else str)
 parser.add_argument('--content-cache',type=Path)
 args=parser.parse_args();resource.setrlimit(resource.RLIMIT_CORE,(0,0));os.umask(0o077)
 hard=resource.getrlimit(resource.RLIMIT_AS)[1];limit=768*1024*1024
 if hard!=resource.RLIM_INFINITY:limit=min(limit,hard)
 resource.setrlimit(resource.RLIMIT_AS,(limit,hard))
 parent=os.getppid();ctypes.CDLL(None).prctl(1,signal.SIGTERM)
 if parent==1 or os.getppid()!=parent:return 1
 root=args.runtime_root.resolve();eye_root=args.eye_root.resolve()
 if not root.is_dir() or not eye_root.is_dir() or not (eye_root/'cyclops_eye/loop.py').is_file():return 2
 # Reject a launcher that forgot its private HOME/XDG binding before importing Eye.
 for name in ('HOME','XDG_STATE_HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME'):
  value=os.environ.get(name)
  if not value or not Path(value).resolve().is_relative_to(root):return 2
 os.chdir(root);sys.path[:0]=[str(Path(__file__).resolve().parent),str(eye_root)]
 import gi,cairo
 gi.require_version('Gtk','3.0');gi.require_version('Gdk','3.0');from gi.repository import Gtk,Gdk,GLib
 from eye_ipc import recv,send
 from eye_runtime import EyeRuntime,wipe
 from neural_surface import paint_eye_expression
 from cyclops_eye.render_box import ThirdEyeBox
 from zilo_outside_look.x11_glimpse import X11Glimpser
 cache=None
 if args.content_cache is not None:
  from async_cache import AsyncContentCache
  def dispatch(callback):
   def run():callback();return False
   GLib.idle_add(run)
  cache=AsyncContentCache(args.content_cache,args.world,dispatch=dispatch)
 runtime=EyeRuntime(args.runtime,args.world,args.eye_runtime,cache=cache,neural_enabled=True);channel=socket.socket(fileno=args.fd);channel.setblocking(False)
 def start_colours():
  from infinite_colour import InfiniteColour
  before=resource.getrlimit(resource.RLIMIT_AS);options=os.environ.get('NODE_OPTIONS');provider=InfiniteColour.__new__(InfiniteColour)
  try:
   # V8 reserves address space independently of its bounded heap. It remains
   # inside the parent's unchanged aggregate 1GiB/no-swap application scope.
   resource.setrlimit(resource.RLIMIT_AS,(hard,hard));os.environ['NODE_OPTIONS']='--max-old-space-size=64'
   provider.__init__(timeout_s=2.0);return provider
  except Exception:
   process=getattr(provider,'process',None)
   if process is not None:
    try:
     if process.poll() is None:process.kill()
     process.wait(timeout=1)
     provider.close()
    except Exception:pass
   return None
  finally:
   resource.setrlimit(resource.RLIMIT_AS,before)
   if options is None:os.environ.pop('NODE_OPTIONS',None)
   else:os.environ['NODE_OPTIONS']=options

 class ImageView(Gtk.DrawingArea):
  def __init__(self,origin):
   super().__init__();self.origin=origin;self.surface=None;self.set_hexpand(True);self.set_vexpand(True);self.connect('draw',self.paint)
  def paint(self,widget,cr):
   cr.set_source_rgb(.025,.025,.035);cr.paint()
   if self.surface is None:return False
   w,h=widget.get_allocated_width(),widget.get_allocated_height();iw,ih=self.surface.get_width(),self.surface.get_height();scale=min(w/iw,h/ih)
   cr.translate((w-iw*scale)/2,(h-ih*scale)/2);cr.scale(scale,scale);cr.set_source_surface(self.surface,0,0);cr.paint()
   if widget.get_mapped():runtime.projection_presented(self.origin)
   return False
  def show_surface(self,surface):self.surface=surface;self.queue_draw()
 class Companion:
  def __init__(self):
   self.closing=False;self.cursor=0;self.desktop=None;self.desktop_epoch=0;self.desktop_failed=False;self.colours=start_colours();self.box=ThirdEyeBox(width=500,colours=self.colours,frame_ms=200)
   runtime.on_observation=self.observation_ready;runtime.on_archive_error=self.archive_failed
   self.eye_sequence=0;self.presentation=None
   self.window=Gtk.Window(title='Alien Eye');self.window.set_wmclass('alien-eye','AlienEye');self.window.set_default_size(900,640)
   outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4);self.window.add(outer)
   self.status=Gtk.Label(label='Local sight • shape, colour and change • no recognition or image uploads'+(' • native ink fallback' if self.colours is None else ''));self.status.set_line_wrap(True);self.status.set_margin_top(6);self.status.set_margin_bottom(6);outer.pack_start(self.status,False,False,0)
   self.tabs=Gtk.Notebook();outer.pack_start(self.tabs,True,True,0)
   self.alien=ImageView('own_display');self.art=ImageView('art');self.eye=Gtk.DrawingArea();self.eye.set_hexpand(True);self.eye.set_vexpand(True);self.eye.connect('draw',self.paint_eye)
   for title,widget in (('Alien',self.alien),('Artwork',self.art),('Eye',self.eye)):self.tabs.append_page(widget,Gtk.Label(label=title))
   self.window.connect('destroy',self.close);self.window.show_all()
   self.watch=GLib.io_add_watch(channel.fileno(),GLib.IO_IN|GLib.IO_HUP|GLib.IO_ERR,self.incoming)
   self.timer=GLib.timeout_add(1000,self.look)
   self.dwell_timer=GLib.timeout_add(200,self.dwell)
  def emit(self,record):
   try:return send(channel,record)
   except (OSError,ValueError):self.close();return False
  def paint_eye(self,widget,cr):
   if runtime.last_scene is None:
    cr.set_source_rgb(.025,.025,.035);cr.paint();runtime.expressions.receipt('eye',runtime.current_tick,eye_runtime=args.eye_runtime,visible=False)
    if widget.get_mapped():runtime.native_presented()
    return False
   size=widget.get_allocated_width(),widget.get_allocated_height();fraction=self.box.fraction()
   self.box.paint(cr,runtime.last_scene,fraction=fraction,size=size);self.eye_sequence+=1
   value=runtime.expressions.at(runtime.current_tick)
   visible=paint_eye_expression(cr,self.box,value,fraction,size)
   receipt=runtime.expressions.receipt('eye',runtime.current_tick,self.eye_sequence,eye_runtime=args.eye_runtime,visible=visible and widget.get_mapped())
   if widget.get_mapped():runtime.native_presented()
   if receipt is not None:
    self.presentation=receipt
    try:runtime.presented(receipt)
    except (ValueError,OSError,sqlite3.Error):self.emit(dict(event='status',runtime=args.runtime,world=args.world,eye_runtime=args.eye_runtime,status='cache_busy'))
   self.flush_presentation();return False
  def flush_presentation(self):
   if self.presentation is not None and self.emit(dict(event='neural_presented',runtime=args.runtime,world=args.world,eye_runtime=args.eye_runtime,record=self.presentation)):self.presentation=None
  def incoming(self,_fd,condition):
   try:
    for _ in range(4):
     item=recv(channel)
     if item is None:break
     record,blob=item
     if record.get('op')=='stop':self.close();return False
     try:
      if record.get('op')=='world_clock':
       if blob is not None:raise ValueError('native clock cannot contain image data')
       if runtime.observe_clock(record):self.eye.queue_draw()
       continue
      if record.get('op')=='neural_expression':
       if blob is not None:raise ValueError('expression cannot contain image data')
       if runtime.expression(record.get('record')):self.eye.queue_draw()
       continue
      before_frame=runtime.last_frame_tick;origin=runtime.offer(record,blob)
      if runtime.known_clock is None and before_frame is not None and runtime.last_frame_tick<before_frame:self.desktop_epoch+=1;self.eye.queue_draw()
      surface=runtime.latest[origin][0]
      (self.alien if origin=='own_display' else self.art).show_surface(surface)
     except ValueError:
      self.emit(dict(event='status',runtime=args.runtime,world=args.world,eye_runtime=args.eye_runtime,status='input_refused'))
    if condition&(GLib.IO_HUP|GLib.IO_ERR):self.close();return False
   except (EOFError,OSError,ValueError):self.close();return False
   return not self.closing
  def desktop_look(self):
   geometry=(Gdk.Display.get_default().get_primary_monitor() or Gdk.Display.get_default().get_monitor(0)).get_geometry();dimensions=geometry.width,geometry.height
   if self.desktop is None or dimensions!=(self.desktop.width,self.desktop.height):
    if self.desktop:
     for surface in (*self.desktop._server,*self.desktop.surfaces()):wipe(surface)
    self.desktop=X11Glimpser();self.desktop_epoch+=1
   captured=time.monotonic_ns();glimpse=self.desktop.glimpse();return runtime.look_desktop(glimpse,captured,self.desktop_epoch)
  def observation_ready(self,observation):
   if not self.closing:self.emit(observation)
  def archive_failed(self,_error):
   if not self.closing:self.emit(dict(event='status',runtime=args.runtime,world=args.world,eye_runtime=args.eye_runtime,status='cache_unavailable'))
  def look(self):
   if self.closing:return False
   if runtime.observation_pending:return True
   order=('own_display','desktop','art');chosen=None
   # An art event is rare and expires just like a frame; take a new one promptly.
   art=runtime.latest.get('art')
   if art and not art[1].get('_measured'):chosen='art'
   else:
    for offset in range(3):
     index=(self.cursor+offset)%3;name=order[index];item=runtime.latest.get(name)
     if (name=='desktop' and not self.desktop_failed) or (item is not None and not item[1].get('_measured')):chosen=name;self.cursor=(index+1)%3;break
   if chosen is None:return True
   try:
    observation=self.desktop_look() if chosen=='desktop' else runtime.look_source(chosen)
    if observation or runtime.observation_pending:
     source=runtime.sources[chosen];self.box.observe(source.eye.state,source.scene);self.eye.queue_draw();self.status.set_text('Last local look • '+chosen.replace('_',' ')+' • meaning unknown'+(' • native ink fallback' if self.colours is None else ''))
     if observation:self.emit(observation)
   except Exception as error:
    from content_cache import CacheBusy
    if isinstance(error,CacheBusy):
     self.emit(dict(event='status',runtime=args.runtime,world=args.world,eye_runtime=args.eye_runtime,status='cache_busy'));return not self.closing
    if chosen=='desktop':self.desktop_failed=True
    self.emit(dict(event='status',runtime=args.runtime,world=args.world,eye_runtime=args.eye_runtime,status=chosen+'_unavailable'))
   return not self.closing
  def dwell(self):
   if self.closing:return False
   self.flush_presentation()
   source=runtime.sources.get(runtime.last_source)
   if source is not None:
    # Native dwell animates held evidence. It creates no new capture, receipt,
    # external observation, or Alien heartbeat.
    source.scene=source.eye.dwell();runtime.last_scene=source.scene;self.box.observe(source.eye.state,source.scene);self.eye.queue_draw()
   return True
  def close(self,*_):
   if self.closing:return
   self.closing=True
   for name in ('watch','timer','dwell_timer'):
    ident=getattr(self,name,0)
    if ident:GLib.source_remove(ident);setattr(self,name,0)
   if self.desktop:
    for surface in (*self.desktop._server,*self.desktop.surfaces()):wipe(surface)
   self.alien.surface=None;self.art.surface=None;runtime.close()
   if self.colours is not None:
    try:self.colours.close()
    except Exception:pass
   cache_flushed=runtime.cache_flushed
   if cache is not None:
    try:cache.close()
    except (ValueError,OSError,sqlite3.Error):cache_flushed=False
   try:send(channel,dict(event='closed',runtime=args.runtime,world=args.world,eye_runtime=args.eye_runtime,cache_flushed=cache_flushed))
   except (OSError,ValueError):pass
   self.window.hide();Gtk.main_quit()
 companion=Companion()
 GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGTERM,lambda:(companion.close(),False)[1])
 GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGINT,lambda:(companion.close(),False)[1])
 companion.emit(dict(event='ready',runtime=args.runtime,world=args.world,eye_runtime=args.eye_runtime,colour_backend='infinite' if companion.colours is not None else 'ink',colour_pid=companion.colours.process.pid if companion.colours is not None else None))
 try:Gtk.main()
 finally:companion.close();channel.close()
 return 0
if __name__=='__main__':raise SystemExit(main())
