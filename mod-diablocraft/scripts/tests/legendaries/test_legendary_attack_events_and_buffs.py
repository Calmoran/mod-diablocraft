"""Legendary bead 4 follow-ups (diablocraft-pl8fc, ruling 2026-10-11):

  * the Obsidian Ring of the Zodiac (a `hit_spender` row) fires at most once per cast or channel tick: the per-attack events leave
    ItemPowers::Hit (one call per enemy) for ItemPowers::Attack, called by Combat::Connected once per cast or tick that hit, where Life
    per Hit already was. Read here (a cast needs the core); the Provider half runs in test_primary_provider.py;
  * The Burning Axe of Sankis shows a buff while its window is up: record 83550 from data/legendary_power_buffs.csv, its $s1 the power
    row's number and the Power file's, put on by ItemPowers' Fire for the row's seconds (the rule, ItemPower::Opened, is driven in
    test_item_power_events.py);
  * Echoing Fury's stacks speed every attack: driven in test_primary_provider.py (AttackSpeed and GrantFrenzy, production source).
"""
import csv
import re
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import barbarian_source  # noqa: E402
import generate_spells
import test_spell_records as records
from test_item_power_events import sankis_numbers

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src/combat"
SHEET = MODULE / "data/legendary_power_buffs.csv"
SANKIS = "Unique_Axe_1H_007_x1"


