"""Receipt-triggered 93-second agent observations; outside words remain unauthority."""
from __future__ import annotations
import hashlib
import shutil
import json
import os
from pathlib import Path
import re
import socket
import stat
import struct
import tempfile
import threading
import time
import uuid

from _ev_bootstrap import DEFAULT_OBSERVATIONS, ensure_electric_vision
from alien_observer import FieldObserver
from observer_history import ObserverJournal

ensure_electric_vision()
from continuous_vision import ContinuousVision

DURATION = 93
ID = re.compile(r'^[a-f0-9]{32}$')
# Alien's named-observer rule (AlienWorld native-named-observers-v1). A valid
# registered name travels as unverified provenance; it is never authority.
PARTICIPANT = re.compile(r'[a-z][a-z0-9_-]{1,23}')
RESERVED = frozenset(('owner','alien','observer','system','native','authority'))
UNNAMED = 'observer agent'


def participant_name(name):
    """A registered name Alien can carry as `observer:<name>`, or None."""
    if not isinstance(name,str):return None
    value = name.strip().lower()
    return value if PARTICIPANT.fullmatch(value) and value not in RESERVED else None


def word_source(participant):return 'observer:'+participant if participant else UNNAMED


class WordsPending(ValueError):
    """Words exchange was refused or unacknowledged; preserve a healthy visit."""


class LiveFieldSource:
    def __init__(self, directory=None):
        base = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
        self.directory = Path(directory) if directory else base / 'alienworld-observer'

    def _request(self, endpoint, record, *, deadline=None):
        endpoint = Path(endpoint)
        folder, item = endpoint.parent.lstat(), endpoint.lstat()
        if (endpoint.parent != self.directory or not stat.S_ISDIR(folder.st_mode) or folder.st_uid != os.getuid()
                or folder.st_mode & 0o077 or not stat.S_ISSOCK(item.st_mode) or item.st_uid != os.getuid()
                or item.st_mode & 0o077):
            raise ValueError('Untrusted Alien endpoint')
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as peer:
            peer.settimeout(3)
            peer.connect(str(endpoint))
            pid, uid, _gid = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid() or endpoint.name != f'{pid}.sock':
                raise ValueError('Alien endpoint process mismatch')
            wire = json.dumps(record, ensure_ascii=False, separators=(',', ':')).encode()
            if len(wire) > 32768:raise ValueError('Words request exceeds endpoint limit')
            if deadline is not None and time.monotonic() >= deadline:raise ValueError('Observation expired before words dispatch')
            peer.sendall(wire)
            raw, _anc, flags, _address = peer.recvmsg(32768)
            if flags & socket.MSG_TRUNC:raise ValueError('Truncated Alien response')
            answer = json.loads(raw)
            if answer.get('ok') is not True:
                code = str(answer.get('error', 'unavailable'))[:160]
                if record['op'] == 'words' and code in ('input_busy','input_status_unknown','input_refused'):
                    raise WordsPending('Alien words receipt: ' + code + '; retry the same request_id')
                raise ValueError('Alien endpoint: ' + code)
            result = answer['result']
            if record['op'] == 'status' and result.get('pid') != pid:
                raise ValueError('Alien endpoint status process mismatch')
            return result

    def status(self, window_id=None):
        from x11_alien_capture import discover_alien
        windows = {x['window_id']:x for x in discover_alien()}
        found = []
        if self.directory.is_dir():
            for endpoint in sorted(self.directory.glob('*.sock'))[:32]:
                try:
                    result = self._request(endpoint, dict(op='status'))
                    window = windows.get(result.get('window_id'))
                    if not result.get('ready') or not window or window['pid'] != result['pid']:continue
                    if window_id is not None and result['window_id'] != window_id:continue
                    if result.get('size') != [window['width'], window['height']]:continue
                    result['_endpoint'] = str(endpoint)
                    found.append(result)
                except (OSError, ValueError, KeyError, TypeError):continue
        if len(found) != 1:
            raise ValueError('Need exactly one ready Alien observation endpoint; reopen the updated Alien or select its window')
        return found[0]

    def _current(self, binding):
        current = self._request(binding['_endpoint'], dict(op='status'))
        if not current.get('ready') or any(current.get(k) != binding.get(k) for k in
                ('pid','window_id','runtime','world_id','segment_id','size','crop','binding')):
            raise ValueError('Alien stopped, changed world or resized; open a new verified observation')
        return current

    def capture(self, binding):
        from x11_alien_capture import capture_alien
        current = self._current(binding)
        if binding.get('_expires_at') is not None and time.monotonic() >= binding['_expires_at']:
            raise ValueError('Observation expired before capture')
        picture, meta = capture_alien(current['window_id'], expected_size=current['size'], crop=current['crop'])
        try:self._current(binding)
        except Exception:
            picture.close();raise
        return picture, meta

    def say(self, binding, text, request_id, participant=None):
        self._current(binding)
        record = dict(op='words', request_id=request_id, runtime=binding['runtime'],
                      world_id=binding['world_id'], binding=binding['binding'], text=text)
        try:
            if participant:
                try:return self._request(binding['_endpoint'], dict(record, participant=participant), deadline=binding.get('_expires_at'))
                except ValueError as error:
                    # An Alien before named observers refuses the unknown field before
                    # any input is queued; send the same words unnamed instead.
                    if str(error) != 'Alien endpoint: invalid_request':raise
            return self._request(binding['_endpoint'], record, deadline=binding.get('_expires_at'))
        except OSError as error:
            raise WordsPending('Alien words delivery is unknown; retry the same request_id') from error


