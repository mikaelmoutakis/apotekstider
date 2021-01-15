from pathlib import Path
import json
from collections import UserDict


class JSONShelve(UserDict):
    """Implements a shelf-like class based on
    json serialization. Ie saves a dictionary to
    disc as a json object.

        >>> f = Foo("path_to_file.json")
        >>> f["hello"]="world"
        >>> f.sync()
    """

    def __init__(self, path):
        """Reads data from json-file (if it exists)
        as a dictionary."""
        self.path = Path(path)
        if self.path.exists() and self.path.is_file():
            # read previous saved file
            with open(path, "r") as f:
                self.data = json.loads(f.read())
        else:
            self.data = {}

    def sync(self):
        """Saves all data to json file"""
        with open(self.path, "w") as f:
            f.write(json.dumps(self.data))

    def close(self):
        self.sync()
