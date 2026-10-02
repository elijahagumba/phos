"""Sessions D2/Ω1: every cited fact reconstructs to a stored observation."""

from tests.atlas.test_engine import corpus, fitted_on_clean_plant, vertical

from phos.atlas import AtlasEngine, observations_under


def test_every_narrative_walks_to_raw_observations() -> None:
    engine: AtlasEngine = vertical(fitted_on_clean_plant())
    narratives = engine.run(
        corpus(60, surge={"FT01": 40.0, "FT01Z": 20.0}, surge_rows=range(40, 46))
    )
    walked = 0
    for narrative in narratives:
        observations = observations_under(narrative, engine.store)
        assert observations
        walked += len(observations)
        for observation in observations:
            assert engine.store.get_observation(observation.id) is observation
    assert walked
