"""Whose file is this — ours, Steam's, or the original we saved?

A Steam update rewrites only the files whose content changed, so it leaves our
patched bundles alone and the backup ends up holding originals from two
different builds. Getting this wrong is what puts an old catalog next to new
bundles, and that combination is a black screen on launch.
"""
import os

import patcher
import steam


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


class TestRevertLegacy:
    def test_only_files_still_ours_go_back(self, fake_game):
        # 1.0.4 on 1.0.66 left a second ru-RU behind; a file Steam has rewritten
        # since is the new build's original and must stay
        layout = steam.locate(str(fake_game(stamp={})))
        mine, steams = patcher.LEGACY_BUNDLES[:2]
        for name, now in ((mine, b"ours"), (steams, b"new build")):
            with open(layout.bundle(name), "wb") as fh:
                fh.write(now)
            with open(os.path.join(layout.backup, name), "wb") as fh:
                fh.write(b"original")
        stamp = stamp_of(**{mine: patcher.sha256(layout.bundle(mine)), steams: "0" * 64})

        assert patcher.revert_legacy(layout, stamp) == 1
        with open(layout.bundle(mine), "rb") as fh:
            assert fh.read() == b"original"
        with open(layout.bundle(steams), "rb") as fh:
            assert fh.read() == b"new build"
