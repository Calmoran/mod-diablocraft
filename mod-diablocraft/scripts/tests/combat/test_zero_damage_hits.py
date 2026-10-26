"""A hit that deals nothing procs nothing (diablocraft-wmdzd): the on-hit hooks wait for damage at every site that calls them.

The bug: an engine cast whose strike deals 0 (a trap's placement, a summon's cast, a buff aimed at enemies by the sheet: every class seam whose
BasePct is 0) skipped the damage, the class hooks and Connected, but ResolveHit still called Passives::Hit, so the legendary gems' on-hit effects
(Toxin, Gogok of Swiftness, Bane of the Stricken), the item powers' hit events and the Barbarian's on-hit passives fired on it. D3: a cast that hits nothing
for damage procs nothing.

What this proves, and how (source-text guards: the engine needs the core to run):

  * **Every site that calls Passives::Hit is behind a positive-damage check.** ResolveHit calls it inside the block `if (hit.total > 0)` that holds the class
    Landed hooks; the channel tick, Strike, the Barbarian's primaries and Whirlwind already skipped a hit of no damage before it. The number of call sites is
    pinned, so a new one is added knowingly, with its own guard.
  * **Planted differences fail.** The guard removed, moved out of the block, or made `>= 0`, in a scratch copy of each site, must fail the same checks.

What it does not prove: anything on a running server; the in-game steps are docs/test-diablocraft-wmdzd.md.

    python mod-diablocraft/scripts/tests/combat/test_zero_damage_hits.py
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
RESOLVE = SRC / "combat/dc_combat_resolve.cpp"
PRIMARIES = SRC / "classes/barbarian/dc_barbarian_primaries.cpp"
WHIRLWIND = SRC / "classes/barbarian/dc_barbarian_whirlwind.cpp"
CALL = re.compile(r"Passives::Hit\s*\(")


def squash(text):
    return re.sub(r"\s+", "", re.sub(r"//[^\n]*", "", text))


def resolve_hit_failures(text):
    """What is wrong with ResolveHit's on-hit call ([] when it is right)."""
    flat = squash(text)
    start = flat.find("boolResolveHit(Player*player,Unit*target,Shellconst&shell,SpellInfoconst*info){")
    end = flat.find("return hit.total>0;}", start) if False else flat.find("returnhit.total>0;}", start)
    body = flat[start:end] if start >= 0 and end > start else ""
    wrong = []
    if not body:
        return ["ResolveHit is not where it was"]
    block = body.find("DealHit(player,target,shell.spellId,hit);if(hit.total>0){")
    if block < 0:
        wrong.append("the class hooks are not behind `if (hit.total > 0)` after the damage is dealt")
        return wrong
    inside = body[block + len("DealHit(player,target,shell.spellId,hit);if(hit.total>0){"):]
    inside = inside[:inside.find("}")]
    if "Passives::Hit(player,target,shell.spellId,hit.school);" not in inside:
        wrong.append("Passives::Hit is not inside the positive-damage block")
    if inside.count("Landed(") != 8:
        wrong.append("the block no longer holds the class Landed hooks it was found by")
    if body.count("Passives::Hit(") != 1:
        wrong.append("ResolveHit calls Passives::Hit more than once or outside the block")
    return wrong


def other_sites_failures(resolve, primaries, whirlwind):
    wrong = []
    flat = squash(resolve)
    # the channel tick: a hit of no damage is skipped before the hooks
    tick = flat.find("DealHit(player,target,channel.spellId,hit);if(hit.total<=0)continue;")
    if tick < 0 or flat.find("Passives::Hit(player,target,channel.spellId,hit.school);", tick) < 0:
        wrong.append("the channel tick's on-hit call is not behind `if (hit.total <= 0) continue;`")
    # Strike: a hit of no damage returns before the hooks
    strike = flat.find("DealHit(player,target,spellId,hit);if(hit.total<=0)returnfalse;")
    if strike < 0 or flat.find("Passives::Hit(player,target,spellId,hit.school);", strike) < 0:
        wrong.append("Strike's on-hit call is not behind `if (hit.total <= 0) return false;`")
    if "if(GetHitDamage()>0)Passives::Hit(player,target,GetSpellInfo()->Id,hit.school);" not in squash(primaries):
        wrong.append("the Barbarian's primaries call the on-hit hook without checking the damage")
    flat_whirl = squash(whirlwind)
    at = flat_whirl.find("DealHit(p,target,row->id,hit);if(hit.total<=0)continue;")
    if at < 0 or flat_whirl.find("Passives::Hit(p,target,row->id,hit.school);", at) < 0:
        wrong.append("Whirlwind's on-hit call is not behind `if (hit.total <= 0) continue;`")
    return wrong


