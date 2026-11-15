# ADR 0348 — S7comm dissection is judged

- **Status:** Accepted
- **Date:** 2026-11-06
- **PART:** Build brief G, S7comm lane
- **Supersedes:** nothing
- **Depends on:** [ADR 0344](0344-industrial-protocol-coverage-is-declared.md),
  [ADR 0347](0347-s7comm-dissection-is-declared.md),
  [ADR 0422](0422-build-brief-g-is-unparked-against-the-refusal-register.md)
- **Judged (fifth take, after five red-team rounds):** `src/phos/atlas/packet/s7comm.py` sha256
  `6afddec3254234f8043948db8509a87c2e4659242c1bb9a7ba30809fa1eabf77`,
  `tests/atlas/packet/test_s7comm.py` sha256
  `2e2fc99128531476a80762803f99bbeb7f338a97a9151d6828ca8d31632d1d26`,
  `tests/atlas/packet/test_s7comm_hardening.py` sha256
  `3bd975a04ef226200092dcca2708417c533b30aab74c19edb4b814ed2228a9f1` (unchanged since take 3),
  `tests/atlas/packet/test_s7comm_adversarial.py` sha256
  `efdcdf28d93bd4b5fa404d79190d8e87fc60268162b9289e4ce59a663c2d6b94`,
  against ADR 0347 as committed at `fdaaab9`
