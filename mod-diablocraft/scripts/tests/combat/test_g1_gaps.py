"""G1 gaps: a per-player gap on DCSLOT, DCPASSIVE and Paragon allocate/deallocate, and the
Paragon module lock released across the commit wait (brief claude-combat-g1-gaps-brief).

The gap tests compile the production helper (dc_request_gap.h) and the production gate
functions cut out of dc_classes.cpp and dc_paragon.cpp, and drive them with the value the
generator wrote into tunables_0003.sql. The lock tests compile the production WithoutLock
and read StorePoints. Each test names the change that must make it fail.
"""
import re
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_class_parity import MODULE, SRC, definition, mutate, run

CLASSES = (SRC / "classes/dc_classes.cpp").read_text(encoding="utf-8")
PARAGON = (SRC / "paragon/dc_paragon.cpp").read_text(encoding="utf-8")
GAP_H = (SRC / "common/dc_request_gap.h").read_text(encoding="utf-8")
MATH_H = (SRC / "paragon/dc_paragon_math.h").read_text(encoding="utf-8")
GENERATED = (MODULE / "data/generated/tunables_0003.sql").read_text(encoding="utf-8")


def generated(category, name):
    """The value the generator emits for one tunable row."""
    match = re.search(r"\('%s', '%s', (?:NULL|[0-9.]+), ([0-9.]+|NULL)," % (category, name), GENERATED)
    assert match and match.group(1) != "NULL", f"{category}/{name} is not in tunables_0003.sql"
    return float(match.group(1))


def compile_gap(harness_body, gate_source, header=GAP_H, tunable_line=""):
    """Run `harness_body` against the production header and the cut gate source."""
    code = r'''
#include <cassert>
#include <chrono>
#include <cstdint>
#include <string>
#include <thread>
namespace DC::Tunables { double value = 0; double Get(std::string const&, std::string const&) { return value; } }
''' + header.replace('#include "dc_request_gap.h"', "") + r'''
struct Guid { std::uint64_t id; std::uint64_t GetRawValue() const { return id; } };
struct Player { Guid guid; Guid GetGUID() const { return guid; } };
struct Probe {
''' + gate_source + r'''
};
int main() {
''' + harness_body + r'''
    return 0;
}
'''
    return run(code)


def bridge_gate(source=CLASSES):
    return "DC::Gap::PerPlayer slotGap_, passiveGap_;\n" + definition(source, "static bool Admit(DC::Gap::PerPlayer& gap")


def paragon_gate(source=PARAGON):
    return "static inline DC::Gap::PerPlayer editGap;\n" + definition(source, "static bool EditGapOpen(")


class GapHelper(unittest.TestCase):
    def test_second_request_inside_the_gap_is_refused_then_allowed(self):
        gap = int(generated("combat", "skill_slot_gap_ms"))
        ok, out = compile_gap(f'''
    DC::Gap::PerPlayer g;
    assert(g.Admit(1, 1000, {gap}));                 // first request goes through
    assert(!g.Admit(1, 1000 + {gap} - 1, {gap}));    // one ms inside the gap: refused
    assert(g.Admit(2, 1000 + 1, {gap}));             // another player is not held
    assert(g.Admit(1, 1000 + {gap}, {gap}));         // measured from the admitted one: allowed
''', "")
        self.assertTrue(ok, out)

    def test_a_refused_request_does_not_extend_the_wait(self):
        ok, out = compile_gap('''
    DC::Gap::PerPlayer g;
    assert(g.Admit(1, 1000, 200));
    assert(!g.Admit(1, 1150, 200));      // refused 150 ms in
    assert(g.Admit(1, 1200, 200));       // still allowed 200 ms after the ADMITTED one
''', "")
        self.assertTrue(ok, out)
        stamps = GAP_H.replace("        auto found = last_.find(player);\n        if (found != last_.end() && Cooling(nowMs, true, found->second, gapMs))\n            return false;",
                               "        auto found = last_.find(player);\n        if (found != last_.end() && Cooling(nowMs, true, found->second, gapMs))\n            { found->second = nowMs; return false; }")
        self.assertNotEqual(stamps, GAP_H)
        ok, _ = compile_gap('''
    DC::Gap::PerPlayer g;
    assert(g.Admit(1, 1000, 200));
    assert(!g.Admit(1, 1150, 200));
    assert(g.Admit(1, 1200, 200));
''', "", header=stamps)
        self.assertFalse(ok)

    def test_zero_is_off_and_a_bad_row_is_off(self):
        ok, out = compile_gap('''
    DC::Gap::PerPlayer g;
    assert(g.Admit(1, 1000, 0) && g.Admit(1, 1000, 0));
    assert(DC::Gap::GapFromTunable(0) == 0);
    assert(DC::Gap::GapFromTunable(-5) == 0);                 // a negative row must not wrap into a huge gap
    assert(DC::Gap::GapFromTunable(1e300) == 0);
    assert(DC::Gap::GapFromTunable(150) == 150);
''', "")
        self.assertTrue(ok, out)
        broken = GAP_H.replace("milliseconds > 0.0 && ", "")
        self.assertNotEqual(broken, GAP_H)
        ok, _ = compile_gap("    assert(DC::Gap::GapFromTunable(-5) == 0);", "", header=broken)
        self.assertFalse(ok)

    def test_a_helper_that_never_refuses_fails(self):
        broken = mutate(GAP_H, "return false;\n        // An entry", "return true;\n        // An entry")
        ok, _ = compile_gap("    DC::Gap::PerPlayer g; assert(g.Admit(1, 1000, 150)); assert(!g.Admit(1, 1001, 150));", "", header=broken)
        self.assertFalse(ok)


