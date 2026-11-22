"""On-demand entrance to the release's owner Observers window.

The component owns its per-history Gtk.Application activation. It is never
imported into Alien's GUI or native hive, and stays in the existing app scope.
"""
import os
from pathlib import Path
import subprocess
import sys

_DESKTOP_ENV=('HOME','USER','LOGNAME','DISPLAY','WAYLAND_DISPLAY','XAUTHORITY',
              'DBUS_SESSION_BUS_ADDRESS','XDG_RUNTIME_DIR','XDG_CONFIG_HOME',
              'XDG_DATA_HOME','XDG_CACHE_HOME','LANG','LC_ALL','LC_CTYPE',
              'DESKTOP_STARTUP_ID','ALIEN_WORLD_ROOT','ALIEN_OBSERVATIONS_DIR',
              'ELECTRIC_VISION_ROOT')
_UNAVAILABLE='Observers unavailable; the interface component could not be opened. Alien continues running.'


class ObserverInterface:
    def __init__(self,bundle=None):
        self.bundle=Path(bundle) if bundle is not None else Path(__file__).resolve().parent.parent/'observer_interface'/'alien_observers.py'
        self._children=[]

    def check(self):
        """Reap completed requests without waiting; zero is normal activation/close."""
        active=[];error=None
        for child in self._children:
            code=child.poll()
            if code is None:active.append(child)
            elif code!=0:error=_UNAVAILABLE
        self._children=active
        return bool(active),error

    def open(self):
        """Launch or activate the same owner window; return a safe owner notice."""
        self.check()
        # One GUI owner plus one short activation request is sufficient, even
        # when the owner clicks repeatedly while the component is starting.
        if len(self._children)>=2:return None
        try:
            if not self.bundle.is_file():return _UNAVAILABLE
            env={name:os.environ[name] for name in _DESKTOP_ENV if name in os.environ}
            env.update(PATH=os.environ.get('PATH','/usr/bin:/bin'),PYTHONDONTWRITEBYTECODE='1')
            child=subprocess.Popen([sys.executable or '/usr/bin/python3','-B',str(self.bundle)],
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                close_fds=True,shell=False,env=env)
        except (OSError,ValueError,subprocess.SubprocessError):return _UNAVAILABLE
        self._children.append(child)
        return None
