"""A passive local NanoFable entrance, used when Alien supplies runtime speech.

The adopted recorder system voice is preserved exactly. The template carries
no user utterance and cannot itself generate a model request. Its logical
loopback URL only identifies the local NanoFable source; no listener is
contacted, because mist_local runs the model in a request-owned child.
"""
from pathlib import Path

from api_config import Config, PRESETS

LOCAL_MIST_TOKEN = 'local-nanofable-mist-no-credential'
LOCAL_MODEL = 'nanofable'
MIST_SYSTEM = Path(__file__).with_name('mist_system.txt').read_bytes().decode('utf-8')


def mist_config(environ=None):
    """Mist always uses the owner's local NanoFable model.

    The environment cannot select another listener, model or cloud
    destination, and never triggers a cloud-key lookup.
    """
    return Config(provider='mist', endpoint=PRESETS['mist'],
                  model=LOCAL_MODEL, prompt=MIST_SYSTEM, allow_local_http=True,
                  token_field='max_tokens', utterance='').validate()


def validate_mist_config(config):
    """Keep the adopted voice and the single local NanoFable source."""
    if (config.url() != PRESETS['mist'] or not config.allow_local_http or
            config.model != LOCAL_MODEL or config.prompt != MIST_SYSTEM):
        raise ValueError('mist requires local NanoFable and the preserved recorder system')
