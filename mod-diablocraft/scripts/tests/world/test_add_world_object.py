"""diablocraft-jn9r: the one-command world object adder (add_world_object.py).

    python3 mod-diablocraft/scripts/tests/world/test_add_world_object.py

Runs the adder on temp copies of the sheets (never the real ones) and drives the production generator over the result:
  * a model the stock table has (AuraRed.m2, stock 264) REUSES that display: no display row, only a template;
  * a model nobody has gets the next free Torment display id and its row; the box is zeros flagged PLACEHOLDER, or the .m2 header's;
  * a model already in our sheet reuses our row; .m2 / forward slashes / case still find it;
  * a refused add leaves both sheets byte for byte as they were;
  * every result passes the generator's own build check (test_world_objects.check_build);
  * single-rule mutants of the adder must each fail one of these.
Needs the server's extracted stock DBCs (azerothcore-wotlk/build/server/data/dbc).
"""
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import add_world_object as adder  # noqa: E402
import generate_world_objects as gen  # noqa: E402
import test_world_objects as base  # noqa: E402

AURA = "World\\Generic\\PassiveDoodads\\ParticleEmitters\\AuraRed.m2"
STAIRS = "World\\Expansion02\\Doodads\\Azjol-Nerub\\Stairs\\Azjol_Stairs01.m2"
SEED_D, SEED_O = "9700,World\\Seed.mdx,Seed,0,0,0,0,0,0,", "910090,9700,Seed,1,"


def run(module, model, name, d, o, **kwargs):
    return module.add(model, name, gen.STOCK_DIR, d, o, run_generator=False, **kwargs)


