"""Tiny decoder for the *observed* indexed SvelteKit __data.json payload.

SvelteKit serializes repeated objects/values in one flat array. Object fields and
array entries point at integer indices. This implementation supports the shapes
observed in the meter-detail response, not every possible devalue feature.
"""

from typing import Any


class SveltePayloadError(ValueError):
    pass


def _unflatten(flat: list[Any]) -> Any:
    if not flat:
        raise SveltePayloadError("Empty flattened payload")
    seen: dict[int, Any] = {}

    def expand(index: int) -> Any:
        if index == -1:  # devalue UNDEFINED marker
            return None
        if isinstance(index, bool) or not isinstance(index, int) or index < 0 or index >= len(flat):
            raise SveltePayloadError("Unexpected value reference in SvelteKit payload")
        if index in seen:
            return seen[index]
        value = flat[index]
        if isinstance(value, dict):
            obj: dict[str, Any] = {}
            seen[index] = obj
            for key, child in value.items():
                obj[key] = expand(child)
            return obj
        if isinstance(value, list):
            if value and isinstance(value[0], str):
                # Tagged devalue types have separate semantics; never guess at them.
                raise SveltePayloadError("Unsupported tagged SvelteKit value")
            arr: list[Any] = []
            seen[index] = arr
            arr.extend(expand(child) for child in value)
            return arr
        seen[index] = value
        return value

    return expand(0)


def decode_meter_detail(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
        raise SveltePayloadError("Expected SvelteKit data nodes")
    for node in payload["nodes"]:
        if isinstance(node, dict) and node.get("type") == "data" and isinstance(node.get("data"), list):
            restored = _unflatten(node["data"])
            if isinstance(restored, dict) and "meterId" in restored and "detail" in restored:
                return restored
    raise SveltePayloadError("No usable meter detail found")
