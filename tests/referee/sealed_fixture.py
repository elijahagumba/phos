"""A sealed family that exists only for tests, and nothing a plant could be drawn from.

Two guards read a family's ``sealed`` flag and need a registered family to read it from:
``phos.referee.sealed_batch._refuse_open_family`` and
``phos.referee.seeds.assert_no_sealed_in_open_pools``. Both used to be tested by naming the real
sealed family, which was wrong twice over.

It published the sealed family's identifier in test files anybody can read, for no benefit: neither
guard cares which family it is, only that the flag is set. And ``public/manifest.toml`` now
withholds ``src/phos/synth/families_sealed/`` from the export, because that package carries the
family's parameter bounds and its ``draw``, so a test that resolved the real family would fail in
the public tree for the export split rather than for a defect.

This family draws nothing. ``draw`` raises, deliberately: a fixture that could generate a plant
would be a second sealed family rather than a stand-in for one.
"""

from __future__ import annotations

from phos.synth.families import ParameterBound, PlantFamily, register_family
from phos.synth.plant_spec import PlantSpec

#: The identifier the fixture family registers under.
SEALED_FAMILY = "sealed-under-test"


class SealedUnderTest(PlantFamily):
    """A sealed family with no physics, registered so the sealed flag can be read."""

    @property
    def family_id(self) -> str:
        """The identifier these tests use."""
        return SEALED_FAMILY

    @property
    def label(self) -> str:
        """Human-readable name."""
        return "Sealed family, test fixture"

    @property
    def process(self) -> str:
        """No process. Nothing from this family is ever built."""
        return SEALED_FAMILY

    @property
    def industry(self) -> str:
        """No sector."""
        return "none"

    @property
    def summary(self) -> str:
        """What this family is for."""
        return "A fixture that answers sealed and refuses to draw. It models no process."

    @property
    def sealed(self) -> bool:
        """``True``, which is the only property of it a test reads."""
        return True

    def bounds(self) -> tuple[ParameterBound, ...]:
        """Return no bounds. A family that varies nothing cannot leak a range."""
        return ()

    def draw(self, master_seed: int) -> PlantSpec:
        """Raise. A fixture that could draw a plant would be a sealed family, not a fixture.

        Args:
            master_seed: Ignored.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("the test fixture family draws nothing")


def register() -> None:
    """Register the fixture family.

    `register_family` allows the same identifier to be registered again by the same type, so this
    is safe to call before every test.
    """
    register_family(SealedUnderTest())
