"""Strategy package — importing it registers the full library."""
from app.strategies import library  # noqa: F401  (side-effect: registers strategies)
from app.strategies.base import (  # noqa: F401
    StrategyDef,
    all_strategies,
    get_strategy,
    merge_params,
    run_strategy,
    stop_target,
)
