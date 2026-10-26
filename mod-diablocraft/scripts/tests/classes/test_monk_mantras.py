"""diablocraft-80cml and n152h: the Monk's four Mantras share one state and are always on while slotted.

The review returned Mantra of Salvation (80cml) and Mantra of Healing (n152h): the passive started only after a cast, not
"always on" as ruled. The cause was that each Mantra's file started its own pulse on its own cast, and kept a state of its
own for "only one Mantra may be active at a time" (so a Healing cast never turned Salvation off). The fix is one state
header (dc_monk_mantras.h) and one PlayerScript that starts every slotted Mantra's pulse at login and then once a second.
The four Mantras are one file, dc_monk_mantras.cpp: one pulse loop and one press, and a section per Mantra
(monk_source.py reads them).

What this proves, and how:

  * **The shared state.** tests/monk_mantras/harness.cpp compiles the real dc_monk_mantras.h: with nothing cast every
    Mantra's passive is on; a cast of any one turns the other three off; the boost window belongs to the cast Mantra and
    runs its seconds; two Monks keep their own; a logout forgets; the id of an ally's contribution differs per Monk and per
    rune. Nine mutations planted in a scratch copy must each make it fail.
  * **Per Mantra, the passive is on at login with no cast.** For each of Salvation, Retribution (Transgression's loop),
    Healing and Conviction: the always-on hook starts that Mantra without a cast, the Mantra's starter is the shared
    loop's, which needs only the skill on the bar (not a cast) and reads the shared state, and the Mantra keeps no state
    of its own. Each check is also run on the hook text with that Mantra's start line removed, and must then fail.
  * **Two Monks on different Healing runes.** The aura's stat contributions are keyed by the Monk that gives them, and
    what a holder wears is kept per (Monk, holder), so one Monk's pulse does not replace or remove the other's.

What it does not prove: anything on a running server (docs/test-diablocraft-80cml.md).

    python mod-diablocraft/scripts/tests/classes/test_monk_mantras.py
"""

import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import monk_source

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
MONK = MODULE / "src/classes/monk"
SOURCES = ["src/classes/monk/dc_monk_mantras.h", "tests/monk_mantras/harness.cpp"]
HEADER = "src/classes/monk/dc_monk_mantras.h"


