"""Portable path resolution and Electric Vision companion discovery for Alien World."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

REPO_ROOT = Path(os.environ.get('ALIEN_WORLD_ROOT') or Path(__file__).resolve().parent.parent).resolve()
DATA_ROOT = Path(os.environ.get('ALIEN_WORLD_DATA_DIR') or (REPO_ROOT / 'data')).resolve()
DEFAULT_OBSERVATIONS = Path(os.environ.get('ALIEN_OBSERVATIONS_DIR') or (DATA_ROOT / 'observations')).resolve()


def runtime_scratch_dir() -> Path:
    """Return a short-path owner runtime directory suitable for AF_UNIX sockets."""
    candidates = [
        os.environ.get('ALIEN_OBSERVER_RUNTIME_DIR'),
        os.environ.get('XDG_RUNTIME_DIR'),
        tempfile.gettempdir(),
    ]
    for item in candidates:
        if item:
            p = Path(item)
            if p.is_dir() and os.access(p, os.W_OK | os.X_OK):
                return p
    return Path(tempfile.gettempdir())


def find_electric_vision_root() -> Path | None:
    """Locate a local checkout of https://github.com/CyclopsEyeTeam/electric-vision."""
    candidates: list[Path] = []
    env_root = os.environ.get('ELECTRIC_VISION_ROOT')
    if env_root:
        candidates.append(Path(env_root).expanduser())
    candidates.extend([
        REPO_ROOT.parent / 'electric-vision',
        REPO_ROOT.parent / 'ElectricVision',
        REPO_ROOT / 'electric-vision',
        REPO_ROOT / 'vendor' / 'electric-vision',
        Path.home() / 'electric-vision',
        Path.home() / 'ElectricVision',
        Path.home() / 'Documents' / 'electric-vision',
        Path.home() / 'Documents' / 'ElectricVision',
    ])
    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / 'electric_vision_agent_bridge.py').is_file():
            return resolved
    return None


def ensure_electric_vision() -> Path | None:
    """Ensure Electric Vision modules are importable on sys.path."""
    root = find_electric_vision_root()
    if root is not None:
        root_str = str(root)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
        return root
    try:
        import electric_vision_agent_bridge as _bridge
        return Path(_bridge.__file__).resolve().parent
    except ImportError as exc:
        raise ImportError(
            'Electric Vision companion repo not found. '
            'Clone https://github.com/CyclopsEyeTeam/electric-vision alongside alien-world '
            '(../electric-vision) or set ELECTRIC_VISION_ROOT=/path/to/electric-vision.'
        ) from exc
