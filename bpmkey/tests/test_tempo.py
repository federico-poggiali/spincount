import numpy as np

from bpmkey import tempo


def _readings(degara, percival, peak=None):
    tg = [[f, 1.0 if peak and abs(f - peak) < 2 else 0.1] for f in np.linspace(220, 50, 200)]
    return {"degara": degara, "percival": percival, "tempogram": tg}


def test_agreeing_estimators_win():
    assert abs(tempo.vote(_readings(128, 128)) - 128) < 2


def test_half_tempo_estimators_still_find_the_tempo_class():
    bpm = tempo.vote(_readings(87, 174))
    assert min(abs(bpm - 87), abs(bpm - 174)) < 2


def test_a_style_prior_picks_the_octave():
    fast = tempo.vote(_readings(87, 87), prior=(np.log(172), 0.05))
    slow = tempo.vote(_readings(87, 87), prior=(np.log(86), 0.05))
    assert abs(fast - 174) < 3 and abs(slow - 87) < 2


def test_no_readings_gives_none():
    assert tempo.vote({"degara": 0.0, "percival": 0.0}) is None


def test_fit_prior_needs_enough_tracks():
    assert tempo.fit_prior([170, 174]) is None
    mu, sd = tempo.fit_prior([170, 172, 174, 175, 176])
    assert abs(np.exp(mu) - 173.4) < 1 and sd == 0.05
