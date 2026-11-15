# The S7comm lane, red-teamed: round 5

- **Date:** 2026-11-06 (rounds 1 to 4 the same day, against earlier bytes)
- **Round:** **5**, the last round for this lane
- **Branch:** `build/g-s7comm`
- **Target, round 5:** `src/phos/atlas/packet/s7comm.py`, sha256
  `e1dd7fa3b4659c353f6afe34bb0537095f3e4b2133479129e5de014eb4a015e0`
- **Superseded targets:** round 4 `01ba9677bff5658b08abaebc4e1583d10763d2433e6a3dfc4477226ee03b519d`;
  round 3 `2c38ed086cb87e097a0c114e6454d432abe58bb8b034870fd12963a5c34d5325`;
  round 2 `6bb5b87ab33af13b4c5a61126aef0f833150d40cab73398fa0109d72165dd5a3`;
  round 1 `a8dba0c90d36d843a496f8735c89f2cc8a00f83cb526117f86a34dbf4f35ba56`
- **Companion tests:** `tests/atlas/packet/test_s7comm_adversarial.py`, sha256
  `efdcdf28d93bd4b5fa404d79190d8e87fc60268162b9289e4ce59a663c2d6b94`
  (482 collected: **479 pass, 3 skipped, 0 fail**)
- **Engineer's test files, not edited by me:** `test_s7comm.py` sha256
  `2ffb1ccdba32a62075717a1c43ae4c929ac5339b705bff168fbe80e95394fd34`;
  `test_s7comm_hardening.py` sha256
  `3bd975a04ef226200092dcca2708417c533b30aab74c19edb4b814ed2228a9f1`
- **I am neither the engineer nor the judge.** I did not write the dissector, I did not grade it,
  and nothing here is a verdict. `docs/adr/0348-s7comm-dissection-is-judged.md` is the verdict and
  it stands or falls on its own reasoning, not on this file. Across five rounds I have written only
  this report and the adversarial test file. I did not edit `s7comm.py`, ADR 0347, ADR 0348,
  `modbus.py`, or any shared file. Nothing is committed.

## What this report is, and what it is not

It is an attempt to break one module and a record of what broke. It is **not** a verdict, and it
carries **no detection claim**: no recall, no precision, no false-alert rate, nothing for **A2**,
**A3** or **A7**. Reach is not performance (ADR 0422). A parser that survives hostile bytes has
proved it survives hostile bytes; it has proved nothing about whether the traffic it reads contains
an attack.

## The lane in five rounds

This is the record, so it names what each round found rather than only where the lane ended.

| Round | Target sha256 (first 8) | Found | Status |
|---|---|---|---|
| 1 | `a8dba0c9` | **D1** — DR, ER and ED decoded as named messages at any length indicator, their missing fixed part counted as user data. **D2** — a class-0 DT's length indicator could hide a whole S7 job: 22 application octets reported as 0. | both closed in round 2 |
| 2 | `6bb5b87a` | Adjudicated the refusal-over-decode ruling for DT (**agreed**). Found the **CR/CC asymmetry**: the D1 shape survived on the two TPDUs excluded from the floor. Found the class-4 DT narrowing and the stale docstring. | CR/CC closed in round 3 |
| 3 | `2c38ed08` | Adjudicated the CR/CC floor of 6 (**agreed**, with the nibble match as load-bearing). Claimed the D1 family **exhausted** — a claim that was scoped to fixed-part minimums and, as round 4 showed, modelled the wrong axis. | claim corrected in round 4 |
| 4 | `01ba9677` | The judge caught **ED at a floor of 3 where its LI should be exactly 3** — the D2 class under another name. I then found a **one-octet variable part** accepted on DR and ER, which RFC 905 §13.2.3 forbids. | ED closed in round 4; variable part closed in round 5 |
| 5 | `e1dd7fa3` | Adjudicated the variable-part rule (**agreed**, and my own sweep was the stale artefact). Verified the rule is generic across DR, ER, CR and CC. **No new defect.** | — |

Four of the five rounds produced a defect; the fifth produced a confirmation. Every defect was found
by sweeping an input space rather than by reading the code and guessing, and two of them (the CR/CC
asymmetry and the ED exact value) were found by exactly the kind of table-driven sweep whose *shape*
round 3 had got wrong.

