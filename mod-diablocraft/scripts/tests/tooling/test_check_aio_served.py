#!/usr/bin/env python3
"""check_aio_served.py (diablocraft-xbba): AIO may serve only dc_aio's files.

Run: python3 mod-diablocraft/scripts/tests/tooling/test_check_aio_served.py
Every tree is a fixture under the scratch folder; the live tree is never read.
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
ROOT = SCRIPTS.parent.parent
CHECK = SCRIPTS / "check_aio_served.py"
SERVED = "if AIO.AddAddon() then\n    print('server')\nend\n"


def write(path, text="x = 1\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class Fixture(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "azerothcore-wotlk" / "build" / "_agent-scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(prefix="aio-served-", dir=scratch))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.server = self.tmp / "server"
        self.scripts = self.server / "bin" / "lua_scripts"
        # dc_aio is a symlink into a release folder, as the PM builds it.
        self.release_aio = self.tmp / "releases" / "current" / "lua" / "aio"
        write(self.release_aio / "dc_a.lua", SERVED)
        write(self.release_aio / "dc_b.lua", SERVED + "-- more\n")
        write(self.release_aio / "dc_helper.lua", "return {}\n")  # no AddAddon: never served
        self.scripts.mkdir(parents=True)
        (self.scripts / "dc_aio").symlink_to(self.release_aio)
        write(self.scripts / "AIO" / "AIO_Server" / "AIO.lua", "function AIO.AddAddon() end\n")
        write(self.scripts / "AIO" / "AIO_Server" / "queue.lua")
        write(self.scripts / "AIO" / "LICENSE", "gpl\n")
        write(self.scripts / "AIO" / "README.md", "aio\n")
        (self.scripts / "extensions").mkdir()
        write(self.scripts / "extensions" / "util.ext", "x = 2\n")

    def run_check(self):
        return subprocess.run([sys.executable, str(CHECK), str(self.server)], capture_output=True, text=True)

    def red(self, needle):
        r = self.run_check()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(needle, r.stdout)



class CheckAioServed(Fixture):
    def test_the_clean_tree_passes_and_counts_what_aio_serves(self):
        r = self.run_check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        expected = sum((self.release_aio / n).stat().st_size for n in ("dc_a.lua", "dc_b.lua"))
        self.assertIn("AIO serves 2 files, %d bytes" % expected, r.stdout)

    def test_an_extra_top_level_folder_fails(self):
        write(self.scripts / "ForgeUI" / "core.lua")
        self.red("lua_scripts/ForgeUI: not allowed at the top level")

    def test_an_extra_top_level_file_fails(self):
        write(self.scripts / "stray.lua")
        self.red("lua_scripts/stray.lua")

    def test_a_missing_required_top_level_entry_fails(self):
        shutil.rmtree(self.scripts / "extensions")
        self.red("lua_scripts/extensions: missing")

    def test_a_missing_lua_scripts_folder_fails(self):
        shutil.rmtree(self.scripts)
        self.red("does not exist")

    def test_aio_holding_more_than_aio_server_fails(self):
        write(self.scripts / "AIO" / "AIO_Client" / "AIO.lua", "x = 1\n")
        self.red("lua_scripts/AIO/AIO_Client")

    def test_an_addaddon_file_outside_dc_aio_fails(self):
        write(self.scripts / "extensions" / "client.lua", SERVED)
        self.red("lua_scripts/extensions/client.lua: calls AddAddon outside dc_aio")

    def test_addaddoncode_outside_dc_aio_fails_too(self):
        write(self.scripts / "extensions" / "code.ext", "AIO.AddAddonCode('x', 'y')\n")
        self.red("lua_scripts/extensions/code.ext")

    def test_only_aios_own_file_is_exempt(self):
        write(self.scripts / "AIO" / "AIO_Server" / "extra.lua", SERVED)
        self.red("lua_scripts/AIO/AIO_Server/extra.lua")

    def test_a_symlinked_folder_is_followed(self):
        outside = self.tmp / "outside"
        write(outside / "forge.lua", SERVED)
        (self.scripts / "extensions" / "link").symlink_to(outside)
        self.red("lua_scripts/extensions/link/forge.lua")

    def test_a_symlink_loop_does_not_hang(self):
        (self.scripts / "extensions" / "loop").symlink_to(self.scripts / "extensions")
        r = self.run_check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_files_ale_does_not_load_are_not_scanned(self):
        write(self.scripts / "extensions" / "notes.txt", SERVED)
        self.assertEqual(self.run_check().returncode, 0)

    def test_usage_error_is_exit_two(self):
        r = subprocess.run([sys.executable, str(CHECK)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_our_own_dc_aio_folder_is_accepted_as_the_served_list(self):
        (self.scripts / "dc_aio").unlink()
        (self.scripts / "dc_aio").symlink_to(ROOT / "mod-diablocraft" / "lua" / "aio")
        r = self.run_check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"AIO serves \d+ files")

    def test_a_discord_token_in_client_bound_code_fails(self):
        # A token shape, not a real one: 24.6.38 characters around two dots.
        write(self.release_aio / "dc_secret.lua", SERVED + 'token = "MTIzNDU2Nzg5MDEyMzQ1Njc4.ABCDEF.GHIJKLMNOPQRSTUVWXYZabcdef123"\n')
        self.red("dc_secret.lua: client-bound code names a Discord token")

    def test_a_discord_webhook_in_client_bound_code_fails(self):
        write(self.release_aio / "dc_hook.lua", SERVED + 'url = "https://discord.com/api/webhooks/123/abc"\n')
        self.red("dc_hook.lua: client-bound code names a Discord webhook")

    def test_a_github_token_in_client_bound_code_fails(self):
        write(self.release_aio / "dc_pat.lua", SERVED + 'pat = "ghp_0123456789abcdefghijKLMNOPQRSTUV"\n')
        self.red("dc_pat.lua: client-bound code names a GitHub token")

    def test_a_channel_or_role_id_in_client_bound_code_fails(self):
        write(self.release_aio / "dc_ids.lua", SERVED + "local role_id = 123456789\n")
        self.red("dc_ids.lua: client-bound code names a channel or role id")

    def test_a_repository_detail_in_client_bound_code_fails(self):
        write(self.release_aio / "dc_repo.lua", SERVED + '-- see https://github.com/Calmoran/Project-Torment\n')
        self.red("dc_repo.lua: client-bound code names a GitHub repository detail")

    def test_a_secret_outside_client_bound_code_is_not_flagged(self):
        # dc_helper.lua never calls AddAddon, so AIO never ships it: the bot's own
        # files, which hold the real token, are not this check's business.
        write(self.release_aio / "dc_helper.lua",
              'token = "MTIzNDU2Nzg5MDEyMzQ1Njc4.ABCDEF.GHIJKLMNOPQRSTUVWXYZabcdef123"\n')
        write(self.scripts / "extensions" / "notes.txt", "github.com/Calmoran/Project-Torment\n")
        r = self.run_check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class DevForgeUI(Fixture):
    """--dev-forgeui LIST (diablocraft-53szt): ForgeUI is allowed on the dev realm, only the files the list names."""

    def setUp(self):
        super().setUp()
        self.list = self.tmp / "forgeui_files.txt"
        self.list.write_text("ForgeUI_Client_A.lua\nLICENSE.txt\nserver/ForgeUI_Server.lua\n")
        write(self.scripts / "ForgeUI" / "ForgeUI_Client_A.lua", SERVED)
        write(self.scripts / "ForgeUI" / "server" / "ForgeUI_Server.lua", "-- server\n")

    def run_dev(self, *extra):
        return subprocess.run([sys.executable, str(CHECK), str(self.server), "--dev-forgeui", str(self.list), *extra],
                              capture_output=True, text=True)

    def red_dev(self, needle):
        r = self.run_dev()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(needle, r.stdout)

    def test_the_listed_files_pass_on_dev_even_though_one_calls_addaddon(self):
        r = self.run_dev()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ForgeUI (dev only) holds 2 listed files", r.stdout)
        self.assertIn("AIO serves 2 files", r.stdout, "ForgeUI's AddAddon file is not counted as dc_aio's")

    def test_the_same_tree_is_red_without_the_flag(self):
        self.red("lua_scripts/ForgeUI: not allowed at the top level")

    def test_a_file_the_list_does_not_name_is_red_on_dev(self):
        write(self.scripts / "ForgeUI" / "ForgeUI_Client_B.lua", SERVED)
        self.red_dev("lua_scripts/ForgeUI/ForgeUI_Client_B.lua: not on the ForgeUI file list")

    def test_a_non_lua_file_the_list_does_not_name_is_red_on_dev(self):
        write(self.scripts / "ForgeUI" / "fonts" / "Unifont.ttf", "font")
        self.red_dev("lua_scripts/ForgeUI/fonts/Unifont.ttf: not on the ForgeUI file list")

    def test_a_file_in_a_nested_folder_must_be_listed_by_its_path(self):
        write(self.scripts / "ForgeUI" / "other" / "ForgeUI_Server.lua", "-- same name, another folder\n")
        self.red_dev("lua_scripts/ForgeUI/other/ForgeUI_Server.lua")

    def test_the_flag_allows_no_other_top_level_folder(self):
        write(self.scripts / "Elsewhere" / "core.lua")
        self.red_dev("lua_scripts/Elsewhere: not allowed at the top level")

    def test_the_flag_allows_no_addaddon_file_outside_dc_aio_and_forgeui(self):
        write(self.scripts / "extensions" / "client.lua", SERVED)
        self.red_dev("lua_scripts/extensions/client.lua: calls AddAddon outside dc_aio")

    def test_a_dev_tree_without_forgeui_still_passes(self):
        shutil.rmtree(self.scripts / "ForgeUI")
        r = self.run_dev()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_missing_or_empty_list_is_red(self):
        self.list.write_text("")
        self.red_dev("the ForgeUI file list")
        self.list.unlink()
        self.red_dev("cannot read the ForgeUI file list")

    def test_a_symlinked_folder_inside_forgeui_is_followed_and_held_to_the_list(self):
        outside = self.tmp / "outside"
        write(outside / "forge.lua", SERVED)
        (self.scripts / "ForgeUI" / "link").symlink_to(outside)
        self.red_dev("lua_scripts/ForgeUI/link/forge.lua: not on the ForgeUI file list")


if __name__ == "__main__":
    unittest.main()
