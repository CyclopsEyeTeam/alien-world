"""Native hive with explicit continuing-world or fresh fixture storage."""
import argparse,asyncio,os,resource,signal,socket,time,uuid
from pathlib import Path
from reference import load_reference,capture_cells
from fast_cells import renderer_class
from protocol import Emitter,send_frame,_geometry
from pacing import Pacer

def run(fd,session,cols,rows,fps,control_fd=None,content_cache=None,continuing=False):
    _geometry(cols,rows)
    session=Path(session)
    if not session.is_dir() or session.is_symlink() or (not continuing and any(session.iterdir())):raise ValueError('fresh empty candidate session required')
    if continuing and any(p.is_symlink() or not p.is_file() or p.name!='preparer.log' for p in session.iterdir()):raise ValueError('Unsupported files in continuing runtime directory')
    os.chmod(session,0o700)
    if content_cache is None:raise ValueError('an explicit shared content cache path is required')
    stop_requested=[False]
    previous={number:signal.getsignal(number) for number in (signal.SIGTERM,signal.SIGINT)}
    def defer_stop(_number,_frame):stop_requested[0]=True
    try:
        for number in previous:signal.signal(number,defer_stop)
        import runpy
        active=Path(__file__).with_name('aura_hive.py')
        ns=runpy.run_path(str(active),run_name='alien_active_hive')['RenderAgent']._frame.__globals__
        capture_cells(ns)
        from async_cache import AsyncContentCache
        from native_cache import install as install_cache
        from contextlib import nullcontext
        from continuity import WorldLease
        with WorldLease(content_cache) if continuing else nullcontext() as lease:
            with AsyncContentCache(content_cache,lease.world_id if lease else uuid.uuid4().hex) as cache:
                try:
                    if stop_requested[0]:return
                    ns['_ENGINE_STOP_REQUESTED']=lambda:stop_requested[0]
                    ns['_CONTINUOUS_WORLD']=continuing
                    install_cache(ns,session,cache)
                    if continuing:
                        from continuity import wake_state,bootstrap_world
                        bootstrap_world(ns,cache,lease.world_id)
                        lifecycle=wake_state(cache,lease.stamp);cache.flush()
                    result=_run_cached(fd,session,cols,rows,fps,control_fd,ns,cache)
                    if continuing:cache.set_json('world.lifecycle','v1',dict(lifecycle,state='asleep',stamp=cache.get_json('native.state','world-clock.json')['stamp']));cache.flush()
                    return result
                finally:
                    # asyncio removes the native handlers when its loop closes.
                    # Keep a repeated Stop from interrupting the final cache drain.
                    for number in previous:signal.signal(number,defer_stop)
    finally:
        for number,handler in previous.items():signal.signal(number,handler)

