"""Class powers P0: class_resources.csv is the one source of each class's power, and the three things generated from it
agree with it and with each other (docs/contracts/class-powers.md).

    python3 mod-diablocraft/scripts/tests/classes/test_class_powers.py

Cross-source: the expected rows are read here from data/d3/class_resources.csv, data/tunables/class_resources.csv and
data/d3/class_map.csv, never from the generator; each output is parsed from the committed file:

  * src/classes/dc_resource_data.h (the server): class, key, name, role, slot, pool, regeneration, decay, colour, token;
  * client-patch/addons/Torment/ResourceNames.lua (the client patch): the per-class rows' token, name, colour and slot,
    and Diablocraft.PowerTokens: one entry per token with its name, colour (hex and the 0-1 floats) and slot;
  * mod-diablocraft/data/generated/class_power_tokens.h (the rebuilt client's engine): compiled with the host compiler
    and driven: TokenFor(WoW class, slot) returns the row's token for every live row, and nullptr for an unused slot of
    a live class and for a stock class no row names (the Rogue's Energy, the Warlock's Mana); UnitsPerPointFor gives
    each live row's storage_scale (what the engine divides the slot by for display in place of the stock tenth on Rage
    and Runic Power) and 0 for every class and slot without a row (the stock divide stays).

The true number (class powers P2, Essence): a full Necromancer bar is 200 slot units, and the slot divided by the
engine's units per point reads 200 (not the stock divide's 20), while the Monk's Spirit on the same slot still reads
its 250 from 2500.

The Demon Hunter's two (class powers P2, diablocraft-a52dy), read from the sheets: Hatred, the primary, on Energy and
Discipline, the second, in Focus (decisions.md 2026-10-16), both paid by the module and starting full, with D3's pools and
rates; no other class is in Focus; and the engine header the class will get (rendered with its class_map.csv row
planted: the Hunter, class 3) names HATRED on Energy and DISCIPLINE in Focus at one unit a point.

Then the committed files are what the generator renders, and planted sheet changes are refused (a token twice, another
slot's stock token, a token that is not UPPER_SNAKE) or change every output (a renamed token, a new colour).
What it does not prove: the client showing the token or the number (P1, the engine, reads the header; P3, the UI).
"""
import csv
import io
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
MODULE = HERE.parents[3]
ROOT = MODULE.parent
sys.path.insert(0, str(MODULE / "scripts"))
import harness_env  # noqa: E402

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_class_resources as gcr  # noqa: E402

D3 = MODULE / "data/d3"
TUNABLES = MODULE / "data/tunables"
HEADER = MODULE / "src/classes/dc_resource_data.h"
LUA = ROOT / "client-patch/addons/Torment/ResourceNames.lua"
ENGINE = MODULE / "data/generated/class_power_tokens.h"
SLOTS = {"Mana": 0, "Rage": 1, "Focus": 2, "Energy": 3, "Happiness": 4, "Rune": 5, "Runic Power": 6}


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def expected():
    """The live rows, from the sheets: (d3 class, key) -> what every output must say."""
    class_map = {r["d3_class"]: r for r in read(D3 / "class_map.csv")}
    torment = {(r["d3_class"], r["resource_key"]): r for r in read(TUNABLES / "class_resources.csv")}
    out = {}
    for row in read(D3 / "class_resources.csv"):
        key = (row["d3_class"], row["resource_key"])
        if row["d3_class"] not in class_map:
            continue
        choice, mapped = torment[key], class_map[row["d3_class"]]
        out[key] = {"class_id": int(mapped["class_id"]), "wow_class_id": int(mapped["wow_class_id"]),
                    "name": row["d3_name"], "role": row["role"], "slot": SLOTS[choice["wow_power"]],
                    "pool": float(row["pool"]), "regen": float(row["regen_per_second"]), "decay": choice["decay"],
                    "colour": choice["display_colour"][1:], "token": choice["token"],
                    "module_paid": choice["paid_by"] == "module", "scale": int(choice["storage_scale"])}
    return out


# Stock classes no D3 class takes (the Rogue's Energy, the Warlock's Mana): their slots keep the stock token.
STOCK_SLOTS = [(4, 3), (9, 0)]


