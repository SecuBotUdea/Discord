import json
from pathlib import Path

def load_team_guild_map() -> dict[str, str]:
    app_root = Path(__file__).parent.parent
    file_paths = [
        app_root / "team_guild_map.json",
        app_root.parent / "team_guild_map.json",
    ]

    for path in file_paths:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

    raise FileNotFoundError(
        f"team_guild_map.json not found in {file_paths[0]!s} or {file_paths[1]!s}. "
        "Place the file at the repository root or inside the app directory."
    )