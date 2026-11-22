"""Read-only presentation of observer history; no capture or dispatch capabilities."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import time


MAX_IMAGE_BYTES = 32 * 1024 * 1024
SHA256 = re.compile(r'^[a-f0-9]{64}$')


def read_process_start(pid):
    """Return the kernel process-start token, refusing dead and zombie processes."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    try:
        raw = Path(f'/proc/{pid}/stat').read_text()
        fields = raw[raw.rindex(')') + 2:].split()
        if fields[0] in ('Z', 'X'):
            return None
        token = fields[19]  # field22; process comm may contain spaces or parentheses.
        return token if token.isdigit() else None
    except (OSError, ValueError, IndexError):
        return None


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def visit_status(visit, *, now=None, process_reader=read_process_start):
    """A recorded active phase alone is never evidence of a current connection."""
    disconnected = dict(connected=False, remaining_seconds=None)
    phase = visit.get('phase')
    if phase != 'active':
        labels = {'awaiting_acknowledgement': 'Awaiting image acknowledgement', 'closed': 'Closed',
                  'expired': 'Expired', 'offer_expired': 'Image offer expired', 'unavailable': 'Unavailable'}
        return dict(disconnected, label=labels.get(phase, 'Unavailable'))
    now = time.monotonic() if now is None else now
    start, duration = visit.get('started_monotonic'), visit.get('duration')
    if (not _finite(start) or start < 0 or not _finite(now) or now < start
            or not _finite(duration) or not 0 < duration <= 93):
        return dict(disconnected, label='Unavailable · invalid observation clock')
    if now >= start + duration:
        return dict(disconnected, label='Expired')
    token = visit.get('process_start')
    try:
        actual = process_reader(visit.get('process_pid'))
    except (OSError, ValueError, TypeError):
        actual = None
    if not isinstance(token, str) or not token.isdigit() or actual != token:
        return dict(disconnected, label='Unavailable · observer process ended')
    remaining = start + duration - now
    return dict(connected=True, remaining_seconds=remaining,
                label=f'Connected · {math.ceil(remaining)} s remaining')


def profile_status(profile, visits, *, now=None, process_reader=read_process_start):
    if profile.get('kind') != 'mcp':
        return dict(connected=False, remaining_seconds=None, label='Not connected · future connector')
    for visit in visits:
        if visit.get('observer_id') == profile.get('id'):
            state = visit_status(visit, now=now, process_reader=process_reader)
            if state['connected']:
                return state
    return dict(connected=False, remaining_seconds=None, label='Not connected')


def event_time(value):
    try:
        if _finite(value):
            return datetime.fromtimestamp(value, timezone.utc).strftime('%d %b %Y · %H:%M:%S UTC')
        return str(value)[:80] if value is not None else 'Time unavailable'
    except (ValueError, OSError, OverflowError):
        return 'Time unavailable'


def _text(value):
    return value if isinstance(value, str) else ''