## Adjudication: the variable-part rule stands, and my sweep was the stale artefact

**The rule is right.** RFC 905 §13.2.3: *"The variable part is used to define less frequently used
parameters. **If the variable part is present, it shall contain one or more parameters.**"* The same
section's diagram gives a parameter as ``[code][length][value...]`` — two octets before any value —
and its NOTE fixes the variable part's length as *"LI minus the length of the fixed part"*. So a
declared variable part of exactly one octet contains neither a code nor a length octet in full, and
is a protocol error by the standard's own words. **A DR at LI 7 with a one-octet tail must refuse.
There is no reading on which it decodes.**

**My `test_the_floor_refuses_below_and_decodes_at_and_above_it` was the wrong artefact.** It
asserted that every LI from the floor upward decodes — a **monotone assumption** that was never
true. It had survived from round 2, when the only thing being tested was that the floor did not
refuse *at or above* the minimum, and it was silently over-claiming from that day. When round 4's
finding made floor+1 a refusal, my own two tests contradicted each other. **The sweep gave way, not
the rule.**

That is worth stating plainly because it is the second time my method, not the module, was the
problem: in round 3 I modelled fixed-part rules as one integer per name, which could not distinguish
*at least* from *exactly*; in round 5 a loop encoded *at least* as if it were *monotone*. Both are
the same mistake in different clothes — treating a rule with a boundary as if it had only one side.

**The replacement asserts the four bands explicitly**, for DR and ER:

```
LI <  floor      the fixed part does not fit                              -> INCONSISTENT_COUNT
LI == floor      no variable part at all, lawful                         -> decodes
LI == floor + 1  a one-octet variable part, cannot hold a parameter       -> INCONSISTENT_COUNT
LI >= floor + 2  room for at least one real parameter                    -> decodes
```

That is a better test than the old one: it pins the *shape* of the rule rather than a lower bound,
so a future edit that removed any one band fails it. I also added
`test_the_dangling_variable_part_refusal_names_its_own_reason`, because the floor refusal and the
variable-part refusal are both `INCONSISTENT_COUNT` and an operator has to be able to tell which
field was wrong.

**The other tests were checked for the same assumption.** Of the eleven loops over `range()` near the
boundaries, nine are exact-shape sweeps (DT and ED must decode at one value only) or below-floor
sweeps, and are correct as written. One is the anonymous-code sweep, which asserts decode at every
LI because nothing is claimed for those codes. The only offender was the one named above, and I
grepped for the pattern rather than assuming.

## Is the rule genuinely generic? Yes — verified, not taken on trust

The engineer's fix lives in `_fixed_part_refusal`, guarded on `_fixed_part_minimum(cotp_code) is not
None` and keyed on `length_indicator - minimum == 1`. Because `_fixed_part_minimum` resolves CR and
CC **by high nibble**, those two reach the same guard without being named in it. I verified the
inheritance rather than reading it:

| TPDU | floor | LI 5 | LI 6 | LI 7 | LI 8 | LI 11 |
|---|---|---|---|---|---|---|
| DR `0x80` | 6 | refuse | **decode** | refuse | decode | decode |
| CR `0xE0` | 6 | refuse | **decode** | refuse | decode | depends on the variable part † |
| CC `0xD0` | 6 | refuse | **decode** | refuse | decode | depends on the variable part † |
| ER `0x70` | 4 | LI 3 refuse | **LI 4 decode** | LI 5 refuse | LI 6 decode | decode |

And the credit nibble follows too: all sixteen CR octets `0xE0`–`0xEF` and all sixteen CC octets
`0xD0`–`0xDF` refuse at LI 7 and decode at LI 6. `TestTheVariablePartRuleIsGeneric` now pins this
with a test that would fail if a future edit special-cased DR and ER and let the nibble branch fall
through.

† **One thing worth stating, because it looks like an inconsistency and is not.** A CR at LI 11 with
five octets of variable part decodes or refuses *depending on what those five octets contain*, because
the CR/CC path walks the parameter list and a five-octet variable part can hold a well-formed
parameter (`C1 03 aa bb cc`) or a dangling code. A DR at the same LI always decodes, because the
module does not walk DR's or ER's variable part — it only checks that the part is not exactly one
octet. That asymmetry is pre-existing and scoped: TSAP-IDs are read only from CR and CC, and nothing
in DR or ER's variable part is ever interpreted. It is not a defect, but a reader comparing the two
rows would wonder, so it is recorded.

## DT and ED are genuinely unaffected

The rule must be **vacuous** for the two exact shapes, not accidentally applied to them. Verified both
ways:

- **They still decode when lawful:** a DT at LI 2 with 20 user octets decodes with `udl=20`; an ED at
  LI 3 with 16 user octets decodes with `udl=16` (its XSDU ceiling).
- **When they refuse, they refuse for their own reason.** The DT and ED branches return before the
  minimum branch is reached, so the variable-part rule can never be the cause. Checked on the
  **detail string**, not just the enum, because all three refusals are `INCONSISTENT_COUNT`:

```
DT LI 3 -> "a DT declares a length indicator of 3, and RFC 905 §13.7.1 a gives the class-0 DT no
            variable part, so its length indicator is exactly 2 ..."
