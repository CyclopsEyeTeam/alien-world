"""Read an explicitly bounded Alien field from existing application compositor storage.

No root/desktop pixel reads, window redirection, input, focusing or app control.
The caller confirms a crop relative to the exact client geometry. Window resize,
unmapping, identity mismatch or unavailable compositor storage fails closed.
Xlib/Pillow buffers are ordinary Python memory, not a secure erasure boundary.
"""
from pathlib import Path
import os
import time

from PIL import Image

from _ev_bootstrap import REPO_ROOT

MAX_PIXELS = 8 * 1024 * 1024


class CaptureUnavailable(RuntimeError):
    def __init__(self, code, message=None):
        self.code = code
        super().__init__(message or code.replace('_', ' '))


def _size(value):
    return (isinstance(value, (tuple, list)) and len(value) == 2
            and all(type(n) is int and n > 0 for n in value)
            and value[0] * value[1] <= MAX_PIXELS)


def validate_crop(actual_size, expected_size, crop):
    """An explicit crop belongs to one exact client size, never a guessed header."""
    if crop is None:
        raise CaptureUnavailable('crop_required', 'Confirm a field crop relative to the client window first')
    if not _size(actual_size) or not _size(expected_size):
        raise CaptureUnavailable('invalid_geometry')
    if tuple(actual_size) != tuple(expected_size):
        raise CaptureUnavailable('geometry_changed', 'Client resized; confirm the field crop again')
    if not isinstance(crop, (tuple, list)) or len(crop) != 4 or any(type(n) is not int for n in crop):
        raise CaptureUnavailable('invalid_crop')
    x, y, width, height = crop
    if x < 0 or y < 0 or width < 1 or height < 1 or x + width > actual_size[0] or y + height > actual_size[1]:
        raise CaptureUnavailable('invalid_crop')
    return x, y, width, height


def trusted_identity(*, title, wm_class, process_uid, argv, owner_uid):
    """Require Alien's native window and the owner's actual release-script command."""
    if title != 'Alien World' or tuple(wm_class or ()) != ('alien-world', 'AlienWorld') or process_uid != owner_uid:
        return False
    if not argv or not Path(argv[0]).name.startswith('python3'):
        return False
    script = None
    for item in argv[1:]:
        if item.startswith('-'):
            if item not in ('-B', '-u', '-E', '-I', '-s', '-S', '-O', '-OO', '-q', '-v', '-b', '-bb', '-d'):
                return False
            continue
        script = Path(item)
        break
    if script is None or not script.is_absolute():
        return False
    script = script.resolve()
    if script.name != 'live.py' or script.parent.name != 'app':
        return False
    direct_app = (REPO_ROOT / 'app' / 'live.py').resolve()
    releases_dir = (REPO_ROOT / 'releases').resolve()
    return script == direct_app or (len(script.parents) >= 3 and script.parents[2] == releases_dir)


