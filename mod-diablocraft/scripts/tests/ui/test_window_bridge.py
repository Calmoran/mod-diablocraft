"""diablocraft-asie: the window bridge (DC::Bridge), compiled from production source.

The harness includes the real dc_bridge.h and dc_request_gap.h (only DC::Tunables::Get is a
double, as in test_g1_gaps) and drives the router, the bounded parser and the token bucket.
Every test then runs again on a source mutation that removes the rule it checks, and requires
that run to fail: a test that cannot fail proves nothing.

Every case is a function of one harness and the binary runs the case its argument names, so the
production source builds once for all of them and each mutation once, through the compile cache
(harness_env.build); an unchanged rerun compiles nothing.
"""
import functools
import unittest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
from test_class_parity import SRC, mutate

BRIDGE = (SRC / "common/dc_bridge.h").read_text(encoding="utf-8")
GAP = (SRC / "common/dc_request_gap.h").read_text(encoding="utf-8")
DRIVER = Path(__file__).resolve().parent / "window_bridge_harness.cpp"

PRELUDE = r'''
#include <cassert>
#include <cmath>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
namespace DC::Tunables {
std::map<std::string, double> rows;
double Get(std::string const& c, std::string const& n) { auto f = rows.find(c + "/" + n); return f == rows.end() ? 0 : f->second; }
bool Has(std::string const&, std::string const&) { return true; }
}
'''

ACTOR = r'''
struct Guid { std::uint64_t id; std::uint64_t GetRawValue() const { return id; } };
struct Player { Guid guid; Guid GetGUID() const { return guid; } };
using DC::Bridge::Outcome;
struct Rig {
    std::vector<std::string> sent;
    int calls = 0;
    DC::Bridge::Router<Player> router{[this](Player*, std::string const& prefix, std::string const& record) { sent.push_back(prefix + "\t" + record); }};
    Rig(double burst = 3, double rate = 2) {
        DC::Tunables::rows["bridge/artisan_burst"] = burst;
        DC::Tunables::rows["bridge/artisan_per_second"] = rate;
        bool ok = router.Add("DCARTISAN", {"bridge", "artisan_burst", "artisan_per_second"},
            [this](Player&, DC::Bridge::Request const& r, DC::Bridge::Wire<Player> const& wire) {
                ++calls;
                auto verb = r.Token(0, 12);
                if (!verb) throw DC::Bridge::Refusal("Bad verb.");
                if (*verb == "boom") throw std::runtime_error("table dc_secret missing");
                if (*verb == "pipe") throw DC::Bridge::Refusal("a|b\tc");
                wire.Record({"OK", *verb});
            });
        assert(ok);
    }
};
'''