def server_rows():
    pattern = re.compile(r'^    \{(\d+), "([^"]+)", "([^"]+)", "([^"]+)", Role::(\w+), (\d+), "[^"]+", ([\d.]+), ([\d.]+), '
                         r'([\d.]+), Decay::(\w+), 0x([0-9A-F]{6}), [\d.]+, (?:true|false), "([A-Z_]+)", '
                         r'(true|false)\},$', re.M)
    return {(m[1], m[2]): {"class_id": int(m[0]), "name": m[3], "role": m[4].lower(), "slot": int(m[5]),
                           "pool": float(m[7]), "regen": float(m[8]), "decay": m[9].lower(), "colour": m[10],
                           "token": m[11], "module_paid": m[12] == "true"}
            for m in pattern.findall(HEADER.read_text(encoding="utf-8"))}


def lua_tables():
    text = LUA.read_text(encoding="utf-8")
    names, tokens = text.split("Diablocraft.PowerTokens = {")
    per_class = {m[4]: {"token": m[5], "name": m[0], "colour": m[1], "slot": int(m[2]), "role": m[3]}
                 for m in re.findall(r'= \{ name = "([^"]+)", colour = "([0-9A-F]{6})", power = (\d), role = "(\w+)", '
                                     r'key = "(\w+)", class = "[^"]+", token = "([A-Z_]+)" \},', names)}
    by_token = {m[0]: {"name": m[1], "colour": m[2], "rgb": tuple(float(v) for v in m[3:6]), "slot": int(m[6])}
                for m in re.findall(r'^    ([A-Z_]+) = \{ name = "([^"]+)", colour = "([0-9A-F]{6})", r = ([\d.]+), '
                                    r'g = ([\d.]+), b = ([\d.]+), power = (\d) \},$', tokens, re.M)}
    return per_class, by_token


def drive_engine(header_text, queries):
    """Compile the engine header with the host compiler and ask each (class, slot): 'TOKEN:units', '-' for a nullptr
    token, units from UnitsPerPointFor."""
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler on this host")
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        (work / "class_power_tokens.h").write_text(header_text, encoding="utf-8")
        (work / "main.cpp").write_text("\n".join([
            "#include <cstdio>",
            "#include <cstdlib>",
            '#include "class_power_tokens.h"',
            "int main(int argc, char** argv)",
            "{",
            "    for (int i = 1; i + 1 < argc; i += 2)",
            "    {",
            "        const char* token = TormentPowers::TokenFor(std::atoi(argv[i]), std::atoi(argv[i + 1]));",
            '        std::printf("%s:%u\\n", token ? token : "-", TormentPowers::UnitsPerPointFor(std::atoi(argv[i]), std::atoi(argv[i + 1])));',
            "    }",
            "    return 0;",
            "}",
            ""]), encoding="utf-8")
        subprocess.run([compiler, "-std=c++17", "-Wall", "-Werror", "-o", str(work / "drive"), str(work / "main.cpp")],
                       check=True, capture_output=True)
        args = [str(v) for query in queries for v in query]
        ran = harness_env.run([str(work / "drive"), *args], capture_output=True, text=True)
        ran.check_returncode()
        return ran.stdout.split()


