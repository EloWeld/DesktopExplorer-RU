"""Telling "never patched" from "patched" from "a game update ate the patch"."""
import state
import steam


def status_of(game):
    return state.status(steam.locate(str(game)))


class TestStatus:
    def test_untouched_game_is_clean(self, fake_game):
        assert status_of(fake_game()).code == state.CLEAN

    def test_patched_game_reports_its_version(self, fake_game):
        st = status_of(fake_game(patched=True, stamp={"version": "1.0.0"}))
        assert st.installed
        assert st.version == "1.0.0"
        assert "установлен" in st.label()

    def test_backup_without_patched_catalog_means_the_update_wiped_it(self, fake_game):
        # Steam replaced the bundles; the backup and its stamp survived
        st = status_of(fake_game(patched=False, stamp={"version": "1.0.0"}))
        assert st.stale
        assert "обновилась" in st.label()

    def test_backup_without_stamp_is_not_treated_as_installed(self, fake_game):
        # what an uninstall leaves behind: originals kept, stamp removed
        game = fake_game(patched=False)
        (game / "_ru_backup_original").mkdir()
        assert status_of(game).code == state.CLEAN

    def test_patched_without_stamp_still_reads_as_installed(self, fake_game):
        st = status_of(fake_game(patched=True))
        assert st.installed
        assert st.version is None

    def test_unreadable_catalog_is_not_a_crash(self, fake_game):
        game = fake_game()
        layout = steam.locate(str(game))
        with open(layout.catalog, "w", encoding="utf-8") as fh:
            fh.write("{ this is not json")
        assert state.status(layout).code == state.CLEAN
