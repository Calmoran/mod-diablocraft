"""The source-text guards of Vile Ward: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_vile_ward.py, which a .cpp edit then does not re-run.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_vile_ward import MODULE, SKILL, SRC, read_csv  # noqa: E402


class Hooks(unittest.TestCase):
    def test_furious_charge_resolves_through_the_target_loop(self):
        """A line to a point with no projectile Speed: Finish hands the cast to ResolveCast, whose loop deals each target's hit (no per-target Impact)."""
        targeting = next(r for r in read_csv("data/d3/skill_targeting.csv") if r["skill"] == SKILL)
        self.assertEqual(("line_to_point", "instant"), (targeting["target_type"], targeting["cast_type"]))
        sql = (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
        columns = [c.strip(" `\n") for c in re.search(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES", sql, re.S)[1].split(",")]
        speed = columns.index("Speed")
        shells = [s for s in read_csv("data/generated/spell_shells.csv") if s["name"].split(" - ")[0] == SKILL and s["kind"] in ("active", "rune")]
        self.assertEqual(6, len(shells))
        for shell in shells:
            record = re.search(r"\((%s,[^)]*)\)" % shell["spell_id"], sql)[1].split(",")
            self.assertEqual("0", record[speed], shell["name"])
        text = (SRC / "combat/dc_combat_resolve.cpp").read_text(encoding="utf-8")
        self.assertIn("return GetSpellInfo()->Speed > 0 && !GetSpellInfo()->IsChanneled();", text)
        self.assertIn("case GroundMissile::Path::AtCast:\n                        ResolveCast(player, shell, center, native, GetExplTargetUnit(), &origin);", text)

    def test_the_places_count_from_where_the_line_starts(self):
        """`center` of a line to a point is the point it ends at; a charge meets its enemies from its start, so the loop counts from the caster's feet."""
        text = (SRC / "combat/dc_combat_resolve.cpp").read_text(encoding="utf-8")
        begin = text[text.index("void Begin()\n            {\n                auto found = FindShell(GetSpellInfo()->Id);"):]
        begin = begin[:begin.index("previousSpline = player->movespline->GetId();")]
        self.assertRegex(begin, r"center = player->GetPosition\(\);\s+origin = center;\s+if \(shell\.targeting\.Destination\(\)\)")
        self.assertLess(begin.index("origin = center;"), begin.index("center = *GetExplTargetDest();"))
        body = text[text.index("void ResolveCast(Player* player, Shell const& shell"):]
        body = body[:body.index("\n        }\n")]
        self.assertIn("Position const* origin = nullptr)", body)
        self.assertIn("Position const& from = origin && shell.targeting.Line() ? *origin : center;", body)
        self.assertIn("distances.push_back(from.GetExactDist(target));", body)
        self.assertNotIn("center.GetExactDist(target)", body)

    def test_the_loop_sets_the_place_around_each_hit_and_puts_it_back(self):
        text = (SRC / "combat/dc_combat_resolve.cpp").read_text(encoding="utf-8")
        body = text[text.index("void ResolveCast(Player* player, Shell const& shell"):]
        body = body[:body.index("\n        }\n")]
        self.assertRegex(body, r"unsigned& place = ItemPowers::HitPlace\(\);\s+unsigned const outer = place;")
        self.assertRegex(body, r"std::size_t index = 0;\s+for \(Unit\* target : targets\)\s+\{\s+place = ItemPower::NearestPlace\(distances, index\+\+\);\s+"
                               r"connected \+= ResolveHit\(player, target, punch\.pct \? punched : shell, info\)")
        self.assertLess(body.index("connected += ResolveHit(player, target,"), body.index("place = outer;"))
        self.assertLess(body.index("place = outer;"), body.index("Abilities::Cast(player, shell.spellId, targets"))
        self.assertEqual(1, body.count("ResolveHit("))

    def test_the_place_is_per_thread_and_read_into_every_situation(self):
        text = item_powers_source.CPP.read_text(encoding="utf-8")
        self.assertRegex(text, r"unsigned& HitPlace\(\)\s+\{\s+thread_local unsigned place = 0;\s+return place;\s+\}")
        situation = text[text.index("ItemPower::Situation SituationOf(std::uint64_t guid"):]
        situation = situation[:situation.index("return situation;")]
        self.assertIn("situation.hitPlace = HitPlace();", situation)

    def test_the_hit_reads_the_damage_row_with_the_base_skill_name(self):
        text = (SRC / "combat/dc_combat.cpp").read_text(encoding="utf-8")
        self.assertIn("std::string const& petName = petSkill ? std::string(petSkill) : shell.skill;", text)
        self.assertIn('hit.legendary = ItemPowers::SkillFactor(player, petName, "damage_increase_pct")', text)
        self.assertLess(text.index('hit.legendary = ItemPowers::SkillFactor(player, petName, "damage_increase_pct")'), text.index("hit.total = Total("))


if __name__ == "__main__":
    unittest.main()
