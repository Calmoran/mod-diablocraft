"""diablocraft-g74u4: lua_errors.py turns a Lua error drop file into readable errors.

A recorded send is built the way BugSack r225 makes one (docs/research/bugsack-wire.md): AceSerializer-3.0 r3's
Serialize of the error array (sections 4-5) cut by AceComm-3.0 r6 into 246-byte chunks under BugSack\\x01, \\x02 and
\\x03 (section 3), written as the drop writes them ("HH:MM:SS <prefix>\\t<text>"). The doc's own worked example A is
used verbatim. Then every rule the script owns is mutated in its source, and the tests must refuse each mutant.
"""
import importlib.util
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = (HERE.parent.parent / "lua_errors.py").read_text(encoding="utf-8")
SCRATCH = HERE.parents[3] / "azerothcore-wotlk/build/_agent-scratch"

# bugsack-wire.md section 6 A, verbatim: one short error, one message (243 bytes)
EXAMPLE_A = ("^1^T^N1^T^Scounter^N1^Stype^Serror^Ssession^N7^Stime^S2026/10/14~`12:34:56^Smessage^SInterface\\AddOns\\"
             "Torment\\core.lua:42:~`attempt~`to~`index~`global~`'foo'~`(a~`nil~`value)~JInterface\\AddOns\\Torment\\"
             "core.lua:42:~`in~`main~`chunk~J~`~`---^t^t")


def load(source=SOURCE):
    spec = importlib.util.spec_from_loader("lua_errors_under_test", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, "lua_errors.py", "exec"), module.__dict__)
    return module


# --- the sender's side, as the r225 libraries write it --------------------------------------------------------------

def escape(text):
    """SerializeStringHelper: control bytes, space, ^, ~ and DEL (AceSerializer-3.0.lua:34-58)."""
    def one(match):
        n = ord(match.group(0))
        if n == 30:
            return "~z"
        if n <= 32:
            return "~" + chr(n + 64)
        return {94: "~}", 126: "~|", 127: "~{"}[n]
    return re.sub(r"[\x00-\x20^~\x7f]", one, text)


def serialize(value):
    if isinstance(value, bool):
        return "^B" if value else "^b"
    if value is None:
        return "^Z"
    if isinstance(value, int):
        return "^N" + str(value)
    if isinstance(value, float):   # a number tostring() does not round-trip: ^F mantissa ^f exponent
        mantissa, exponent = value.as_integer_ratio()
        shift = exponent.bit_length() - 1
        return f"^F{mantissa}^f-{shift}"
    if isinstance(value, str):
        return "^S" + escape(value)
    items = enumerate(value, 1) if isinstance(value, list) else value.items()
    return "^T" + "".join(serialize(k) + serialize(v) for k, v in items) + "^t"


def send(clock, errors):
    """The drop file's lines for one BugSack send (SendCommMessage, AceComm-3.0.lua:96-128)."""
    text = "^1" + serialize(errors) + "^^"
    if len(text) <= 247:
        return [f"{clock} BugSack\t{text}"]
    chunks = [text[i:i + 246] for i in range(0, len(text), 246)]
    markers = ["\x01"] + ["\x02"] * (len(chunks) - 2) + ["\x03"]
    return [f"{clock} BugSack{m}\t{c}" for m, c in zip(markers, chunks)]


STACK = ["Interface\\AddOns\\Torment\\bags.lua:%d: in function 'f%d'" % (100 + i, i) for i in range(24)]
LONG = ("Interface\\AddOns\\Torment\\bags.lua:99: attempt to compare number with nil\n" + "\n".join(STACK)
        + "\nLocals:|r\n  self = |cff00ff00<table>|r\n  count = 3\n  name = \"Horadric ^ Cube ~ 5\"\n  ---")
assert len(LONG) > 980   # BugGrabber stores it as pieces, so the reader must join them
ERRORS = [
    {"message": [LONG[:980], LONG[980:]] if len(LONG) > 980 else LONG, "session": 12, "time": "2026/10/14 09:15:02",
     "type": "error", "counter": 3},
    {"message": "Interface\\AddOns\\Torment\\map.lua:7: bad argument #1\n  ---", "session": 12,
     "time": "2026/10/14 09:16:40", "type": "error", "counter": 1},
]


