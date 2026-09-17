"""Example policy for direct file tools; shell-write parsing belongs to the provider."""

import json
import sys
from pathlib import Path


def should_block(event: dict) -> bool:
    return any("_sources" in Path(path).parts for path in event["paths"])


if __name__ == "__main__":
    print(json.dumps(should_block(json.load(sys.stdin))))
