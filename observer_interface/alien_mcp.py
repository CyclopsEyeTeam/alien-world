#!/usr/bin/env python3
"""Alien observation MCP stdio boundary. No capture, words or clock starts at startup."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import signal
import sys

from _ev_bootstrap import DEFAULT_OBSERVATIONS

PROTOCOLS = ('2025-06-18', '2025-03-26', '2024-11-05')
MAX_LINE = 128 * 1024
MAX_IMAGE = 8 * 1024 * 1024
MAX_IMAGES_TOTAL = 16 * 1024 * 1024


def _string(*, pattern=None, maximum=4096):
    schema = dict(type='string', minLength=1, maxLength=maximum)
    if pattern:schema['pattern'] = pattern
    return schema


SESSION = _string(maximum=128)
TOKEN = _string(pattern='^[0-9a-f]{32}$', maximum=32)
SHA256 = _string(pattern='^[0-9a-f]{64}$', maximum=64)


def _tool(name, description, properties, required=(), *, read_only=True):
    return dict(name=name, description=description,
                inputSchema=dict(type='object', properties=properties, required=list(required), additionalProperties=False),
                annotations=dict(readOnlyHint=read_only, destructiveHint=False, openWorldHint=False))


TOOLS = [
    _tool('alien_observer_register',
          'Install this agent channel with its chosen display name and actual host binding. A plain lowercase name '
          '(e.g. spark) also labels its words in Alien as unverified observer:<name>; any other name affects history only. '
          'Names never grant authority. Registration does not capture or start a clock.',
          {'name':_string(maximum=128), 'host_kind':dict(type='string', enum=['codex_queue','mcp_wait'],
           minLength=1,maxLength=32), 'thread_id':_string(maximum=128)}, ('name','host_kind'),read_only=False),
    _tool('alien_observer_pending',
          'Read a pending owner Connect request for this registered channel. No observation begins.',
          {'channel_id':TOKEN}, ('channel_id',)),
    _tool('alien_observer_claim',
          'Claim one finite owner Connect request belonging to this registered channel before opening a picture. '
          'Claiming does not start the 93-second observation clock.',
          {'channel_id':TOKEN,'request_id':TOKEN}, ('channel_id','request_id'),read_only=False),
    _tool('alien_observer_wait',
          'Wait up to 60 seconds for an owner Connect request on this registered channel. '
          'Only the actual waiting tool receives a request; no observation or model call is started.',
          {'channel_id':TOKEN,'timeout':dict(type='integer',minimum=1,maximum=60)}, ('channel_id',)),
    _tool('alien_observe_open',
          'Prepare one verified Alien field image via Electric Vision. Opening and sending the image do not start the '
          '93-second clock. Register your channel name first with alien_observer_register if you want named attribution '
          '(and claim an owner Connect request first if --require-owner-connect is enabled). Actually inspect the returned '
          'image, then explicitly confirm its receipt and SHA-256 to begin observing.',
          {'window_id':dict(type='integer', minimum=1)}),
    _tool('alien_observe_confirm',
          'Confirm that the agent received and inspected the offered verified image. Only a valid confirmation starts '
          'the 93-second observation lease; opening, queuing and tool-send time are not charged.',
          {'session_id':SESSION,'receipt':TOKEN,'sha256':SHA256}, ('session_id','receipt','sha256')),
    _tool('alien_observe_read',
          'Return the next chronological visual interval and newest full-detail image pinned at packet creation. '
          'An optional cursor replays that interval; naturally expired visits allow recorded readback. '
          'Pictures do not establish the cause of activity or semantic truth.',
          {'session_id':SESSION,'after_sequence':dict(type='integer',minimum=0,maximum=466)}, ('session_id',)),
    _tool('alien_observe_status',
          'Inspect observation readiness, remaining time and expiry without starting or extending any clock.',
          {'session_id':SESSION}),
    _tool('alien_observe_note',
          'Save the observer agent\'s overall visual account for this visit, grounded in the first supplied picture and offered visual packet hashes. '
          'Optionally supply frame_id for a supporting snapshot note. Notes stay outside the hive and are '
          'attributed to the observer; they are not words sent to Alien or established truth.',
          {'session_id':SESSION,'frame_id':TOKEN,'description':_string()}, ('session_id','description'),
          read_only=False),
    _tool('alien_say',
          'Explicitly send words from the observer agent through Alien\'s existing bounded input path while allowed '
          'by the observation lease. The origin is external agent material, never Owner authority or hive truth. '
          'Words carry observer:<name> when the registered name is plain lowercase, otherwise observer agent. '
          'Use a stable request_id for retries; no model request is made by this tool.',
          {'session_id':SESSION,'text':_string(),'request_id':TOKEN}, ('session_id','text','request_id'),
          read_only=False),
    _tool('alien_observe_close',
          'End this observation connection and release its owned capture/measurement resources. '
          'This does not close, restart or modify the Alien application.', {'session_id':SESSION}),
]
SCHEMAS = {tool['name']:tool['inputSchema'] for tool in TOOLS}
METHODS = dict(alien_observer_register='observer_register',alien_observer_pending='observer_pending',
               alien_observer_claim='observer_claim',alien_observer_wait='observer_wait',alien_observe_open='open',alien_observe_confirm='confirm',alien_observe_read='read',
               alien_observe_status='status',alien_observe_note='note',alien_say='say',alien_observe_close='close')


def _error(ident, code, message):
    return dict(jsonrpc='2.0', id=ident, error=dict(code=code, message=message))


def _validate(name, arguments):
    if name not in SCHEMAS or not isinstance(arguments, dict):
        raise ValueError('Unknown tool or invalid arguments')
    schema = SCHEMAS[name]
    if set(arguments) - set(schema['properties']) or set(schema['required']) - set(arguments):
        raise ValueError('Tool arguments contain unknown fields or omit required fields')
    for key, value in arguments.items():
        prop = schema['properties'][key]
        if prop['type'] == 'string':
            if (not isinstance(value, str) or not value.strip() or len(value) > prop['maxLength']
                    or ('pattern' in prop and re.fullmatch(prop['pattern'], value) is None)
                    or ('enum' in prop and value not in prop['enum'])):
                raise ValueError(f'Invalid {key}')
        elif prop['type'] == 'integer':
            if type(value) is not int or value < prop['minimum'] or value > prop.get('maximum',value):
                raise ValueError(f'Invalid {key}')
    return arguments


def _image_content(path, metadata):
    """Only manager-supplied internal paths can reach this function; no path tool argument exists."""
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_IMAGE:
        raise ValueError('Observation image is missing or exceeds the 8 MiB bound')
    with path.open('rb') as stream:
        data = stream.read(MAX_IMAGE + 1)
    if len(data) > MAX_IMAGE or not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Observation image is not a bounded PNG')
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as picture:
            if picture.format != 'PNG' or not 0 < picture.width * picture.height <= 8_388_608:
                raise ValueError('Invalid PNG dimensions')
            picture.verify()
    except Exception as error:
        raise ValueError('Observation image is not a valid PNG') from error
    expected = metadata.get('sha256')
    if expected is not None and expected != hashlib.sha256(data).hexdigest():
        raise ValueError('Observation image no longer matches its verified SHA-256')
    return dict(type='image', data=base64.b64encode(data).decode('ascii'), mimeType='image/png')


def _valid_id(value):
    return (value is None or type(value) in (str, int)
            or (type(value) is float and math.isfinite(value)))


def _reject_constant(_value):
    raise ValueError('Non-finite JSON constants are prohibited')


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError('JSON number exceeds finite range')
    return value


def handle(manager, request):
    ident = request.get('id') if isinstance(request, dict) else None
    if (not isinstance(request, dict) or request.get('jsonrpc') != '2.0'
            or not isinstance(request.get('method'), str) or not _valid_id(ident)):
        return _error(ident if _valid_id(ident) else None, -32600, 'Invalid JSON-RPC request')
    if 'id' not in request:
        return None
    ident, method = request['id'], request['method']
    params = request.get('params', {})
    if not isinstance(params, dict):
        return _error(ident, -32602, 'Parameters must be an object')
    if method == 'initialize':
        wanted = params.get('protocolVersion')
        return dict(jsonrpc='2.0', id=ident, result=dict(protocolVersion=wanted if wanted in PROTOCOLS else PROTOCOLS[0],
                    capabilities={'tools':{'listChanged':False}}, serverInfo={'name':'alien-observer','version':'1.0.0'}))
    if method == 'ping':
        return dict(jsonrpc='2.0', id=ident, result={})
    if method == 'tools/list':
        return dict(jsonrpc='2.0', id=ident, result={'tools':TOOLS})
    if method != 'tools/call':
        return _error(ident, -32601, 'Method not found')
    name = params.get('name')
    try:
        arguments = _validate(name, params.get('arguments', {}))
    except (ValueError, TypeError):
        return _error(ident, -32602, 'Unknown tool or invalid tool arguments')
    try:
        metadata = getattr(manager, METHODS[name])(**arguments)
        if not isinstance(metadata, dict):
            raise ValueError('Observation manager returned an invalid result')
        # Encode metadata before reading images, so no binary escapes into text.
        summary = json.dumps(metadata, ensure_ascii=False, allow_nan=False, sort_keys=True)
        content = [dict(type='text', text=summary)]
        if metadata.get('image_path') is not None:
            content.append(_image_content(metadata['image_path'], metadata))
        if metadata.get('detail_image_path') is not None:
            if not metadata.get('detail_sha256'):raise ValueError('Detail image requires a verified SHA-256')
            content.append(_image_content(metadata['detail_image_path'], {'sha256':metadata['detail_sha256']}))
        if sum(len(base64.b64decode(item['data'])) for item in content if item['type']=='image') > MAX_IMAGES_TOTAL:
            raise ValueError('Observation images exceed the 16 MiB aggregate bound')
        if name=='alien_observe_read' and metadata.get('packet_id') is not None:
            metadata = manager.commit_read(metadata)
            content[0]['text'] = json.dumps(metadata,ensure_ascii=False,allow_nan=False,sort_keys=True)
        failed = metadata.get('status') in ('error','unavailable','refused') or metadata.get('ok') is False
        result = dict(content=content, isError=failed)
    except Exception as error:
        result = dict(content=[dict(type='text', text=json.dumps(dict(status='error',reason=str(error),
                                                                   error_type=type(error).__name__)))], isError=True)
    return dict(jsonrpc='2.0', id=ident, result=result)


def serve(manager, stdin, stdout):
    """Serve bounded UTF-8 JSON lines until EOF; resources never outlive the connection."""
    def send(value):
        if value is not None:
            stdout.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')
            stdout.flush()
    try:
        while True:
            line = stdin.readline(MAX_LINE + 1)
            if not line:
                break
            byte_size = len(line.encode('utf-8')) if isinstance(line, str) else len(line)
            if byte_size > MAX_LINE:
                while line and not line.endswith('\n' if isinstance(line, str) else b'\n'):
                    line = stdin.readline(MAX_LINE + 1)
                send(_error(None, -32600, 'Request exceeds the 128 KiB limit'))
                continue
            try:
                request = json.loads(line, parse_constant=_reject_constant, parse_float=_finite_float)
            except (ValueError, UnicodeError, RecursionError):
                send(_error(None, -32700, 'Parse error'))
                continue
            send(handle(manager, request))
    finally:
        manager.shutdown()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observations', type=Path, default=DEFAULT_OBSERVATIONS)
    parser.add_argument('--endpoint-dir', type=Path)
    parser.add_argument('--observer-id', default='observer-agent', help='Existing owner history profile ID')
    parser.add_argument('--require-owner-connect', action='store_true',
                        default=os.environ.get('ALIEN_OBSERVER_REQUIRE_CONNECT', '').strip() in ('1', 'true', 'yes'),
                        help='Require a manual Connect click in the Observers window before opening a session')
    args = parser.parse_args(argv)
    # Save the real protocol destination before any Eye code can fork or print.
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), 'w', encoding='utf-8', buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr
    from alien_observation_session import ObservationManager
    manager = ObservationManager(observations_dir=args.observations, endpoint_dir=args.endpoint_dir,
                                 observer_id=args.observer_id, require_owner_connect=args.require_owner_connect)
    def stop(_signum, _frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        serve(manager, sys.stdin.buffer, protocol)
    finally:
        protocol.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