def read(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def body(source, start, end):
    text = source[source.index(start):]
    return text[:text.index(end)]


class PerAttackEvents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.powers = (item_powers_source.CPP).read_text(encoding="utf-8")
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "dc_combat_internal.h", *sorted((SRC).glob("dc_combat*.cpp"))])
        cls.abilities = barbarian_source.abilities((".cpp",))
        cls.primaries = (SRC.parent / "classes" / "barbarian" / "dc_barbarian_primaries.cpp").read_text(encoding="utf-8")

    def test_a_hit_on_one_enemy_fires_only_the_hit_event(self):
        hit = body(self.powers, "void Hit(Player* player, Unit* target, std::uint32_t spellId)", "void Attack(")
        self.assertEqual(['"hit"'], re.findall(r'Fire\(player, ("\w+")', hit))
        attack = body(self.powers, "void Attack(Player* player, std::uint32_t spellId, unsigned enemies)", "void Taken(")
        self.assertEqual(['"hit_generator"', '"hit_spender"'], re.findall(r'Fire\(player, ("\w+")', attack))

    def test_connected_is_life_per_hit_and_the_per_attack_events(self):
        connected = body(self.combat, "void Connected(Player* player, std::uint32_t spellId, unsigned enemies)", "\n    }\n")
        self.assertIn("Stats::SkillHit(player);", connected)
        self.assertIn("ItemPowers::Attack(player, spellId, enemies);", connected)   # the count for enemies_hit_at_most (2z25c)
        self.assertIn("Shaman::Connected(player, spellId, enemies);", connected)   # the Shaman's Maelstrom generation, told once per attack like the other classes'
        # Life per Hit is reached only through it: no site pays one without the other
        for path in sorted((MODULE / "src").rglob("*.cpp")):
            text = path.read_text(encoding="utf-8")
            calls = text.count("Stats::SkillHit(")
            self.assertEqual(1 if path.name == "dc_combat_resolve.cpp" else 0, calls, path.name)

    def test_each_cast_and_tick_calls_it_once_after_its_enemies(self):
        # every site, after the loop over the enemies and behind the cast's own `connected`
        sites = {
            "the ground impact": (self.combat, "if (connected)\n                Connected(player, id);\n        }\n\n        class dc_wizard_ground"),
            # (the Monk's punch may change the primary's damage: Fists of Thunder's third hit, `punched` in place of `shell`)
            "a resolved cast": (self.combat, "for (Unit* target : targets)\n            {\n                place = ItemPower::NearestPlace(distances, index++);\n"
                                             "                connected += ResolveHit(player, target, punch.pct ? punched : shell, info) ? 1 : 0;\n            }\n            place = outer;\n            enemies = outerEnemies;\n"
                                             "            Abilities::Cast(player, shell.spellId, targets, &center,shell.extraDamage);\n"
                                             "            Wizard::Cast(player, shell.spellId, targets, center, explicitTarget);\n"
                                             "            Monk::Cast(player, shell.spellId, targets, punch);\n"
                                             "            Crusader::Cast(player, shell.spellId, targets);\n"
                                             "            Necromancer::Cast(player, shell.spellId, targets);\n"
                                             "            DemonHunter::Cast(player, shell.spellId, targets);\n"
                                             "            WitchDoctor::Cast(player, shell.spellId, targets);\n"
                                             "            Shaman::Cast(player, shell.spellId, targets);\n"
                                             "            Monk::Ground(player, shell.spellId, center);\n"
                                             "            Crusader::Ground(player, shell.spellId, center);\n"
                                             "            Necromancer::Ground(player, shell.spellId, center);\n"
                                             "            DemonHunter::Ground(player, shell.spellId, center);\n"
                                             "            WitchDoctor::Ground(player, shell.spellId, center);\n"
                                             "            Shaman::Ground(player, shell.spellId, center);\n"
                                             "            if (connected)\n                Connected(player, shell.spellId, connected);"),
            "a channel tick": (self.combat, "            if (connected)\n                Connected(player, channel.spellId);\n            return true;"),
            "Boulder Toss": (self.combat, "hit += ResolveHit(player, u, shell, GetSpellInfo()) ? 1 : 0;\n                    enemies = outer;\n                    if (hit)\n                        Connected(player, shell.spellId, hit);\n                    return;"),
            "a projectile, once per Spell": (self.combat, "if (ResolveHit(player, target, shell, GetSpellInfo()) && !connected)\n                {\n"
                                                          "                    connected = true;\n                    Connected(player, shell.spellId, struck);"),
            "a module strike area": (self.combat, "if (!hit.empty() && !periodic)\n            Connected(player, spellId, static_cast<unsigned>(hit.size()));"),
            "a Whirlwind tick": (self.abilities, "if(connected)Connected(p,row->id);"),
            "a zone, once": (self.abilities, "if (!zone.connected)\n                            {\n                                zone.connected = true;\n"
                                             "                                Connected(p, zone.spell);"),
            "a primary, on its first target": (self.primaries, "if (first)\n                    {\n                        grant = FuryGain(player, *row);\n"
                                                               "                        Connected(player, info->Id);"),
        }
        for name, (source, text) in sites.items():
            self.assertIn(" ".join(text.split()), " ".join(source.split()), name)
        # and nowhere else: a new call site is a decision this test has to learn
        # the Monk's, the Crusader's, the Necromancer's, the Demon Hunter's, the Witch Doctor's and the Shaman's hooks (Monk::Connected, Crusader::Connected, Necromancer::Connected, DemonHunter::Connected, WitchDoctor::Connected, Shaman::Connected) are called from the definition, not a site of their own
        self.assertEqual(7, self.combat.replace("Monk::Connected(", "").replace("Crusader::Connected(", "").replace("Necromancer::Connected(", "").replace("DemonHunter::Connected(", "").replace("WitchDoctor::Connected(", "").replace("Shaman::Connected(", "").count("Connected("), "six sites and the definition")
        self.assertEqual(2, self.abilities.count("Connected("))
        self.assertEqual(1, self.primaries.count("Connected("))


