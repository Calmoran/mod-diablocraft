// diablocraft-crash-ancients-summon: the module's own dc_barbarian_call_of_the_ancients.h guards, compiled against
// mock AIs shaped like the real ones (ScriptedAI keeps its own `me`, CreatureAI has another).
#include "dc_barbarian_call_of_the_ancients.h"
#include <cstdio>

namespace A = DC::Classes::Ancients;

struct Creature {};
struct CreatureAI { virtual ~CreatureAI() = default; Creature* const me; explicit CreatureAI(Creature* c) : me(c) {} };
struct ScriptedAI : CreatureAI { Creature* me; explicit ScriptedAI(Creature* c) : CreatureAI(c), me(c) {} };
struct AncientAI final : ScriptedAI { using ScriptedAI::ScriptedAI; };
struct RiftMeleeAI final : CreatureAI { using CreatureAI::CreatureAI; };

static int failures = 0;
static void Check(bool ok, char const* what)
{
    if (!ok)
    {
        ++failures;
        std::fprintf(stderr, "FAIL: %s\n", what);
    }
}

int main()
{
    Creature c;
    RiftMeleeAI rift(&c);
    AncientAI ours(&c);
    CreatureAI* swapped = &rift;
    CreatureAI* own = &ours;
    Check(A::AiAs<AncientAI>(swapped) == nullptr, "a rift AI is not taken for the ancient AI");
    Check(A::AiAs<AncientAI>(own) == &ours, "the ancient AI is recognised");
    Check(A::AiAs<AncientAI>(static_cast<CreatureAI*>(nullptr)) == nullptr, "a creature with no AI is refused");
    Check(!A::IsAncientEntry(900099) && A::IsAncientEntry(900100) && A::IsAncientEntry(900101) &&
          A::IsAncientEntry(900102) && !A::IsAncientEntry(900103), "the entry range is 900100-900102");
    // diablocraft-i8i3: companions. Fight the owner's victim, else his selection only while he is in
    // combat; with nothing to fight the order is Follow (Pick::None).
    using P = A::Pick;
    Check(A::PickTarget(false, false, false) == P::None, "nothing to fight: follow");
    Check(A::PickTarget(false, false, true) == P::None, "a mere selection out of combat does not start a fight");
    Check(A::PickTarget(false, true, true) == P::Selected, "in combat, the owner's selection is fought");
    Check(A::PickTarget(false, true, false) == P::None, "in combat with no usable selection: follow");
    Check(A::PickTarget(true, false, true) == P::Victim, "the owner's victim comes first");
    Check(A::PickTarget(true, true, true) == P::Victim, "the victim beats the selection");
    Check(A::FollowAngle(0) != A::FollowAngle(1) && A::FollowAngle(1) != A::FollowAngle(2) &&
          A::FollowAngle(0) != A::FollowAngle(2), "each Ancient has its own spot beside the owner");
    return failures ? 1 : 0;
}
