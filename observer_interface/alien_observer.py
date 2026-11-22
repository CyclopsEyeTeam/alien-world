#!/usr/bin/env python3
"""On-demand Alien field pictures plus derived Electric Eye geometry; never hive input."""
from __future__ import annotations

import argparse
from collections import Counter, deque
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time

from PIL import Image, ImageChops, ImageDraw, ImageStat

from _ev_bootstrap import ensure_electric_vision, runtime_scratch_dir

ORIGIN = 'authorized_alien_field_trace'
SOURCE = 'src_alien_field'
FRAME = (512, 512)
ALLOWED_CAPTURE_METHODS = ('xcomposite_named_window_pixmap', 'x11_client_window_drawable')


def _rectangles(indices, width, height, background):
    finished, active = [], {}
    for y in range(height):
        row = indices[y * width:(y + 1) * width]
        next_row, x = {}, 0
        while x < width:
            colour, end = row[x], x
            while end + 1 < width and row[end + 1] == colour:
                end += 1
            if colour != background:
                key = (x, end, colour)
                rectangle = active.pop(key, [x, y, end, y, colour])
                rectangle[3] = y
                next_row[key] = rectangle
            x = end + 1
        finished.extend(active.values())
        active = next_row
    return finished + list(active.values())


def trace_picture(picture):
    """Bounded 16-colour reconstruction. Geometry refers to this trace, not original pixels."""
    if not isinstance(picture, Image.Image) or not (0 < picture.width * picture.height <= 8_388_608):
        raise ValueError('Unsupported field image size')
    image = picture.convert('RGB')
    scale = min(FRAME[0] / image.width, FRAME[1] / image.height)
    fitted = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    offset = ((FRAME[0] - fitted[0]) // 2, (FRAME[1] - fitted[1]) // 2)
    grid = 128
    while True:
        size = (max(1, round(fitted[0] * grid / max(fitted))), max(1, round(fitted[1] * grid / max(fitted))))
        reduced = image.resize(size, Image.Resampling.BOX).quantize(colors=16, method=Image.Quantize.MEDIANCUT,
                                                                  dither=Image.Dither.NONE)
        palette = reduced.getpalette()
        indices = list(reduced.get_flattened_data() if hasattr(reduced, 'get_flattened_data') else reduced.getdata())
        w, h = size
        edge = indices[:w] + indices[-w:] + [indices[y * w] for y in range(h)] + [indices[y * w + w - 1] for y in range(h)]
        background = Counter(edge).most_common(1)[0][0]
        rectangles = _rectangles(indices, w, h, background)
        if len(rectangles) <= 1024 or grid <= 8:
            break
        grid = max(8, int(grid * .75))
    rectangles.sort(key=lambda r: -(r[2] - r[0] + 1) * (r[3] - r[1] + 1))
    dropped = max(0, len(rectangles) - 1024)
    rectangles = rectangles[:1024]
    colour = lambda index: palette[index * 3:index * 3 + 3]
    reconstructed = Image.new('RGB', size, tuple(colour(background)))
    marks = []
    for n, (x0, y0, x1, y1, index) in enumerate(rectangles):
        reconstructed.paste(tuple(colour(index)), (x0, y0, x1 + 1, y1 + 1))
        marks.append(dict(mark_id=f'm{n}', shape='rect',
                          x0=offset[0] + x0 * fitted[0] // w, y0=offset[1] + y0 * fitted[1] // h,
                          x1=offset[0] + (x1 + 1) * fitted[0] // w - 1, y1=offset[1] + (y1 + 1) * fitted[1] // h - 1,
                          rgba=[*colour(index), 255]))
    difference = ImageChops.difference(image, reconstructed.resize(image.size, Image.Resampling.NEAREST))
    histograms = difference.split()
    close_mask = ImageChops.lighter(ImageChops.lighter(histograms[0], histograms[1]), histograms[2]).histogram()
    return dict(marks=marks, frame=FRAME, grid=size, colours=len(set(indices)), scale=scale, offset=offset,
                dropped=dropped, lossy=True, background=colour(background),
                fidelity=dict(close_fraction=sum(close_mask[:25]) / (image.width * image.height),
                              mean_absolute_error=sum(ImageStat.Stat(difference).mean) / 3))


def _atomic(path, payload):
    fd, temp = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def _json(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def _png(image):
    out = io.BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()


class FieldObserver:
    def __init__(self, eye, output_dir, *, keep=3):
        if type(keep) is not int or not 1 <= keep <= 8:
            raise ValueError('Keep between 1 and 8 field samples')
        self.eye, self.output_dir, self.keep = eye, Path(output_dir), keep
        self.output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if any(self.output_dir.iterdir()):
            raise ValueError('Use an empty dedicated observation directory')
        self.sequence, self.frames = 0, deque()
        self.previous = None
        self._signal_buffer = None
        self._signal_stream = None
        try:
            ensure_electric_vision()
            from signal_buffer import ElectricSignalTempBuffer
            self._signal_buffer = ElectricSignalTempBuffer(max_entries=8)
            self._signal_stream = self.eye.create_continuous_stream(
                'src_alien_sig', width=512, height=512, max_window_frames=8
            )
        except Exception:
            self._signal_buffer = None
            self._signal_stream = None

    def observe(self, picture, capture):
        if self.sequence >= 32:
            raise ValueError('Observation burst is limited to 32 samples; close this Eye session before another burst')
        if not isinstance(picture, Image.Image) or not 0 < picture.width * picture.height <= 8_388_608:
            raise ValueError('Unsupported field image size')
        now = time.monotonic_ns()
        stamp, start = capture.get('captured_ns'), capture.get('capture_started_ns')
        crop, size = capture.get('crop'), capture.get('window_size')
        if (type(stamp) is not int or type(start) is not int or not 0 <= start <= stamp <= now
                or now - start > 2_500_000_000 or capture.get('source_scope') != 'alien_field'
                or capture.get('capture_method') not in ALLOWED_CAPTURE_METHODS
                or not isinstance(crop, (list, tuple)) or len(crop) != 4
                or not isinstance(size, (list, tuple)) or len(size) != 2
                or any(type(v) is not int for v in [*crop, *size])
                or min(*size, crop[2], crop[3]) <= 0 or min(crop[:2]) < 0
                or crop[0] + crop[2] > size[0] or crop[1] + crop[3] > size[1]
                or tuple(crop[2:]) != picture.size):
            raise ValueError('Field sample has invalid geometry, scope or freshness')
        self.sequence += 1
        raw = _png(picture)
        digest = hashlib.sha256(raw).hexdigest()
        previous = self.previous
        same_geometry = previous is not None and all(previous['capture'].get(k) == capture.get(k)
                                                     for k in ('window_id', 'pid', 'window_size', 'crop'))
        reused = bool(same_geometry and previous['source_png_sha256'] == digest)
        trace_change = None
        pixel_change = None
        if same_geometry:
            delta = ImageChops.difference(picture.convert('RGB'), previous['_picture'])
            channels = delta.split()
            histogram = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2]).histogram()
            changed = picture.width * picture.height - histogram[0]
            pixel_change = dict(scope='captured_field_rgb', changed_pixels=changed, fraction=changed / (picture.width * picture.height))
        version = previous['_version'] if reused else f'v{self.sequence}'
        if reused:
            trace_info, inspection = previous['_trace'], previous['_inspection']
            trace_change = dict(scope='simplified_trace', changed_pixels=0)
        else:
            trace_info = trace_picture(picture)
            self.eye.register_synthetic_canvas(SOURCE, version, trace_info['marks'], width=512, height=512,
                                               source_kind='canvas_state', origin_attestation=ORIGIN)
            inspection = self.eye.inspect_canvas(SOURCE, version)
            if same_geometry:
                diff = self.eye.compare_canvases((SOURCE, previous['_version']), (SOURCE, version))
                trace_change = dict(scope='simplified_trace', **diff['native_diff_metrics'])
            if previous:
                self.eye.evict_synthetic_canvas(SOURCE, previous['_version'])
        boxes = []
        components = inspection['native_simd_metrics']['op_connected_components_4c']
        scale, (ox, oy) = trace_info['scale'], trace_info['offset']
        # The existing native component operator can truncate foreground runs.
        # A sum of rectangle heights bounds those runs without trusting truncated boxes.
        run_bound = sum(m['y1'] - m['y0'] + 1 for m in trace_info['marks'])
        uncertain_runs = run_bound > max(1024, FRAME[1] * 8)
        shapes_complete = not uncertain_runs and components['component_count'] <= len(components['components'])
        shapes_warning = ('foreground_run_budget_may_truncate' if uncertain_runs else
                          'component_list_is_partial' if not shapes_complete else None)
        for component in ([] if uncertain_runs else components['components']):
            box = component['bbox']
            boxes.append([max(0, round((box['x_min'] - ox) / scale)), max(0, round((box['y_min'] - oy) / scale)),
                          min(picture.width - 1, round((box['x_max'] + 1 - ox) / scale) - 1),
                          min(picture.height - 1, round((box['y_max'] + 1 - oy) / scale) - 1)])
        name = f'frame-{self.sequence:06}'
        report = dict(status='ok', sequence=self.sequence, origin=ORIGIN, observed=False, native_tick=None,
                      measurement_state='derived', measurement_reused=reused, capture=capture,
                      source_png_sha256=digest, trace={k:trace_info[k] for k in ('frame', 'grid', 'colours', 'dropped', 'lossy', 'fidelity', 'background')},
                      shapes=boxes, shapes_complete=shapes_complete, shapes_warning=shapes_warning,
                      trace_change=trace_change, pixel_change=pixel_change, sampled_motion_not_continuous=True,
                      measurement_age_ms=(time.monotonic_ns() - stamp) / 1_000_000,
                      image=str(self.output_dir / (name + '.png')),
                      shapes_image=str(self.output_dir / (name + '-shapes.png')),
                      report=str(self.output_dir / (name + '.json')))
        report['trace'].update(fidelity_scope='palette_reconstruction_with_background',
                               eye_scope='background_excluded_geometry_and_colour')
        if self._signal_buffer is not None and self._signal_stream is not None:
            try:
                entry = self._signal_buffer.get('alien_field', str(capture.get('window_id')))
                same_raw = bool(entry is not None and entry.raw_sha256 == digest and entry.size == picture.size)
                obs = self._signal_buffer.observe_frame(
                    target_id='alien_field',
                    xid=str(capture.get('window_id')),
                    title='Alien World',
                    stream=self._signal_stream,
                    tick=self.sequence,
                    img=None if same_raw else picture.convert('RGB').copy(),
                    raw_sha256=digest,
                    size=picture.size,
                )
                report['signal_buffer'] = {
                    'words': obs['words'],
                    'move': obs['move'],
                    'measures': obs['measures'],
                    'receipt': obs['receipt'],
                    'buffered': obs['buffered'],
                    'stats': self._signal_buffer.stats(),
                }
            except Exception:
                pass
        overlay = picture.convert('RGB').copy()
        draw = ImageDraw.Draw(overlay)
        for box in boxes:
            if box[2] >= box[0] and box[3] >= box[1]:draw.rectangle(box, outline='#00ffff', width=1)
        _atomic(Path(report['image']), raw)
        _atomic(Path(report['shapes_image']), _png(overlay))
        _atomic(Path(report['report']), _json(report))
        self.frames.append(report)
        expired = self.frames.popleft() if len(self.frames) > self.keep else None
        _atomic(self.output_dir / 'latest.json', _json(dict(schema='ALIEN_FIELD_OBSERVER_V1', frames=list(self.frames))))
        if expired:
            for k in ('image', 'shapes_image', 'report'):Path(expired[k]).unlink(missing_ok=True)
        self.previous = dict(report, _version=version, _trace=trace_info, _inspection=inspection, _picture=picture.convert('RGB').copy())
        if previous:previous['_picture'].close()
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('discover', 'observe'))
    parser.add_argument('--window', type=lambda s:int(s, 0))
    parser.add_argument('--size', type=int, nargs=2, metavar=('WIDTH', 'HEIGHT'))
    parser.add_argument('--crop', type=int, nargs=4, metavar=('X', 'Y', 'WIDTH', 'HEIGHT'))
    parser.add_argument('--count', type=int, default=3)
    parser.add_argument('--interval', type=float, default=2.)
    parser.add_argument('--keep', type=int, default=3)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    from x11_alien_capture import discover_alien, capture_alien, CaptureUnavailable
    try:
        if args.command == 'discover':
            print(json.dumps(dict(windows=discover_alien(), capture_performed=False)))
            return 0
        if args.window is None or args.size is None or args.crop is None:
            parser.error('observe needs --window, --size and an explicitly verified --crop; no guessed crop')
        if not 1 <= args.count <= 32 or not 2 <= args.interval <= 60 or not 1 <= args.keep <= 8:
            parser.error('count 1..32, interval 2..60 seconds, keep 1..8')
        scratch = runtime_scratch_dir()
        output = args.output or Path(tempfile.mkdtemp(prefix='alien-observations-', dir=scratch))
        ensure_electric_vision()
        from electric_vision_agent_bridge import ElectricVisionAgentSession
        with tempfile.TemporaryDirectory(prefix='ae-', dir=scratch) as sockets:
            with ElectricVisionAgentSession(run_dir=sockets, allow_alien_field=True) as eye:
                observer = FieldObserver(eye, output, keep=args.keep)
                for i in range(args.count):
                    if i:time.sleep(args.interval)
                    image, meta = capture_alien(args.window, expected_size=tuple(args.size), crop=tuple(args.crop))
                    print(json.dumps(observer.observe(image, meta)), flush=True)
        return 0
    except (CaptureUnavailable, ValueError, RuntimeError, OSError) as error:
        print(json.dumps(dict(status='unavailable', code=getattr(error, 'code', 'observer_failed'), reason=str(error))), flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
