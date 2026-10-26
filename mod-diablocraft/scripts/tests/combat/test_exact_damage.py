"""Native 64-bit health Part 2, the Combat cutover (diablocraft-dxpy): every damage producer writes the exact hit, and BigLife is gone.

The core holds Life and hits in 64 bits (core patches 0027 and 0028), so the module no longer converts a hit to 32 bits, keeps a receipt of what it cut, or tells an
addon about it. What this proves, and how:

  * **The rules that need no core type.** tests/exact_damage/harness.cpp compiles the real src/combat/dc_exact_damage.h: a hit is the formula's amount dropped to a whole
    number, nothing for an amount that is not above 0, the largest 64-bit number past 2^64, and nothing is cut at 2^32; the GM's dev multiplier (`.dc dmgmult`) multiplies a
    hit by a finite number above 0 and changes nothing otherwise. Planted differences in a scratch copy of the header must each make the driver fail.
  * **The producers.** The source of each one is read: DealHit, the Barbarian primaries' provider, the Rend tick's provider and the Ancients' blow each boost by the GM's multiplier,
    make the hit whole with ExactDamage and hand the 64-bit amount over (the provider overrides take the core's `uint64&` and write it back), and `cleanDamage`, the one
    32-bit field of the log, takes the saturating cast. Planted differences in the text must each fail the guards.
  * **The commands.** `.dc biglife <Life>` gives the selected creature that real max Life through the core's `SetBaseHealth`, `UpdateMaxHealth` and `SetFullHealth`; `.dc dmgmult`
    keeps its rules and its logout cleanup.
  * **What is gone.** BigLife's math, hook, receipts, wire and addon, and the four wire tunables, are deleted, and a test fails if one comes back. The Combat lane's files are held
    to it always; the whole tree is held to it too, once the World cutover (diablocraft-88i0) has taken its own callers out.

What it does not prove: anything on a running server. The compile against the patched core, and the checks on dev with the rebuilt client, are docs/test-diablocraft-dxpy.md's.

    python mod-diablocraft/scripts/tests/combat/test_exact_damage.py
"""
import csv
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import generate_tunables as tunables  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
HEADER = SRC / "combat/dc_exact_damage.h"
HARNESS = MODULE / "tests/exact_damage/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
MAX64 = 18446744073709551615


def cases():
    out = []
    for amount, want in ((0, 0), (-5, 0), ("nan", 0), ("-inf", 0), (0.9, 0), (1, 1), (199.99, 199), (4294967294, 4294967294), (4294967295, 4294967295), (4294967296, 4294967296),
                         (10000000000, 10000000000), (5e12, 5000000000000), (9007199254740992, 9007199254740992), (1.8446744073709550e19, 18446744073709549568),
                         (18446744073709551616.0, MAX64), (1e20, MAX64), ("inf", MAX64)):
        out.append((T("exact", amount), str(want)))
    for amount, mult, want in ((100, 1, "100"), (100, 2.5, "250"), (1e9, 10, "1e+10"), (100, 0, "100"), (100, -3, "100"), (100, "nan", "100"), (100, "inf", "100"), (100, "-inf", "100"),
                               (0, 5, "0"), (250, 0.5, "125")):
        out.append((T("boosted", amount, mult), want))
    return out


def drive(header_text, name="real"):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files={"combat/dc_exact_damage.h": header_text})
    work = Path(tempfile.mkdtemp(prefix="exactdamage-%s-" % name, dir=str(SCRATCH)))
    try:
        lines = cases()
        (work / "cases.txt").write_text("\n".join(line for line, _ in lines) + "\n")
        run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        return [want for _, want in lines], run.stdout.split("\n")[:-1]
    finally:
        shutil.rmtree(work, ignore_errors=True)