- **Superseded judgements:** take 1 against `s7comm.py` sha256 `6dd04cd8…04b5` / `test_s7comm.py`
  `76332f67…921b`; take 2 against `a8dba0c9…ba56`; take 3 against `2c38ed08…d5325`. None of those
  verdicts is inherited by this one; each is re-taken against the bytes it names (see "Re-judgement
  after an escalated defect", "Third take, after two red-team rounds", and "Fifth take, and the
  five-round record").

## Context

ADR 0347 declared the S7comm lane of build brief G and was committed at
`fdaaab9`, before a line of the module existed: that commit's stat is
`docs/adr/0347-...md | 217 ++++` and `eval_runs/build/lane-g/s7comm/spec-audit.md |
132 +++`, and there is no `.py` in it. The three files this record judges are
still untracked on `build/g-s7comm` (`git status --porcelain` reports
`?? src/phos/atlas/packet/s7comm.py`, `?? tests/.../test_s7comm.py`,
`?? tests/.../test_s7comm_hardening.py`), and no tracked file is modified
(`git diff --stat HEAD` is empty — `modbus.py`, `test_dissect.py` and
`test_hardening.py` are untouched).

The lane's claim is deliberately narrow and is the claim being judged: the
module decodes **TPKT** (RFC 1006 §6) and **COTP** (RFC 905 §13) and reports
`iso-tsap`, the IANA service on port 102. It does not decode an S7 application
message, and no `ProgramAct` is constructible from it.

**I did not build this code.** I was given ADR 0347's done list and refusal list
as the bar, a spec-audit I did not write, and the engineer's own report of two
decisions. Nothing in this record is a restatement of the declaration's
intent — every done-list item below is answered by a test I read or by a
command I ran, and the probes in the adversarial section are inputs I
constructed, not the engineer's.

## Decision

**The verdict is met.** All fifteen done-list items hold, all six refusals hold, the four
spec-audit defects are honoured, every fixed-part floor and both exact-value rules are right on the
RFC (re-derived by me from primary text, never inherited), and **the ED residual I recorded at
take 3 is now closed** — its length indicator is pinned to exactly 3 and its count is derived from
the verified TPKT length, so no named TPDU in this module any longer hands a caller a user-data
count the sender steered. The last finding the red team made in this lane (a DR or ER with a
one-octet variable part) was real, is closed, and is closed **generically** rather than by a
per-code special case.

Every defect this lane produced was a case the bar already excluded, not one the declaration
licensed. Nothing in ADR 0347 permitted a steerable count or a named TPDU decoded with an
unenforced fixed part; the bar was right and the implementation lagged it, five times.

## Fifth take, and the five-round record

**What changed since take 3.** Three edits, all verified by me against the current bytes:

1. **ED is an exact value, not a floor.** `_ED_LENGTH_INDICATOR = 3` (`:271`) and a DT-style exact
   branch in `_fixed_part_refusal` (`:758-766`); `_user_data_length` gains an ED branch
   (`:879-880`) returning `tpkt_length − 4 − _ED_HEADER_OCTETS`, where `_ED_HEADER_OCTETS = 4`
   (`:253`) because RFC 1006's expedited format has a credit octet the DT does not.
2. **The 16-octet XSDU cap**, enforced in `dissect` at `:590-597` as `FIELD_OUT_OF_RANGE`, guarded on
   `cotp_code == TpduCode.EXPEDITED_DATA` so it cannot touch a DT.
3. **The dangling-variable-part rule** (`:776-783`, constant `_DANGLING_VARIABLE_PART_OCTETS = 1` at
   `:333`): when a TPDU's fixed-part minimum is known, `length_indicator − minimum == 1` is refused,
   because a variable part must hold at least one two-octet parameter.
4. Lint/format only: the E501 and D415 the red team reported at `s7comm.py:338` and
   `test_s7comm.py:598` are gone and both files are clean under `ruff check` and
   `ruff format --check`. I checked the character counts myself (94 and 99 characters respectively,
   the longest line in the module being 100) — the earlier 101/104 readings were byte counts against
   multi-byte `§` and `—`, not real overflows.

### Rule 1 — ED at exactly LI 3: **right**, and the arithmetic is right too

RFC 1006 §6, fetched, gives the expedited TPDU as

```
| header length | code | credit |TPDU-NR and EOT|   user data   |
```

and says it is "nearly identical to the format for the normal data, DT, TPDU. The only difference is
that the value used for the TPDU's code is ED, not DT". There is no variable-part column. Under
RFC 905 §13.2.1 — LI is "the header length in octets including parameters, but excluding the length
indicator field and user data" — the header is code + credit + TPDU-NR/EOT = **3**. So 3 is exact,
not a floor. That matches spec-audit D4, which recorded LI = 3 for RFC 1006's ED and warned that
X.224's class-1 ED (LI 4, with DST-REF) is a *different* shape.

**The user-data arithmetic checks out.** The ED header from the length indicator onward is four
octets — LI, code, credit, TPDU-NR/EOT — not three, so the count is `tpkt_length − 4 − 4`. I verified
this exhaustively rather than by reading it: for every n in 0…16, an ED carrying n application
octets reports exactly `udl = n`. An off-by-one here would have been silent, and it is the specific
error the `_ED_HEADER_OCTETS` docstring names.

**The take-3 defect is closed, demonstrated on the same experiment.** The take-3 failure was that
identical wire octets reported 6, 5, 4, 1 as the length indicator varied. Re-run against these bytes:

```
ED LI 3, identical 11-octet COTP -> udl=7
ED LI 4, identical 11-octet COTP -> refused/INCONSISTENT_COUNT
ED LI 5, identical 11-octet COTP -> refused/INCONSISTENT_COUNT
ED LI 8, identical 11-octet COTP -> refused/INCONSISTENT_COUNT
```

I also swept **all 255 length indicators** for ED and the accepted set is exactly `[3]`.

### Rule 2 — the XSDU cap: **right reason, correctly scoped**

`FIELD_OUT_OF_RANGE` is the right member of the existing vocabulary: the `MalformedReason` docstring
defines it as "a count or quantity exceeded the protocol's stated limit", and 16 is a stated limit
rather than a malformed header field or a buffer disagreement. The detail string names the number,
the clause, and that the limit is expedited-only, so a reader cannot mistake a lawful 5,000-octet DT
for an illegal one.

**Scope verified both ways.** The guard is on `cotp_code == TpduCode.EXPEDITED_DATA` and nothing
else. My probe set:

| Case | Result |
|---|---|
| ED, 16 application octets | decodes, `udl=16` |
| ED, 17 | `FIELD_OUT_OF_RANGE` |
| ED, 5,000 | `FIELD_OUT_OF_RANGE` |
| DT, 16 / 17 / 100 / 5,000 / **65,528** | all decode, `udl` exact — the cap does not touch a DT |
| CR/CC/DR/ER with 100 trailing octets | all decode — no other TPDU carries an XSDU |

The cap's source is sound: RFC 1006 §6 says "the TP specification limits the size of an expedited
transport service data unit (XSDU) to 16 octets", and RFC 905 §13.8.5 says the field "contains an
expedited TSDU (1 to 16 octets)". Note the lower bound in that clause is **1**, and the module
accepts 0 — see finding 8.

### Rule 3 — the dangling one-octet variable part: **RFC 905 §13.2.3 is decisive**

The clause, fetched: "The variable part is used to define less frequently used parameters. **If the
variable part is present, it shall contain one or more parameters.**" Its NOTE fixes the variable
part's length as "LI minus the length of the fixed part". A parameter is `[code][length][value…]`,
so the shortest parameter is **two** octets. Therefore a variable part of **exactly one octet**
declares a parameter field that cannot exist. Two octets is one parameter with a zero-length value;
three is one with a one-octet value. **Exactly one is the only impossible length**, which is exactly
what the rule refuses and nothing more. I confirmed both directions:

| Case | Result |
|---|---|
| DR LI 6 (no variable part) | decodes |
| DR LI 7 (1-octet variable part) | `INCONSISTENT_COUNT`, detail cites §13.2.3 |
| DR LI 8 (2-octet variable part) | decodes |
| ER LI 4 / LI 5 / LI 6 / LI 8 | decode / refuse / decode / decode |

**Is the rule actually generic?** Yes, and I verified the mechanism rather than the claim. It is
guarded on `_fixed_part_minimum(cotp_code) is not None` and keyed on
`length_indicator − minimum == 1`, and `_fixed_part_minimum` resolves **CR and CC by high nibble**
(`:703-707`). So CR and CC reach the same guard without being named in it, and any **seventh** TPDU
added to `_FIXED_PART_MINIMUMS` inherits it automatically. Probes:

| Case | Result |
|---|---|
| CR LI 7 (1-octet variable part) | `INCONSISTENT_COUNT` |
| CR LI 8 (`0xC0` zero-length parameter) | decodes |
| CC LI 7 / CC LI 8 | refuse / decode |
| all 32 CR/CC octets at LI 6 | all decode |

DT and ED are correctly **unaffected**, because their branches return before the minimum lookup is
reached — so a DT at LI 3 refuses with the §13.7.1 a reason and an ED at LI 4 with the RFC 1006 §6
reason, neither mentioning §13.2.3. The red team checked this on the detail strings; I confirmed it
by reading the branch order at `:748-766` (both `return None` before `_fixed_part_minimum` is called
at `:768`).

### Nothing lawful is newly refused — the over-correction check

This lane's defects have all been over-permissiveness, so the risk of these three fixes is
over-correction. Every case the brief named, tested by me:

| Probe | Result |
|---|---|
| CR LI 6 + **5,000** octets of initial user data | decodes, `udl=5000` |
| CR with both TSAPs + a third `0xC0` parameter | decodes, both TSAPs read |
| CR third parameter + 100 user octets | decodes, `udl=100` |
| CC LI 6 class 4 | decodes, `cotp_class=4` |
| CC LI 6 class 4 + 20 user octets | decodes, `udl=20` |
| ED LI 3 with 0 / 16 user octets | decodes, `udl=0` / `udl=16` |
| DT LI 2 with 5,000 user octets | decodes, `udl=5000` |
| `0300000702f000` | decodes, `data`, `udl=0` |
| reserved `0x00` / `0x7F` / `0xFF` | all decode, value recorded |
| CR/CC at LI 6, credit `0x0` / `0x7` / `0xF` | all decode |
| CR at exactly 128 octets (LI 127 + 119-octet TSAP) | decodes; at 129, `FIELD_OUT_OF_RANGE` |

**Done-list item 10 survives all three fixes**, which was the item most at risk: the CR/CC floor and
the new dangling rule both bound the header, and RFC 1006 §5's initial user data lies past it. The
red team's five guards (`test_s7comm_adversarial.py:1204-1245`) and its
`TestTheVariablePartRuleIsGeneric` (`:1863`) and `TestTheExpeditedDataShape` (`:1632`) assert the
same, and all pass.

### Gates, run by me against `6afddec3…bf77`

```
uv run pytest tests/atlas/packet/ -q
    → 1120 passed, 3 skipped in 16.18s

uv run mypy --strict src
    → Success: no issues found in 295 source files

uv run ruff check
    → All checks passed!

uv run ruff format --check
    → 735 files already formatted
```

Plus, for the two suites this lane added: `test_s7comm_adversarial.py` → **479 passed, 3 skipped**;
`test_s7comm_hardening.py` → **85 passed**; `TestTheDoneList` → **18 passed**. The 3 skips are
`test_s7comm_adversarial.py:342`, "does not fit a length indicator" — a parametrisation whose value
cannot be expressed in a 254-maximum field, not a disabled assertion. Coverage **99%** (227
statements, 72 branches, two missed lines `:532` and `:913`, both discussed under findings).

**On the red team's reported lint failures.** Its round-5 report says
`ruff check` over the repository failed with E501 at `s7comm.py:338` and D415 plus a format diff in
`test_s7comm.py`, and that those files were outside its scope. Both are now clean at the bytes I
judged, so the engineer did the cleanup. I verified the cleanup was formatting-only rather than
suppressing the rule: the E501 was a 101-character docstring line that is now 94 characters (it was
byte-counted above 100 by tools that treat `§` as multi-byte), and the D415 was a class docstring
first line that now ends with a full stop. No `# noqa` and no per-file ignore was added for either.

### Item 13 — the declared seed corpus is provably intact

`test_s7comm_hardening.py` is **byte-identical to take 3** (sha256 `3bd975a0…a9f1`, unchanged), so the
declared corpus cannot have been weakened by these fixes: seed `20261105`, `RANDOM_INPUTS = 2000`,
`MUTATED_INPUTS = 2000`, the four claims still each a named test at `:216`, `:229`, `:282`, `:420`,
and `assert_contained` unchanged. The adversarial file grew (`990001`, its own seed) but that is
additive. This is the strongest possible answer to "did the fixes change fixtures in a way that
weakened the corpus": the file did not change at all.

### What five rounds against a "met" module means

This is the fact the record has to carry, and I will not soften it. **The S7comm lane took five
red-team rounds and five judgement takes to reach a stable verdict, and four of the five rounds
found a real defect in a module I had already pronounced met.** Round 1 found D1 and D2 (named TPDUs
at any LI; a DT whose count the sender chose). Round 2 found the CR/CC asymmetry — the same D1 shape
surviving on the two TPDUs the first fix had argued out of the floor. Round 3 found nothing but
wrongly claimed the family exhausted. Round 4 found the ED exact value, which *I* had missed and
recorded as a residual, plus a one-octet variable part on DR and ER. Round 5 found nothing.

**What that says about the verdict.** It does not say the verdict is unreliable. It says the first
three verdicts were, and the reason is specific rather than general: each of them tested *the
categories the declaration named* rather than sweeping the axes those categories range over. Take 1
checked DT thoroughly because item 7 named DT; it did not sweep LI against the other six codes.
Take 3 swept 256 codes × 254 LIs and declared the D1 family exhausted — a true statement about fixed
part **minimums**, and false as a statement about the family, because the same defect also lives on
the *exact-value* axis that a minimum-shaped sweep cannot see. The judge's own habit was the
weakness: reading the bar, building the cases the bar names, and calling the shape covered.

**What it says about the loop.** The loop worked, and the evidence for that is structural rather
than sentimental. The judge, the red team and the engineer were three separate parties who did not
edit each other's files: the red team wrote only its report and its own test file, I wrote only this
ADR, and neither of us touched the dissector. The rounds that found defects found them by sweeping
input spaces (`256 × 256`, `256 × 254`, 300,000-case differential fuzzing) that no reading of a doc
list would have produced. Every one of the five findings arrived because a party whose job was
*breaking* the module had no incentive to agree that the last fix was sufficient. A single agent
asked to build, judge and re-judge this lane in one context would very likely have stopped at take
1, and take 1 was wrong in two independent ways.

**What it does not say.** It is not a reason to distrust this verdict, and the distinction is
falsifiable rather than rhetorical: the last four takes each re-took the judgement against new bytes
and each recorded the specific evidence, so the accumulation is traceable in this document. The
fifth take's claims are checkable by the same means as the first — the sha256 is pinned, the probes
are described, and the two exact-value rules are now sweep-verified over the whole 256 × 256 space
rather than sampled. What has changed is that the *method* is now the right one: every named TPDU is
pinned to a measured least-and-greatest decodable LI (see finding 9), which is the test that would
have caught rounds 1 through 4 on day one.

**The honest summary**: this lane needed five rounds because the first three verdicts were too
narrow, not because the module was unusually bad or the bar unusually weak. Both of those would be
more comfortable explanations than the true one, which is that a judge who tests only what a
declaration enumerates will keep missing a defect class that ranges over an axis the enumeration
crosses.

## Third take, after two red-team rounds

**What the red team found, and whether the bar permitted it.** This is the question the record has
to answer plainly, because a lane whose defects were *licensed* by its declaration has a weak
declaration, and that is a different verdict from a lane whose defects slipped past a bar that
already excluded them.

| Finding | Round | Was it a case the bar permitted? |
|---|---|---|
| **D2** — `user_data_length` derived from the attacker-chosen length indicator, so 22 octets of S7 job could be reported as `udl=0` | 2 | **No.** Done-list item 7 already refuses an LI that claims more header than is present, and this was that same lie *inside* the declared header. The module's own docstring said the application octets are "counted … not decoded", and a count the sender chooses is not a count. The bar excluded it; the code did not implement it. |
| **D1** — DR/ER/ED (and then CR/CC) decoded as named messages with their fixed parts unenforced, the missing octets counted as user data | 1–2 | **No.** Done-list item 15 requires every decoded message to trace to the frame it came from; reporting fields that were never sent inverts that. Item 7's `INCONSISTENT_COUNT` for a DT with LI below the class-0 fixed part is the same rule for one code; the bar's shape covered the family even though its wording named only DT. |
| **CR/CC floor** — the first fix argued CR and CC out of the floor, and the D1 shape survived there | 2 | **No.** It was the same defect in the one place the argument had been made, and the argument was wrong for a reason the audit had already supplied: RFC 1006's initial-data permission lengthens a TPDU past its header, it never shortens the header. |

So the declaration was **not** too weak. Its bar excluded all three; the implementation did not
meet it, my first two takes missed it, and an adversarial lane found it. The honest reading is that
the judge under-tested rather than that the bar was permissive, and that is worth recording against
me rather than against ADR 0347.

**What changed.** Three edits, all in `_fixed_part_refusal` / `_fixed_part_minimum` plus the
`user_data_length` helper: a DT must declare LI exactly 2 and its count is derived from the verified
TPKT length; DR, ER and ED gain floors of 6, 4 and 3; CR and CC gain a floor of 6 resolved **by
nibble**, because a CR's low nibble is the credit field (RFC 905 §13.2.2.2) and `0xE7` is as much a
CR as `0xE0`. The dead `cotp_class` branch I escalated at take 2 is gone; `cotp_class` is still
recorded from `_preferred_class` (`:527`) and still assigned to the message (`:560`).

### Every floor re-derived from primary text, not from the brief's arithmetic

The brief warned that it had DR wrong once (5 instead of 6) and told me not to inherit its
numbers. I re-derived all six from the clauses. **All six are right.** The load-bearing fact is
RFC 905 §13.2.1, which all six depend on:

> The length indicated shall be the header length in octets including parameters, but excluding the
> length indicator field and user data, if any.

So LI counts **the code octet** plus everything after it up to the variable part. That is exactly
why DR is 6 and not the 5 the field list suggests.

| Floor | Value | My derivation from the clause | Verdict |
|---|---|---|---|
| **DT** | exactly **2** | §13.7.1 a) prints the normal format for classes 0 and 1 as `LI │ DT │ TPDU-NR and EOT │ User Data` — octets 2 and 3, **no variable part**. §13.2.1 excludes LI and user data, so the header is the code plus octet 3 = 2. An LI above 2 declares a variable part the format does not have; §13.2.2.1 makes that a protocol error. | **Right, and exact rather than a floor** |
| **DR** | **6** | §13.5.1 prints `LI │ DR │ DST-REF │ SRC-REF │ REASON │ VARIABLE │ USER DATA`, with REASON in octet 7. §13.5.3 is headed "Fixed Part (Octets 2 to 7)". Excluding LI, that is 6. | **Right** |
| **ER** | **4** | §13.12.1 prints `LI │ ER │ DST-REF │ Reject Cause │ Variable Part`; §13.12.3 lists ER, DST-REF (2) and REJECT CAUSE. Code + 2 + 1 = 4. | **Right** |
| **ED** | **3** | RFC 1006 §6 prints the expedited TPDU as `header length │ code │ credit │ TPDU-NR and EOT │ user data` and says it is "nearly identical to the format for the normal data, DT, TPDU. The only difference is that the value used for the TPDU's code is ED, not DT." Code + credit + TPDU-NR/EOT = 3. (X.224's class-1 ED is a *different* shape with DST-REF, LI 4 — spec-audit D4 — and RFC 1006 governs this port.) | **Right as a minimum; see finding 6** |
| **CR** | **6** | §13.3.1 prints octets 2–7 as `CR CDT │ DST-REF │ SRC-REF │ CLASS OPTION`; §13.3.3 is headed "Fixed Part (Octets 2 to 7)". Code + 2 + 2 + 1 = 6. | **Right** |
| **CC** | **6** | §13.4.1 prints octets 2–7 as `CC CDT │ DST-REF │ SRC-REF │ CLASS OPTION`; §13.4.3 is headed "Fixed Part (Octets 2 to 7)". | **Right** |

The brief's DR story checks out: **6 is correct and 5 is wrong**, for exactly the reason given —
§13.2.1 puts the code octet inside the length LI measures. I checked the one place RFC 905 is
self-inconsistent: Table 8 prints the DR code as `1000 0000`, while the §13.5.1 diagram prints
`1000 0001`. The module names `0x80` and `0x81` as `unknown(129)`, which is the safe reading (Table
8 is normative and the diagram is a typo), and it means a `0x81` DR is decoded as an unnamed code
with no floor rather than being refused — see finding 7.

### The floors verified by sweep, not by reading

I ran my **own** 256-code × 254-LI sweep, building each TPDU so its declared header really is as
long as its LI claims — the only thing that can justify a refusal is then the floor:

```
connection_confirm   least decodable LI 6  my RFC floor 6  OK
connection_request   least decodable LI 6  my RFC floor 6  OK
data                 least decodable LI 2  my RFC floor 2  OK
disconnect_request   least decodable LI 6  my RFC floor 6  OK
error                least decodable LI 4  my RFC floor 4  OK
expedited_data       least decodable LI 3  my RFC floor 3  OK
named decodes below their own fixed part: 0
```

Every named type decodes at exactly its floor and not one octet below. That independently confirms
the red team's claim for the six named codes, which is what I was asked to verify.

### Done-list item 10 survived the CR/CC floor — checked because it is the one that could break

This was the item at risk: a floor on a connection TPDU could have swallowed RFC 1006 §5's initial
user data. **It did not.** The floor bounds the *header*; initial user data lives past it.

| Probe | Result |
|---|---|
| CR at LI 6 with **5,000** octets of initial user data | decodes, `connection_request`, `udl=5000` |
| CR at LI 6 with 1 octet, and with 0 octets | decodes, `udl=1` / `udl=0` |
| CR with both TSAPs **and a third parameter** (0xC0) | decodes, `calling_tsap=b"\x01\x00"`, `called_tsap=b"\x01\x02"` |
| CR with a third parameter **and** 100 octets of user data | decodes, `udl=100`, `calling_tsap` intact |
| CC at LI 6 with class 4 **and 20 octets of user data** | decodes, `cotp_class=4`, `udl=20` |
| CR/CC at LI 6, every credit value `0x0`–`0xF` | all 32 octets decode |
| CR/CC at LI 5, same octets | all 32 refuse `INCONSISTENT_COUNT` |

The red team's own guards (`test_initial_user_data_at_the_floor_still_decodes_and_is_counted` at
`test_s7comm_adversarial.py:1204`, `test_a_third_parameter_at_the_floor_still_decodes` at `:1218`,
`test_both_together_initial_user_data_after_a_third_parameter` at `:1229`,
`test_a_connection_confirm_at_the_floor_carrying_user_data_decodes` at `:1239`) assert the same
thing, and they pass. **Item 10 holds.** Refusal-list item 2 also survives: a CR carrying class 4
still decodes with `cotp_class=4`, because the class octet is recorded and never a refusal reason.

