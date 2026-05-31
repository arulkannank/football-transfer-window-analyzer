import numpy as np

from ftw import stats


def test_spearman_monotonic():
    assert stats.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert stats.spearman([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0
    assert stats.spearman([1, 2], [1, 2]) is None          # too few points


def test_spearman_no_scipy(monkeypatch):
    """Guard the deploy bug: Spearman must not import scipy."""
    import builtins
    real = builtins.__import__

    def blocked(name, *a, **k):
        if name == "scipy" or name.startswith("scipy."):
            raise ImportError("scipy is banned in this test")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", blocked)
    assert stats.spearman([3, 1, 2, 5, 4], [3, 1, 2, 4, 5]) is not None


def test_variance_components_and_k():
    # large within-group spread, near-identical group means -> large k
    groups = [[0, 10, 0, 10], [1, 9, 1, 9], [0, 9, 1, 10]]
    within, between, nbar = stats.variance_components(groups)
    assert within > between
    k = stats.estimate_shrinkage_k(groups)
    assert k > 5


def test_shrink():
    # equal weight and k -> halfway to prior
    assert stats.shrink(8.0, 4, 4.0, 4) == 6.0
    assert stats.shrink(None, 4, 4.0, 4) is None


def test_ols_cluster_recovers_slope():
    rng = np.random.default_rng(0)
    x = rng.normal(size=200)
    y = 2.0 * x + 1.0 + rng.normal(scale=0.1, size=200)
    X = np.column_stack([np.ones(200), x])
    clusters = np.arange(200) % 20
    beta, se, t = stats.ols_cluster(y, X, clusters)
    assert abs(beta[1] - 2.0) < 0.05
    assert t[1] > 5                       # strongly significant


def test_demean_by():
    out = stats.demean_by([1, 3, 10, 14], ["a", "a", "b", "b"])
    assert list(out) == [-1.0, 1.0, -2.0, 2.0]
