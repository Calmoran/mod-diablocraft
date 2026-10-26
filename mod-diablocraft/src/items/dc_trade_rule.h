#ifndef DC_TRADE_RULE_H
#define DC_TRADE_RULE_H

// Every item is account bound, so
// the trade window carries gold and nothing else. The core asks
// PlayerScript::OnPlayerCanSetTradeItem before an item enters a trade slot
// (TradeHandler.cpp, HandleSetTradeItemOpcode), so the refusal is the server's,
// whatever the client sends. Pure, so the test compiles this very header.
// Returns the line the player reads; there is no item this rule lets through.
namespace DC::Trade
{
constexpr char const* ItemRefusal()
{
    return "Items are account bound and cannot be traded. Gold only.";
}
}

#endif // DC_TRADE_RULE_H
