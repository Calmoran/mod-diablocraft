// diablocraft-barbarian-skills B (GitHub #44): Bash - Punish's buff through the
// module's own Punish and DamageBonus. argv: the values sheet's
// damage_bonus_pct, max_stacks_count and duration in milliseconds.
#include "punish_shim.h"
#include "dc_barbarian_primary_data.h"
#include "dc_spell_shells.h"
#include "punish_extract.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>

namespace P = DC::Combat::Primaries;
namespace D = DC::Combat::PrimaryData;

static int failures = 0;
static void Check(bool ok, std::string const& what)
{
    if (!ok)
    {
        ++failures;
        std::fprintf(stderr, "FAIL: %s\n", what.c_str());
    }
}

int main(int argc, char** argv)
{
    if (argc != 4)
        return 2;
    double const pct = std::atof(argv[1]);
    unsigned const cap = unsigned(std::atoi(argv[2]));
    int32 const duration = std::atoi(argv[3]);
    uint32 const id = DC::Combat::Shells::HelperFor("Punish");
    Check(id != 0, "the generated helper table names a Punish record");
    D::Row const* row = D::Find(81034);
    Check(row && row->behavior == D::Behavior::punish, "81034 is Bash - Punish");
    if (!row || !id)
        return 1;

    Player player;
    Check(P::DamageBonus(&player) == 0, "no buff, no bonus");
    for (unsigned cast = 1; cast <= cap + 2; ++cast)
    {
        P::Punish(&player, *row);
        Aura* aura = player.GetAura(id);
        unsigned const expected = std::min(cast, cap);
        Check(aura != nullptr, "cast " + std::to_string(cast) + ": the buff is on the player");
        if (!aura)
            continue;
        Check(aura->GetStackAmount() == expected, "cast " + std::to_string(cast) + ": " +
                                                      std::to_string(aura->GetStackAmount()) + " stacks, expected " +
                                                      std::to_string(expected));
        Check(aura->duration == duration && aura->maxDuration == duration,
              "cast " + std::to_string(cast) + ": timer " + std::to_string(aura->duration) + " ms, expected " +
                  std::to_string(duration));
        double const bonus = P::DamageBonus(&player);
        Check(std::fabs(bonus - expected * pct) < 1e-9, "cast " + std::to_string(cast) + ": bonus " +
                                                            std::to_string(bonus) + "%, expected " +
                                                            std::to_string(expected * pct) + "%");
    }
    Check(player.adds == 1, "one aura, restacked, not a new one per cast");

    // The aura's own expiry is the end of the bonus, and the next cast starts over.
    player.Expire(id);
    Check(P::DamageBonus(&player) == 0, "expired buff, no bonus");
    P::Punish(&player, *row);
    Check(player.GetAura(id) && player.GetAura(id)->GetStackAmount() == 1, "after expiry the next cast is one stack");
    Check(std::fabs(P::DamageBonus(&player) - pct) < 1e-9, "after expiry the bonus is one stack's");

    if (failures)
        return 1;
    std::puts("ok");
    return 0;
}
