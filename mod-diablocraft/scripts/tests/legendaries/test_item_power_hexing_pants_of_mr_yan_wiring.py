"""The source-text guards of Hexing Pants of Mr. Yan: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_hexing_pants_of_mr_yan.py, which a .cpp edit then does not re-run.
Two readers (the additive pool of a hit, the resource a class pays itself) and the movement read; the classes' sites are the places each class pays the resource its skills generate.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_hexing_pants_of_mr_yan import MODULE  # noqa: E402

SRC = MODULE / "src"
COMBAT = SRC / "combat/dc_combat.cpp"
READERS = item_powers_source.FOLDER / "dc_item_powers_readers.cpp"
POWERS = item_powers_source.FOLDER / "dc_item_powers.cpp"

# Where each class pays the primary resource its skills generate, and what that line must multiply by (ItemPowers::GenerationFactor).
SITES = {
    "Barbarian": (SRC / "classes/barbarian/dc_barbarian_passives.cpp",
                  'Resources::Generated(p, Resources::Fury, 1.0) * ItemPowers::GenerationFactor(p);'),
    "Wizard": (SRC / "combat/dc_combat_internal.h",
               "Resources::Energize(player, Resources::ArcanePower, spellId, points * ItemPowers::GenerationFactor(player));"),
    "Monk": (SRC / "classes/monk/dc_monk.cpp",
             '(row ? ItemPowers::SkillFactor(player, row->skill, "resource_generation_pct") : 1.0) * ItemPowers::GenerationFactor(player);'),
    "Demon Hunter": (SRC / "classes/demon_hunter/dc_demon_hunter.cpp",
                     'Passive::Generated(player, spellId, *generated) * ItemPowers::SkillFactor(player, row->skill, "resource_generation_pct") * ItemPowers::GenerationFactor(player));'),
    "Necromancer": (SRC / "classes/necromancer/dc_necromancer_effects.cpp",
                    'points * ItemPowers::SkillFactor(player, row->skill, "resource_generation_pct") * ItemPowers::GenerationFactor(player));'),
    "Crusader": (SRC / "classes/crusader/dc_crusader.cpp",
                 'points * ItemPowers::SkillFactor(player, row->skill, "resource_generation_pct") * ItemPowers::GenerationFactor(player));'),
    "Witch Doctor": (SRC / "classes/witch_doctor/dc_witch_doctor.cpp",
                     "Gain(player, Classes::ClassIdOf(player), spellId, *perHit * ItemPowers::GenerationFactor(player), enemies);"),
}


def failures(texts):
    """What is wrong with the readers, the additive pool, the movement read and the classes' sites (the source guards; [] when they are right)."""
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    combat, readers, powers = texts["combat"], texts["readers"], texts["powers"]
    pool = "GemPowers::DamageBonus(player) + ItemPowers::DamageBonus(player) + hit.targetBonus);"
    need("the additive pool of a hit takes the item powers' percent, once", combat.count("ItemPowers::DamageBonus(player)") == 1 and pool in combat)
    need("...in the pool Additive turns into the step 4 multiplier", "hit.additive = Additive(" in combat and pool in combat and combat.index("hit.additive = Additive(") < combat.index(pool))
    for name, call in (("DamageBonus", "ItemPower::GenerationDamagePct(Data().rows, CountsOf(guid), SituationOf(guid, std::move(seen)))"),
                       ("GenerationFactor", "ItemPower::GenerationFactor(Data().rows, CountsOf(guid), SituationOf(guid, std::move(seen)))")):
        start = readers.find("double %s(Player const* player)" % name)
        reader = readers[start:readers.index("\n    }\n", start)] if start >= 0 else ""
        need("%s is the rule over the situation the hit reads, under the lock" % name,
             start >= 0 and "return " + call + ";" in reader and reader.index("Seen(player)") < reader.index("std::lock_guard<std::mutex> lock(mutex);"))
        need("%s has no player, no number" % name, "if (!player)" in reader)
    need("a row under a movement condition turns the read on", 'loaded.moves = loaded.moves || row.cond == "moving" || row.cond == "not_moving";' in powers)
    need("the movement is read when the number is, only when a row wants it",
         "if (Data().moves)\n                situation.moving = player->isMoving();" in powers
         and "!Data().life && !Data().moves)\n                return situation;" in powers)
    for klass, (path, line) in SITES.items():
        text = texts[klass]
        need("%s multiplies the resource it pays by the item powers' generation" % klass, text.count(line) == 1)
    need("no other place reads it", sum(texts[k].count("ItemPowers::GenerationFactor(") for k in SITES) == len(SITES))   # one line in each class's file
    return wrong


def read():
    texts = {"combat": COMBAT.read_text(encoding="utf-8"), "readers": READERS.read_text(encoding="utf-8"), "powers": POWERS.read_text(encoding="utf-8")}
    for klass, (path, _) in SITES.items():
        texts[klass] = path.read_text(encoding="utf-8")
    return texts


class Hooks(unittest.TestCase):
    def test_the_readers_and_the_sites(self):
        self.assertEqual([], failures(read()))

    def test_the_source_guards_fail_their_mutants(self):
        texts = read()
        mutants = {
            "not_in_the_pool": ("combat", " + ItemPowers::DamageBonus(player)", ""),
            "pool_after_the_target_bonus": ("combat", "GemPowers::DamageBonus(player) + ItemPowers::DamageBonus(player) + hit.targetBonus", "GemPowers::DamageBonus(player) + hit.targetBonus"),
            "wrong_damage_rule": ("readers", "ItemPower::GenerationDamagePct(Data().rows", "ItemPower::PlayerSum(Data().rows"),
            "wrong_factor_rule": ("readers", "return ItemPower::GenerationFactor(Data().rows, CountsOf(guid)", "return ItemPower::CutFactor(Data().rows, CountsOf(guid)"),
            "no_player_check_in_the_factor": ("readers", "        if (!player)\n            return 1.0;\n        ItemPower::Situation seen = Seen(player);\n        std::lock_guard<std::mutex> lock(mutex);\n        std::uint64_t const guid = player->GetGUID().GetRawValue();\n        return ItemPower::GenerationFactor(", "        ItemPower::Situation seen = Seen(player);\n        std::lock_guard<std::mutex> lock(mutex);\n        std::uint64_t const guid = player->GetGUID().GetRawValue();\n        return ItemPower::GenerationFactor("),
            "flag_never_set": ("powers", 'loaded.moves = loaded.moves || row.cond == "moving" || row.cond == "not_moving";', ""),
            "flag_only_moving": ("powers", 'loaded.moves = loaded.moves || row.cond == "moving" || row.cond == "not_moving";', 'loaded.moves = loaded.moves || row.cond == "moving";'),
            "movement_never_read": ("powers", "situation.moving = player->isMoving();", ""),
            "movement_inverted": ("powers", "situation.moving = player->isMoving();", "situation.moving = !player->isMoving();"),
            "read_even_when_nothing_wants_it": ("powers", "!Data().life && !Data().moves)\n                return situation;", "!Data().life)\n                return situation;"),
        }
        for klass, (path, line) in SITES.items():
            mutants["%s_site_lost" % klass] = (klass, " * ItemPowers::GenerationFactor(" + line.split("ItemPowers::GenerationFactor(", 1)[1].split(")", 1)[0] + ")", "")
        for name, (key, old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, texts[key].count(old), name + " does not apply once")
                mutated = dict(texts)
                mutated[key] = texts[key].replace(old, new)
                self.assertTrue(failures(mutated), name + " survived")


if __name__ == "__main__":
    unittest.main()
