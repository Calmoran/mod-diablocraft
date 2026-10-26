# Constant (audit 144, 1800): Stale build-lock timeout seconds; Operational tooling, no gameplay effect; script was read, never run.
# Constant (audit 145, 10): Build-lock retry interval seconds; Operational tooling, no gameplay effect; script was read, never run.
# Constant (audit 146, 5): Build-lock heartbeat interval seconds; Operational tooling, no gameplay effect; script was read, never run.
# Constant (audit 147, 45): Failure-log tail line count; Operational tooling, no gameplay effect; script was read, never run.
"""Serial account-economy server build; safe shared lock and scratch logs."""
from pathlib import Path
import os
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    lock = ROOT / "build.lock"
    owner = f"Codex account economy {uuid.uuid4()} {time.time()}"
    while True:
        try:
            with lock.open("x", encoding="utf-8") as stream:
                stream.write(owner)
            break
        except FileExistsError:
            if time.time() - lock.stat().st_mtime >= 1800:
                raise RuntimeError("Stale build.lock: inspect owner before continuing")
            print("Waiting for build.lock", flush=True)
            time.sleep(10)
    try:
        logs = ROOT / "azerothcore-wotlk/build/_agent-scratch/logs"
        logs.mkdir(parents=True, exist_ok=True)
        path = logs / f"account-economy-{time.strftime('%Y%m%d-%H%M%S')}.log"
        print(f"Build log: {path}", flush=True)
        with path.open("w", encoding="utf-8") as log:
            subprocess.run(
                [r"C:\Program Files\CMake\bin\cmake.exe", "-S", "azerothcore-wotlk", "-B", "azerothcore-wotlk/build"],
                cwd=ROOT, env={key.upper(): value for key, value in os.environ.items()},
                stdout=log, stderr=subprocess.STDOUT, check=True)
            process = subprocess.Popen(
                [r"C:\Program Files\CMake\bin\cmake.exe", "--build", "azerothcore-wotlk/build",
                 "--config", "Release", "--target", "worldserver", "--", "-m:1", "/p:CL_MPCount=1"],
                cwd=ROOT, env={key.upper(): value for key, value in os.environ.items()},
                stdout=log, stderr=subprocess.STDOUT)
            while process.poll() is None:
                os.utime(lock, None)
                time.sleep(5)
        if process.returncode:
            print("\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-45:]))
            raise RuntimeError(f"Build failed: {process.returncode}")
        print("PASS Release worldserver build", flush=True)
    finally:
        if lock.read_text(encoding="utf-8") == owner:
            lock.unlink()


if __name__ == "__main__":
    main()
