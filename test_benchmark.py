import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import common
from benchmark_sklearn_spark import median_run


class DatasetTests(unittest.TestCase):
    def test_scaled_records_keep_their_original_split(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(common, 'SCALED_DIR', Path(tmp)):
            original = pd.read_csv(common.scaled_csv(1))
            scaled = pd.read_csv(common.scaled_csv(3))
            self.assertEqual(len(scaled), 3 * len(original))
            self.assertEqual(set(original['split']), {'train', 'test'})
            self.assertEqual(scaled.groupby('source_id')['split'].nunique().max(), 1)
            self.assertEqual(dict(original.groupby('source_id')['split'].first()),
                             dict(scaled.groupby('source_id')['split'].first()))
            self.assertEqual(int((scaled['split'] == 'test').sum()),
                             3 * int((original['split'] == 'test').sum()))

    def test_invalid_scale_is_rejected(self):
        with self.assertRaises(ValueError):
            common.scaled_csv(0)

    def test_repeats_preserve_raw_totals_and_variation(self):
        runs = iter([1.0, 2.0, 9.0])
        raw = []
        def run():
            value = next(runs)
            return dict(fit_time_s=value, inference_time_s=value, total_time_s=value)
        result = median_run(run, 3, raw, 10)
        self.assertEqual(result['total_time_s'], 2.0)
        self.assertGreater(result['total_time_s_std'], 0)
        self.assertEqual([r['total_time_s'] for r in raw], [1.0, 2.0, 9.0])
        self.assertEqual([r['repeat'] for r in raw], [1, 2, 3])
        self.assertEqual({r['scale'] for r in raw}, {10})


if __name__ == '__main__':
    unittest.main()
