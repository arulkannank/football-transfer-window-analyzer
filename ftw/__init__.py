"""ftw — Football Transfer Window analysis package.

Pipeline: scrape Transfermarkt (squads, minutes, ages, market values, transfers)
+ SofaScore (player ratings) -> detect problem positions -> classify transfers ->
score each transfer per successive season -> aggregate to a window grade.
"""
__all__ = ["__version__"]
__version__ = "0.1.0"