class Rules(unittest.TestCase):
    def test_every_rule_agrees_with_the_meaning(self):
        want, got = drive(HEADER.read_text(encoding="utf-8"))
        self.assertGreater(len(want), 25)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = HEADER.read_text(encoding="utf-8")
        want, _ = drive(real)
        mutants = {
            "a_negative_hit_wraps": ("if (!(amount > 0))", "if (amount == 0)"),
            "nan_is_a_hit": ("if (!(amount > 0))\n            return 0;\n        if (amount >=", "if (amount <= 0)\n            return 0;\n        if (amount >="),
            "no_ceiling": ("        if (amount >= 18446744073709551616.0)\n            return std::numeric_limits<std::uint64_t>::max();\n", ""),
            "the_ceiling_is_32_bits": ("if (amount >= 18446744073709551616.0)", "if (amount >= 4294967296.0)"),
            "a_hit_is_rounded": ("return static_cast<std::uint64_t>(amount);", "return static_cast<std::uint64_t>(amount + 0.5);"),
            "a_hit_is_cut_to_32_bits": ("return static_cast<std::uint64_t>(amount);", "return static_cast<std::uint32_t>(amount);"),
            "zero_multiplier_zeroes_the_hit": ("return mult > 0 && std::isfinite(mult) ? amount * mult : amount;", "return std::isfinite(mult) ? amount * mult : amount;"),
            "an_infinite_multiplier_passes": ("return mult > 0 && std::isfinite(mult) ? amount * mult : amount;", "return mult > 0 ? amount * mult : amount;"),
            "the_multiplier_is_ignored": ("return mult > 0 && std::isfinite(mult) ? amount * mult : amount;", "return amount;"),
            "the_multiplier_adds": ("amount * mult : amount;", "amount + mult : amount;"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                _, got = drive(real.replace(old, new, 1), name)
                self.assertNotEqual(want, got, name + " survived")


def squeeze(text):
    return re.sub(r"\s+", " ", re.sub(r"//[^\n]*", "", text))


def problems(files):
    """What is wrong with the producers and the commands in `files` ({key: source text}); [] when they are right."""
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    combat = squeeze(files["combat"])
    hit = combat[combat.index("void DealHit(Player* player, Unit* target, std::uint32_t spellId, Hit const& hit, bool fixed)"):]
    hit = hit[:hit.index("ClearPreCritHit(player); }")]
    need("DealHit boosts the hit by the GM's multiplier", "double const adjusted = DevBoost(player, fixed ? hit.total : VictimAdjustedTotal(player, target, hit));" in hit)
    need("DealHit makes it whole in 64 bits", "log.damage = ExactDamage(adjusted);" in hit)
    need("the log's one 32-bit field takes the saturating cast", "log.cleanDamage = LifeToUInt32(log.damage);" in hit)
    need("DealHit boosts, makes whole, then logs and deals", hit.find("DevBoost(") < hit.find("ExactDamage(") < hit.find("SendSpellNonMeleeDamageLog") < hit.find("DealSpellDamage"))
    need("DealHit leaves no receipt to clear", "ClearTrueDamage" not in combat)
    need("the life commands are registered with the combat's", "RegisterLifeCommands();" in combat)
    primaries = squeeze(files["primaries"])
    need("the provider works on the core's 64-bit hit", "uint64& damage = damage64;" in primaries and "uint64& damage64, bool& critical) override" in primaries)
    need("the provider boosts and makes the hit whole", "hit.total = DevBoost(player, hit.total); damage = ExactDamage(hit.total);" in primaries)
    need("the provider keeps no 32-bit handover", not any(word in primaries for word in ("Handover", "uint32 damage =", "LifeToUInt32")))
    rend = squeeze(files["rend"])
    need("the Rend tick is 64 bits end to end", "bool FinalTick(AuraEffect const* effect, Unit* caster, Unit* target, uint64& damage, bool& critical)" in rend and
         "uint64& damage = damage64;" in rend)
    need("the Rend tick is boosted and made whole", "double const adjusted = DevBoost(player, VictimAdjustedTotal(player, target, tick)); damage = ExactDamage(adjusted);" in rend)
    need("the Rend provider keeps no 32-bit handover", not any(word in rend for word in ("Handover", "LifeToUInt32")))
    ancients = squeeze(files["ancients"])
    need("the Ancients' blow is boosted and made whole",
         "hit.total = Combat::DevBoost(p, hit.total); log.damage = Combat::ExactDamage(hit.total); log.cleanDamage = LifeToUInt32(log.damage);" in ancients)
    for key, text in (("combat", combat), ("primaries", primaries), ("rend", rend), ("ancients", ancients)):
        need("%s has no BigLife, clamp or receipt left" % key, not any(word in text for word in ("BigLife", "Clamp(target", "NoteTrueDamage", "ClearTrueDamage", "dc_big_life")))
    commands = squeeze(files["commands"])
    big = commands[commands.index("static bool HandleMaxLife("):]
    big = big[:big.index("handler->PSendSysMessage(\"Life {} / {}.\"")]
    need("`.dc biglife` gives the creature its real max Life, whole", "creature->SetBaseHealth(*life); creature->UpdateMaxHealth(); creature->ResetPlayerDamageReq(); creature->SetFullHealth();" in big)
    need("`.dc biglife` refuses a Life of 0", "if (!*life) {" in big and "A Life above 0." in big)
    need("`.dc biglife` knows no 1,000,000,000 line", "1000000000" not in commands and "CORE_MAX" not in commands)
    logout = commands[commands.index("class DevMultLogout"):]
    logout = logout[:logout.index("} }")]
    need("`.dc dmgmult` goes at logout", "devMult.erase(player->GetGUID().GetRawValue());" in logout and "PLAYERHOOK_ON_LOGOUT" in logout)
    need("the boost is the header's rule", "return Boosted(amount, DevMultiplier(dealer));" in commands)
    return wrong


def sources():
    return {"combat": (SRC / "combat/dc_combat.cpp").read_text(encoding="utf-8"),
            "primaries": (SRC / "classes/barbarian/dc_barbarian_primaries.cpp").read_text(encoding="utf-8"),
            "rend": (SRC / "classes/barbarian/dc_barbarian_rend.cpp").read_text(encoding="utf-8"),
            "ancients": (SRC / "classes/barbarian/dc_barbarian_call_of_the_ancients.cpp").read_text(encoding="utf-8"),
            "commands": (SRC / "combat/dc_life_commands.cpp").read_text(encoding="utf-8")}


class Producers(unittest.TestCase):
    def test_every_producer_writes_the_exact_hit(self):
        self.assertEqual([], problems(sources()))

    def test_the_source_guards_fail_their_mutants(self):
        mutants = [
            ("combat", "not_boosted", "double const adjusted = DevBoost(player, fixed ?", "double const adjusted = (player, fixed ?"),
            ("combat", "cut_to_32_bits", "log.damage = ExactDamage(adjusted);", "log.damage = uint32(adjusted);"),
            ("combat", "clean_damage_wraps", "log.cleanDamage = LifeToUInt32(log.damage);", "log.cleanDamage = uint32(log.damage);"),
            ("combat", "commands_not_registered", "RegisterLifeCommands();", ""),
            ("primaries", "provider_cut", "damage = ExactDamage(hit.total);", "damage = LifeToUInt32(ExactDamage(hit.total));"),
            ("primaries", "provider_not_boosted", "hit.total = DevBoost(player, hit.total);", ""),
            ("primaries", "provider_copy", "uint64& damage = damage64;", "uint32 damage = LifeToUInt32(damage64);"),
            ("rend", "tick_cut", "damage = ExactDamage(adjusted);", "damage = uint32(adjusted);"),
            ("rend", "tick_not_boosted", "double const adjusted = DevBoost(player, VictimAdjustedTotal(player, target, tick));", "double const adjusted = VictimAdjustedTotal(player, target, tick);"),
            ("rend", "tick_32_bit_signature", "Unit* target, uint64& damage, bool& critical)", "Unit* target, uint32& damage, bool& critical)"),
            ("ancients", "blow_cut", "log.damage = Combat::ExactDamage(hit.total);", "log.damage = uint32(hit.total);"),
            ("ancients", "blow_not_boosted", "hit.total = Combat::DevBoost(p, hit.total);", ""),
            ("commands", "biglife_not_whole", "creature->SetBaseHealth(*life);", "creature->SetMaxHealth(*life);"),
            ("commands", "biglife_not_full", "creature->SetFullHealth();", ""),
            ("commands", "biglife_zero", "if (!*life)", "if (false)"),
            ("commands", "dmgmult_stays_after_logout", "devMult.erase(player->GetGUID().GetRawValue());\n            }", "}"),
            ("commands", "boost_ignores_the_rule", "return Boosted(amount, DevMultiplier(dealer));", "return amount * DevMultiplier(dealer);"),
        ]
        files = sources()
        for which, name, old, new in mutants:
            with self.subTest(mutant=name):
                self.assertEqual(1, files[which].count(old), name + " does not apply")
                changed = {**files, which: files[which].replace(old, new, 1)}
                self.assertNotEqual([], problems(changed), name + " survived")

    def test_the_boost_and_the_hit_are_the_headers(self):
        text = (SRC / "combat/dc_life_commands.cpp").read_text(encoding="utf-8")
        self.assertIn('#include "dc_exact_damage.h"', text)
        for path in ("combat/dc_combat_internal.h", "classes/barbarian/dc_barbarian_primaries.cpp", "classes/barbarian/dc_barbarian_rend.cpp",
                     "classes/barbarian/dc_barbarian_call_of_the_ancients.cpp"):
            self.assertIn('dc_exact_damage.h"', (SRC / path).read_text(encoding="utf-8"), path)


BANNED = re.compile(r"BigLife|dc_big_life|NoteTrueDamage|ClearTrueDamage|TakeTrueDamage|DCBIGLIFE|BigLifeWire|BigLifeMath|TrueMax\(|TrueHealth\(|CORE_MAX")
COMBAT_LANE = ("combat", "stats", "classes", "items", "hardcore", "paragon")
ADDON_FILES = ("client-patch/addons/ElvUI_Torment/biglife.lua", "mod-diablocraft/src/combat/dc_big_life.h", "mod-diablocraft/src/combat/dc_big_life.cpp",
               "mod-diablocraft/src/combat/dc_big_life_wire.h", "mod-diablocraft/src/combat/dc_big_life_wire.cpp", "mod-diablocraft/src/common/dc_big_life.h",
               "mod-diablocraft/tests/big_life/harness.cpp", "mod-diablocraft/tests/big_life_wire/harness.cpp",
               "mod-diablocraft/scripts/tests/stats/test_big_life.py", "mod-diablocraft/scripts/tests/stats/test_big_life_wire.py",
               "mod-diablocraft/scripts/tests/ui/test_elvui_biglife.lua")
RETIRED_TUNABLES = ("big_life_pull_burst", "big_life_pull_per_second", "big_life_window_ms", "big_life_hit_messages_per_second")


def offenders(folders, base=SRC):
    out = []
    for folder in folders:
        for path in sorted((base / folder).rglob("*")):
            if path.suffix in (".cpp", ".h", ".hpp") and BANNED.search(path.read_text(encoding="utf-8", errors="replace")):
                out.append(path.relative_to(base).as_posix())
    return out


class Gone(unittest.TestCase):
    def test_the_files_are_deleted(self):
        self.assertEqual([], [p for p in ADDON_FILES if (REPO / p).exists()])

    def test_the_addon_no_longer_loads_it(self):
        toc = (REPO / "client-patch/addons/ElvUI_Torment/ElvUI_Torment.toc").read_text(encoding="utf-8")
        core = (REPO / "client-patch/addons/ElvUI_Torment/core.lua").read_text(encoding="utf-8")
        self.assertNotIn("biglife", toc.lower())
        self.assertNotIn("TrueLife", core)

    def test_the_wire_tunables_are_retired_and_nothing_reads_them(self):
        with (MODULE / "data/tunables/combat.csv").open(encoding="utf-8", newline="") as stream:
            rows = {r["name"] for r in csv.DictReader(stream)}
        self.assertEqual(set(), rows & set(RETIRED_TUNABLES))
        for name in RETIRED_TUNABLES:
            self.assertIn(("combat", name), tunables.RETIRED)
        for path in list(SRC.rglob("*.cpp")) + list(SRC.rglob("*.h")):
            text = path.read_text(encoding="utf-8", errors="replace")
            for name in RETIRED_TUNABLES:
                self.assertNotIn(name, text, path.name)

    def test_the_combat_lanes_files_name_none_of_it(self):
        self.assertEqual([], offenders(COMBAT_LANE))
        self.assertEqual([], [p for p in (SRC / "common").glob("*") if BANNED.search(p.read_text(encoding="utf-8", errors="replace")) and p.name != "dc_tiers.h"])

    def test_no_file_of_the_module_names_it(self):
        left = offenders(sorted(p.name for p in SRC.iterdir() if p.is_dir()))
        if left:
            self.skipTest("the World cutover (diablocraft-88i0) has not been merged: %s" % ", ".join(left))
        self.assertEqual([], left)

    def test_the_guard_finds_a_word_that_comes_back(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="exactdamage-gone-", dir=str(SCRATCH)))
        try:
            (work / "combat").mkdir()
            (work / "combat/clean.cpp").write_text("double x = ExactDamage(1.0);\n", encoding="utf-8")
            self.assertEqual([], offenders(("combat",), work))
            for word in ("BigLife::Clamp(target, 1.0)", "NoteTrueDamage(victim, 1)", "ClearTrueDamage()", "TrueMax(unit)", "DCBIGLIFE", "CORE_MAX", "dc_big_life.h"):
                (work / "combat/back.cpp").write_text("// " + word + "\n", encoding="utf-8")
                self.assertEqual(["combat/back.cpp"], offenders(("combat",), work), word)
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
