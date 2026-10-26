"""The source-text guards of counter: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_counter.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import crafting_source  # noqa: E402
import item_powers_source  # noqa: E402
import barbarian_source
from test_item_power_counter import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    """Source-text guards: the call is there. They do not run the C++."""

    @classmethod
    def setUpClass(cls):
        cls.items = items_source.source()
        cls.combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        cls.powers = item_powers_source.CPP.read_text(encoding="utf-8")

    def test_apply_refreshes_the_count_beside_the_gems(self):
        gems = "DC::Combat::GemPowers::Refresh(player, item, equipping, *instance);"
        mine = "DC::Combat::ItemPowers::Refresh(player, item, equipping, *instance);"
        self.assertIn(mine, self.items)
        self.assertLess(self.items.index(gems), self.items.index(mine))

    def test_the_roller_takes_the_tables_stats_as_presets_and_their_range(self):
        self.assertIn("DC::Combat::ItemPowers::ItemStats(base.d3Id)", self.items)
        self.assertIn("DC::Combat::ItemPower::RollRange(powerStats, base.d3Id, entry.affixId, entry.min, entry.max);", self.items)
        # the range is applied before the value is rolled
        self.assertLess(self.items.index("ItemPower::RollRange("), self.items.index('take(entry, "preset");'))

    def test_the_roller_stores_a_ranged_power_once_and_a_primal_at_the_top(self):
        self.assertIn("DC::Combat::ItemPower::RollPowers(DC::Combat::ItemPowers::ItemRows(base.d3Id), base.d3Id, atTop,", self.items)
        self.assertIn("return RollValue(range);", self.items)  # the roller's own value rule, whole numbers for a whole range
        self.assertIn('power.key, "", power.value, power.min, power.max, "power", false, false});', self.items)
        # rolled with the item's other rows, so the row is in the same transaction and its seq follows theirs
        self.assertLess(self.items.index('fill(secondaryPool, plan.randomSecondary, "secondary");'), self.items.index("ItemRows(base.d3Id), base.d3Id, atTop"))
        self.assertLess(self.items.index("ItemRows(base.d3Id), base.d3Id, atTop"), self.items.index("for (Affix const& affix : rolled)"))

    def test_an_item_without_a_stored_roll_gets_one_at_its_first_server_read(self):
        # Load is the one server read (Apply on equip and login, every consumer of Get); the backfill runs before the rows are read, so
        # the instance it returns holds the roll, and the hit path (WornRolls) never rolls
        backfill = self.items[self.items.index("void BackfillPowers(", self.items.index("double RollValue")):self.items.index("// G1: the seven weapon elemental affixes")]
        self.assertIn("DC::Quality::AtTop(qualityTier)", backfill)  # a Primal gets the top
        self.assertIn("}, have))", backfill)  # only the powers it lacks
        self.assertIn("INSERT INTO dc_item_affix", backfill)
        # stored before the rows are read: it waits for the commit under the lock, as RollItem does; CommitTransaction only queues it
        self.assertIn("if (next != firstSeq)\n        CharacterDatabase.AsyncCommitTransaction(transaction).m_future.get();", backfill)
        self.assertNotIn("CharacterDatabase.CommitTransaction(", backfill)
        load = self.items[self.items.index("std::optional<Instance> Load("):self.items.index("void Erase(")]
        self.assertLess(load.index("BackfillPowers(itemGuid, instance.baseItem, instance.qualityTier);"), load.index("FROM dc_item_affix WHERE item_guid={} ORDER BY seq"))
        self.assertNotIn("Backfill", self.powers)
        self.assertNotIn("RollPowers", self.powers)
        # the tooltip reads the table itself, so the bags are read once at login
        self.assertIn("SweepPowerRolls(player);", self.items)
        self.assertIn("ItemPowers::HasItemPower(item->GetEntry())", self.items)

    def test_the_readers_of_an_items_rows_skip_a_power(self):
        crafting = crafting_source.source()
        self.assertIn('if (affix.kind == "socket" || affix.kind == "power" || affix.kind == DC::GrantedPassive::Kind) continue;', self.items)  # Items::Apply: not a stat
        # the Mystic never offers it, nor Caldesann's `augment` row (Cube 7, diablocraft-wpt7l.8), which sits beside the rolled lines
        self.assertIn('if (RequiredShieldAffix(a.affixId) || a.kind == "power" || a.kind == "augment" || a.kind == DC::GrantedPassive::Kind)', self.items)
        self.assertIn('if (a.kind != "power" && a.kind != "passive" && a.kind != "augment")', crafting)  # the window's item record (the augment row too, Cube 7)

    def test_the_read_follows_the_worn_unbroken_item(self):
        # Items::Apply passes equipping=false for a broken item, so the entry is erased; logout forgets the player
        self.assertIn("mine[changed->GetGUID().GetCounter()] = std::move(values);", self.powers)
        self.assertIn("mine.erase(changed->GetGUID().GetCounter());", self.powers)
        self.assertIn("worn.erase(player->GetGUID().GetRawValue());", self.powers)
        self.assertIn("if (equipping && item->IsBroken())\n        equipping = false;", self.items)
        self.assertIn("std::vector<double> WornRolls(Player const*", (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8"))

    def test_the_hit_multiplies_by_the_skills_powers(self):
        self.assertIn('hit.legendary = ItemPowers::SkillFactor(player, petName, "damage_increase_pct") * ItemPowers::DealtFactor(player) * CopyFactor();', self.combat)
        self.assertNotIn("hit.legendary = 1.0;", self.combat)

    def test_the_rend_bleed_takes_its_length_from_the_table_once(self):
        # on the real apply only (a reapply would restart the bleed); the ticks follow the aura, not a constant
        rend = barbarian_source.named("dc_barbarian_rend.cpp")
        self.assertIn("(mode & AURA_EFFECT_HANDLE_REAL)", rend)
        self.assertIn('ItemPowers::SkillSetTo(player, "Rend", "dot_duration_seconds", ownSeconds)', rend)
        self.assertIn("tick.total = ItemPower::BleedDamage(stacks, number);", rend)
        self.assertNotIn("REND_TICKS", rend)
        self.assertIn("number > uint32(effect->GetTotalTicks())", rend)

    def test_mutilate_marks_for_as_long_as_the_bleed(self):
        abilities = barbarian_source.abilities((".cpp",))
        self.assertIn('ItemPowers::SkillSetTo(p, "Rend", "dot_duration_seconds", Numbers::Num(b->id, "dot_duration_seconds"))', abilities)

    def test_the_scripts_are_registered(self):
        self.assertIn("ItemPowers::RegisterScripts();", self.combat)
        self.assertIn("new SetCountCommand();", self.powers)
        self.assertIn("new Cache();", self.powers)

    def test_damage_taken_takes_the_players_powers_in_both_mitigation_paths(self):
        # Mitigate (the hit) and DamageTakenFactor (the sheet's preview, `.dc`) read one number, so they cannot drift apart
        self.assertEqual(2, self.combat.count("ItemPowers::IncomingFactor(victim->ToPlayer())"))

    def test_the_hit_reads_damage_dealt_and_a_hit_taken_resets_the_stacks(self):
        self.assertIn('ItemPowers::SkillFactor(player, petName, "damage_increase_pct") * ItemPowers::DealtFactor(player) * CopyFactor();', self.combat)
        mitigate = self.combat[self.combat.index("std::optional<double> Mitigate("):]
        mitigate = mitigate[:mitigate.index("return result;")]
        self.assertIn("ItemPowers::Hurt(victim->ToPlayer());", mitigate)
        self.assertIn("if (result > 0)", mitigate)

    def test_the_snapshot_rule_one_read_in_the_hit_and_snapshotting_skills_keep_the_hit(self):
        # docs/contracts/legendary-powers.md "The snapshot rule": a power is read once, inside ComputeHit, when a skill applies; a skill that
        # snapshots keeps the Hit it got, so a condition that held then holds for it until it ends. No other place reads a damage power.
        everything = "".join(p.read_text(encoding="utf-8") for p in sorted(SRC.rglob("*.cpp")))
        # The other SkillFactor reads are not damage powers: a skill's own attack speed (li0ie, Bracers of the First Men) in
        # HandAttacksPerSecond, the Ancients' swings (tab0h, Fury of the Ancients) in their AI, both outside the hit, the Spirit a Monk
        # primary generates (atyj0, Band of Rue Chambers) in Monk::SpiritFactor and the Wrath a Crusader primary generates in Crusader's Generate and the Essence a Necromancer primary generates in PayEssence and the Hatred a Demon Hunter primary generates in DemonHunter::Connected, and the Maelstrom a Shaman skill generates in Shaman::Connected (dc_shaman_maelstrom.cpp), and Iron Impact's armor and duration (rune_effect_pct,
        # Might of the Earth 4-piece, diablocraft-tydva) in Leap's cast and Refresh, and the explosion part of Exploding Palm (lxvl2, The Fist of Az'Turrasq, N-SKPART), read at the enemy's death in
        # ExplodingPalm::Explode.
        self.assertEqual(12, everything.count("ItemPowers::SkillFactor("))   # the 8th: the hit's "skill - rune" row (Skular's Salvation), in ComputeHit; the 9th: the Crusader's Wrath; the 10th: the Necromancer's Essence; the 11th: the Demon Hunter's Hatred; the 12th: the Shaman's Maelstrom
        self.assertEqual(5, everything.count('ItemPowers::SkillFactor(player, row->skill, "resource_generation_pct")'))
        shaman = (SRC / "classes/shaman/dc_shaman_maelstrom.cpp").read_text(encoding="utf-8")
        self.assertEqual(1, shaman.count('ItemPowers::SkillFactor(player, row->skill, "resource_generation_pct")'))
        self.assertEqual(1, everything.count('ItemPowers::SkillFactor(player, std::string(Skill), "explosion_damage_pct")'))
        self.assertEqual(2, everything.count('ItemPowers::SkillFactor(p, "Leap", "rune_effect_pct")'))
        self.assertEqual(1, everything.count('ItemPowers::SkillFactor(player, ability->skill, "attack_speed_pct")'))
        self.assertEqual(1, everything.count('Combat::ItemPowers::SkillFactor(p, "Call of the Ancients", "summon_attack_speed_pct")'))
        self.assertEqual(1, everything.count("ItemPowers::DealtFactor("))
        self.assertEqual(1, everything.count("ItemPowers::ElementBonus("))
        self.assertEqual(1, everything.count("ItemPowers::TargetFactor("))   # Fjord Cutter (N-TCTRL, 5i88h): by the hit's target, in the hit only
        self.assertEqual(1, everything.count("ItemPowers::DerivedFactor("))   # Standoff (r2lly): the hit reads it once, in ComputeHit
        compute = self.combat[self.combat.index("bool ComputeHit("):self.combat.index("std::string Hit::Describe()")]
        self.assertIn('ItemPowers::SkillFactor(player, petName, "damage_increase_pct")', compute)
        self.assertIn('ItemPowers::SkillFactor(player, hit.skillName, "damage_increase_pct")', compute)
        self.assertIn("ItemPowers::DealtFactor(", compute)
        self.assertIn("ItemPowers::ElementBonus(player, shell.element)", compute)
        self.assertIn("ItemPowers::DerivedFactor(player, petName, *sheet)", compute)
        self.assertIn("ItemPowers::TargetFactor(player, target, petName)", compute)
        rend = barbarian_source.named("dc_barbarian_rend.cpp")
        bleed = rend[rend.index("class dc_rend_bleed"):rend.index("class RendPeriodicProvider")]
        self.assertEqual(2, bleed.count("ComputeHit("))   # taken on apply (Snapshot) and for a further bleed that stacks (AddStack), never in a tick
        tick = bleed[bleed.index("bool FinalTick("):bleed.index("void Register()")]
        self.assertNotIn("ComputeHit(", tick)
        self.assertIn("Hit tick = snapshot;", tick)
        # the zones and the Dust Devils take their Hit from ComputeHit when they start, and their ticks copy it
        abilities = barbarian_source.abilities((".cpp",))
        self.assertIn("ComputeHit(p, nullptr, row.id, h)", abilities)
        self.assertIn("ComputeHit(p,nullptr,row->id,hit)", abilities)
        self.assertIn("Hit tick = zone.snapshot;", abilities)
        self.assertIn("devil.snapshot", abilities)

    def test_whirlwind_and_the_wizards_channels_feed_the_clock(self):
        abilities = barbarian_source.abilities((".cpp",))
        self.assertIn('ItemPowers::ChannelStarted(p,"Whirlwind");', abilities)
        # ended only when it was running (StopWhirlwind runs on every other cast too)
        self.assertIn('if(ended) ItemPowers::ChannelEnded(p,"Whirlwind");', abilities)
        self.assertIn("ItemPowers::ChannelStarted(player, shell.skill);", self.combat)
        self.assertIn("ItemPowers::ChannelEnded(player, row->skill);", self.combat)
        self.assertIn("clocks.erase(player->GetGUID().GetRawValue());", self.powers)

    @staticmethod
    def replaced_channel_ends(combat):
        """diablocraft-y8ucg: StartChannel reads the channel it replaces (the core interrupted it without StopChannel) and ends that skill's
        span before the new one starts, so a Wizard switching Disintegrate to Ray of Frost leaves no span running."""
        start = combat.index("void StartChannel(Player* player, Shell const& shell")
        body = combat[start:combat.index("class WizardChannels", start)]
        looked = body.find("channels.find(player->GetGUID().GetRawValue())")
        ended = body.find("ItemPowers::ChannelEnded(player, row->skill);")
        started = body.find("ItemPowers::ChannelStarted(player, shell.skill);")
        return 0 <= looked < ended < started

    def test_a_replaced_channel_ends_its_span(self):
        self.assertTrue(self.replaced_channel_ends(self.combat))
        block = """            if (replaced)
                if (auto row = Shells::FindAbility(replaced))
                    ItemPowers::ChannelEnded(player, row->skill);
"""
        self.assertIn(block, self.combat)
        # mutants: the old span is left running, or ended after the new one starts
        gone = self.combat.replace(block, "")
        self.assertFalse(self.replaced_channel_ends(gone))
        started = "            ItemPowers::ChannelStarted(player, shell.skill);\n"
        late = gone.replace(started, started + block)
        self.assertNotEqual(late, gone)
        self.assertFalse(self.replaced_channel_ends(late))

    def test_a_broken_piece_is_not_worn_and_a_logout_forgets(self):
        self.assertIn("!item->IsBroken()", self.powers)
        self.assertIn("counts.erase(player->GetGUID().GetRawValue());", self.powers)


if __name__ == "__main__":
    unittest.main()