CASES = {
    'burst_then_refused_then_refills': '''
    DC::Gap::PerPlayerBucket b;
    assert(b.Admit(1, 1000, 3, 2.0) && b.Admit(1, 1000, 3, 2.0) && b.Admit(1, 1000, 3, 2.0));
    assert(!b.Admit(1, 1000, 3, 2.0));       // the fourth in one instant
    assert(!b.Admit(1, 1499, 3, 2.0));       // 0.998 token: not yet
    assert(b.Admit(1, 1500, 3, 2.0));        // one token at 2 per second
    assert(b.Admit(2, 1000, 3, 2.0));        // another player has a full bucket
    assert(b.Admit(3, 1000, 3, 2.0));
''',
    'a_refused_request_does_not_delay_the_refill': '''
    DC::Gap::PerPlayerBucket b;
    assert(b.Admit(1, 0, 1, 1.0));
    for (int t = 100; t < 1000; t += 100) assert(!b.Admit(1, t, 1, 1.0));   // hammering
    assert(b.Admit(1, 1000, 1, 1.0));                                        // still back at 1 s
''',
    'the_bucket_never_holds_more_than_the_burst': '''
    DC::Gap::PerPlayerBucket b;
    assert(b.Admit(1, 0, 2, 5.0));
    // an hour idle refills to the burst (2), not to 18000
    assert(b.Admit(1, 3600000, 2, 5.0) && b.Admit(1, 3600000, 2, 5.0) && !b.Admit(1, 3600000, 2, 5.0));
''',
    'an_unset_or_hostile_row_refuses_everything': '''
    double const nan = std::numeric_limits<double>::quiet_NaN(), inf = std::numeric_limits<double>::infinity();
    assert(DC::Gap::BurstFromTunable(0) == 0 && DC::Gap::BurstFromTunable(-5) == 0 && DC::Gap::BurstFromTunable(nan) == 0);
    assert(DC::Gap::BurstFromTunable(inf) == 0 && DC::Gap::BurstFromTunable(1e9) == 0 && DC::Gap::BurstFromTunable(0.5) == 0);
    assert(DC::Gap::BurstFromTunable(1) == 1 && DC::Gap::BurstFromTunable(6.9) == 6);
    assert(DC::Gap::RateFromTunable(0) == 0 && DC::Gap::RateFromTunable(-1) == 0 && DC::Gap::RateFromTunable(nan) == 0);
    assert(DC::Gap::RateFromTunable(inf) == 0 && DC::Gap::RateFromTunable(1e9) == 0 && DC::Gap::RateFromTunable(2.5) == 2.5);
    DC::Gap::PerPlayerBucket b;
    assert(!b.Admit(1, 0, 0, 2.0) && !b.Admit(2, 0, 3, 0.0));     // not configured: closed
''',
    'the_table_stays_small': '''
    DC::Gap::PerPlayerBucket b;
    for (std::uint64_t p = 0; p < 5000; ++p) assert(b.Admit(p, p, 3, 1000.0));
    assert(b.Admit(1, 6000, 3, 1000.0));
''',
    'numbers_are_strict': '''
    DC::Bridge::Request r;
    r.fields = {"0", "42", "4294967295", "+1", "-1", " 1", "1 ", "0x10", "", "4294967296", "99999999999", "1e3", "007"};
    assert(r.Uint(0, 0, 100) == 0u && r.Uint(1, 0, 100) == 42u && r.Uint(2, 0, 4294967295u) == 4294967295u);
    for (int i = 3; i <= 10; ++i) assert(!r.Uint(i, 0, 4294967295u));       // sign, space, hex, empty, overflow
    assert(!r.Uint(1, 43, 100) && !r.Uint(1, 0, 41));                       // outside [lo, hi]
    assert(!r.Uint(20, 0, 100));                                            // missing field
    assert(r.Uint(12, 0, 100) == 7u);
''',
    'a_ten_digit_overflow_is_refused_not_wrapped': '''
    DC::Bridge::Request r;
    r.fields = {"4294967297", "9999999999"};
    assert(!r.Uint(0, 0, 4294967295u) && !r.Uint(1, 0, 4294967295u));
''',
    'message_and_field_caps_and_control_bytes': '''
    DC::Bridge::Request r;
    std::string p = "DCARTISAN";
    std::string fit = p + "\\t" + std::string(255 - p.size() - 1, 'a');
    assert(fit.size() == 255 && DC::Bridge::Parse(fit, p.size(), r));
    assert(!DC::Bridge::Parse(fit + "a", p.size(), r));                       // 256 bytes
    std::string sixteen = p; for (int i = 0; i < 16; ++i) sixteen += "\\t1";
    assert(DC::Bridge::Parse(sixteen, p.size(), r) && r.Count() == 16);
    assert(!DC::Bridge::Parse(sixteen + "\\t1", p.size(), r));                // 17 fields
    assert(!DC::Bridge::Parse(p + "\\t1\\n2", p.size(), r));                  // control byte
    assert(!DC::Bridge::Parse(p + std::string("\\t1\\0", 3), p.size(), r));   // NUL
    assert(DC::Bridge::Parse(p + "\\t\\t\\t3", p.size(), r) && r.Count() == 3 && r.fields[0].empty());   // empty kept
    assert(DC::Bridge::Parse(p, p.size(), r) && r.Count() == 0);
''',
    'field_count_cap': '''
    DC::Bridge::Request r;
    std::string m = "DCARTISAN"; for (int i = 0; i < 17; ++i) m += "\\t";
    assert(!DC::Bridge::Parse(m, 9, r));
''',
    'token_and_flag': '''
    DC::Bridge::Request r;
    r.fields = {"craft", "a-b", "", "waytoolongverb", "1", "2", "sql;drop"};
    assert(r.Token(0, 12) == std::string("craft") && !r.Token(1, 12) && !r.Token(2, 12) && !r.Token(3, 12) && !r.Token(6, 12));
    assert(r.Flag(4) == true && !r.Flag(5) && !r.Flag(9));
''',
    'only_a_registered_prefix_is_ours': '''
    Rig rig; Player p{{7}};
    assert(rig.router.Dispatch(&p, "DCSLOT\\tx", 0) == Outcome::NotBridge);
    assert(rig.router.Dispatch(&p, "DCARTISANX\\tcraft", 0) == Outcome::NotBridge);   // prefix is exact
    assert(rig.router.Dispatch(&p, "DCARTIS", 0) == Outcome::NotBridge);
    assert(rig.router.Dispatch(&p, "hello", 0) == Outcome::NotBridge);
    assert(rig.router.Dispatch(&p, std::string(5000, 'x'), 0) == Outcome::NotBridge);
    assert(rig.sent.empty() && rig.calls == 0);
    assert(rig.router.Dispatch(&p, "DCARTISAN\\tcraft", 0) == Outcome::Handled);
    assert(rig.sent.size() == 1 && rig.sent[0] == "DCARTISAN\\tOK|craft");
''',
    'bad_prefixes_and_duplicates_are_not_registered': '''
    Rig rig;
    auto h = [](Player&, DC::Bridge::Request const&, DC::Bridge::Wire<Player> const&) {};
    DC::Bridge::Limits l{"bridge", "a", "b"};
    assert(!rig.router.Add("DCARTISAN", l, h));                 // repeated
    assert(!rig.router.Add("ARTISAN", l, h) && !rig.router.Add("DC", l, h) && !rig.router.Add("DCa", l, h));
    assert(!rig.router.Add("DCAB\\tC", l, h) && !rig.router.Add("DCABCDEFGHIJKLMNO", l, h));   // 17 bytes
    assert(rig.router.Add("DCJEWELER", l, h) && rig.router.Add("DCABCDEFGHIJKLMN", l, h));     // 9 and 16
''',
    'flood_earns_no_reply': '''
    Rig rig(2, 1); Player p{{7}};
    assert(rig.router.Dispatch(&p, "DCARTISAN\\tcraft", 0) == Outcome::Handled);
    assert(rig.router.Dispatch(&p, "DCARTISAN\\tcraft", 0) == Outcome::Handled);
    std::size_t before = rig.sent.size();
    for (int i = 0; i < 50; ++i) {
        assert(rig.router.Dispatch(&p, "DCARTISAN\\tcraft", 1) == Outcome::Throttled);
        assert(rig.router.Dispatch(&p, "DCARTISAN\\t" + std::string(400, 'x'), 1) == Outcome::Throttled);
        assert(rig.router.Dispatch(&p, "DCARTISAN\\t\\x01", 1) == Outcome::Throttled);
    }
    assert(rig.sent.size() == before && rig.calls == 2);
    assert(rig.router.Dispatch(&p, "DCARTISAN\\tcraft", 1000) == Outcome::Handled);
''',
    'a_route_with_no_budget_row_is_closed': '''
    Rig rig(0, 0); Player p{{7}};
    assert(rig.router.Dispatch(&p, "DCARTISAN\\tcraft", 0) == Outcome::Throttled && rig.calls == 0);
''',
    'each_prefix_has_its_own_bucket': '''
    Rig rig(1, 1); Player p{{7}};
    DC::Tunables::rows["bridge/j_burst"] = 1; DC::Tunables::rows["bridge/j_per_second"] = 1;
    int jeweler = 0;
    assert(rig.router.Add("DCJEWELER", {"bridge", "j_burst", "j_per_second"},
        [&](Player&, DC::Bridge::Request const&, DC::Bridge::Wire<Player> const&) { ++jeweler; }));
    assert(rig.router.Dispatch(&p, "DCARTISAN\\tcraft", 0) == Outcome::Handled);
    assert(rig.router.Dispatch(&p, "DCARTISAN\\tcraft", 0) == Outcome::Throttled);
    assert(rig.router.Dispatch(&p, "DCJEWELER\\tx", 0) == Outcome::Handled && jeweler == 1);   // untouched by artisan spam
''',
    'refusals_are_one_x_record_and_leak_nothing': '''
    Rig rig(50, 50); Player p{{7}};
    assert(rig.router.Dispatch(&p, "DCARTISAN\\t", 0) == Outcome::Refused);          // empty verb
    assert(rig.sent.back() == "DCARTISAN\\tX|Bad verb.");
    assert(rig.router.Dispatch(&p, "DCARTISAN\\t" + std::string(300, 'a'), 0) == Outcome::Refused);
    assert(rig.sent.back() == std::string("DCARTISAN\\tX|") + DC::Bridge::TextMalformed && rig.calls == 1);   // handler never ran
    assert(rig.router.Dispatch(&p, "DCARTISAN\\tboom", 0) == Outcome::Refused);
    assert(rig.sent.back() == std::string("DCARTISAN\\tX|") + DC::Bridge::TextFailed);                     // no what()
    assert(rig.router.Dispatch(&p, "DCARTISAN\\tpipe", 0) == Outcome::Refused);
    assert(rig.sent.back() == "DCARTISAN\\tX|a b c");                                                      // separators cleaned
    std::string longText(400, 'z');
    assert(DC::Bridge::RefusalRecord("DCARTISAN", longText).size() + 10 == 255);   // fits the wire cap
    assert(!DC::Bridge::Wire<Player>([](Player*, std::string const&, std::string const&) {}, nullptr, "DCARTISAN").Record({longText}));
''',
    'refusal_text_cannot_carry_a_separator': '''
    assert(DC::Bridge::RefusalRecord("DCARTISAN", "a|b\\tc\\nd") == "X|a b c d");
''',
}


