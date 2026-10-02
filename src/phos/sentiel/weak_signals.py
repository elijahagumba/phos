"""Small departures that mean nothing apart, measured for whether they mean something together.

This is the capability a per-day score **structurally cannot** express, and saying why is worth
more than the code. PART 6B collapses an entity-day into one number by summing bounded per-feature
contributions. Two consequences follow immediately. A day on which four families each departed a
little scores about the same as a day on which one family departed a lot — the sum cannot tell
"broad and shallow" from "narrow and deep". And a *week* on which a different family departed
slightly each day produces seven unremarkable scores and no seventh thing at all, because there is
nothing in the design that a week could be.

An episode is that missing seventh thing. Once one exists, three quantities become askable that
were not askable before, and this module asks them:

* **Breadth over time.** How many distinct behaviour families the episode touched, against the most
  any single one of its days touched. If those are equal, accumulation added nothing at all and the
  episode is just its loudest day wearing a longer name.
* **What the carried days brought.** An episode's *carried* days are the ones below the anchor
  threshold — behaviour a queue at this budget could never have shown an analyst. If a family
  appears only on carried days, that family reached the analyst **solely** because of accumulation.
  `WeakSignalProfile.carried_only_families` is that set, and it is the sharpest available statement
  of the capability working.
* **Accumulation across the declared graph.** Two entities the directory says are related, each
  with an episode, overlapping in time. The edge is declared (`phos.sentiel.graph`), the episodes
  are observed, and neither is inferred from the other — the same separation `phos.sentiel.paths`
  keeps.

**Every one of these is a measurement, not a detector.** Nothing here scores, ranks or alerts.
`weak_signal_profile` describes an episode that some other rule already produced, so a profile
cannot smuggle a threshold in through the back door, and a report that finds
``carried_only_families`` empty across the whole corpus has learned something real: that on this
corpus weak-signal accumulation had nothing to accumulate.

**The honest failure mode is stated up front.** Breadth here is counted over
`phos.sentiel.BehaviourFamily`, of which there are four, and one of them — ``PEER`` — is populated
by features whose positive case is untested on CERT (`PEER_REGISTER_UNTESTED_CAVEAT`). So the
ceiling on "cross-domain" is low, and an episode touching three families is nearer the maximum than
it sounds. `WeakSignalProfile.n_families_available` carries that denominator so no ratio is read
without it.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from phos.sentiel.episodes import Episode
from phos.sentiel.graph import DeclaredGraph, DeclaredRelation
from phos.sentiel.templates import BehaviourFamily

__all__ = [
    "WEAK_SIGNAL_CEILING_CAVEAT",
    "LinkedEpisodes",
    "WeakSignalProfile",
    "linked_episodes",
    "weak_signal_profile",
]

logger = logging.getLogger(__name__)

WEAK_SIGNAL_CEILING_CAVEAT: Final = (
    "Cross-domain breadth is counted over the FOUR declared BehaviourFamily values, and one of "
    "them (PEER) rests on features with no labelled positive anywhere in the data PHOS reads. An "
    "episode spanning three families is close to the ceiling, not modestly broad, and no ratio "
    "here should be read without n_families_available beside it."
)


class WeakSignalProfile(BaseModel):
    """What accumulating an episode's days added over its single loudest day.

    Attributes:
        entity_id: Whose episode this describes.
        n_days: Days in the episode.
        n_anchor_days: Days that would have reached the operator's budget alone.
        n_carried_days: Days that would not have.
        episode_families: Distinct behaviour families across the whole episode, sorted.
        best_day_families: Distinct families on the single day that touched most.
        carried_only_families: Families that appear **only** on carried days, sorted. These reached
            the analyst solely because accumulation put them in front of one.
        n_families_available: How many families exist to be touched — the denominator any breadth
            ratio needs.
        carried_score: The carried days' scores summed. Evidence that was in the corpus and, at
            this budget, would otherwise have been invisible.
        anchor_score: The anchor days' scores summed.
    """

    model_config = ConfigDict(frozen=True)

    entity_id: str
    n_days: int = Field(ge=1)
    n_anchor_days: int = Field(ge=0)
    n_carried_days: int = Field(ge=0)
    episode_families: tuple[str, ...] = ()
    best_day_families: int = Field(default=0, ge=0)
    carried_only_families: tuple[str, ...] = ()
    n_families_available: int = Field(default=len(BehaviourFamily), ge=1)
    carried_score: float = Field(default=0.0, ge=0.0)
    anchor_score: float = Field(default=0.0, ge=0.0)

    @property
    def breadth_gain(self) -> int:
        """Families the episode touched beyond what its broadest single day did.

        Zero means accumulation over time added no new domain: the episode is its loudest day.
        """
        return len(self.episode_families) - self.best_day_families

    @property
    def accumulated(self) -> bool:
        """Whether accumulation contributed anything a single day could not have.

        True when the episode either reached a domain no one day reached, or carried a family that
        only sub-threshold days spoke for.
        """
        return self.breadth_gain > 0 or bool(self.carried_only_families)


def weak_signal_profile(episode: Episode) -> WeakSignalProfile:
    """Describe what one episode's accumulation added. Pure; scores and ranks nothing.

    Args:
        episode: The episode to describe.

    Returns:
        The profile.
    """
    episode_families = sorted({name for day in episode.days for name in day.family_names})
    anchor_families = {name for day in episode.days if day.anchor for name in day.family_names}
    carried_families = {name for day in episode.days if not day.anchor for name in day.family_names}
    return WeakSignalProfile(
        entity_id=episode.entity_id,
        n_days=episode.n_days,
        n_anchor_days=episode.n_anchor_days,
        n_carried_days=episode.n_carried_days,
        episode_families=tuple(episode_families),
        best_day_families=max((day.families for day in episode.days), default=0),
        carried_only_families=tuple(sorted(carried_families - anchor_families)),
        n_families_available=len(BehaviourFamily),
        carried_score=sum(day.score for day in episode.days if not day.anchor),
        anchor_score=sum(day.score for day in episode.days if day.anchor),
    )


class LinkedEpisodes(BaseModel):
    """Two overlapping episodes on entities the directory declares a relationship between.

    The edge comes from the org chart and the episodes come from behaviour; neither produced the
    other. That is what makes this an observation about declared structure rather than a cluster
    discovered in the activity — which would be the circularity `phos.sentiel.graph` refuses.

    Attributes:
        one: The earlier entity, by id.
        other: The later entity, by id.
        relation: What the directory says they are to each other.
        overlap_days: Calendar days both episodes' spans cover.
    """

    model_config = ConfigDict(frozen=True)

    one: str
    other: str
    relation: DeclaredRelation
    overlap_days: int = Field(ge=1)


def linked_episodes(
    episodes: Sequence[Episode],
    graph: DeclaredGraph,
    *,
    relations: frozenset[DeclaredRelation] | None = None,
) -> list[LinkedEpisodes]:
    """Find overlapping episodes on declared-related entities.

    Args:
        episodes: The episodes to pair, in any order.
        graph: The declared graph. The only source of any relationship asserted here.
        relations: Which declared relations count as a link. Defaults to the reporting line and
            the two narrowest containers — the relations that describe people who actually work
            together. On r3.1 the wider containers are near-universal (73% of employee pairs share
            only the business unit), so including them would link almost everybody to almost
            everybody and the finding would carry nothing.

    Returns:
        One entry per linked pair, ordered by entity id. Quadratic in the number of episodes, which
        is fine at CERT's scale and is noted so a corpus-scale caller can bound it.
    """
    wanted = relations or frozenset(
        {
            DeclaredRelation.SUPERVISOR,
            DeclaredRelation.DIRECT_REPORT,
            DeclaredRelation.SAME_TEAM,
            DeclaredRelation.SAME_DEPARTMENT,
        }
    )
    ordered = sorted(episodes, key=lambda episode: (episode.entity_id, episode.start))
    found: list[LinkedEpisodes] = []
    for index, first in enumerate(ordered):
        for second in ordered[index + 1 :]:
            if first.entity_id == second.entity_id:
                continue
            overlap = min(first.end, second.end) - max(first.start, second.start)
            if overlap.days < 0:
                continue
            relation = graph.relation_between(
                first.entity_id.removeprefix("ent_"), second.entity_id.removeprefix("ent_")
            )
            if relation not in wanted:
                continue
            found.append(
                LinkedEpisodes(
                    one=first.entity_id,
                    other=second.entity_id,
                    relation=relation,
                    overlap_days=overlap.days + 1,
                )
            )
    logger.info(
        "found %d linked episode pair(s) across %d episode(s) on declared relations %s",
        len(found),
        len(episodes),
        ", ".join(sorted(relation.value for relation in wanted)),
    )
    return found
