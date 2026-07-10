from __future__ import annotations

import unittest

from vinyl_panel.event_hook import apply_event
from vinyl_panel.state import empty_state


class EventHookTests(unittest.TestCase):
    def test_track_changed_sets_pending_metadata(self) -> None:
        state = apply_event(
            empty_state(),
            {
                "PLAYER_EVENT": "track_changed",
                "TRACK_ID": "track-a",
                "NAME": "Song A",
                "ARTISTS": "Artist A",
                "ALBUM": "Album A",
                "DURATION_MS": "180000",
                "COVERS": "https://example.invalid/a.jpg",
                "ITEM_TYPE": "Track",
            },
            "2026-07-10T12:00:00+00:00",
        )

        self.assertEqual(state["current_track"]["id"], "")
        self.assertEqual(state["pending_track"]["id"], "track-a")
        self.assertEqual(state["pending_track"]["name"], "Song A")
        self.assertEqual(state["pending_track"]["artist_text"], "Artist A")

    def test_playing_promotes_pending_track(self) -> None:
        pending = apply_event(
            empty_state(),
            {
                "PLAYER_EVENT": "track_changed",
                "TRACK_ID": "track-a",
                "NAME": "Song A",
                "ARTISTS": "Artist A",
                "DURATION_MS": "180000",
            },
            "2026-07-10T12:00:00+00:00",
        )
        playing = apply_event(
            pending,
            {
                "PLAYER_EVENT": "playing",
                "TRACK_ID": "track-a",
                "POSITION_MS": "5000",
            },
            "2026-07-10T12:00:01+00:00",
        )

        self.assertEqual(playing["current_track"]["id"], "track-a")
        self.assertEqual(playing["current_track"]["name"], "Song A")
        self.assertEqual(playing["pending_track"]["id"], "")
        self.assertEqual(playing["playback"]["status"], "playing")
        self.assertEqual(playing["playback"]["position_ms"], 5000)

    def test_preloading_does_not_replace_current_track(self) -> None:
        state = empty_state()
        state["current_track"].update({"id": "track-a", "name": "Song A"})
        state["playback"].update({"status": "playing", "duration_ms": 180000})

        result = apply_event(
            state,
            {"PLAYER_EVENT": "preloading", "TRACK_ID": "track-b"},
            "2026-07-10T12:01:00+00:00",
        )

        self.assertEqual(result["current_track"]["id"], "track-a")
        self.assertEqual(result["pending_track"]["id"], "track-b")
        self.assertEqual(result["playback"]["status"], "playing")

    def test_manual_skip_switches_on_playing_event(self) -> None:
        state = empty_state()
        state["current_track"].update({"id": "track-a", "name": "Song A"})
        state["playback"].update({"status": "playing", "position_ms": 60000, "duration_ms": 180000})
        state = apply_event(
            state,
            {
                "PLAYER_EVENT": "track_changed",
                "TRACK_ID": "track-b",
                "NAME": "Song B",
                "ARTISTS": "Artist B",
                "DURATION_MS": "200000",
            },
            "2026-07-10T12:02:00+00:00",
        )

        result = apply_event(
            state,
            {"PLAYER_EVENT": "playing", "TRACK_ID": "track-b", "POSITION_MS": "0"},
            "2026-07-10T12:02:01+00:00",
        )

        self.assertEqual(result["current_track"]["id"], "track-b")
        self.assertEqual(result["current_track"]["name"], "Song B")
        self.assertEqual(result["playback"]["position_ms"], 0)

    def test_seek_keeps_playing_status(self) -> None:
        state = empty_state()
        state["current_track"].update({"id": "track-a", "name": "Song A"})
        state["playback"].update({"status": "playing", "position_ms": 10000, "duration_ms": 180000})

        result = apply_event(
            state,
            {"PLAYER_EVENT": "seeked", "TRACK_ID": "track-a", "POSITION_MS": "90000"},
            "2026-07-10T12:03:00+00:00",
        )

        self.assertEqual(result["playback"]["status"], "playing")
        self.assertEqual(result["playback"]["position_ms"], 90000)

    def test_pause_and_resume(self) -> None:
        state = empty_state()
        state["current_track"].update({"id": "track-a", "name": "Song A"})

        paused = apply_event(
            state,
            {"PLAYER_EVENT": "paused", "TRACK_ID": "track-a", "POSITION_MS": "45000"},
            "2026-07-10T12:04:00+00:00",
        )
        resumed = apply_event(
            paused,
            {"PLAYER_EVENT": "playing", "TRACK_ID": "track-a", "POSITION_MS": "45000"},
            "2026-07-10T12:04:01+00:00",
        )

        self.assertEqual(paused["playback"]["status"], "paused")
        self.assertEqual(resumed["playback"]["status"], "playing")

    def test_control_events_do_not_wipe_track(self) -> None:
        state = empty_state()
        state["current_track"].update({"id": "track-a", "name": "Song A"})

        result = apply_event(
            state,
            {"PLAYER_EVENT": "shuffle_changed", "SHUFFLE": "true"},
            "2026-07-10T12:05:00+00:00",
        )

        self.assertEqual(result["current_track"]["id"], "track-a")
        self.assertEqual(result["controls"]["shuffle"], "true")


if __name__ == "__main__":
    unittest.main()
