from app.ps1.models import OccupancyAssignment as Row
from app.ps1.semantics_audit import direct_night_contradictions


def test_same_and_different_night_has_minimal_source_witness():
    rows = [Row('A', 1, 'tunnel', 'shared'), Row('B', 1, 'tunnel', 'shared'),
            Row('A', 1, 'platform', 'one'), Row('B', 1, 'platform', 'two')]
    result = direct_night_contradictions(rows)
    assert len(result) == 1
    assert result[0]['activities'] == ['A', 'B']
    assert result[0]['same_night']['csv_rows'] == [2, 3]
    assert result[0]['different_nights']['csv_rows'] == [4, 5]


def test_labels_are_not_global_and_weeks_are_independent():
    rows = [Row('A', 1, 'left', 'g'), Row('B', 1, 'right', 'g'),
            Row('A', 2, 'left', 'g'), Row('B', 2, 'left', 'other')]
    assert direct_night_contradictions(rows) == []


def test_consistent_local_labels_do_not_need_global_names():
    rows = [Row('A', 1, 'tunnel', 'one'), Row('B', 1, 'tunnel', 'one'),
            Row('A', 1, 'platform', 'two'), Row('B', 1, 'platform', 'two')]
    assert direct_night_contradictions(rows) == []