ED LI 4 -> "an ED declares a length indicator of 4, and RFC 1006 §6 gives the expedited TPDU the DT
            format with no variable part, so its length indicator is exactly 3 ..."
```

Neither mentions §13.2.3. `test_the_rule_is_vacuous_for_the_two_exact_shapes` sweeps LI 2 to 254 and
asserts that on every refusal.

## Is a one-octet variable part ever lawful? No — checked

The question the rule's generality depends on. RFC 905 §13.2.3 governs **every** variable part and
gives **one** parameter structure: ``[code][length][value...]``. No TPDU's section defines a different
parameter format — §13.3.4 (CR) and §13.4.4 (CC) inherit it, §13.5.4 (DR) and §13.12.4 (ER) name
their permitted parameter codes but the same two-octet header, and §13.7.4/§13.8.4 (DT/ED) permit
only a Class-4-only checksum. So there is no exemption, and odd variable parts above one octet are
still lawful: three octets is one parameter with a one-octet value, five is one with a three-octet
value. **Exactly one is the only impossible length**, which is precisely what the rule refuses and
what `test_a_three_octet_variable_part_is_lawful` and `test_a_five_octet_variable_part_is_lawful`
pin in the other direction.

**CR specifically, and whether it was already true:** a CR at LI 7 was **already refused before this
fix**, by `_decode_parameters` rather than by the new rule — the parameter walk needs a code octet
and a length octet inside the header and finds only one. So the round-4 finding was genuinely
confined to DR and ER, and the round-5 fix closes them without changing CR/CC's behaviour. The
detail string differs between the two paths (the walk says "a parameter at octet N", the new rule
says "variable part … §13.2.3"), which is correct: they are two different checks that happen to
agree here.

## Re-attack results against `e1dd7fa3…15e0`

Seed **990001** and its offsets, the same seeds as rounds 1 to 4. The reference reader was updated
for the one-octet rule and re-derived from the RFC diagrams before comparison.

| Attack | Scale | Raised | Wrong outcomes |
|---|---|---|---|
| Differential fuzz vs. independent reference reader | 300,000 | 0 | **0**, `user_data_length` **0** |
| Exhaustive LI 0-255 x code 0-255, both rule directions | 65,536 | 0 | **0** |
| Structure-aware hostile corpus | 4,000 | 0 | 0 (110 decoded / 3,890 refused) |
| Four bands x DR/ER/CR/CC | 20 | 0 | 0 |
| Credit nibble x CR/CC at LI 6 / LI 7 | 32 | 0 | 0 |
| Every prefix of every fixture | 47 cuts | 0 | 0 decoded |
| 16-bit packet-length sweep, every value | 65,536 | 0 | **0** |

**Named-shape rule table, verified by sweep rather than asserted** (LI set per named type; gaps are
the refused values):

```
connection_confirm   n=125  min=  6  gaps=[7, 9, 11] ...
connection_request   n= 61  min=  6  gaps=[7, 9, 11] ...
disconnect_request   n=248  min=  6  gaps=[7]
error                n=250  min=  4  gaps=[5]
data                 n=  1  min=  2  gaps=[]          EXACT
expedited_data       n=  1  min=  3  gaps=[]          EXACT
```

Two exact shapes, four minimums, and **zero** decodes off-rule across all 65,536 combinations. The
larger gap lists for CR and CC are the parameter walk rejecting odd-sized declared variable parts,
which is correct and pre-existing.

**The six regression cases all still hold:**

```
0300000702f000                    decode udl=0
0300000702f080                    decode udl=0
CR LI 6 + 5,000 initial user octets   decode udl=5000
CR LI 13 + third parameter 0xC0   decode calling_tsap=0100
CC LI 6 class 4                   decode cotp_class=4
reserved=0xFF                     decode reserved_octet=255
CR class 4                        decode cotp_class=4
```

**Timing and resources.** Best-of-5 with interleaved repeats, because this machine swings by nearly
2x between identical runs: **102,767 minimal envelopes/s**, peak **69,816 B** on a 65,535-octet
TPKT, determinism drift **0** over 10,000 repeats. The rule costs nothing measurable; the peak is
byte-for-byte what it was in rounds 2, 3 and 4.

## Final answer on the D1/D2 family

**I believe this module has no remaining defect of the D1/D2 family.** Stated precisely, because the
family has now produced four findings and I have twice been wrong about it:

**The family is two questions**, and both now have a sweep that checks both of their directions:

1. **A named TPDU with an unenforced or over-permissive structural rule.** The rules are: four
   minimums (DR 6, ER 4, CR 6, CC 6) and two exact values (DT 2, ED 3), plus the one-octet
   variable-part rule on the four minimums. The sweep enumerates all 256 codes x all 256 length
   indicators and finds **zero** decodes off-rule, in either direction — not below a minimum, and not
   off an exact value. `TestNoNamedTpduIsLeftUnchecked` encodes the rule *kind* per name, so it
   cannot repeat round 3's mistake of treating an equality as a floor.
2. **A sender-steerable count.** The four routes (DT count via LI, ED count via LI, ED count via a
   large body, any count via a lying TPKT) are all closed and each has a test with fixed wire octets.
   The only remaining steering is legitimate: on CR/CC/DR/ER the length indicator genuinely delimits
   a variable part.

**What would show it is not exhausted.** Any one of these, and each has a test that would fire:

1. **A seventh named TPDU** not in `MINIMUM` or `EXACT` — `test_the_table_covers_every_named_message_the_module_can_emit`.
2. **An exact value loosened back to a minimum** — `test_breaking_either_kind_of_rule_would_be_caught` now asserts `value + 1` refuses for *both* kinds and that a minimum decodes again at `value + 2`.
3. **A minimum shape that stops refusing at `value + 1`** — same test, the round-5 case.
4. **A named code whose fixed part depends on the class or the normal/extended format.** Today's six
   names have no such variants on this port, but RFC 905 §13.2.2.1's NOTE says *"different variants
   may exist for the same TPDU code"*. A future class-2 lane would need this re-derived.
5. **A count derived from the wrong header width** — the DT header is 3 octets and the ED's is 4,
   both named as constants; `test_the_count_equals_the_octets_after_the_four_octet_header` sweeps
   every ED size 0-16 and would catch a reuse of the DT width.
6. **A change to `_message_type` widening the nibble match.** If DR became nibble-matched, `0x81`
   would be named and its floor of 6 would wrongly apply — a false *refusal*, a different defect
   class, caught by `test_an_unnamed_code_is_never_in_the_family_at_any_length_indicator`.
7. **A structural rule outside the fixed-part/variable-part axis.** This is the honest limit and the
   one I would watch. My four findings all came from the same two axes because those are the axes the
   module's refusals live on. If someone later adds a rule about, say, TSAP-ID lengths or the
   relationship between DST-REF and SRC-REF, no sweep in this file covers it. I have no evidence such
   a rule is missing; I am naming the blind spot rather than claiming there is none.

**Scope of the claim.** It is about the two one-byte fields and the TPKT length, exhaustively, plus
the variable-part presence rule. It is **not** a proof about the module. Twice I have claimed this
family exhausted and been wrong once — in round 3, because my table could not express *exactly* — so
the claim here rests on a sweep that now checks both directions of both rule kinds, and the report
says which axis is unwatched.

## Final state, and the two lint errors I could not fix

The suite is **fully green**: `1120 passed, 3 skipped`, of which **479 passed, 3 skipped, 0 failed**
are mine. My file is clean under `ruff check` and `ruff format --check`.

**`uv run ruff check` over the repository is not clean, and all three findings are not mine to
fix.** In round 2 I was asked to clear 13 lint errors, all in my file, and did. This round there are
three, all in files this round's brief forbids me to edit:

```
src/phos/atlas/packet/s7comm.py:338:101   E501  Line too long (101 > 100)
tests/atlas/packet/test_s7comm.py:598:5   D415  First line should end with a period
tests/atlas/packet/test_s7comm.py         ruff format would reformat this file
```

`s7comm.py:338` is a docstring line in the new `_DANGLING_VARIABLE_PART_OCTETS` block; the
`test_s7comm.py` findings are a class docstring's first line and a formatting pass. **All three are
the engineer's to fix** — one-character and formatter changes — and I am reporting rather than making
them, because the brief says not to edit those files and I would rather hand back a red gate with a
precise location than quietly widen my own scope. I flag them plainly because the *lane cannot land*
while either gate is red, so this is a real blocker, not a footnote.

## What this report is not

It is **not a verdict**. It adds **no detection claim, no recall, no precision, no false-alert
rate**, and **nothing for A2, A3 or A7**. Reach is not performance (ADR 0422). The corpora are
synthetic and prove robustness against chosen bytes, not accuracy against traffic. Nothing here says
an S7 program transfer would be recognised, counted, or reported — the module reads an envelope,
names it `iso-tsap`, and that ceiling is unchanged.

**No real S7 capture exists in this repository**, so every shape above is standards-conformant, not
field-observed. Three standing consequences of this lane's choices, unchanged by round 5 and worth
restating for whoever owns the estate conversation:

- **Every class-4 DT is refused** (the DT LI == 2 rule). RFC 1006 §6 says only class-0 TPDUs are
  exchanged on this port, so this is defensible — but a lawful class-4 estate appears as a
  `cotp_class=4` setup followed by a run of malformations. Anything counting malformations as hostile
  should know that.
- **Every TPKT that crosses a TCP segment boundary is refused.** A 5,000-octet program download
  becomes four segments at an ordinary 1,460-octet MSS and none decodes. Documented at `:97-107`. A
  caller needing reassembly should use `reassembly.ContiguousStream.take_pdu`.
- **DR and ER variable parts are checked for presence but not parsed.** A DR at LI 11 with a
  well-formed parameter and one with five octets of rubbish both decode. Nothing is read out of them,
  so nothing is misinterpreted, but a consumer expecting a DR's clearing parameter to be validated
  will not get that.

Five rounds, four defects, all now closed, and a fix that broke nothing I could find in roughly 1.8
million inputs across the five rounds. The last round found nothing, which after four rounds of
finding something is either a genuinely settled module or the limit of a red team that has run out of
axes to sweep. I have told you which axes I swept and which I did not, so that judgement is yours
rather than mine.

## Verification commands, as run

```
uv run pytest tests/atlas/packet/ -q
1120 passed, 3 skipped in 15.62s

uv run pytest tests/atlas/packet/test_s7comm_adversarial.py -q
479 passed, 3 skipped in 7.09s

uv run ruff check tests/atlas/packet/test_s7comm_adversarial.py
[]                                    (exit 0 — my file is clean)

uv run ruff format --check tests/atlas/packet/test_s7comm_adversarial.py
1 file already formatted              (exit 0)

uv run ruff check                     (whole repository)
src/phos/atlas/packet/s7comm.py:338:101   E501  Line too long (101 > 100)
tests/atlas/packet/test_s7comm.py:598:5   D415  First line should end with a period
Found 2 errors.                       (exit 1 — both in files I am not permitted to edit)

uv run ruff format --check            (whole repository)
Would reformat: tests/atlas/packet/test_s7comm.py
1 file would be reformatted, 734 files already formatted
                                      (exit 1 — again the engineer's file, not mine)
```
