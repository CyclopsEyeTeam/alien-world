"""ACK-gated written computations on the hive's existing native tick stream.

The two lanes are computed representations, never independent outside evidence.
Source archives are inert history. Only this process's issued, typed letter
events can enter the learning adaptor; no archive is restored or replayed here.
"""
import asyncio
from collections import OrderedDict, deque
import copy
import hashlib
import json
from queue import SimpleQueue, Empty
import math
import uuid

from alphabet_math import PROFILE_ID, index_to_value
from world_clock import validate_stamp


_LANES = ("incoming", "own")
_STAMP_KEYS = ("world_id", "segment_id", "tick", "period", "cycle", "slot", "pi", "version")


def _stamp(value):
    try:
        validated = validate_stamp(value)
        return None if validated is None else {key: copy.deepcopy(validated[key]) for key in _STAMP_KEYS}
    except (ValueError, TypeError, KeyError):
        return None


def _typed_equal(actual, expected):
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(
            _typed_equal(actual[key], value) for key, value in expected.items())
    if type(expected) is list:
        return len(actual) == len(expected) and all(
            _typed_equal(value, wanted) for value, wanted in zip(actual, expected))
    return actual == expected


def _json_safe(value):
    if value is None or type(value) in (str, int, bool):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is list:
        return all(_json_safe(item) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _json_safe(item) for key, item in value.items())
    return False


def _symbols(text):
    events = []
    for char in text:
        if "A" <= char <= "Z" or "a" <= char <= "z":
            index = ord(char.upper()) - 65
            events.append(dict(type="letter", char=char, index=index,
                               value=index_to_value(index), exponent=[2 * index, 25]))
        elif char == " ":
            events.append(dict(type="space", char=char))
        else:
            events.append(dict(type="rejected", char=char, reason="unmapped_symbol"))
    return events


