-- luacheck: globals INT_SPELL_DURATION_SEC INT_SPELL_DURATION_MIN INT_SPELL_DURATION_HOURS INT_SPELL_DURATION_DAYS SPELL_DURATION_SEC SPELL_DURATION_MIN SPELL_RECAST_TIME_SEC SPELL_RECAST_TIME_MIN
-- Torment tooltip units: the words "seconds" and "minutes", never "sec" and
-- "min".
--
-- The client formats a spell's duration and cooldown itself and reads these
-- globals when it does. The route is proved in game:
-- `/run INT_SPELL_DURATION_MIN = "%d minutes"` made War Cry's `$d` read
-- "2 minutes" in the same session. One key on one path was proved; the rest are
-- the same family but each is its own check.
--
-- Every value below is the stock string from the 3.3.5 FrameXML
-- GlobalStrings.lua with only the unit word changed, so each format specifier
-- is exactly the stock one. The `|4second:seconds;` / `|4minute:minutes;` forms
-- are the client's own plural choice (the stock HOURS and DAYS keys already use
-- `|4` with `%d`), so a one-second value reads "1 second", not "1 seconds".
-- The `|4` plural form is used only on the four `%d` keys; the `%.2f` and
-- `%.3g` keys keep the plain "seconds"/"minutes" wording (a
-- format specifier does not say the value can never be 1; `%.3g` can print 1).
--
-- Verified against wowgaming/3.3.5-interface-files at
-- d0339b17b0221db76e6acd2dc2915d224a5b62ca,
-- `pm-ui-audit-framexml-stock/GlobalStrings.lua`: INT_SPELL_DURATION_SEC:4291
-- ("%d sec"), INT_SPELL_DURATION_MIN:4290 ("%d min"),
-- INT_SPELL_DURATION_HOURS:4289 ("%d |4hour:hrs;"),
-- INT_SPELL_DURATION_DAYS:4288 ("%d |4day:days;"), SPELL_DURATION_SEC:6936
-- ("%.2f sec"), SPELL_DURATION_MIN:6935 ("%.2f min"),
-- SPELL_RECAST_TIME_SEC:7241 ("%.3g sec cooldown"), SPELL_RECAST_TIME_MIN:7240
-- ("%.3g min cooldown").
--
-- SPELL_DURATION ("Lasts %s") and SPELL_RECAST_TIME_INSTANT ("Instant
-- cooldown") are deliberately left stock.
--
-- This only reaches the lines the client formats. A literal word in our own D3
-- sentence, e.g. "for $<duration_seconds> seconds", is our text and is not
-- affected: the `$<name>` variable renders a bare number, so those sentences
-- are unchanged by this file.
INT_SPELL_DURATION_SEC = "%d |4second:seconds;"
INT_SPELL_DURATION_MIN = "%d |4minute:minutes;"
INT_SPELL_DURATION_HOURS = "%d |4hour:hours;"
INT_SPELL_DURATION_DAYS = "%d |4day:days;"
SPELL_DURATION_SEC = "%.2f seconds"
SPELL_DURATION_MIN = "%.2f minutes"
SPELL_RECAST_TIME_SEC = "%.3g seconds cooldown"
SPELL_RECAST_TIME_MIN = "%.3g minutes cooldown"
