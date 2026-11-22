"""Bounded, scalar-only host diagnostics. Never part of Alien's native clock.

Hot callbacks update bounded aggregates in RAM. One owned writer handles disk;
no frame, glyph, prompt, credential, exception text or private world is recorded.
"""
from collections import OrderedDict,deque
import gc,json,math,os,re,threading,time,uuid
from pathlib import Path
from stage_metrics import profile_fields
from remote_diagnostics import remote_field_fields

SCHEMA=1
MAX_QUEUE=64
MAX_LOG_BYTES=2*1024*1024
MAX_LOG_FILES=4
MAX_LINE_BYTES=64*1024
ROLES=('gui','worker','helper','preparer','eye','api')
API_KINDS=('dispatch','reply','admitted','cancelled','error')
REASONS=('owner_stop','window_close','application_error','shutdown','unknown')
BOUNDS=(.1,.5,1.,2.,5.,10.,20.,50.,100.,250.,500.,1000.,2000.,5000.,10000.,60000.,1000000.,1e9,1e12)
METRICS=('frame_gap_ms','draw_gap_ms','source_age_ms','receive_to_draw_ms','upload_ms','draw_ms',
         'sample_gap_ms','frame_gap_api_recent_ms','draw_gap_api_recent_ms','sample_work_ms')+tuple(
         f'{role}_{unit}' for role in ROLES for unit in ('cpu_pct','rss_bytes'))
COUNTERS=('frames_received','render_callbacks','draw_sequence_advances','received_sequence_missing',
          'received_out_of_order','samples','invalid_inputs','queue_dropped','write_errors','written_records',
          'rotations','source_clock_unavailable','world_interruptions')+tuple('api_'+kind for kind in API_KINDS)
LATEST=('sequence','tick','generation','cols','rows','draw_sequence')
BUFFER_NUMBERS=('offers','coalesced','processed','delivered','delivery_coalesced','refused','source_sequence',
                'source_tick','source_generation','pending','inflight','control_pending','control_outgoing','quota_pending')
BUFFER_BOOLS=('thread_alive','closed','api_active')
INTAKE_NUMBERS=('pending','ready','retained','used_bytes','max_bytes','evicted_material','inflight')
LIBRARY_NUMBERS=('allocatedBytes','readyBytes','gatherBytes','configuredReadyBytes','configuredGatherBytes',
 'physicalArrayAllocations','pagesGrown','pagesDropped','gatheredBytes','writtenBytes','clearedBytes',
 'pageClearedBytes','gatherClearedBytes','directSubmissions','gatherSubmissions','gatherGrowths','gatherShrinks',
 'peakAllocatedBytes','peakTransientBytes','allocationRefusals','trims','active','armed','sealed')
RETENTION_NUMBERS=('observations','profiles','activeProfiles','selectedHorizon','maxObservedHorizon','demandBytes',
 'demandReadyBlocks','evictions','failures','maxProfiles','maxHorizon','metadataBytesEstimate')
BURST_NUMBERS=('snapshots','lastReadyBlocks','peakReadyBlocks','failures')
BLANKET_NUMBERS=('regions','regionBytes','paddingBytes','allocations','reuses','directSubmissions','gatherFallbacks',
 'dropped','metadataBytesEstimate')
ARCHIVE_NUMBERS=('read_failures','read_busy_errors','last_read_code','pending_bytes','pending_records','max_pending_bytes','max_pending_records','accepted_sequence',
 'durable_sequence','commits','pending_continuations','max_pending_continuations')
HEALTH_NUMBERS=('queue_pending','queue_capacity','queue_dropped','write_errors','thread_count','gc0','gc1','gc2',
                'gc_collections0','gc_collections1','gc_collections2')

def number(value,maximum=1e24):
    return (type(value) is int and 0<=value<=maximum or
            type(value) is float and math.isfinite(value) and 0<=value<=maximum)

def integer(value,maximum=2**64-1):
    return type(value) is int and 0<=value<=maximum

def numeric_fields(value,names):
    if type(value) is not dict:return {}
    return {key:value[key] for key in names if key in value and number(value[key])}

def boolean_fields(value,names):
    if type(value) is not dict:return {}
    return {key:value[key] for key in names if key in value and type(value[key]) is bool}

