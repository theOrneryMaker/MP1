# ember: the MP1 Ember pad program (NOTES/PAD_CORE.md). Frozen into the firmware once settled.


def forget(name):
    """Really unload an ember module: drop it from sys.modules AND from this package (importing
    sets ember.<name>, which would otherwise keep it in memory)."""
    import sys
    import ember
    sys.modules.pop("ember." + name, None)
    try:
        delattr(ember, name)
    except (AttributeError, TypeError, KeyError):
        pass
