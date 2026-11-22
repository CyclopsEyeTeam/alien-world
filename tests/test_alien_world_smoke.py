"""Automated unit and headless Electric Vision integration tests for Alien World."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / 'app'))
sys.path.insert(0, str(REPO_ROOT / 'observer_interface'))


class CoreAlienWorldUnitTests(unittest.TestCase):
    def test_fast_cells_matches_python_renderer_bit_for_bit(self):
        import aura_hive
        import fast_cells
        import fast_ripples

        ns = vars(aura_hive)
        PyCls = fast_ripples.renderer_class(ns)
        FastCls = fast_cells.renderer_class(ns)

        genome = aura_hive.Genome()
        params = dict(aura_hive.DEFAULT_PARAMS) if hasattr(aura_hive, 'DEFAULT_PARAMS') else {}
        py_r = PyCls(params, genome, True)
        fast_r = FastCls(params, genome, True)
        py_r.cols = fast_r.cols = 64
        py_r.rows = fast_r.rows = 24
        t = 12.345
        void = (8, 10, 16)
        py_r._prepare_field(64, 24, t)
        fast_r._prepare_field(64, 24, t)
        cells_py = py_r._build_cells(64, 24, t, void)
        cells_fast = fast_r._build_cells(64, 24, t, void)
        self.assertEqual(cells_fast, cells_py)

    def test_colour_recipes_and_background_pulse_bounds(self):
        import background_pulse
        import recipe_palette

        ring = recipe_palette.table_for(25.0, 0.42)
        self.assertGreaterEqual(len(ring), 384 * 3)
        rgb = recipe_palette.recipe_rgb(ring, 0.35, 0.85, 0.92)
        self.assertEqual(len(rgb), 3)
        bg = background_pulse.pulse((0.03, 0.03, 0.05), 48)
        self.assertEqual(len(bg), 3)
        for ch in bg:
            self.assertGreaterEqual(ch, 0.03)
            self.assertLessEqual(ch, 1.0)

    def test_named_observer_participants_and_drawing_measurement(self):
        import observer_participants as participants

        self.assertEqual(participants.participant('spark'), 'spark')
        with self.assertRaises(ValueError):
            participants.participant('owner')

        img = Image.new('RGBA', (32, 32), (8, 8, 12, 255))
        draw = ImageDraw.Draw(img)
        draw.ellipse((8, 8, 24, 24), fill=(0, 230, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        png_bytes = buf.getvalue()

        reading = participants.measure(png_bytes)
        self.assertEqual(reading['width'], 32)
        self.assertEqual(reading['height'], 32)
        self.assertGreater(reading['ink'], 0.05)
        line = participants.drawing_text('spark', 'cyan orb', reading)
        self.assertIn('drawing from spark: cyan orb', line)

    def test_mcp_protocol_initialize_tools_and_channel_register(self):
        import alien_mcp
        from alien_observation_session import ObservationManager

        tmp = Path(tempfile.mkdtemp(prefix='aw-mcp-test-'))
        os.chmod(tmp, 0o700)
        try:
            obs_dir = tmp / 'observations'
            ep_dir = tmp / 'endpoints'
            obs_dir.mkdir(mode=0o700)
            ep_dir.mkdir(mode=0o700)
            mgr = ObservationManager(observations_dir=obs_dir, endpoint_dir=ep_dir, require_owner_connect=False)
            try:
                init_resp = alien_mcp.handle(mgr, {
                    'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                    'params': {'protocolVersion': '2025-03-26'},
                })
                self.assertEqual(init_resp['result']['serverInfo']['name'], 'alien-observer')

                tools_resp = alien_mcp.handle(mgr, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}})
                tool_names = {t['name'] for t in tools_resp['result']['tools']}
                self.assertIn('alien_observe_open', tool_names)
                self.assertIn('alien_say', tool_names)

                reg_resp = alien_mcp.handle(mgr, {
                    'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                    'params': {
                        'name': 'alien_observer_register',
                        'arguments': {'name': 'claude', 'host_kind': 'mcp_wait'},
                    },
                })
                self.assertFalse(reg_resp['result']['isError'])
                body = json.loads(reg_resp['result']['content'][0]['text'])
                self.assertEqual(body['channel']['name'], 'claude')
            finally:
                mgr.shutdown()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class LiveHeadlessElectricEyeDemoTest(unittest.TestCase):
    """End-to-end test: launches Alien World and observes it via Electric Vision + MCP."""

    def test_launch_alien_world_and_observe_with_electric_eye_and_mcp(self):
        if not os.environ.get('DISPLAY'):
            self.skipTest('DISPLAY not set (run under xvfb-run or a desktop X11 session)')
        from _ev_bootstrap import find_electric_vision_root
        if find_electric_vision_root() is None:
            self.skipTest('Companion electric-vision repo not present')

        tmp = Path(tempfile.mkdtemp(prefix='aw-live-e2e-'))
        os.chmod(tmp, 0o700)
        data_dir = tmp / 'data'
        rt_dir = tmp / 'rt'
        data_dir.mkdir(mode=0o700)
        rt_dir.mkdir(mode=0o700)

        env = dict(os.environ)
        env['ALIEN_WORLD_DATA_DIR'] = str(data_dir)
        env['ALIEN_OBSERVATIONS_DIR'] = str(data_dir / 'observations')
        env['XDG_RUNTIME_DIR'] = str(rt_dir)
        env['GDK_BACKEND'] = 'x11'
        env.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')

        alien_pid = None
        try:
            # 1. Launch Alien World in background mode and wait for ready JSON
            launch = subprocess.run(
                [sys.executable, str(REPO_ROOT / 'bin' / 'alien-world'), '--background', '--wait-timeout', '20'],
                env=env, capture_output=True, text=True, timeout=25,
            )
            self.assertEqual(launch.returncode, 0, f'Launch failed: {launch.stdout}\n{launch.stderr}')
            ready_info = json.loads(launch.stdout.strip().splitlines()[-1])
            self.assertEqual(ready_info['status'], 'ready')
            alien_pid = int(ready_info['pid'])

            # 2. Observe live window via `./bin/observe-with-electric-eye` + send named unauthority greeting
            obs = subprocess.run(
                [
                    sys.executable, str(REPO_ROOT / 'bin' / 'observe-with-electric-eye'),
                    '--count', '2', '--interval', '0.6',
                    '--as', 'spark', '--say', 'hello from automated electric eye test',
                ],
                env=env, capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(obs.returncode, 0, f'Observe CLI failed: {obs.stdout}\n{obs.stderr}')
            obs_json = json.loads(obs.stdout)
            self.assertEqual(obs_json['status'], 'ok')
            self.assertEqual(obs_json['frames_observed'], 2)
            self.assertTrue(Path(obs_json['latest_image']).is_file())
            self.assertTrue(Path(obs_json['latest_shapes_overlay']).is_file())
            self.assertIsNotNone(obs_json['signal_temp_buffer'])
            self.assertTrue(obs_json['say_receipt']['ok'])
            self.assertEqual(obs_json['say_receipt']['result']['source'], 'observer:spark')
            self.assertEqual(obs_json['say_receipt']['result']['authority'], 'unauthority')

            # 3. Also verify the full stdio MCP server (`bin/alien-observer-mcp`) end-to-end!
            mcp_err_path = tmp / 'mcp-stderr.log'
            with mcp_err_path.open('w+') as mcp_err:
                mcp_proc = subprocess.Popen(
                    [str(REPO_ROOT / 'bin' / 'alien-observer-mcp')],
                    env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=mcp_err, text=True,
                )
                try:
                    def rpc(req_id, method, params=None):
                        mcp_proc.stdin.write(json.dumps({
                            'jsonrpc': '2.0', 'id': req_id, 'method': method, 'params': params or {},
                        }) + '\n')
                        mcp_proc.stdin.flush()
                        line = mcp_proc.stdout.readline()
                        if not line:
                            mcp_err.seek(0)
                            self.fail(f'MCP EOF on req {req_id}; rc={mcp_proc.poll()}; stderr={mcp_err.read()}')
                        return json.loads(line)

                    r_init = rpc(1, 'initialize', {'protocolVersion': '2025-03-26'})
                    self.assertEqual(r_init['result']['serverInfo']['name'], 'alien-observer')

                    r_reg = rpc(2, 'tools/call', {
                        'name': 'alien_observer_register',
                        'arguments': {'name': 'codex', 'host_kind': 'mcp_wait'},
                    })
                    self.assertFalse(r_reg['result']['isError'], r_reg)

                    r_open = rpc(3, 'tools/call', {'name': 'alien_observe_open', 'arguments': {}})
                    self.assertFalse(r_open['result']['isError'], r_open)
                    open_meta = json.loads(r_open['result']['content'][0]['text'])
                    img_block = r_open['result']['content'][1]
                    self.assertEqual(img_block['type'], 'image')
                    import base64
                    actual_sha = hashlib.sha256(base64.b64decode(img_block['data'])).hexdigest()
                    self.assertEqual(actual_sha, open_meta['sha256'])

                    r_conf = rpc(4, 'tools/call', {
                        'name': 'alien_observe_confirm',
                        'arguments': {
                            'session_id': open_meta['session_id'],
                            'receipt': open_meta['receipt'],
                            'sha256': actual_sha,
                        },
                    })
                    self.assertFalse(r_conf['result']['isError'], r_conf)

                    time.sleep(0.6)
                    r_read = rpc(5, 'tools/call', {
                        'name': 'alien_observe_read',
                        'arguments': {'session_id': open_meta['session_id']},
                    })
                    self.assertFalse(r_read['result']['isError'], r_read)

                    r_note = rpc(6, 'tools/call', {
                        'name': 'alien_observe_note',
                        'arguments': {
                            'session_id': open_meta['session_id'],
                            'description': 'Observed shimmering aurora ribbons and electric-glass underlight.',
                        },
                    })
                    self.assertFalse(r_note['result']['isError'], r_note)

                    r_say = rpc(7, 'tools/call', {
                        'name': 'alien_say',
                        'arguments': {
                            'session_id': open_meta['session_id'],
                            'text': 'greetings from mcp observer',
                            'request_id': 'a' * 32,
                        },
                    })
                    self.assertFalse(r_say['result']['isError'], r_say)
                    say_meta = json.loads(r_say['result']['content'][0]['text'])
                    self.assertEqual(say_meta['source'], 'observer:codex')
                    self.assertEqual(say_meta['authority'], 'unauthority')

                    r_close = rpc(8, 'tools/call', {
                        'name': 'alien_observe_close',
                        'arguments': {'session_id': open_meta['session_id']},
                    })
                    self.assertFalse(r_close['result']['isError'], r_close)
                finally:
                    for pipe in (mcp_proc.stdin, mcp_proc.stdout):
                        try:
                            if pipe:
                                pipe.close()
                        except Exception:
                            pass
                    try:
                        mcp_proc.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        mcp_proc.terminate()
                        mcp_proc.wait(timeout=5)
        finally:
            if alien_pid is not None:
                try:
                    os.kill(alien_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    try:
                        os.kill(alien_pid, 0)
                        time.sleep(0.1)
                    except ProcessLookupError:
                        break
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
