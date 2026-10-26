#ifndef DC_IDENTIFY_RULE_H
#define DC_IDENTIFY_RULE_H

// G7 (docs/security.md): one rule for every way into identification - the
// right-click spell, the tome, `.dc identify slot` and the Lua Identify that
// runs it. Alive, out of combat, and the shell is not in a trade window.
// Pure, so the test compiles this very header. Returns nullptr when allowed.
namespace DC::Identify
{
constexpr char const* Refusal(bool alive, bool inCombat, bool itemInTrade)
{
    return !alive ? "You cannot identify while dead."
         : inCombat ? "You cannot identify in combat."
         : itemInTrade ? "That item is in a trade."
         : nullptr;
}
}

#endif // DC_IDENTIFY_RULE_H
