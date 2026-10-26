#!/usr/bin/env python3
"""Emit the sourced numeric unlock columns without regenerating other lanes."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_migration
from generate_sql import MODULE_ROOT, TABLES, render_table


def generate(module: Path = MODULE_ROOT):
    sql, count = render_table(module / 'data/d3/difficulty_tiers.csv', TABLES['difficulty_tiers'])
    (module / 'data/generated/difficulty_tiers.sql').write_text(sql, encoding='utf-8')
    write_migration(module, module / 'data/sql/db-world/updates/difficulty_0008_unlock_rules.sql', sql)
    return count


if __name__ == '__main__':
    import argparse
    import sys
    from applied_migrations import AppliedStateError
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        count = generate()
    except (AppliedStateError, OSError, UnicodeError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
    print(f'Generated {count} sourced tier unlock rows')
