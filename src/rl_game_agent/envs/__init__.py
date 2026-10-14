"""Game environment wrappers (Gymnasium Env).

ruggrogue-v1: BrowserGameEnv + RuggrogueAdapter (wayfinder tickets 04-07).
"""

from .browser_env import BrowserGameEnv
from .ruggrogue import make_adapter

# Registry of available environments: name -> callable returning gym.Env.
# The factory lambda keeps browser instances isolated per VecEnv worker.
ENV_REGISTRY: dict = {
    "ruggrogue-v1": lambda: BrowserGameEnv(adapter=make_adapter()),
}

__all__ = ["BrowserGameEnv", "make_adapter", "ENV_REGISTRY"]
