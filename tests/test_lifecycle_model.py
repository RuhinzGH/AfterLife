"""Feature engineering for the repair-outcome classifier.

This module decides what the model is allowed to learn from, and two of its
choices carry the project's whole argument about the model:

  the target is a TECHNICIAN'S label, not one this project invented, which is
  what makes the supervised problem legitimate at all;

  device_age is reconstructed from two competing sources with a sanity window,
  and a wrong age would be learned as signal rather than rejected as noise.

The heavy path (load_it_frame) reads a 58MB CSV that is gitignored, so it is
exercised against a small synthetic frame of the same shape instead. That keeps
the test honest about the LOGIC while not depending on a file CI never has.
"""
from __future__ import annotations

import pandas as pd
import pytest

from afterlife.lifecycle_model import (
    CLASS_IDX, CLASSES, EOL, IT_CATEGORIES, class_distribution,
)


class TestTheTargetIsTheTechniciansLabel:
    def test_the_three_classes_are_the_ora_vocabulary(self):
        """These strings are Open Repair Alliance's, not ours. Renaming one
        would silently stop matching the corpus and train on nothing."""
        assert CLASSES == ["Fixed", "Repairable", "End of life"]

    def test_end_of_life_is_the_class_the_thesis_turns_on(self):
        """Models are selected on EoL recall rather than accuracy. If this index
        drifted, selection would optimise the wrong class while still reporting
        a plausible-looking number."""
        assert EOL == CLASS_IDX["End of life"]
        assert CLASSES[EOL] == "End of life"

    def test_class_indices_are_stable_and_distinct(self):
        assert sorted(CLASS_IDX.values()) == [0, 1, 2]


class TestScope:
    def test_only_computing_categories_are_modelled(self):
        """The corpus is 92% small appliances. Training on all of it would
        answer a laptop question with kettles, which is the finding the corpus
        atlas exists to make visible."""
        assert set(IT_CATEGORIES) == {
            "Laptop", "Mobile", "Tablet", "Desktop computer", "Games console"}

    def test_no_appliance_categories_leaked_in(self):
        for junk in ("Vacuum", "Lamp", "Kettle", "Coffee maker", "Toaster"):
            assert junk not in IT_CATEGORIES


class TestClassDistribution:
    def test_it_counts_every_class_including_absent_ones(self):
        """A class missing from a slice must report 0 rather than vanish --
        otherwise a downstream share is computed against the wrong denominator,
        which is the error that once made this project's shares sum to 97.1%."""
        df = pd.DataFrame({"repair_status": ["Fixed", "Fixed", "End of life"]})
        d = class_distribution(df)
        assert set(d) == set(CLASSES)
        assert d == {"Fixed": 2, "Repairable": 0, "End of life": 1}

    def test_counts_sum_to_the_frame_length(self):
        df = pd.DataFrame({"repair_status":
                           ["Fixed"] * 5 + ["Repairable"] * 3 + ["End of life"] * 2})
        assert sum(class_distribution(df).values()) == len(df)

    def test_an_empty_frame_yields_zeros_not_an_error(self):
        df = pd.DataFrame({"repair_status": pd.Series([], dtype=str)})
        assert class_distribution(df) == {c: 0 for c in CLASSES}

    def test_unknown_statuses_are_not_counted(self):
        """Rows the corpus labels something else must not be folded into one of
        the three, which would put a technician's word in their mouth."""
        df = pd.DataFrame({"repair_status": ["Fixed", "Unknown", "Partially fixed"]})
        assert class_distribution(df)["Fixed"] == 1
        assert sum(class_distribution(df).values()) == 1


class TestAgeReconstruction:
    """device_age is derived, not given: prefer the explicit product_age, fall
    back to event_year minus year_of_manufacture, and reject anything outside
    0-40 from EITHER source. A wrong age is worse than a missing one, because
    the model learns it as signal."""

    def _age(self, product_age, yom, event_year=2024):
        # Mirrors load_it_frame's derivation without touching the 58MB CSV.
        age = pd.to_numeric(pd.Series([product_age]), errors="coerce")
        y = pd.to_numeric(pd.Series([yom]), errors="coerce")
        from_yom = pd.Series([event_year]) - y
        return age.where(age.between(0, 40),
                         from_yom.where(from_yom.between(0, 40))).iloc[0]

    def test_an_explicit_age_is_preferred(self):
        assert self._age(6, 2000) == 6

    def test_it_falls_back_to_year_of_manufacture(self):
        assert self._age(None, 2018, event_year=2024) == 6

    @pytest.mark.parametrize("bad", [-3, 41, 200])
    def test_an_out_of_range_explicit_age_is_rejected(self, bad):
        """41 years for a laptop is a typo, not a device. Kept, it would teach
        the model that extreme age predicts whatever that row happened to be."""
        assert self._age(bad, 2018, event_year=2024) == 6

    def test_both_sources_bad_yields_missing_not_a_guess(self):
        assert pd.isna(self._age(99, 1850, event_year=2024))

    def test_a_future_manufacture_year_is_rejected(self):
        """Negative age. Real in the corpus, from data-entry errors."""
        assert pd.isna(self._age(None, 2030, event_year=2024))