class Guards(unittest.TestCase):
    def test_resolve_hit_calls_the_hook_only_for_damage(self):
        self.assertEqual([], resolve_hit_failures(RESOLVE.read_text(encoding="utf-8")))

    def test_the_other_sites_skip_a_hit_of_no_damage(self):
        self.assertEqual([], other_sites_failures(*(p.read_text(encoding="utf-8") for p in (RESOLVE, PRIMARIES, WHIRLWIND))))

    def test_the_call_sites_are_the_five_known(self):
        sites = {}
        for path in SRC.rglob("*.cpp"):
            if path.name == "dc_passives.cpp":
                continue
            count = len(CALL.findall(path.read_text(encoding="utf-8")))
            if count:
                sites[path.name] = count
        self.assertEqual({"dc_combat_resolve.cpp": 3, "dc_barbarian_primaries.cpp": 1, "dc_barbarian_whirlwind.cpp": 1}, sites,
                         "a new call of Passives::Hit needs its own positive-damage guard and a line in this test")

    def test_the_mutants_fail(self):
        real = RESOLVE.read_text(encoding="utf-8")
        mutants = {
            "the_call_is_unguarded_again": ("                Passives::Hit(player,target,shell.spellId,hit.school);\n            }\n            Abilities::HitEffects",
                                            "            }\n            Passives::Hit(player, target, shell.spellId, hit.school);\n            Abilities::HitEffects"),
            "the_guard_lets_zero_through": ("            DealHit(player, target, shell.spellId, hit);\n            if (hit.total > 0)\n            {\n                GainPerEnemyHit",
                                            "            DealHit(player, target, shell.spellId, hit);\n            if (hit.total >= 0)\n            {\n                GainPerEnemyHit"),
            "the_call_is_dropped": ("                Passives::Hit(player,target,shell.spellId,hit.school);\n            }\n            Abilities::HitEffects", "            }\n            Abilities::HitEffects"),
            "the_call_is_twice": ("                Passives::Hit(player,target,shell.spellId,hit.school);\n            }\n            Abilities::HitEffects",
                                  "                Passives::Hit(player,target,shell.spellId,hit.school);\n            }\n            Passives::Hit(player, target, shell.spellId, hit.school);\n            Abilities::HitEffects"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                self.assertNotEqual([], resolve_hit_failures(real.replace(old, new, 1)), name + " survived")
        other = {
            "the_tick_hook_ignores_damage": ("                DealHit(player, target, channel.spellId, hit);\n                if (hit.total <= 0)\n                    continue;", "                DealHit(player, target, channel.spellId, hit);"),
            "strike_hooks_ignore_damage": ("        DealHit(player, target, spellId, hit);\n        if (hit.total <= 0)\n            return false;", "        DealHit(player, target, spellId, hit);"),
        }
        for name, (old, new) in other.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                self.assertNotEqual([], other_sites_failures(real.replace(old, new, 1), PRIMARIES.read_text(encoding="utf-8"), WHIRLWIND.read_text(encoding="utf-8")), name + " survived")
        primaries, whirlwind = PRIMARIES.read_text(encoding="utf-8"), WHIRLWIND.read_text(encoding="utf-8")
        old = "if(GetHitDamage()>0)Passives::Hit("
        self.assertEqual(1, primaries.count(old))
        self.assertNotEqual([], other_sites_failures(real, primaries.replace(old, "Passives::Hit(", 1), whirlwind), "primaries survived")
        old = "if(hit.total<=0)continue;\n                        connected=true;\n                        Passives::Hit("
        self.assertEqual(1, whirlwind.count(old))
        self.assertNotEqual([], other_sites_failures(real, primaries, whirlwind.replace(old, "connected=true;\n                        Passives::Hit(", 1)), "whirlwind survived")


if __name__ == "__main__":
    unittest.main()
