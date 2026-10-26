#!/usr/bin/env python3
"""Exercise the production SQL claim guard on connection-local TEMPORARY tables.

No persistent player/drop/account row is read or written. MySQL --force lets
these fixtures explicitly ROLLBACK after the expected CHECK failures, matching
MySQLConnection::ExecuteTransaction's rollback on a failed statement.
"""
import argparse
import subprocess
from pathlib import Path


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--defaults-file', default=None)
    parser.add_argument('--mysql', default=None)
    args = parser.parse_args()
    if not (args.mysql and args.defaults_file):
        import fixture_db
        fixture_mysql, fixture_defaults = fixture_db.mysql_and_defaults([])
        args.mysql, args.defaults_file = args.mysql or fixture_mysql, args.defaults_file or fixture_defaults
    source = (Path(__file__).resolve().parents[3] / 'src/loot/dc_loot_delivery.cpp').read_text()
    # Exercise the actual SQL guard string rather than a parallel assertion.
    guard = 'INSERT INTO dc_loot_claim_check(id,valid) VALUES({},IF(ROW_COUNT()=1,1,0))'
    assert guard in source
    def claim(row):
        return (f'DELETE FROM dc_loot_buffer WHERE id={row} AND guid=99 AND expires_at>NOW();\n'
                + guard.replace('{}',str(row)) + ';\n'
                + f'DELETE FROM dc_loot_claim_check WHERE id={row};\n')
    sql = '''CREATE TEMPORARY TABLE dc_loot_buffer LIKE dc_loot_buffer;
CREATE TEMPORARY TABLE dc_loot_claim_check LIKE dc_loot_claim_check;
CREATE TEMPORARY TABLE dc_ground_test_inventory (count INT NOT NULL) ENGINE=InnoDB;
INSERT INTO dc_ground_test_inventory VALUES(0);
INSERT INTO dc_loot_buffer(id,guid,base_item,item_level,kind,carrier_guid,map_id,expires_at) VALUES
(1,99,100000,70,'ground',101,1,DATE_ADD(NOW(),INTERVAL 600 SECOND)),
(2,99,100000,70,'ground',102,1,DATE_SUB(NOW(),INTERVAL 1 SECOND)),
(3,99,100000,70,'ground',103,1,DATE_ADD(NOW(),INTERVAL 600 SECOND)),
(4,99,100000,70,'ground',104,1,DATE_ADD(NOW(),INTERVAL 600 SECOND)),
(5,99,100000,70,'ground',700,1,DATE_ADD(NOW(),INTERVAL 600 SECOND)),
(6,99,100000,70,'ground',700,2,DATE_ADD(NOW(),INTERVAL 600 SECOND));
START TRANSACTION;
'''+claim(1)+'''UPDATE dc_ground_test_inventory SET count=count+1;
COMMIT;
SELECT 'pickup',count FROM dc_ground_test_inventory;
START TRANSACTION;
UPDATE dc_ground_test_inventory SET count=count+1;
'''+claim(1)+'''ROLLBACK;
SELECT 'duplicate',count FROM dc_ground_test_inventory;
START TRANSACTION;
UPDATE dc_ground_test_inventory SET count=count+1;
'''+claim(2)+'''ROLLBACK;
SELECT 'expiry',count FROM dc_ground_test_inventory;
START TRANSACTION;
'''+claim(3)+'''UPDATE dc_ground_test_inventory SET count=count+1;
INSERT INTO dc_loot_claim_check VALUES(3,0);
ROLLBACK;
SELECT 'failed_delivery',count FROM dc_ground_test_inventory;
SELECT 'descriptor_restored',COUNT(*) FROM dc_loot_buffer WHERE id=3;
SELECT 'refused_click_unchanged',COUNT(*) FROM dc_loot_buffer WHERE id=4;
SELECT 'buffer_drain_excludes_ground',COUNT(*) FROM dc_loot_buffer WHERE kind<>'ground';
START TRANSACTION;
'''+claim(5)+'''UPDATE dc_ground_test_inventory SET count=count+1;
COMMIT;
SELECT 'other_map_survives',COUNT(*) FROM dc_loot_buffer WHERE map_id=2 AND carrier_guid=700;
SELECT 'claim_check_empty',COUNT(*) FROM dc_loot_claim_check;
'''
    sql = sql.replace('dc_loot_buffer','dc_ground_fixture_buffer').replace('dc_loot_claim_check','dc_ground_fixture_check')
    sql = sql.replace('LIKE dc_ground_fixture_buffer','LIKE dc_loot_buffer').replace('LIKE dc_ground_fixture_check','LIKE dc_loot_claim_check')
    result = subprocess.run([args.mysql,f'--defaults-file={args.defaults_file}', '--force', '--batch',
                             '--skip-column-names','acore_characters'],input=sql,text=True,capture_output=True)
    expected = ['pickup\t1','duplicate\t1','expiry\t1','failed_delivery\t1','descriptor_restored\t1',
                'refused_click_unchanged\t1','buffer_drain_excludes_ground\t0','other_map_survives\t1','claim_check_empty\t0']
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == expected, result.stdout + result.stderr
    assert result.stderr.count('ERROR 3819') == 3, result.stderr
    assert result.stderr.count('ERROR ') == 3, result.stderr
    print('SQL claims passed: pickup, duplicate, expiry, delivery rollback, refusal, buffer isolation and map-local GUIDs')


if __name__ == '__main__':
    main()
