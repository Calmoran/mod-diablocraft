"""The source-text guards of crudest boots: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_crudest_boots.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_crudest_boots import SRC  # noqa: E402


ALLY = SRC / "classes/monk/dc_monk_mystic_ally.cpp"


COMBAT = SRC / "combat/dc_combat.cpp"


def reader_failures(text):
    """What is wrong with the Monk's reading of the Boots in `text` (the source guards; [] when it is right)."""
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    need("the extra is the item's summon_count_add on the skill, base 0",
         'ItemPowers::SkillSetTo(player, std::string(Skill), "summon_count_add", 0)' in text)
    upkeep = text[text.index("void Upkeep(Player* player, uint32 diff)"):]
    upkeep = upkeep[:upkeep.index("\n        void Leave(")]
    need("Upkeep asks the extra on the poll only", "unsigned const extra = due ? ExtraAllies(player) : 0;" in upkeep)
    need("and before the lock that decides", "ExtraAllies(player)" in upkeep and
         upkeep.index("ExtraAllies(player)") < upkeep.index("State& state = states[player->GetGUID().GetRawValue()];\n                previous"))
    need("the count follows the extra", "unsigned const wanted = slotted ? AllyCount(extra) : 0;" in upkeep)
    need("a slot past the count is sent away", "std::uint32_t const bar = i < wanted ? slotted : 0;" in upkeep)
    need("each slot is decided and summoned with its own index", "AllyAI::Mode::Fight, i," in upkeep and "Decide(bar, slot.summoned, slot.rebornAt, now)" in upkeep)
    cast = text[text.index("    void Cast(Player* player, std::uint32_t spellId)"):]
    cast = cast[:cast.index("    // Water Ally's Passive")]
    need("every living ally of the rune acts", "for (Slot const& slot : state.slots)" in cast and "allies.push_back(living);" in cast)
    need("Earth Ally's boulder goes through FormSeconds",
         'mind->Roll(FormSeconds(player, Numbers::Num(spellId, "duration_seconds")));' in cast)
    need("Fire Ally's fuse goes through FormSeconds", 'double const seconds = FormSeconds(player, Tune("mystic_ally_fire_max_seconds"));' in cast)
    need("the base Active's window goes through FormSeconds", 'FormSeconds(player, IsRune(spellId, "") ? Numbers::Num(spellId, "duration_seconds", "active") : 0)' in cast
         and "state.empoweredUntil = Now() + Millis(window);" in cast)
    need("Fire Ally's bombs come from every ally", "for (Creature* ally : allies)\n                for (unsigned i = 0; i < count; ++i, ++index)" in cast)
    need("Earth and Water act for every ally", cast.count("for (Creature* ally : allies)") >= 4)
    enduring = cast[cast.index('if (IsRune(spellId, "Enduring Ally"))'):cast.index('else if (IsRune(spellId, "Fire Ally"))')]
    need("Enduring Ally's heal is paid by each living ally of the rune, once per press each",
         "for (std::size_t paid = 0; paid < allies.size(); ++paid)\n            {\n                HealInfo heal(" in enduring
         and enduring.count("player->HealBySpell(heal);") == 1)
    need("a spent Active spends every ally of the rune", "if (slot.summoned == spellId)\n                    Spent(player, slot);" in cast)
    need("the percent is the designer's tunable, and only the Boots' wearer gets it",
         'MysticAlly::FormSeconds(seconds, ExtraAllies(player) > 0, Tune("mystic_ally_boots_form_duration_pct"))' in text)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_file_reads_the_boots(self):
        self.assertEqual([], reader_failures(ALLY.read_text(encoding="utf-8")))

    def test_the_damage_is_the_standing_skill_multiplier(self):
        # S-DMG: every hit of the skill's shell (the allies' swings, the boulder, the explosions and the waves strike with Mystic Ally's
        # record ids) takes SkillFactor(damage_increase_pct) in hit.legendary.
        combat = COMBAT.read_text(encoding="utf-8")
        self.assertIn('hit.legendary = ItemPowers::SkillFactor(player, petName, "damage_increase_pct")', combat)
        ally = ALLY.read_text(encoding="utf-8")
        self.assertIn("Combat::Strike(player, target, skill, pct)", ally)
        self.assertIn("Combat::StrikeArea(", ally)

    def test_the_monk_name_stays_in_the_monks_folder(self):
        for path in (SRC / "combat").rglob("*"):
            if path.suffix in (".cpp", ".h") and path.name != "dc_spell_shells.h":
                self.assertNotIn("summon_count_add", path.read_text(encoding="utf-8", errors="replace"), path)

    def test_the_source_guards_fail_their_mutants(self):
        real = ALLY.read_text(encoding="utf-8")
        mutants = {
            "no_extra": ('ItemPowers::SkillSetTo(player, std::string(Skill), "summon_count_add", 0)', "0.0"),
            "extra_of_another_stat": ('"summon_count_add", 0)', '"damage_increase_pct", 0)'),
            "extra_asked_every_update": ("unsigned const extra = due ? ExtraAllies(player) : 0;", "unsigned const extra = ExtraAllies(player);"),
            "count_ignores_the_extra": ("unsigned const wanted = slotted ? AllyCount(extra) : 0;", "unsigned const wanted = slotted ? 1 : 0;"),
            "extra_slots_kept": ("std::uint32_t const bar = i < wanted ? slotted : 0;", "std::uint32_t const bar = slotted;"),
            "one_index_for_all": ("AllyAI::Mode::Fight, i,", "AllyAI::Mode::Fight, 0,"),
            "earth_without_the_form_seconds": ('mind->Roll(FormSeconds(player, Numbers::Num(spellId, "duration_seconds")));',
                                               'mind->Roll(Numbers::Num(spellId, "duration_seconds"));'),
            "fire_without_the_form_seconds": ('FormSeconds(player, Tune("mystic_ally_fire_max_seconds"))', 'Tune("mystic_ally_fire_max_seconds")'),
            "window_without_the_form_seconds": ("state.empoweredUntil = Now() + Millis(window);",
                                                'state.empoweredUntil = Now() + Millis(Numbers::Num(spellId, "duration_seconds", "active"));'),
            "only_the_first_ally_acts": ("for (Slot const& slot : state.slots)\n                if (slot.summoned == spellId)\n                    if (Creature* living",
                                         "for (Slot const& slot : std::vector<Slot>(state.slots.begin(), state.slots.begin() + 1))\n                if (slot.summoned == spellId)\n                    if (Creature* living"),
            "no_percent": ('Tune("mystic_ally_boots_form_duration_pct")', "0.0"),
            "another_tunable": ('Tune("mystic_ally_boots_form_duration_pct")', 'Tune("mystic_ally_fire_max_seconds")'),
            "the_heal_paid_once": ("for (std::size_t paid = 0; paid < allies.size(); ++paid)", "for (std::size_t paid = 0; paid < 1; ++paid)"),
            "the_heal_paid_twice_each": ("                player->HealBySpell(heal);\n", "                player->HealBySpell(heal);\n                player->HealBySpell(heal);\n"),
            "forms_longer_without_the_boots": ("MysticAlly::FormSeconds(seconds, ExtraAllies(player) > 0,", "MysticAlly::FormSeconds(seconds, true,"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply once")
                self.assertTrue(reader_failures(real.replace(old, new)), name + " survived")


if __name__ == "__main__":
    unittest.main()