class Outputs(unittest.TestCase):
    def setUp(self):
        self.want = expected()

    def test_the_sheet_names_a_token_for_every_row(self):
        tokens = [r["token"] for r in read(TUNABLES / "class_resources.csv")]
        self.assertEqual(tokens, ["FURY", "ARCANE_POWER", "WRATH", "HATRED", "DISCIPLINE", "SPIRIT", "ESSENCE", "MANA", "MAELSTROM"])
        self.assertEqual(len(set(tokens)), len(tokens))

    def test_the_server_header_is_the_sheet(self):
        got = server_rows()
        self.assertEqual(set(got), set(self.want))
        for key, row in self.want.items():
            self.assertEqual(got[key], {k: row[k] for k in got[key]}, key)

    def test_the_client_lua_is_the_sheet(self):
        per_class, by_token = lua_tables()
        self.assertEqual(set(per_class), {key for _, key in self.want})
        self.assertEqual(set(by_token), {row["token"] for row in self.want.values()})
        for (_, key), row in self.want.items():
            self.assertEqual(per_class[key], {k: row[k] for k in per_class[key]}, key)
            entry = by_token[row["token"]]
            self.assertEqual((entry["name"], entry["colour"], entry["slot"]), (row["name"], row["colour"], row["slot"]))
            rgb = tuple(int(row["colour"][i:i + 2], 16) / 255 for i in (0, 2, 4))
            for have, wanted in zip(entry["rgb"], rgb):
                self.assertAlmostEqual(have, wanted, delta=0.0006)

    def test_the_engine_header_answers_each_live_row_and_nothing_else(self):
        rows = list(self.want.values())
        live_ids = {row["wow_class_id"] for row in rows}
        unused = [(row["wow_class_id"], slot) for row in rows for slot in SLOTS.values()
                  if not any(r["wow_class_id"] == row["wow_class_id"] and r["slot"] == slot for r in rows)]
        stock = [(c, s) for c, s in STOCK_SLOTS if c not in live_ids]
        queries = [(row["wow_class_id"], row["slot"]) for row in rows] + unused[:3] + stock
        answers = drive_engine(ENGINE.read_text(encoding="utf-8"), queries)
        self.assertEqual(answers[:len(rows)], ["%s:%d" % (row["token"], row["scale"]) for row in rows])
        self.assertEqual(set(answers[len(rows):]), {"-:0"})

    def test_a_full_bar_shows_its_true_number(self):
        """Every power one unit a point (class powers P2, the x10 convention retired): a full bar holds its pool in slot
        units and the engine's divisor is 1, so it shows the pool; the stock divide on Rage and Runic Power would show
        a tenth (Fury 10, Spirit 25, Essence 20)."""
        rows = {key[1]: row for key, row in self.want.items()}
        keys = sorted(rows)
        units = [int(a.split(":")[1]) for a in
                 drive_engine(ENGINE.read_text(encoding="utf-8"), [(rows[k]["wow_class_id"], rows[k]["slot"]) for k in keys])]
        self.assertEqual(units, [1] * len(keys), "a power stored at other than one unit a point")
        stored = {k: rows[k]["pool"] * rows[k]["scale"] for k in ("fury", "spirit", "essence")}
        self.assertEqual(stored, {"fury": 100, "spirit": 250, "essence": 200})
        self.assertEqual({k: v // 10 for k, v in stored.items()}, {"fury": 10, "spirit": 25, "essence": 20},
                         "the stock divide the engine replaces")

    def test_the_rebuilt_client_s_row_pattern_still_reads_the_token_table(self):
        """P1's own test (client-extension/tests/test_class_power_tokens.py) reads ClassPowerTokens with this pattern;
        the units table beside it must not match it."""
        text = ENGINE.read_text(encoding="utf-8")
        found = re.findall(r'\{(\d+), (\d+), "([A-Z_]+)"\}', text)
        self.assertEqual(sorted(found), sorted((str(r["wow_class_id"]), str(r["slot"]), r["token"]) for r in self.want.values()))

    def test_the_committed_files_are_the_render(self):
        entries = gcr.registry()
        self.assertEqual(HEADER.read_text(encoding="utf-8"), gcr.render(entries))
        self.assertEqual(LUA.read_text(encoding="utf-8"), gcr.render_names(entries))
        self.assertEqual(ENGINE.read_text(encoding="utf-8"), gcr.render_engine(entries))


class Planted(unittest.TestCase):
    """Each plant edits a copy of the Torment sheet and runs the generator's reader over it."""

    def with_sheet(self, change):
        text = (TUNABLES / "class_resources.csv").read_text(encoding="utf-8")
        planted = change(text)
        self.assertNotEqual(planted, text, "the plant did not apply")
        work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, work)
        (work / "class_resources.csv").write_text(planted, encoding="utf-8")
        saved = gcr.TUNABLES
        gcr.TUNABLES = work
        try:
            return gcr.rows(include_planned=True)
        finally:
            gcr.TUNABLES = saved

    def refused(self, change, words):
        with self.assertRaises(SystemExit) as caught:
            self.with_sheet(change)
        self.assertIn(words, str(caught.exception))

    def test_a_token_twice_is_refused(self):
        self.refused(lambda t: t.replace(",Runic Power,ESSENCE,", ",Runic Power,SPIRIT,"), "one token is one power")

    def test_another_slots_stock_token_is_refused(self):
        self.refused(lambda t: t.replace(",Energy,WRATH,", ",Energy,MANA,"), "another slot's stock token")

    def test_core_paying_rage_or_runic_power_is_refused(self):
        self.refused(lambda t: t.replace(",Runic Power,ESSENCE,1,none,module,", ",Runic Power,ESSENCE,1,none,core,"),
                     "it is the module's")

    def test_a_live_row_without_a_payer_is_refused(self):
        self.refused(lambda t: t.replace(",WRATH,1,none,module,", ",WRATH,1,none,,"), "needs paid_by module or core")

    def test_an_unknown_payer_is_refused(self):
        self.refused(lambda t: t.replace(",WRATH,1,none,module,", ",WRATH,1,none,server,"), "paid_by 'server'")

    def test_a_token_that_is_not_upper_snake_is_refused(self):
        self.refused(lambda t: t.replace(",Energy,WRATH,", ",Energy,Wrath,"), "UPPER_SNAKE_CASE")

    def test_a_renamed_token_changes_every_output(self):
        entries = [e for e in self.with_sheet(lambda t: t.replace(",Runic Power,ESSENCE,", ",Runic Power,SOULS,"))
                   if e["live"]]
        for render, path in ((gcr.render, HEADER), (gcr.render_names, LUA), (gcr.render_engine, ENGINE)):
            text = render(entries)
            self.assertIn("SOULS", text, path.name)
            self.assertNotIn('"ESSENCE"', text, path.name)

    def test_core_paying_focus_is_refused(self):
        self.refused(lambda t: t.replace(",Focus,DISCIPLINE,1,none,module,", ",Focus,DISCIPLINE,1,none,core,"),
                     "it is the module's")

    def test_a_regenerating_row_no_one_pays_on_a_slot_without_a_stock_gain_is_refused(self):
        self.refused(lambda t: t.replace(",Focus,DISCIPLINE,1,none,module,", ",Focus,DISCIPLINE,1,none,,"),
                     "no stock path refills Focus")

    def test_a_new_colour_changes_the_server_and_the_lua(self):
        entries = [e for e in self.with_sheet(lambda t: t.replace("#2EA78F", "#123456")) if e["live"]]
        self.assertIn("0x123456", gcr.render(entries))
        self.assertIn('colour = "123456", r = 0.071, g = 0.204, b = 0.337', gcr.render_names(entries))