def _run_cached(fd,session,cols,rows,fps,control_fd,ns,cache):
    # Both environment and function seams keep this candidate offline.
    for key in ('AURA_LLM_BASE','AURA_LLM_MODEL','AURA_LLM_KEY','OPENAI_API_KEY','OPENROUTER_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY'):os.environ.pop(key,None)
    ns['llm_endpoint']=lambda:None;ns['try_remote_embed']=lambda text:None
    geometry=[cols,rows]
    def set_display_geometry(columns,lines):
        _geometry(columns,lines);geometry[:]=[columns,lines]
        return dict(cols=columns,rows=lines)
    ns['terminal_size']=lambda:tuple(geometry);ns['set_display_geometry']=set_display_geometry;ns['AURA_T0']=time.monotonic()
    from integration import Hub
    from stage_metrics import StageMetrics,profile_renderer,profile_agents
    profile=StageMetrics()
    ns['_STAGE_METRICS']=profile
    hub=Hub(ns,session,cache=cache);hub.profile=profile
    import fast_field
    hub.remote_field_statistics=getattr(fast_field,'remote_field_statistics',None)
    if ns.get('_CONTINUOUS_WORLD'):
        from continuity import install_ticks
        install_ticks(ns,hub)
    from progression import install as install_progression
    hub.progression=install_progression(ns,cache,hub)
    from neural_core import install as install_neural
    hub.neural=install_neural(ns,hub,cache)
    profile.bind(getattr(hub.progression,'adaptor',None),('on_event','accept_sensory'),'learning')
    profile.bind(hub.neural,('observe','ingest','train'),'neural')
    profile.bind(getattr(hub,'rift',None),('on_event',),'rift')
    profile.bind(getattr(cache,'_actor',None),('query',),'cache_read')
    profile.bind(hub.progression,('absorb','observe','remember'),'progression')
    profile.bind(getattr(hub.progression,'text_learning',None),('pump',),'text_learning')
    profile.bind(getattr(hub.neural,'language',None),('before','observe','flush'),'language')
    profile.bind(hub,('capture_art',),'art_read')
    atomic_write=ns['atomic_write']
    def timed_write(path,text):
        if path.name=='world-clock.json':return profile.call('tick_checkpoint',atomic_write,path,text)
        return atomic_write(path,text)
    ns['atomic_write']=timed_write
    BaseBus=ns['EventBus']
    class ProfileBus(BaseBus):
        def _emit(self,*args,**kwargs):return profile.call('event_bus',super()._emit,*args,**kwargs)
    ns['EventBus']=ProfileBus
    profile_agents(ns,profile)
    control=socket.socket(fileno=control_fd) if control_fd is not None else None
    if control:control.setblocking(False)
    channel=socket.socket(fileno=fd);channel.setblocking(False)
    Fast=profile_renderer(renderer_class(ns),profile);emitter=Emitter()
    class LiveRender(Fast):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.native_tick=0
        def _on(self,event):
            if event['name']=='tick':self.native_tick=int(event.get('payload',{}).get('tick') or 0)
            return super()._on(event)
        def _frame(self,columns,lines,t):
            result=super()._frame(columns,lines,t)
            packet=profile.call('encode',emitter.packet,result[0],timestamp=time.monotonic(),entropy=result[1],colour=result[2],tick=self.native_tick,generation=self.genome.generation)
            try:profile.call('send',send_frame,channel,packet)
            except (BrokenPipeError,ConnectionResetError):os.kill(os.getpid(),15)
            return result
        async def run(self,bus,stop):
            if fps==0:return await super().run(bus,stop)
            pacer=Pacer(fps)
            self._queue=bus.subscribe('keystroke','fragment_ready','mutation_applied','generation_complete','vector_match','entropy_spike','agent_died','thought','dream_begin','dream_scene','dream_end','inject','conflict','valuation','residue',*ns['MATH_EVENTS'],*ns['BALANCE_EVENTS'],*ns['CACHE_EVENTS'],'private_thought','tick',*ns['FEELING_EVENTS'],'load','enter_sleep','wake','possible_activity','dreamed_input','mirror_truth','shutdown')
            while not stop.is_set():
                self.beat(bus)
                now=time.monotonic();wait=min(self.pace(.064/self.tempo),pacer.delay(now))
                event=await ns['wait_evt'](self._queue,max(.0001,wait));drained=0
                while event is not None and drained<30:
                    if not self._on(event):return
                    drained+=1
                    try:event=self._queue.get_nowait()
                    except asyncio.QueueEmpty:event=None
                now=time.monotonic()
                if not pacer.due(now):continue
                pacer.mark(now)
                dt=ns['clamp'](now-self._last_t,0,.12);self._last_t=now
                self._expire_held();self._decay(dt)
                skip=self.load_skip if self.load_high and self.load_skip>1 else 1
                if self.sleeping:skip=max(skip,6)
                draw=True
                if skip>1:draw=self._draw_n%skip==0;self._draw_n+=1
                if draw or not self._cached_frame:
                    columns,lines=ns['terminal_size']()
                    frame,entropy,colour=self._frame(columns,lines,now-ns['AURA_T0'])
                    self._cached_frame=frame;self._cached_entropy=entropy;self._cached_color=colour
                else:entropy=self._cached_entropy;colour=self._cached_color
                if now-self._last_stats>.5:
                    self._last_stats=now;body={'entropy':round(entropy,4),'color_var':round(colour,4),'age':round(now-self.born,3)}
                    if self._glyph_sample:body['sample']=self._glyph_sample
                    bus.publish('frame_stats',body)
    ns['RenderAgent']=LiveRender
    async def main():
        requested=ns.get('_ENGINE_STOP_REQUESTED',lambda:False)
        try:
            if requested():return
            hub.start(control)
            def relay_early_stop():
                if requested():os.kill(os.getpid(),signal.SIGTERM)
            # Native amain installs its real stop event before yielding. Relay
            # a signal latched during startup only after that handoff.
            asyncio.get_running_loop().call_soon(relay_early_stop)
            await ns['amain'](False)
        finally:
            try:await hub.neural.drain()
            finally:
                try:hub.close()
                finally:
                    try:hub.progression.close()
                    finally:hub.neural.close()
    import gc
    gc.collect();gc.freeze();gc.set_threshold(50000,10,10)
    try:asyncio.run(main())
    finally:channel.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--fd',type=int,required=True);p.add_argument('--session',type=Path,required=True)
    p.add_argument('--control-fd',type=int)
    p.add_argument('--content-cache',type=Path,required=True)
    p.add_argument('--continue-world',action='store_true')
    p.add_argument('--cols',type=int,default=160);p.add_argument('--rows',type=int,default=48);p.add_argument('--fps',type=float,default=0)
    args=p.parse_args();Pacer(args.fps)
    inherited=resource.getrlimit(resource.RLIMIT_AS)[1]
    limit=min(768*1024*1024,inherited) if inherited!=resource.RLIM_INFINITY else 768*1024*1024
    resource.setrlimit(resource.RLIMIT_AS,(limit,limit));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    run(args.fd,args.session,args.cols,args.rows,args.fps,args.control_fd,args.content_cache,args.continue_world)
