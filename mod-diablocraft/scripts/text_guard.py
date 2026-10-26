"""The one refusal for text a generator fills (diablocraft-unfilled-tokens, GitHub #87).

A template token the fill step missed prints to every player verbatim. Every
generator that fills player-facing text calls refuse_unfilled on the filled
result, so the pattern and the message live here and nowhere else. The error
names the token and the source row.
"""
import re

# Every token a player must never see: printf (%d %.1f %s), WoW ($s1 $d), {braces}, [Name].
UNFILLED_TOKEN = re.compile(r"%[0-9.]*[dfsu](?![A-Za-z])|\$[A-Za-z0-9]|\{[^}]*\}|\[[A-Za-z_]+\]")
# Spell descriptions are WoW text: $s1, $d, $o1 and ${$x1-1} are the client's own tokens there, filled at draw time.
UNFILLED_TOKEN_WOW = re.compile(r"%[0-9.]*[dfsu](?![A-Za-z])|(?<!\$)\{[^}]*\}|\[[A-Za-z_]+\]")


class UnfilledToken(ValueError):
    """Filled text still carries a template token."""


def find_unfilled(*texts, pattern=UNFILLED_TOKEN):
    """The first unfilled token in any of the texts, or None."""
    for text in texts:
        found = pattern.search(text)
        if found:
            return found[0]
    return None


def refuse_unfilled(source, *texts, pattern=UNFILLED_TOKEN):
    """Raise UnfilledToken, naming the token and `source`, when a text carries one."""
    token = find_unfilled(*texts, pattern=pattern)
    if token is not None:
        shown = " | ".join(repr(text) for text in texts)
        raise UnfilledToken(f"Unfilled token {token!r} in {source}: {shown}")