class DemonHunter(unittest.TestCase):
    CLASS = "Demon Hunter"
    PLANTED = {"d3_class": CLASS, "wow_class": "Hunter", "wow_power_type": "Energy", "primary_stat": "Dexterity",
               "class_id": "6", "wow_class_id": "3"}

    def test_the_two_powers_from_the_sheets(self):
        d3 = {r["resource_key"]: r for r in read(D3 / "class_resources.csv") if r["d3_class"] == self.CLASS}
        torment = {r["resource_key"]: r for r in read(TUNABLES / "class_resources.csv") if r["d3_class"] == self.CLASS}
        self.assertEqual({k: (d3[k]["role"], d3[k]["pool"], d3[k]["regen_per_second"], d3[k]["decays_out_of_combat"])
                          for k in d3},
                         {"hatred": ("primary", "125", "5", "0"), "discipline": ("second", "30", "1", "0")})
        self.assertEqual({k: (r["wow_power"], r["token"], r["storage_scale"], r["decay"], r["paid_by"], r["starts_full"])
                          for k, r in torment.items()},
                         {"hatred": ("Energy", "HATRED", "1", "none", "module", "1"),
                          "discipline": ("Focus", "DISCIPLINE", "1", "none", "module", "1")})
        others = [r["d3_class"] for r in read(TUNABLES / "class_resources.csv")
                  if r["wow_power"] == "Focus" and r["d3_class"] != self.CLASS]
        self.assertEqual(others, [], "another class in Focus")
        entries = {e["key"]: e for e in gcr.rows(include_planned=True) if e["d3_class"] == self.CLASS}
        self.assertEqual({k: (e["power_id"], e["role"], e["pool"], e["regen"], e["paid_by"], e["starts_full"])
                          for k, e in entries.items()},
                         {"hatred": (SLOTS["Energy"], "primary", 125.0, 5.0, "module", True),
                          "discipline": (SLOTS["Focus"], "second", 30.0, 1.0, "module", True)})

    def test_the_engine_names_both_once_the_class_is_live(self):
        real = gcr.read

        def planted(path):
            rows = real(path)
            return rows + [dict(self.PLANTED)] if path.name == "class_map.csv" else rows

        gcr.read = planted
        try:
            entries = gcr.registry()
        finally:
            gcr.read = real
        engine = gcr.render_engine(entries)
        for line in ('{3, 3, "HATRED"}', '{3, 2, "DISCIPLINE"}', "{3, 3, 1}", "{3, 2, 1}"):
            self.assertIn(line, engine)
        self.assertNotIn("{3, 0,", engine, "the Demon Hunter is on Mana")
        server = gcr.render(entries)
        self.assertIn('{6, "Demon Hunter", "discipline", "Discipline", Role::Second, 2, "Focus", 1.0, 30.0, 1.0,', server)


if __name__ == "__main__":
    unittest.main()
