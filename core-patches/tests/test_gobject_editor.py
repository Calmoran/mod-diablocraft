"""0021: the vendored mod-gobject-editor is off unless dev's conf says 1, and refuses everyone below GM 3.

Base: the verbatim mirror reference/mod-gobject-editor/ (upstream norrathreborn/GObject-Editor-Tool at
86f64cbcd63aba0005fc2c7da6a63bef9ea504ed). The patch core-patches/0021-gobject-editor-hardening.patch is applied to a
copy of it here, and what is checked is the patched text:

  * the patch applies (`patch -p1`; the PM's `git apply` form is proved in the test doc) and changes exactly the module's source and its conf.dist;
  * IsModuleEnabled, RequiredSecurity, HasAccess, the chat hook, HandleClear and the logout hook are cut out of the
    patched source and COMPILED against stand-ins for the core types (gobject_editor/shim.h), then run on the cases
    gobject_editor/driver.cpp names: Enable missing or 0 answers nothing (not even a refusal), the gate cannot be
    lowered below 3, a player below it is refused (CLEAR answers GE_ACCESS_DENIED and clears nothing), logout sends
    nothing;
  * every opcode DispatchPayload routes (and HELLO) runs its handler, and every such handler's first statement is the
    HasAccess gate; the module registers one PlayerScript and nothing else, so DispatchPayload is the only way in;
  * each rule above is mutated in the patched text and the driver or the structure check must go red.

What this does NOT cover: the handlers' own work (the world database, maps, summons) is not run here; the module
as a whole is compiled by `syntax_check.sh` (the close report states its result) and used by the designer on dev.

    python core-patches/tests/test_gobject_editor.py
"""
from pathlib import Path
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mod-diablocraft" / "scripts"))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

PATCH = ROOT / "core-patches" / "0021-gobject-editor-hardening.patch"
MIRROR = ROOT / "reference" / "mod-gobject-editor"
RIG = Path(__file__).resolve().parent / "gobject_editor"
SCRATCH = ROOT / "azerothcore-wotlk" / "build" / "_agent-scratch"
SOURCE = "modules/mod-gobject-editor/src/GObjectEditor.cpp"
CONF = "modules/mod-gobject-editor/conf/mod_gobject_editor.conf.dist"
# The mirror is the upstream pin byte for byte: a changed mirror is a different base for the patch.
MIRROR_SHA256 = {
    "src/GObjectEditor.cpp": "97803ac582f3a07ad5a88ac4eab378e0edf3aeafcc896e0f7e06fdea5def885a",
    "conf/mod_gobject_editor.conf.dist": "0c0d5c832aa698785d4c553d505d087442f59f2b9b450154a26ccd3574fe87bb",
}


def close_of(text: str, start: int) -> int:
    """Index just past the brace that closes the first `{` at or after `start`."""
    depth, i = 0, text.index("{", start)
    while True:
        depth += text[i] == "{"
        depth -= text[i] == "}"
        i += 1
        if depth == 0:
            return i


def function(text: str, signature: str) -> str:
    start = text.index(signature)
    return text[start:close_of(text, start)]


def gate_inc(text: str) -> str:
    """The production text the driver runs, cut out of the (possibly mutated) patched source."""
    constants = "\n".join(re.findall(r'constexpr char GE_\w+\[\] = "[^"]*";', text))
    first = text.index("static bool IsModuleEnabled()")
    last_start = text.index("static bool HasAccess(Player* player)")
    readers = text[first:close_of(text, last_start)]
    cls_start = text.index("class gobject_editor_player_script")
    cls = text[cls_start:close_of(text, cls_start)] + ";"
    return "\n\n".join([constants, readers, function(text, "static bool ParsePrefixedAddonMessage("),
                        function(text, "static void HandleClear(Player* player)"), cls]) + "\n"


def routed_handlers(text: str) -> list:
    """Every function DispatchPayload calls for an opcode (HELLO is answered before the chain, by HandleHello)."""
    chain = function(text, "static void DispatchPayload(")
    return sorted(set(re.findall(r'parts\[0\] == "[A-Z_]+"\)\s*(\w+)\(player', chain)))


GATE = re.compile(r"\{\s*if \(!HasAccess\(player\)\)\s*\{\s*SendAddonPayload\(player, GE_ACCESS_DENIED\);\s*return;\s*\}")


def ungated(text: str) -> list:
    bad = []
    for name in routed_handlers(text):
        head = re.search(r"static void %s\(Player\* player[^)]*\)\s*" % name, text)
        if not head or not GATE.match(text[head.end():]):
            bad.append(name)
    hello = function(text, "static void HandleHello(Player* player)")
    if not re.match(r"[^{]*\{\s*if \(HasAccess\(player\)\)\s*SendAddonPayload\(player, GE_ACCESS_VERIFIED\);\s*else\s*SendAddonPayload\(player, GE_ACCESS_DENIED\);", hello):
        bad.append("HandleHello")
    return bad