def m2(path, box, radius=1.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = bytearray(0x100)
    data[:4] = b"MD20"
    struct.pack_into("<6ff", data, adder.BOX_OFFSET, *box, radius)
    path.write_bytes(data)


class Adder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="add_world_object_test_")
        self.d, self.o = (Path(self.tmp.name, n) for n in ("d.csv", "o.csv"))
        self.d.write_text("display_id,model_path,name,min_x,min_y,min_z,max_x,max_y,max_z,notes\n" + SEED_D + "\n")
        self.o.write_text("entry,display_id,name,size,notes\n" + SEED_O + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def check(self):
        base.check_build(gen, self.d, self.o)

    def test_stock_model_reuses_the_stock_display(self):
        said = run(adder, AURA, "Red Aura", self.d, self.o)
        self.assertEqual(len(base.read(self.d)), 1, "no display row added")
        added = base.read(self.o)[-1]
        self.assertEqual((added["entry"], added["display_id"], added["name"]), ("910091", "264", "Red Aura"))
        self.assertIn("stock display 264", said)
        self.check()

    def test_the_real_aura_is_stock_264(self):
        self.assertEqual(adder.stock_display(AURA, gen.stock_store(gen.STOCK_DIR)), 264)

    def test_m2_slashes_and_case_find_the_stock_row(self):
        store = gen.stock_store(gen.STOCK_DIR)
        for spelling in (AURA, AURA.replace("\\", "/"), AURA.replace(".m2", ".mdx"), AURA.lower(), "\\" + AURA):
            self.assertEqual(adder.stock_display(spelling, store), 264, spelling)

    def test_unknown_model_gets_the_next_display_with_a_flagged_box(self):
        run(adder, STAIRS, "Stairs", self.d, self.o)
        row = base.read(self.d)[-1]
        self.assertEqual((row["display_id"], row["model_path"]), ("9701", STAIRS.replace(".m2", ".mdx")))
        self.assertTrue(all(float(row[f]) == 0 for f in gen.BOX) and "PLACEHOLDER" in row["notes"])
        self.assertEqual(base.read(self.o)[-1]["display_id"], "9701")
        self.check()

    def test_second_template_on_our_model_adds_no_display(self):
        run(adder, STAIRS, "Stairs", self.d, self.o)
        run(adder, STAIRS.lower().replace("\\", "/"), "More Stairs", self.d, self.o)
        self.assertEqual(len(base.read(self.d)), 2)
        self.assertEqual([r["display_id"] for r in base.read(self.o)], ["9700", "9701", "9701"])
        self.check()

    def test_box_comes_from_the_m2_header(self):
        m2(Path(self.tmp.name, "client", "world", "EXPANSION02", "Doodads", "Azjol-Nerub", "Stairs", "azjol_stairs01.M2"),
           (-1, -2, -3, 4, 5, 6))
        run(adder, STAIRS, "Stairs", self.d, self.o, client_dir=Path(self.tmp.name, "client"))
        row = base.read(self.d)[-1]
        self.assertEqual([float(row[f]) for f in gen.BOX], [-1, -2, -3, 4, 5, 6])
        self.assertNotIn("PLACEHOLDER", row["notes"])
        self.check()

    def test_bad_models_are_refused(self):
        client = Path(self.tmp.name, "client")
        with self.assertRaisesRegex(gen.ObjectError, "no .m2 under"):
            run(adder, STAIRS, "Stairs", self.d, self.o, client_dir=client)
        m2(client / "World/Expansion02/Doodads/Azjol-Nerub/Stairs/Azjol_Stairs01.m2", (1, 1, 1, 0, 0, 0))
        with self.assertRaisesRegex(gen.ObjectError, "inverted"):
            run(adder, STAIRS, "Stairs", self.d, self.o, client_dir=client)

    def test_a_refused_add_changes_nothing(self):
        before = (self.d.read_bytes(), self.o.read_bytes())
        for model, name, kwargs, text in ((AURA, "seed", {}, "already exists"), (AURA, "Red Aura", {"size": 0}, "positive size"),
                                          ("", "x", {}, "both needed")):
            with self.assertRaisesRegex(gen.ObjectError, text):
                run(adder, model, name, self.d, self.o, **kwargs)
            self.assertEqual((self.d.read_bytes(), self.o.read_bytes()), before, text)

    def test_a_full_block_is_refused(self):
        rows = [f"{e},264,N{e},1," for e in gen.OBJECT_RANGE]
        self.o.write_text("entry,display_id,name,size,notes\n" + "\n".join(rows) + "\n")
        with self.assertRaisesRegex(gen.ObjectError, "full"):
            run(adder, AURA, "One More", self.d, self.o)

    def test_the_generator_runs_when_asked(self):
        calls, saved = [], adder.gen.main
        adder.gen.main = lambda argv: calls.append(argv)
        try:
            adder.add(AURA, "Red Aura", gen.STOCK_DIR, self.d, self.o)
        finally:
            adder.gen.main = saved
        self.assertEqual(len(calls), 1)


def mutant(*replacements):
    source = (HERE / "add_world_object.py").read_text(encoding="utf-8")
    for old, new in replacements:
        assert source.count(old) == 1, f"mutant anchor not unique: {old!r}"
        source = source.replace(old, new)
    module = types.ModuleType("add_world_object_mutant")
    module.__file__ = str(HERE / "add_world_object.py")
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    module.gen = types.SimpleNamespace(**vars(gen))  # a private namespace, so a test can patch main
    return module


class Mutants(unittest.TestCase):
    def killed(self, *replacements):
        """Run the real scenarios against the mutant; at least one must fail."""
        for case in (Adder.test_stock_model_reuses_the_stock_display, Adder.test_unknown_model_gets_the_next_display_with_a_flagged_box,
                     Adder.test_second_template_on_our_model_adds_no_display, Adder.test_box_comes_from_the_m2_header,
                     Adder.test_a_refused_add_changes_nothing, Adder.test_the_generator_runs_when_asked, Adder.test_m2_slashes_and_case_find_the_stock_row):
            global adder
            real, adder = adder, mutant(*replacements)
            try:
                suite = unittest.TestSuite([Adder(case.__name__)])
                result = unittest.TestResult()
                suite.run(result)
            finally:
                adder = real
            if not result.wasSuccessful():
                return
        self.fail("the mutant survived every scenario")

    def test_stock_lookup_dropped(self):
        self.killed(("new_display, display = None, stock_display(model, store)", "new_display, display = None, None"))

    def test_our_row_not_reused(self):
        self.killed(("elif (own := next(", "elif (own := None and next("))

    def test_new_display_ignores_the_ones_we_have(self):
        self.killed(("[r[\"display_id\"] for r in display_rows]", "[]"))

    def test_next_entry_always_the_first(self):
        self.killed(("if e not in taken", "if e in taken"))

    def test_box_columns_misordered(self):
        self.killed(("*(box or [0] * 6)", "*(box[::-1] if box else [0] * 6)"))

    def test_validation_skipped_before_writing(self):
        self.killed(("gen.generate(stock_dir, d, o)", "pass"))

    def test_name_clash_allowed(self):
        self.killed(("if any(r[\"name\"].strip().lower() == name.strip().lower() for r in object_rows):", "if False:"))

    def test_generator_not_run(self):
        self.killed(("if run_generator:", "if False:"))


if __name__ == "__main__":
    unittest.main()
