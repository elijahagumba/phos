"""A tiny, hand-built CERT-shaped release, with answers computed by hand in the tests.

Every column name, activity word and separator here was copied from a real Release 3.1 file — the
email log deliberately has no ``user`` or ``pc`` column, because the real one does not. A fixture
that matched the *published schema* rather than the actual file would let a reader that cannot read
CERT pass its whole test suite.

The cast is three users:

* ``ALICE001`` — ordinary: in-hours logons, an internal email, an intranet host.
* ``MALLORY9`` — the insider: two off-hours logons on two machines, a thumb drive, wikileaks and
  dropbox, three file copies of two distinct files, and one email to a personal address.
* ``outsider@elsewhere.com`` — not an employee, sends one message *in*, and must be skipped.

Monday 4 January 2010 and Tuesday 5 January 2010 were chosen so that a weekday/weekend mistake in
`WorkingHours` cannot pass unnoticed.
"""

from pathlib import Path

import pytest

LOGON_CSV = """id,date,user,pc,activity
{L1},01/04/2010 09:00:00,ALICE001,PC-1,Logon
{L2},01/04/2010 22:30:00,MALLORY9,PC-2,Logon
{L3},01/04/2010 23:00:00,MALLORY9,PC-9,Logon
{L4},01/05/2010 09:15:00,ALICE001,PC-1,Logon
{L5},01/05/2010 17:00:00,ALICE001,PC-1,Logoff
"""

DEVICE_CSV = """id,date,user,pc,activity
{D1},01/04/2010 22:35:00,MALLORY9,PC-2,Connect
{D2},01/04/2010 22:50:00,MALLORY9,PC-2,Disconnect
{D3},01/05/2010 10:00:00,ALICE001,PC-1,Connect
"""

HTTP_CSV = """id,date,user,pc,url,content
{H1},01/04/2010 22:40:00,MALLORY9,PC-2,http://wikileaks.org/leak,some words
{H2},01/04/2010 22:41:00,MALLORY9,PC-2,http://WWW.Dropbox.com/upload,some words
{H3},01/05/2010 09:20:00,ALICE001,PC-1,http://intranet.dtaa.com/home,some words
"""

# No `user` column and no `pc` column: r3.1's email log identifies its actor by `from` alone.
EMAIL_CSV = """id,date,to,from,size,attachments,content
{E1},01/04/2010 22:45:00,friend@gmail.com;bob@dtaa.com,mallory.m.nine@dtaa.com,100,0,words
{E2},01/05/2010 09:30:00,bob@dtaa.com,alice.a.one@dtaa.com,100,0,words
{E3},01/05/2010 09:31:00,alice.a.one@dtaa.com,outsider@elsewhere.com,100,0,words
"""

FILE_CSV = """id,date,user,pc,filename,content
{F1},01/04/2010 22:46:00,MALLORY9,PC-2,secret.doc,D0-CF words
{F2},01/04/2010 22:47:00,MALLORY9,PC-2,secret.doc,D0-CF words
{F3},01/04/2010 22:48:00,MALLORY9,PC-2,other.doc,D0-CF words
"""

LDAP_CSV = (
    "employee_name,user_id,email,role,business_unit,functional_unit,"
    "department,team,supervisor\n"
    "Alice A One,ALICE001,alice.a.one@dtaa.com,Salesman,1,2 - Sales,"
    "3 - Retail,Team A,Boss Person\n"
    "Mallory M Nine,MALLORY9,mallory.m.nine@dtaa.com,ITAdmin,1,1 - IT,"
    "1 - Ops,,Boss Person\n"
)

INSIDERS_CSV = """dataset,scenario,details,user,start,end
2,1,r2.csv,SOMEONE1,3/6/2010 1:41:56,3/20/2010 8:10:12
3.1,1,r3.1-1.csv,MALLORY9,01/04/2010 22:30:00,01/04/2010 23:59:59
"""


@pytest.fixture
def release_dir(tmp_path: Path) -> Path:
    """Write a complete CERT-shaped release and return its directory."""
    root = tmp_path / "r3.1"
    root.mkdir()
    for name, body in (
        ("logon.csv", LOGON_CSV),
        ("device.csv", DEVICE_CSV),
        ("http.csv", HTTP_CSV),
        ("email.csv", EMAIL_CSV),
        ("file.csv", FILE_CSV),
    ):
        (root / name).write_text(body, encoding="utf-8")
    ldap = root / "LDAP"
    ldap.mkdir()
    (ldap / "2010-01.csv").write_text(LDAP_CSV, encoding="utf-8")
    return root


@pytest.fixture
def answers_dir(tmp_path: Path) -> Path:
    """Write a CERT-shaped ``answers`` directory and return it."""
    answers = tmp_path / "answers"
    answers.mkdir()
    (answers / "insiders.csv").write_text(INSIDERS_CSV, encoding="utf-8")
    return answers
