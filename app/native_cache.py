"""Adapt the unchanged native hive's state/art seams to the shared byte cache.

The native source remains frozen. These paths are logical record names, including
when a native helper casts one through Path again. No original state is read and
the new world's art feedback does not poll any filesystem artwork.
"""
import asyncio,copy,io,json,logging,os
from pathlib import Path,PosixPath
from content_cache import CacheBusy,json_bytes

_raster_pool=None
def _raster_pool_get():
    global _raster_pool
    if _raster_pool is None:
        from concurrent.futures import ThreadPoolExecutor
        _raster_pool=ThreadPoolExecutor(1,thread_name_prefix='native-raster')
    return _raster_pool

FILES=('aura_memory.json','aura_vectors.json','aura_cache.json','aura_private.json','root_truth.json','world-clock.json','temporal.json','alien_register.json')

def raster_png(svg):
    """Render the actual native composition, transiently, into real image bytes."""
    import cairo,gi
    gi.require_foreign('cairo');gi.require_version('GdkPixbuf','2.0');gi.require_version('Gdk','3.0')
    from gi.repository import GdkPixbuf,Gdk
    loader=GdkPixbuf.PixbufLoader.new_with_type('svg');loader.set_size(960,540)
    loader.write(svg.encode('utf-8'));loader.close();pixbuf=loader.get_pixbuf()
    if pixbuf is None:raise ValueError('native picture could not be rasterized')
    surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,960,540)
    try:
        cr=cairo.Context(surface);Gdk.cairo_set_source_pixbuf(cr,pixbuf,0,0);cr.paint();surface.flush()
        output=io.BytesIO();surface.write_to_png(output);return output.getvalue()
    finally:surface.finish()