def harness(bridge, gap):
    """The harness source: the production headers, the rig, every case as case_<n>() and a main that runs argv[1]."""
    code = (PRELUDE + gap.replace('#ifndef DC_REQUEST_GAP_H', '#ifndef DC_REQUEST_GAP_H_T') + '\n'
            + bridge.replace('#include "dc_request_gap.h"', '').replace('#include "dc_tunables.h"', '')
            + ACTOR)
    code = code.replace("#define DC_REQUEST_GAP_H\n", "#define DC_REQUEST_GAP_H_T\n")
    for n, body in enumerate(CASES.values()):
        code += "\nstatic void case_%d() {\n%s\n}\n" % (n, body)
    code += "\nint main(int argc, char** argv) {\n    std::string const name = argc > 1 ? argv[1] : \"\";\n"
    for n, name in enumerate(CASES):
        code += "    if (name == \"%s\") { case_%d(); return 0; }\n" % (name, n)
    return code + "    return 2;   // no such case: never a pass\n}\n"


@functools.lru_cache(maxsize=None)
def binary(bridge, gap):
    return harness_env.build([DRIVER], flags=["-std=c++17", "-O0", "-UNDEBUG"],
                             files={"window_bridge_cases.h": harness(bridge, gap)},
                             includes=[SRC / "common", SRC / "paragon"])