class AlphabetRift:
    def __init__(self, cache, clock, runtime):
        if type(runtime) is not str or not runtime or len("native.alphabet.incoming|" + runtime) > 96:
            raise ValueError("Alphabet runtime must fit a bounded native source identity.")
        self.cache = cache
        self.clock = clock
        self.runtime = runtime
        self.sources = {lane: "native.alphabet." + lane + "|" + runtime for lane in _LANES}
        self.closed = self.sleeping = self.dreaming = self.load_high = False
        self.load_stride = 1
        self.loop = None
        self._acks = SimpleQueue()
        self._jobs = OrderedDict()
        self._lanes = {lane: deque() for lane in _LANES}
        self._epochs = {lane: 0 for lane in _LANES}
        self._active = {lane: None for lane in _LANES}
        self._issued = OrderedDict()
        self._seen = OrderedDict()
        self._queued_bytes = 0
        self._next_lane = 0
        self.steering = None
        self._last_lane = None
        self._lane_run = 0
        self._timeline = None
        self._highest_tick = None
        self._last_tick = None
        self._cadence_stamp = None
        self._counts = dict(inputs_incoming=0, inputs_own=0, letters=0, spaces=0,
                            rejected_symbols=0, refused=0, archive_failed=0, deferred=0)
        initial = self._current()
        if initial is not None:
            self._timeline = (initial["world_id"], initial["segment_id"])
            self._highest_tick = initial["tick"]
            self._last_tick = (*self._timeline, initial["tick"])
        self._bind()

    def _current(self):
        try:
            return _stamp(self.clock.stamp())
        except (ValueError, TypeError, AttributeError):
            return None

    def _bind(self):
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self.loop is None:
            self.loop = current

    def _paused(self):
        return self.closed or self.sleeping or self.dreaming

    def _retire(self, cancel=False):
        self._issued.clear()
        for lane in _LANES:
            self._epochs[lane] += 1
            self._active[lane] = None
        if cancel:
            self._counts["refused"] += len(self._jobs)
            self._jobs.clear()
            for lane in _LANES:
                self._lanes[lane].clear()
            self._queued_bytes = 0
            self._cadence_stamp = None

    def _sync(self):
        stamp = self._current()
        if stamp is None:
            if self._timeline is not None:
                self._retire(cancel=True)
                self._timeline = self._highest_tick = self._last_tick = None
            return None
        timeline = (stamp["world_id"], stamp["segment_id"])
        if self._timeline is None:
            self._timeline = timeline
        elif timeline != self._timeline:
            self._retire(cancel=True)
            self._timeline = timeline
            self._last_tick = (*timeline, stamp["tick"])
            self._highest_tick = None
        if self._highest_tick is not None and stamp["tick"] < self._highest_tick:
            self._retire(cancel=True)
            return None
        self._highest_tick = stamp["tick"]
        return stamp

    def _remove(self, job):
        if self._jobs.pop(job["id"], None) is not None:
            self._lanes[job["lane"]].remove(job["id"])
            self._queued_bytes -= job["bytes"]

    def _finish_ack(self, ident, success, ack_stamp):
        if self.closed:
            return
        job = self._jobs.get(ident)
        if job is None or job["state"] != "waiting":
            return
        if success:
            job["state"] = "ready"
            job["ack_stamp"] = ack_stamp
        else:
            self._counts["archive_failed"] += 1
            self._remove(job)

    def _ack(self, ident, success):
        # The writer callback performs no publication and never advances time.
        # Readiness mutations belong to the owning loop (or next synchronous
        # fixture event when no loop is bound), including cross-thread ACKs.
        if self.closed:
            return
        ack_stamp = self._current()
        if self.loop is not None and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self._finish_ack, ident, success, ack_stamp)
        else:
            self._acks.put((ident, success, ack_stamp))

    def _apply_acks(self):
        while True:
            try:
                record = self._acks.get_nowait()
            except Empty:
                return
            self._finish_ack(*record)

    def offer(self, lane, text, provenance=None):
        """Retain one whole source or explicitly refuse it; never strip symbols."""
        self._bind()
        stamp = self._sync()
        if self.closed or stamp is None or lane not in _LANES or type(text) is not str:
            self._counts["refused"] += 1
            return False
        try:
            size = len(text.encode("utf-8"))
            if provenance is not None and (type(provenance) is not dict or not _json_safe(provenance)):
                raise ValueError("Invalid provenance")
            packed_provenance = json.dumps(provenance, ensure_ascii=False, allow_nan=False, sort_keys=True)
            if len(packed_provenance.encode("utf-8")) > 8192:
                raise ValueError("Oversized provenance")
            retained = copy.deepcopy(provenance)
            if retained is not None:
                if "runtime" in retained and retained["runtime"] != self.runtime:
                    raise ValueError("Stale runtime")
                for field in ("source_stamp", "admitted_stamp"):
                    if field in retained and not _typed_equal(_stamp(retained[field]), stamp):
                        raise ValueError("Stale source stamp")
        except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
            self._counts["refused"] += 1
            return False
        if (size > 4096 or len(self._jobs) >= 8 or len(self._lanes[lane]) >= 4 or
                self._queued_bytes + size > 16384):
            self._counts["refused"] += 1
            return False
        identity = None
        if retained and ("input_id" in retained or "publication_id" in retained):
            identity = hashlib.sha256(json.dumps(
                [lane, stamp["world_id"], stamp["segment_id"],
                 retained.get("input_id"), retained.get("publication_id")],
                sort_keys=True, allow_nan=False).encode()).hexdigest()
            if identity in self._seen:
                self._counts["refused"] += 1
                return False
        ident = uuid.uuid4().hex
        record = dict(schema="ALIEN_ALPHABET_WRITTEN_STUDY_V1", profile=PROFILE_ID,
                      study_id=ident, runtime=self.runtime, lane=lane, source=self.sources[lane],
                      source_text=text, source_stamp=copy.deepcopy(stamp), provenance=retained,
                      events=_symbols(text), authority="unauthority", semantic_verification="unknown",
                      independent_outside_evidence=False, derived_representation=True)
        job = dict(id=ident, lane=lane, bytes=size, record=record, position=0,
                   state="waiting", ack_stamp=None, cache_ref=None)
        self._jobs[ident] = job
        self._lanes[lane].append(ident)
        self._queued_bytes += size
        try:
            job["cache_ref"] = self.cache.append("alphabet.written.study", copy.deepcopy(record))
            if not isinstance(job["cache_ref"], str) or not 1 <= len(job["cache_ref"]) <= 256:
                raise ValueError("Invalid study archive reference")
            if getattr(self.cache, "background_writer", False):
                self.cache.after_flush(lambda: self._ack(ident, True), lambda _error: self._ack(ident, False))
            else:
                # A synchronous cache's completed flush is its durability ACK.
                self.cache.flush()
                self._ack(ident, True)
        except (OSError, ValueError, TypeError, AttributeError):
            self._counts["archive_failed"] += 1
            self._remove(job)
            return False
        if identity is not None:
            self._seen[identity] = True
            while len(self._seen) > 512:
                self._seen.popitem(last=False)
        self._counts["inputs_" + lane] += 1
        return True

    def _publish(self, job, stamp, bus):
        lane = job["lane"]
        position = job["position"]
        event = copy.deepcopy(job["record"]["events"][position])
        proof = dict(profile=PROFILE_ID, study_id=job["id"], lane=lane, position=position,
                     event=event, cache_ref=job["cache_ref"],
                     provenance=copy.deepcopy(job["record"]["provenance"]))
        body = dict(alphabet=proof, source=self.sources[lane], source_epoch=self._epochs[lane],
                    source_stamp=copy.deepcopy(job["record"]["source_stamp"]), world_stamp=copy.deepcopy(stamp),
                    authority="unauthority", confidence=0., semantic_verification="unknown",
                    derived_representation=True, independent_outside_evidence=False,
                    char=event["char"], vid="alphabet:" + job["id"][:24] + ":" + str(position))
        provenance = job["record"]["provenance"] or {}
        if type(provenance.get("context_ref")) is str and len(provenance["context_ref"]) <= 256:
            body["context_ref"] = provenance["context_ref"]
        if type(provenance.get("origin")) is dict:
            body["origin"] = copy.deepcopy(provenance["origin"])
        if event["type"] == "letter":
            index, value = event["index"], event["value"]
            body.update(index=index, value=value, exponent=event["exponent"][:], log=math.log10(value),
                        scale=value, focus="scale", constant="alphabet",
                        text=f"{event['char']}[{index}] 220*2^({2 * index}/25)")
            proof["issued_id"] = uuid.uuid4().hex
            self._issued[proof["issued_id"]] = dict(body=copy.deepcopy(body), consumed=False,feeling_consumed=False,
                evidence=hashlib.sha256(json.dumps(body, sort_keys=True, allow_nan=False).encode()).hexdigest())
            while len(self._issued) > 128:
                self._issued.popitem(last=False)
            self._active[lane] = copy.deepcopy(stamp)
            name = "numeric_pattern"
            self._counts["letters"] += 1
        elif event["type"] == "space":
            name = "alphabet_space"
            self._counts["spaces"] += 1
        else:
            name = "alphabet_rejected"
            self._counts["rejected_symbols"] += 1
        job["position"] += 1
        if job["position"] == len(job["record"]["events"]):
            self._remove(job)
        self._cadence_stamp = copy.deepcopy(stamp)
        bus.publish(name, body)

    def on_event(self, name, body, bus):
        self._bind()
        if name == "shutdown":
            self.close()
            return
        if self.closed:
            return
        stamp = self._sync()
        self._apply_acks()
        was_paused = self._paused()
        was_loaded = self.load_high
        if name == "enter_sleep":
            self.sleeping = True
        elif name == "wake":
            self.sleeping = False
        elif name == "dream_begin":
            self.dreaming = True
        elif name == "dream_end":
            self.dreaming = False
        elif name == "load":
            self.load_high = bool(body.get("high"))
            skip = body.get("skip")
            self.load_stride = max(4, skip if type(skip) is int and skip > 0 else 1) if self.load_high else 1
        entering_load = self.load_high and not was_loaded
        if (not was_paused and self._paused()) or entering_load:
            self._retire()
        if entering_load:
            self._cadence_stamp = copy.deepcopy(stamp)
        if name != "tick" or stamp is None:
            return
        if (type(body) is not dict or type(body.get("tick")) is not int or body["tick"] != stamp["tick"] or
                "world_stamp" in body and not _typed_equal(_stamp(body["world_stamp"]), stamp)):
            return
        key = (stamp["world_id"], stamp["segment_id"], stamp["tick"])
        if key == self._last_tick:
            return
        self._last_tick = key
        if self._paused():
            if self._jobs:
                self._counts["deferred"] += 1
            return
        # Native load can remain high indefinitely at full detail. Slow this
        # new stream using genuine tick distance rather than starving it or
        # changing the existing LoadAgent, clock or display cadence.
        previous = self._cadence_stamp
        stride=max(self.load_stride if self.load_high else 1,
                   self.steering.study_stride() if self.steering is not None else 1)
        if (stride>1 and previous is not None and
                all(previous[field] == stamp[field] for field in ("world_id", "segment_id")) and
                stamp["tick"] - previous["tick"] < stride):
            if self._jobs:
                self._counts["deferred"] += 1
            return
        order=[(self._next_lane+offset)%2 for offset in range(2)]
        preferred=self.steering.preferred_lane() if self.steering is not None else None
        if preferred in _LANES and (self._last_lane!=preferred or self._lane_run<2):
            index=_LANES.index(preferred);order=[index,1-index]
        for lane_index in order:
            queue = self._lanes[_LANES[lane_index]]
            while queue:
                job = self._jobs[queue[0]]
                if job["state"] != "ready":
                    break
                if not job["record"]["events"]:
                    self._remove(job)
                    continue
                ack = job["ack_stamp"]
                if (ack is None or any(ack[field] != stamp[field] for field in ("world_id", "segment_id")) or
                        stamp["tick"] <= max(ack["tick"], job["record"]["source_stamp"]["tick"])):
                    break
                self._next_lane = (lane_index + 1) % 2
                lane=_LANES[lane_index]
                self._lane_run=self._lane_run+1 if lane==self._last_lane else 1
                self._last_lane=lane
                self._publish(job, stamp, bus)
                return
        if self._jobs:
            self._counts["deferred"] += 1

    def source_active(self, row):
        stamp = self._sync()
        if self._paused() or stamp is None or type(row) is not dict or type(row.get("source_epoch")) is not int:
            return False
        lane = next((lane for lane in _LANES if row.get("source") == self.sources[lane]), None)
        if lane is None or row["source_epoch"] != self._epochs[lane]:
            return False
        active = self._active[lane]
        if active is None or any(active[field] != stamp[field] for field in ("world_id", "segment_id")) or not 0 <= stamp["tick"] - active["tick"] <= 64:
            return False
        if "world_stamp" in row:
            origin = _stamp(row["world_stamp"])
            if origin is None or any(origin[field] != stamp[field] for field in ("world_id", "segment_id")) or origin["tick"] > stamp["tick"]:
                return False
        return True

    def owns(self,body):
        """Non-consuming feeling check after bounded bus context additions."""
        from rift_interface import owned_projection
        if type(body) is not dict or type(body.get('alphabet')) is not dict:return False
        ident=body['alphabet'].get('issued_id');issued=self._issued.get(ident) if type(ident) is str else None
        return bool(issued and owned_projection(body,issued['body']) and self.source_active(dict(source=body['source'],source_epoch=body['source_epoch'],world_stamp=body['world_stamp'])))

    def claim_feeling(self,body):
        if not self.owns(body):return False
        issued=self._issued[body['alphabet']['issued_id']]
        if issued['feeling_consumed']:return False
        issued['feeling_consumed']=True
        return True

    def measurement(self, body):
        if type(body) is not dict or type(body.get("alphabet")) is not dict:
            return None
        ident = body["alphabet"].get("issued_id")
        issued = self._issued.get(ident) if type(ident) is str else None
        if issued is None or issued["consumed"] or not _typed_equal(body, issued["body"]):
            return None
        if not self.source_active(dict(source=body["source"], source_epoch=body["source_epoch"], world_stamp=body["world_stamp"])):
            return None
        issued["consumed"] = True
        return dict(source=body["source"], epoch=body["source_epoch"], stamp=copy.deepcopy(body["world_stamp"]),
                    evidence=issued["evidence"], features=dict(alphabet_position=body["index"] / 25,
                    log_scale=.5 + math.atan(body["log"]) / math.pi))

    def summary(self):
        return dict(self._counts, pending=len(self._jobs), queued_bytes=self._queued_bytes,
                    closed=self.closed, sleeping=self.sleeping, dreaming=self.dreaming,
                    load_high=self.load_high, load_stride=self.load_stride)

    def close(self):
        if self.closed:
            return
        self._retire(cancel=True)
        self.closed = True
        self._apply_acks()
