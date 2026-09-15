"""Whose file is this — ours, Steam's, or the original we saved?

A Steam update rewrites only the files whose content changed, so it leaves our
patched bundles alone and the backup ends up holding originals from two
different builds. Getting this wrong is what puts an old catalog next to new
bundles, and that combination is a black screen on launch.
"""
import os

import patcher


def stamp_of(**patched):
    return {"version": "1.0.0", "patched": patched, "written": 1_000_000}


def files(tmp_path, game_bytes, saved_bytes):
    game = tmp_path / "catalog.json"
    saved = tmp_path / "saved.json"
    game.write_bytes(game_bytes)
    saved.write_bytes(saved_bytes)
    return str(game), str(saved)


class TestSteamRewrote:
    def test_our_own_output_is_not_mistaken_for_an_update(self, tmp_path):
        game, saved = files(tmp_path, b"patched", b"original")
        stamp = stamp_of(**{"catalog.json": patcher.sha256(game)})
        assert not patcher.steam_rewrote(game, saved, "catalog.json", stamp)

    def test_untouched_original_is_not_an_update(self, tmp_path):
        game, saved = files(tmp_path, b"original", b"original")
        assert not patcher.steam_rewrote(game, saved, "catalog.json", stamp_of())

    def test_file_replaced_since_the_patch_is_an_update(self, tmp_path):
        game, saved = files(tmp_path, b"new build", b"original")
        stamp = stamp_of(**{"catalog.json": "0" * 64})   # what we left, long gone
        assert patcher.steam_rewrote(game, saved, "catalog.json", stamp)

    def test_stamp_without_hashes_falls_back_on_the_clock(self, tmp_path):
        game, saved = files(tmp_path, b"new build", b"original")
        stamp = {"version": "1.0.0", "written": os.path.getmtime(game) - 1}
        assert patcher.steam_rewrote(game, saved, "catalog.json", stamp)

        stamp["written"] = os.path.getmtime(game) + 1     # patched after, by us
        assert not patcher.steam_rewrote(game, saved, "catalog.json", stamp)

    def test_no_stamp_at_all_leaves_the_backup_alone(self, tmp_path):
        # a first install that crashed midway: the game holds half-patched files
        # and nothing says they are Steam's, so the saved originals stay
        game, saved = files(tmp_path, b"half patched", b"original")
        assert not patcher.steam_rewrote(game, saved, "catalog.json", {})