def decode_rgb(data, width, height, stride, bits_per_pixel, byte_order, masks):
    """Decode supported TrueColor formats with their actual byte order and stride."""
    if not _size((width, height)) or bits_per_pixel not in (24, 32) or byte_order not in (0, 1):
        raise CaptureUnavailable('unsupported_pixel_format')
    if stride < width * (bits_per_pixel // 8) or len(data) != stride * height:
        raise CaptureUnavailable('invalid_pixel_buffer')
    modes = {
        (32, 0, (0xff0000, 0xff00, 0xff)): 'BGRX',
        (32, 1, (0xff0000, 0xff00, 0xff)): 'XRGB',
        (32, 0, (0xff, 0xff00, 0xff0000)): 'RGBX',
        (32, 1, (0xff, 0xff00, 0xff0000)): 'XBGR',
        (24, 0, (0xff0000, 0xff00, 0xff)): 'BGR',
        (24, 1, (0xff0000, 0xff00, 0xff)): 'RGB',
        (24, 0, (0xff, 0xff00, 0xff0000)): 'RGB',
        (24, 1, (0xff, 0xff00, 0xff0000)): 'BGR',
    }
    mode = modes.get((bits_per_pixel, byte_order, tuple(masks)))
    if mode is None:
        raise CaptureUnavailable('unsupported_pixel_masks')
    return Image.frombytes('RGB', (width, height), data, 'raw', mode, stride, 1)


def _window_size(window):
    from Xlib import X
    attributes = window.get_attributes()
    if attributes.map_state != X.IsViewable:
        raise CaptureUnavailable('window_unmapped')
    geometry = window.get_geometry()
    if geometry.border_width:
        raise CaptureUnavailable('unsupported_window_border')
    size = (geometry.width, geometry.height)
    if not _size(size):
        raise CaptureUnavailable('invalid_geometry')
    return size, attributes


def _ancestry(connection, client):
    """Mapped client and actual ancestors, excluding every screen's root window."""
    records = []
    current = client
    seen = set()
    for _ in range(16):
        tree = current.query_tree()
        if current.id == tree.root.id or current.id in seen:
            raise CaptureUnavailable('root_capture_prohibited')
        seen.add(current.id)
        size, attributes = _window_size(current)
        point = current.translate_coords(client, 0, 0)
        if not point.same_screen:
            raise CaptureUnavailable('ancestry_changed')
        records.append((current, size, attributes, point.x, point.y, tree.parent.id))
        if tree.parent.id == tree.root.id:
            return records
        current = tree.parent
    raise CaptureUnavailable('ancestry_too_deep')


def _ancestry_stamp(records):
    return [(window.id, size, attributes.visual, x, y, parent)
            for window, size, attributes, x, y, parent in records]


def _named_crop(connection, window, size, attributes, crop):
    """A missing independently redirected pixmap permits trying a real ancestor."""
    from Xlib import X, error
    visual = next((visual for depth in connection.screen().allowed_depths for visual in depth.visuals
                   if visual.visual_id == attributes.visual), None)
    if visual is None or visual.visual_class != X.TrueColor:
        raise CaptureUnavailable('unsupported_pixel_format')
    errors = []
    def handled(error_, request):
        errors.append(error_)
        return 1  # A false return also invokes Xlib's default stderr handler.
    pixmap = window.composite_name_window_pixmap(onerror=handled)
    try:
        connection.sync()
        if errors:
            if all(isinstance(item, error.BadMatch) for item in errors):
                return None
            raise CaptureUnavailable('compositor_storage_unavailable')
        geometry = pixmap.get_geometry()
        if (geometry.width, geometry.height) != size:
            raise CaptureUnavailable('geometry_changed')
        x, y, width, height = crop
        # The only pixel read targets this named ancestor pixmap and client crop.
        reply = pixmap.get_image(x, y, width, height, X.ZPixmap, 0xffffffff)
        format_ = next((fmt for fmt in connection.display.info.pixmap_formats if fmt.depth == reply.depth), None)
        if format_ is None or format_.scanline_pad not in (8, 16, 32):
            raise CaptureUnavailable('unsupported_pixel_format')
        stride = ((width * format_.bits_per_pixel + format_.scanline_pad - 1) // format_.scanline_pad) * (format_.scanline_pad // 8)
        return decode_rgb(reply.data, width, height, stride, format_.bits_per_pixel,
                          connection.display.info.image_byte_order, (visual.red_mask, visual.green_mask, visual.blue_mask))
    finally:
        # Failed NameWindowPixmap also allocated a local Xlib resource ID. Free it
        # with a handled server error; no unrelated protocol errors are silenced.
        pixmap.free(onerror=lambda *_: 1)
        connection.sync()


def _client_drawable_crop(connection, window, size, attributes, crop):
    """Fallback for uncomposited X11 / Xvfb servers where NameWindowPixmap returns BadMatch."""
    from Xlib import X
    visual = next((visual for depth in connection.screen().allowed_depths for visual in depth.visuals
                   if visual.visual_id == attributes.visual), None)
    if visual is None or visual.visual_class != X.TrueColor:
        raise CaptureUnavailable('unsupported_pixel_format')
    geometry = window.get_geometry()
    if (geometry.width, geometry.height) != size:
        raise CaptureUnavailable('geometry_changed')
    x, y, width, height = crop
    try:
        reply = window.get_image(x, y, width, height, X.ZPixmap, 0xffffffff)
    except Exception as error:
        raise CaptureUnavailable('compositor_storage_unavailable') from error
    format_ = next((fmt for fmt in connection.display.info.pixmap_formats if fmt.depth == reply.depth), None)
    if format_ is None or format_.scanline_pad not in (8, 16, 32):
        raise CaptureUnavailable('unsupported_pixel_format')
    stride = ((width * format_.bits_per_pixel + format_.scanline_pad - 1) // format_.scanline_pad) * (format_.scanline_pad // 8)
    return decode_rgb(reply.data, width, height, stride, format_.bits_per_pixel,
                      connection.display.info.image_byte_order, (visual.red_mask, visual.green_mask, visual.blue_mask))


def read_pixmap(connection, window, expected_size, crop):
    """Take one atomic, cropped application snapshot from existing X storage.

    Briefly serialize the X server while ancestry, translated coordinates and
    pixels are sampled, so another client cannot move/reparent the source through
    an ABA race. Always release before process checks, image output or analysis.
    No root pixmap, redirection, input or focus operation is used.
    """
    image, _method = read_pixmap_with_method(connection, window, expected_size, crop)
    return image


def read_pixmap_with_method(connection, window, expected_size, crop):
    try:
        connection.grab_server()
        connection.sync()
        return _read_pixmap_locked(connection, window, expected_size, crop)
    finally:
        connection.ungrab_server()
        connection.sync()


def _read_pixmap_locked(connection, window, expected_size, crop):
    """Read client crop while the caller holds the short X snapshot boundary."""
    before = _ancestry(connection, window)
    client_size = before[0][1]
    x, y, width, height = validate_crop(client_size, expected_size, crop)
    stamp = _ancestry_stamp(before)
    has_composite = connection.has_extension('Composite')
    if has_composite:
        version = connection.composite_query_version()
        has_composite = (version.major_version, version.minor_version) >= (0, 2)
    if has_composite:
        for candidate, size, attributes, offset_x, offset_y, _parent in before:
            try:
                validate_crop(size, size, (offset_x, offset_y, *client_size))
            except CaptureUnavailable as error:
                raise CaptureUnavailable('client_outside_ancestor') from error
            translated = (offset_x + x, offset_y + y, width, height)
            image = _named_crop(connection, candidate, size, attributes, translated)
            if image is None:
                continue
            try:
                if _ancestry_stamp(_ancestry(connection, window)) != stamp:
                    raise CaptureUnavailable('ancestry_changed')
                return image, 'xcomposite_named_window_pixmap'
            except Exception:
                image.close()
                raise
    # Uncomposited X11 / Xvfb fallback on the verified Alien client window itself (never root).
    client_window, c_size, c_attrs, _ox, _oy, _parent = before[0]
    image = _client_drawable_crop(connection, client_window, c_size, c_attrs, (x, y, width, height))
    try:
        if _ancestry_stamp(_ancestry(connection, window)) != stamp:
            raise CaptureUnavailable('ancestry_changed')
        return image, 'x11_client_window_drawable'
    except Exception:
        image.close()
        raise


def verified_window_pid(connection, window):
    """Bind the declared EWMH PID to the local client PID reported by X-Resource."""
    from Xlib import Xatom
    from Xlib.ext import res
    if not connection.has_extension('X-Resource'):
        raise CaptureUnavailable('server_pid_unavailable')
    version = connection.res_query_version()
    if (version.server_major, version.server_minor) < (1, 2):
        raise CaptureUnavailable('server_pid_unavailable')
    reply = connection.res_query_client_ids([dict(client=window.id, mask=res.LocalClientPIDMask)])
    pids = [int(item.value[0]) for item in reply.ids
            if item.spec.mask & res.LocalClientPIDMask and len(item.value) == 1]
    if len(pids) != 1 or pids[0] < 1:
        raise CaptureUnavailable('server_pid_unavailable')
    atom = connection.intern_atom('_NET_WM_PID', only_if_exists=True)
    declared = window.get_full_property(atom, Xatom.CARDINAL) if atom else None
    if declared is None or len(declared.value) != 1 or int(declared.value[0]) != pids[0]:
        raise CaptureUnavailable('identity_unverified')
    return pids[0]


def _identity(connection, window):
    from Xlib import Xatom
    atom = connection.intern_atom('_NET_WM_NAME', only_if_exists=True)
    title_property = window.get_full_property(atom, 0) if atom else None
    title = title_property.value.decode('utf-8', 'replace') if title_property is not None else window.get_wm_name()
    pid = verified_window_pid(connection, window)
    process = Path('/proc') / str(pid)
    process_uid = process.stat().st_uid
    with (process / 'cmdline').open('rb') as stream:
        command = stream.read(16385)
    if len(command) > 16384:
        raise CaptureUnavailable('identity_unverified')
    argv = [part.decode('utf-8', 'strict') for part in command.rstrip(b'\0').split(b'\0')]
    if not trusted_identity(title=title, wm_class=window.get_wm_class(), process_uid=process_uid,
                            argv=argv, owner_uid=os.getuid()):
        raise CaptureUnavailable('identity_unverified')
    if not (process / 'exe').resolve().name.startswith('python3'):
        raise CaptureUnavailable('identity_unverified')
    return pid


def discover_alien():
    """Return matching mapped native clients; no images, command text or state files."""
    from Xlib import display, Xatom, error
    connection = None
    try:
        connection = display.Display()
        root = connection.screen().root
        atom = connection.intern_atom('_NET_CLIENT_LIST', only_if_exists=True)
        listing = root.get_full_property(atom, Xatom.WINDOW) if atom else None
        if listing is not None:
            candidate_ids = [int(wid) for wid in list(listing.value)[:4096]]
        else:
            # Bare X11 / Xvfb without an EWMH window manager: inspect mapped top-level children.
            candidate_ids = [int(w.id) for w in root.query_tree().children[:4096]]
        found = []
        for window_id in candidate_ids:
            try:
                window = connection.create_resource_object('window', int(window_id))
                pid = _identity(connection, window)
                size, _ = _window_size(window)
                found.append(dict(window_id=int(window_id), pid=pid, width=size[0], height=size[1]))
            except (CaptureUnavailable, OSError, UnicodeError, error.XError):
                continue
        return found
    except Exception as error:
        raise CaptureUnavailable('display_unavailable') from error
    finally:
        if connection is not None:
            connection.close()


def process_starttime(stat_line, pid):
    """Linux process start ticks (field22), without confusing ')' inside comm."""
    if not stat_line.startswith(str(pid) + ' ('):
        raise CaptureUnavailable('process_lifetime_unavailable')
    try:
        _comm, fields = stat_line.rsplit(') ', 1)
        value = int(fields.split()[19])
        if value < 1:
            raise ValueError('invalid starttime')
        return value
    except (ValueError, IndexError) as error:
        raise CaptureUnavailable('process_lifetime_unavailable') from error


def _process_token(pid):
    with (Path('/proc') / str(pid) / 'stat').open() as stream:
        stat_line = stream.read(4097)
    if len(stat_line) > 4096:
        raise CaptureUnavailable('process_lifetime_unavailable')
    return pid, process_starttime(stat_line, pid)


def capture_alien(window_id, *, expected_size, crop):
    """Sample one confirmed field crop, with observation time but no inferred tick."""
    validate_crop(expected_size, expected_size, crop)
    if type(window_id) is not int or window_id < 1:
        raise CaptureUnavailable('invalid_window')
    from Xlib import display
    connection = None
    image = None
    started = time.monotonic_ns()
    try:
        connection = display.Display()
        window = connection.create_resource_object('window', window_id)
        pid = _identity(connection, window)
        process_token = _process_token(pid)
        image, capture_method = read_pixmap_with_method(connection, window, expected_size, crop)
        if _identity(connection, window) != pid or _process_token(pid) != process_token:
            raise CaptureUnavailable('identity_changed')
        return image, dict(source_scope='alien_field', window_id=window_id, pid=pid,
                           window_size=list(expected_size), crop=list(crop), capture_started_ns=started,
                           captured_ns=time.monotonic_ns(), capture_method=capture_method, native_tick=None)
    except CaptureUnavailable:
        if image is not None:
            image.close()
        raise
    except Exception as error:
        if image is not None:
            image.close()
        raise CaptureUnavailable('capture_unavailable') from error
    finally:
        if connection is not None:
            connection.close()
