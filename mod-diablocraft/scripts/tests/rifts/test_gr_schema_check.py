"""diablocraft-29u9: the startup schema check in dc_rift_scripts.cpp names the columns of rifts_0008 and rifts_0009.

RecordGreaterRiftBeaten writes dc_character_gr.beaten_solo and RecordGuardianResult writes dc_rift.time_left; a
missing migration fails the INSERT and the whole unlock is lost, so the load must say so loudly instead.
Cross-source: the (table, column) pairs and the file names come out of the two migrations, and the check in the
production source must be a `SELECT COUNT(<column>) FROM <table>` that throws and names the migration file.
DC_RIFTS_SOURCE points at a mutated copy (mutation runs)."""
import os
import re
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[3]
SOURCE = Path(os.environ.get('DC_RIFTS_SOURCE', MODULE / 'src/rifts/dc_rift_scripts.cpp')).read_text(encoding='utf-8')
MIGRATIONS = ('rifts_0008_gr_time_left.sql', 'rifts_0009_gr_beaten_solo.sql')


def added_columns(name):
    sql = (MODULE / 'data/sql/db-characters/updates' / name).read_text(encoding='utf-8')
    alter = re.search(r'ALTER TABLE `(\w+)`\s+ADD COLUMN `(\w+)`', sql)
    return alter.group(1), alter.group(2)


class StartupSchemaCheck(unittest.TestCase):
    def test_each_added_column_is_checked_and_names_its_migration(self):
        for name in MIGRATIONS:
            table, column = added_columns(name)
            check = re.search(r'if \(!CharacterDatabase\.Query\("SELECT COUNT\(%s\) FROM %s"\)\)\s*'
                              r'throw std::runtime_error\(\s*"[^"]*"?\s*"?[^;]*?%s' % (column, table, re.escape(name)),
                              SOURCE)
            self.assertTrue(check, f'{table}.{column} ({name}) has no startup check that throws and names the file')


if __name__ == '__main__':
    unittest.main()