class SankisBuff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sheet = read(SHEET)
        cls.names, cls.spells = records.parse((MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"), every_class=True)

    def field(self, spell, column):
        return self.spells[spell][self.names.index(column)]

    def test_the_record_states_the_power_rows_number(self):
        self.assertEqual([("83550", SANKIS, "damage_reduction_pct")], [(r["spell_id"], r["owner"], r["stat"]) for r in self.sheet if r["owner"] == SANKIS])
        power = next(r for r in read(MODULE / "data/legendary_powers.csv") if r["owner"] == SANKIS)
        stated = int(self.field(83550, "EffectBasePoints_1")) + int(self.field(83550, "EffectDieSides_1"))
        # three sources, one number: the record, the power table, the Power file (SF_1 damage reduction = 0.35)
        self.assertEqual(float(power["value_min"]), stated)
        self.assertEqual(sankis_numbers()[2], stated)
        self.assertEqual("Damage taken reduced by $s1%.", records.unquote(self.field(83550, "AuraDescription_Lang_enUS")))
        self.assertEqual("The Burning Axe of Sankis", records.unquote(self.field(83550, "Name_Lang_enUS")))
        self.assertEqual(("6", "4", "1"), tuple(self.field(83550, c) for c in ("Effect_1", "EffectAura_1", "ImplicitTargetA_1")),
                         "one SPELL_AURA_DUMMY on the wearer: display only")
        self.assertEqual(("0", "0"), (self.field(83550, "Effect_2"), self.field(83550, "Effect_3")))
        self.assertEqual(self.field(83411, "DurationIndex"), self.field(83550, "DurationIndex"), "infinite, like a gem buff: the module sets the seconds")
        attributes = int(self.field(83550, "Attributes"))
        self.assertFalse(attributes & 0x40, "not passive: the client shows it")
        self.assertFalse(attributes & 0x04000000, "a buff, not a debuff")

    def test_the_icon_is_the_donors(self):
        if not (generate_spells.DBC / "Spell.dbc").is_file():
            self.skipTest("no stock Spell.dbc on this machine")
        rows, _, _, _ = generate_spells.load_dbc("Spell.dbc")
        donor = int(self.sheet[0]["icon"])
        icon = self.names.index("SpellIconID")
        self.assertEqual(str(generate_spells.struct.unpack_from("<I", rows[donor], icon * 4)[0]), self.field(83550, "SpellIconID"))

    def test_the_header_and_manifest_carry_it(self):
        header = (SRC / "dc_spell_shells.h").read_text(encoding="utf-8")
        self.assertIn('{83550, "Unique_Axe_1H_007_x1", "damage_reduction_pct"},', header)
        table = re.findall(r"\d+", re.search(r"ShellIds\[\] = \{(.*?)\};", header, re.S).group(1))
        self.assertIn("83550", table)
        manifest = {r["spell_id"]: r for r in read(MODULE / "data/generated/spell_shells.csv")}
        self.assertEqual("power_buff", manifest["83550"]["kind"])

    def test_the_generator_refuses_a_number_it_cannot_bake(self):
        good = dict(self.sheet[0])
        self.assertEqual(35, generate_spells.power_buff_number(good))
        with tempfile.TemporaryDirectory() as folder:
            sheet = Path(folder) / "legendary_powers.csv"
            rows = read(MODULE / "data/legendary_powers.csv")
            for row in rows:
                if row["owner"] == SANKIS:
                    row["value_max"] = "40"
            with sheet.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            saved = generate_spells.LEGENDARY_POWERS_SHEET
            generate_spells.LEGENDARY_POWERS_SHEET = sheet
            try:
                with self.assertRaises(SystemExit):
                    generate_spells.power_buff_number(good)            # a ranged row: no one number for every wearer
            finally:
                generate_spells.LEGENDARY_POWERS_SHEET = saved
        with self.assertRaises(SystemExit):
            generate_spells.power_buff_number(dict(good, stat="damage_dealt_pct"))   # names no row

    def test_fire_puts_it_on_for_the_rows_seconds(self):
        powers = (item_powers_source.CPP).read_text(encoding="utf-8")
        fire = body(powers, "void Fire(Player* player, char const* event", "} // namespace Detail")
        self.assertIn("ItemPower::Opened(Data().rows, situation, event)", fire)
        self.assertIn("Shells::PowerBuffFor(row->owner.c_str(), row->stat.c_str())", fire)
        self.assertIn("static_cast<std::int32_t>(row->arg * 1000.0)", fire)
        self.assertIn("aura->SetMaxDuration(ms);", fire)
        self.assertIn("aura->SetDuration(ms);", fire)


if __name__ == "__main__":
    unittest.main()
