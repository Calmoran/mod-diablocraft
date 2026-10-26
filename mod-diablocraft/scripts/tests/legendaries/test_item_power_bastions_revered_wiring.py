"""The source-text guards of bastions revered: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_bastions_revered.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_bastions_revered import SRC  # noqa: E402


PRIMARIES = SRC / "classes/barbarian/dc_barbarian_primaries.cpp"


def function(source, marker):
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def guard(test, source):
    """The C++ shape of the power in dc_barbarian_primaries.cpp, as the contract words it; `test` is the TestCase asserting."""
    cap = function(source, "unsigned MaxStacks(")
    test.assertIn('ItemPowers::SkillSetTo(player, "Frenzy", "buff_max_stacks", D::frenzy_max_stacks)', cap)
    begin = function(source, "void Begin()")
    test.assertIn('unsigned const cap = row && std::string(row->skill) == "Frenzy" ? MaxStacks(player) : 0u;', begin)
    test.assertIn("buff.frenzy = std::min(buff.frenzy + 1, cap);", begin)
    grant = function(source, "void GrantFrenzy(")
    test.assertIn("unsigned const cap = MaxStacks(player);", grant)
    test.assertEqual(2, grant.count(", cap);"))
    for body in (begin, grant):
        test.assertNotIn("D::frenzy_max_stacks", body)
    landed = function(source, "void Landed()")
    test.assertIn('if (std::string(row->skill) == "Frenzy")\n                    FrenzyChain(player, target, *row, hit);', landed)
    chain = function(source, "void FrenzyChain(")
    test.assertIn('ItemPowers::SkillSetTo(player, "Frenzy", "extra_hits_per_stack", 0)', chain)
    test.assertIn('ItemPowers::SkillSetTo(player, "Frenzy", "chain_yards", 0)', chain)
    test.assertIn("ItemPower::ExtraHits(perStack, stacks)", chain)
    test.assertIn("ComputeHit(player, target, row.id, extra)", chain)
    test.assertIn("extra.offHand = hit.offHand;", chain)
    test.assertIn("ItemPower::ChainShare(extra.total, static_cast<unsigned>(victims.size()))", chain)
    test.assertIn("DealHit(player, victim, row.id, share);", chain)
    test.assertIn("Enemies(player, target, yards)", chain)


class Hooks(unittest.TestCase):
    source = PRIMARIES.read_text(encoding="utf-8")

    def test_the_code_has_the_shape_the_contract_words(self):
        guard(self, self.source)

    def test_mutated_sources_fail_the_guard(self):
        mutants = {
            "the_cast_keeps_the_constant": ('? MaxStacks(player) : 0u;', "? unsigned(D::frenzy_max_stacks) : 0u;"),
            "the_cast_clamps_to_the_constant": ("std::min(buff.frenzy + 1, cap)", "std::min(buff.frenzy + 1, unsigned(D::frenzy_max_stacks))"),
            "the_grant_keeps_the_constant": ("buff.frenzy = std::min(std::max(held, stacks), cap);", "buff.frenzy = std::min(std::max(held, stacks), unsigned(D::frenzy_max_stacks));"),
            "the_grant_sets_the_wrong_counter": ("buff.granted = std::min(std::max(granted, stacks), cap);", "buff.granted = std::min(std::max(granted, stacks), 5u);"),
            "the_extra_hits_hit_every_skill": ('if (std::string(row->skill) == "Frenzy")\n                    FrenzyChain', "if (true)\n                    FrenzyChain"),
            "the_extra_hit_repeats_the_swings_roll": ("Hit extra;\n                extra.offHand = hit.offHand;\n                if (!ComputeHit(player, target, row.id, extra))\n                    return;", "Hit extra = hit;"),
            "the_extra_hit_is_not_split": ("DealHit(player, victim, row.id, share);", "DealHit(player, victim, row.id, extra);"),
            "the_chain_ignores_the_yards": ("Enemies(player, target, yards)", "Enemies(player, target, 15.0f)"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertIn(old, self.source, name + " target is gone")
                with self.assertRaises(AssertionError):
                    guard(self, self.source.replace(old, new, 1))


if __name__ == "__main__":
    unittest.main()
