"""0019: the mail and trade readers serve only the caller's own mailbox and trade.

Compiles the patch's own `GetMailAttachment` and `GetTradeItem` (the added lines
of core-patches/0019, extracted, not retyped) against `mail_trade/shim.h`, which
stands in for the core types with the core's names, and runs `mail_trade/driver.cpp`
on a small world: rows that skip deleted, undelivered and expired mail, the
50-mail list cap, another player's mailbox and a trade the caller is not in.
Each mutation of the patch must then fail that driver, so a green run means the
driver can tell a leak from a correct answer.

    python core-patches/tests/test_mail_trade_readers.py
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mod-diablocraft" / "scripts"))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

PATCH = ROOT / "core-patches" / "0019-ale-mail-trade-item-readers.patch"
RIG = Path(__file__).resolve().parent / "mail_trade"
SCRATCH = ROOT / "azerothcore-wotlk" / "build" / "_agent-scratch"


def readers() -> str:
    """The two readers as the patched PlayerMethods.h holds them: the hunk's
    context and added lines, cut from the first reader's doc comment to the
    close of the second."""
    after, inside = [], False
    for line in PATCH.read_text(encoding="utf-8").splitlines():
        if line.startswith("--- "):
            inside = line.endswith("PlayerMethods.h")
        elif inside and line[:1] in (" ", "+") and not line.startswith("+++"):
            after.append(line[1:])
    first = next(i for i, l in enumerate(after) if "int GetMailAttachment" in l)
    while after[first].strip() != "/**":
        first -= 1
    second = next(i for i, l in enumerate(after) if "int GetTradeItem" in l)
    last = next(i for i in range(second, len(after)) if after[i] == "    }")
    return "\n".join(after[first:last + 1]) + "\n"


MUTATIONS = {
    "lists deleted, undelivered and expired mail":
        ("mail->state == MAIL_STATE_DELETED || now < mail->deliver_time || now > mail->expire_time", "false"),
    "ignores the 50-mail list cap":
        ("if (listed >= INBOX_LIST_CAPACITY)\n                    break;", ""),
    "reads everyone's mail": ("player->GetMails()", "World::allMail"),
    "partner read returns the caller's own side": ("if (data && partner)", "if (false)"),
    "serves a trade the caller is not in": ("player->GetTradeData()", "World::someoneElsesTrade"),
    "reads past the last trade slot": ("slot < TRADE_SLOT_COUNT", "true"),
}


class MailTradeReaders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        cls.work = Path(tempfile.mkdtemp(prefix="mail-trade-", dir=SCRATCH))
        cls.addClassCleanup(shutil.rmtree, cls.work, True)

    def run_driver(self, text: str, name: str):
        (self.work / "readers.inc").write_text(text, encoding="utf-8")
        exe = self.work / name
        build = subprocess.run(["g++", "-std=c++17", "-Wall", "-I", str(RIG), "-I", str(self.work),
                                str(RIG / "driver.cpp"), "-o", str(exe)], capture_output=True, text=True)
        self.assertEqual(build.returncode, 0, build.stderr[-3000:])
        return harness_env.run([str(exe)], capture_output=True, text=True)

    def test_patch_answers_correctly(self):
        result = self.run_driver(readers(), "base")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ALL OK", result.stdout)

    def test_every_mutation_is_caught(self):
        base = readers()
        for label, (old, new) in MUTATIONS.items():
            with self.subTest(label):
                self.assertEqual(base.count(old), 1, f"mutation target not found once: {old!r}")
                result = self.run_driver(base.replace(old, new), "mutant")
                self.assertNotEqual(result.returncode, 0, f"mutation survived: {label}")

    def test_only_ale_registration_and_the_two_readers_are_added(self):
        text = PATCH.read_text(encoding="utf-8")
        for name in ("GetMailAttachment", "GetTradeItem"):
            self.assertIn(f'+    {{ "{name}", &LuaPlayer::{name} }},', text)
        self.assertEqual(sum(1 for l in text.splitlines() if l.startswith("--- a/")), 2)


if __name__ == "__main__":
    unittest.main()