def timeline_rows(events, *, snapshots=True):
    """Group retries by logical request while retaining every recorded outcome."""
    events = [event for event in events if isinstance(event, dict)]
    frames = {event.get('payload', {}).get('frame_id'): event['payload'] for event in events
              if event.get('kind') == 'frame' and isinstance(event.get('payload'), dict)}
    rows, words = [], {}
    for event in events:
        kind, payload = event.get('kind'), event.get('payload')
        if not isinstance(payload, dict):
            continue
        common = dict(id=event.get('id'), created_at=event.get('created_at'), image=None)
        if kind == 'frame' and snapshots:
            overview = payload.get('panel_kind') == 'temporal_overview'
            details = f"Frame {payload.get('frame_id', '')}\nSHA256 {payload.get('sha256', '')}"
            if overview:
                details += (f"\nSequence {payload.get('sequence_start', '?')}–{payload.get('sequence_end', '?')}"
                            f"\nFull-detail capture time: {payload.get('detail_capture_time', 'unavailable')}"
                            "\nOverview thumbnails show the interval; full detail has its own capture time.")
            rows.append(dict(common, kind='frame', title='Visual interval' if overview else 'Captured image', text='',
                             status='Temporal overview · retained interval pictures' if overview else
                                    'Actual field image · retained when available', image=payload, details=details))
        elif kind == 'note' and payload.get('scope') == 'overall':
            evidence = payload.get('evidence_frames')
            evidence = [ref for ref in evidence if isinstance(ref, dict)] if isinstance(evidence, list) else []
            verified = [frames[ref['frame_id']] for ref in evidence
                        if isinstance(ref.get('frame_id'), str) and ref['frame_id'] in frames
                        and isinstance(ref.get('frame_sha256'), str)
                        and SHA256.fullmatch(ref['frame_sha256'])
                        and frames[ref['frame_id']].get('sha256') == ref['frame_sha256']]
            details = ['Source: observer agent', 'Overall visual account · agent interpretation']
            details.extend(f"Frame {ref.get('frame_id', '')}\nSHA256 {ref.get('frame_sha256', '')}"
                           for ref in evidence)
            rows.append(dict(common, kind='overall', title='Overall visual account',
                             text=_text(payload.get('description')),
                             status='Agent interpretation · not sent to Alien',
                             image=verified[-1] if verified else None, details='\n'.join(details)))
        elif kind == 'note' and snapshots:
            rows.append(dict(common, kind='note', title='Snapshot description', text=_text(payload.get('description')),
                             status='Agent interpretation · not sent to Alien',
                             image=frames.get(payload.get('frame_id')),
                             details=f"Source: observer agent\nFrame {payload.get('frame_id', '')}\n"
                                     f"SHA256 {payload.get('frame_sha256', '')}"))
        elif kind in ('word_intent', 'word_receipt', 'word_error'):
            request_id = payload.get('request_id')
            key = request_id if isinstance(request_id, str) and request_id else f"missing:{event.get('id')}"
            if key not in words:
                row = dict(common, kind='words', title='Words to Alien', text='', status='Delivery unverified',
                           request_id=request_id, attempts=[], details='')
                words[key] = row
                rows.append(row)
            words[key]['attempts'].append(event)
    for row in words.values():
        intents = [event['payload'] for event in row['attempts'] if event['kind'] == 'word_intent']
        texts = [_text(payload.get('text')) for payload in intents]
        row['text'] = texts[0] if texts else '(Words text unavailable)'
        hashes = {payload['text_sha256'] for payload in intents if isinstance(payload.get('text_sha256'), str)}
        conflict = (len(set(texts)) > 1 or len(hashes) > 1
                    or any(payload.get('text_sha256') and payload['text_sha256'] != hashlib.sha256(
                        _text(payload.get('text')).encode()).hexdigest() for payload in intents))
        details = [f"Request: {row.get('request_id') or 'unavailable'}", 'Source: observer agent · authority: unauthority']
        received, has_error, all_not_received, dispatched = False, False, True, False
        for event in row['attempts']:
            payload, kind = event['payload'], event['kind']
            stamp = event_time(event.get('created_at'))
            if kind == 'word_intent':
                dispatched = True
                details.append(f"{stamp} · Attempt recorded: {_text(payload.get('text'))}")
            elif kind == 'word_error':
                has_error = True
                all_not_received = all_not_received and payload.get('delivery') == 'not_received'
                details.append(f"{stamp} · {payload.get('delivery', 'unknown')}: {_text(payload.get('error'))}")
            elif kind == 'word_receipt':
                receipt = payload.get('receipt')
                if not isinstance(receipt, dict):
                    receipt = {}
                receipt_hash = payload.get('text_sha256')
                if receipt_hash and hashes and receipt_hash not in hashes:
                    conflict = True
                src = receipt.get('source')
                valid = (receipt.get('state') == 'received'
                         and (src == 'observer agent' or (isinstance(src, str) and src.startswith('observer:')))
                         and receipt.get('authority') == 'unauthority' and bool(receipt.get('input_id')))
                received = received or valid
                details.append(f"{stamp} · Native receipt: {receipt.get('state', 'unverified')}"
                               f" · input {receipt.get('input_id', 'unavailable')}"
                               f" · source {receipt.get('source', 'unavailable')}"
                               f" · authority {receipt.get('authority', 'unavailable')}")
        if conflict:
            row['status'] = 'Conflicting history'
        elif received:
            row['status'] = 'Received by Alien'
        elif has_error:
            row['status'] = 'Not received' if all_not_received else 'Delivery unknown'
        elif dispatched and not any(event['kind'] == 'word_receipt' for event in row['attempts']):
            row['status'] = 'Delivery unknown · intent recorded'
        row['details'] = '\n'.join(details)
    for row in rows:
        image = row.get('image') or {}
        path, digest = image.get('detail_image_path'), image.get('detail_sha256')
        row['detail_image'] = (dict(image_path=path, sha256=digest, image_role='full_detail',
                                    frame_id=image.get('detail_frame_id'))
                               if isinstance(path, str) and isinstance(digest, str)
                               and SHA256.fullmatch(digest) else None)
    return rows


