"""Offline export of allowlisted diagnostics; never copies raw session files."""
import argparse,json,os,stat,tempfile,zipfile
from pathlib import Path
from stage_metrics import STAGES
from run_diagnostics import (SCHEMA,MAX_LINE_BYTES,MAX_LOG_FILES,BOUNDS,COUNTERS,LATEST,METRICS,ROLES,
    API_KINDS,REASONS,HEALTH_NUMBERS,number,integer,numeric_fields,boolean_fields,metadata_fields,buffer_fields)

MAX_INPUT_BYTES=16*1024*1024
MAX_RECORDS=200000
MAX_CANDIDATES=10000

def _latest(value):
    if type(value) is not dict:return {}
    return {key:value[key] for key in LATEST if integer(value.get(key))}

def _resources(value):
    if type(value) is not dict:return {}
    result={}
    for role in ROLES:
        item=value.get(role)
        if type(item) is not dict:continue
        clean=boolean_fields(item,('available','duplicate_pid'))
        clean.update(numeric_fields(item,('rss_bytes','threads')))
        cpu=item.get('cpu_pct');clean['cpu_pct']=cpu if number(cpu,6400) else None
        result[role]=clean
    return result

def _record(value):
    if type(value) is not dict or type(value.get('schema')) is not int or value.get('schema')!=SCHEMA or not number(value.get('elapsed_s'),1e9):return None
    result={'schema':SCHEMA,'type':value.get('type'),'elapsed_s':value['elapsed_s']}
    if result['type']=='sample':
        result.update(resources=_resources(value.get('resources')),buffer=buffer_fields(value.get('buffer')),latest=_latest(value.get('latest')))
        health=value.get('health');result['health']=numeric_fields(health,HEALTH_NUMBERS)
        result['health'].update(boolean_fields(health,('writer_alive',)))
    elif result['type']=='api':
        if value.get('kind') not in API_KINDS:return None
        result['kind']=value['kind']
    elif result['type']=='start':result['metadata']=metadata_fields(value.get('metadata'))
    elif result['type']=='stop':result['reason']=value.get('reason') if value.get('reason') in REASONS else 'unknown'
    else:return None
    return result

def _summary(value):
    if type(value) is not dict or value.get('type')!='summary' or type(value.get('schema')) is not int or value.get('schema')!=SCHEMA or not number(value.get('elapsed_s'),1e9):return None
    result={'schema':SCHEMA,'type':'summary','elapsed_s':value['elapsed_s'],'metadata':metadata_fields(value.get('metadata')),
            'complete':value.get('complete') is True,'reason':value.get('reason') if value.get('reason') in REASONS else 'unknown',
            'latest':_latest(value.get('latest')),'counters':{},'distributions':{}}
    counters=value.get('counters')
    if type(counters) is dict:result['counters']={key:counters[key] for key in COUNTERS if integer(counters.get(key))}
    distributions=value.get('distributions')
    if type(distributions) is dict:
        for name in METRICS:
            item=distributions.get(name)
            if type(item) is not dict or item.get('bounds')!=list(BOUNDS):continue
            bins=item.get('bins')
            if type(bins) is not list or len(bins)!=len(BOUNDS)+1 or not all(integer(x) for x in bins):continue
            count=item.get('count')
            if not integer(count) or sum(bins)!=count or not all(number(item.get(k)) for k in ('min','max','sum')):continue
            if item['min']>item['max']:continue
            result['distributions'][name]={'count':count,'min':item['min'],'max':item['max'],'sum':item['sum'],'bounds':list(BOUNDS),'bins':list(bins)}
    return result