class HandlerGates(unittest.TestCase):
    """The production gate functions, driven with the generated values."""

    def drive(self, gate, call, tunable):
        value = generated(*tunable)
        return compile_gap(f'''
    Probe p; Player a{{{{1}}}}, b{{{{2}}}};
    DC::Tunables::value = {value};
    assert({call.format(player="a")});                    // first goes through
    assert(!{call.format(player="a")});                   // second inside the gap: refused
    assert({call.format(player="b")});                    // a different player is not held
    std::this_thread::sleep_for(std::chrono::milliseconds({int(value) + 60}));
    assert({call.format(player="a")});                    // allowed after the gap
    DC::Tunables::value = 0;
    assert({call.format(player="a")} && {call.format(player="a")});  // 0 = off
''', gate)

    def test_dcslot_gate(self):
        ok, out = self.drive(bridge_gate(), "Probe::Admit(p.slotGap_, &{player}, \"skill_slot_gap_ms\")", ("combat", "skill_slot_gap_ms"))
        self.assertTrue(ok, out)

    def test_dcpassive_gate(self):
        ok, out = self.drive(bridge_gate(), "Probe::Admit(p.passiveGap_, &{player}, \"passive_slot_gap_ms\")", ("combat", "passive_slot_gap_ms"))
        self.assertTrue(ok, out)

    def test_paragon_gate(self):
        ok, out = self.drive(paragon_gate(), "Probe::EditGapOpen(&{player})", ("paragon", "allocate_gap_ms"))
        self.assertTrue(ok, out)

    def test_gates_read_their_own_rows(self):
        self.assertIn('"combat", tunable', bridge_gate())
        self.assertIn('"allocate_gap_ms"', paragon_gate())

    def test_a_gate_that_admits_everything_fails(self):
        broken = bridge_gate().replace("return gap.Admit(", "return true || gap.Admit(")
        self.assertNotEqual(broken, bridge_gate())
        ok, _ = self.drive(broken, "Probe::Admit(p.slotGap_, &{player}, \"skill_slot_gap_ms\")", ("combat", "skill_slot_gap_ms"))
        self.assertFalse(ok)
        broken = paragon_gate().replace("!player || ", "true || ")
        ok, _ = self.drive(broken, "Probe::EditGapOpen(&{player})", ("paragon", "allocate_gap_ms"))
        self.assertFalse(ok)

    def test_handlers_call_the_gates_before_the_write(self):
        bridge = definition(CLASSES, "void OnPlayerBeforeSendChatMessage(")
        slot = bridge.index('parts[0] == "DCSLOT"')
        passive = bridge.index('parts[0] == "DCPASSIVE"')
        self.assertLess(bridge.index("Admit(slotGap_", slot), bridge.index("SetSlot(player"))
        self.assertLess(bridge.index("Admit(passiveGap_", passive), bridge.index("SetPassive(player"))
        edit = definition(PARAGON, "static bool Edit(ChatHandler* h")
        self.assertLess(edit.index("EditGapOpen("), edit.index("return Run("))
        # allocate and deallocate both go through Edit
        self.assertIn("Edit(h,key,amount,true)", PARAGON)
        self.assertIn("Edit(h,key,amount,false)", PARAGON)
        # A handler with its gate call cut out fails.
        self.assertNotIn("Admit(slotGap_", bridge.replace("if (!Admit(slotGap_, player, \"skill_slot_gap_ms\"))", ""))