def scratch_tree(mutate=None):
    """The headers one build stages ({path under src/: text}); the mutation edits one of them."""
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8") for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/monk_mantras/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    return harness_env.run([str(binary)], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_shared_state(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 30, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("nothing cast turns every passive off",
             (HEADER, "return found == detail::states.end() || found->second.active == mantra;",
              "return found != detail::states.end() && found->second.active == mantra;")),
            ("every Mantra stays on", (HEADER, "found == detail::states.end() || found->second.active == mantra;", "true;")),
            ("the boost outlasts its seconds", (HEADER, "now < found->second.boostUntil", "now <= found->second.boostUntil")),
            ("another Mantra is boosted too", (HEADER, "found->second.active == mantra && now < found->second.boostUntil",
                                               "now < found->second.boostUntil")),
            ("the window starts at zero", (HEADER, "{mantra, now + boostMs}", "{mantra, boostMs}")),
            ("a cast is kept for nobody", (HEADER, "detail::states[monk] = {mantra, now + boostMs};",
                                           "detail::states[0] = {mantra, now + boostMs};")),
            ("a logout forgets nothing", (HEADER, "detail::states.erase(monk);", "(void)monk;")),
            ("the key ignores the Monk", (HEADER, "return (monk << 32) | (id & 0xFFFFFFFFull);",
                                          "return id & 0xFFFFFFFFull;")),
            ("the key ignores the rune", (HEADER, "return (monk << 32) | (id & 0xFFFFFFFFull);", "return monk << 32;")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


def function_body(text, signature):
    """The text from `signature` to the closing brace of the function it opens (4-space or deeper indentation)."""
    at = text.index(signature)
    open_at = text.index("{", at)
    depth = 0
    for index in range(open_at, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[open_at:index + 1]
    raise AssertionError(signature)


# The always-on hook, per Mantra: the call it makes.
MANTRAS = {
    "Salvation": "Salvation::Touch(player);",
    "Retribution": "Retribution::Touch(player);",
    "Healing": "Healing::Touch(player);",
    "Conviction": "Conviction::Touch(player);",
}
# What would be a state of a Mantra's own beside the shared one.
OWN_STATE = ("Slot slot", "Slot>", ".mantra.", "MantraState", "current_")


def hook_starts(hook_text, call):
    """Whether the always-on hook calls `call` from Start, and Start from the update, with the first look at login."""
    start = function_body(hook_text, "void Start(Player* player)")
    update = function_body(hook_text, "void OnPlayerUpdate(Player* player, std::uint32_t diff) override")
    first_look = "waited[player->GetGUID().GetRawValue()] = 0;" in update and "Start(player);" in update
    return call in start and first_look


class Always(unittest.TestCase):
    def setUp(self):
        self.hook = monk_source.hook()

    def check(self, name):
        call = MANTRAS[name]
        # the hook starts this Mantra at login (the first update looks at once) and then on the poll
        self.assertTrue(hook_starts(self.hook, call), f"{name}: the hook does not start it")
        # and the check can fail: the same hook text without this Mantra's line is refused
        self.assertFalse(hook_starts(self.hook.replace(call, ""), call), f"{name}: the check cannot fail")
        self.assertFalse(hook_starts(self.hook.replace("waited[player->GetGUID().GetRawValue()] = 0;", ""), call),
                         f"{name}: the login look is not checked")
        code = monk_source.section(name)
        # the starter is the shared loop's (test_the_shared_loop_starts_from_the_bar), and the press the shared one, which
        # alone writes the shared state
        self.assertIn("Mantras::StartPulse(flavour, player);", function_body(code, "void Touch(Player* player)"), name)
        cast = function_body(code, "void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)")
        self.assertIn("Mantras::Press(flavour, player, spellId, targets);", cast, name)
        self.assertNotIn("Mantras::Cast(", code, f"{name}: writes the shared state itself")
        # the Mantra keeps no state of its own
        for own in OWN_STATE:
            self.assertNotIn(own, code, f"{name}: keeps a state of its own ({own})")

    def test_salvation_passive_is_on_at_login_with_no_cast(self):
        self.check("Salvation")

    def test_retribution_passive_is_on_at_login_with_no_cast(self):
        self.check("Retribution")

    def test_healing_passive_is_on_at_login_with_no_cast(self):
        self.check("Healing")

    def test_conviction_passive_is_on_at_login_with_no_cast(self):
        self.check("Conviction")

    def test_the_shared_loop_starts_from_the_bar(self):
        mechanism = monk_source.mechanism()
        start = function_body(mechanism, "void StartPulse(Flavour const& flavour, Player* player)")
        beat = function_body(mechanism, "void Beat(Flavour const& flavour, Player* owner, std::uint64_t generation)")
        # the starter needs the skill on the bar, not a cast: neither it nor the beat reads or writes the cast state
        # to stay quiet; both read the one shared state
        for body in (start, beat):
            self.assertNotIn("Mantras::Cast(", body)
            self.assertIn("Mantras::On(guid, BaseId(flavour.skill))", body)
        self.assertIn("flavour.runs(Slotted(player, flavour.skill))", start)
        # one cast writes the shared state, for all four: the press
        press = function_body(mechanism,
                              "void Press(Flavour const& flavour, Player* player, std::uint32_t spellId, "
                              "std::vector<Unit*> const& targets)")
        self.assertEqual(press.count("Mantras::Cast("), 1)
        self.assertEqual(monk_source.mantras().count("Mantras::Cast("), 1)
        for own in OWN_STATE:
            self.assertNotIn(own, monk_source.mantras())

    def test_the_hook_is_registered_once_through_the_monks_scripts(self):
        monk = (MONK / "dc_monk.cpp").read_text(encoding="utf-8")
        self.assertEqual(monk.count("Mantras::RegisterScripts();"), 1)
        self.assertEqual(len(re.findall(r"^\s*void RegisterScripts\(\)\s*$", monk, flags=re.M)), 1)
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.assertEqual(combat.count("Monk::RegisterScripts();"), 1)
        self.assertIn("new Always();", self.hook)

    def test_the_hook_watches_the_bar_again_and_forgets_a_logout(self):
        self.assertIn("PLAYERHOOK_ON_UPDATE", self.hook)
        self.assertIn("PLAYERHOOK_ON_LOGOUT", self.hook)
        logout = function_body(self.hook, "void OnPlayerLogout(Player* player) override")
        self.assertIn("Forget(guid);", logout)
        self.assertIn("waited.erase(guid);", logout)


class Unity(unittest.TestCase):
    def test_unity_asks_the_shared_state_which_mantra_is_in_force(self):
        code = (MONK / "dc_monk_passives_harmony.cpp").read_text(encoding="utf-8")
        body = function_body(code, "std::uint32_t SlottedMantra(Player* player)")
        self.assertIn("Mantras::On(player->GetGUID().GetRawValue(), BaseMantra(row->skill))", body)
        # and the check can fail: without the shared-state read any slotted Mantra counts
        self.assertNotIn("Mantras::On(", body.replace("Mantras::On(player->GetGUID().GetRawValue(), BaseMantra(row->skill))", ""))


class TwoMonks(unittest.TestCase):
    def test_healing_keeps_what_a_holder_wears_per_monk(self):
        code = monk_source.section("Healing")
        self.assertIn("std::map<std::pair<std::uint64_t, std::uint64_t>, Worn> worn;", code)
        wear = function_body(code, "void Wear(Player* owner, Player* holder, std::uint32_t runeId)")
        release = function_body(code, "void Release(std::uint64_t owner, std::uint64_t guid)")
        for body in (wear, release):
            self.assertIn("Mantras::Key(", body)
            self.assertNotIn("Stat::LifePercent, Mantras::BaseId(Skill))", body)
            self.assertNotIn("Stat::SpecificReduction, Mantras::BaseId(Skill))", body)
        self.assertIn("Release(guid, left);", code)
        self.assertIn("Wear(owner, holder, runeId);", code)

    def test_transgression_is_keyed_by_the_monk_that_gives_it(self):
        code = monk_source.section("Retribution")
        give = function_body(code, "void Give(Player* monk, Player* who, std::uint32_t runeId, bool recompute)")
        take = function_body(code, "void Take(std::uint64_t monk, std::uint64_t guid, std::uint32_t runeId)")
        self.assertIn("Mantras::Key(monk->GetGUID().GetRawValue(), runeId)", give)
        self.assertIn("Mantras::Key(monk, runeId)", take)
        self.assertIn("Take(self, guid, runeId);", code)


if __name__ == "__main__":
    unittest.main()