### Does the LI == 2 rule refuse a lawful frame? The class-4 DT question

**Yes, it refuses every class-4 DT, and that is correct for this port.** RFC 1006 §6, fetched:
"Note that only TPDUs formatted for transport class 0 are exchanged (different transport classes may
use slightly different formats)." A class-4 DT's fixed part per §13.7.1 b) is DST-REF plus TPDU-NR
and EOT, so its LI can never be 2 — it is refused by the same rule that refuses any other wrong LI,
not by a class check. That is the honest outcome, and the module says so in its own words at
`:71-88` rather than claiming a decode it cannot perform: "refusing it is the honest answer rather
than a guess at its layout", and "That is the shape of a class-4 estate on this port: setup visible,
data refused." I verified the refusal text names the LI, not a class, so nothing in the message
claims the module inspected a class it cannot see.

The cost is real and correctly stated: an operator on a class-4 estate gets a CR recording
`cotp_class=4` followed by refused data TPDUs. That is a limit of the lane, documented, not a
silent misread — and it is strictly better than take 2, where the same frame decoded through a
class-0 layout one octet short.

### Can `user_data_length` still lie? On DT, no — and I tried

| Route I tried | Result |
|---|---|
| Padding after the DT header, 0 / 1 / 100 / 5,000 octets | `udl` 0 / 1 / 100 / 5,000 — all counted |
| TPKT lengths 7, 8, 100, 65,535 | all report exactly `len(payload) − 7` |
| The original D2 payload at LI 2…29, 100, 200, 254 | decodes **only** at LI 2; every other LI refuses; zero count errors |
| DT at LI 3, 4, 5 | `INCONSISTENT_COUNT` |
| The brief's own `0300000702f000` | `data`, `udl=0` |
| 70,000-octet payload, 65,535 declared | `TRAILING_BYTES`, "4465 bytes follow" |
| 65,535 declared, 8 present | `LENGTH_MISMATCH` |

Because a decoded DT has `tpkt_length == len(payload)` (proved at `:467-486` before any slice) and
`udl = tpkt_length − 7`, the count is a function of bytes that actually arrived. It cannot be
steered on a DT. **It can still be steered on an ED — finding 6.**

## Re-judgement after an escalated defect

**What I escalated.** At the first judgement (`s7comm.py` `6dd04cd8…04b5`) I recorded as finding 1
that `_decode_data_transfer` contained a branch `if cotp_class not in (None, 0): return
_DataTransferFields()` which was **provably dead** — `_preferred_class` returns a value only for CR
and CC codes, and that function is reached only when `cotp_code == 0xF0` (DT), so no DT could ever
carry a recorded class. The consequence was a documentation defect: the module docstring at
`:66-80` described a "different fixed part" protection the code did not have, implying a class-4 DT
was handled when in fact **every** DT was read through the class-0 layout regardless. I ruled it did
not move the verdict, because ADR 0347 already accepts the limitation and no done-list item depends
on it, and named it the one thing to escalate.

**What changed.** Verified myself against the new bytes, not taken on trust:

