#!/usr/bin/env python3
"""The login-screen strings in client-patch GlueStrings.lua send nobody to a Blizzard host.

  * the strings the client fetches on its own at startup or login are blank, so it fetches nothing: the server alert
    (the `serverAlert` cvar's default tag), the agreements archive, the Scan.dll version file and DLL, and the four
    account-messaging endpoints, whose query carries the account name and a session-key hash. A blank URL fails
    InternetCrackUrlA, the download returns false and the client marks it done (wowdecomp OsURLDownload.cpp,
    CGlueMgr.cpp RequestLatestAgreements and the server alert, ScanDLLGlue.cpp ScanDLLStart);
  * account creation, realm status and the account point at the website;
  * the banned, suspended, busy and expired texts, and the URL each login-error dialog opens, name no Blizzard address.
"""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
GLUE = ROOT / "client-patch/art/Interface/GlueXML/GlueStrings.lua"
SITE = "https://example.com"
BLIZZARD = re.compile(r"worldofwarcraft|blizzard|battle\.net|wow-europe", re.I)

FETCHED_UNASKED = [
    "SERVER_ALERT_URL", "LATEST_AGREEMENTS_URL", "SCANDLL_URL_LAUNCHER_TXT", "SCANDLL_URL_WIN32_SCAN_DLL",
    "ACCOUNT_MESSAGE_BODY_NO_READ_URL", "ACCOUNT_MESSAGE_BODY_URL", "ACCOUNT_MESSAGE_HEADERS_URL",
    "ACCOUNT_MESSAGE_READ_URL",
]
WEBSITE = {
    "ACCOUNT_CREATE_URL": SITE + "/account/register",
    "AUTH_DB_BUSY_URL": SITE + "/",
    "AUTH_NO_TIME_URL": SITE + "/account",
    "AUTH_BANNED_URL": SITE + "/rules",
    "AUTH_SUSPENDED_URL": SITE + "/rules",
}
TEXTS = [
    "AUTH_BANNED", "AUTH_SUSPENDED", "AUTH_DB_BUSY", "AUTH_NO_TIME",
    "LOGIN_BANNED", "LOGIN_SUSPENDED", "LOGIN_DBBUSY", "LOGIN_AUTH_OUTAGE", "LOGIN_EXPIRED", "LOGIN_NOTIME",
    "LOGIN_TRIAL_EXPIRED", "REALM_LIST_REALM_NOT_FOUND",
]


def glue_strings(text):
    return {m.group(1): m.group(2) for m in re.finditer(r'^([A-Z0-9_]+) = "((?:[^"\\]|\\.)*)";\s*$', text, re.M)}


def login_error_url_tags(text):
    """The <code, "X_URL"> pairs CGlueMgr's s_loginErrorURLs opens from the OKAY_WITH_URL dialog."""
    return re.findall(r'\{\s*AUTH_[A-Z_]+,\s*"([A-Z_]+_URL)"\s*\}', text)


class GlueUrls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = GLUE.read_text(encoding="utf-8")
        cls.strings = glue_strings(cls.text)

    def test_every_named_string_is_in_the_file(self):
        for name in FETCHED_UNASKED + list(WEBSITE) + TEXTS:
            self.assertIn(name, self.strings, name)

    def test_strings_fetched_unasked_are_blank(self):
        for name in FETCHED_UNASKED:
            self.assertEqual(self.strings[name], "", name)

    def test_account_and_status_links_go_to_the_website(self):
        for name, url in WEBSITE.items():
            self.assertEqual(self.strings[name], url, name)

    def test_banned_busy_and_expired_texts_name_no_blizzard_address(self):
        for name in TEXTS:
            self.assertIsNone(BLIZZARD.search(self.strings[name]), name)
            self.assertNotIn("World of Warcraft", self.strings[name], name)

    def test_every_login_error_dialog_url_is_on_the_website(self):
        decomp = Path.home() / "diablocraft/reference/wowdecomp/WoW/Source/Glue/CGlueMgr.cpp"
        if not decomp.is_file():
            self.skipTest("reference/wowdecomp is not here")
        tags = login_error_url_tags(decomp.read_text(encoding="utf-8", errors="replace"))
        self.assertIn("AUTH_BANNED_URL", tags)
        for tag in tags:
            if tag == "AUTH_PARENTAL_CONTROL_URL":
                continue  # parental control is a retail account feature; the auth server never sends it
            self.assertTrue(self.strings[tag].startswith(SITE), tag)

    def test_the_file_still_parses_as_lua(self):
        luac = shutil.which("luac5.1") or shutil.which("luac")
        if not luac:
            self.skipTest("no luac")
        out = subprocess.run([luac, "-p", str(GLUE)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)


if __name__ == "__main__":
    unittest.main()
