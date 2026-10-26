// The follower companion's rules (src/campaign/dc_follower_rules.h), compiled alone and driven with the values
// of data/d3/followers_rules.csv, which the test script passes in seconds and yards: revive, party leave, catch-up
// seconds, catch-up yards.
#include "dc_follower_rules.h"

#include <cstdio>
#include <cstdlib>

namespace F = DC::Campaign::Followers;

static int failures = 0;
static void Check(bool ok, char const* what)
{
    if (!ok)
    {
        ++failures;
        std::fprintf(stderr, "FAIL: %s\n", what);
    }
}

static F::Situation Now(bool hired, bool alone, bool alive, bool out)
{
    F::Situation s;
    s.hired = hired;
    s.alone = alone;
    s.ownerAlive = alive;
    s.out = out;
    return s;
}

int main(int argc, char** argv)
{
    if (argc != 5)
        return 2;
    F::Rules rules;
    rules.reviveMs = std::uint32_t(std::atof(argv[1]) * 1000);
    rules.partyLeaveMs = std::uint32_t(std::atof(argv[2]) * 1000);
    rules.catchUpMs = std::uint32_t(std::atof(argv[3]) * 1000);
    rules.catchUpYards = float(std::atof(argv[4]));
    Check(F::Usable(rules), "the sheet's rules are usable");
    Check(!F::Usable(F::Rules{}), "a zero rule is refused");
    Check(F::Usable(F::Rules{20000, 0, 5000, 20.0f}), "the party rule may be zero: the follower goes at once");
    Check(!F::Usable(F::Rules{0, 0, 5000, 20.0f}) && !F::Usable(F::Rules{20000, 0, 0, 20.0f}) &&
              !F::Usable(F::Rules{20000, 0, 5000, 0.0f}),
          "the other rules may not be zero");

    // Nothing hired: never out, and the clock is cleared.
    {
        F::Clock c;
        c.reviveLeftMs = 5, c.partyMs = 7, c.ownerDown = true;
        Check(!F::Tick(c, 250, Now(false, true, true, true), rules), "nothing hired: no companion");
        Check(c.reviveLeftMs == 0 && c.partyMs == 0 && !c.ownerDown, "nothing hired: the clock is cleared");
    }
    // Hired, alone, alive: out at once, from the first step.
    {
        F::Clock c;
        Check(F::Tick(c, 250, Now(true, true, true, false), rules), "hired and alone: out at once");
        Check(F::Tick(c, 250, Now(true, true, true, true), rules), "and it stays");
    }
    // A fallen follower returns after exactly the revive rule.
    {
        F::Clock c;
        F::Fell(c, rules);
        std::uint32_t elapsed = 0;
        bool out = false;
        while (elapsed < rules.reviveMs - 250)
        {
            out = F::Tick(c, 250, Now(true, true, true, false), rules);
            elapsed += 250;
            Check(!out, "a fallen follower stays down before the revive rule is spent");
        }
        Check(F::Tick(c, 250, Now(true, true, true, false), rules), "a fallen follower returns when the rule is spent");
    }
    // The player falls: the follower goes down with them, the timer starts at that moment and runs while they lie dead.
    {
        F::Clock c;
        Check(!F::Tick(c, 250, Now(true, true, false, true), rules), "the player falls: the follower goes down");
        Check(c.ownerDown && c.reviveLeftMs == rules.reviveMs - 250, "the revive timer starts when the player falls");
        std::uint32_t dead = 250;
        while (dead < rules.reviveMs)
        {
            Check(!F::Tick(c, 250, Now(true, true, false, false), rules), "still down while the player lies dead");
            dead += 250;
        }
        Check(c.reviveLeftMs == 0, "the timer ran while the player was dead");
        Check(F::Tick(c, 250, Now(true, true, true, false), rules), "the player revives after the rule: the follower is back at once");
        Check(!c.ownerDown, "the player is up again");
    }
    // A short death: the follower waits out what is left of its timer after the player revives.
    {
        F::Clock c;
        F::Tick(c, 250, Now(true, true, false, true), rules);
        Check(!F::Tick(c, 250, Now(true, true, true, false), rules), "revived early: the follower is still down");
    }
    // A second player joins: a follower that is out stays for the party rule and then leaves; one not out never comes.
    // The sheet's rule is none (it leaves in the step the party forms); a one-second stand-in checks the wait itself.
    for (std::uint32_t leave : {rules.partyLeaveMs, std::uint32_t(1000)})
    {
        F::Rules waits = rules;
        waits.partyLeaveMs = leave;
        F::Clock c;
        std::uint32_t joined = 0;
        while (joined + 250 < leave)
        {
            Check(F::Tick(c, 250, Now(true, false, true, true), waits), "a follower already out stays until the party rule is spent");
            joined += 250;
        }
        Check(!F::Tick(c, 250, Now(true, false, true, true), waits), "it leaves when the party rule is spent");
        Check(!F::Tick(c, 250, Now(true, false, true, false), waits), "and stays gone while the party stands");
        Check(F::Tick(c, 250, Now(true, true, true, false), waits), "it returns when the player is alone again");
        F::Clock fresh;
        Check(!F::Tick(fresh, 250, Now(true, false, true, false), waits), "a follower not out does not come to a party");
        // The hire is kept all through: the party ends, the same follower is wanted again, and the clock is clean.
        Check(c.partyMs == 0, "the party clock starts over when the party ends");
    }
    // The catch-up: beyond the yards for the rule's time, then it starts over; at the yards or nearer, never.
    {
        std::uint32_t far = 0, elapsed = 0;
        while (elapsed + 250 < rules.catchUpMs)
        {
            Check(!F::CatchUp(far, 250, rules.catchUpYards + 1.0f, rules), "left behind, but not for long enough");
            elapsed += 250;
        }
        Check(F::CatchUp(far, 250, rules.catchUpYards + 1.0f, rules), "left behind for the rule's time: it jumps");
        Check(far == 0, "and the count starts over");
        Check(!F::CatchUp(far, 250, rules.catchUpYards + 1.0f, rules), "one step later it has not jumped again");
        far = 100;
        Check(!F::CatchUp(far, rules.catchUpMs * 4, rules.catchUpYards, rules) && far == 0,
              "exactly at the yards counts as beside the player");
        far = 100;
        Check(!F::CatchUp(far, 250, 0.0f, rules) && far == 0, "beside the player resets the count");
    }
    // What talking to a follower offers: Hire in the hub for a follower that is not the hired one; nothing outside it.
    {
        using Id = F::Id;
        Check(F::OffersHire(true, Id::None, Id::Templar), "in the hub, with nothing hired, a follower offers Hire");
        Check(F::OffersHire(true, Id::Scoundrel, Id::Templar), "in the hub, another follower offers Hire (it replaces)");
        Check(!F::OffersHire(true, Id::Templar, Id::Templar), "the hired follower offers no Hire");
        Check(!F::OffersHire(false, Id::None, Id::Templar), "outside the hub nothing is hired by talking");
        Check(!F::OffersHire(false, Id::Scoundrel, Id::Templar), "outside the hub, with another hired, nothing either");
        Check(!F::OffersHire(true, Id::None, Id::None) && !F::OffersHire(true, Id::Templar, Id::None),
              "no follower, no Hire");
    }
    // The ids and the side it walks on.
    Check(!F::Valid(0) && F::Valid(1) && F::Valid(3) && !F::Valid(4), "ids 1 to 3");
    Check(F::FollowAngle > 1.0f && F::FollowAngle < 2.0f, "a flank, not trailing behind");
    Check(F::IsFollowerScript("dc_follower") && !F::IsFollowerScript("dc_legendary_ally"), "the script name");
    return failures ? 1 : 0;
}