1. **The dead branch is gone and was not replaced with anything else.** `grep -n "not in (None, 0)"
   src/phos/atlas/packet/s7comm.py` returns nothing. `_decode_data_transfer`'s signature is now
   `(cotp: bytes, length_indicator: int, cotp_code: int)` (`:566-568`) — three parameters, no
   `cotp_class` — and the call site at `:462-464` passes three. The function's tail is now
   `if cotp_code != TpduCode.DATA: return _DataTransferFields()` → the LI<2 refusal → `return
   _DataTransferFields(eot=..., tpdu_nr=...)` with **no class condition at all**, which is what the
   docstring now claims.
2. **`cotp_class` is still recorded on the message and is not orphaned.** Four references remain and
   each is correct: the field docstring at `:324`, the model field at `:341`
   (`Field(default=None, ge=0, le=_PREFERRED_CLASS_MASK)`), the assignment from `_preferred_class`
   at `:460` (still called in `dissect`, unchanged), and the constructor argument at `:493`. I
   grepped for any *other* use and found none — no condition reads it. The tests still assert it in
   eleven places, including `test_a_dt_never_records_a_class` and `test_every_class_value_decodes`.
   Removing the branch therefore removed a dead guard without removing the record.
3. **The module docstring now states the limitation unconditionally.** The paragraph at `:66-84`
   reads "**Every DT is read through the class-0 layout, and that is a recorded limitation**" and
   "**Every DT gets the class-0 reading, without exception**… No recorded class governs this,
   because for a DT there is never one to consult." I read it for residual over-claims
   specifically: it asserts no protection that the code lacks, and its one forward-looking sentence
   — "nothing downstream trusts a class-4 DT's fields as though they were class-0 ones: the raw code
   is recorded" — is true as written, because it describes what a *consumer* can do with
   `cotp_code`, not what this module guarantees. It no longer implies a class-4 path exists.
4. **The function docstring matches** (`:569-587`): "**Every DT is read through the class-0 layout,
   without exception.** … a DT on a class-4 connection is read through a layout that is wrong by an
   octet. That is a known, accepted limitation of this lane rather than a bug in this function."
   Consistent with the module docstring and with the code.

**Gates at take 3**, all run by me against `2c38ed08…d5325` (preserved as history; the fifth-take
gates are above):

```
uv run pytest tests/atlas/packet/ -q           → 1051 passed, 3 skipped in 17.85s
uv run mypy --strict src                       → Success: no issues found in 295 source files
uv run ruff check                              → All checks passed!
uv run ruff format --check                     → 735 files already formatted
uv run pytest tests/atlas/packet/test_s7comm_adversarial.py -q
                                               → 435 passed, 3 skipped in 6.23s
uv run pytest tests/atlas/packet/test_s7comm_hardening.py -q
                                               → 85 passed in 5.83s
uv run pytest tests/atlas/packet/test_dissect.py -q
                                               → 19 passed in 0.05s
uv run pytest tests/atlas/packet/test_s7comm.py::TestTheDoneList -q
                                               → 18 passed in 0.04s
```

The 3 skips are `test_s7comm_adversarial.py:333`, "does not fit a length
indicator" — a parametrisation whose values cannot be expressed in the field, not
a disabled assertion. Coverage: **99%**, 208 statements, 62 branches, two missed
lines (`:490`, `:822`), both discussed under findings.

**Proof the edit changed no behaviour.** Because the deleted guard was dead, restoring it must
produce identical output. I reconstructed the pre-edit function in-process and compared it with the
new one over **8,960** `(code, LI, octet3)` combinations spanning all 256 TPDU codes, LI 0–7 and
five octet-3 values: **0 mismatches**. I then drove 20,000 random payloads (seed 424242) through the
new dissector: **0 decoded / 20,000 refused**, the same ratio as before the edit, and the structured
corpus still decodes **15,540** of 20,000 on seed 31337 — identical to the first judgement. The edit
is behaviourally inert, as the deadness proof predicted.

## The fifteen done-list items

| # | Item | Verdict | Evidence |
|---|---|---|---|
| 1 | Payload shorter than four octets is `SHORT_HEADER` | **met** | `test_item_1_a_payload_shorter_than_four_octets_is_short_header` (`test_s7comm.py:683`) sweeps 0–3; `test_a_payload_of_every_legal_length_up_to_the_header_is_refused` (`hardening:469`). Code: `s7comm.py:494-501`. My probes 9 and 10 confirm. |
| 2 | TPKT version ≠ 3 is `BAD_HEADER_FIELD` | **met** | `test_item_2_a_version_other_than_3_is_bad_header_field` (`:688`) sweeps 0,1,2,4,5,0xFF; `test_item_2_is_reachable_because_the_claim_is_the_port_not_the_version` (`:695`) proves the branch is reachable at all, which is the ambiguity ADR 0347 resolved. Code: `s7comm.py:503`. |
| 3 | Declared length < 7 is `FIELD_OUT_OF_RANGE`, checked **before** any slice | **met** | `test_item_3_a_declared_length_below_7_is_field_out_of_range` (`:702`) sweeps 0–6; `test_item_3_is_checked_before_any_slice_is_taken` (`:709`) asserts a 4-octet payload declaring 6 returns `FIELD_OUT_OF_RANGE` and not an `IndexError`/`SHORT_HEADER`. Order verified in source: `:509` (bound) precedes `:530` (slice), with `:516` and `:522` between. My probe 2 at 65535 with 8 octets present returns `LENGTH_MISMATCH`, never an allocation. |
| 4 | Declared length > bytes present is `LENGTH_MISMATCH`, never a past-buffer read or an allocation of the declared size | **met** | `test_item_4_a_length_greater_than_the_bytes_present_is_length_mismatch` (`:716`) at 7/10/100 present; `test_item_4_never_allocates_the_declared_size` (`:721`) asserts `payload_length == 7` for a 65535 declaration; `test_no_declared_length_ever_sizes_an_allocation` (`hardening:420`) over 200 random declarations of 0xFFFE/0xFFFF/0x8000/0x1000. Code: `s7comm.py:516-521`, which uses `len(payload)` and never `tpkt_length` as a bound. My probe 13 at 70,000 octets present with 65535 declared returns `TRAILING_BYTES` and reports `4465 bytes follow`, not a 65,535-octet structure. |
| 5 | Declared length < bytes present is `TRAILING_BYTES` | **met** | `test_item_5_a_length_smaller_than_the_bytes_present_is_trailing_bytes` (`:727`) and `test_item_5_a_pipelined_second_tpkt_is_trailing_bytes` (`:731`). My probe 13 crosses this path at 70,000 octets. Code: `s7comm.py:522-528`. |
| 6 | LI 255 is `FIELD_OUT_OF_RANGE` | **met** | `test_item_6_a_length_indicator_of_255_is_field_out_of_range` (`:736`) also asserts `"extensions"` appears in the detail, so the reason is not merely the right enum but the right explanation. `test_every_length_indicator_of_255_is_refused` (`hardening:483`). Code: `s7comm.py:541`. My probe 2. |
| 7 | LI claiming more header than the packet contains is `INCONSISTENT_COUNT`; a DT with LI < 2 is `INCONSISTENT_COUNT` | **met** | `test_item_7_an_li_claiming_more_header_than_present_is_inconsistent` (`:741`, LI 254 against 3 octets); `test_item_7_a_dt_with_an_li_below_2_is_inconsistent` (`:745`); `test_a_dt_whose_length_indicator_is_below_2_is_inconsistent` (`:277`) sweeps LI 0 and 1. Code: `s7comm.py:558-564` (the overrun check) and `:748-756` (the DT exact-LI rule). My probe 3 (LI 0) and probe 22 (LI 6, 3 octets present) both return `INCONSISTENT_COUNT`. |
| 8 | `reserved` recorded on every decoded message, never a refusal reason for any value | **met** | `test_item_8_the_reserved_octet_is_recorded_and_never_a_reason` (`:749`); stronger, `test_a_non_zero_reserved_octet_is_never_a_refusal_reason` (`:376`) sweeps **all 256** values asserting `isinstance(..., IsoTsapMessage)`; `test_every_reserved_octet_decodes` (`hardening:607`) sweeps all 256 again through a different builder. Source: `reserved_octet` is assigned at `:606` and never tested in any condition (grep for `reserved` finds only the field, the docstring and the unpack at `:502`). My probe 21 with `0x80`. |
| 9 | COTP class ≠ 0 recorded and never a refusal reason | **met** | `test_item_9_a_class_other_than_0_is_recorded_and_never_a_reason` (`:754`); `test_every_class_value_decodes` (`:387`) sweeps 0,1,2,3,4,5,15; `test_class_4_is_recorded_and_not_refused` (`:392`) names the Siemens "(Class 4)" evidence directly. Code: `:569` assigns `cotp_class` and `:612` puts it on the message; since the re-judgement, **no condition anywhere reads a class value** — the dead `cotp_class not in (None, 0)` branch my first verdict escalated has been deleted, so a class is recorded and nothing is inferred from it, which is a stronger form of the same guarantee. My probes 6 (CC class 4) and 15 (CR class 0). |
| 10 | A CR/CC with user data or a third parameter decodes; never refused | **met** | `test_item_10_a_cr_with_user_data_or_a_third_parameter_decodes` (`:758`); `test_a_cr_carrying_user_data_decodes` (`:428`); `test_a_cr_carrying_a_third_parameter_decodes` (`:435`, the 0xC0 max-TPDU-size parameter); `test_a_connection_confirm_carrying_user_data_decodes` (`:446`). Code: `_decode_parameters` at `:884-946` skips unnamed codes and refuses only a parameter that overruns the declared header. **The CR/CC floor and the new dangling-variable-part rule were both risks to this item, and I tested them directly at this take**: a CR at LI 6 with **5,000 octets** of initial user data decodes with `udl=5000`; a CR with both TSAPs **and** a third 0xC0 parameter decodes with both TSAPs read; a CR with a third parameter plus 100 user octets decodes with `udl=100`; a CC at LI 6 with class 4 and 20 user octets decodes. All 32 CR/CC code octets (every credit value) decode at LI 6 and refuse at LI 5. The red team's five guard tests at `test_s7comm_adversarial.py:1204-1245` assert the same and pass. |
| 11 | EOT is bit 8 of octet 3 and TPDU-NR bits 7–1; no other bit position used | **met** | `test_item_11_eot_is_bit_8_and_tpdu_nr_bits_7_to_1_on_a_dt` (`:767`) asserts 0xFF→(EOT,127), 0x80→(EOT,0), 0x00→(no EOT,0); `test_eot_and_tpdu_nr_occupy_different_bits` (`:206`) uses 0x81→(EOT,1), which is the single most discriminating octet and fails under a shift; `test_tpdu_nr_is_bits_7_to_1_of_octet_3` (`:201`) is parametrised over 0,1,2,63,64,125,126,127. Constants: `_EOT_MASK = 0x80` (`:268`), `_TPDU_NR_MASK = 0x7F` (`:271`), read at `:842-843`. My probe 7 (0xFF→127) and probe 4. |
| 12 | No `ProgramAct`, no station, no peer role, no application value from any input | **met** | `test_item_12_no_program_act_station_or_peer_role_from_any_input` (`:778`) asserts over six inputs that `act`, `program_act`, `station`, `peer_role`, `job`, `opcode` are **absent from `type(result).model_fields`** on both outcome types; `test_no_decoded_message_exposes_an_application_field` (`hardening:676`) adds `s7`, and `test_the_whole_corpus_produces_only_envelope_fields` (`hardening:681`) asserts `set(result.model_dump()) == allowed` over a 200-input corpus. Structurally: the type is `Literal["iso-tsap"]` (`:164`), so `protocol="s7comm"` raises `ValidationError` (`test_the_string_s7comm_is_unrepresentable_in_the_message_model`, `:833`). Verified independently by grep: the only occurrences of `"s7comm"` in the module are inside docstrings explaining that it is unrepresentable. |
| 13 | Seeded corpus: seed **20261105**, passing the four `test_hardening.py` claims | **met** | `SEED: Final = 20261105` (`hardening:60`), used as `random.Random(FIXED_SEED)` at `:217`, `:252`, `:284` and via `+n` offsets elsewhere. I instrumented the generators directly: `random_payloads` emits **2000** and `mutated_payloads` emits **2000**. The four claims are each a named test: never raises (`:216`), never reads out of bounds (`assert_contained`, `hardening:123-160`, with the provenance asserts at `:133-136`), never allocates unbounded (`:420`), always terminates (`:283`, 30-second budget, measured 7.17s for the whole file). |
| 14 | `modbus.py` untouched and `tests/atlas/packet/test_dissect.py` still passes | **met** | `git diff --stat HEAD` empty for `src/phos/atlas/packet/modbus.py`, `tests/atlas/packet/test_dissect.py` and `tests/atlas/packet/test_hardening.py`; `uv run pytest tests/atlas/packet/test_dissect.py -q` → **19 passed in 0.05s**. Also `test_both_can_be_registered_without_a_name_clash` (`:914`) asserts `registry.names == ("modbus", "iso-tsap")`. |
| 15 | Every decoded message and every refusal traces to the frame it came from | **met** | `test_item_15_every_result_traces_to_its_frame` (`:795`) and `TestTraceability` (`:852`) assert capture, frame index, timestamp, `src` and `dst` on both outcomes; `assert_contained` (`hardening:133-136`) asserts `source`, `timestamp`, `src`, `dst` on **every one of the ~140,000 corpus outcomes across the hardening and adversarial suites**. Source: `IsoTsapMessage` is constructed with all five at `:600-604`; `_refuse` with all five plus `payload_length` at `:620-630`. |

