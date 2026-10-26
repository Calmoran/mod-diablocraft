"""harness_env.build, the compile cache (audit 2026-10-19 section 5.1).

A template that compiles one harness for every case or row mutant must pay for one compile per distinct
program. The risk of a cache is a stale binary: a mutant served the green program would pass its own
"the mutant survived" check. So each rule below is paired with the edit that must NOT be served from cache:

  * the same sources, files, flags and headers compile once, and the second call returns the same binary;
  * a changed `files` text, a changed flag, a changed source, and a changed repo header (the one the source
    includes through `includes=`, edited in place, same length) each compile again and RUN differently;
  * a relative include path (includes=, -I, -isystem, -include) names the folder it is run from: the same text
    run from another folder is another program;
  * another compiler (a different `c++ --version` at one path) compiles and links again; other include folders
    holding a different same-named header, and a flag that only the link reads (-Wl,--defsym), give other binaries;
  * a library named on the link line is keyed by its content;
  * run_cpp (a harness that is a string, the contract test_class_parity.run had): the same text compiles once, another text
    compiles again, a failing harness answers (False, output), a compile error raises BuildError, the module's src/common is on the
    include path and `extra` sources are linked in;
  * build_text(files=) stages headers by content (a changed header compiles again, the same one does not), and stage_files makes
    one folder per content for a harness that includes by relative path;
  * a source shared by two harnesses compiles to one object, and two binaries with the same objects share a link;
  * a hit still reads the headers (the runner's strace records them as the test's inputs);
  * a failed compile raises BuildError and is not remembered; threads building one program all get a working binary;
  * an entry nobody used for KEEP_SECONDS is deleted by the next build; a used one is kept.

Every binary here is compiled and run through harness_env, so the script is in test_harness_core_limit.RUNNERS.

    python mod-diablocraft/scripts/tests/tooling/test_harness_env_build.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

SCRATCH = SCRIPTS.parents[1] / "azerothcore-wotlk/build/_agent-scratch/harness-env-build"
FLAGS = ["-std=c++17", "-O0"]
MAIN = '#include <cstdio>\n#include "value.h"\nint main() { std::printf("%d\\n", VALUE); }\n'


class Cache(unittest.TestCase):
    def setUp(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(prefix="build-", dir=SCRATCH)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        patch = mock.patch.dict(os.environ, {harness_env.CACHE_ENV: str(self.root / "cache")})
        patch.start()
        self.addCleanup(patch.stop)
        self.src = self.root / "src"
        self.src.mkdir()
        self.main = self.write("main.cpp", MAIN)
        harness_env.compiles.clear()

    def write(self, name, text):
        path = self.src / name
        path.write_text(text, encoding="utf-8")
        return path

    def value(self, binary):
        ran = harness_env.run([str(binary)], capture_output=True, text=True)
        self.assertEqual(0, ran.returncode, ran.stderr)
        return ran.stdout.strip()

    def built(self, **kwargs):
        return harness_env.build(kwargs.pop("sources", [self.main]), flags=kwargs.pop("flags", FLAGS),
                                 files=kwargs.pop("files", {"value.h": "#define VALUE 7\n"}), **kwargs)

    def test_the_same_inputs_compile_once_and_give_the_same_binary(self):
        first = self.built()
        second = self.built()
        self.assertEqual(first, second)
        self.assertEqual(["%s" % self.main, "link"], harness_env.compiles)
        self.assertEqual("7", self.value(second))

    def test_a_changed_files_text_flag_or_source_is_not_served_from_cache(self):
        self.assertEqual("7", self.value(self.built()))
        self.assertEqual("8", self.value(self.built(files={"value.h": "#define VALUE 8\n"})))
        self.assertEqual("9", self.value(self.built(files={"value.h": "#define VALUE 9\n"})))
        flagged = self.write("flagged.cpp", '#include <cstdio>\nint main() { std::printf("%d\\n", FLAG); }\n')
        self.assertEqual("1", self.value(self.built(sources=[flagged], flags=FLAGS + ["-DFLAG=1"])))
        self.assertEqual("2", self.value(self.built(sources=[flagged], flags=FLAGS + ["-DFLAG=2"])))
        self.write("flagged.cpp", '#include <cstdio>\nint main() { std::printf("%d\\n", FLAG + 10); }\n')
        self.assertEqual("12", self.value(self.built(sources=[flagged], flags=FLAGS + ["-DFLAG=2"])))

    def test_an_edit_that_is_put_back_is_served_without_a_compile(self):
        source = self.write("flip.cpp", '#include <cstdio>\nint main() { std::printf("a\\n"); }\n')
        a = self.built(sources=[source], files={})
        self.write("flip.cpp", '#include <cstdio>\nint main() { std::printf("b\\n"); }\n')
        self.assertEqual("b", self.value(self.built(sources=[source], files={})))
        harness_env.compiles.clear()
        self.write("flip.cpp", '#include <cstdio>\nint main() { std::printf("a\\n"); }\n')
        self.assertEqual(a, self.built(sources=[source], files={}))
        self.assertEqual([], harness_env.compiles)

    def test_link_flags_change_the_binary(self):
        main = self.write("sym.cpp", '#include <cstdio>\nextern "C" char ANSWER;\nint main() { std::printf("%ld\\n", (long)&ANSWER); }\n')
        for number in (11, 12):
            with self.subTest(number):
                binary = self.built(sources=[main], files={}, flags=FLAGS + ["-no-pie"], link_flags=["-Wl,--defsym,ANSWER=%d" % number])
                self.assertEqual(str(number), self.value(binary))

    def folders(self, text="#define VALUE %d\n"):
        """d1/ and d2/, each with inc/value.h defining VALUE as 1 and 2, and the same main.cpp."""
        for number in (1, 2):
            folder = self.root / ("d%d" % number)
            (folder / "inc").mkdir(parents=True)
            (folder / "inc" / "value.h").write_text(text % number, encoding="utf-8")
        return self.root / "d1", self.root / "d2"

    def cwd(self, folder):
        before = os.getcwd()
        self.addCleanup(os.chdir, before)
        os.chdir(folder)

    def test_a_relative_include_run_from_another_folder_is_another_program(self):
        d1, d2 = self.folders()
        for label, kwargs in (("includes", {"includes": ["inc"]}),
                              ("-Iinc", {"flags": FLAGS + ["-Iinc"]}),
                              ("-I inc", {"flags": FLAGS + ["-I", "inc"]}),
                              ("-isystem inc", {"flags": FLAGS + ["-isystem", "inc"]}),
                              ("-iquote inc", {"flags": FLAGS + ["-iquote", "inc"]})):
            with self.subTest(label):
                self.cwd(d1)
                one = self.built(files={}, **kwargs)
                self.cwd(d2)
                two = self.built(files={}, **kwargs)
                self.assertEqual(("1", "2"), (self.value(one), self.value(two)))
                self.assertNotEqual(one, two)

    def test_a_relative_forced_include_run_from_another_folder_is_another_program(self):
        d1, d2 = self.folders()
        main = self.write("forced.cpp", '#include <cstdio>\nint main() { std::printf("%d\\n", VALUE); }\n')
        results = []
        for folder in (d1, d2):
            self.cwd(folder)
            results.append(self.value(self.built(sources=[main], files={}, flags=FLAGS + ["-include", "inc/value.h"])))
        self.assertEqual(["1", "2"], results)

    def test_the_same_relative_include_from_the_same_folder_is_a_hit(self):
        d1, _ = self.folders()
        self.cwd(d1)
        first = self.built(files={}, includes=["inc"])
        harness_env.compiles.clear()
        self.assertEqual(first, self.built(files={}, includes=[d1 / "inc"]))
        self.assertEqual([], harness_env.compiles)

    def test_other_include_folders_with_a_same_named_header_give_other_binaries(self):
        d1, d2 = self.folders()
        one = self.built(files={}, includes=[d1 / "inc"])
        two = self.built(files={}, includes=[d2 / "inc"])
        self.assertEqual(("1", "2"), (self.value(one), self.value(two)))

    def compilers(self):
        """Two folders whose `c++` is one script with one real path that answers --version differently."""
        real = shutil.which("c++") or shutil.which("g++")
        script = self.root / "fake-cxx"
        script.write_text('#!/bin/sh\ncase "$1" in --version) echo "fake compiler as $0"; exit 0;; esac\nexec %s "$@"\n' % real,
                          encoding="utf-8")
        script.chmod(0o755)
        paths = []
        for name in ("a", "b"):
            (self.root / name).mkdir()
            (self.root / name / "c++").symlink_to(script)
            paths.append(str(self.root / name))
        return paths

    def test_another_compiler_compiles_and_links_again(self):
        path_a, path_b = self.compilers()
        with mock.patch.dict(os.environ, {"PATH": path_a + os.pathsep + os.environ["PATH"]}):
            harness_env._compiler_ids.clear()
            first = self.built()
        with mock.patch.dict(os.environ, {"PATH": path_b + os.pathsep + os.environ["PATH"]}):
            harness_env._compiler_ids.clear()
            second = self.built()
        harness_env._compiler_ids.clear()
        self.assertEqual(["%s" % self.main, "link"] * 2, harness_env.compiles)
        self.assertNotEqual(first, second)

    def test_the_same_compiler_twice_is_a_hit(self):
        path_a, _ = self.compilers()
        with mock.patch.dict(os.environ, {"PATH": path_a + os.pathsep + os.environ["PATH"]}):
            harness_env._compiler_ids.clear()
            self.built()
            harness_env._compiler_ids.clear()
            self.built()
        harness_env._compiler_ids.clear()
        self.assertEqual(["%s" % self.main, "link"], harness_env.compiles)

    def test_a_flag_only_the_link_reads_changes_the_binary(self):
        main = self.write("sym.cpp", '#include <cstdio>\nextern "C" char ANSWER;\nint main() { std::printf("%ld\\n", (long)&ANSWER); }\n')
        for number in (11, 12):
            with self.subTest(number):
                binary = self.built(sources=[main], files={}, flags=FLAGS + ["-no-pie", "-Wl,--defsym,ANSWER=%d" % number])
                self.assertEqual(str(number), self.value(binary))

    def test_a_library_named_on_the_link_line_is_keyed_by_its_content(self):
        user = self.write("user.cpp", '#include <cstdio>\nint Answer();\nint main() { std::printf("%d\\n", Answer()); }\n')
        results = []
        for number in (3, 4):
            lib = self.write("answer.cpp", "int Answer() { return %d; }\n" % number)
            obj = self.root / "answer.o"
            harness_env.run(["c++", "-c", str(lib), "-o", str(obj)]).check_returncode()
            results.append(self.value(self.built(sources=[user], files={}, link_flags=[str(obj)])))
        self.assertEqual(["3", "4"], results)

    def test_a_relative_library_folder_run_from_another_folder_is_another_program(self):
        user = self.write("user.cpp", '#include <cstdio>\nint Answer();\nint main() { std::printf("%d\\n", Answer()); }\n')
        folders = []
        for number in (5, 6):
            folder = self.root / ("lib%d" % number)
            (folder / "lib").mkdir(parents=True)
            lib = folder / "answer.cpp"
            lib.write_text("int Answer() { return %d; }\n" % number, encoding="utf-8")
            harness_env.run(["c++", "-c", str(lib), "-o", str(folder / "answer.o")]).check_returncode()
            harness_env.run(["ar", "rcs", str(folder / "lib/libanswer.a"), str(folder / "answer.o")]).check_returncode()
            folders.append(folder)
        results = []
        for folder in folders:
            self.cwd(folder)
            results.append(self.value(self.built(sources=[user], files={}, link_flags=["-L", "lib", "-lanswer"])))
        self.assertEqual(["5", "6"], results)

    def test_run_cpp_compiles_a_text_once_and_answers_ok_and_output(self):
        code = '#include <cstdio>\nint main() { std::puts("hello"); return 0; }\n'
        self.assertEqual((True, "hello\n"), harness_env.run_cpp(code))
        self.assertEqual((True, "hello\n"), harness_env.run_cpp(code))
        self.assertEqual(["link"], [c for c in harness_env.compiles if c == "link"])
        self.assertEqual(1, len([c for c in harness_env.compiles if c != "link"]))
        self.assertEqual((True, "bye\n"), harness_env.run_cpp(code.replace("hello", "bye")))
        self.assertEqual(2, len([c for c in harness_env.compiles if c != "link"]))

    def test_run_cpp_reports_a_failing_harness_and_raises_on_a_compile_error(self):
        self.assertEqual((False, "no\n"), harness_env.run_cpp('#include <cstdio>\nint main() { std::puts("no"); return 3; }\n'))
        with self.assertRaises(harness_env.BuildError) as raised:
            harness_env.run_cpp("int main() { return missing_name; }\n")
        self.assertIn("missing_name", raised.exception.stderr)

    def test_run_cpp_gives_the_flags_to_the_compile_and_returns_stderr_with_stdout(self):
        code = '#include <cstdio>\nint main() { std::fputs("out ", stdout); std::fprintf(stderr, "err%d", X); return 0; }\n'
        self.assertEqual((True, "out err5"), harness_env.run_cpp(code, flags=("-std=c++17", "-DX=5")))
        self.assertEqual((True, "out err6"), harness_env.run_cpp(code, flags=("-std=c++17", "-DX=6")))

    def test_run_cpp_passes_extra_flags_and_their_values_on(self):
        header = self.root / "inc"
        header.mkdir()
        (header / "five.h").write_text("#define FIVE 5\n", encoding="utf-8")
        code = '#include <cstdio>\n#include "five.h"\nint main() { std::printf("%d\\n", FIVE); return 0; }\n'
        self.assertEqual((True, "5\n"), harness_env.run_cpp(code, extra=("-I", str(header))))
        self.assertEqual((True, "5\n"), harness_env.run_cpp(code, extra=("-I" + str(header),)))

    def test_run_cpp_sees_the_modules_common_headers_and_links_extra_sources(self):
        extra = self.write("extra.cpp", "int Extra() { return 4; }\n")
        code = ('#include "dc_request_gap.h"\n#include <cstdio>\nint Extra();\n'
                'int main() { std::printf("%d\\n", Extra()); return 0; }\n')
        self.assertEqual((True, "4\n"), harness_env.run_cpp(code, extra=[extra]))

    def test_build_text_stages_headers_by_content(self):
        code = '#include <cstdio>\n#include "v.h"\nint main() { std::printf("%d\\n", V); }\n'
        first = harness_env.build_text(code, files={"v.h": "#define V 1\n"})
        self.assertEqual("1", self.value(first))
        self.assertEqual(first, harness_env.build_text(code, files={"v.h": "#define V 1\n"}))
        self.assertEqual(2, len(harness_env.compiles))        # one compile and one link, the second call a hit
        self.assertEqual("2", self.value(harness_env.build_text(code, files={"v.h": "#define V 2\n"})))

    def test_stage_files_is_one_folder_per_content(self):
        one = harness_env.stage_files({"a/b.h": "x\n", "c.h": b"y\n"})
        self.assertEqual("x\n", (one / "a/b.h").read_text())
        self.assertEqual(one, harness_env.stage_files({"c.h": "y\n", "a/b.h": "x\n"}))
        self.assertNotEqual(one, harness_env.stage_files({"a/b.h": "x2\n", "c.h": "y\n"}))

    def test_a_hit_refreshes_the_age_of_what_it_used(self):
        binary = self.built()
        cache = self.root / "cache"
        entries = [binary.parent, *(cache / "obj").iterdir(), *(cache / "stage").iterdir()]
        old = time.time() - 86400
        for entry in entries:
            os.utime(entry, (old, old))
        self.built()
        for entry in entries:
            self.assertGreater(entry.stat().st_mtime, old + 3600, "%s kept its old age on a hit" % entry.parent.name)

    def test_a_repo_header_edited_in_place_is_noticed_even_at_the_same_length(self):
        header = self.write("value.h", "#define VALUE 5\n")
        main = self.write("main.cpp", MAIN)
        before = self.built(sources=[main], files={}, includes=[self.src])
        self.assertEqual("5", self.value(before))
        stamp = header.stat().st_mtime_ns
        header.write_text("#define VALUE 6\n", encoding="utf-8")
        os.utime(header, ns=(stamp, stamp))  # nothing for a size or mtime check to see
        after = self.built(sources=[main], files={}, includes=[self.src])
        self.assertEqual("6", self.value(after))
        self.assertNotEqual(before, after)
        self.assertEqual(2, harness_env.compiles.count(str(main)))
        header.write_text("#define VALUE 5\n", encoding="utf-8")
        self.assertEqual(before, self.built(sources=[main], files={}, includes=[self.src]))

    def test_a_hit_reads_the_headers_again(self):
        header = self.write("value.h", "#define VALUE 5\n")
        self.built(sources=[self.main], files={}, includes=[self.src])
        opened = []
        real = Path.read_bytes

        def spy(path):
            opened.append(str(path))
            return real(path)

        with mock.patch.object(Path, "read_bytes", spy):
            self.built(sources=[self.main], files={}, includes=[self.src])
        self.assertIn(str(header), opened)

    def test_a_shared_source_compiles_once_and_equal_objects_share_a_link(self):
        shared = self.write("shared.cpp", "int Shared() { return 3; }\n")
        a = self.write("a.cpp", '#include <cstdio>\nint Shared();\nint main() { std::printf("%d\\n", Shared() + 1); }\n')
        b = self.write("b.cpp", '#include <cstdio>\nint Shared();\nint main() { std::printf("%d\\n", Shared() + 2); }\n')
        one = self.built(sources=[a, shared], files={})
        two = self.built(sources=[b, shared], files={})
        self.assertEqual(("4", "5"), (self.value(one), self.value(two)))
        self.assertEqual(1, harness_env.compiles.count(str(shared)))
        self.assertEqual(3, len([c for c in harness_env.compiles if c != "link"]))
        harness_env.compiles.clear()
        self.assertEqual(one, self.built(sources=[a, shared], files={}))
        self.assertEqual([], harness_env.compiles)

    def test_a_broken_source_raises_with_the_compiler_text_and_is_not_remembered(self):
        broken = self.write("broken.cpp", "int main() { return missing_name; }\n")
        for _ in range(2):
            with self.assertRaises(harness_env.BuildError) as raised:
                self.built(sources=[broken], files={})
            self.assertIn("missing_name", raised.exception.stderr)
        self.assertEqual(2, harness_env.compiles.count(str(broken)))
        self.write("broken.cpp", "int main() { return 0; }\n")
        self.assertEqual("", self.value(self.built(sources=[broken], files={})))

    def test_threads_building_one_program_all_get_a_working_binary(self):
        got, errors = [], []

        def go():
            try:
                got.append(self.value(self.built()))
            except BaseException as error:  # noqa: BLE001 - reported below
                errors.append(error)

        threads = [threading.Thread(target=go) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual([], errors)
        self.assertEqual(["7"] * 4, got)
        self.assertEqual([], [p.name for p in (self.root / "cache/obj").iterdir() if p.name.startswith("tmp-")])

    def test_old_entries_are_pruned_and_used_ones_kept(self):
        old = self.built()
        kept = self.built(files={"value.h": "#define VALUE 8\n"})
        cache = self.root / "cache"
        stale = time.time() - harness_env.KEEP_SECONDS - 60
        os.utime(old.parent, (stale, stale))
        (cache / ".pruned").unlink(missing_ok=True)
        harness_env._pruned.discard(str(cache))
        self.built(files={"value.h": "#define VALUE 9\n"})
        self.assertFalse(old.exists(), "an entry unused past KEEP_SECONDS was kept")
        self.assertTrue(kept.exists(), "a recently used entry was deleted")

    def test_a_script_that_is_not_registered_may_not_build(self):
        """build() refuses an unregistered test on its own run, like run() (the registry is test_harness_core_limit)."""
        tree = self.root / "repo"
        scripts = tree / "mod-diablocraft/scripts"
        (scripts / "tests/tooling").mkdir(parents=True)
        for name in ("harness_env.py", "scripts_path.py", "tests/tooling/test_harness_core_limit.py"):
            (scripts / name).write_text((SCRIPTS / name).read_text(encoding="utf-8"), encoding="utf-8")
        (self.src / "x.cpp").write_text("int main() { return 0; }\n", encoding="utf-8")
        body = ("import sys\nsys.path.insert(0, %r)\nimport harness_env\nharness_env.build([%r])\n"
                % (str(scripts), str(self.src / "x.cpp")))
        script = scripts / "test_zz_not_registered.py"
        script.write_text(body, encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        ran = subprocess.run([sys.executable, str(script)], cwd=tree, env=env, capture_output=True, text=True)
        self.assertNotEqual(0, ran.returncode, "an unregistered test compiled through the cache")
        self.assertIn("RUNNERS", ran.stderr.strip().splitlines()[-1])


if __name__ == "__main__":
    unittest.main()
