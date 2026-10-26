"""The source-text guards of Ancestors' Grace: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_ancestors_grace.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_ancestors_grace import SRC, at  # noqa: E402

POWERS = item_powers_source.CPP
HOOKS = SRC / "combat/dc_combat_hooks.cpp"


def block(text, start, end="\n    }\n"):
    rest = text[at(text, start):]
    return rest[:at(rest, end)]


def fatal_guard(powers, hooks, header):
    """The fatal judgement, the effect and the damage hook."""
    fatal = block(powers, "void Fatal(Player* player, std::uint32_t& damage)")
    assert '!Data().events.count("fatal")' in fatal, "nothing to look at unless a row waits for a fatal hit"
    assert "!ItemPower::IsFatal(damage, player->GetHealth())" in fatal, "the rule, with the Life now"
    assert at(fatal, "Saved() = false;") < at(fatal, 'Fire(player, "fatal", "", 1.0);'), "the flag is cleared before the event"
    saved = fatal[at(fatal, 'Fire(player, "fatal", "", 1.0);'):]
    assert "damage = 0;" in saved[at(saved, "if (Saved())"):], "the hit is zeroed when the effect saved the player"
    assert "damage = 0;" not in fatal[:at(fatal, 'Fire(player, "fatal", "", 1.0);')], "never zeroed before the event"
    assert saved.count("Saved() = false;") == 1, "the flag is put back"
    assert 'one.stat == "revive_full" && one.row' in powers and "Revive(player, one.row->owner);" in powers, "the effect revives"
    revive = block(powers, "void Revive(Player* player, std::string const& powerId)", "\n        }\n")
    assert "!item->IsBroken()" in revive, "a broken item is not worn"
    assert "found->second == powerId" in revive, "the item that owns the power (a legacy twin included, through the owners map)"
    assert "if (!host)\n                return;" in revive, "no worn item, no save"
    assert at(revive, "player->DestroyItem(host->GetBagSlot(), host->GetSlot(), true);") < at(revive, "player->SetFullHealth();"), \
        "the item goes first, so the maximums are the ones without it"
    assert "resource.classId == classId" in revive, "the player's class resources, no class named"
    assert "player->SetPower(Resources::Slot(resource), static_cast<int32>(Resources::MaxUnits(player, resource)));" in revive, "every resource to its maximum"
    assert revive.rstrip().endswith("Saved() = true;"), "the save is reported last"
    assert "void Fatal(Player*, std::uint32_t& damage);" in header, "declared"
    damage = block(hooks, "void OnDamage(Unit* attacker, Unit* victim, uint32& damage) override", "\n            }\n")
    assert "if (!player || !damage)" in damage, "every class passes, not the Barbarian alone"
    assert "Barbarian(player))\n                {\n                    Classes::Ancients::Redirect(player, damage);\n" \
           "                    Passives::Fatal(player,damage);\n                }" in damage, "the Barbarian's own steps stay in a block of his"
    assert at(damage, "Passives::Fatal(player,damage);") < at(damage, "ItemPowers::Fatal(player, damage);") < at(damage, "Abilities::Taken("), \
        "the item after Nerves of Steel, before the Barbarian's Fury steps"
    assert "if (!Barbarian(player))\n                    return;" in damage, "the Fury steps are the Barbarian's alone"


class Hooks(unittest.TestCase):
    def texts(self):
        return POWERS.read_text(encoding="utf-8"), HOOKS.read_text(encoding="utf-8"), (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8")

    def test_the_event_and_the_effect_are_wired(self):
        fatal_guard(*self.texts())

    def test_the_source_mutants_fail_the_guard(self):
        powers, hooks, header = self.texts()
        for name, (where, old, new) in {
            "no_event_filter": ("p", '!Data().events.count("fatal") || ', ""),
            "any_hit": ("p", "!ItemPower::IsFatal(damage, player->GetHealth())", "false"),
            "no_event": ("p", 'Fire(player, "fatal", "", 1.0);', ";"),
            "zeroed_always": ("p", "        if (Saved())\n        {\n            Saved() = false;\n            damage = 0;\n        }\n",
                              "        Saved() = false;\n        damage = 0;\n"),
            "flag_kept": ("p", "            Saved() = false;\n            damage = 0;", "            damage = 0;"),
            "no_dispatch": ("p", "Revive(player, one.row->owner);", ";"),
            "broken_item_counts": ("p", "item && !item->IsBroken()", "item"),
            "any_item": ("p", "found->second == powerId", "true"),
            "no_host_still_saves": ("p", "            if (!host)\n                return;\n", ""),
            "item_kept": ("p", "player->DestroyItem(host->GetBagSlot(), host->GetSlot(), true);", ";"),
            "heal_before_the_item_goes": ("p", "            player->DestroyItem(host->GetBagSlot(), host->GetSlot(), true);\n            player->SetFullHealth();",
                                          "            player->SetFullHealth();\n            player->DestroyItem(host->GetBagSlot(), host->GetSlot(), true);"),
            "no_heal": ("p", "player->SetFullHealth();", ";"),
            "another_class_resources": ("p", "resource.classId == classId", "resource.classId != classId"),
            "resources_unrestored": ("p", "player->SetPower(Resources::Slot(resource), static_cast<int32>(Resources::MaxUnits(player, resource)));", ";"),
            "no_report": ("p", "            Saved() = true;\n", ""),
            "barbarian_only": ("h", "if (!player || !damage)", "if (!Barbarian(player) || !damage)"),
            "item_before_nerves": ("h", "                    Passives::Fatal(player,damage);\n                }\n                // After Nerves of Steel, so the Barbarian's free save is used before an item's\n                ItemPowers::Fatal(player, damage);\n",
                                   "                    ItemPowers::Fatal(player, damage);\n                    Passives::Fatal(player,damage);\n                }\n"),
            "no_hook": ("h", "                ItemPowers::Fatal(player, damage);\n", ""),
            "fury_for_all": ("h", "                if (!Barbarian(player))\n                    return;\n", ""),
        }.items():
            with self.subTest(mutant=name):
                text = powers if where == "p" else hooks
                self.assertEqual(1, text.count(old), name + " does not apply once")
                changed = text.replace(old, new)
                args = (changed, hooks, header) if where == "p" else (powers, changed, header)
                with self.assertRaises(AssertionError, msg=name + " survived"):
                    fatal_guard(*args)


if __name__ == "__main__":
    unittest.main()
