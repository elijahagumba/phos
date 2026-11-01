# ADR 0401 — GRFICS runs on this host through a single bridge, and that is a different corpus

- **Status:** Accepted
- **Date:** 2026-11-01
- **PART:** GRFICS corpus registration. Precondition for the tank-level pair
- **Supersedes:** nothing. [ADR 0144](0144-the-october-build-is-declared.md)'s declared corpus
  `grfics-v3` is unchanged, still ungenerated, and still the one that needs a Linux host
- **Depends on:** [ADR 0144](0144-the-october-build-is-declared.md),
  [ADR 0400](0400-the-refused-lane-e-modules-stay-and-the-grfics-generator-is-named.md),
  [ADR 0006](0006-dataset-registry-and-never-committing-data.md),
  [ADR 0049](0049-split-scorecard-public-files-vs-partner.md)

## Context

ADR 0400 named the GRFICS generator and fixed its rules. The next step was to establish whether
the stack runs at all. It does not, as declared.

**The declared corpus needs `macvlan` on a physical host NIC.** `docker-compose.yml` defines two
macvlan networks on `eth0.95` and `eth0.90`, and the file explains why at length: with both zones on
one broadcast domain, *"Kali (DMZ) got direct ARP replies from the PLC and EWS… firewall, Suricata
and arpmon all saw nothing."* Docker's own documentation states the macvlan driver *"only works on
Linux hosts. It is not supported on Docker Desktop for Mac or Windows,"* and GRFICSv3's README says
*"Recommended OS: Linux (native, VM, or WSL2)."* The host here is macOS on arm64.

**A probe established the precise failure and then an unexpected remedy.** Two throwaway stacks were
run on OrbStack, neither touching this repository:

1. **Bridge, default subnet.** The PLC image came up healthy and the simulation image exited 1 with
   `[entrypoint] ERROR: no interface found with 192.168.95.x address`. So the entrypoint's
   requirement is not "a macvlan" but **an address inside the ICS zone's own subnet**.
2. **Bridge on `192.168.95.0/24`.** Both containers came up. The simulation logged `modbus`,
   `noise_floor` and `simulation` entering `RUNNING`; six Modbus servers listened on
   `192.168.95.10`–`.15` port 502; the PLC answered **200** to the simulation; the dashboard
   answered **200** to the host.

All eight GRFICSv3 images resolve a native `arm64` manifest, so nothing runs under emulation.

The remedy is real and it is not the declared topology. A bridge on one subnet has no router between
zones, so the DMZ/ICS separation — and the firewall, Suricata and arpmon evidence that separation
exists to produce — is absent.

## Decision

1. **A second corpus is registered: `grfics-v3-bridge`.** Role `development`, status
   `declared-external-testbed`, same pinned commit
   `37bdf101f3ad0706a7595bd01d696ce7b84db436`, same licence digest `605e9047…e44ad`. Its
   `status_note` records the probe's observations and names what the topology drops. **It is not
   `grfics-v3`, and the registry says so in the entry and in the caveats.**

2. **The two are never pooled, and a result from one is never reported beside the other as if they
   shared a topology.** This is the same discipline the split scorecard applies to corpora that
   differ in kind (ADR 0049). A difference in network topology is a difference in what the data can
   pose: `grfics-v3`'s zones can carry cross-zone evidence and `grfics-v3-bridge` cannot.

3. **The bridge entry carries the same twenty run ids by reference, not by copy.** Its note says
   *"Same run design as grfics-v3"* and enumerates nothing. The generator reads that sentence and
   follows it to `grfics-v3`'s own table, so there is one copy of the design and no second source to
   drift. A note that neither declares runs nor names a design it shares is refused rather than
   guessed at, and a test pins both halves.

4. **The generator's default entry moves to `grfics-v3-bridge`, and `grfics-v3` stays unreachable
   from it.** `registry_runs("grfics-v3")` still works for a host that has macvlan; the script's
   `DEV_ENTRY` names the bridge because that is what this host can run. Nothing in this record
   generates `grfics-v3` or claims it.

5. **What is in scope on the bridge corpus is narrow, and it is the pair the programme exists for.**
   The single-zone departures on `tank_level` and `tank_pressure`: `97201` (physical/frozen) against
   `97206` (cyber/frozen), the same signal freezing for a failed instrument and for an attacker.
   Runs that depend on cross-zone behaviour — an attacker on the DMZ reaching the PLC through the
   router — are **not** in scope on this corpus, and a later record that wants them needs the
   declared topology.

6. **Every remaining caveat travels unchanged.** It is an emulated plant, so any result is diagnosis
   and not proof (R4, ADR 0143). GRFICS source is never committed. Commercial tiers are not used.
   Fortiphyd is credited. **It is not a substitute for a real plant, and its existence does not
   advance P1.**

7. **Nothing is measured here.** No capture exists. `eval_runs/log.jsonl` is not appended, no frozen
   row is read, and v1 stays **8 of 12**.

## Consequences

- **The tank-level pair becomes reachable today, for nothing**, on the machine already in use. That
  was not true this morning: `data/grfics-dev/` had no route to any data.
- **`grfics-v3` remains the declared corpus and remains ungenerated.** Anyone comparing results to
  other GRFICS work needs that one, and it still needs a Linux host. This record does not narrow
  that gap; it provides a cheaper question alongside it.
- The probe's findings are recorded in the registry rather than only in this ADR, so a reader who
  asks "why is there a bridge corpus?" does not have to find a decision record to learn it.
- One `.gitignore` hole was found and closed while probing: `!data/*/` un-ignored every subdirectory,
  so a cloned external testbed was offered to git as a whole tree. `data/grfics-source/` and
  `data/icssim-source/` are now named explicitly, because ADR 0144 forbids the former from entering
  the repository at all.

## What would reverse this

Reporting a `grfics-v3-bridge` result as a `grfics-v3` result, or placing the two in one table as a
single topology; claiming cross-zone evidence, firewall behaviour or IDS coverage from the bridge
corpus; generating a held-back seed; committing GRFICS source or any payload; treating the bridge
corpus as a substitute for a real plant; or generating `grfics-v3` on a host without macvlan and
calling the result the declared corpus.
