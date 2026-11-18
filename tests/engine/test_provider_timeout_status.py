import pytest

from alphadiana.results.status import infer_score_status, is_legacy_timeout_zero_record


@pytest.mark.parametrize('error_type', ['APITimeoutError', 'HTTPTimeoutError'])
def test_provider_timeout_is_not_a_scored_solver_timeout(error_type):
    record = {
        'score': None,
        'correct': None,
        'error': {'error_type': error_type, 'error': 'Request timed out.'},
        'token_usage': {},
    }
    assert not is_legacy_timeout_zero_record(record)
    assert infer_score_status(record) == 'provider_error'