def metadata_fields(value):
    result={'schema':SCHEMA,'scope':'owned-pid-subset'}
    if type(value) is not dict:return result
    if value.get('continuous_world') is True:result['continuous_world']=True
    # These are build provenance, not a general string/log entrance.
    if value.get('release') in ('native-living-buffer-v1','native-learning-yield-v1','native-temporal-rift-v1','native-continuous-world-v1','native-packed-receive-v1','native-alphabet-maths-v1','native-field-archive-v2','native-alphabet-rift-v1','native-rift-steering-v1','native-responsive-learning-v1'):result['release']=value['release']
    revision=value.get('living_buffer_revision')
    if type(revision) is str and re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}',revision):result['living_buffer_revision']=revision
    return result

LEARNING_NUMBERS=('observations','refused','unique_patterns','reinforced','established','revised','working_established','working_revised','computed_establishments','computed_revisions','yielded','coalesced','discarded','archive_refused','archive_failed','checkpoint_busy','checkpoint_io_failed','checkpoint_invalid','durable_committed','obsolete','deferred','state_rejected','deferred_load','deferred_sleep','deferred_dream','deferred_closed','pending','inflight','active_streams','active_conclusions','recent_evidence','prediction_skill','recipes','temporal_observations','temporal_refused','temporal_past_links','temporal_lateral_links','temporal_routes','temporal_crossings','temporal_unknown_links','temporal_nodes','temporal_links','temporal_active_streams','temporal_state_rejected')

LEARNING_NUMBERS += ('alphabet_inputs_incoming','alphabet_inputs_own','alphabet_letters','alphabet_spaces','alphabet_rejected_symbols','alphabet_refused','alphabet_archive_failed','alphabet_deferred','alphabet_pending','alphabet_queued_bytes','alphabet_load_stride','alphabet_written_yields')

LEARNING_NUMBERS += tuple('rift_'+key for key in ('signals','intents','feedback','withdrawals','rejected','state_rejected','archive_failed','pressure','aperture','stride','active_preferences','exploration_windows','curious_crossings'))
LEARNING_NUMBERS += ('curious_yields',)
LEARNING_NUMBERS += ('warm_priors','warm_blends','rift_wake_windows','rift_remembered_visits')
LEARNING_NUMBERS += ('spark_charged','spark_sparked','spark_empty','spark_bits')
LEARNING_NUMBERS += tuple('crossing_'+key for key in ('attempts','inflight','published','no_anchor','no_peer','paused','settling','narrowed','source_expired','preference_withdrawn','gain_disabled','obsolete','archive_refused','archive_failed','cancelled'))
LEARNING_NUMBERS += tuple('text_'+key for key in ('queued','completed','chunks','pending','refused','read_errors','archive_failed','feedback','feedback_rejected','inflight','admission_waiting'))

def observer_fields(value):
    """Scalar counts per named observer; names only, never any input text."""
    from observer_participants import NAME,UNNAMED,METRICS,MAX_PARTICIPANTS
    if type(value) is not dict:return {}
    names=[name for name in value if isinstance(name,str) and (name==UNNAMED or NAME.fullmatch(name))][:MAX_PARTICIPANTS]
    return {name:numeric_fields(value[name],METRICS) for name in names if type(value[name]) is dict}

def buffer_fields(value):
    if type(value) is not dict:return {}
    result=numeric_fields(value,BUFFER_NUMBERS);result.update(boolean_fields(value,BUFFER_BOOLS))
    if type(value.get('learning')) is dict:
        result['learning']=numeric_fields(value['learning'],LEARNING_NUMBERS)
        result['learning'].update(boolean_fields(value['learning'],('closed','sleeping','dreaming','load_high','rift_closed','text_reader_alive','text_closed')))
    remote=remote_field_fields(value.get('remote_field'))
    if remote:result['remote_field']=remote
    if value.get('status') in ('not_started','starting','active','native_fallback','closed'):result['status']=value['status']
    for key,names in (('intake',INTAKE_NUMBERS),('archive',ARCHIVE_NUMBERS),('worker_archive',ARCHIVE_NUMBERS)):
        if type(value.get(key)) is dict:
            result[key]=numeric_fields(value[key],names)
            if key=='intake':result[key].update(boolean_fields(value[key],('api_reserved',)))
            if key in ('archive','worker_archive'):result[key].update(boolean_fields(value[key],('failed','writer_alive','admission_paused')))
    if type(value.get('continuity')) is dict:
        result['continuity']=numeric_fields(value['continuity'],('interruptions',))
        result['continuity'].update(boolean_fields(value['continuity'],('interrupted',)))
    for name in ('worker_profile','presentation_profile','receiver_profile'):
        if type(value.get(name)) is dict:result[name]=profile_fields(value[name])
    observers=observer_fields(value.get('observers'))
    if observers:result['observers']=observers
    library=value.get('library')
    if type(library) is dict:
        clean=numeric_fields(library,LIBRARY_NUMBERS);clean.update(boolean_fields(library,('recipes_used',)))
        for key,names in (('retention',RETENTION_NUMBERS),('burstPressure',BURST_NUMBERS),('blankets',BLANKET_NUMBERS)):
            nested=library.get(key)
            if type(nested) is not dict:continue
            clean[key]=numeric_fields(nested,names);clean[key].update(boolean_fields(nested,('enabled',)))
            if key=='retention' and nested.get('mode') in ('learned','fixed'):clean[key]['mode']=nested['mode']
        result['library']=clean
    return result