## The refusal list

| Refusal | How I checked it | Result |
|---|---|---|
| The module emits a `ProgramAct`, a station, or an application field | `test_item_12` asserts field-name absence on `model_fields` for both outcome types; `test_the_whole_corpus_produces_only_envelope_fields` asserts `model_dump()` equal to the allowed set over a corpus; I grepped the module for `ProgramAct`, `station`, `peer_role`, `opcode`, `job` — one hit, prose in the module docstring at `:16` explaining that no such field exists. No `ProgramAct` import exists anywhere in the file. | **Not violated** |
| The dissector reports `protocol == "s7comm"` or claims to have read S7 | `IsoTsapProtocolName = Literal["iso-tsap"]` (`:164`); `IsoTsapMessage.protocol` typed with it (`:442`). `test_every_message_reports_iso_tsap` (`:819`), `test_every_refusal_reports_iso_tsap` (`:829`), `test_every_message_reports_iso_tsap`'s hardening twin `test_no_corpus_result_reports_s7comm` (`hardening:697`). `assert_contained` asserts it on every corpus outcome. | **Not violated** |
| A non-zero `reserved`, a class ≠ 0, or a CR/CC with user data becomes a `MalformedFrame` | Three separate 256-value and multi-class sweeps, plus my probes 5, 6, 15, 16, 21. No condition in the source reads `reserved_octet`; no condition refuses on `cotp_class`; `_decode_parameters` never refuses on parameter count. | **Not violated** |
| `65524` appears in the source as a bound | `grep -n 65524 src/phos/atlas/packet/s7comm.py` → exactly **one** hit, line 38, inside the module docstring: *"65524 is deliberately absent: RFC 1006 states it as a maximum TSDU and it contradicts the memo's own minus-3 rule…"*. No `Field(le=65524)`, no `Final = 65524`, no comparison against it. The only coded ceilings are `TPKT_MAX_OCTETS = 65535` (`:188`) and `TPDU_MAX_OCTETS = 65531` (`:195`). | **Not violated** |
| A declared length sizes an allocation or slice before comparison with bytes present and with 65535 | Source order: `:494` header-length gate → `:503` version → `:509` `tpkt_length < 7` → `:516` `tpkt_length > len(payload)` → `:522` `tpkt_length < len(payload)` → **only then** `:530` the slice `payload[4:tpkt_length]`. Every later bound (`:558` `header_end`, `:915`) derives from `length_indicator`, itself read at `:540` after `:531` established three octets exist. `test_item_4_never_allocates_the_declared_size`, `test_item_3_is_checked_before_any_slice_is_taken`, `test_no_declared_length_ever_sizes_an_allocation`. My probe 13 (70,000 octets, 65535 declared) and probe 1 (65535 declared, 8 present). | **Not violated** |
| The implementation raises on any input, or wraps the decode in `try` | AST scan of the module: **zero `Try` nodes, zero bare `except`, zero `Global` statements, no module-level mutable state** (only `__all__` and a `Literal` alias). Grep for `try`/`except` returns only docstring lines explaining that there is none. Empirically: 20,000 random payloads on my seed 777777, 20,000 structurally-valid envelopes on seed 31337, 2,304 exhaustive LI×code combinations, 169 length-sweep combinations, and the 65,535-octet maximum — none raised. | **Not violated** |

Two further refusals ADR 0347 makes are also honoured. **No act mapping:** the
module produces no act, and the parameter decoder (`:884-946`) reads only TSAP
codes `0xC1`/`0xC2`, skipping everything else without interpreting it. **The
IEC 61850 consequence:** an MMS frame on 102 decodes as a valid `IsoTsapMessage`
with its payload unread, which is what the record says should happen.

## The spec-audit's four defects

| Defect | Required behaviour | Honoured? |
|---|---|---|
| **D1** — `65524` is arithmetically wrong | Record it, never code it as a bound | **Yes.** One docstring mention at `:38`, no code. 65535 and 65531 are the only coded ceilings. |
| **D2** — the reserved octet's basis is RFC 2126 §6.10, not RFC 1006 silence | Record, never refuse | **Yes.** Module docstring `:57-59` cites "RFC 2126 §4.3 assigns it 0 and §6.10 says it 'should be ignored on input'"; the field docstring `:419` cites §6.10 verbatim. 256-value sweeps in both test files. |
| **D3** — X.224 prints `1111 000y`; the class-0 layout is an assumption | Document it, do not apply it silently | **Yes, and more than asked.** `:71-93` writes the assumption down — and after this round it is not an assumption at all but a refusal: the class-0 DT's LI is pinned to exactly 2, so a class-4 DT is refused rather than read through a layout one octet short.  `test_a_dt_with_roa_set_is_unknown_rather_than_read_as_class_0` (`:285`) proves the behaviour. **After the re-judgement this is stronger than "not applied silently": it is now stated as an unconditional limitation**, which is what closes the defect I escalated. |
| **D6** — RFC 1006 §5 permits CR/CC user data; do not refuse it | Decode it | **Yes.** See done-list item 10. The 128-octet CR bound is applied to the **header** (`:577`), not to user data, and the docstring at `:189-191` says so. Note `test_a_cc_is_not_bounded_at_128_because_the_clause_names_the_cr` (`:505`) correctly declines to extend the CR bound to a CC. |

## My own adversarial probes

Two throwaway scripts, both deleted; neither is committed. The first is 22
hand-built hostile inputs, none of which appears in the engineer's test files:

