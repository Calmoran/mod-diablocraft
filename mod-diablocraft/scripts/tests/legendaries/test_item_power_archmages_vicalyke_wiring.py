"""The source-text guards of archmages vicalyke: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_archmages_vicalyke.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import generate_legendary_powers as generator
import wizard_source
from test_item_power_archmages_vicalyke import REPO, SRC, TUNABLE, mutate, read_csv  # noqa: E402


def definition(marker, source):
    assert source.count(marker) == 1, "%r is not there exactly once" % marker
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def problems(wizard, powers, header, wizard_h, tunables_sheet):
    """What the source-text guards find wrong, for the four server files (the C++ is compile-checked, not run, here)."""
    out = []
    # the death: the Image's own AI, and nothing else, reports it
    image_ai = definition("class ImageAI final : public ScriptedAI", wizard)
    if "void JustDied(Unit* killer) override" not in image_ai:
        out.append("ImageAI has no JustDied")
    elif ("ItemPower::ImageDeathCounts(killer != nullptr, killer && killer->IsHostileTo(owner))" not in image_ai
          or "ItemPowers::ImageDied(owner, me)" not in image_ai or "Player* owner = OwnerOf(me)" not in image_ai):
        out.append("JustDied does not report the death of an Image killed by an enemy of its owner, to its own owner")
    if wizard.count("JustDied(") != 1:
        out.append("JustDied is in the Wizard's code %d times: only the Image's own death reports" % wizard.count("JustDied("))
    if wizard.count("ImageDied(") != 1:
        out.append("ImageDied is called %d times from the Wizard's code (once: ImageAI::JustDied)" % wizard.count("ImageDied("))
    for name in ("Despawn", "ClearSummons"):
        if "ImageDied" in definition("void %s(Player* player" % name, wizard):
            out.append("%s (a despawn, not a kill) reports a death" % name)
    # the event
    died = definition("void ImageDied(Player* player, Unit* image)", powers)
    if 'Fire(player, "image_death", "", 1.0, image);' not in died:
        out.append("ImageDied does not fire image_death with the dead Image as the target")
    if "void ImageDied(Player*, Unit*" not in header:
        out.append("ImageDied is not declared in dc_item_powers.h")
    # the executor: outside the lock, the chance from the tunable by the sheet's name, the Wizard makes the copy
    fire = definition("void Fire(Player* player, char const* event, std::string const& skill, double scale, Unit* target, unsigned enemies,", powers)
    at = fire.find('one.stat == "multiply_image"')
    if at < 0:
        out.append("no executor for multiply_image")
    else:
        executor = fire[at:fire.index("\n            }\n        }", at)]
        if "lock_guard" in fire[fire.index("for (ItemPower::Fired const& one : fired)"):]:
            out.append("the executors take the item powers' lock")
        if fire.index("for (ItemPower::Fired const& one : fired)") > at:
            out.append("multiply_image is done before the lock is released")
        want = 'DC::Tunables::Has("%s", "%s")' % TUNABLE
        if want not in executor or 'DC::Tunables::Get("%s", "%s")' % TUNABLE not in executor:
            out.append("the executor does not read the chance from the tunable %s.%s" % TUNABLE)
        if "ItemPower::ImageMultiplies(chance," not in executor or "target" not in executor or "Wizard::MultiplyImage(player, target)" not in executor:
            out.append("the executor does not roll ImageMultiplies and hand the dead Image to Wizard::MultiplyImage")
    if tunables_sheet != 1:
        out.append("the tunable %s.%s is on the sheet %d times" % (TUNABLE + (tunables_sheet,)))
    if "bool MultiplyImage(Player* player, Unit* dead);" not in wizard_h:
        out.append("dc_wizard.h does not declare MultiplyImage")
    # the Wizard's copy: the owner's own Image, the dead one's time, a normal Image counted in State.images
    mult = definition("bool MultiplyImage(Player* player, Unit* dead)", wizard)
    for need, why in (("std::find(state.images.begin(), state.images.end(), dead->GetGUID())", "only an Image the player summoned"),
                      ("ItemPower::ImageCopyMs(", "the copy's time is the rule's"),
                      ("->GetTimer()", "the dead Image's remaining time"),
                      ("SummonImage(player, state.imageCast,", "the one routine SummonImages uses"),
                      ("*mine = copy->GetGUID();", "the copy replaces the dead one in State.images"),
                      ("state.imageCast", "the cast's own numbers")):
        if need not in mult:
            out.append("MultiplyImage lacks %s (%s)" % (need, why))
    summon = definition("void SummonImages(Player* player, uint32 id)", wizard)
    if "SummonImage(player, id," not in summon or "state.imageCast = id;" not in summon or "state.images.push_back(" not in summon:
        out.append("SummonImages does not use the shared SummonImage routine and record its cast")
    one = definition("TempSummon* SummonImage(Player* player, uint32 id,", wizard)
    for need in ("TEMPSUMMON_TIMED_DESPAWN", "MIRROR_IMAGE_ENTRY", "CLONE_ME", "SetMaxHealth("):
        if need not in one:
            out.append("SummonImage lacks %s" % need)
    return out


class Hooks(unittest.TestCase):
    wizard = wizard_source.CPP.read_text(encoding="utf-8")
    powers = item_powers_source.CPP.read_text(encoding="utf-8")
    header = (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8")
    wizard_h = (SRC / "classes/wizard/dc_wizard.h").read_text(encoding="utf-8")

    def sheet(self):
        return len([r for r in read_csv("data/tunables/wizard.csv") if r["name"] == TUNABLE[1]])

    def test_the_guards_hold_on_the_source(self):
        self.assertEqual([], problems(self.wizard, self.powers, self.header, self.wizard_h, self.sheet()))

    def test_the_death_has_one_caller_in_the_whole_module(self):
        callers = [p.name for p in SRC.rglob("*.cpp") if "ItemPowers::ImageDied(" in p.read_text(encoding="utf-8")]
        self.assertEqual(["dc_wizard_mirror_image.cpp"], callers)
        callers = [p.name for p in SRC.rglob("*.cpp") if "Wizard::MultiplyImage(" in p.read_text(encoding="utf-8")]
        self.assertEqual(["dc_item_powers_effects.cpp"], callers)

    def test_the_event_is_in_the_generator_and_the_contract(self):
        self.assertIn("image_death", generator.EVENTS)
        self.assertIn("multiply_image", generator.EFFECT_STATS)
        text = (REPO / "docs/contracts/legendary-powers.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"\| `image_death` \(")
        self.assertRegex(text, r"\| `multiply_image` \(")
        self.assertIn("Archmage's Vicalyke `Unique_WizardHat_101_x1`", text)

    def test_the_server_mutants_fail_the_guards(self):
        w, p, h, wh = self.wizard, self.powers, self.header, self.wizard_h
        sheet = self.sheet()
        mutants = {
            "the_death_ignores_the_killer": (mutate(w, "ItemPower::ImageDeathCounts(killer != nullptr, killer && killer->IsHostileTo(owner))", "true"), p, h, wh, sheet),
            "the_wrong_owner": (mutate(w, "ItemPowers::ImageDied(owner, me)", "ItemPowers::ImageDied(owner, me); ItemPowers::ImageDied(owner, me)"), p, h, wh, sheet),
            "a_despawn_reports_a_death": (mutate(w, "        state.images.clear();\n    }\n\n    Player* OwnerOf", "        state.images.clear();\n        ItemPowers::ImageDied(player, nullptr);\n    }\n\n    Player* OwnerOf"), p, h, wh, sheet),
            "the_wrong_event": (w, mutate(p, 'Fire(player, "image_death", "", 1.0, image);', 'Fire(player, "kill", "", 1.0, image);'), h, wh, sheet),
            "the_chance_is_a_literal": (w, mutate(p, 'DC::Tunables::Get("wizard", "archmages_vicalyke_multiply_chance_pct")', "50.0"), h, wh, sheet),
            "the_chance_has_another_name": (w, mutate(p, 'DC::Tunables::Get("wizard", "archmages_vicalyke_multiply_chance_pct")', 'DC::Tunables::Get("wizard", "archmages_vicalyke_chance")'), h, wh, sheet),
            "the_tunable_is_not_on_the_sheet": (w, p, h, wh, 0),
            "the_roll_is_skipped": (w, mutate(p, "ItemPower::ImageMultiplies(chance,", "ItemPower::ImageMultiplies(100,"), h, wh, sheet),
            "the_copy_is_made_under_the_lock": (w, mutate(p, "                else if (one.stat == \"multiply_image\"", "                else if (std::lock_guard<std::mutex> hold(mutex), one.stat == \"multiply_image\""), h, wh, sheet),
            "another_players_image_is_copied": (mutate(w, "std::find(state.images.begin(), state.images.end(), dead->GetGUID())", "state.images.end()"), p, h, wh, sheet),
            "the_copy_is_not_counted": (mutate(w, "*mine = copy->GetGUID();", ""), p, h, wh, sheet),
            "the_copy_is_not_a_normal_image": (mutate(w, "SummonImage(player, state.imageCast, dead->GetPosition(), ms, life)", "player->SummonCreature(MIRROR_IMAGE_ENTRY, dead->GetPosition(), TEMPSUMMON_TIMED_DESPAWN, ms)"), p, h, wh, sheet),
            "the_copy_has_a_fresh_time": (mutate(w, "ItemPower::ImageCopyMs(", "ItemPower::ImageCopyMsFresh("), p, h, wh, sheet),
        }
        for name, args in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual([], problems(*args), name + " survived")


if __name__ == "__main__":
    unittest.main()
