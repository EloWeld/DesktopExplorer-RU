"""Finding the game — the part that runs before anything can go right."""
import os
import sys

import pytest

import steam
from errors import GameLayoutError, GameNotFound


class TestCleanPath:
    @pytest.mark.skipif(sys.platform == "win32",
                        reason="на Windows обратный слеш — разделитель пути, а не экранирование")
    def test_finder_drop_keeps_escaped_spaces_together(self):
        dropped = r"/Users/me/Library/Application\ Support/Steam"
        assert steam.clean_path(dropped) == "/Users/me/Library/Application Support/Steam"

    def test_quoted_path(self):
        assert steam.clean_path('"/Games/Desktop Explorer"') == "/Games/Desktop Explorer"

    def test_trailing_separator_and_whitespace(self):
        assert steam.clean_path("  /Games/Desktop Explorer/  ") == "/Games/Desktop Explorer"

    def test_tilde_expands(self):
        assert steam.clean_path("~/Games").startswith(os.path.expanduser("~"))

    def test_empty(self):
        assert steam.clean_path("   ") == ""

    def test_unbalanced_quote_is_used_as_typed(self):
        assert steam.clean_path('/Games/it"s') == '/Games/it"s'


class TestLibraryDiscovery:
    def test_reads_second_library_from_vdf(self, fake_steam):
        root, other = fake_steam
        found = steam.candidates()
        assert os.path.join(str(other), "steamapps", "common", steam.GAME) in found
        assert os.path.join(str(root), "steamapps", "common", steam.GAME) in found

    def test_finds_game_in_secondary_library(self, fake_steam, monkeypatch, tmp_path):
        _root, other = fake_steam
        game = other / "steamapps" / "common" / steam.GAME
        game.mkdir(parents=True)
        assert steam.find_game() == str(game)

    def test_missing_game_explains_itself(self, fake_steam):
        with pytest.raises(GameNotFound) as excinfo:
            steam.find_game()
        assert excinfo.value.hint            # the player is told what to do next

    def test_explicit_path_wins(self, fake_steam, tmp_path):
        somewhere = tmp_path / "Custom" / "Desktop Explorer"
        somewhere.mkdir(parents=True)
        assert steam.find_game(str(somewhere)) == str(somewhere)

    def test_explicit_missing_path_reports_that_path(self, tmp_path):
        with pytest.raises(GameNotFound):
            steam.find_game(str(tmp_path / "nope"))

    def test_windows_style_vdf_paths_are_unescaped(self, tmp_path, monkeypatch):
        root = tmp_path / "Steam"
        (root / "steamapps").mkdir(parents=True)
        (root / "steamapps" / "libraryfolders.vdf").write_text(
            '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"D:\\\\SteamLibrary"\n\t}\n}\n',
            encoding="utf-8")
        monkeypatch.setattr(steam, "STEAM_ROOTS", [str(root)])
        assert any("D:\\SteamLibrary" in c for c in steam.candidates())

    def test_absent_vdf_still_yields_the_steam_root(self, tmp_path, monkeypatch):
        root = tmp_path / "Steam"
        root.mkdir()
        monkeypatch.setattr(steam, "STEAM_ROOTS", [str(root)])
        assert steam.candidates() == [
            os.path.join(str(root), "steamapps", "common", steam.GAME)]


class TestLayout:
    def test_reads_a_healthy_install(self, fake_game):
        layout = steam.locate(str(fake_game()))
        assert os.path.basename(layout.plat) == "StandaloneOSX"
        assert layout.images.startswith(steam.IMAGES_EN)
        assert os.path.isfile(layout.catalog)
        assert layout.backup.endswith("_ru_backup_original")

    def test_folder_without_addressables_is_named_as_such(self, tmp_path):
        empty = tmp_path / "Somewhere"
        empty.mkdir()
        with pytest.raises(GameLayoutError) as excinfo:
            steam.locate(str(empty))
        assert "локализации" in excinfo.value.message

    def test_missing_artwork_bundle_suggests_an_update(self, fake_game):
        game = fake_game(images=None)
        with pytest.raises(GameLayoutError) as excinfo:
            steam.locate(str(game))
        assert "русификатор" in (excinfo.value.hint or "")

    def test_missing_dll_is_reported_separately(self, fake_game):
        game = fake_game()
        dll = (game / "Desktop Explorer.app" / "Contents" / "Resources" / "Data"
               / "Managed" / "Assembly-CSharp.dll")
        dll.unlink()
        with pytest.raises(GameLayoutError) as excinfo:
            steam.locate(str(game))
        assert "Assembly-CSharp.dll" in excinfo.value.message

    def test_nonexistent_folder(self, tmp_path):
        with pytest.raises(GameNotFound):
            steam.locate(str(tmp_path / "gone"))