class Rules(unittest.TestCase):
    """Each test takes the module so the mutant run can hand it a mutated one."""

    def example_a(self, L):
        text, count = L.readable(["12:00:01 BugSack\t" + EXAMPLE_A])
        self.assertEqual(1, count)
        self.assertIn("== 2026/10/14 12:34:56  x1  (error, session 7, sent 12:00:01)\n"
                      "Interface\\AddOns\\Torment\\core.lua:42: attempt to index global 'foo' (a nil value)\n"
                      "Stack:\n  Interface\\AddOns\\Torment\\core.lua:42: in main chunk\n", text)
        self.assertNotIn("problems", text)

    def chunked_send(self, L):
        lines = send("09:20:00", ERRORS)
        self.assertGreater(len(lines), 3)
        self.assertEqual({"\x01", "\x02", "\x03"}, {line[16] for line in lines})
        text, count = L.readable(lines)
        self.assertEqual(2, count)
        first = text.split("\n\n")[0].split("\n")
        self.assertEqual("== 2026/10/14 09:15:02  x3  (error, session 12, sent 09:20:00)", first[0])
        self.assertEqual("Interface\\AddOns\\Torment\\bags.lua:99: attempt to compare number with nil", first[1])
        self.assertEqual(["Stack:"] + ["  " + s for s in STACK], first[2:2 + 1 + len(STACK)])
        self.assertEqual(["Locals:", "  self = <table>", "  count = 3", '  name = "Horadric ^ Cube ~ 5"'],
                         first[3 + len(STACK):])
        self.assertIn("== 2026/10/14 09:16:40  x1", text)
        self.assertNotIn("problems", text)

    def broken_sends(self, L):
        lines = send("09:20:00", ERRORS)
        text, count = L.readable(lines[:-1] + ["09:21:00 BugSack\t" + EXAMPLE_A])
        self.assertEqual(1, count)
        self.assertIn("a send began before the last one ended", text)
        # the lost chunk turning up after a new send is not glued onto the old one's first chunks
        text, count = L.readable(lines[:-1] + ["09:21:00 BugSack\t" + EXAMPLE_A, lines[-1]])
        self.assertEqual(1, count)
        self.assertIn("a chunk with no first chunk before it", text)
        text, count = L.readable(lines[1:])
        self.assertEqual(0, count)
        self.assertIn("a chunk with no first chunk before it", text)

    def escapes_and_numbers(self, L):
        tricky = "a b^c~d\x1ee\x7ff\tg\nh"
        self.assertEqual([tricky, 2.5, -3, True, False, None],
                         L.deserialize("^1" + "".join(serialize(v) for v in (tricky, 2.5, -3, True, False, None)) + "^^"))
        # Deserialize drops control characters and spaces first, so reflowed text reads the same (bugsack-wire.md 4)
        self.assertEqual(["a b", 7], L.deserialize("^1 ^Sa~`b\n^N7 \r^^"))

    def test_example_a(self):
        self.example_a(load())

    def test_a_chunked_send_with_stack_locals_and_a_split_message(self):
        self.chunked_send(load())

    def test_a_lost_last_chunk_is_reported_and_the_next_send_still_reads(self):
        self.broken_sends(load())

    def test_every_escape_and_value_type(self):
        self.escapes_and_numbers(load())

    def test_the_script_writes_the_readable_file_beside_the_raw_one(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix="lua-errors-", dir=SCRATCH))
        try:
            raw = folder / "2026-10-14" / "the designer.txt"
            raw.parent.mkdir()
            raw.write_text("\n".join(send("09:20:00", ERRORS)) + "\n", encoding="utf-8")
            before = raw.read_bytes()
            self.assertEqual(0, load().main(["lua_errors.py", str(raw)]))
            self.assertEqual(before, raw.read_bytes())
            self.assertIn("x3", (raw.parent / "the designer.readable.txt").read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(folder)


MUTANTS = {
    "a middle chunk is dropped": ('        elif marker == "\\x02":\n            open_.append(text)',
                                  '        elif marker == "\\x02":\n            pass'),
    "an unfinished send is kept": ('(its last chunk never came)")\n            open_ = None', '(its last chunk never came)")'),
    "the last chunk is not joined": ('            open_.append(text)\n            out.append((clock, "".join(open_)))',
                                     '            out.append((clock, "".join(open_)))'),
    "^ stays escaped": ('"}": "^"', '"}": "~}"'),
    "~ stays escaped": ('"|": "~"', '"|": "~|"'),
    "control bytes off by one": ("return chr(ord(c) - 64)", "return chr(ord(c) - 63)"),
    "no whitespace strip": ('    text = re.sub(r"[\\x00-\\x1f\\x7f ]", "", text)', "    pass"),
    "a split message is not joined": ('        message = "".join(str(p) for p in pieces)', "        message = str(pieces[0])"),
    "^F ignores the exponent": ("return float(data) * 2.0 ** int(exponent)", "return float(data)"),
    "colour codes kept": ('    text = COLOUR.sub("", str(message))', "    text = str(message)"),
    "locals left in the stack": ('    text, _, locals_ = text.partition("\\nLocals:")', '    locals_ = ""'),
    "the counter is not shown": ("x{err.get('counter', 1)}", "x1"),
}


class Mutants(unittest.TestCase):
    def test_every_rule_is_needed(self):
        checks = [Rules.example_a, Rules.chunked_send, Rules.broken_sends, Rules.escapes_and_numbers]
        for name, (old, new) in MUTANTS.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, SOURCE.count(old), name)
                mutant = load(SOURCE.replace(old, new))
                failed = 0
                for check in checks:
                    try:
                        check(Rules(), mutant)
                    except Exception:   # an assertion, or the mutant crashing on the input
                        failed += 1
                self.assertGreater(failed, 0, "mutant survived: " + name)


if __name__ == "__main__":
    unittest.main()
