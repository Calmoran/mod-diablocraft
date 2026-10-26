"""The game version players see (diablocraft-version-display, ruling q-1001-42 A).

    python3 mod-diablocraft/scripts/tests/release/test_game_version.py

One source: VERSION's `module` (X.Y.Z) and `launcher_letter` (empty, or one letter for a launcher-only
publish). The real header dc_version_parse.h is compiled once for the whole file (compose, the published
version, the published patch, the reply); `.dc version`, the startup read and the enforcement path are pinned
in dc_version.cpp, the conf and the contract. Every pin is run against a broken copy and must fail. VERSION's
`schema` is checked against schema.csv. (test_version_parse.py and test_version_enforcement.py were merged
in here.) Not run: the worldserver itself (the sheet runs `.dc version`)."""
import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

ROOT = Path(__file__).resolve().parents[4]
HEADER = ROOT / "mod-diablocraft/src/common/dc_version_parse.h"
CPP = ROOT / "mod-diablocraft/src/common/dc_version.cpp"
VERSION = ROOT / "VERSION"
SCHEMA = ROOT / "mod-diablocraft/data/sql/schema.csv"
CONF = ROOT / "mod-diablocraft/conf/mod_diablocraft.conf.dist"
CONTRACT = ROOT / "docs/contracts/version-enforcement.md"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/game-version"

MAIN = r'''
#include "dc_version_parse.h"
#include <iostream>
using namespace DC::Version;
int main(){ std::string kind, a, b, c, d, e;
  while (std::getline(std::cin, kind)) { std::getline(std::cin, a); std::getline(std::cin, b);
    try {
      if (kind == "compose") std::cout << "[" << ComposeVersion(a, b) << "]\n";
      else if (kind == "published") std::cout << "[" << ParsePublishedVersion(a) << "]\n";
      else if (kind == "reply") std::cout << VersionReply(a, b, 30, 55, "") << "\n";
      else if (kind == "reply_pub") std::cout << VersionReply(a, b, 30, 55, "0.1.1a") << "\n";
      else if (kind == "patch") std::cout << ParsePublishedPatch(a) << "\n";
    } catch (...) { std::cout << "THROW\n"; } } }
'''