def _file_fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def frame_fingerprint(root, frame):
    """Stat the same confined regular file; no symlinks or file bytes are read."""
    path = frame.get('image_path')
    if not isinstance(path, str) or not path or '\x00' in path or '\\' in path:
        return None
    relative = PurePosixPath(path)
    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
        return None
    descriptors = []
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(directory)
        for part in relative.parts[:-1]:
            directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            descriptors.append(directory)
        file_fd = os.open(relative.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        descriptors.append(file_fd)
        info = os.fstat(file_fd)
        if stat.S_ISREG(info.st_mode) and info.st_size <= MAX_IMAGE_BYTES:
            return _file_fingerprint(info)
    except (OSError, ValueError, TypeError):
        pass
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    return None


def read_frame_image(root, frame, *, max_bytes=MAX_IMAGE_BYTES):
    """Read one immutable byte snapshot under root without following any symlink."""
    def unavailable(reason):
        return dict(available=False, data=None, reason=reason)
    path, digest = frame.get('image_path'), frame.get('sha256')
    if not isinstance(path, str) or not path or '\x00' in path:
        return unavailable('Image unavailable · unsafe image path')
    relative = PurePosixPath(path)
    if relative.is_absolute() or '..' in relative.parts or not relative.parts or '\\' in path:
        return unavailable('Image unavailable · unsafe image path')
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        return unavailable('Image unavailable · original hash missing')
    descriptors = []
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(directory)
        for part in relative.parts[:-1]:
            directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            descriptors.append(directory)
        file_fd = os.open(relative.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        descriptors.append(file_fd)
        meta = os.fstat(file_fd)
        if not stat.S_ISREG(meta.st_mode):
            return unavailable('Image unavailable · not a regular image')
        if meta.st_size > max_bytes:
            return unavailable('Image unavailable · image too large')
        pieces, size = [], 0
        while True:
            piece = os.read(file_fd, min(65536, max_bytes + 1 - size))
            if not piece:
                break
            pieces.append(piece)
            size += len(piece)
            if size > max_bytes:
                return unavailable('Image unavailable · image too large')
        data = b''.join(pieces)
        if hashlib.sha256(data).hexdigest() != digest:
            return unavailable('Image unavailable · original hash does not match')
        fingerprint = _file_fingerprint(meta)
        if fingerprint != _file_fingerprint(os.fstat(file_fd)):
            fingerprint = None
        return dict(available=True, data=data, reason='Original image verified', fingerprint=fingerprint)
    except (OSError, ValueError, TypeError):
        return unavailable('Image unavailable · missing, unsafe or no longer retained')
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
