from unittest.mock import patch
import numpy as np
from neuroloop import kragel


def test_padded_terminal_window_is_not_presented_as_observed_stimulus():
    prediction = np.arange(6*4).reshape(6,4)
    with patch.object(kragel, 'decode', return_value={'status':'experimental'}) as score:
        result = kragel.decode_source_supported(prediction, [0.,1.,2.,3.,4.,5.], [1.]*6, 5.)
    rows, starts, lengths, duration = score.call_args.args
    np.testing.assert_array_equal(rows, prediction[:5])
    assert starts == [0.,1.,2.,3.,4.] and lengths == [1.]*5 and duration == 5.
    assert result['excluded_padding_rows'] == [5]
    assert prediction.shape == (6,4)


def test_fractional_terminal_window_preserves_only_actual_source_support():
    prediction = np.ones((2,4))
    with patch.object(kragel, 'decode', return_value={}) as score:
        result = kragel.decode_source_supported(prediction, [0.,1.], [1.,1.], 1.25)
    assert score.call_args.args[2] == [1.,.25]
    assert result['excluded_padding_rows'] == []