def _schedule(seconds, callback):
    timer = threading.Timer(seconds, callback)
    timer.daemon = True
    timer.start()
    return timer


class ObservationManager:
    def __init__(self, observations_dir=DEFAULT_OBSERVATIONS, endpoint_dir=None, *, source=None, clock=time.monotonic,
                 schedule=_schedule, observer_id='observer-agent', require_owner_connect=False, stream_factory=ContinuousVision):
        self.root = Path(observations_dir)
        self.source = source or LiveFieldSource(endpoint_dir)
        self.clock, self.schedule = clock, schedule
        self.stream_factory = stream_factory
        self.streams = []
        self.lock = threading.RLock()
        self.current = None
        self.retired = {}
        self.eye = None
        self.eye_context = None
        self.sockets = None
        self.observer_id = observer_id
        self.journal = None
        self.history_error = None
        self.require_owner_connect = require_owner_connect
        self.channels = None
        self.channel = None
        self.claimed_request = None
        self.claimant_id = uuid.uuid4().hex

    def _channels(self):
        if self.journal is None:
            self.journal = ObserverJournal(self.root)
        if self.channels is None:
            from observer_channels import ChannelRegistry
            self.channels = ChannelRegistry(self.journal, monotonic=self.clock)
        return self.channels

    def _channel(self, channel_id):
        if self.channel is None or self.channel['id'] != channel_id:
            raise ValueError('Channel must match this MCP connection registration')
        return self.channel

    def observer_register(self, name, host_kind, thread_id=None):
        with self.lock:
            if self.channel is not None:
                if (name,host_kind,thread_id) != tuple(self.channel[k] for k in ('name','host_kind','thread_id')):
                    raise ValueError('This MCP connection is already registered to a different channel')
                channel = self.channel
            else:
                if self.current and self._state(self.current)['phase'] in ('active','awaiting_acknowledgement'):
                    raise ValueError('Close the existing observation before registering a channel')
                channel = self._channels().register(name,host_kind,thread_id)
                self.channel = channel
                self.observer_id = channel['observer_id']
            return dict(channel=channel,source='observer agent',authority='unauthority',remaining_seconds=None)

    def observer_pending(self, channel_id):
        with self.lock:
            self._channel(channel_id)
            request = self._channels().pending(channel_id)
            return dict(channel_id=channel_id,request=request,remaining_seconds=None)

    def observer_claim(self, channel_id, request_id):
        with self.lock:
            self._channel(channel_id)
            if self.current and self._state(self.current)['phase'] in ('active','awaiting_acknowledgement'):
                if request_id != self.current.get('connect_request_id'):
                    raise ValueError('Close the existing observation before claiming another request')
            request = self._channels().claim(channel_id,request_id,claimant_id=self.claimant_id)
            self.claimed_request = request['id']
            return dict(channel_id=channel_id,request=request,remaining_seconds=None)

    def observer_wait(self, channel_id, timeout=60):
        with self.lock:
            self._channel(channel_id)
            channels = self._channels()
        # Owner Connect is served by another process; never hold the capture lock during a wait.
        request = channels.wait(channel_id,timeout)
        return dict(channel_id=channel_id,request=request,remaining_seconds=None)

    def _owner_request(self):
        if self.channel is None:
            if self.require_owner_connect:
                raise ValueError('Register this MCP channel and claim an owner Connect request before opening')
            return None
        if self.claimed_request is None:
            if not self.require_owner_connect:
                return None
            raise ValueError('Claim an owner Connect request before opening')
        request = self._channels().claim(self.channel['id'],self.claimed_request,claimant_id=self.claimant_id)
        if request['observer_id'] != self.observer_id or request.get('visit_id') is not None:
            raise ValueError('Owner Connect request already belongs to an observation')
        return request

    def _finish_request(self, session):
        if session is None or not session.get('connect_request_id') or session.get('request_finished'):
            return
        phase = session['phase']
        if phase in ('active','awaiting_acknowledgement'):
            return
        state = dict(closed='completed',expired='completed',offer_expired='expired',unavailable='failed')[phase]
        try:
            request = self.channels.get(session['connect_request_id'])
            if request.get('visit_id') != session['id']:
                return
            self.channels.finish(session['connect_request_id'],state,claimant_id=self.claimant_id)
            session['request_finished'] = True
            if self.claimed_request == session['connect_request_id']:
                self.claimed_request = None
        except Exception as error:
            self._history_failure(error)

    def _history_failure(self, error):
        self.history_error = f'Observer history unavailable: {type(error).__name__}: {error}'[:500]

    def _history_visit(self, session):
        try:
            if self.journal is None:
                self.journal = ObserverJournal(self.root)
            return self.journal.save_visit(session['id'], session['binding'], session['phase'],
                started=session['started'], duration=DURATION, observer_id=self.observer_id)
        except Exception as error:
            self._history_failure(error)
            return None

    def _history_record(self, session, kind, payload, event_id=None, *, required=False):
        try:
            if self.journal is None:
                raise ValueError('history storage is unavailable')
            return self.journal.record(session['id'], kind, payload, event_id)
        except Exception as error:
            self._history_failure(error)
            if required:
                raise ValueError('Observer history could not preserve word intent; no words dispatched') from error
            return None

    def _session(self, session_id=None):
        if self.current and session_id in (None, self.current['id']):return self.current
        if session_id in self.retired:return self.retired[session_id]
        raise ValueError('Unknown observation session')

    def _stop(self, phase):
        session = self.current
        if session and session['phase'] in ('active','awaiting_acknowledgement'):
            stream = session.get('stream')
            if stream is not None:
                stream.stop(reason=phase)
                # The timer cannot rewrite a recorder's earlier nonnatural ending.
                if phase=='expired' and stream.status()['phase'] in ('failed','limited','stopped'):
                    phase='unavailable'
            session['phase'] = phase
            if session.get('timer'):session['timer'].cancel()
        observer = session.pop('observer', None) if session else None
        if observer is not None:
            if observer.previous is not None:observer.previous['_picture'].close()
            observer.previous = None
            observer.eye = None
        eye, self.eye = self.eye, None
        if self.eye_context is not None:
            context, self.eye_context = self.eye_context, None
            context.__exit__(None, None, None)
        if self.sockets is not None:
            sockets, self.sockets = self.sockets, None
            sockets.cleanup()
        if session:
            self._history_visit(session)
        # Optional broker bookkeeping follows all native resource release, even when history fails.
        self._finish_request(session)
        return eye

    def _stream_terminal(self, ident, status):
        """Recorder notification runs outside its lock; no caller or join is needed."""
        if status['phase'] not in ('failed','limited','stopped'):
            return
        with self.lock:
            if self.current and self.current['id']==ident and self.current['phase']=='active':
                self._stop('unavailable')

    def _expire(self, ident, phase, expected_phase, deadline):
        with self.lock:
            if (self.current and self.current['id'] == ident and self.current['phase'] == expected_phase
                    and self.clock() >= deadline):self._stop(phase)

    def _state(self, session):
        if session['phase'] == 'awaiting_acknowledgement' and self.clock() >= session['offer_deadline']:
            if session is self.current:self._stop('offer_expired')
        if session['phase'] == 'active' and session.get('stream'):
            if session['stream'].status()['phase'] in ('failed','limited','stopped'):
                if session is self.current:self._stop('unavailable')
        if session['phase'] == 'active' and self.clock() >= session['started'] + DURATION:
            if session is self.current:self._stop('expired')
        remaining = max(0., DURATION - (self.clock() - session['started'])) if session['started'] is not None else None
        return dict(session_id=session['id'],phase=session['phase'],duration_seconds=DURATION,
                    remaining_seconds=remaining,source='observer agent',world_id=session['binding']['world_id'],
                    runtime=session['binding']['runtime'],
                    **({'continuous':session['stream'].status()} if session.get('stream') else {}),
                    **({'history_error':self.history_error} if self.history_error else {}))

    def _check_source(self, session):
        current = self.source.status(session['binding']['window_id'])
        if current.get('ready') is not True or any(current.get(k) != session['binding'].get(k) for k in
               ('pid','window_id','runtime','world_id','segment_id','size','crop','binding')):
            raise ValueError('Alien observation source changed')

    def _active(self, session_id):
        session = self._session(session_id)
        if self._state(session)['phase'] != 'active':raise ValueError('Observation is not active')
        try:self._check_source(session)
        except Exception:
            self._stop('unavailable');raise
        if self._state(session)['phase'] != 'active':raise ValueError('Observation expired during source verification')
        return session

    def _snapshot(self, session):
        binding = dict(session['binding'])
        if session['phase'] == 'active':binding['_expires_at'] = session['started'] + DURATION
        image, meta = self.source.capture(binding)
        try:report = session['observer'].observe(image, meta)
        finally:image.close()
        frame_id = uuid.uuid4().hex
        frame = dict(frame_id=frame_id,sha256=report['source_png_sha256'],image_path=report['image'],
                     shapes_image=report['shapes_image'],measurement=report,session_id=session['id'])
        if not session['frames']:
            # The receipt image survives FieldObserver's bounded derived-sample eviction.
            initial = session['directory']/'initial-offer.png'
            shutil.copyfile(frame['image_path'],initial)
            frame['image_path'] = str(initial)
        session['frames'][frame_id] = frame
        session['last_capture'] = self.clock()
        payload = dict(frame)
        payload['measurement'] = {key:value for key,value in report.items() if key not in ('image','shapes_image')}
        for key in ('image_path', 'shapes_image'):
            payload[key] = str(Path(frame[key]).absolute().relative_to(self.root.absolute()))
        self._history_record(session, 'frame', payload, event_id=frame_id)
        return frame

    def open(self, window_id=None):
        with self.lock:
            if self.current:
                state = self._state(self.current)
                if state['phase'] in ('active','awaiting_acknowledgement'):
                    raise ValueError('Close the existing observation before opening another')
                self.retired[self.current['id']] = self.current
                while len(self.retired) > 16:self.retired.pop(next(iter(self.retired)))
            request = self._owner_request()
            # Verification precedes storage, daemons or any budget/timer creation.
            binding = self.source.status(window_id)
            if binding.get('ready') is not True:raise ValueError('Alien is not ready')
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                if self.journal is None:
                    self.journal = ObserverJournal(self.root)
            except Exception as error:
                self._history_failure(error)
            if self.journal is not None and self.observer_id not in {p['id'] for p in self.journal.list_profiles()}:
                raise ValueError('Unknown observer profile')
            ident = uuid.uuid4().hex
            directory = self.root / ident
            directory.mkdir(mode=0o700)
            ensure_electric_vision()
            from electric_vision_agent_bridge import ElectricVisionAgentSession
            self.sockets = tempfile.TemporaryDirectory(prefix='am-', dir=os.environ.get('XDG_RUNTIME_DIR') or tempfile.gettempdir())
            self.eye_context = ElectricVisionAgentSession(run_dir=self.sockets.name, allow_alien_field=True)
            try:
                self.eye = self.eye_context.__enter__()
                session = dict(id=ident,phase='awaiting_acknowledgement',binding=binding,started=None,frames={},
                               receipt=uuid.uuid4().hex,observer=FieldObserver(self.eye,directory/'frames',keep=3),
                               timer=None,directory=directory,notes=0,sent={},attempted={},attempts={},
                               receipt_records={},offer_deadline=self.clock() + 300,stream=None,read_cursor=0,
                               offered_packets={},staged_packets={},derived_details={},
                               connect_request_id=request['id'] if request else None)
                self.current = session
                self._history_visit(session)
                if request:
                    self.channels.attach_visit(request['id'],ident,claimant_id=self.claimant_id,
                                               offer_deadline=session['offer_deadline'])
                frame = self._snapshot(session)
                session['first_frame'] = frame
                offer_deadline = session['offer_deadline']
                session['timer'] = self.schedule(300,lambda:self._expire(ident,'offer_expired','awaiting_acknowledgement',offer_deadline))
                return dict(frame,receipt=session['receipt'],**{k:v for k,v in self._state(session).items() if k!='session_id'})
            except Exception:
                self._stop('unavailable');raise

    def confirm(self, session_id, receipt, sha256):
        with self.lock:
            session = self._session(session_id)
            if receipt != session['receipt'] or sha256 != session['first_frame']['sha256']:
                raise ValueError('Acknowledgement must match the delivered verified image')
            state = self._state(session)
            if state['phase'] == 'active':return state
            if state['phase'] != 'awaiting_acknowledgement':raise ValueError('Observation offer is no longer available')
            try:self._check_source(session)
            except Exception:
                self._stop('unavailable');raise
            if self._state(session)['phase'] != 'awaiting_acknowledgement':raise ValueError('Observation offer expired during verification')
            session['timer'].cancel()
            session['started'] = self.clock()
            session['phase'] = 'active'
            binding = dict(session['binding'], _expires_at=session['started'] + DURATION)
            try:
                stream = self.stream_factory(self.source,binding,session['directory']/'stream',
                    started=session['started'],deadline=session['started']+DURATION,clock=self.clock,
                    on_terminal=lambda status:self._stream_terminal(session['id'],status))
                session['stream'] = stream
                self.streams = [owner for owner in self.streams if owner.status()['worker_alive']]
                self.streams.append(stream)
                stream.start()
            except Exception:
                self._stop('unavailable');raise
            self._history_visit(session)
            session['timer'] = self.schedule(DURATION,lambda:self._expire(session['id'],'expired','active',session['started'] + DURATION))
            return self._state(session)

    def _derive_detail(self, session, packet):
        """Optional bounded Eye derivation; it must never limit original visual recording."""
        frame = packet.get('detail_frame', {})
        ident = packet['detail_frame_id']
        observer = session.get('observer')
        capture = packet.get('detail_capture', frame.get('capture', {}))
        now = time.monotonic_ns()
        start, stamp = capture.get('capture_started_ns'), capture.get('captured_ns')
        if (observer is None or observer.sequence >= 32 or type(start) is not int or type(stamp) is not int
                or not 0 <= start <= stamp <= now or now-start > 2_500_000_000):
            return dict(measurement_state='unavailable',reason='detail outside derived freshness or sample limit')
        if ident in session['derived_details']:
            return session['derived_details'][ident]
        try:
            from PIL import Image
            path = Path(packet['detail_image_path'])
            with path.open('rb') as original:raw = original.read(8*1024*1024+1)
            if len(raw) > 8*1024*1024 or hashlib.sha256(raw).hexdigest() != packet['detail_sha256']:
                raise ValueError('Detail original no longer matches its verified image')
            with Image.open(path) as image:
                report = observer.observe(image,capture)
            result = dict(measurement=report,measurement_state='derived',measurement_frame_id=ident)
        except Exception as error:
            result = dict(measurement_state='unavailable',reason=str(error)[:300])
        session['derived_details'][ident] = result
        return result

    def read(self, session_id, after_sequence=None):
        if after_sequence is not None and (type(after_sequence) is not int or not 0 <= after_sequence <= 466):
            raise ValueError('after_sequence must be an integer from 0 to 466')
        with self.lock:
            session = self._session(session_id)
            phase = self._state(session)['phase']
            if phase == 'active':
                session = self._active(session_id)
            elif phase != 'expired':
                raise ValueError('Observation is not active or naturally expired')
            stream = session.get('stream')
            if stream is None:raise ValueError('No continuous visual recording is available')
            cursor = session['read_cursor'] if after_sequence is None else after_sequence
            try:packet = stream.packet(after_sequence=cursor)
            except Exception:
                if session is self.current and session['phase']=='active':self._stop('unavailable')
                raise
            state = self._state(session)
            if state['phase'] not in ('active','expired'):
                raise ValueError('Continuous visual recording is no longer available')
            if packet is None:
                return dict(**state,visual_state='recorded' if state['phase']=='expired' else 'live',
                            next_sequence=cursor,frame_count=0)
            historical = state['phase']=='expired'
            packet = dict(packet,frame_id=packet['packet_id'],session_id=session_id,
                          visual_state='recorded' if historical else 'live')
            derivation = (dict(measurement_state='recorded',reason='Recorded visual; no live Eye derivation')
                          if historical else self._derive_detail(session,packet))
            # Derivation can be slow; never return expired work labelled as live.
            state = self._state(session)
            if state['phase']=='expired':
                packet['visual_state']='recorded'
                derivation=dict(measurement_state='recorded',reason='Recorded visual; no live Eye derivation')
            elif state['phase']!='active':raise ValueError('Observation stopped during visual delivery')
            else:
                self._active(session_id)  # Recheck native source after potentially slow packet/Eye work.
                state = self._state(session)
            # Packet preparation is not delivery: MCP first verifies and materializes
            # both images, then commits this internal offer without a public acknowledgement.
            keys = ('frame_id','packet_id','panel_kind','sequence_start','sequence_end','next_sequence',
                    'frame_count','interval_started','interval_ended','image_path','sha256','detail_image_path',
                    'detail_sha256','detail_frame_id','detail_sequence','detail_capture_time','session_id','visual_state')
            session['staged_packets'][packet['packet_id']] = {key:packet[key] for key in keys if key in packet}
            return dict(packet,**{k:v for k,v in state.items() if k!='session_id'},**derivation)

    def commit_read(self, metadata):
        """Internal transport commit after both ImageContent blocks were verified.

        This is not an agent acknowledgement and has no effect on the fixed lease.
        Failed serialization leaves the default cursor and note evidence untouched.
        """
        with self.lock:
            session = self._session(metadata['session_id'])
            packet_id = metadata['packet_id']
            summary = session['staged_packets'].get(packet_id)
            if summary is None or any(metadata.get(key)!=summary.get(key)
                    for key in ('sha256','detail_sha256','next_sequence')):
                raise ValueError('Unknown or changed staged visual packet')
            state = self._state(session)
            if state['phase']=='active':
                self._active(session['id'])
                state = self._state(session)
            elif state['phase']!='expired':
                raise ValueError('Observation stopped before visual delivery')
            if packet_id not in session['offered_packets']:
                summary = dict(summary,visual_state='recorded' if state['phase']=='expired' else 'live')
                payload = dict(summary)
                for key in ('image_path','detail_image_path'):
                    payload[key] = str(Path(payload[key]).absolute().relative_to(self.root.absolute()))
                self._history_record(session,'frame',payload,event_id=packet_id)
            # History I/O can cross expiry. Retained pixels remain available without
            # any new source contact/capture/derivation or input authority.
            state = self._state(session)
            if state['phase'] not in ('active','expired'):
                raise ValueError('Observation stopped during visual delivery')
            summary = dict(summary,visual_state='recorded' if state['phase']=='expired' else 'live')
            session['offered_packets'][packet_id] = summary
            session['frames'][packet_id] = summary
            session['read_cursor'] = max(session['read_cursor'],summary['next_sequence'])
            result = dict(metadata,**{k:v for k,v in state.items() if k!='session_id'},
                          visual_state=summary['visual_state'])
            if state['phase']=='expired':
                for key in ('measurement','measurement_frame_id'):
                    result.pop(key,None)
                result.update(measurement_state='recorded',reason='Recorded visual; no live Eye derivation')
            return result

    def status(self, session_id=None):
        with self.lock:
            if not self.current and session_id is None:return dict(phase='idle',remaining_seconds=None,duration_seconds=DURATION)
            session = self._session(session_id)
            if self._state(session)['phase'] in ('active','awaiting_acknowledgement'):
                try:self._check_source(session)
                except Exception:self._stop('unavailable')
            return self._state(session)

    def note(self, session_id, frame_id=None, description=None):
        with self.lock:
            session = self._session(session_id)
            if not session['frames']:raise ValueError('A visual account requires at least one verified observation frame')
            if frame_id is not None and frame_id not in session['frames']:raise ValueError('Unknown observation frame')
            if not isinstance(description,str) or not 1 <= len(description.encode()) <= 4096:
                raise ValueError('Description must be 1..4096 UTF-8 bytes')
            if session['notes'] >= 64:raise ValueError('Observation note storage is full')
            scope = 'overall' if frame_id is None else 'frame'
            references = [dict(frame_id=key,frame_sha256=frame['sha256'],
                               **({'detail_sha256':frame['detail_sha256']} if 'detail_sha256' in frame else {}))
                          for key,frame in session['frames'].items()]
            evidence = (references[:1] + references[1:][-64:] if frame_id is None else
                        [next(row for row in references if row['frame_id']==frame_id)])
            record = dict(session_id=session_id,scope=scope,evidence_frames=evidence,source='observer agent',
                          epistemic_label='agent_interpretation',description=description,sent_to_alien=False,
                          **{k:session['binding'].get(k) for k in ('world_id','runtime','segment_id','window_id','pid','crop','size')})
            if frame_id is None and len(references)>len(evidence):
                record.update(omitted_earlier_offered_references=len(references)-len(evidence),
                              offered_evidence_sha256=hashlib.sha256(json.dumps(references,sort_keys=True).encode()).hexdigest())
            if len(json.dumps(record,ensure_ascii=False).encode())>32768:
                raise ValueError('Visual account exceeds bounded history record')
            if frame_id is not None:
                record.update(frame_id=frame_id,frame_sha256=session['frames'][frame_id]['sha256'])
            path = session['directory']/'notes.jsonl'
            fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
            with os.fdopen(fd,'a') as stream:
                stream.write(json.dumps(record,ensure_ascii=False)+'\n');stream.flush();os.fsync(stream.fileno())
            session['notes'] += 1
            self._history_record(session, 'note', record)
            return dict(source='observer agent',sent_to_alien=False,notes_path=str(path),scope=scope,
                        **({'frame_id':frame_id} if frame_id is not None else {}),
                        **({'history_error':self.history_error} if self.history_error else {}))

    def say(self, session_id, text, request_id):
        with self.lock:
            session = self._active(session_id)
            if not isinstance(text,str) or not 1 <= len(text.encode()) <= 4096:raise ValueError('Words must be 1..4096 UTF-8 bytes')
            if not isinstance(request_id,str) or not ID.fullmatch(request_id):raise ValueError('Use an opaque32-hex request ID')
            digest = hashlib.sha256(text.encode()).hexdigest()
            previous_digest = session['attempted'].get(request_id)
            if previous_digest is not None and previous_digest != digest:
                raise ValueError('Request ID already belongs to different words')
            prior = session['sent'].get(request_id)
            if prior:
                # Receipt I/O is retried, never the physical send, after a completed dispatch.
                self._history_record(session, 'word_receipt', session['receipt_records'][request_id],
                                     event_id=f'{session["id"]}:{request_id}:receipt')
                return prior[1]
            if len(session['attempted']) >= 128 and previous_digest is None:
                raise ValueError('Words receipt storage is full')
            participant = participant_name(self.channel['name']) if self.channel else None
            intent = dict(request_id=request_id, text=text, text_sha256=digest,
                          source=word_source(participant), authority='unauthority')
            self._history_record(session, 'word_intent', intent,
                                 event_id=f'{session["id"]}:{request_id}:intent', required=True)
            session['attempted'][request_id] = digest
            binding = dict(session['binding'], _expires_at=session['started'] + DURATION)
            if self._state(session)['phase'] != 'active':
                raise ValueError('Observation expired before words dispatch')
            attempt = session['attempts'].get(request_id, 0) + 1
            session['attempts'][request_id] = attempt
            try:
                answer = (self.source.say(binding,text,request_id,participant=participant) if participant
                          else self.source.say(binding,text,request_id))
            except Exception as error:
                self._history_record(session, 'word_error', dict(request_id=request_id, text_sha256=digest,
                    attempt=attempt, error=str(error)[:1000], error_type=type(error).__name__, delivery='unknown'))
                if isinstance(error, WordsPending):
                    try:self._check_source(session)
                    except Exception:self._stop('unavailable')
                    self._state(session)
                else:
                    self._stop('unavailable')
                raise
            if (not isinstance(answer, dict) or answer.get('source') not in {word_source(participant), UNNAMED}
                    or answer.get('authority') != 'unauthority' or answer.get('state') != 'received'):
                self._history_record(session, 'word_error', dict(request_id=request_id, text_sha256=digest,
                    attempt=attempt, error='Alien did not return an attributed received receipt',
                    error_type='InvalidReceipt', delivery='unknown'))
                self._stop('unavailable')
                raise ValueError('Alien did not preserve observer attribution or receipt')
            # Cache the real receipt before optional journal I/O. A full disk cannot resend words.
            session['sent'][request_id] = (digest,answer)
            payload = dict(request_id=request_id, text_sha256=digest, attempt=attempt, receipt=answer)
            session['receipt_records'][request_id] = payload
            self._history_record(session, 'word_receipt', payload,
                                 event_id=f'{session["id"]}:{request_id}:receipt')
            return answer

    def close(self, session_id=None):
        with self.lock:
            if not self.current and session_id is None:return dict(phase='idle')
            session = self._session(session_id)
            if session is self.current:self._stop('closed')
            return self._state(session)

    def shutdown(self):
        with self.lock:
            self._stop('closed')
            streams = list(self.streams)
            for stream in streams:stream.stop(reason='shutdown')
        # Capture publication never waits behind a join holding the manager lock.
        for stream in streams:stream.join(timeout=7.0)
        with self.lock:
            if self.journal is not None:
                self.journal.close()
                self.journal = None
                self.channels = None
