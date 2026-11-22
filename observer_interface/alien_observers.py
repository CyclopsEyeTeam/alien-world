#!/usr/bin/env python3
"""AlienWorld-owned native owner interface for named observer history.

Reads the public Sight journal and requests a wake through installed channels.
It has no field capture, confirmation, words, provider, or Alien process control.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
import struct
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango

from _ev_bootstrap import DEFAULT_OBSERVATIONS
from observer_history import ObserverJournal
from observer_channels import ChannelRegistry
from observer_view_model import event_time, frame_fingerprint, profile_status, read_frame_image, timeline_rows, visit_status


def label(text='', *, css=None, wrap=True):
    widget = Gtk.Label(label=text, xalign=0)
    widget.set_use_markup(False)
    widget.set_line_wrap(wrap)
    widget.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    widget.set_selectable(False)
    if css:
        widget.get_style_context().add_class(css)
    return widget


def box(*, spacing=10, margin=0):
    widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
    widget.set_border_width(margin)
    return widget


def scroll(child, *, width=-1, height=-1):
    widget = Gtk.ScrolledWindow()
    widget.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    widget.set_size_request(width, height)
    widget.add(child)
    return widget


class ObserversWindow(Gtk.Window):
    def __init__(self, journal, *, registry=None, poll=True):
        super().__init__(title='Alien Observers')
        self.journal = journal
        self.registry = registry if registry is not None else ChannelRegistry(journal)
        self.set_default_size(1180, 790)
        self.set_size_request(940, 620)
        self._updating = False
        self._closed = False
        self._history_available = False
        self._timer = None
        self._selected_profile = None
        self._selected_channel = None
        self._selected_choice = None
        self._channels = []
        self._channel_requests = {}
        self._connect_errors = {}
        self._dispatching = set()
        self._selected_visit = None
        self._events_key = None
        self._profiles_key = None
        self._visits_key = None
        self._visits = []
        self._profiles = []
        self._pixbuf = None
        self._image_item = None
        self._selected_item = None
        self._image_cache_key = None
        self._image_verified_label = ''
        self._install_style()
        header = Gtk.HeaderBar(title='Alien Observers', subtitle='Installed agents, visual accounts and words')
        header.set_show_close_button(True)
        self.set_titlebar(header)
        layout = box(spacing=14, margin=18)
        self.add(layout)
        layout.pack_start(label('Observers', css='page-title'), False, False, 0)
        layout.pack_start(label('Select an installed agent and Connect. Explore its visual account and the words Alien received.', css='muted'), False, False, 0)
        panes = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        panes.set_position(258)
        layout.pack_start(panes, True, True, 0)
        sidebar = box(spacing=12)
        sidebar.set_size_request(230, -1)
        sidebar.get_style_context().add_class('sidebar')
        panes.pack1(sidebar, False, False)
        profile_heading = Gtk.Box(spacing=8)
        profile_heading.pack_start(label('Installed agents', css='section-title'), True, True, 0)
        setup = Gtk.Button.new_with_label('Agent setup')
        setup.connect('clicked', self._setup_dialog)
        profile_heading.pack_end(setup, False, False, 0)
        sidebar.pack_start(profile_heading, False, False, 0)
        self.profile_list = Gtk.ListBox()
        self.profile_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.profile_list.connect('row-selected', self._profile_selected)
        sidebar.pack_start(scroll(self.profile_list, height=160), False, True, 0)
        self.connect_button = Gtk.Button.new_with_label('Connect')
        self.connect_button.set_sensitive(False)
        self.connect_button.connect('clicked', self._connect_selected)
        sidebar.pack_start(self.connect_button, False, False, 0)
        self.connect_state = label('No installed agent selected.', css='muted')
        sidebar.pack_start(self.connect_state, False, False, 0)
        sidebar.pack_start(Gtk.Separator(), False, False, 0)
        sidebar.pack_start(label('Recent visits', css='section-title'), False, False, 0)
        self.visits_list = Gtk.ListBox()
        self.visits_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.visits_list.connect('row-selected', self._visit_selected)
        sidebar.pack_start(scroll(self.visits_list), True, True, 0)
        self.visits_empty = label('No recorded visits for this observer.', css='muted')
        self.visits_empty.set_no_show_all(True)
        sidebar.pack_start(self.visits_empty, False, False, 0)
        content = box(spacing=10, margin=12)
        panes.pack2(content, True, False)
        self.visit_title = label('Select a visit', css='section-title')
        self.visit_state = label('', css='muted')
        self.visit_context = label('', css='muted')
        content.pack_start(self.visit_title, False, False, 0)
        content.pack_start(self.visit_state, False, False, 0)
        content.pack_start(self.visit_context, False, False, 0)
        split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        split.set_position(390)
        content.pack_start(split, True, True, 0)
        timeline_panel = box(spacing=8)
        timeline_panel.pack_start(label('Overall account & words', css='section-title'), False, False, 0)
        self.snapshots_toggle = Gtk.CheckButton.new_with_label('Pictures & optional notes')
        self.snapshots_toggle.connect('toggled', self._snapshots_changed)
        timeline_panel.pack_start(self.snapshots_toggle, False, False, 0)
        self.timeline_list = Gtk.ListBox()
        self.timeline_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.timeline_list.connect('row-selected', self._timeline_selected)
        timeline_panel.pack_start(scroll(self.timeline_list, width=260), True, True, 0)
        self.timeline_empty = label('No overall account or words recorded. Pictures shows visual intervals and optional individual notes.', css='muted')
        self.timeline_empty.set_no_show_all(True)
        timeline_panel.pack_start(self.timeline_empty, False, False, 0)
        split.pack1(timeline_panel, True, False)
        detail_panel = box(spacing=10, margin=10)
        split.pack2(detail_panel, True, False)
        detail_panel.pack_start(label('Selected image', css='section-title'), False, False, 0)
        self.picture = Gtk.Image()
        self.picture.set_size_request(280, 220)
        image_frame = Gtk.Frame()
        image_frame.add(self.picture)
        detail_panel.pack_start(image_frame, False, True, 0)
        self.image_status = label('Select a captured image or visual description.', css='muted')
        detail_panel.pack_start(self.image_status, False, False, 0)
        self.detail_image_toggle = Gtk.CheckButton.new_with_label('Show full-detail original')
        self.detail_image_toggle.set_no_show_all(True)
        self.detail_image_toggle.connect('toggled', self._detail_image_changed)
        detail_panel.pack_start(self.detail_image_toggle, False, False, 0)
        self.detail_title = label('Details', css='section-title')
        detail_panel.pack_start(self.detail_title, False, False, 0)
        detail = Gtk.TextView()
        detail.set_editable(False)
        detail.set_cursor_visible(False)
        detail.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        detail.set_left_margin(8)
        detail.set_right_margin(8)
        detail.set_top_margin(8)
        detail.set_bottom_margin(8)
        self.detail_buffer = detail.get_buffer()
        detail_panel.pack_start(scroll(detail, height=180), True, True, 0)
        self.error_label = label('', css='muted')
        layout.pack_start(self.error_label, False, False, 0)
        layout.pack_start(label('Descriptions are agent interpretations. Received means received or queued by Alien; it does not mean learned.', css='muted'), False, False, 0)
        self.connect('destroy', self._destroyed)
        self._refresh()
        if poll:
            self._timer = GLib.timeout_add_seconds(1, self._refresh)

    def _install_style(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(b'.page-title { font-size: 24px; font-weight: bold; }\n'
                                b'.section-title { font-weight: bold; font-size: 14px; }\n'
                                b'.muted { opacity: 0.72; font-size: 12px; }\n'
                                b'list row { padding: 10px 8px; }\n')
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _destroyed(self, *_):
        self._closed = True
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _refresh(self):
        if self._closed:
            return False
        try:
            self._channels = self.registry.list_installed()
            self._profiles = self.journal.list_profiles()
            for channel in self._channels:
                request = self.registry.pending(channel['id'])
                if request is not None:
                    self._channel_requests[channel['id']] = request
                elif channel['id'] in self._channel_requests:
                    self._channel_requests[channel['id']] = self.registry.get(self._channel_requests[channel['id']]['id'])
            self._visits = self.journal.recent_visits(limit=50)
            self._history_available = True
            self._render_profiles()
            self._render_visits()
            self._render_current()
            self._render_connect_controls()
            self.error_label.set_text('')
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
            self._history_available = False
            self.error_label.set_text(f'History unavailable: {error}')
            self._updating = False
            self.visit_state.set_text('Unavailable · history could not be refreshed')
            self.connect_button.set_sensitive(False)
            self.connect_state.set_text('Unavailable · installed agents or history could not be refreshed')
            for row in self.profile_list.get_children() + self.visits_list.get_children():
                row.status_label.set_text('Unavailable · history could not be refreshed')
            if self.picture.get_pixbuf() is not None:
                self.image_status.set_text('Historical image · current history unavailable')
        return True

    @staticmethod
    def _clear(widget):
        for child in widget.get_children():
            widget.remove(child)

    def _render_profiles(self):
        registered = {channel['observer_id'] for channel in self._channels}
        choices = [dict(choice_id=channel['id'], channel_id=channel['id'],
                        profile_id=channel['observer_id'], name=channel['name']) for channel in self._channels]
        choices.extend(dict(choice_id='history:' + profile['id'], channel_id=None,
                            profile_id=profile['id'], name='History · ' + profile['name'])
                       for profile in self._profiles if profile['id'] not in registered)
        key = json.dumps(choices, sort_keys=True)
        if key != self._profiles_key:
            self._updating = True
            self._clear(self.profile_list)
            for choice in choices:
                row = Gtk.ListBoxRow()
                row.profile_id = choice['profile_id']
                row.channel_id = choice['channel_id']
                row.choice_id = choice['choice_id']
                content = box(spacing=5)
                content.pack_start(label(choice['name'], css='section-title'), False, False, 0)
                row.status_label = label('', css='muted')
                content.pack_start(row.status_label, False, False, 0)
                row.add(content)
                self.profile_list.add(row)
            children = self.profile_list.get_children()
            chosen = next((row for row in children if row.choice_id == self._selected_choice), children[0] if children else None)
            if chosen:
                self.profile_list.select_row(chosen)
                self._selected_profile = chosen.profile_id
                self._selected_channel = chosen.channel_id
                self._selected_choice = chosen.choice_id
            else:
                self._selected_profile = self._selected_channel = self._selected_choice = None
            self._profiles_key = key
            self._updating = False
            self.profile_list.show_all()
        channels = {channel['id']: channel for channel in self._channels}
        for row in self.profile_list.get_children():
            row.status_label.set_text(self._channel_status(channels[row.channel_id]) if row.channel_id
                                      else 'Earlier history · connection unavailable')

    def _channel_status(self, channel):
        visits = [visit for visit in self._visits if visit.get('observer_id') == channel['observer_id']]
        state = profile_status(dict(id=channel['observer_id'], kind='mcp'), visits)
        if state['connected']:
            return state['label']
        if channel['id'] in self._connect_errors:
            return 'Host unavailable · ' + self._connect_errors[channel['id']] + ' · clock off'
        request = self._channel_requests.get(channel['id'])
        if request:
            phase = request.get('state')
            if phase == 'failed':
                return 'Host unavailable · ' + str(request.get('error') or 'wake failed') + ' · clock off'
            if phase == 'pending':
                return 'Waiting for agent · clock off'
            if phase == 'notified':
                return 'Wake queued · waiting for agent · clock off'
            if phase == 'claimed':
                return 'Agent responding · awaiting image acknowledgement · clock off'
            if phase == 'expired':
                return 'Connect request expired · clock off'
            if phase == 'cancelled':
                return 'Connect request cancelled · clock off'
        if channel['id'] in self._dispatching:
            return 'Requesting agent · clock off'
        if visits and visits[0].get('phase') == 'awaiting_acknowledgement':
            return 'Awaiting image acknowledgement · clock off'
        return 'Installed · not connected'

    def _render_connect_controls(self):
        channel = next((channel for channel in self._channels if channel['id'] == self._selected_channel), None)
        self.connect_button.set_sensitive(bool(channel) and self._history_available
                                          and channel['id'] not in self._dispatching
                                          and self._channel_requests.get(channel['id'], {}).get('state')
                                          not in ('pending', 'notified', 'claimed'))
        self.connect_state.set_text(self._channel_status(channel) if channel else
                                    'History only. Agents install their own channel; see Agent setup.')

    def _connect_selected(self, *_):
        channel_id = self._selected_channel
        if not self._history_available or not channel_id or channel_id in self._dispatching:
            return
        if self._channel_requests.get(channel_id, {}).get('state') in ('pending', 'notified', 'claimed'):
            return
        self._dispatching.add(channel_id)
        self._connect_errors.pop(channel_id, None)
        self._render_connect_controls()
        def dispatch():
            request, error = None, None
            try:
                request = self.registry.request_connect(channel_id)
                request = self.registry.wake(request['id'])
            except (OSError, ValueError, RuntimeError, sqlite3.Error) as failure:
                error = str(failure)
            GLib.idle_add(self._connect_finished, channel_id, request, error)
        threading.Thread(target=dispatch, name='observer-channel-wake', daemon=True).start()

    def _connect_finished(self, channel_id, request, error):
        if self._closed:
            return False
        self._dispatching.discard(channel_id)
        if request is not None:
            self._channel_requests[channel_id] = request
        if error is not None:
            self._connect_errors[channel_id] = error
        self._refresh()
        return False

    def _render_visits(self):
        visits = [visit for visit in self._visits if visit.get('observer_id') == self._selected_profile]
        key = json.dumps(visits, sort_keys=True)
        if key != self._visits_key:
            self._updating = True
            self._clear(self.visits_list)
            for visit in visits:
                row = Gtk.ListBoxRow()
                row.visit_id = visit['id']
                content = box(spacing=5)
                content.pack_start(label(event_time(visit.get('updated_at'))), False, False, 0)
                row.status_label = label('', css='muted')
                content.pack_start(row.status_label, False, False, 0)
                row.add(content)
                self.visits_list.add(row)
            children = self.visits_list.get_children()
            chosen = next((row for row in children if row.visit_id == self._selected_visit), children[0] if children else None)
            self._selected_visit = chosen.visit_id if chosen else None
            if chosen:
                self.visits_list.select_row(chosen)
            self._visits_key = key
            self._updating = False
            self.visits_list.show_all()
        self.visits_empty.set_visible(not visits)
        by_id = {visit['id']: visit for visit in visits}
        for row in self.visits_list.get_children():
            row.status_label.set_text(visit_status(by_id[row.visit_id])['label'])

    def _render_current(self):
        visit = next((visit for visit in self._visits if visit['id'] == self._selected_visit), None)
        if not visit:
            self.visit_title.set_text('No visit selected')
            self.visit_state.set_text('Select an observer with a recorded visit.')
            self.visit_context.set_text('')
            self._clear(self.timeline_list)
            self._events_key = None
            self._show_item(None)
            self.timeline_empty.set_visible(False)
            return
        self.visit_title.set_text(visit.get('profile_name') or 'Observer visit')
        self.visit_state.set_text(visit_status(visit)['label'])
        binding = visit.get('binding') or {}
        self.visit_context.set_text(f"World: {binding.get('world_id', 'unavailable')}\nVisit: {visit['id']}")
        events = self.journal.events(visit['id'], limit=200)
        key = json.dumps([visit['id'], events, self.snapshots_toggle.get_active()], sort_keys=True)
        if key == self._events_key:
            if self._image_item:
                self._show_image(self._image_item)
            return
        previous = self.timeline_list.get_selected_row()
        previous_id = previous.history_item['id'] if previous else None
        self._clear(self.timeline_list)
        chosen = None
        for item in timeline_rows(events, snapshots=self.snapshots_toggle.get_active()):
            row = Gtk.ListBoxRow()
            row.history_item = item
            content = box(spacing=6)
            content.pack_start(label(item['title'], css='section-title'), False, False, 0)
            content.pack_start(label(event_time(item['created_at']), css='muted'), False, False, 0)
            if item['text']:
                content.pack_start(label(item['text']), False, False, 0)
            content.pack_start(label(item['status'], css='muted'), False, False, 0)
            row.add(content)
            self.timeline_list.add(row)
            if item['id'] == previous_id:
                chosen = row
        children = self.timeline_list.get_children()
        self.timeline_list.show_all()
        self.timeline_empty.set_visible(not children)
        self.timeline_list.select_row(chosen or (children[-1] if children else None))
        if not children:
            self._show_item(None)
        self._events_key = key

    def _profile_selected(self, _list, row):
        if self._updating or not row:
            return
        self._selected_profile = row.profile_id
        self._selected_channel = row.channel_id
        self._selected_choice = row.choice_id
        self._selected_visit = None
        self._visits_key = None
        self._refresh()

    def _visit_selected(self, _list, row):
        if self._updating or not row:
            return
        self._selected_visit = row.visit_id
        self._events_key = None
        self._refresh()

    def _snapshots_changed(self, *_):
        self._events_key = None
        self._render_current()

    def _timeline_selected(self, _list, row):
        self._show_item(row.history_item if row else None)

    def _detail_image_changed(self, *_):
        item = self._selected_item
        self._image_item = (item.get('detail_image') if self.detail_image_toggle.get_active()
                            else item.get('image')) if item else None
        self._show_image(self._image_item)

    def _show_item(self, item):
        self._selected_item = item
        self.detail_image_toggle.set_active(False)
        self.detail_image_toggle.set_visible(bool(item and item.get('detail_image')))
        self._image_item = item.get('image') if item else None
        self.detail_title.set_text(item['title'] if item else 'Details')
        self.detail_buffer.set_text('\n\n'.join(value for value in
                                  (item['text'], item['status'], item['details']) if value) if item else '')
        self._show_image(self._image_item)

    def _show_image(self, frame):
        fingerprint = frame_fingerprint(self.journal.root, frame) if frame else None
        cache_key = (str(self.journal.root), frame.get('image_path'), frame.get('sha256'), fingerprint) if frame else None
        if fingerprint is not None and self._pixbuf is not None and cache_key == self._image_cache_key:
            self.image_status.set_text(self._image_verified_label if self._history_available
                                       else 'Historical image · current history unavailable')
            return
        self.picture.clear()
        self._pixbuf = None
        self._image_cache_key = None
        if not frame:
            self.image_status.set_text('Image unavailable · no captured frame linked to this entry.')
            return
        result = read_frame_image(self.journal.root, frame)
        if not result['available']:
            self.image_status.set_text(result['reason'])
            return
        data = result['data']
        # Decode only the already verified byte snapshot, with a bounded PNG size.
        if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n':
            self.image_status.set_text('Image unavailable · retained file is not a PNG image.')
            return
        width, height = struct.unpack('>II', data[16:24])
        if not width or not height or width * height > 8_388_608:
            self.image_status.set_text('Image unavailable · image dimensions exceed the preview limit.')
            return
        loader = GdkPixbuf.PixbufLoader.new_with_type('png')
        try:
            loader.write(data)
            loader.close()
            original = loader.get_pixbuf()
            scale = min(1., 440 / original.get_width(), 300 / original.get_height())
            self._pixbuf = original.scale_simple(max(1, round(original.get_width() * scale)),
                                                max(1, round(original.get_height() * scale)),
                                                GdkPixbuf.InterpType.BILINEAR)
            self.picture.set_from_pixbuf(self._pixbuf)
            self._image_cache_key = (str(self.journal.root), frame.get('image_path'), frame.get('sha256'), result.get('fingerprint'))
            role = ('Temporal overview verified' if frame.get('panel_kind') == 'temporal_overview' else
                    'Full-detail original image verified' if frame.get('image_role') == 'full_detail' else
                    'Original image verified')
            self._image_verified_label = f"{role} · {width} × {height}\nSHA256 {frame['sha256']}"
            self.image_status.set_text(self._image_verified_label if self._history_available
                                       else 'Historical image · current history unavailable')
        except GLib.Error:
            self.image_status.set_text('Image unavailable · retained PNG could not be decoded.')

    def _setup_dialog(self, *_):
        dialog = Gtk.Dialog(title='Agent channel setup', transient_for=self, modal=True)
        dialog.set_default_size(670, 490)
        dialog.add_button('Close', Gtk.ResponseType.CLOSE)
        content = dialog.get_content_area()
        content.set_spacing(12)
        content.set_border_width(18)
        content.add(label('Give these steps to the agent you want to install. It chooses and registers its own name.'))
        try:
            instructions = Path(__file__).with_name('AGENT-INSTALL.md').read_text()
        except OSError:
            instructions = ('1. Install the packaged Alien observer MCP server in your existing agent host.\n'
                            '2. Use alien_observer_register with your chosen name and supported existing host binding.\n'
                            '3. Ask the owner to select your installed name here and press Connect.\n'
                            '4. Claim your matching owner request, open the verified image and acknowledge it.\n'
                            'The 93-second observation begins only after that image acknowledgement.\n'
                            '5. Read flowing visual intervals and their full-detail pictures. Capture continues while you think.\n'
                            '6. Optionally leave one overall visual account; individual notes are optional. Send words only through the observer tool.\n'
                            'See the package installation guide for the exact MCP command and arguments.')
        view = Gtk.TextView()
        view.set_editable(False)
        view.set_cursor_visible(False)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.get_buffer().set_text(instructions)
        content.pack_start(scroll(view, height=320), True, True, 0)
        copy = Gtk.Button.new_with_label('Copy steps')
        copy.connect('clicked', lambda *_: Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(instructions, -1))
        content.pack_start(copy, False, False, 0)
        dialog.show_all()
        dialog.run()
        dialog.destroy()


class ObserversApplication(Gtk.Application):
    """One AlienWorld observer window for each canonical Sight history root."""
    def __init__(self, observations):
        self.observations = Path(observations).resolve()
        identity = hashlib.sha256(bytes(self.observations)).hexdigest()
        super().__init__(application_id='org.cyclops.AlienWorld.Observers.h' + identity)
        self.journal = None
        self.window = None
        self.startup_failed = False

    def do_activate(self):
        if self.window is None:
            try:
                if self.journal is None:
                    self.journal = ObserverJournal(self.observations)
                self.window = ObserversWindow(self.journal)
                self.window.connect('destroy', self._window_destroyed)
                self.add_window(self.window)
                self.window.show_all()
                self.window.visits_empty.set_visible(not self.window.visits_list.get_children())
            except Exception as error:
                self.startup_failed = True
                print(f'Observer interface unavailable: {error}', file=sys.stderr)
                self.quit()
                return
        self.window.present()

    def _window_destroyed(self, *_):
        self.window = None

    def do_shutdown(self):
        if self.journal is not None:
            self.journal.close()
            self.journal = None
        Gtk.Application.do_shutdown(self)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Open AlienWorld’s observer interface.')
    parser.add_argument('--observations', type=Path, default=DEFAULT_OBSERVATIONS,
                        help='Sight observation history directory')
    args = parser.parse_args(argv)
    application = ObserversApplication(args.observations)
    result = application.run([parser.prog])
    return 1 if application.startup_failed else result


if __name__ == '__main__':
    raise SystemExit(main())