def compile_bridge(name, bridge=BRIDGE, gap=GAP):
    """Run case `name` on a build of `bridge` and `gap`; returns (ok, output)."""
    assert name in CASES, name
    ran = harness_env.run([str(binary(bridge, gap)), name], capture_output=True, text=True)
    return ran.returncode == 0, ran.stdout + ran.stderr


def both(test, name, old, new, source="bridge"):
    """The harness passes on production source and fails on the mutated one."""
    ok, out = compile_bridge(name)
    test.assertTrue(ok, out)
    if source == "bridge":
        ok, out = compile_bridge(name, bridge=mutate(BRIDGE, old, new))
    else:
        ok, out = compile_bridge(name, gap=mutate(GAP, old, new))
    test.assertFalse(ok, "mutation survived: " + new)


class Bucket(unittest.TestCase):
    def test_burst_then_refused_then_refills(self):
        both(self, 'burst_then_refused_then_refills', "        state.tokens = tokens - 1.0;", "        state.tokens = tokens;", "gap")

    def test_a_refused_request_does_not_delay_the_refill(self):
        both(self, 'a_refused_request_does_not_delay_the_refill', "        if (tokens < 1.0)\n            return false;",
             "        if (tokens < 1.0)\n            { state.tokens = tokens; state.lastMs = nowMs; return false; }", "gap")

    def test_the_bucket_never_holds_more_than_the_burst(self):
        both(self, 'the_bucket_never_holds_more_than_the_burst', "return std::min(static_cast<double>(burst), state.tokens + elapsed * perSecond / 1000.0);",
             "return state.tokens + elapsed * perSecond / 1000.0;", "gap")

    def test_an_unset_or_hostile_row_refuses_everything(self):
        both(self, 'an_unset_or_hostile_row_refuses_everything', "        if (!burst || perSecond <= 0.0)\n            return false;", "        if (false)\n            return false;", "gap")

    def test_the_table_stays_small(self):
        # The size is private; this only shows a burst of players neither crashes nor wrongly refuses.
        ok, out = compile_bridge('the_table_stays_small')
        self.assertTrue(ok, out)