MUTATIONS = {
    "Enable defaults to on": ('GetOption<bool>("GObjectEditor.Enable", false)', 'GetOption<bool>("GObjectEditor.Enable", true)'),
    "the gate can be lowered": ('std::max<uint32>(sConfigMgr->GetOption<uint32>("GObjectEditor.RequiredSecurity", SEC_ADMINISTRATOR), SEC_ADMINISTRATOR)',
                                'sConfigMgr->GetOption<uint32>("GObjectEditor.RequiredSecurity", SEC_ADMINISTRATOR)'),
    "the hook answers with the module off": ("if (lang != LANG_ADDON || !IsModuleEnabled())", "if (lang != LANG_ADDON)"),
    "HasAccess ignores the module switch": ("    if (!IsModuleEnabled())\n        return false;\n", ""),
    "HasAccess lets a player through": ("player->GetSession()->GetSecurity()) >= RequiredSecurity()", "player->GetSession()->GetSecurity()) >= 0"),
    "CLEAR has no gate": ("    if (!HasAccess(player))\n    {\n        SendAddonPayload(player, GE_ACCESS_DENIED);\n        return;\n    }\n\n    ClearEditorSession(player, true);",
                          "    ClearEditorSession(player, true);"),
    "logout notifies the leaving player": ("ClearEditorSession(player, false);", "ClearEditorSession(player, true);"),
}


class GObjectEditorPatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        cls.work = Path(tempfile.mkdtemp(prefix="gobject-editor-", dir=SCRATCH))
        cls.addClassCleanup(shutil.rmtree, cls.work, True)
        cls.tree = cls.work / "tree"
        for rel in ("src/GObjectEditor.cpp", "conf/mod_gobject_editor.conf.dist"):
            target = cls.tree / "modules" / "mod-gobject-editor" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(MIRROR / rel, target)
        # Not `git apply`: the scratch folder lies inside a checkout, where git would resolve the patch's paths from its root.
        cls.applied = subprocess.run(["patch", "-p1", "--batch", "--no-backup-if-mismatch", "-d", str(cls.tree), "-i", str(PATCH)],
                                     capture_output=True, text=True)
        cls.source = (cls.tree / SOURCE).read_text(encoding="utf-8")
        cls.upstream = (MIRROR / "src/GObjectEditor.cpp").read_text(encoding="utf-8")

    def run_driver(self, text: str, name: str):
        (self.work / "gate.inc").write_text(gate_inc(text), encoding="utf-8")
        exe = self.work / name
        build = subprocess.run(["g++", "-std=c++17", "-Wall", "-I", str(RIG), "-I", str(self.work),
                                str(RIG / "driver.cpp"), "-o", str(exe)], capture_output=True, text=True)
        self.assertEqual(build.returncode, 0, build.stderr[-3000:])
        # The mutation runs may crash on purpose; the helper's core limit keeps apport out of it.
        return subprocess.run([str(exe)], capture_output=True, text=True, preexec_fn=lambda: harness_env.limit_core())

    def test_the_mirror_is_the_upstream_pin(self):
        for rel, digest in MIRROR_SHA256.items():
            self.assertEqual(hashlib.sha256((MIRROR / rel).read_bytes()).hexdigest(), digest, rel)

    def test_the_patch_applies_and_touches_exactly_the_module(self):
        self.assertEqual(self.applied.returncode, 0, self.applied.stderr)
        text = PATCH.read_text(encoding="utf-8")
        self.assertEqual(sorted(re.findall(r"^\+\+\+ b/(\S+)", text, re.M)), sorted([SOURCE, CONF]))
        self.assertNotEqual(self.source, self.upstream)

    def test_the_conf_ships_off_and_the_gate_at_3(self):
        conf = (self.tree / CONF).read_text(encoding="utf-8")
        self.assertRegex(conf, r"(?m)^GObjectEditor\.Enable = 0$")
        self.assertRegex(conf, r"(?m)^GObjectEditor\.RequiredSecurity = 3$")

    def test_the_gate_code_answers_the_cases(self):
        ran = self.run_driver(self.source, "gate")
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertIn("ALL OK", ran.stdout)

    def test_every_mutation_is_caught(self):
        for label, (old, new) in MUTATIONS.items():
            with self.subTest(label):
                self.assertEqual(self.source.count(old), 1, f"mutation target not found once: {old!r}")
                ran = self.run_driver(self.source.replace(old, new), "mutant")
                self.assertNotEqual(ran.returncode, 0, f"mutation survived: {label}")

    def test_every_routed_handler_starts_with_the_gate(self):
        routed = routed_handlers(self.source)
        self.assertEqual(len(routed), 24, routed)  # the 24 distinct handlers of the 25 opcodes (FLASH is REFRESH_PREVIEW's twin)
        for name in ("HandleClear", "HandleScan", "HandleSave", "HandleDeleteSelected", "HandlePlaceCreatureTemplate"):
            self.assertIn(name, routed)
        self.assertEqual(ungated(self.source), [])
        # The same check on the upstream text finds the known hole: CLEAR ran ClearEditorSession with no gate.
        self.assertEqual(ungated(self.upstream), ["ClearEditorSession"])

    def test_removing_one_handlers_gate_is_caught(self):
        gate = "static void HandleSearchTemplate(Player* player, std::vector<std::string> const& parts)\n{\n    if (!HasAccess(player))"
        self.assertEqual(self.source.count(gate), 1)
        self.assertEqual(ungated(self.source.replace(gate, gate.replace("!HasAccess(player)", "false"))), ["HandleSearchTemplate"])

    def test_dispatch_is_the_only_way_in(self):
        self.assertEqual(re.findall(r"class (\w+) : public (\w+Script)\b", self.source), [("gobject_editor_player_script", "PlayerScript")])
        self.assertEqual(self.source.count("new gobject_editor_player_script()"), 1)
        self.assertEqual(re.findall(r"\bvoid (On\w+)\(", self.source), ["OnPlayerBeforeSendChatMessage", "OnPlayerLogout"])
        hook = function(self.source, "void OnPlayerBeforeSendChatMessage")
        self.assertEqual(re.findall(r"\b(DispatchPayload)\(", hook), ["DispatchPayload"])


if __name__ == "__main__":
    unittest.main()
