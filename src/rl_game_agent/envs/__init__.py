"""Game environment wrappers (Gymnasium Env). Target game TBD via wayfinder."""

# Registry of available environments: name -> callable returning gym.Env
ENV_REGISTRY: dict = {}
