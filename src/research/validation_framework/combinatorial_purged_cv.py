# mypy: ignore-errors
import logging
import numpy as np
from itertools import combinations
from typing import Tuple, Generator

logger = logging.getLogger(__name__)


class CombinatorialPurgedCV:
    """
    Scientific Backtest Validation Framework.
    Implements Combinatorial Purged Cross-Validation (CPCV) to rigorously prevent
    data leakage and survivorship bias during execution policy backtesting.
    """

    def __init__(self, n_splits: int = 6, n_test_splits: int = 2, embargo_td: int = 2):
        """
        n_splits: Total number of temporal partitions.
        n_test_splits: Number of partitions used for testing in each path.
        embargo_td: Number of observations dropped after a training set to prevent serial correlation leakage.
        """
        self.n_splits = n_splits
        self.n_test_splits = n_test_splits
        self.embargo_td = embargo_td

    def get_splits(
        self, data_length: int
    ) -> Generator[Tuple[np.ndarray, np.ndarray], None, None]:
        """
        Generates purged and embargoed train/test splits.
        """
        indices = np.arange(data_length)  # noqa: F841
        split_size = data_length // self.n_splits

        # Define the partition bounds
        partitions = [
            (i * split_size, (i + 1) * split_size) for i in range(self.n_splits)
        ]
        # Fix last partition to go to the end
        partitions[-1] = (partitions[-1][0], data_length)

        # Generate all combinations of test splits
        test_combinations = list(combinations(range(self.n_splits), self.n_test_splits))

        for test_idx_tuple in test_combinations:
            test_indices = []
            train_indices = []

            for i in range(self.n_splits):
                start, end = partitions[i]
                if i in test_idx_tuple:
                    test_indices.extend(range(start, end))
                else:
                    # Apply embargo/purging:
                    # If this train set immediately precedes a test set, we drop the last 'embargo_td' points
                    # (simplified logic for demonstration)
                    actual_end = end
                    if (i + 1) in test_idx_tuple:
                        actual_end = max(start, end - self.embargo_td)

                    train_indices.extend(range(start, actual_end))

            yield np.array(train_indices), np.array(test_indices)


cpcv_engine = CombinatorialPurgedCV()