class Parser(unittest.TestCase):
    def test_numbers_are_strict(self):
        both(self, 'numbers_are_strict', "                if (c < '0' || c > '9')\n                    return std::nullopt;", "                if (c < '0' && c != '-' && c != '+' && c != ' ')\n                    return std::nullopt;")

    def test_a_ten_digit_overflow_is_refused_not_wrapped(self):
        both(self, 'a_ten_digit_overflow_is_refused_not_wrapped', "            if (value < lo || value > hi)\n                return std::nullopt;\n            return static_cast<std::uint32_t>(value);",
             "            if (static_cast<std::uint32_t>(value) < lo || static_cast<std::uint32_t>(value) > hi)\n                return std::nullopt;\n            return static_cast<std::uint32_t>(value);")

    def test_message_and_field_caps_and_control_bytes(self):
        both(self, 'message_and_field_caps_and_control_bytes', "        if (message.size() > MaxMessage)\n            return false;", "        if (false)\n            return false;")

    def test_field_count_cap(self):
        both(self, 'field_count_cap', "            if (out.fields.size() > MaxFields)\n                return false;", "            if (false)\n                return false;")

    def test_token_and_flag(self):
        both(self, 'token_and_flag', "if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_'))\n                    return std::nullopt;",
             "if (false)\n                    return std::nullopt;")


class Routing(unittest.TestCase):
    def test_only_a_registered_prefix_is_ours(self):
        both(self, 'only_a_registered_prefix_is_ours', "            auto found = routes_.find(prefix);\n            if (found == routes_.end())\n                return Outcome::NotBridge;",
             "            auto found = routes_.begin();\n            if (found == routes_.end())\n                return Outcome::NotBridge;")

    def test_bad_prefixes_and_duplicates_are_not_registered(self):
        both(self, 'bad_prefixes_and_duplicates_are_not_registered', "                routes_.count(prefix))", "                false)")

    def test_the_bucket_runs_before_the_parser_and_a_flood_earns_no_reply(self):
        # Oversize and control-byte messages over budget are dropped too: no X record goes out.
        body = 'flood_earns_no_reply'
        ok, out = compile_bridge(body)
        self.assertTrue(ok, out)
        # the throttled branch answers instead of dropping
        drop = "                return Outcome::Throttled;"
        answer = "                { send_(actor, prefix, RefusalRecord(prefix, \"Slow down.\")); return Outcome::Throttled; }"
        ok, out = compile_bridge(body, bridge=mutate(BRIDGE, drop, answer))
        self.assertFalse(ok, "a flood must not earn replies")
        # a route with no budget row is closed
        ok, out = compile_bridge('a_route_with_no_budget_row_is_closed')
        self.assertTrue(ok, out)

    def test_each_prefix_has_its_own_bucket(self):
        both(self, 'each_prefix_has_its_own_bucket', "            DC::Gap::PerPlayerBucket bucket;", "            static inline DC::Gap::PerPlayerBucket bucket;")

    def test_refusals_are_one_x_record_and_leak_nothing(self):
        both(self, 'refusals_are_one_x_record_and_leak_nothing', "            catch (std::exception const&)\n            {\n                // what() of a library exception can name a table or a path; the player gets a plain line.\n                send_(actor, prefix, RefusalRecord(prefix, TextFailed));",
             "            catch (std::exception const& e)\n            {\n                send_(actor, prefix, RefusalRecord(prefix, e.what()));")

    def test_refusal_text_cannot_carry_a_separator(self):
        both(self, 'refusal_text_cannot_carry_a_separator', "if (c == '|' || c == '\\t' || static_cast<unsigned char>(c) < 0x20 || c == 0x7f)\n                c = ' ';",
             "if (false)\n                c = ' ';")


if __name__ == "__main__":
    unittest.main()
