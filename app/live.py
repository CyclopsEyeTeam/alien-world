#!/usr/bin/python3
"""Alien display with a continuing world and isolated fixture entrance."""
import argparse,json,time,signal
from pathlib import Path
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib,Gdk,Pango
from process import Worker
from stage_metrics import StageMetrics
from protocol import receive_latest,PacketError
from gpu import FieldSurface
from prep_process import read_packet,write_packet
from control_queue import SendQueue
from display import initial_geometry,grid_for_viewport
from neural_types import validate_expression,validate_presented,validate_sensory

class Window(Gtk.Window):
    def __init__(self,args):
        super().__init__(title='Alien World')
        self.set_wmclass('alien-world','AlienWorld')
        self.agent_observer=None;self.agent_observer_failed=False
        self.profile=StageMetrics()
        self.args=args;self.renderer='';self.message=None;self.watch=0;self.timer=0;self.stopped=False;self.error=None;self.notice='Starting hardware display…'
        self.dynamic_geometry=args.cols is None and args.rows is None
        if (args.cols is None)!=(args.rows is None):raise ValueError('explicit geometry requires both columns and rows')
        self.continuing=getattr(args,'world_data',None) is not None
        self.worker=Worker(args.world_data if self.continuing else args.sessions,continuous=self.continuing,cols=args.cols or 20,rows=args.rows or 8,fps=args.fps,content_cache=getattr(args,'content_cache',None))
        if not getattr(args,'content_cache',None):args.content_cache=self.worker.content_cache
        self.active_geometry=None;self.desired_geometry=None;self.resize_inflight=False;self.resize_timer=0
        self.control_watch=0;self.control_seq=0;self.requests={};self.callbacks={};self.world=None;self.latest_control=None;self.last_display_receipt=None;self.feed=None;self.api_panel=None
        self.world_clock_sequence=0
        self.living=None;self.diagnostics=None;self.last_received=None;self.report_busy=False
        self.control_writer=0;self.outgoing=SendQueue(lambda record:write_packet(self.worker.control,record))
        self.content_cache=None
        self.eye=None;self.eye_retiring=None;self.eye_requested=False
        self.neural_latest=None;self.neural_presentations={};self.neural_context=validate_sensory(None,'own_display')
        self.set_default_size(1120,680);self.set_size_request(500,320)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=0);self.add(box)
        header=Gtk.Box(spacing=8);header.set_border_width(6)
        self.header_label=Gtk.Label(label='Alien World');self.header_label.set_xalign(0);self.header_label.set_ellipsize(Pango.EllipsizeMode.END)
        header.pack_start(self.header_label,True,True,0)
        self.button=Gtk.Button(label='Sleep world' if self.continuing else 'Stop world');self.button.connect('clicked',lambda *_:self.stop('Sleeping until reopened' if self.continuing else 'Stopped by owner'))
        self.api_button=Gtk.Button(label='API material');self.api_button.connect('clicked',self.open_api);header.pack_end(self.api_button,False,False,0)
        from observer_interface import ObserverInterface
        self.observer_interface=ObserverInterface();self.observers_watch=0;self.observers_checks=0
        self.observers_button=Gtk.Button(label='Observers');self.observers_button.set_tooltip_text('Open the owner observation interface')
        self.observers_button.connect('clicked',self.open_observers);header.pack_end(self.observers_button,False,False,0)
        self.eye_button=Gtk.Button(label='Eye');self.eye_button.connect('clicked',self.toggle_eye)
        if getattr(args,'eye_root',None):header.pack_end(self.eye_button,False,False,0)
        header.pack_end(self.button,False,False,0);box.pack_start(header,False,False,0)
        self.report_button=Gtk.Button(label='Save report' if self.continuing else 'Save run report');self.report_button.set_tooltip_text('Save a shareable report of timings, memory and Living Buffer receiving; excludes keys and private content')
        self.report_button.connect('clicked',self.save_run_report);header.pack_end(self.report_button,False,False,0)
        self.display_overlay=Gtk.Overlay();box.pack_start(self.display_overlay,True,True,0)
        self.area=FieldSurface(self);self.area.connect('size-allocate',self.allocated);self.display_overlay.add(self.area)
        from rolling_text import RollingText
        self.rolling_text=RollingText(self.display_overlay)
        self.connect('destroy',self.close);self.connect('key-press-event',self.key)
        self.show_all();GLib.idle_add(self.start)
    def note(self,text,visible=False):
        self.notice=text;self.header_label.set_tooltip_text(text)
        if visible:self.header_label.set_text('Alien World · '+text)
    def open_observers(self,*_):
        error=self.observer_interface.open()
        if error:self.note(error,True);return
        # Startup feedback is optional, nonblocking, and bounded to five seconds
        # after the latest click; it never becomes a permanent idle poll.
        self.observers_checks=20
        if not self.observers_watch:self.observers_watch=GLib.timeout_add(250,self.check_observers)
    def check_observers(self):
        if not self.get_visible():self.observers_watch=0;return False
        running,error=self.observer_interface.check()
        if error:self.note(error,True)
        self.observers_checks-=1
        if not running or self.observers_checks<=0:self.observers_watch=0;return False
        return True
    def key(self,_window,event):
        if event.keyval==Gdk.KEY_Escape:self.destroy();return True
        return False
    def bind_content_cache(self):
        path=getattr(self.args,'content_cache',None)
        if not path or not self.world or not self.world.get('clock'):return
        world=self.world['clock']['world_id']
        if self.content_cache and self.content_cache.world_id==world:return
        if self.feed:self.feed.disable()
        if self.content_cache:self.content_cache.close();self.content_cache=None
        try:
            from async_cache import AsyncContentCache
            def dispatch(callback):
                def completed():callback();return False
                return GLib.idle_add(completed)
            self.content_cache=AsyncContentCache(path,world,dispatch=dispatch)
            if self.feed:
                self.feed.content_sink=self.content_cache.put;self.feed.content_flush=self.content_cache.flush
                self.feed.content_after_flush=self.content_cache.after_flush
        except Exception:self.note('Content storage unavailable; API and Eye are waiting',True)
    def api_admitted(self,record):
        if self.diagnostics:self.diagnostics.note_api('admitted')
        if not self.stopped:self.rolling_text.admitted(record)
    def diagnostic_draw(self,sequence,upload_ms,draw_ms):
        if self.diagnostics:self.diagnostics.note_draw(sequence,upload_ms=upload_ms,draw_ms=draw_ms)
    def diagnostic_sample(self):
        if not self.diagnostics:return
        try:
            state=self.living.statistics() if self.living else {}
            intake=(self.world or {}).get('buffer',{})
            state['learning']=(self.world or {}).get('learning',{})
            state['worker_profile']=(self.world or {}).get('worker_profile',{})
            state['remote_field']=(self.world or {}).get('remote_field',{})
            state['worker_archive']=(self.world or {}).get('archive',{})
            state['presentation_profile']=self.profile.snapshot()
            if self.area.gpu:state['presentation_profile'].update({'staging_'+k:v for k,v in self.area.gpu.workspace.summary().items() if k in ('allocations','reuses','bytes')});state['presentation_profile'].update({k:v for k,v in self.area.gpu.workspace.summary().items() if k in ('packed_frames','legacy_frames')})
            state['continuity']=(self.world or {}).get('continuity',{})
            state['intake']={key:value for key,value in intake.items() if key in ('pending','ready','retained','used_bytes','max_bytes','evicted_material','inflight','api_reserved')}
            state.update(control_pending=len(self.requests),control_outgoing=len(self.outgoing.pending),api_active=bool(self.feed and self.feed.active),quota_pending=self.feed.quota_pending if self.feed else 0)
            if self.agent_observer:state['observers']=self.agent_observer.participant_summary()
            if self.content_cache:state['archive']={key:value for key,value in self.content_cache.statistics().items() if key!='error'}
            eye_process=getattr(getattr(self.eye,'process',None),'process',None)
            extra={'preparer':(self.world or {}).get('preparer_pid'),'eye':getattr(eye_process,'pid',None)}
            self.diagnostics.sample(worker_pid=self.worker.process.pid if self.worker.process else None,helper_pid=getattr(self.living,'pid',None),buffer=state,extra_pids=extra)
        except Exception:pass
    def living_present(self,message):
        if self.stopped or (self.message and message.sequence<=self.message.sequence):return
        self.message=message;self.area.present(message);self.rolling_text.pulse(message)
    def living_failed(self,_reason):
        if self.stopped:return
        if self.last_received:self.living_present(self.last_received)
        self.note('Living Buffer unavailable; native display continues',True)
    def start_receiving(self):
        def dispatch(callback):
            def once():callback();return False
            return GLib.idle_add(once)
        try:
            from run_diagnostics import RunDiagnostics
            self.diagnostics=RunDiagnostics(self.worker.directory/'diagnostics',metadata={'release':'native-cycle-discovery-v1','living_buffer_revision':'64a17ae6f254640cce5f27ef4e5c787c98ea3f96'},continuous=self.continuing)
        except Exception:
            self.diagnostics=None
            if self.continuing:self.note('Saved diagnostic history unavailable; existing files preserved',True)
        try:
            from living_process import LivingReceiver
            self.living=LivingReceiver(dispatch,self.living_present,self.living_failed);self.living.start()
        except Exception:self.living_failed('unavailable')
    def save_run_report(self,*_):
        if self.report_busy:return
        if not self.diagnostics:
            self.report_result(None);return
        self.report_busy=True;self.report_button.set_sensitive(False)
        import threading
        session=self.worker.directory
        def work():
            result=None
            try:
                from analyse_run import analyse_session
                result=analyse_session(session,session.parent/'reports' if self.continuing else session/'reports')
            except Exception:pass
            def done():self.report_busy=False;self.report_button.set_sensitive(True);self.report_result(result);return False
            GLib.idle_add(done)
        threading.Thread(target=work,name='alien-report-export',daemon=True).start()
    def report_result(self,result):
        if not self.get_visible():return
        dialog=Gtk.MessageDialog(transient_for=self,modal=False,message_type=Gtk.MessageType.INFO,buttons=Gtk.ButtonsType.CLOSE,text='Run report saved' if result else 'Run report unavailable')
        if result:
            dialog.format_secondary_text('Send this ZIP here for investigation:\n'+str(result)+'\n\nIt contains timings and resource counts, without keys, messages or private thoughts.')
            dialog.add_button('Open folder',Gtk.ResponseType.APPLY)
        else:dialog.format_secondary_text('No diagnostic data is available yet, or the report could not be written. Alien continues running.')
        def response(widget,value):
            if value==Gtk.ResponseType.APPLY:
                from gi.repository import Gio
                try:Gio.AppInfo.launch_default_for_uri(Path(result).parent.as_uri(),None)
                except Exception:pass
            else:widget.destroy()
        dialog.connect('response',response);dialog.show_all()
    def ensure_eye(self):
        if self.stopped or not self.eye_requested or self.eye or not self.world or not self.world.get('clock'):return
        if getattr(self.args,'content_cache',None) and self.content_cache is None:return
        if self.eye_retiring:
            if not self.eye_retiring.link.can_reconnect:return
            self.eye_retiring=None
        try:
            from eye_companion import EyeCompanion
            self.eye=EyeCompanion(self,self.args.eye_root);self.eye_button.set_label('Disconnect Eye')
            if self.neural_latest:self.eye.expression(self.neural_latest)
        except Exception:self.eye_requested=False;self.note('Private Eye unavailable',True)
    def toggle_eye(self,*_):
        if self.eye:self.eye_requested=False;self.eye_disconnected('Private Eye disconnected')
        else:self.eye_requested=True;self.ensure_eye()
    def eye_disconnected(self,reason):
        self.eye_requested=False
        eye=self.eye;self.eye=None
        if eye:
            if not self.stopped:self.eye_retiring=eye
            eye.stop(cancel_buffer=not self.stopped)
        self.eye_button.set_label('Eye disconnecting…' if self.eye_retiring else 'Eye');self.eye_button.set_tooltip_text(reason)
        self.eye_button.set_sensitive(not self.stopped and not self.eye_retiring)
    def eye_retired(self,eye):
        if self.eye_retiring is eye:self.eye_retiring=None
        if not self.stopped:self.eye_button.set_label('Eye');self.eye_button.set_sensitive(True);self.ensure_eye()
    def eye_capture_due(self):return bool(self.eye and self.eye.link.capture_due())
    def eye_frame(self,png,meta):
        if self.eye:self.eye.link.frame(png,meta)
    def eye_capture_failed(self,reason):self.eye_button.set_tooltip_text('Eye capture skipped: '+reason)
    def neural_expression(self,record):
        if self.stopped:return False
        value=validate_expression(record)
        if not self.world:self.neural_latest=value;return False
        stamp=self.world.get('clock')
        if not stamp or value['runtime']!=self.world['runtime'] or value['world_id']!=stamp['world_id'] or value['stamp']['segment_id']!=stamp['segment_id'] or stamp['tick']>value['expires_tick']:return False
        self.neural_latest=value;accepted=self.area.expression(value)
        if self.eye:self.eye.expression(value)
        return accepted
    def neural_presented(self,record):
        if self.stopped:return False
        value=validate_presented(record);stamp=(self.world or {}).get('clock')
        if not stamp or value['runtime']!=self.world['runtime'] or value['world_id']!=stamp['world_id'] or value['stamp']['segment_id']!=stamp['segment_id']:return False
        self.neural_presentations[value['surface']]=value
        self.flush_neural_presentations();return True
    def flush_neural_presentations(self):
        if self.stopped:return
        for surface,record in list(self.neural_presentations.items()):
            if self.control_request('neural_presented',record=record):self.neural_presentations.pop(surface,None)
    def gpu_failed(self,_area):
        self.error='Hardware display failed';self.stop(self.error);return False
    def viewport_geometry(self):
        font=self.area.font
        if font is None:raise ValueError('Display font is not ready')
        return initial_geometry(self.args.cols,self.args.rows,self.area.get_allocated_width(),self.area.get_allocated_height(),font.cell_width,font.cell_height)
    def allocated(self,_area,_allocation):
        if not self.dynamic_geometry or self.stopped or not self.area.font:return
        if self.resize_timer:GLib.source_remove(self.resize_timer)
        self.resize_timer=GLib.timeout_add(60,self.resize_ready)
    def resize_ready(self):
        self.resize_timer=0
        if self.stopped:return False
        try:self.desired_geometry=self.viewport_geometry()
        except ValueError:
            self.note('Window exceeds supported cell geometry; no lower-detail grid was selected',True);return False
        self.send_resize();return False
    def send_resize(self):
        if self.stopped or not self.worker.process or self.resize_inflight or not self.desired_geometry or self.desired_geometry==self.active_geometry:return
        desired=self.desired_geometry
        def received(reply):
            self.resize_inflight=False
            if reply.get('ok'):
                self.active_geometry=desired
                if self.header_label.get_text().startswith('Alien World · Window exceeds'):self.header_label.set_text('Alien World')
                if self.desired_geometry!=desired:self.send_resize()
            else:self.note('Display resize was not accepted',True)
        self.resize_inflight=True
        if not self.control_request('resize',callback=received,cols=desired[0],rows=desired[1]):self.resize_inflight=False
    def start(self):
        if self.stopped:return False
        if self.area.failed or not self.area.gpu:
            self.error='Hardware display unavailable';self.stop(self.error);return False
        try:
            self.active_geometry=self.viewport_geometry();self.desired_geometry=self.active_geometry
            self.worker.cols,self.worker.rows=self.active_geometry
            self.worker.start()
            self.start_receiving()
            self.watch=GLib.io_add_watch(self.worker.socket.fileno(),GLib.IO_IN|GLib.IO_HUP|GLib.IO_ERR,self.incoming)
            self.control_watch=GLib.io_add_watch(self.worker.control.fileno(),GLib.IO_IN|GLib.IO_HUP|GLib.IO_ERR,self.control_incoming)
            self.timer=GLib.timeout_add(1000,self.refresh)
            print('START '+json.dumps({'renderer':self.renderer,'worker':self.worker.process.pid,'session':str(self.worker.session),'fps':self.args.fps,'geometry':self.active_geometry,'font':self.area.font.description}),flush=True)
        except Exception as error:self.error=str(error);self.stop('Startup failed: '+str(error))
        return False
    def incoming(self,_fd,condition):
        try:
            message=self.profile.call('receive',receive_latest,self.worker.socket,self.last_received.sequence if self.last_received else None,packed=True)
            if message:
                self.last_received=message
                if self.diagnostics:self.diagnostics.note_frame(message.sequence,message.tick,message.generation,message.timestamp,len(message.frame.cells[0]),len(message.frame.cells))
                if not self.living or not self.living.offer(message):self.living_present(message)
            if condition&(GLib.IO_HUP|GLib.IO_ERR):raise EOFError('worker disconnected')
        except (EOFError,OSError,PacketError) as error:
            self.watch=0;self.error=str(error);self.stop('Worker stopped: '+str(error));return False
        return True
    def open_api(self,*_):
        if self.stopped:return
        try:
            from api_ui import create_feed,Panel
            if self.feed is None:self.feed=create_feed(self,getattr(self.args,'api_data',None) or self.args.sessions.parent/'api-feed')
            if self.api_panel is None:self.api_panel=Panel(self,self.feed,(getattr(self.args,'api_data',None) or self.args.sessions.parent/'api-feed')/'config.json')
            self.api_panel.show_all();self.api_panel.present()
        except Exception:self.note('API settings unavailable; check key and allowance storage',True)
    def control_request(self,op,callback=None,**fields):
        if self.stopped or not self.worker.control:return None
        if len(self.requests)>=128 and op not in ('cancel_api','cancel_eye'):return None
        self.control_seq+=1;seq=self.control_seq
        if self.outgoing.put(dict(seq=seq,op=op,**fields)):
            self.requests[seq]=op
            if callback:self.callbacks[seq]=callback
            if op=='submit' and 'observer' in str(fields.get('source','')) and fields.get('text') and hasattr(self,'rolling_text'):
                try:self.rolling_text.admitted(dict(text=str(fields['text']),origin=dict(provider=str(fields['source']),reported_model='observer')))
                except Exception:pass
            if self.outgoing.pending and not self.control_writer:self.control_writer=GLib.io_add_watch(self.worker.control.fileno(),GLib.IO_OUT|GLib.IO_HUP|GLib.IO_ERR,self.flush_control)
            return seq
        self.note('Input channel busy; please retry');return None
    def flush_control(self,_fd,condition):
        try:
            if condition&(GLib.IO_HUP|GLib.IO_ERR):raise EOFError()
            if not self.outgoing.flush():return True
            self.control_writer=0;return False
        except (EOFError,OSError,ValueError):self.control_writer=0;self.stop('Input channel closed');return False
    def control_incoming(self,_fd,condition):
        try:
            for _ in range(8):
                message=read_packet(self.worker.control)
                if message is None:break
                if message.get('event')=='api_receipt':
                    if self.feed:self.feed.receipt(message)
                    continue
                if message.get('event')=='eye_receipt':
                    if self.eye:self.eye.link.receipt(message)
                    continue
                if message.get('event')=='alien_art':
                    if self.eye:self.eye.link.art(message)
                    continue
                if message.get('event')=='neural_expression':
                    self.neural_expression(message);continue
                self.latest_control=message;op=self.requests.pop(message.get('seq'),None)
                callback=self.callbacks.pop(message.get('seq'),None)
                if callback:callback(message);continue
                if not message.get('ok'):self.note(message.get('error','Input failed'));continue
                if op=='status':
                    self.world=message['result']
                    self.world_clock_sequence=message['seq']
                    if self.eye and self.world.get('clock'):self.eye.observe_clock(self.world['clock'],self.world_clock_sequence)
                    self.bind_content_cache()
                    if self.feed:self.feed.observe(self.world)
                    self.ensure_eye()
                    if self.neural_latest:self.neural_expression(self.neural_latest)
                    if self.eye and self.world.get('last_eye_receipt'):self.eye.link.receipt(self.world['last_eye_receipt'])
            if condition&(GLib.IO_HUP|GLib.IO_ERR):raise EOFError('input channel closed')
        except (EOFError,OSError,ValueError) as error:
            self.control_watch=0;self.error=str(error);self.stop(str(error));return False
        return True
    def ensure_agent_observer(self):
        if self.stopped or self.agent_observer is not None or self.agent_observer_failed:return
        try:
            from agent_observer_io import AgentObserverEndpoint,window_status
            if not window_status(self)['ready']:return
            self.agent_observer=AgentObserverEndpoint(lambda:window_status(self),self.control_request).start()
        except (OSError,ValueError,TypeError,AttributeError,ImportError):
            self.agent_observer_failed=True # Optional external observation never stops Alien.
    def refresh(self):
        if self.stopped:return False
        self.diagnostic_sample()
        self.flush_neural_presentations()
        if self.worker.process.poll() is not None:
            self.timer=0;self.stop('Worker exited');return False
        self.control_request('status');self.send_resize()
        if self.api_panel:self.api_panel.refresh()
        if self.message:
            m=self.message;age=time.monotonic()-m.timestamp
            self.note('%s · tick %d · generation %d · frame %d · %.1fs old'%(('Receiving' if age<2 else 'Waiting'),m.tick,m.generation,m.sequence,age))
        else:self.note('Waiting for the first fresh-state frame…')
        self.ensure_agent_observer()
        return True
    def stop(self,reason):
        if self.stopped:return
        self.stopped=True
        if self.agent_observer:
            observer=self.agent_observer;self.agent_observer=None
            try:observer.close()
            except Exception:pass # Optional observation cannot block native Stop/cancellation.
        self.diagnostic_sample()
        if self.feed:self.feed.close()
        allowance_error=self.feed.close_error if self.feed else None
        self.rolling_text.clear()
        self.neural_latest=None;self.neural_presentations.clear();self.area.clear_expression()
        if self.eye_retiring:self.eye_retiring.link.abandon_cancel();self.eye_retiring=None
        self.eye_disconnected('World stopped')
        if self.resize_timer:GLib.source_remove(self.resize_timer);self.resize_timer=0
        if self.control_writer:GLib.source_remove(self.control_writer);self.control_writer=0
        if self.watch:GLib.source_remove(self.watch);self.watch=0
        if self.timer:GLib.source_remove(self.timer);self.timer=0
        if self.control_watch:GLib.source_remove(self.control_watch);self.control_watch=0
        if self.living:self.living.close()
        self.worker.stop();self.button.set_sensitive(False);self.api_button.set_sensitive(False);self.eye_button.set_sensitive(False)
        self.note(reason+(' · '+self.worker.stop_error if self.worker.stop_error else '')+(' · '+allowance_error if allowance_error else ''),True)
        if self.content_cache:
            try:self.content_cache.close()
            except Exception:self.note('Content storage did not close cleanly',True)
            self.content_cache=None
        if self.api_panel:self.api_panel.refresh()
        if self.diagnostics:self.diagnostics.close('owner_stop' if self.error is None else 'application_error')
        print('STOP '+json.dumps({'reason':reason,'worker_exit':self.worker.process.poll() if self.worker.process else None,'forced':self.worker.forced,'stop_error':self.worker.stop_error,'last_sequence':self.message.sequence if self.message else 0,'drawn_sequence':self.area.drawn_sequence}),flush=True)
    def close(self,*_):self.stop('Window closed');Gtk.main_quit()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sessions',type=Path,default=Path(__file__).resolve().parents[1]/'sessions')
    parser.add_argument('--world-data',type=Path,help='Persistent Alien world; sleeps while closed')
    parser.add_argument('--api-data',type=Path,help='Private installation-wide API allowance and nonsecret settings')
    parser.add_argument('--keys-file',type=Path,help='Owner-provided local provider key file')
    parser.add_argument('--eye-root',type=Path,help='Private verified Cyclops Eye source copy')
    parser.add_argument('--content-cache',type=Path,help='Shared binary content archive')
    parser.add_argument('--cols',type=int,default=None,help='Explicit comparison grid; specify with --rows')
    parser.add_argument('--rows',type=int,default=None,help='Explicit comparison grid; specify with --cols')
    parser.add_argument('--fps',type=float,default=0,help='0 preserves original renderer cadence; positive values are an explicit experimental cap')
    args=parser.parse_args()
    if args.content_cache is None:args.content_cache=args.sessions.parent/'alien.cache'
    if args.world_data is None:args.world_data=args.content_cache.parent/'world'
    if (args.cols is None)!=(args.rows is None):parser.error('--cols and --rows must be supplied together')
    window=Window(args)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGTERM,lambda:(window.destroy(),False)[1])
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGINT,lambda:(window.destroy(),False)[1])
    try:Gtk.main()
    finally:window.worker.stop()
if __name__=='__main__':main()
