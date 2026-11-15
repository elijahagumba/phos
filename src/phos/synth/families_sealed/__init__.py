"""Families held back from the default registry, and the switch that admits them.

PART R2, task 5. A **sealed** family is one the generator can draw from but does not advertise: it
is absent from `phos.synth.families.list_families`, absent from the command line's listing, and
absent from the registry entirely unless ``PHOS_SYNTH_ALLOW_SEALED=1`` is set in the environment,
because this package is only imported when it is.

**It is a loading switch and nothing else.** No scoring lives here, no exam logic, and nothing in
this package or in `phos.synth.families` knows what a sealed family is *for*. That separation is
deliberate rather than tidy: PART S6's referee is what decides to run a private exam on a process
no detector has seen, and a generator that knew which of its plants were the exam could favour
them — by tuning their bounds, by making them easier, or simply by a developer reading the code
and remembering. The generator's job is to produce plants. Which plants are kept back is a
decision made somewhere else and is not visible from here.

**The process type is deliberately not one of the five open families.** A sealed family that was
another tank chain would test whether a detector had memorised some parameters. A sealed family
that is a *gas pressure network* tests whether it learned how a plant behaves, because nothing in
the open set has compressible inventory, square-law transport between segments, or a controlled
variable the compressor only reaches after the whole line has repacked.

Importing this package registers its families and their process templates. A spec naming a sealed
process therefore cannot be built at all without the switch, which is a stronger guarantee than
hiding it from a listing would be and is asserted in ``tests/synth/test_sealed_families.py``.
"""

from phos.synth.families_sealed.gas_pressure import GasPressureFamily, GasPressurePlant

__all__ = ["GasPressureFamily", "GasPressurePlant"]
