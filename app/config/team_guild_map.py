import json
from pathlib import Path

def load_team_guild_map() -> dict[str, str]:
    path = Path(__file__).parent.parent / "team_guild_map.json"
    with open(path) as f:
        return json.load(f)