def _open_regular(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('unsupported diagnostic file')
        return os.fdopen(fd,'rb')
    except BaseException:os.close(fd);raise

def _has_diagnostics(path):
    return not path.is_symlink() and path.is_dir() and ((path/'summary.json').exists() or any((path/f'events.{i}.jsonl').exists() for i in range(MAX_LOG_FILES)))

def _runs(root):
    """At most two fixed directory levels; never inspect cache/log contents."""
    root=Path(root)
    if root.is_symlink():return []
    if _has_diagnostics(root):return [root]
    if _has_diagnostics(root/'diagnostics'):return [root/'diagnostics']
    candidates=[];visited=0
    bases=[root/'diagnostics',root]
    for base in bases:
        if base.is_symlink() or not base.is_dir():continue
        for item in base.iterdir():
            visited+=1
            if visited>MAX_CANDIDATES:return candidates
            if item.name.startswith('run-') and _has_diagnostics(item):candidates.append(item)
            elif item.name.startswith('fresh-') and item.is_dir() and not item.is_symlink():
                directory=item/'diagnostics'
                if directory.is_symlink() or not directory.is_dir():continue
                for child in directory.iterdir():
                    visited+=1
                    if visited>MAX_CANDIDATES:return candidates
                    if child.name.startswith('run-') and _has_diagnostics(child):candidates.append(child)
    return sorted(set(candidates),key=lambda p:p.name)

def _load_summary(run,coverage):
    path=run/'summary.json'
    if not path.exists():return None
    try:
        with _open_regular(path) as stream:raw=stream.read(256*1024+1)
        if len(raw)>256*1024:coverage['input_limited']=True;return None
        result=_summary(json.loads(raw))
        if result is None:coverage['invalid_summary']=True
        return result
    except (OSError,ValueError,RecursionError,OverflowError):coverage['invalid_summary']=True;return None

def _stream_records(run,coverage):
    budget=MAX_INPUT_BYTES;records=0
    for index in range(MAX_LOG_FILES-1,-1,-1):
        path=run/f'events.{index}.jsonl'
        if not path.exists() and not path.is_symlink():continue
        try:
            with _open_regular(path) as stream:
                while budget>0 and records<MAX_RECORDS:
                    raw=stream.readline(min(MAX_LINE_BYTES+1,budget+1))
                    if not raw:break
                    budget-=len(raw)
                    if budget<0:coverage['input_limited']=True;return
                    if len(raw)>MAX_LINE_BYTES:
                        coverage['oversized_lines']+=1
                        # Drain this line in bounded pieces so it cannot become a new record.
                        while raw and not raw.endswith(b'\n') and budget>0:
                            raw=stream.readline(min(MAX_LINE_BYTES+1,budget+1));budget-=len(raw)
                        if budget<=0:coverage['input_limited']=True;return
                        continue
                    if not raw.endswith(b'\n'):
                        coverage['truncated_tail']=True;continue
                    try:clean=_record(json.loads(raw))
                    except (ValueError,UnicodeError,RecursionError,OverflowError):clean=None
                    if clean is None:coverage['invalid_lines']+=1;continue
                    records+=1;yield clean
                if budget<=0 or records>=MAX_RECORDS:coverage['input_limited']=True;return
        except (OSError,ValueError):coverage['unreadable_files']+=1

def _write_text(path,text):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:stream.write(text)

def _report_text(report):
    coverage=report['coverage'];whole=report['whole_run'];lines=['# Alien World run report','']
    lines.append('Scope: observed GUI callbacks, explicitly supplied worker/helper/preparer/Eye/API process samples, and allowlisted receiving/intake counters. This is a measured PID subset, not whole-application or system-wide usage.')
    lines.append('Host monotonic elapsed time is diagnostic only; native tick and generation remain separate. No keys, messages, glyphs, internal charge text or raw application logs are included.\n')
    if coverage['summary_complete'] and coverage['stop_observed']:lines.append('A graceful stop and a final whole-run summary were observed.')
    else:lines.append('Coverage is incomplete or the session is still active: a finalized summary and/or stop record is missing. The latest summary is a checkpoint, not a claim that the application stopped cleanly.')
    lines.append(f"Retained window: {coverage['retained_records']} sanitized records, elapsed {coverage['first_elapsed_s']}–{coverage['last_elapsed_s']} seconds. Rotated: {coverage['rotated']}; dropped by writer queue/record bounds: {coverage['queue_dropped']}. Whole-run aggregates below are separate from this retained window.")
    lines.append(f"Input limitations: invalid lines {coverage['invalid_lines']}, oversized lines {coverage['oversized_lines']}, unreadable files {coverage['unreadable_files']}, truncated tail {coverage['truncated_tail']}, bounded-input limit {coverage['input_limited']}.\n")
    if whole and whole.get('metadata',{}).get('continuous_world'):
        lines.append('One continuing Alien world. Diagnostic elapsed time accumulates observed on-time across opens; closed time adds no ticks or frame/CPU gap samples. Wake and stop markers belong to this same retained history.\n')
    learning=report.get('learning',{})
    remote=report.get('remote_field',{})
    if remote:
        calls=remote.get('field_requests',0)
        lines.append(f"Remote field: current process adapter snapshot at {report.get('remote_field_observed_elapsed_s')}s; requests {calls}, returned remote fields {remote.get('field_successes',0)}, fallback transitions {remote.get('fallback_entries',0)}, local fallback frames {remote.get('fallback_frames',0)}. Existing field-call round trip mean {remote.get('field_call_wall_ms',0)/max(1,calls):.3f}ms, maximum {remote.get('field_call_max_wall_ms',0):.3f}ms. This includes local-helper, broker and remote waits; it is not isolated network latency.\n")
        lines.append(f"Remote field failure categories: handshake {remote.get('handshake_failures',0)}, request {remote.get('request_failures',0)}, validation {remote.get('validation_failures',0)}, notification {remote.get('notification_failures',0)}. No host, socket, genes, pixels or exception text is exported.\n")
    if 'crossing_attempts' in learning:
        reasons=('published','no_anchor','no_peer','paused','settling','narrowed','source_expired','preference_withdrawn','gain_disabled','obsolete','archive_refused','archive_failed','cancelled')
        details=', '.join(f"{key} {learning.get('crossing_'+key,0)}" for key in reasons)
        lines.append(f"Crossing outcomes: selected attempts {learning.get('crossing_attempts',0)}, inflight {learning.get('crossing_inflight',0)}; {details}. Each real selected attempt has one terminal outcome or remains inflight. Ranking and permission queries add no attempts.\n")
    if 'text_queued' in learning:
        lines.append(f"Text learning: queued {learning.get('text_queued',0)}, completed {learning.get('text_completed',0)}, committed chunks {learning.get('text_chunks',0)}, pending {learning.get('text_pending',0)}, refused {learning.get('text_refused',0)}, read errors {learning.get('text_read_errors',0)}, archive failures {learning.get('text_archive_failed',0)}, derived feedback {learning.get('text_feedback',0)}. Input retains its source stamp; processing and derived feedback do not create outside observations.\n")
    if learning:
        lines.append(f"Mathematical yield at the latest retained learning sample ({report.get('learning_observed_elapsed_s')}s): observations {learning.get('observations','unknown')}, distinct formulations {learning.get('unique_patterns','unknown')}, durable yielded conclusions {learning.get('yielded','unknown')}, published establishments {learning.get('established','unknown')}, published revisions {learning.get('revised','unknown')}.")
        lines.append('Working mathematical support and predictive skill remain provisional. Published counters require a real archive acknowledgement. These are internal patterns, not semantic truth, causation, general intelligence or an independent assessment of learning quality. No conclusion text or feature values are exported.\n')
    if 'deferred_load' in learning:
        lines.append(f"Learning input deferrals: load {learning.get('deferred_load',0)}, low-power idle {learning.get('deferred_sleep',0)}, discharge cycle {learning.get('deferred_dream',0)}, closed {learning.get('deferred_closed',0)}. Current flags: load-high {learning.get('load_high','unknown')}, idle {learning.get('sleeping','unknown')}, discharging {learning.get('dreaming','unknown')}. Each rejected input is assigned one reason.\n")
    if 'checkpoint_busy' in learning:
        lines.append(f"Learning checkpoint write failures: capacity/closing {learning.get('checkpoint_busy',0)}, storage I/O {learning.get('checkpoint_io_failed',0)}, invalid state {learning.get('checkpoint_invalid',0)}. These count individual checkpoint writes, separately from failed durability acknowledgements.\n")
    if report.get('archives'):
        lines.extend(['','Archive health: separate worker and window processes. Pending work is volatile; only the durable sequence acknowledges writes. These are latest retained samples, not proof of uninterrupted writer health.','','| Process | Pending records | Accepted / durable | Writer alive | Failed | Read errors / busy | Last SQLite code |','|---|---:|---:|---|---|---:|---:|'])
        for name,row in report['archives'].items():
            lines.append(f"| {name} | {row.get('pending_records','unknown')} | {row.get('accepted_sequence','unknown')} / {row.get('durable_sequence','unknown')} | {row.get('writer_alive','unknown')} | {row.get('failed','unknown')} | {row.get('read_failures','unknown')} / {row.get('read_busy_errors','unknown')} | {row.get('last_read_code','unknown')} |")
    if 'alphabet_letters' in learning:
        lines.append(f"Written alphabet study at that sample: incoming sources {learning.get('alphabet_inputs_incoming',0)}, own sparked lines {learning.get('alphabet_inputs_own',0)}, studied letters {learning.get('alphabet_letters',0)}, spaces {learning.get('alphabet_spaces',0)}, explicitly rejected symbols {learning.get('alphabet_rejected_symbols',0)}, durable written returns {learning.get('alphabet_written_yields',0)}, current native load stride {learning.get('alphabet_load_stride',1)}, pending studies {learning.get('alphabet_pending',0)}, refused inputs {learning.get('alphabet_refused',0)}, archive failures {learning.get('alphabet_archive_failed',0)}. These are internal computations from writing, not independent outside evidence. Original writing and symbol receipts stay private in the existing cache.\n")
    if 'rift_signals' in learning:
        lines.append(f"Internal rift steering: sensed signals {learning.get('rift_signals',0)}, native current-path intents {learning.get('rift_intents',0)}, ACK-gated crossing feedback {learning.get('rift_feedback',0)}, withdrawals {learning.get('rift_withdrawals',0)}, pressure {learning.get('rift_pressure',0)}, aperture {learning.get('rift_aperture',0)}, study stride {learning.get('rift_stride',1)}, exploration windows {learning.get('rift_exploration_windows',0)}, curious crossings {learning.get('rift_curious_crossings',0)}, curious yields {learning.get('curious_yields',0)}, wake windows {learning.get('rift_wake_windows',0)}, remembered visits {learning.get('rift_remembered_visits',0)}, warm forecaster priors {learning.get('warm_priors',0)}, warm blends {learning.get('warm_blends',0)}. These are derived internal control states, never new outside observations or semantic truth. Private source preferences and routes are excluded.\n")
    if 'spark_charged' in learning:
        lines.append(f"Spark windows: charge received {learning.get('spark_charged',0)}, windows filled {learning.get('spark_sparked',0)}, windows left open {learning.get('spark_empty',0)}, charge held {learning.get('spark_bits',0)}. Windows fill only from real typed, Eye, maths and mist/API charge; nothing is scripted.\n")
    if 'temporal_observations' in learning:
        lines.append(f"Temporal crossings at that retained sample: measured receipts {learning.get('temporal_observations','unknown')}, active streams {learning.get('temporal_active_streams','unknown')}, durable routes {learning.get('temporal_routes','unknown')}, crossed stream links {learning.get('temporal_crossings','unknown')}. Traversal is not new evidence; unknown gaps retain unknown duration. Private routes and measurements are excluded.\n")
    for name,row in sorted(report.get('observers',{}).items()):
        lines.append(f"Observer {name}: words {row.get('words',0)}, drawings {row.get('drawings',0)}, received {row.get('received',0)}, refused {row.get('refused',0)}, rate-limited {row.get('rate_limited',0)}. Unverified unauthority provenance; no input text is exported.\n")
    if report.get('profiles'):lines.append('Cumulative world aggregates may include earlier releases. The stage profiles below describe only the latest retained process profiles; use matching retained sample intervals for before/after comparisons.')
    for name,title in (('worker','Worker stages'),('presentation','Presentation stages'),('receiver','Living Buffer round trip')):
        profile=report.get('profiles',{}).get(name,{})
        if not profile:continue
        lines.extend(['',title+': current process profile; wall and current-thread CPU spans are inclusive. Nested stages overlap; do not sum them. Unmeasured work and other threads remain outside these spans.',f"Profile observed for {profile.get('elapsed_ms',0)/1000:.3f}s; latest retained sample at {report.get('profile_observed_elapsed_s',{}).get(name)}s.",'','| Stage | Calls | CPU total ms | CPU mean ms | Wall mean ms | Wall max ms |','|---|---:|---:|---:|---:|---:|'])
        for stage in STAGES:
            calls=profile.get(stage+'_calls',0)
            if calls:lines.append(f"| {stage} | {calls} | {profile.get(stage+'_cpu_ms',0):.3f} | {profile.get(stage+'_cpu_ms',0)/calls:.3f} | {profile.get(stage+'_wall_ms',0)/calls:.3f} | {profile.get(stage+'_max_wall_ms',0):.3f} |")
        if name=='receiver':lines.append('Receiver CPU is Python receiver-thread work; round-trip wall includes Node/IPC wait. Node helper CPU is measured separately in the process-role samples.')
        if name=='presentation':lines.append(f"Packed frames {profile.get('packed_frames','unknown')}; staging allocations {profile.get('staging_allocations','unknown')}; staging reuses {profile.get('staging_reuses','unknown')}; bytes {profile.get('staging_bytes','unknown')}.")
    if whole:
        counters=whole['counters'];lines.append(f"Whole-run aggregate checkpoint: {whole['elapsed_s']:.3f} seconds.")
        lines.append(f"Observed received frames: {counters.get('frames_received','unknown')}; render callbacks: {counters.get('render_callbacks','unknown')}; draw sequence advances: {counters.get('draw_sequence_advances','unknown')}; missing sequence values between observed receives: {counters.get('received_sequence_missing','unknown')}.")
        lines.append('Render callbacks can repeat a sequence, including expression redraws. These counts are not vblank FPS or proof that every generated frame was displayed. Sequence gaps combine upstream non-delivery/coalescing; they do not identify a cause.\n')
        lines.extend(['| Observed metric | Count | Mean | Exact observed maximum |','|---|---:|---:|---:|'])
        for name,item in whole['distributions'].items():
            if item['count']:lines.append(f"| {name} | {item['count']} | {item['sum']/item['count']:.3f} | {item['max']:.3f} |")
        lines.append('\nNumeric distributions in report.json are fixed-bin histograms with inclusive upper bounds and a final overflow bin, not a percentile estimate. Maxima are exact among observed callbacks/samples, not unobserved intervals.')
    else:lines.append('No usable whole-run summary is available. Retained samples alone cannot reconstruct whole-run counts or maxima.')
    lines.append('\nAPI-adjacent gaps are intervals ending within five seconds after an observed admitted API event. They describe correlation, not causality; dispatch/reply/admission counts do not prove provider work, native learning or semantic truth.')
    lines.append('CPU is process CPU / diagnostic elapsed time (100% is one core), sampled separately by role. Missing/exited processes and first CPU observations are unknown, not zero. Duplicate PIDs are marked; RSS includes shared pages and must not be summed as unique physical RAM. No unobserved descendants are inferred.')
    lines.append('The one-second sample gap describes observed scheduling intervals. The diagnostic writer has its own bounded queue and can drop records under pressure while retaining in-memory aggregates. A crash can lose work after the last summary checkpoint. Export while active is a bounded best-effort view, not an atomic multi-file snapshot. Diagnostics are unsigned observations, not independent verification.\n')
    return '\n'.join(lines)+'\n'

def analyse_session(session,output):
    """Return a new privacy-filtered ZIP; safe while the writer is still active."""
    runs=_runs(Path(session))
    if not runs:raise ValueError('no diagnostic session available')
    run=runs[-1]
    coverage={'summary_complete':False,'stop_observed':False,'retained_records':0,'retained_samples':0,'first_elapsed_s':None,'last_elapsed_s':None,
              'rotated':False,'queue_dropped':0,'invalid_lines':0,'invalid_summary':False,'oversized_lines':0,
              'unreadable_files':0,'truncated_tail':False,'input_limited':False}
    whole=_load_summary(run,coverage)
    if whole:
        coverage.update(summary_complete=whole['complete'],rotated=whole['counters'].get('rotations',0)>0,queue_dropped=whole['counters'].get('queue_dropped',0))
    output=Path(output);output.mkdir(parents=True,exist_ok=True,mode=0o700)
    target=Path(tempfile.mkdtemp(prefix='run-report-',dir=output))
    observers={};learning={};learning_elapsed=None;profiles={};profile_elapsed={};archives={};archive_elapsed={};remote={};remote_elapsed=None;remote_seen=-1
    cleaned=target/'sanitized.jsonl'
    fd=os.open(cleaned,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:
        for record in _stream_records(run,coverage):
            stream.write(json.dumps(record,allow_nan=False,separators=(',',':'))+'\n')
            coverage['retained_records']+=1;coverage['retained_samples']+=record['type']=='sample'
            if record['type']=='start' and record['elapsed_s']>=remote_seen:
                remote={};remote_elapsed=None;remote_seen=record['elapsed_s']
            if record['type']=='sample' and record.get('buffer',{}).get('learning') and (learning_elapsed is None or record['elapsed_s']>=learning_elapsed):
                learning=dict(record['buffer']['learning']);learning_elapsed=record['elapsed_s']
            if record['type']=='sample' and record.get('buffer',{}).get('observers'):observers=dict(record['buffer']['observers'])
            if record['type']=='sample':
                if record['elapsed_s']>=remote_seen:
                    remote=dict(record.get('buffer',{}).get('remote_field',{}));remote_seen=record['elapsed_s'];remote_elapsed=remote_seen if remote else None
                for name,key in (('worker','worker_archive'),('gui','archive')):
                    value=record.get('buffer',{}).get(key)
                    if value and record['elapsed_s']>=archive_elapsed.get(name,-1):archives[name]=value;archive_elapsed[name]=record['elapsed_s']
                for name in ('worker','presentation','receiver'):
                    value=record.get('buffer',{}).get(name+'_profile')
                    if value and record['elapsed_s']>=profile_elapsed.get(name,-1):profiles[name]=value;profile_elapsed[name]=record['elapsed_s']
            coverage['stop_observed']|=record['type']=='stop'
            elapsed=record['elapsed_s']
            coverage['first_elapsed_s']=elapsed if coverage['first_elapsed_s'] is None else min(coverage['first_elapsed_s'],elapsed)
            coverage['last_elapsed_s']=elapsed if coverage['last_elapsed_s'] is None else max(coverage['last_elapsed_s'],elapsed)
    report={'schema':SCHEMA,'scope':'owned-pid-subset','coverage':coverage,'whole_run':whole,'learning':learning,'observers':observers,'learning_observed_elapsed_s':learning_elapsed,'profiles':profiles,'profile_observed_elapsed_s':profile_elapsed,'archives':archives,'archive_observed_elapsed_s':archive_elapsed}
    if remote:report.update(remote_field=remote,remote_field_observed_elapsed_s=remote_elapsed)
    _write_text(target/'report.json',json.dumps(report,allow_nan=False,indent=2)+'\n')
    _write_text(target/'report.md',_report_text(report))
    archive=target/'report.zip'
    descriptor=os.open(archive,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'wb') as stream:
        with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
            for name in ('report.md','report.json','sanitized.jsonl'):bundle.write(target/name,arcname=name)
    return archive

def main(argv=None):
    parser=argparse.ArgumentParser(description='Export scalar Alien World diagnostics without private content.')
    source=parser.add_mutually_exclusive_group(required=True);source.add_argument('--session',type=Path);source.add_argument('--sessions',type=Path)
    parser.add_argument('--latest',action='store_true');parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    try:
        if args.sessions and not args.latest:
            for run in _runs(args.sessions):print(run)
            return 0
        if args.output is None:parser.error('--output is required for export')
        print(analyse_session(args.session or args.sessions,args.output));return 0
    except (OSError,ValueError):
        print('Diagnostic report unavailable; source files were left unchanged.');return 1

if __name__=='__main__':raise SystemExit(main())