def program():
    """The compiled harness: one build of the real header for every test of the file (cached across runs by its text)."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    source = SCRATCH / "m.cpp"
    if not source.is_file() or source.read_text(encoding="utf-8") != MAIN:
        source.write_text(MAIN, encoding="utf-8")
    return harness_env.build([source], flags=["-std=c++17"], includes=[HEADER.parent])


def run(*pairs):
    stdin = "".join("%s\n%s\n%s\n" % p for p in pairs)
    return harness_env.run([str(program())], input=stdin, capture_output=True, text=True).stdout.splitlines()


def version_file():
    return dict(line.split("=", 1) for line in VERSION.read_text().splitlines() if "=" in line)


class Compose(unittest.TestCase):
    def test_cases(self):
        cases = [("0.1.1", "", "[0.1.1]"), ("0.1.1", "a", "[0.1.1a]"), ("0.1.0", "b\r", "[0.1.0b]"),
                 ("0.1.1\r", "", "[0.1.1]"), ("0.1.1", "ab", "[0.1.1]"), ("0.1.1", "A", "[0.1.1]"),
                 ("0.1.1", "1", "[0.1.1]"), ("0.1", "", "[]"), ("x.y.z", "a", "[]"), ("", "", "[]"),
                 ("0.1.1a", "", "[]"), ("0.1.99999", "", "[]")]
        got = run(*[("compose", m, l) for m, l, _ in cases])
        self.assertEqual(got, [w for _, _, w in cases])

    def test_published_version(self):
        cases = [('{"schema":1,"client_patch":55,"version":"0.1.1"}', "[0.1.1]"),
                 ('{"version": "0.1.1a", "client_patch":56}', "[0.1.1a]"), ('{"client_patch":55}', "[]"),
                 ('{"version":"banana"}', "[]"), ('{"version":"0.1.1ab"}', "[]"), ('{"version":1}', "[]"), ("", "[]")]
        self.assertEqual(run(*[("published", b, "") for b, _ in cases]), [w for _, w in cases])

    def test_the_published_patch_read_never_throws(self):
        """ParsePublishedPatch, the read the .dc version reply uses, whatever the manifest holds."""
        cases = [('{"client_patch": 7}', 7), ('{"a":1,"client_patch":12,"b":2}', 12), ('{"client_patch":"7"}', 0), ('{}', 0), ('', 0),
                 ('{"client_patch": 999999}', 999999),
                 ('{"client_patch": 99999999999999999999999999}', 0),  # would make std::stoi throw out_of_range
                 ('{"client_patch": 2147483648}', 0), ('{"client_patch": 1234567}', 0)]   # more than 6 digits is not a patch number
        self.assertEqual(run(*[("patch", body, "") for body, _ in cases]), [str(want) for _, want in cases])

    def test_reply_names_version_next_to_the_client_patch_line(self):
        out = run(("reply", "0.1.1", "0.1.1"), ("reply", "", "0.1.1"), ("reply_pub", "0.1.1", "0.1.1"),
                  ("reply_pub", "0.1.1a", "0.1.1"))
        self.assertEqual(out[0], "Torment version 0.1.1. Server expects client patch 55 or newer. Module 0.1.1, schema 30.")
        self.assertTrue(out[1].startswith("Torment version 0.1.1."), out[1])        # no label: the module text
        self.assertIn("(published client: version 0.1.1a)", out[2])               # a launcher-only publish moved on
        self.assertNotIn("published client", out[3])                              # same version: not repeated


class OneSource(unittest.TestCase):
    def test_version_file_carries_the_version_and_the_letter(self):
        v = version_file()
        self.assertRegex(v["module"], r"^\d+\.\d+\.\d+$")
        self.assertIn("launcher_letter", v)
        self.assertRegex(v["launcher_letter"], r"^[a-z]?$")
        self.assertEqual(run(("compose", v["module"], v["launcher_letter"]))[0], "[%s%s]" % (v["module"], v["launcher_letter"]))


def schema_problems(values, rows):
    out = []
    if [int(row["schema"]) for row in rows] != list(range(1, int(values["schema"]) + 1)):
        out.append("schema.csv does not number 1..VERSION's schema")
    if not rows or rows[-1]["schema"] != values["schema"]:
        out.append("schema.csv's last row is not VERSION's schema")
    if not all(row["last_file"] for row in rows):
        out.append("a schema row names no last file")
    return out


class Schema(unittest.TestCase):
    def test_the_version_files_schema_is_schema_csvs_last_row(self):
        with SCHEMA.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(schema_problems(version_file(), rows), [])
        values = version_file()
        self.assertTrue(schema_problems(dict(values, schema=str(int(values["schema"]) + 1)), rows), "a schema ahead of schema.csv passed")
        self.assertTrue(schema_problems(values, rows[:-1]), "a schema.csv missing its last row passed")
        self.assertTrue(schema_problems(values, [dict(row, last_file="") for row in rows]), "a row with no last file passed")
        self.assertTrue(schema_problems(values, [dict(row, schema=str(i + 2)) for i, row in enumerate(rows)]), "numbers not from 1 passed")


class Production(unittest.TestCase):
    cpp = CPP.read_text(encoding="utf-8")

    @staticmethod
    def pins(text):
        return [
            ("startup composes from VERSION's two lines",
             'version = ComposeVersion(module, values.count("launcher_letter") ? values.at("launcher_letter") : "");' in text),
            (".dc version replies through VersionReply with the version",
             "VersionReply(version, module, schema," in text and "PublishedVersion()" in text),
            ("the startup log names the version", "[DC version] version={}" in text),
            ("the old reply without a version is gone", 'Torment version: module {}' not in text),
            ("a version refusal stops the worldserver at startup", "World::StopNow(ERROR_EXIT_CODE)" in text),
            ("the published check reads the module and released migrations", "state IN ('MODULE','RELEASED')" in text),
            ("a mismatch never blocks login", "mismatch never blocks login" in text),
            ("the client patch is the newer of the client's and the published", "std::max(clientPatch, PublishedPatch())" in text),
        ]

    def test_pins_hold(self):
        for name, ok in self.pins(self.cpp):
            self.assertTrue(ok, name)

    def test_each_pin_fails_on_a_broken_copy(self):
        breaks = [("module only", 'version = ComposeVersion(module, values.count("launcher_letter") ? values.at("launcher_letter") : "");',
                   "version = module;"),
                  ("old reply", "VersionReply(version, module, schema,", "VersionReply(module, module, schema,"),
                  ("no version in log", "[DC version] version={}", "[DC version] module={}"),
                  ("old text", "handler->SendSysMessage(VersionReply(", 'handler->SendSysMessage("Torment version: module {}"); (VersionReply('),
                  ("no stop on a refusal", "World::StopNow(ERROR_EXIT_CODE)", "(void)ERROR_EXIT_CODE"),
                  ("only module migrations", "state IN ('MODULE','RELEASED')", "state IN ('MODULE')"),
                  ("a mismatch blocks", "mismatch never blocks login", "mismatch blocks login"),
                  ("the client's patch alone", "std::max(clientPatch, PublishedPatch())", "clientPatch")]
        for name, old, new in breaks:
            self.assertEqual(self.cpp.count(old), 1, name)
            self.assertTrue(any(not ok for _, ok in self.pins(self.cpp.replace(old, new))), name + " survived")

    def test_the_conf_and_the_contract_name_the_mismatch_message(self):
        def problems(conf, contract):
            out = [] if "Diablocraft.ClientMismatchMessage" in conf else ["the conf has no ClientMismatchMessage"]
            return out + ["the contract has no " + field for field in ("client_patch", "server_client_patch", "addon", "mismatch",
                                                                         "Diablocraft.ClientMismatchMessage") if field not in contract]
        conf, contract = CONF.read_text(encoding="utf-8"), CONTRACT.read_text(encoding="utf-8")
        self.assertEqual(problems(conf, contract), [])
        self.assertTrue(problems(conf.replace("Diablocraft.ClientMismatchMessage", "Diablocraft.Other"), contract))
        for field in ("client_patch", "server_client_patch", "addon", "mismatch"):
            self.assertTrue(problems(conf, contract.replace(field, "x" * len(field))), field)


if __name__ == "__main__":
    unittest.main(verbosity=2)
