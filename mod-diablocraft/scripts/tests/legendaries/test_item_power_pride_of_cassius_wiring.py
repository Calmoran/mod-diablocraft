"""The source-text guards of pride of cassius: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_pride_of_cassius.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import barbarian_source
from test_item_power_pride_of_cassius import SRC  # noqa: E402


class Hooks(unittest.TestCase):
    def test_the_reader_is_declared_and_reads_before_the_power_lock(self):
        self.assertIn("double DurationSeconds(Player const*, std::string const& skill, double base);",
                      (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8"))
        text = item_powers_source.CPP.read_text(encoding="utf-8")
        body = text[text.index("double DurationSeconds("):]
        body = body[:body.index("\n    }\n")]
        self.assertRegex(body, r"if \(!player\)\s+return base;")
        self.assertIn("ItemPower::DurationSeconds(Data().rows, CountsOf(guid), skill, base,", body)
        self.assertLess(body.index("Seen(player)"), body.index("std::lock_guard"))

    def test_ignore_pains_cast_adds_it_to_every_mark(self):
        text = barbarian_source.named("dc_barbarian_ignore_pain.cpp")
        body = text[text.index("void OnCast("):text.index("void OnSpent(")]
        self.assertIn('duration = ItemPowers::DurationSeconds(p, "Ignore Pain", duration);', body)
        self.assertIn('Mark(p, p, *r, duration);', body)
        # the allies of Mob Rule are marked for the lengthened skill too
        self.assertIn('Mark(p, u, *r, ItemPowers::DurationSeconds(p, "Ignore Pain", Numbers::Num(r->id, "duration_seconds")));', body)
        self.assertLess(body.index("DurationSeconds"), body.index("Mark(p, p, *r, duration);"))


if __name__ == "__main__":
    unittest.main()