| Probe | Result |
|---|---|
| TPKT declaring 65535 with 8 octets present | `LENGTH_MISMATCH`, detail names both numbers |
| LI 255 | `FIELD_OUT_OF_RANGE`, "reserved for extensions" |
| LI 0 | `INCONSISTENT_COUNT`, "no TPDU code at all" |
| LI exactly equal to the header present, zero user data | decodes, `user_data_length=0` |
| CR LI 127 + **100 octets of user data** | decodes, `connection_request`, `user_data_length=100` |
| CC octet 7 with class = 4 | decodes, `cotp_class=4` |
| DT with `cotp[2] = 0xFF` | decodes, `eot=True`, `tpdu_nr=127` |
| TPKT length exactly equal to `len(payload)` | decodes, `tpkt_length=11` |
| Empty payload | `SHORT_HEADER` |
| One-octet payload | `SHORT_HEADER` |
| Port 102 at **both** ends | decodes; `direction=UNKNOWN`, not a guessed role |
| UDP frame on 102 | **not claimed** — `claims()` returns False, matching IANA's registration being a TPKT stream and `Transport.TCP` being required |
| 70,000-octet payload, 65,535 declared | `TRAILING_BYTES`, "4465 bytes follow" |
| 65,535-octet TPKT with LI 254 | decodes, `user_data_length=65276` |
| CR LI 6 | decodes, `cotp_class=0` |
| CR LI 5 (octet 7 absent) | decodes, `cotp_class=None` — not back-filled to 0 |
| CR LI 200 (over the 128 bound) | `FIELD_OUT_OF_RANGE`, "applied to the header, not to lawful initial user data" |
| DT `0xF1` (ROA) with an S7-shaped body | decodes as `unknown(241)` with `eot`/`tpdu_nr` both `None` |
| 4 octets present, 7 declared | `LENGTH_MISMATCH` |
| CR at exactly 128 octets with a 119-octet TSAP | decodes |
| Reserved `0x80` | decodes, `reserved_octet=128` |
| Declared 7 with only 3 COTP octets | `INCONSISTENT_COUNT` |

Every one returned `IsoTsapMessage` or `MalformedFrame`, never raised, preserved
`source`/`timestamp`/`src`/`dst` exactly, reported `protocol == "iso-tsap"`, and
carried a non-empty `detail` and an exact `payload_length` on every refusal.

The second script is an independent fuzz on seeds the engineer did not use:

```
exhaustive LI x 9 codes: 2304 cases, none raised
length sweep: 13 x 13 cases, none raised
independent fuzz 20000 inputs, seed 777777: decoded=0 refused=20000, none raised
structured fuzz 20000 envelopes, seed 31337: 15540 decoded, rest refused, none raised
65535-octet TPKT decodes, user_data_length = 65528
```

The `65528` corroborates spec-audit D1 independently: the largest DT that fits a
maximum TPKT carries 65,528 octets of user data, which is exactly TPDU 65,531 − 3
for the class-0 DT header — **not** RFC 1006's unreconciled 65,524. The coded
bounds behave as the audit's arithmetic says they should.

I also checked that both outcomes are reachable from **my** generator and not
only from the engineer's: my 20,000 random payloads were 100% refused (matching
the engineer's honest note that uniformly random bytes essentially never spell
version 3 and a self-consistent length), while my 20,000 *structured* envelopes
decoded 15,540 times. So the decoder is not a stub that refuses everything.

### Third-take probes against `2c38ed08…d5325`

Re-run against the bytes this verdict names, not reused from take 2. Every case below is my own,
constructed independently of the red team's corpus.

| Probe | Result |
|---|---|
| The original D2 payload (22 octets of S7 job), LI swept 2–29, 100, 200, 254 | decodes **only** at LI 2; 0 count errors at any LI |
| Brief's own `0300000702f000` | `data`, `udl=0` |
| DT LI 22 carrying the job | `INCONSISTENT_COUNT` |
| DR / ER / ED at LI 1 and LI 2 | all `INCONSISTENT_COUNT` |
| DR LI 5 (one below floor) / DR LI 6 (floor) | refuse / decode `disconnect_request` |
| ER LI 3 / ER LI 4 | refuse / decode `error` |
| ED LI 2 / ED LI 3 | refuse / decode `expedited_data`, `udl=1` |
| CR `0xE0` at LI 5 / 6 / 7 / 8 | refuse / decode / refuse (parameter list short) / decode with a zero-length `0xC0` |
| CC `0xD0` at LI 5 / 6 / 7 / 8 | same pattern |
| CR and CC at LI 6, credit `0x0`, `0x1`, `0x7`, `0xF` | all eight decode |
| CR and CC at LI 5, same credit values | all eight refuse |
| **CR LI 6 + 5,000 octets of user data** | decodes, `udl=5000` |
| CR with TSAPs + third parameter | decodes, both TSAPs read |
| CR third parameter + 100 user octets | decodes, `udl=100` |
| CC LI 6, class 4, 20 user octets | decodes, `cotp_class=4`, `udl=20` |
| 7-octet empty DT | decodes, `udl=0`, `eot=True`, `tpdu_nr=0` |
| Class-4 DT at LI 4 and LI 7 | `INCONSISTENT_COUNT` (LI rule, not a class check) |
| Empty payload / 70,000 octets / 65,535-declared-with-8-present | `SHORT_HEADER` / `TRAILING_BYTES` ("4465 bytes follow") / `LENGTH_MISMATCH` |
| LI 255 / LI 0 | `FIELD_OUT_OF_RANGE` / `INCONSISTENT_COUNT` |
| UDP frame on 102 | **not claimed** |
| Port 102 at both ends | decodes, `direction=UNKNOWN` |
| DT padding 0 / 1 / 100 / 5,000 octets | `udl` 0 / 1 / 100 / 5,000 |
| TPKT lengths 7 / 8 / 100 / 65,535 | all report exactly `len(payload) − 7` |
| **ED, same wire octets, LI 3 / 4 / 5 / 8** | `udl` 6 / 5 / 4 / 1 — **count steered by LI** (finding 6) |
| **ED LI 3 with 5,000 application octets** | decodes, `udl=5000` (XSDU cap of 16 not enforced) |

Every case returned `IsoTsapMessage` or `MalformedFrame`, none raised, and on **every** decoded
message `source`, `timestamp`, `src` and `dst` matched the frame, `protocol == "iso-tsap"`, and the
declared bounds held (`tpkt_length == len(payload)`, `0 ≤ user_data_length ≤ 65531`,
`0 ≤ tpdu_nr ≤ 127`). On every decoded **DT** I additionally asserted
`user_data_length == len(payload) − 7` and that `eot`/`tpdu_nr` were populated — the D2 invariant,
checked on every DT in my probe set rather than on a sample.

Two of my own fixtures were wrong on first run and I am recording it, because a clean probe table
should not be cleaner than the work was: a DR/ER/ED at LI 1 cannot be built with a 4+1 = 5- or
6-octet TPDU because the TPKT 7-octet minimum rejects it before the floor is reached (`TPKT
length is 6, below the 7-octet minimum`), and my LI-7 CR fixture asked for a negative-length
parameter. Corrected, both behaved as the table says. That first mistake is itself evidence the
floor ordering is right: the TPKT minimum fires before the fixed-part check, so a floor can never be
the reason a too-short packet is refused.

### Fifth-take probes against `6afddec3…bf77`

Constructed by me, not reused from take 3 and not taken from the red team's corpus.

| Probe | Result |
|---|---|
| ED, identical 11-octet COTP, LI 3 / 4 / 5 / 8 | `udl=7` / refuse / refuse / refuse |
| ED accepted length indicators over all 255 | exactly `[3]` |
| ED, 0 / 1 / 16 application octets | decode, `udl` 0 / 1 / 16 |
| ED, 17 / 5,000 application octets | `FIELD_OUT_OF_RANGE`, detail names the XSDU cap and says it is expedited-only |
| DT, 0 / 16 / 17 / 100 / 5,000 / 65,528 octets | all decode, `udl` exact — cap does not touch DT |
| CR/CC/DR/ER with 100 trailing octets | all decode — no other TPDU carries an XSDU |
| DR LI 6 / 7 / 8 | decode / refuse / decode |
| ER LI 4 / 5 / 6 / 8 | decode / refuse / decode / decode |
| CR LI 6 / 7 / 8 | decode / refuse / decode |
| CC LI 6 / 7 / 8 | decode / refuse / decode |
| CR at exactly 128 octets (LI 127, 119-octet TSAP) | decodes; 129 refuses `FIELD_OUT_OF_RANGE` |
| CR LI 6 + 5,000 user octets | decodes, `udl=5000` |
| CR with TSAPs + third `0xC0` parameter | decodes, both TSAPs read |
| CR third parameter + 100 user octets | decodes, `udl=100` |
| CC LI 6 class 4 (+ 20 user octets) | decodes, `cotp_class=4`, `udl=20` |
| `0300000702f000` | decodes, `data`, `udl=0` |
| reserved `0x00` / `0x7F` / `0xFF` | all decode, value recorded |
| CR/CC at LI 6, credit `0x0` / `0x7` / `0xF` | all six decode |

Every case returned `IsoTsapMessage` or `MalformedFrame`, none raised, and on every decoded message
`source`, `timestamp`, `src`, `dst` matched the frame and `protocol == "iso-tsap"`. On every decoded
**DT** I asserted `udl == len(payload) − 7`; on every decoded **ED**, `udl == len(payload) − 8` —
the two header widths, checked as invariants rather than on samples.

