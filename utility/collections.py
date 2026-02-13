def filtered_dict(value: dict, key=lambda k, v: v is not None) -> dict:
    return {k: v for k, v in value.items() if key(k, v)}