class ParagonLock(unittest.TestCase):
    def test_lock_is_free_during_the_wait_and_taken_again_after(self):
        ok, out = compile_gap(r'''
    std::mutex m;
    std::unique_lock<std::mutex> lock(m);
    bool freeDuring = false;
    int result = DC::Paragon::WithoutLock(lock, [&] {
        std::thread other([&] { freeDuring = m.try_lock(); if (freeDuring) m.unlock(); });
        other.join();
        return 7;
    });
    assert(result == 7 && freeDuring);
    assert(lock.owns_lock());                      // held again for the shared state
    bool threw = false;
    try { DC::Paragon::WithoutLock(lock, [&]() -> int { throw std::runtime_error("commit failed"); }); }
    catch (std::runtime_error const&) { threw = true; }
    assert(threw && lock.owns_lock());             // and held again on a throw
''', "", header="#include <mutex>\n#include <stdexcept>\n#include <thread>\nnamespace DC::Paragon {\n" + self.wrapper(MATH_H) + "\n}\n")
        self.assertTrue(ok, out)

    @staticmethod
    def wrapper(text):
        return definition(text, "template<class Lock, class Wait> auto WithoutLock(")

    def test_a_wait_that_keeps_the_lock_fails(self):
        broken = self.wrapper(MATH_H).replace("    lock.unlock();\n", "", 1)
        self.assertNotEqual(broken, self.wrapper(MATH_H))
        ok, _ = compile_gap(r'''
    std::mutex m;
    std::unique_lock<std::mutex> lock(m);
    bool freeDuring = false;
    DC::Paragon::WithoutLock(lock, [&] {
        std::thread other([&] { freeDuring = m.try_lock(); if (freeDuring) m.unlock(); });
        other.join();
        return 0;
    });
    assert(freeDuring);
''', "", header="#include <mutex>\n#include <stdexcept>\n#include <thread>\nnamespace DC::Paragon {\n" + broken + "\n}\n")
        self.assertFalse(ok)

    def test_store_points_awaits_the_commit_without_the_lock(self):
        store = definition(PARAGON, "void StorePoints(")
        without = re.search(r"WithoutLock\(lock, \[&\]\s*\{(.*?)\n        \}\);", store, re.S)
        self.assertIsNotNone(without, "the commit wait must run inside WithoutLock")
        inside = without.group(1)
        self.assertIn("AsyncCommitTransaction(tx).m_future.get()", inside)
        self.assertIn("ReadPoints(", inside)
        self.assertEqual(store.count("m_future.get()"), 1)
        # Shared state is touched only with the lock held: ReplaceParagon is outside the wait.
        self.assertNotIn("ReplaceParagon", inside)
        self.assertNotIn("ready", inside)
        # Two changes to one character cannot overlap while the lock is free.
        self.assertLess(store.index("Need(!state.saving"), store.index("state.saving = true"))
        self.assertLess(store.index("state.saving = true"), store.index("WithoutLock"))
        self.assertLess(store.index("WithoutLock"), store.index("state.saving = false"))
        # A store with the wait moved back under the lock fails this test.
        held = store.replace("saved = WithoutLock(lock, [&]", "saved = ([&]").replace("        });\n    }\n    catch", "        })();\n    }\n    catch", 1)
        self.assertNotEqual(held, store)
        self.assertIsNone(re.search(r"WithoutLock\(lock, \[&\]\s*\{(.*?)\n        \}\);", held, re.S))

    def test_run_hands_the_lock_to_edit_and_respec(self):
        self.assertIn("std::unique_lock<std::mutex> lock(mutex);", definition(PARAGON, "template<class Action> static bool Run("))
        self.assertEqual(len(re.findall(r"StorePoints\(p,state,[^;]*,lock\)", PARAGON)), 2)


if __name__ == "__main__":
    unittest.main()