I also swept `(code × LI)` over 256 × 254 to produce the accepted-range table in finding 9, which is
the measurement this lane should have had from the start.

## The two engineer-flagged questions

### (i) `cotp[2] & 0x7F` rather than a shift for TPDU-NR — **correct, and the alternative is wrong**

RFC 905 §13.2 (fetched, line 7267 of `rfc905.txt`):

> The bits in an octet are numbered from 1 to 8, where bit 1 is the low-ordered bit.

and §13.7.3 d) (line 8330):

> TPDU-NR is bits 7-1 of octet 3 for classes 0 and 1.

Bit 1 is the **least** significant, so "bits 7–1" is the seven **low** bits and
octet 3 must be read as `octet & 0x7F`. Bit 8 is the high bit and carries EOT
(§13.7.3 c)); the mask `0x80` is therefore right for EOT and wrong for TPDU-NR.
A shift `octet >> 1` would read bits 8–2 and would put EOT inside TPDU-NR:
`0x80` would report TPDU-NR 64 instead of 0, and `0x81` would report 64 instead
of 1. The engineer's choice is the RFC's numbering, not a shortcut, and
`test_eot_and_tpdu_nr_occupy_different_bits` (`:206`) is exactly the assertion
that fails under the shift. **Ruling: correct as implemented; `0x7F` masks and
`0x80` EOT are the only readings consistent with RFC 905 §13.2.**

### (ii) A refusal for `LI == 0` — **justified, though it is an addition to the declaration**

ADR 0347's done list item 7 names `INCONSISTENT_COUNT` for an LI that claims
more header than the packet contains, and for a DT with LI < 2. It does not name
LI 0 separately, so the engineer is right that the refusal is not on the list.

It is nonetheless **justified**, for three reasons. First, LI 0 declares a
one-octet header — the length indicator alone — so there is no octet 2 and
therefore no TPDU code at all; continuing would require reading user data as a
header, which is the exact class of error the package exists to prevent. Second,
RFC 905 §13.2.1 bounds LI's range from the format, and a header of zero
parameters and no code describes no TPDU Table 8 names. Third, the reason it
emits already exists and is the right one: `INCONSISTENT_COUNT` is the shape
"two counts that must agree did not", and here the declared header does not
contain the code the TPDU requires.

The discipline question is whether an engineer may add a refusal. ADR 0347's
refusal list forbids refusals on four specific grounds — non-zero reserved,
class ≠ 0, CR/CC user data, and `65524` as a bound — and LI 0 is none of them.
Its own done list is explicitly *"the judge tests exactly these"* for the fifteen
items, not a closed set of permitted refusals, and item 7's own wording ("an LI
that claims more header than the packet contains") is a floor that LI 0 violates
more severely than LI 1 does. **Ruling: justified. It is a tightening inside the
declaration's spirit, not scope invented against it, and it should be written
into the next declaration for this family rather than left as an engineer's
note.** I record that I would have reached the same verdict with the refusal
absent, since LI 1 already exercises the branch.

**Both rulings stand, at every take including this one.** The LI 0 refusal is at
`:549-556` (it has moved twice with added constants) and is the same branch, still
returning `INCONSISTENT_COUNT`; I re-probed it against the current bytes and it
holds. Ruling (i) is likewise unchanged: `cotp[2] & _TPDU_NR_MASK` is still the
reading (`:843`), `_TPDU_NR_MASK = 0x7F` still exists (`:297`), the model-level
bound `Field(ge=0, le=_TPDU_NR_MASK)` is still on the field (`:449`), and the
mutation check below shows the tests that enforce it still fire under a shift.
**The LI == 0 ruling therefore still applies**, and the new `_fixed_part_refusal`
does not overlap it: an LI of 0 is refused before any fixed-part floor is
consulted, because there is no code octet to key a floor on.

## Findings that do not change the verdict

These are recorded because a judge who does not report them is not judging.

1. **Two lines are uncovered (99% of statements, 72 branches, 227 statements).**
   Measured with the Coverage API because `--cov` under `uv run` hits an
   `ImportError: cannot load module more than once per process` in numpy — a
   pre-existing environment quirk, not this lane's. The two missed lines are
   `:532` and `:913`.
   - `:532` is the `_COTP_MIN_HEADER_OCTETS` guard. It is **defensively
     unreachable**: `tpkt_length >= 7` at `:509` and `len(payload) == tpkt_length`
     at `:516`/`:522` together guarantee the COTP slice is at least 3 octets, so
     no input can reach it. Keeping it is the right call — the constant's own
     docstring says the safety of the slice "does not rest on a constant two
     modules away" — but a guard nothing can reach is not evidence.
   - `:913` is the `length_indicator < _CONNECT_FIXED_PART_OCTETS` guard inside
     `_decode_parameters`. It became unreachable **because of the take-3 fix**:
     `_fixed_part_refusal` refuses any CR/CC below LI 6 before the parameter
     parser runs, so the guard can never fire. It is harmless defence in depth,
     and the code says so in `_preferred_class`'s docstring, but it is the same
     shape as the defect I escalated at take 2: a branch kept for safety whose
     reachability a fix removed. I am **not** escalating it — it guards an
     index, it makes no claim about behaviour, and removing a belt-and-braces
     index guard is the kind of change that turns a future reordering into an
     `IndexError`. Recording it is the honest middle.
2. **`grep -rn 65524 src/` also matches a stale
   `src/phos/atlas/packet/__pycache__/s7comm.cpython-312.pyc`.** Byte code is
   not source and the tracked tree is clean, but a future `65524` audit that
   greps the working tree will get a false positive from a build artifact. Not a
   finding against the engineer.
3. **The module is not exported from `phos.atlas.packet`.** Correct per ADR 0347
   ("Package exports are added by the orchestrator, not the engineer"), and the
   tests import from the submodule, which is why they pass. The lane is not
   reachable from `dissect_capture` until the orchestrator lands the export —
   worth stating so nobody reads "met" as "Atlas now reads 102 in production".
4. **The three new tests do not all discriminate the shift, and that is
   correct.** Mutation testing (below) shows only
   `test_an_asymmetric_octet_3_separates_the_two_candidate_readings` fails under
   `tpdu_nr=(cotp[2] >> 1) & 0x7F`; the other two pass. That is the right
   outcome, because they claim something else: one pins the unconditional
   class-0 layout, the other pins the absence of cross-frame correlation. A
   reviewer who expected all three to fail would be wrong about what they are
   for. The engineer's self-report on this — that `0xFF` is degenerate and an
   asymmetric octet was needed — is **sound**, and I verified it arithmetically.
5. **Residual wording of the same class as the escalated defect — closed at this
   take.** At take 2 the `eot` and `tpdu_nr` *field* docstrings read "``None``
   for every other TPDU, and for a DT whose layout this module does not read",
   describing a DT case that could not occur. **The engineer has now corrected
   them**: `:386-390` reads "always populated on one: every accepted DT is a
   class-0 DT, because any other length indicator is refused. ``None`` for every
   non-DT TPDU, whose fixed part has no EOT field." I re-checked the claim — I
   swept all 256 octet-3 values and no DT produces `eot is None` or
   `tpdu_nr is None` — so the docstring now matches the code. Finding closed,
   retained as history.
6. **The ED steerable-count defect — closed at this take.** At take 3 I recorded
   that an ED with a length indicator above 3 was accepted and its
   attacker-chosen LI steered `user_data_length`, so the same six application
   octets reported 6, 5, 4 and 1. That was the D2 defect surviving on the one
   other code with a DT-like shape, and I said then that it would move the
   verdict to `needs-work` if the programme decided a steerable count was
   unacceptable anywhere. **That call was made and the defect is fixed.**
   Re-running the exact take-3 experiment against these bytes:

   ```
   ED LI 3, identical 11-octet COTP -> udl=7
   ED LI 4, identical 11-octet COTP -> refused/INCONSISTENT_COUNT
   ED LI 5, identical 11-octet COTP -> refused/INCONSISTENT_COUNT
   ED LI 8, identical 11-octet COTP -> refused/INCONSISTENT_COUNT
   ```

   Sweeping all 255 length indicators, the ED accepted set is exactly `[3]`, and
   the count is now `tpkt_length − 8` (LI + code + credit + TPDU-NR/EOT = 4
   header octets plus the 4-octet TPKT header), which I verified for every n in
   0…16. The XSDU cap of 16 is enforced and correctly expedited-only. **Finding
   closed**, retained as history because the take-3 reasoning is what justified
   the change.
7. **RFC 905 contradicts itself on the DR code octet, and the module takes the
   safe side.** Table 8 prints `1000 0000`; the §13.5.1 structure diagram prints
   `1000 0001`; §13.5.3 a) prints `1000 0000`. The module names `0x80` and
   therefore decodes a `0x81` DR as `unknown(129)` — a decoded message with no
   floor rather than a refused one. That is correct: Table 8 and §13.5.3 both say
   `0x80`, the diagram is the outlier, and an unnamed code carrying no claim
   imposes no fixed part. Worth recording because a future session reading only
   §13.5.1 would "fix" the module in the wrong direction.