def _append_line(path,data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'ab') as stream:stream.write(data)

def _write_summary(path,value):
    temporary=path.with_name('summary.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:
        json.dump(value,stream,allow_nan=False,separators=(',',':'));stream.write('\n')
    os.replace(temporary,path)

def _read_process(pid):
    """Only this explicitly supplied process; never environ, cmdline or trees."""
    if type(pid) is not int or not 0<pid<2**31:return None
    try:
        with open(f'/proc/{pid}/stat','r',encoding='ascii') as stream:raw=stream.read(8192)
        fields=raw[raw.rfind(')')+2:].split()
        return (int(fields[19]),int(fields[11])+int(fields[12]),max(0,int(fields[21]))*os.sysconf('SC_PAGE_SIZE'),int(fields[17]))
    except (OSError,ValueError,IndexError):return None

class RunDiagnostics:
    def __init__(self,directory,metadata=None,continuous=False):
        self.continuous=continuous;self.directory=Path(directory) if continuous else Path(directory)/('run-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:12])
        self.metadata=metadata_fields(metadata)
        if continuous:self.metadata['continuous_world']=True
        self.started=time.monotonic();self.lock=threading.Condition(threading.RLock())
        self.queue=deque();self.closing=False;self.closed=False;self.failed=False;self.reason='unknown'
        self.counters={key:0 for key in COUNTERS};self.distributions={};self.latest={};self.received=OrderedDict()
        self.last_frame=None;self.last_draw=None;self.last_sample=None;self.last_api=None;self.last_sequence=None;self.process_draw_sequence=-1
        self.resource_previous={};self._log_bytes=0
        if continuous:
            from analyse_run import _summary
            summary=self.directory/'summary.json'
            if self.directory.is_symlink() or summary.is_symlink():raise ValueError('Unsupported diagnostic history path')
            if summary.exists():
                if summary.stat().st_size>256*1024:raise ValueError('Diagnostic history exceeds allowance')
                try:saved=_summary(json.loads(summary.read_text()))
                except (ValueError,OSError):raise ValueError('Existing diagnostic history is damaged')
                if saved is None:raise ValueError('Existing diagnostic history is damaged')
                self.started-=saved['elapsed_s'];self.counters.update(saved['counters']);self.distributions=saved['distributions'];self.latest=saved['latest']
            elif self.directory.exists() and any(self.directory.glob('events.*.jsonl')):raise ValueError('Diagnostic summary missing; history preserved')
            current=self.directory/'events.0.jsonl'
            if current.is_symlink():raise ValueError('Unsupported diagnostic log')
            if current.exists():self._log_bytes=current.stat().st_size
        self.thread=threading.Thread(target=self._run,name='alien-diagnostic-writer',daemon=True)
        self.queue.append({'schema':SCHEMA,'type':'start','elapsed_s':self._elapsed(),'metadata':self.metadata})
        self.thread.start()

    def _elapsed(self,now=None):return max(0.,(time.monotonic() if now is None else now)-self.started)

    def _metric(self,key,value):
        if key not in METRICS or not number(value):return
        metric=self.distributions.setdefault(key,{'count':0,'sum':0.,'min':value,'max':value,'bounds':list(BOUNDS),'bins':[0]*(len(BOUNDS)+1)})
        metric['count']+=1;metric['sum']+=value;metric['min']=min(metric['min'],value);metric['max']=max(metric['max'],value)
        bucket=len(BOUNDS)
        for index,upper in enumerate(BOUNDS):
            if value<=upper:bucket=index;break
        metric['bins'][bucket]+=1

    def _invalid(self):
        with self.lock:self.counters['invalid_inputs']+=1

    def _enqueue(self,record):
        if self.failed or len(self.queue)>=MAX_QUEUE:self.counters['queue_dropped']+=1;return
        self.queue.append(record);self.lock.notify()

    def note_frame(self,sequence,tick,generation,source_timestamp,cols,rows):
        try:
            if not all(integer(x) for x in (sequence,tick,generation)) or not number(source_timestamp,1e12) or not (type(cols) is int and type(rows) is int and 1<=cols<=512 and 1<=rows<=128):self._invalid();return
            now=time.monotonic()
            with self.lock:
                if self.closing or self.closed:return
                self.counters['frames_received']+=1
                if self.last_sequence is not None:
                    if sequence>self.last_sequence:self.counters['received_sequence_missing']+=sequence-self.last_sequence-1
                    else:self.counters['received_out_of_order']+=1
                self.last_sequence=sequence
                if self.last_frame is not None:
                    gap=max(0.,now-self.last_frame)*1000;self._metric('frame_gap_ms',gap)
                    if self.last_api is not None and 0<=now-self.last_api<=5:self._metric('frame_gap_api_recent_ms',gap)
                self.last_frame=now
                if 0<=now-source_timestamp<=86400:self._metric('source_age_ms',(now-source_timestamp)*1000)
                else:self.counters['source_clock_unavailable']+=1
                self.latest.update(sequence=sequence,tick=tick,generation=generation,cols=cols,rows=rows)
                self.received[sequence]=now
                if len(self.received)>128:self.received.popitem(last=False)
        except Exception:self._invalid()

    def note_draw(self,sequence,upload_ms=0,draw_ms=0):
        try:
            if not integer(sequence) or not number(upload_ms,60000) or not number(draw_ms,60000):self._invalid();return
            now=time.monotonic()
            with self.lock:
                if self.closing or self.closed:return
                self.counters['render_callbacks']+=1
                if sequence>self.process_draw_sequence:self.counters['draw_sequence_advances']+=1
                self.process_draw_sequence=sequence
                self.latest['draw_sequence']=sequence
                if self.last_draw is not None:
                    gap=max(0.,now-self.last_draw)*1000;self._metric('draw_gap_ms',gap)
                    if self.last_api is not None and 0<=now-self.last_api<=5:self._metric('draw_gap_api_recent_ms',gap)
                self.last_draw=now;self._metric('upload_ms',upload_ms);self._metric('draw_ms',draw_ms)
                if sequence in self.received:self._metric('receive_to_draw_ms',max(0.,now-self.received[sequence])*1000)
        except Exception:self._invalid()

    def note_api(self,kind):
        try:
            if type(kind) is not str or kind not in API_KINDS:self._invalid();return
            now=time.monotonic()
            with self.lock:
                if self.closing or self.closed:return
                self.counters['api_'+kind]+=1
                if kind=='admitted':self.last_api=now
                self._enqueue({'schema':SCHEMA,'type':'api','elapsed_s':self._elapsed(now),'kind':kind})
        except Exception:self._invalid()

    def sample(self,worker_pid=None,helper_pid=None,buffer=None,extra_pids=None):
        try:
            began=time.monotonic()
            with self.lock:
                if self.closing or self.closed:return
            pids={'gui':os.getpid(),'worker':worker_pid,'helper':helper_pid}
            if type(extra_pids) is dict:
                pids.update({key:extra_pids.get(key) for key in ('preparer','eye','api')})
            resources={};seen=set()
            with self.lock:
                for role in ROLES:
                    pid=pids.get(role);current=_read_process(pid);previous=self.resource_previous.get(role)
                    resource={'available':current is not None,'cpu_pct':None}
                    if current is not None:
                        start,ticks,rss,threads=current
                        if previous is not None and previous[0]==pid and previous[1]==start and began>previous[3] and ticks>=previous[2]:
                            resource['cpu_pct']=min(6400.,(ticks-previous[2])/os.sysconf('SC_CLK_TCK')/(began-previous[3])*100)
                            self._metric(role+'_cpu_pct',resource['cpu_pct'])
                        resource.update(rss_bytes=rss,threads=threads,duplicate_pid=pid in seen);seen.add(pid)
                        self.resource_previous[role]=(pid,start,ticks,began);self._metric(role+'_rss_bytes',rss)
                    else:self.resource_previous.pop(role,None)
                    resources[role]=resource
                clean=buffer_fields(buffer).get('continuity',{})
                self.counters['world_interruptions']=max(self.counters['world_interruptions'],clean.get('interruptions',0))
                self.counters['samples']+=1
                if self.last_sample is not None:self._metric('sample_gap_ms',max(0.,began-self.last_sample)*1000)
                self.last_sample=began
                counts=gc.get_count();collections=gc.get_stats()
                health={'queue_pending':len(self.queue),'queue_capacity':MAX_QUEUE,'queue_dropped':self.counters['queue_dropped'],
                        'write_errors':self.counters['write_errors'],'writer_alive':self.thread.is_alive(),'thread_count':threading.active_count()}
                for index in range(3):health['gc'+str(index)]=counts[index];health['gc_collections'+str(index)]=collections[index]['collections']
                self._metric('sample_work_ms',max(0.,time.monotonic()-began)*1000)
                self._enqueue({'schema':SCHEMA,'type':'sample','elapsed_s':self._elapsed(began),'resources':resources,
                               'buffer':buffer_fields(buffer),'health':health,'latest':dict(self.latest)})
        except Exception:self._invalid()

    def statistics(self):
        with self.lock:
            return {'writer_alive':self.thread.is_alive(),'queue_pending':len(self.queue),'queue_dropped':self.counters['queue_dropped'],
                    'write_errors':self.counters['write_errors'],'closed':self.closed,'failed':self.failed}

    def _summary(self,complete=False):
        with self.lock:
            return {'schema':SCHEMA,'type':'summary','metadata':dict(self.metadata),'elapsed_s':self._elapsed(),
                    'complete':complete,'reason':self.reason if complete else 'unknown','counters':dict(self.counters),
                    'latest':dict(self.latest),'distributions':{key:{field:list(value) if type(value) is list else value for field,value in metric.items()} for key,metric in self.distributions.items()}}

    def _write_record(self,record):
        raw=(json.dumps(record,allow_nan=False,separators=(',',':'))+'\n').encode('utf-8')
        if len(raw)>min(MAX_LINE_BYTES,MAX_LOG_BYTES):
            with self.lock:self.counters['queue_dropped']+=1
            return
        if self._log_bytes+len(raw)>MAX_LOG_BYTES:
            oldest=self.directory/f'events.{MAX_LOG_FILES-1}.jsonl'
            if oldest.exists():oldest.unlink()
            for index in range(MAX_LOG_FILES-2,-1,-1):
                source=self.directory/f'events.{index}.jsonl'
                if source.exists():os.replace(source,self.directory/f'events.{index+1}.jsonl')
            self._log_bytes=0
            with self.lock:self.counters['rotations']+=1
        _append_line(self.directory/'events.0.jsonl',raw);self._log_bytes+=len(raw)
        with self.lock:self.counters['written_records']+=1

    def _run(self):
        try:
            self.directory.parent.mkdir(parents=True,exist_ok=True,mode=0o700);self.directory.mkdir(mode=0o700,exist_ok=self.continuous)
            while True:
                with self.lock:
                    while not self.queue and not self.closing:self.lock.wait()
                    if not self.queue:break
                    record=self.queue.popleft()
                self._write_record(record)
                if record['type'] in ('start','sample'):_write_summary(self.directory/'summary.json',self._summary())
            self._write_record({'schema':SCHEMA,'type':'stop','elapsed_s':self._elapsed(),'reason':self.reason})
            _write_summary(self.directory/'summary.json',self._summary(complete=True))
        except Exception:
            with self.lock:self.counters['write_errors']+=1;self.failed=True;self.queue.clear()
        finally:
            with self.lock:self.closed=True;self.lock.notify_all()

    def close(self,reason='owner_stop'):
        try:
            with self.lock:
                if not self.closing:self.reason=reason if type(reason) is str and reason in REASONS else 'unknown'
                self.closing=True;self.lock.notify_all()
            if threading.current_thread() is not self.thread:self.thread.join(timeout=2.)
        except Exception:pass
