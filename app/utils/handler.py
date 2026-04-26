def remove_validation_input(value):
    if isinstance(value, dict):
        return {
            key: remove_validation_input(item)
            for key, item in value.items()
            if key != "input"
        }
    if isinstance(value, list):
        return [remove_validation_input(item) for item in value]
    return value
