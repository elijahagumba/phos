# ADR 0163 — The TU Wien pilot factory is registered, and the split is two benign files

- **Status:** Accepted
- **Date:** 2026-10-17
- **PART:** October 2026 build, lane D, TU Wien (normal behaviour only)
- **Depends on:** [ADR 0040](0040-no-labelled-public-command-corpus.md),
  [ADR 0143](0143-the-plant-map-fails-the-gate.md),
  [ADR 0144](0144-the-october-build-is-declared.md)

## Context

The operator's instruction of 17 October 2026 says this lane registers the TU Wien pilot factory
and declares its development and held-back split before any of its files is downloaded. ADR 0144
left it out of that declaration on purpose.

The record is https://researchdata.tuwien.ac.at/records/vs6hv-1vs74, version 1.0.0, published
2024-08-11, DOI 10.48436/vs6hv-1vs74. The metadata rights title is Creative Commons Attribution
4.0 International (CC BY 4.0). The same text asks for a citation of "Malware Communication in
Smart Factories: A Network Traffic Data Set".

The metadata, not the payload, names nine files and 146,683,465,352 bytes. That is not the
brief's about 5.6 GB. `extractions.zip` is 5,583,930,351 bytes. The publisher's file note says
files whose names start with `tf` are training files of benign operational data, and the other
main files contain operational data and attack data. `a_day_tuesday_dos.zip` is an extra attack
day, including a denial of service, and the publisher says it is not labelled. `images.zip` is
descriptive images. `extractions.zip` mixes labelled and unlabelled extracts. Checksums in the
record are MD5. There is no publisher sha256.

An August 2026 assessment already refused this record as a labelled command corpus (ADR 0040).
The attacks are scans. They never command a controller. That refusal stands. This registration
does not turn the record into a catch corpus.

## Decision

Two scored halves, whole files, chosen from the metadata:

| Half | Registry name | File | Bytes | MD5 |
| --- | --- | --- | ---: | --- |
| Development | `tu-wien-pilot-factory` | `tf_a.zip` | 43,271,721,723 | `e1e689c877b45858fc6c41fd000f85da` |
| Held back | `tu-wien-pilot-factory-heldout` | `tf_s.zip` | 57,610,245,633 | `1a809db9022a5073ff4f30f00639addb` |

The development URL is
`https://researchdata.tuwien.ac.at/api/records/vs6hv-1vs74/files/tf_a.zip/content`.
The held-back URL is the same path with `tf_s.zip`. The held-back file is not downloaded.

These files are not in either scored half, and they are not downloaded:

| File | Bytes | MD5 |
| --- | ---: | --- |
| `a_day1.zip` | 3,021,578,268 | `4f64a19cdf5d0806512cb2cb34bb09a5` |
| `a_day2.zip` | 2,023,443,392 | `e64e23cc64756365a207292bc11c8fc3` |
| `s_day1.zip` | 5,955,896,387 | `cad30e6c1d0e7feeb06c41e3674974d0` |
| `s_day2.zip` | 6,458,154,365 | `94c35bf961d07abb2617080fe4783d57` |
| `a_day_tuesday_dos.zip` | 22,754,004,822 | `31c7c2d1186095372e917885fb0c7e0e` |
| `extractions.zip` | 5,583,930,351 | `80e6f68d3a5024131fd7d8b69f788f20` |
| `images.zip` | 4,490,411 | `3083b39a47ebdc9261a3d1e37d285c6a` |

Use the development file, if it is fetched, only to learn a command graph and to count false
alerts. Do not count catches. Do not treat a scan as a command attack. Record sha256 before use.
Do not commit the payload.

## Consequences

`tu-wien-pilot-factory-heldout` is the last name in `DECLARED_HELD_OUT`. The August refusal as a
command corpus stays in the registry note. Known-station lead 0/16 and unknown-master lead 1/4
are unchanged.
