# Security

PHOS is a research pre-release. It is not deployable, it has never run on a live plant, and it
holds no user data. There is no release in production to patch, so the version table a deployed
product would carry is not written here.

## Reporting something

Write to [elijahagumba.research@proton.me](mailto:elijahagumba.research@proton.me). One researcher
reads that address, so a reply is best effort rather than a service level. Please say what you ran,
what you expected, and what happened, and include the commit you were on.

If what you found would put someone at risk were this code deployed, say so in the first line and
do not open a public issue for it. Anything else is welcome as a normal issue.

There is no bug bounty.

## In scope

The code in this repository: the parser, the declared-law page, the older detectors kept here so
published measurements still reproduce, and the harness scripts. A crash, a path traversal, a
dependency with a known advisory, a way to make the page assert something the record does not
support: all of these are worth reporting.

## Not a vulnerability, and better raised as an issue or a discussion

Some reports arrive against a detection system that are really arguments about measurement, and
they are more useful in the open:

- **Atlas missed an attack, or raised an alert that was not one.** That is a measurement, not a
  defect. Every rate published here is in the record with the corpus and the caveat it was measured
  under, including the ones that failed.
- **A law has no check.** A declared law the page cannot check is listed and takes no line. That is
  the designed behaviour, not a gap in the code.
- **The page said nothing.** An empty page means the checks ran and the laws stood, or the plant
  named a law and supplied nothing to check it against. It is not a claim that the plant is safe.
- **A break was not called an attack.** A break means a declared law is false. Naming the cause is
  refused by design.

## Please do not

Send live attack tooling, exploit code against third-party plants, or data from a real plant that
you are not authorised to share. This project tests against published corpora only, and an
unsolicited plant capture creates a problem for both of us.
