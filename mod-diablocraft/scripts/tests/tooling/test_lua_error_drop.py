"""diablocraft-g74u4: the Lua error drop, compiled from production source.

The harness includes the real dc_lua_error_drop.h and drives its rules: BugSack's prefix with and without AceComm's
\\x01-\\x03 chunk marker (docs/research/bugsack-wire.md section 3), one stamped line per chunk, the per-day per-character
file and its cap, and the drop name core patch 0025 asks about. Every harness test runs again on a source mutation
that removes the rule it checks, and that run must fail. The glue (dc_lua_error_drop.cpp: the options, the chat hook,
the GlobalScript answer), the loader line, the conf template and the reserved-name migration are pinned by text.
"""
import re
import shutil
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_class_parity import MODULE, SCRATCH, SRC, mutate, run  # noqa: E402

HEADER = (SRC / "common/dc_lua_error_drop.h").read_text(encoding="utf-8")
GLUE = (SRC / "common/dc_lua_error_drop.cpp").read_text(encoding="utf-8")
LOADER = (SRC / "mod_diablocraft_loader.cpp").read_text(encoding="utf-8")
CONF = (MODULE / "conf/mod_diablocraft.conf.dist").read_text(encoding="utf-8")
RESERVED = (MODULE / "data/sql/db-characters/updates/tooling_0001_reserved_name_torment.sql").read_text(encoding="utf-8")

PRELUDE = r'''
#include <cassert>
#include <sstream>
'''

HELPERS = r'''
using namespace DC::LuaErrorDrop;
static std::string Read(std::filesystem::path const& p) { std::ifstream in(p, std::ios::binary); std::stringstream s; s << in.rdbuf(); return s.str(); }
'''


def harness(body, header=HEADER, folder=""):
    code = (PRELUDE + header + HELPERS + "\nint main() {\n    std::string const dir = " + '"' + folder + '"' + ";\n"
            + body + "\n    return 0;\n}\n")
    return run(code)


def both(test, body, old, new, folder=""):
    """The harness passes on production source and fails on the mutated one."""
    ok, out = harness(body, folder=folder)
    test.assertTrue(ok, out)
    if folder:
        shutil.rmtree(folder)
        Path(folder).mkdir()
    ok, out = harness(body, header=mutate(HEADER, old, new), folder=folder)
    test.assertFalse(ok, "mutation survived: " + new)


class Prefix(unittest.TestCase):
    BODY = r'''
    assert(IsBugSack(std::string("BugSack\t^1^T^t")));
    assert(IsBugSack(std::string("BugSack\x01\t^1^T")));
    assert(IsBugSack(std::string("BugSack\x02\tmid")));
    assert(IsBugSack(std::string("BugSack\x03\t^t^t")));
    assert(!IsBugSack(std::string("BugSack\x04\tx")));
    assert(!IsBugSack(std::string("BugSackX\tx")));
    assert(!IsBugSack(std::string("BugSac\tx")));
    assert(!IsBugSack(std::string("BugSack")));
    assert(!IsBugSack(std::string("BugSack\x01")));
    assert(!IsBugSack(std::string("bugsack\tx")));
    assert(!IsBugSack(std::string("DCARTISAN\tx")));'''

    def test_bare_prefix_and_the_three_chunk_markers(self):
        both(self, self.BODY, "if (tab < msg.size() && msg[tab] >= '\\x01' && msg[tab] <= '\\x03')",
             "if (false)")

    def test_no_fourth_marker(self):
        both(self, self.BODY, "msg[tab] <= '\\x03'", "msg[tab] <= '\\x04'")

    def test_the_tab_ends_the_prefix(self):
        both(self, self.BODY, "return tab < msg.size() && msg[tab] == '\\t';", "return true;")


class Lines(unittest.TestCase):
    def test_one_stamped_line_per_chunk_and_no_stray_break(self):
        both(self, r'''
    assert(Line("12:34:56", "BugSack\x01\t^1^T^N1") == std::string("12:34:56 BugSack\x01\t^1^T^N1\n"));
    assert(Line("00:00:01", "BugSack\tx\ny\rz") == "00:00:01 BugSack\tx y z\n");''',
             "if (c == '\\n' || c == '\\r')", "if (false)")

    def test_the_file_is_the_characters_day(self):
        both(self, r'''
    assert(File("/drop", "2026-10-14", "the designer") == std::filesystem::path("/drop/2026-10-14/the designer.txt"));''',
             "return std::filesystem::path(dir) / date / (name + \".txt\");",
             "return std::filesystem::path(dir) / (name + \".txt\");")


