"""diablocraft-dm9vg.9 - the Horadric Caches are account-bound, like D3's (the designer, decisions 2026-10-12 (2)).

What this proves, and what it does not:

  * The migration `bounties_0004_cache_account_bound.sql` is the generator's render, and its mirror. It sets the five
    caches (the generated bounties_0003 rows) to the core's bind-to-account flag and bind on pickup.
  * The flag is the core's: its value is read out of ItemTemplate.h. The core's account rules key on that flag alone
    (Item::IsBoundAccountWide; the mail handler sends a bound account item only to the same account). Those lines are
    pinned, not executed.
  * Replayed on a disposable MySQL: bounties_0003, then 0004 twice. Each cache reads back with the has-loot flag and the
    bind flag, bonding 1. Each part of the UPDATE has a mutant that must fail that check.
  * Not covered: the client. Item.dbc carries no flags or bonding (build_item.py's record: class, subclass, sound,
    material, display, inventory type, sheath), so there is no client change. The tooltip comes from the server's item
    query; the test sheet checks it on dev, together with bags, stash and mail.

    python3 mod-diablocraft/scripts/tests/items/test_cache_account_bound.py
"""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_bounties as G  # noqa: E402
from test_account_economy_sql import MYSQL, isolated  # noqa: E402
from test_set_caches import STUB  # noqa: E402
from test_slot_vendors import check  # noqa: E402

MODULE = G.MODULE
UPDATES = MODULE / "data/sql/db-world/updates"
CORE = MODULE.parent / "azerothcore-wotlk/src/server/game"
CACHES = [101141, 101142, 101143, 101144, 101145]
HAS_LOOT = 0x4


def core_flag():
    found = re.search(r"ITEM_FLAG_IS_BOUND_TO_ACCOUNT\s*=\s*(0x[0-9A-Fa-f]+)",
                      (CORE / "Entities/Item/ItemTemplate.h").read_text(encoding="utf-8"))
    return int(found.group(1), 16)


def test_render():
    text = (UPDATES / G.BOUND).read_text(encoding="utf-8")
    check(text == G.render_cache_binding(), "the migration is the generator's render")
    check(text == (MODULE / "data/generated" / G.BOUND).read_text(encoding="utf-8"), "the generated mirror is the migration")
    check(G.BOUND > G.CACHES, "a new migration after bounties_0003 (which stays as it is)")
    check(G.ITEM_FLAG_IS_BOUND_TO_ACCOUNT == core_flag() == 0x08000000, "the flag is the core's ITEM_FLAG_IS_BOUND_TO_ACCOUNT")
    item = (CORE / "Entities/Item/Item.h").read_text(encoding="utf-8")
    check("bool IsBoundAccountWide() const { return GetTemplate()->HasFlag(ITEM_FLAG_IS_BOUND_TO_ACCOUNT) != 0; }" in item,
          "core: an item is account-bound by that flag alone, whatever its quality")
    mail = (CORE / "Handlers/MailHandler.cpp").read_text(encoding="utf-8")
    check("if (item->IsBoundAccountWide() && item->IsSoulBound() && GetAccountId() != rc_account)" in mail,
          "core: a bound account item is mailed only to the same account")


def test_mysql(port):
    command = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root",
               "--batch", "--raw", "--skip-column-names", "--default-character-set=utf8mb4"]

    def sql(text, database):
        done = subprocess.run(command + [f"--database={database}"], input=text, text=True, capture_output=True,
                              encoding="utf-8")
        if done.returncode:
            raise RuntimeError(done.stderr)
        return done.stdout.rstrip("\n")

    caches = (UPDATES / G.CACHES).read_text(encoding="utf-8")
    bound = (UPDATES / G.BOUND).read_text(encoding="utf-8")
    want = "\n".join(f"{e}\t{HAS_LOOT | core_flag()}\t1" for e in CACHES)

    def replayed(name, migration):
        subprocess.run(command, input=f"CREATE DATABASE {name} CHARACTER SET utf8mb4;", text=True, check=True)
        sql(STUB, name)
        sql(caches, name)
        sql(migration, name)
        sql(migration, name)
        return sql("SELECT entry, Flags, bonding FROM item_template WHERE entry BETWEEN 101141 AND 101145 ORDER BY entry", name)

    check(replayed("cache_bound", bound) == want, "0003 then 0004 twice: each cache has loot, binds to account, bonding 1")
    mutants = [
        ("no bind flag", "`Flags` = `Flags` | 134217728, ", ""),
        ("the flag replaces the has-loot flag", "`Flags` = `Flags` | 134217728", "`Flags` = 134217728"),
        ("bonding left as it was", ", `bonding` = 1", ""),
    ]
    for number, (what, old, new) in enumerate(mutants):
        assert bound.count(old) == 1, "mutant target moved: " + old
        check(replayed(f"cache_mutant_{number}", bound.replace(old, new)) != want, "mutant killed: " + what)
    print("PASS isolated MySQL checks; no live database selected", flush=True)


if __name__ == "__main__":
    test_render()
    isolated(test_mysql)
    print("PASS all")