def install(ns,directory,cache):
    root=Path(directory).absolute()
    def key_for(path):
        path=Path(os.path.abspath(path))
        return path.name if path.parent==root and path.name in FILES else None
    def read(path):
        key=key_for(path)
        if key is None:raise OSError('native content path is not registered')
        value=cache.get_json('native.state',key)
        if value is None:raise FileNotFoundError(str(path))
        return json_bytes(value)
    class CachePath(PosixPath):
        def read_bytes(self):return read(self)
        def read_text(self,encoding=None,errors=None):return read(self).decode(encoding or 'utf-8',errors or 'strict')
        def stat(self,*,follow_symlinks=True):
            if key_for(self) is None:return super().stat(follow_symlinks=follow_symlinks)
            return os.stat_result((0o100600,0,0,1,os.getuid(),os.getgid(),len(read(self)),0,0,0))
        def write_text(self,data,encoding=None,errors=None,newline=None):
            atomic_write(self,data);return len(data)
        def write_bytes(self,data):
            atomic_write(self,data.decode('utf-8'));return len(data)
    def atomic_write(path,text):
        key=key_for(path)
        if key is None:raise OSError('native file output is replaced by the content cache')
        if not isinstance(text,str):raise ValueError('native state must be UTF-8 JSON')
        cache.set_json('native.state',key,json.loads(text))
    ns['Path']=CachePath;ns['ROOT']=CachePath(root);ns['atomic_write']=atomic_write;ns['content_cache']=cache
    for variable,name in zip(('MEMORY_PATH','VECTOR_PATH','CACHE_PATH','PRIVATE_PATH','ROOT_TRUTH_PATH'),FILES):ns[variable]=CachePath(root/name)
    background_writer=bool(getattr(cache,'background_writer',False))
    art_next=[int(cache.get_json('native.sequence','art',0))+1]
    ns['svg_file_index']=(lambda _root:art_next[0]) if background_writer else (lambda _root:int(cache.get_json('native.sequence','art',0))+1)
    BaseChannel=ns['ChannelAgent'];BaseFeedback=ns['FeedbackAgent']
    # A supervisor may replace its channel while a disk fence is outstanding.
    # Keep the one publication slot at installation scope, across replacements.
    art_pending=[None]
    class CachedChannel(BaseChannel):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);self.archive_error=None
        def _request(self,bus,*args,**kwargs):
            indexed=background_writer and self.genome.channel() in ('svg','both')
            if indexed:
                if art_pending[0] is not None or self.pending_svg:return
                self._index=max(self._index,art_next[0])
            try:return super()._request(bus,*args,**kwargs)
            finally:
                if indexed:art_next[0]=max(art_next[0],self._index)
        def _release(self,bus,job):
            background=bool(getattr(cache,'background_writer',False))
            spec=copy.deepcopy(job['spec']);lines=list(self.lines[-6:]);spec['lines']=lines
            if lines:spec['description']=' · '.join(lines[-3:])[:180]
            mode=str(spec.get('channel') or self.genome.channel());index=job.get('index');publication=None
            reason=str(job.get('reason') or spec.get('reason') or '');collision=bool(job.get('collision'))
            if background and mode in ('svg','both') and index is not None and art_pending[0] is not None:raise CacheBusy('native art is awaiting durable acknowledgement')
            def publish(publication):
                bus.publish('channel_shift',dict(channel=mode,reason=reason,authority=spec['authority'],collision=collision,balance=spec['balance'],title=spec['title'],seed=spec['seed'],dream=bool(spec['dream']),cache_ref=publication['cache_ref'] if publication else None))
                if mode!='terminal':bus.publish('svg_spec',spec)
                if publication:
                    # Keep the native feedback queue/ranking contract without an SVG payload.
                    bus.publish('svg_ready',publication)
                    bus.publish('art_ready',publication)
            def ready(image_ref,spec_ref):
                return dict(cache_ref=image_ref,spec_ref=spec_ref,format='png',width=960,height=540,title=spec['title'],description=spec['description'],palette=spec['palette'],seed=spec['seed'],channel=mode,authority=spec['authority'],collision=spec['collision'],dream=spec['dream'])
            def failed(error):
                self.archive_error=type(error).__name__+': '+str(error)[:160]
                logging.getLogger(__name__).error('Native art archive failed: %s',self.archive_error)
            if mode in ('svg','both') and index is not None:
                try:
                    if background:art_next[0]=max(art_next[0],int(index)+1)
                    if background:
                        # Rasterisation runs off the agent thread; every cache
                        # write and publication still lands back on the loop.
                        state=dict(png=None,image_ref=None,spec_ref=None,sequence=False,future=None)
                        art_pending[0]=state
                        def abort(error):
                            if art_pending[0] is not state:return
                            art_pending[0]=None;state.clear();failed(error)
                        def complete():
                            if art_pending[0] is not state:return
                            result=ready(state['image_ref'],state['spec_ref'])
                            art_pending[0]=None;state.clear();self.archive_error=None;publish(result)
                        def fence(callback):
                            try:state['future']=cache.after_flush(callback,abort)
                            except (OSError,ValueError) as error:abort(error)
                        def enqueue():
                            if art_pending[0] is not state:return
                            try:
                                if state['image_ref'] is None:
                                    state['image_ref']=cache.put('art.png',f'dream:{int(index)}',state['png'],{'title':spec['title'],'index':int(index)})
                                    state['png']=None
                                if state['spec_ref'] is None:state['spec_ref']=cache.put('art.spec',f'dream:{int(index)}',json_bytes(spec),{'image_ref':state['image_ref']})
                                if not state['sequence']:cache.set_json('native.sequence','art',int(index));state['sequence']=True
                            except CacheBusy:
                                # Retain this one selected picture and retry only the
                                # refused stage after the existing prefix drains.
                                fence(enqueue);return
                            except (OSError,ValueError) as error:abort(error);return
                            fence(complete)
                        dispatch=getattr(cache,'dispatch',None)
                        if dispatch is None:
                            try:dispatch=asyncio.get_running_loop().call_soon_threadsafe
                            except RuntimeError:dispatch=None
                        if dispatch is None:
                            state['png']=raster_png(ns['make_aura_svg'](spec))
                            enqueue()
                        else:
                            raster=_raster_pool_get().submit(lambda:raster_png(ns['make_aura_svg'](spec)))
                            def resume():
                                if art_pending[0] is not state:return
                                try:state['png']=raster.result()
                                except BaseException as error:abort(error);return
                                enqueue()
                            def hop(_r):
                                try:dispatch(resume)
                                except Exception as error:logging.getLogger(__name__).error('Native art resume failed: %s',error)
                            raster.add_done_callback(hop)
                        return state.get('future')
                    png=raster_png(ns['make_aura_svg'](spec))
                    image_ref=cache.put('art.png',f'dream:{int(index)}',png,{'title':spec['title'],'index':int(index)})
                    spec_ref=cache.put('art.spec',f'dream:{int(index)}',json_bytes(spec),{'image_ref':image_ref})
                    cache.set_json('native.sequence','art',int(index));cache.flush()
                    publication=ready(image_ref,spec_ref)
                except (OSError,ValueError) as error:failed(error)
            publish(publication)
    class CachedFeedback(BaseFeedback):
        def _listing(self):return {}
        def _scan_disk(self,bus):return None
        def _on_svg(self,bus,payload):
            text=' '.join(str(payload.get('description') or payload.get('title') or '').split())[:80]
            worth=self._worth_ready();dream=bool(payload.get('dream'))
            if self._emit(bus,path=None,text=text,worth=worth,authority=self._reentry_flag(worth,dream),kind='art',depth=0,dream=dream,source='self'):self.ready_worth=None
    ns['ChannelAgent']=CachedChannel;ns['FeedbackAgent']=CachedFeedback
    return CachePath