class Cap(unittest.TestCase):
    BODY = r'''
    Drop drop;
    auto const today = File(dir, "2026-10-14", "the designer");
    auto const one = Line("12:00:00", "BugSack\x01\taaaa");
    auto const two = Line("12:00:01", "BugSack\x03\tbb");
    std::uintmax_t const cap = one.size() + two.size();
    assert(drop.Append(today, one, cap) == Outcome::Written);
    assert(drop.Append(today, two, cap) == Outcome::Written);
    assert(Read(today) == one + two);
    assert(drop.Append(today, one, cap) == Outcome::CapReached);
    assert(drop.Append(today, two, cap) == Outcome::Capped);
    assert(Read(today) == one + two);
    auto const other = File(dir, "2026-10-14", "Bea");
    assert(drop.Append(other, one, cap) == Outcome::Written);
    auto const tomorrow = File(dir, "2026-10-15", "the designer");
    assert(drop.Append(tomorrow, one, cap) == Outcome::Written);
    assert(Read(tomorrow) == one);'''

    def setUp(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.folder = tempfile.mkdtemp(prefix="lua-error-drop-", dir=SCRATCH)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_a_line_that_would_pass_the_cap_is_refused(self):
        both(self, self.BODY, "if (size + line.size() > cap)", "if (size > cap)", folder=self.folder)

    def test_the_cap_is_reported_once_per_file(self):
        both(self, self.BODY, "return capped.insert(file.string()).second ? Outcome::CapReached : Outcome::Capped;",
             "return Outcome::CapReached;", folder=self.folder)

    def test_appends_never_truncate(self):
        both(self, self.BODY, "std::ios::binary | std::ios::app", "std::ios::binary", folder=self.folder)


class DropName(unittest.TestCase):
    def test_only_the_configured_name_and_blank_is_off(self):
        both(self, r'''
    assert(IsDropName("Torment", "Torment"));
    assert(!IsDropName("the designer", "Torment"));
    assert(!IsDropName("", ""));''', "return !name.empty() && to == name;", "return to == name;")


class Glue(unittest.TestCase):
    def test_the_chat_hook_takes_addon_bugsack_from_every_character_when_on(self):
        hook = GLUE[GLUE.index("void OnPlayerBeforeSendChatMessage("):GLUE.index("class WhisperScript")]
        self.assertIn('PlayerScript("dc_lua_error_drop", {PLAYERHOOK_ON_BEFORE_SEND_CHAT_MESSAGE})', GLUE)
        self.assertIn("if (lang != LANG_ADDON || !player || !IsBugSack(msg))\n                    return;", hook)
        self.assertIn("if (now.dir.empty())\n                    return;", hook)
        # a class that is not Playable yet (a Necromancer before 2a) still has its errors written
        self.assertNotIn("Playable", hook)
        self.assertNotIn("dc_classes.h", GLUE)
        self.assertIn('std::strftime(date, sizeof(date), "%Y-%m-%d", &local);', hook)
        self.assertIn('std::strftime(clock, sizeof(clock), "%H:%M:%S", &local);', hook)
        self.assertIn("Files().Append(File(now.dir, date, player->GetName()), Line(clock, msg), now.cap)", hook)
        # the hook only reads: the message goes on to the chat handler unchanged
        self.assertNotRegex(hook, r"\b(msg|lang|type)\s*=[^=]")

    def test_the_whisper_answer_is_the_name_option(self):
        self.assertIn('GlobalScript("dc_lua_error_drop_whisper", {GLOBALHOOK_IS_ADDON_WHISPER_DROP})', GLUE)
        self.assertIn("return IsDropName(to, Current().name);", GLUE)

    def test_the_options_are_read_at_startup_and_reload_with_the_templates_defaults(self):
        read = dict(re.findall(r'GetOption<[\w:]+>\("(Diablocraft\.LuaErrorDrop\.\w+)", ("?[^)]*?"?)\)', GLUE))
        self.assertEqual({"Diablocraft.LuaErrorDrop.Dir": '""', "Diablocraft.LuaErrorDrop.Name": '"Torment"',
                          "Diablocraft.LuaErrorDrop.CapBytes": "2097152"}, read)
        conf = dict(re.findall(r"^(Diablocraft\.LuaErrorDrop\.\w+) = (.*)$", CONF, re.M))
        self.assertEqual({"Diablocraft.LuaErrorDrop.Dir": '""', "Diablocraft.LuaErrorDrop.Name": "Torment",
                          "Diablocraft.LuaErrorDrop.CapBytes": "2097152"}, conf)
        self.assertIn("{WORLDHOOK_ON_STARTUP, WORLDHOOK_ON_AFTER_CONFIG_LOAD}", GLUE)
        self.assertIn("void OnStartup() override\n            {\n                Load();", GLUE)
        self.assertIn("if (reload)\n                    Load();", GLUE)
        self.assertEqual(1, GLUE.count("sConfigMgr->GetOption<std::string>(\"Diablocraft.LuaErrorDrop.Dir\""))

    def test_the_loader_registers_it_and_the_name_is_reserved(self):
        self.assertIn('#include "common/dc_lua_error_drop.h"', LOADER)
        self.assertIn("    DC::LuaErrorDrop::RegisterScripts();\n", LOADER)
        self.assertIn("INSERT IGNORE INTO `reserved_name` (`name`) VALUES ('Torment');", RESERVED)


if __name__ == "__main__":
    unittest.main()
