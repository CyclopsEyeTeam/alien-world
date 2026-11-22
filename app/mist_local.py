"""A request-owned local NanoFable process for one Mist completion.

Mist runs only on the owner's local NanoFable model. Each request starts one
Node child that reads the hash-verified NanoFable checkpoint and runtime, writes
one reply and exits. No socket, SSH connection or HTTP listener is involved, and
no other model is ever selected. This module runs in the single-threaded API
helper, where the child is also contained with Linux's parent-death signal.
"""
import ctypes
import functools
import hashlib
import json
import os
import signal
import subprocess
from pathlib import Path

NANOFABLE_ROOT = Path(os.environ['ALIEN_NANOFABLE_ROOT']) if os.environ.get('ALIEN_NANOFABLE_ROOT') else None
SCRIPT = Path(__file__).with_name('mist_nanofable.mjs')
# Files the Mist child loads, checked against NanoFable's own manifest.
VERIFIED = ('checkpoint/architecture.json', 'checkpoint/model.safetensors',
            'runtime/js/model.mjs', 'runtime/js/runtime.mjs',
            'runtime/js/tokenizer.mjs', 'runtime/original/tokenizer.json')
TIMEOUT = 115


def _verified_root(root):
    root = Path(root)
    expected = {}
    for line in (root / 'MANIFEST.sha256').read_text(encoding='ascii').splitlines():
        digest, _, name = line.strip().partition('  ')
        if digest and name:
            expected[name] = digest
    for name in VERIFIED:
        path = root / name
        if path.is_symlink() or name not in expected:
            raise OSError('NanoFable file is not in its manifest')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected[name]:
            raise OSError('NanoFable file does not match its manifest')
    return root, expected['checkpoint/model.safetensors']


def _contain(parent):
    """Executed only after fork in the single-threaded API helper's child."""
    if ctypes.CDLL(None).prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        os._exit(125)
    if parent == 1 or os.getppid() != parent:
        os._exit(125)


def _reap(child):
    if child.poll() is None:
        try:
            child.terminate()
        except ProcessLookupError:
            pass
    try:
        child.wait(timeout=.3)
    except subprocess.TimeoutExpired:
        try:
            child.kill()
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=.2)
        except subprocess.TimeoutExpired:
            raise OSError('Local Mist worker could not be reaped') from None


def nanofable_complete(config, body, node=None, root=None):
    """Return the child's raw reply bytes; never fall back to another model."""
    if config.provider != 'mist':
        raise ValueError('Only Mist uses the local NanoFable entrance')
    node = node or os.environ.get('ALIEN_MIST_NODE', '')
    if not node or not os.path.isabs(node):
        raise OSError('Node is unavailable for local Mist')
    chosen_root = NANOFABLE_ROOT if root is None else root
    if chosen_root is None:
        raise OSError('Local NanoFable Mist model path is not configured (set ALIEN_NANOFABLE_ROOT)')
    root, weights = _verified_root(chosen_root)
    payload = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode()
    child = subprocess.Popen([node, '--max-old-space-size=96', str(SCRIPT), str(root), weights],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, close_fds=True,
                             env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'},
                             preexec_fn=functools.partial(_contain, os.getpid()))
    try:
        raw, _ = child.communicate(payload, timeout=TIMEOUT)
        if child.returncode != 0:
            raise OSError('Local NanoFable Mist failed')
        return raw
    finally:
        _reap(child)