8. **RFC 905 §13.8.5's lower bound on ED user data is not enforced, and I am not
   treating it as a defect.** That clause reads "This field contains an expedited
   TSDU **(1 to 16 octets)**". The module enforces the 16 and accepts 0: an ED at
   LI 3 with no application octets decodes with `udl=0`. I probed it specifically
   because the upper bound was just added, and a lower bound left out in the same
   clause is the kind of asymmetry a later round would find.

   It does not move the verdict, and the reason is stronger than "the bar does not
   name it": unlike the upper bound, accepting 0 **cannot be steered and cannot
   mislead**. A zero-length ED reports zero, which is the truth about the octets
   that arrived; the defect class this lane spent five rounds on is a count that
   *lies*, not a count that is permissive. Refusing it would be a behaviour change
   with no evidence that a zero-octet expedited TPDU breaks anything, and the
   declaration names no refusal for it. The adversarial file records the same
   judgement at `test_an_ed_with_no_user_data_decodes`. If a later record decides
   1 is a floor, that is a one-line change in the same place as the cap.
9. **The lane's real lesson, mechanised: measure the least *and greatest*
   decodable length indicator for every named TPDU.** My 256-code × 254-LI sweep
   at this take reports, for each named type, the LI range it will accept:

   ```
   connection_confirm   LI   6..254  range 249
   connection_request   LI   6..126  range 121   (128 at the CR bound, see below)
   data                 LI   2..2    EXACT
   disconnect_request   LI   6..254  range 249
   error                LI   4..254  range 251
   expedited_data       LI   3..3    EXACT
   ```

   Two numbers there deserve a note so they are not read as defects. The CR's
   apparent ceiling of 126 is my sweep's fixture, not the module: LI 127 with
   all-zero filler is a parameter walk that fails because the last octet is a
   dangling code, and a properly-formed **128-octet** CR (LI 127 plus a 119-octet
   TSAP) decodes while 129 refuses — the RFC 905 §13.3 bound, intact. The DR/ER
   ceiling of 254 is correct because their variable parts are bounded but never
   parsed, so any length above the dangling one is lawful. **A range rather than
   a minimum is the test that would have caught rounds 1, 2 and 4 on day one**, and
   it is now what the adversarial suite pins (`test_no_named_tpdu_without_a_variable_part_accepts_a_larger_indicator`
   at `test_s7comm_adversarial.py:1529`).

### Mutation check on the new tests

I copied the whole repository (a `PYTHONPATH` overlay does **not** work here:
`pyproject.toml` sets `pythonpath = ["src", "."]`, which outranks it, so a
naive overlay silently tests the real module — worth knowing before anyone
trusts a future mutation run), substituted `tpdu_nr=(cotp[2] >> 1) & 0x7F` for
`tpdu_nr=cotp[2] & _TPDU_NR_MASK` in the copy, and ran the two S7comm files
against it:

```
11 failed, 168 passed in 8.63s
```

The engineer's count of **11 is exactly right**. The failures are
`test_a_valid_dt_request_decodes`, the eight `test_tpdu_nr_is_bits_7_to_1_of_octet_3`
parametrisations, `test_eot_and_tpdu_nr_occupy_different_bits`,
`test_an_asymmetric_octet_3_separates_the_two_candidate_readings`, and
`test_item_11_eot_is_bit_8_and_tpdu_nr_bits_7_to_1_on_a_dt`. Note that
`test_tpdu_nr_is_bits_7_to_1_of_octet_3[127]` **passes** under the mutant —
127 is degenerate — which is precisely why the asymmetric case was needed.

The mutant's actual output, confirming the tests fail for the right reason:

```
octet3=0xff -> eot=True tpdu_nr=127   (degenerate: mask and shift agree)
octet3=0x80 -> eot=True tpdu_nr=64    (mask gives 0)
octet3=0x81 -> eot=True tpdu_nr=64    (mask gives 1)
octet3=0x7f -> eot=False tpdu_nr=63   (mask gives 127)
```

The original module was never edited; `/tmp/mutrepo` was deleted afterwards.

## What this verdict does not claim

- **No detection.** This is a parser. It says the envelope was read; it says
  nothing about whether anything in it is anomalous, hostile or wrong.
- **No recall, no precision, no false-alert rate.** No corpus was scored, none
  was opened, and `eval_runs/log.jsonl` was not touched. The fuzz corpora are
  synthetic and prove robustness, not accuracy.
- **No A2, A3 or A7 evidence.** Reach is not performance (ADR 0422). This lane
  widens what Atlas can *hear*; it does not move the queue-ranking question (A3,
  refused by ADR 0068 and retired by ADR 0290) or the re-derivation question
  (A7, both looks spent).
- **No S7 decoding.** The module reads TPKT and COTP. It does not read an S7
  job, a PDU reference, a function code or a program transfer, and no
  `ProgramAct` is constructible from it. The act mapping remains refused, and
  the wiring lane (ADR 0361) may not construct one from this record — the audit
  signed no job byte and this verdict signs none.
- **No claim that a real Siemens PLC sends what these fixtures send.** Every
  byte tested was hand-built from RFC text. No licence-clean S7comm capture
  exists in the repository, so the shapes are standards-conformant, not
  field-observed.
- **No claim that a class-4 COTP connection is decoded.** It is not: the CR/CC is
  accepted and its class recorded, and **every data TPDU on that connection is
  refused** because a class-4 DT's fixed part cannot be two octets. That is
  correct on this port (RFC 1006 §6 exchanges only class-0 TPDUs) and it is
  declared in the module at `:70-89`, but an operator on a class-4 estate sees a
  run of malformations rather than a coverage gap. A consumer that counts
  malformed frames as hostile must know that.
- **No claim that `user_data_length` is unsteerable in general.** It is now
  unsteerable **everywhere this module reports it**: a DT's count comes from the
  verified TPKT length with LI pinned to 2, an ED's from the same source with LI
  pinned to 3 and capped at 16, and every other TPDU's from the LI-declared
  header, which is the correct source because those formats really do have a
  variable part. What is *not* claimed is that a CR's or a DR's variable part is
  interpreted: those are bounded and counted, never parsed, so a CR whose
  parameter list is nonsense can still report a `udl` derived from a header
  length the sender chose — but the octets it counts really are past the header
  the sender declared, so the count is not a lie. That distinction is the whole
  of finding 9.
- **No claim that RFC 905 §13.8.5's lower bound on ED user data is enforced.** It
  is not: an ED with zero application octets decodes with `udl=0`, though that
  clause says the field carries "1 to 16 octets". Finding 8 records why I judged
  that acceptable — a truthful zero cannot be steered or mislead, unlike the
  upper bound's absence which could be.
- **No claim that this file is committed.** It is not; the four judged files are
  untracked on `build/g-s7comm`, and `eval_runs/build/lane-g/s7comm/red-team.md`
  is untracked too. Landing is a separate step, and on `main` it drags
  `encyclopedia/`, `easy to reads/` and `README.md` with it (ADR 0044).

## What would reverse this

- A primary source naming an S7 job byte, which would make the current refusal
  to build an act mapping look like a gap rather than a decision — and would
  change what the *next* lane owes, not what this one proved.
- Any input that makes `dissect()` raise, return a value outside the bounds
  `IsoTsapMessage` declares, or lose its `FrameSource`. I found none in the
  sweeps at any of the five takes; one counter-example reverses done-list items
  13 and 15 and the never-raises refusal.
- A demonstration that the port-102 claim mislabels traffic in a way ADR 0347's
  registry argument does not cover — e.g. a non-ISO protocol registered on 102
  by IANA, which is not the case today: IANA lists exactly one service there.
- A finding that `cotp[2] & 0x7F` is wrong under a later authority. RFC 905
  §13.2 is explicit that bit 1 is the low-ordered bit, and X.224 repeats the
  §13.7.3 wording; a primary source disagreeing would reverse the ruling in (i).
- A ruling that LI 0 must **not** be refused, which would reverse (ii) and make
  the module accept a TPDU with no code octet. Nothing in RFC 905 or RFC 1006
  supports that.
- An edit to `src/phos/atlas/packet/s7comm.py` after the sha256 above. This
  verdict is against that byte-for-byte content; a changed module is a new
  judgement, not a re-reading of this one. **Five takes is the record of what
  re-judging costs, not a reason to re-stamp a sixth time without new bytes.**
- A later record showing that refusing the class-4 DT caused a real problem. The
  lane **refuses** it rather than misreading it, and the position rests on
  RFC 1006 §6 ("only TPDUs formatted for transport class 0 are exchanged"). A
  capture showing Siemens sending class-4 DT TPDUs on 102 — contrary to that
  clause — would turn this refusal into a false negative and reopen the lane.
- A re-introduction of a condition on `cotp_class` inside `_decode_data_transfer`,
  or of a *floor* where the format has an exact value (DT 2, ED 3). Either would
  recreate the steerable-count defect this document spent three takes closing,
  and each is now pinned by a full 256 × 256 sweep rather than a spot check.
- A decision that RFC 905 §13.8.5's lower bound (ED user data "1 to 16") must be
  enforced, which would make a zero-octet ED a refusal. I judged against it at
  finding 8; the counter-argument is that a clause's whole range should be
  enforced once its upper half has been, and it is a defensible position.
- **A defect the input sweep cannot see.** Everything in this verdict rests on
  sweeps of one- and two-field spaces plus a 300,000-case differential. A defect
  that needs a *sequence* of frames — the class-negotiation asymmetry the module
  cannot observe because it is stateless — is outside what any of the five rounds
  tested. That is the honest boundary of this "met", and it is the same boundary
  the reassembly limitation describes from the other side.
