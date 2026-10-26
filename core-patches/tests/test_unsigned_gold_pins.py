"""Pin what core patch 0005 (unsigned gold accounting) leaves in the installed core.

0007 rewrote some of 0005's hunks (ModifyMoney's body, the debit casts in several
handlers), so after 0007 the arithmetic harness (test_account_economy.py) no longer
notices if 0005 is lost: with 0005 partly or wholly reverted it stays green. This test reads the installed source and pins every place
0005 changed, and then proves it can fail: it rebuilds the installed files with 0005
reverted fully (the 0005 files as they are at core-commit.txt), reverted partly (the
hunks that reverse cleanly, which is what is left once 0007 has rewritten the rest),
each file reverted alone, the debit widening undone at one call site, and a trade
guard narrowed, and requires the check to fail on each, naming the right check.

Core, patch folder and pin come from the environment so the same test runs against
another tree: TORMENT_CORE, TORMENT_PATCHES, TORMENT_PIN (defaults: this repo's
azerothcore-wotlk, core-patches and core-commit.txt). Nothing in the core is written;
scratch is under build/_agent-scratch.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
CORE = Path(os.environ.get('TORMENT_CORE') or REPO / 'azerothcore-wotlk')
PATCHES = Path(os.environ.get('TORMENT_PATCHES') or REPO / 'core-patches')
PIN = os.environ.get('TORMENT_PIN') or (REPO / 'core-commit.txt').read_text(encoding='utf-8').split()[0]
OUT = REPO / 'azerothcore-wotlk/build/_agent-scratch/scripts/unsigned-gold-pins'
GAME = 'src/server/game/'

# file -> literal fragments 0005 leaves in it (whitespace-insensitive)
PINS = {
    'Entities/Player/Player.h': [
        '#define MAX_MONEY_AMOUNT 0xFFFFFFFFu',
        'bool ModifyMoney(int64 amount, bool sendError = true);',
        'uint8 slot, uint32 price, ItemTemplate const* pProto, Creature* pVendor',
    ],
    'Entities/Player/Player.cpp': [
        'bool Player::ModifyMoney(int64 amount, bool sendError /*= true*/)',
        'sScriptMgr->OnPlayerMoneyChangedWide(this, amount);',
        'if (GetMoney() > cap || uint64(amount) > uint64(cap) - GetMoney())',
        'int64 excessPoints = int64(value) - sWorld->getIntConfig(CONFIG_MAX_HONOR_POINTS);',
        'double baseCost = double(LostDurability) * dmultiplier * dQualitymodEntry->quality_mod;',
        'if (baseCost > MAX_MONEY_AMOUNT)',
        'double adjustedCost = double(costs) * discountMod * sWorld->getRate(RATE_REPAIRCOST);',
        'if (adjustedCost > MAX_MONEY_AMOUNT)',
        'if (cost > MAX_MONEY_AMOUNT - totalcost)',
        'totalcost = uint32(std::min(double(MAX_MONEY_AMOUNT), ceil(double(totalcost) * discount)));',
        'firstcost = uint32(std::min(double(MAX_MONEY_AMOUNT), ceil(double(firstcost) * discount)));',
        'price = uint32(std::min(double(MAX_MONEY_AMOUNT), std::floor(double(price) * GetReputationPriceDiscount(creature))));',
        'uint8 slot, uint32 price, ItemTemplate const* pProto, Creature* pVendor',
    ],
    'Entities/Player/PlayerGossip.cpp': ['uint32 cost = item->BoxMoney;'],
    'Entities/Player/PlayerQuest.cpp': [
        'int64 moneyRew = 0;',
        'uint32(std::min<int64>(moneyRew, MAX_MONEY_AMOUNT))',
    ],
    'Entities/Creature/Trainer.cpp': [
        'uint32 moneyCost = uint32(std::min(double(MAX_MONEY_AMOUNT), double(trainerSpell->MoneyCost) * reputationDiscount));',
    ],
    'Movement/MovementGenerators/WaypointMovementGenerator.h': ['uint32 Cost;'],
    'Movement/MovementGenerators/WaypointMovementGenerator.cpp': [
        'uint32(std::min(double(MAX_MONEY_AMOUNT), ceil(double(cost) * discount)))',
    ],
    'AuctionHouse/AuctionHouseMgr.cpp': [
        'uint32 deposit = uint32(std::min(double(MAX_MONEY_AMOUNT), ((double(multiplier) * MSV * count / 3) * timeHr * 3) * sWorld->getRate(RATE_AUCTION_DEPOSIT)));',
        'uint64 totalProfit = uint64(auction->bid) + auction->deposit - auction->GetAuctionCut();',
        'uint32 profit = uint32(std::min<uint64>(totalProfit, MAX_MONEY_AMOUNT));',
        'uint32 extraProfit = uint32(totalProfit - profit);',
        'if (sendMail && extraProfit)',
        'return uint32(std::clamp(cut, 0.0, double(bid)));',
    ],
    'Handlers/AuctionHouseHandler.cpp': [
        'uint64(price) < uint64(auction->bid) + AuctionEntry::CalculateAuctionOutBid(auction->bid)',
    ],
    'Handlers/MailHandler.cpp': [
        'uint64 totalCost = uint64(cost) + money;',
        'if (!PlayerEconomy::Managed() && totalCost > MAX_MONEY_AMOUNT)',
        'uint64 reqmoney = totalCost;',
    ],
    'Handlers/ItemHandler.cpp': [
        'uint64 totalMoney = uint64(pProto->SellPrice) * packet.Count;',
        'if (totalMoney > UINT32_MAX || totalMoney > (PlayerEconomy::Managed() ? UINT64_MAX : uint64(MAX_MONEY_AMOUNT)) - _player->GetAccountMoney())',
        'uint32 money = uint32(totalMoney);',
    ],
    'Scripting/ScriptMgr.h': ['void OnPlayerMoneyChangedWide(Player* player, int64& amount);'],
    'Scripting/ScriptDefines/PlayerScript.h': [
        'PLAYERHOOK_ON_MONEY_CHANGED_WIDE,',
        'virtual void OnPlayerMoneyChangedWide(Player* /*player*/, int64& /*amount*/) { }',
    ],
    'Scripting/ScriptDefines/PlayerScript.cpp': [
        'void ScriptMgr::OnPlayerMoneyChangedWide(Player* player, int64& amount)',
        'PLAYERHOOK_ON_MONEY_CHANGED_WIDE, script->OnPlayerMoneyChangedWide(player, amount)',
    ],
    '../scripts/Commands/cs_modify.cpp': [
        'int64 moneyToAdd = *moneyToAddO;',
    ],
}

# the two trade-window guards, written the way the trade handler evaluates them
TRADE_GUARDS = [
    'his_trade->GetMoney() > (PlayerEconomy::Managed() ? UINT64_MAX : uint64(MAX_MONEY_AMOUNT)) - (_player->GetAccountMoney() - my_trade->GetMoney())',
    'my_trade->GetMoney() > (PlayerEconomy::Managed() ? UINT64_MAX : uint64(MAX_MONEY_AMOUNT)) - (trader->GetAccountMoney() - his_trade->GetMoney())',
]
TRADE = 'Handlers/TradeHandler.cpp'
MIN_DEBIT_SITES = 20


def norm(text):
    return re.sub(r'\s+', ' ', text)


def full(rel):
    # PINS keys are relative to src/server/game/ unless they climb out of it
    return os.path.normpath(GAME + rel).replace('\\', '/')


class Source:
    def __init__(self, overlay=None):
        self.overlay = overlay or {}

    def text(self, path):
        if path in self.overlay:
            return self.overlay[path]
        return (CORE / path).read_text(encoding='utf-8')


def money_files():
    found = []
    for path in sorted((CORE / 'src/server').rglob('*.cpp')):
        if 'ModifyMoney(-' in path.read_text(encoding='utf-8', errors='replace'):
            found.append(path.relative_to(CORE).as_posix())
    return found


def check(source, debit_files):
    """Return {check id: message} for everything that does not hold."""
    failed = {}
    sites = 0
    for path in sorted(set(debit_files) | set(source.overlay)):
        for number, line in enumerate(source.text(path).splitlines(), 1):
            if 'ModifyMoney(-' in line:
                sites += 1
                if 'ModifyMoney(-int64(' not in line:
                    failed.setdefault('debit-widening', f'{path}:{number}: {line.strip()}')
    if sites < MIN_DEBIT_SITES:
        failed.setdefault('debit-widening', f'only {sites} debit call sites found; the audit is not looking at the core')
    trade = norm(source.text(full(TRADE)))
    for guard in TRADE_GUARDS:
        if norm(guard) not in trade:
            failed.setdefault('trade-guard', guard)
    for rel, needles in PINS.items():
        path = full(rel)
        text = norm(source.text(path))
        for needle in needles:
            if norm(needle) not in text:
                failed.setdefault(Path(path).name, []).append(needle)
    return failed


def patch_files():
    patch = next(PATCHES.glob('0005-*.patch'))
    files = re.findall(r'^\+\+\+ b/(\S+)$', patch.read_text(encoding='utf-8'), re.M)
    assert len(files) >= 20, (patch, files)
    return patch, files


def pristine(files):
    check_pin = subprocess.run(['git', '-C', str(CORE), 'cat-file', '-e', PIN + '^{commit}'])
    assert check_pin.returncode == 0, f'core history lacks pin {PIN}; cannot rebuild the unpatched files'
    out = {}
    for path in files:
        shown = subprocess.run(['git', '-C', str(CORE), 'show', f'{PIN}:{path}'], capture_output=True, text=True, encoding='utf-8')
        assert shown.returncode == 0, (path, shown.stderr)
        out[path] = shown.stdout
    return out


def partly_reverted(patch, files):
    work = OUT / 'partial'
    shutil.rmtree(work, ignore_errors=True)
    for path in files:
        (work / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CORE / path, work / path)
    environment = dict(os.environ, GIT_CEILING_DIRECTORIES=str(OUT))
    result = subprocess.run(['git', 'apply', '-R', '--reject', '--whitespace=nowarn', str(patch)],
                            cwd=work, env=environment, capture_output=True, text=True)
    rejects = len(list(work.rglob('*.rej')))
    changed = {path: (work / path).read_text(encoding='utf-8') for path in files}
    shutil.rmtree(work, ignore_errors=True)
    return changed, rejects, result.returncode


def expect_fail(name, source, debit_files, only=None):
    failed = check(source, debit_files)
    assert failed, f'{name}: the check still passes, so it does not pin 0005'
    if only is not None:
        assert only in failed, f'{name}: failed on {sorted(failed)}, not on {only}'
    print(f'PASS {name}: fails on {", ".join(sorted(failed))}')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    patch, files = patch_files()
    debit_files = money_files()
    installed = Source()
    failed = check(installed, debit_files)
    assert not failed, 'installed core lost part of 0005:\n' + '\n'.join(f'  {key}: {value}' for key, value in sorted(failed.items()))
    print(f'PASS 0005 applied: {sum(len(v) for v in PINS.values())} source pins, {len(TRADE_GUARDS)} trade guards, '
          f'debit audit over {len(debit_files)} files, all hold.')

    originals = pristine(files)
    expect_fail('0005 reverted fully (its files as at the pin)', Source(originals), debit_files)

    partial, rejects, _ = partly_reverted(patch, files)
    assert rejects > 0, 'a partial revert should leave rejected hunks once 0007 has rewritten them'
    assert any(partial[path] != installed.text(path) for path in files), 'partial revert changed nothing'
    expect_fail(f'0005 reverted partly ({rejects} files keep hunks that 0007 rewrote)', Source(partial), debit_files)

    for path in files:
        expect_fail(f'0005 reverted in {Path(path).name} alone', Source({path: originals[path]}), debit_files)

    # one debit widening undone at one call site, in a file that carries nothing else of 0005's
    path = next(p for p in files if p.endswith('Guild/Guild.cpp') or p.endswith('Guilds/Guild.cpp'))
    text = installed.text(path)
    site = re.search(r'ModifyMoney\(-int64\(', text)
    assert site, path
    expect_fail('debit widening mutated at one call site',
                Source({path: text[:site.start()] + 'ModifyMoney(-int32(' + text[site.end():]}), debit_files, only='debit-widening')

    trade = installed.text(full(TRADE))
    for number, guard in enumerate(TRADE_GUARDS, 1):
        narrowed = guard.replace('uint64(MAX_MONEY_AMOUNT)', 'int32(MAX_MONEY_AMOUNT)', 1)
        assert norm(guard) in norm(trade)
        mutated = re.sub(r'\s+', ' ', trade).replace(norm(guard), norm(narrowed))
        expect_fail(f'trade guard {number} narrowed to int32', Source({full(TRADE): mutated}), debit_files, only='trade-guard')

    header = installed.text(GAME + 'Entities/Player/Player.h')
    capped = re.sub(r'(#define\s+MAX_MONEY_AMOUNT\s+)0xFFFFFFFFu', r'\g<1>(0x7FFFFFFF-1)', header)
    assert capped != header
    expect_fail('MAX_MONEY_AMOUNT back to the signed ceiling', Source({GAME + 'Entities/Player/Player.h': capped}), debit_files, only='Player.h')

    # control: a harmless edit (a comment) must not trip it
    harmless = {path: installed.text(path) + '\n// unrelated edit\n'}
    assert not check(Source(harmless), debit_files), 'an unrelated edit made the check fail'
    print('PASS control: an unrelated edit leaves the check green.')


if __name__ == '__main__':
    main()
