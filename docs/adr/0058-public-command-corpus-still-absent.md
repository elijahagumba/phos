# ADR 0058 — Public command corpus still absent (Clock A restatement)

- **Status:** Accepted
- **Date:** 2026-08-23
- **PART:** Category programme Session D3
- **Supersedes:** nothing. Restates [ADR 0040](0040-no-labelled-public-command-corpus.md).
- **Depends on:** ADR 0040, ADR 0046, ADR 0047, ADR 0056

## Context

Session D3 is the same gate as command-lead session 5. No labelled control-action
capture arrived during Clock A.

## Decision

`discover_labelled_command_corpora` remains empty.
`test_this_repository_holds_no_labelled_command_corpus` still passes.
Data4Cyber process-phase clocks are not command windows. S7 parquet is not a pcap.
3W faults are not attacks.

## Consequences

- Known-station 0/16 and unknown-master 1/4 stay frozen, unpooled.
- ≥70% remains unearned.
