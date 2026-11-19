#!/usr/bin/env python3
"""OmniSave: a small, cross-platform terminal library and direct media downloader."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from email.message import Message
from pathlib import Path
from typing import Any

APP_NAME = "OmniSave"
USER_AGENT = "OmniSave/1.0 (direct file downloader)"


def data_dir() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return root / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "omnisave"


def default_download_dir() -> Path:
    termux_shared = Path.home() / "storage" / "downloads"
    if termux_shared.is_dir():
        return termux_shared / APP_NAME
    return Path.home() / "Downloads" / APP_NAME


DATA_DIR = data_dir()
LIBRARY_FILE = DATA_DIR / "library.json"


def load_library() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        library = json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))
        if isinstance(library, dict) and isinstance(library.get("titles"), list):
            library.setdefault("download_dir", str(default_download_dir()))
            return library
    except (OSError, json.JSONDecodeError):
        pass
    return {"titles": [], "download_dir": str(default_download_dir())}


def save_library(library: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = LIBRARY_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(library, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(LIBRARY_FILE)


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def ask_number(prompt: str, default: int | None = None, minimum: int = 1) -> int:
    while True:
        value = ask(prompt, str(default) if default is not None else "")
        try:
            number = int(value)
            if number >= minimum:
                return number
        except ValueError:
            pass
        print(f"Enter a whole number of {minimum} or more.")


def valid_http_url(value: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(value)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except ValueError:
        return False


def ask_url() -> str:
    while True:
        value = input("Direct video file URL: ").strip()
        if valid_http_url(value):
            return value
        print("Please enter a valid http:// or https:// URL.")


def short_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    path = parsed.path.rsplit("/", 1)[-1] or parsed.netloc
    return (path[:52] + "…") if len(path) > 53 else path


def title_summary(title: dict[str, Any]) -> str:
    if title["kind"] == "movie":
        return "Movie · direct link saved" if title.get("url") else "Movie · no link yet"
    seasons = title.get("seasons", [])
    episodes = sum(len(season.get("episodes", [])) for season in seasons)
    return f"Series · {len(seasons)} season(s), {episodes} episode(s)"


def add_title(library: dict[str, Any]) -> dict[str, Any] | None:
    name = ask("Title name")
    if not name:
        print("Title name cannot be empty.")
        return None
    print("1) Series   2) Movie")
    kind = "series" if ask("Choose type", "1") != "2" else "movie"
    title: dict[str, Any] = {"id": uuid.uuid4().hex, "name": name, "kind": kind}
    if kind == "series":
        title["seasons"] = []
    else:
        title["url"] = ""
    library["titles"].append(title)
    save_library(library)
    print(f"Added {name}.")
    return title


def choose_season(title: dict[str, Any], create: bool = False) -> dict[str, Any] | None:
    seasons = sorted(title.get("seasons", []), key=lambda item: item["number"])
    if seasons:
        print("Seasons: " + ", ".join(str(item["number"]) for item in seasons))
    default = (seasons[-1]["number"] if seasons else 1)
    number = ask_number("Season number", default)
    for season in seasons:
        if season["number"] == number:
            return season
    if not create:
        print("That season has no saved episodes yet.")
        return None
    season = {"number": number, "episodes": []}
    title.setdefault("seasons", []).append(season)
    return season


def add_episode(library: dict[str, Any], title: dict[str, Any]) -> None:
    season = choose_season(title, create=True)
    if season is None:
        return
    episodes = season.setdefault("episodes", [])
    next_number = max((episode["number"] for episode in episodes), default=0) + 1
    number = ask_number("Episode number", next_number)
    episode_name = ask("Episode name (optional)")
    url = ask_url()
    episodes.append({"id": uuid.uuid4().hex, "number": number, "name": episode_name, "url": url})
    save_library(library)
    print("Episode source saved.")


def safe_filename(value: str) -> str:
    value = value.replace("\\", "/").rsplit("/", 1)[-1]
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return value[:180] or "video"


def response_filename(response: Any, url: str, fallback: str) -> str:
    disposition = response.headers.get("Content-Disposition", "")
    message = Message()
    message["content-disposition"] = disposition
    name = message.get_filename()
    if name:
        return safe_filename(name)
    path_name = urllib.parse.unquote(Path(urllib.parse.urlsplit(url).path).name)
    return safe_filename(path_name or fallback)


def unique_path(folder: Path, filename: str) -> Path:
    path = folder / filename
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    number = 1
    while True:
        candidate = folder / f"{stem} ({number}){suffix}"
        if not candidate.exists():
            return candidate
        number += 1


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def download(url: str, library: dict[str, Any], fallback: str) -> None:
    if not valid_http_url(url):
        print("This saved URL is invalid.")
        return
    folder = Path(os.path.expandvars(os.path.expanduser(library["download_dir"])))
    try:
        folder.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            content_type = response.headers.get_content_type().lower()
            if content_type in ("text/html", "application/xhtml+xml"):
                print("The URL returned a web page, not a direct media file. Use a direct file URL.")
                return
            filename = response_filename(response, url, fallback)
            destination = unique_path(folder, filename)
            partial = destination.with_name(destination.name + ".part")
            total_header = response.headers.get("Content-Length")
            total = int(total_header) if total_header and total_header.isdigit() else 0
            received = 0
            started = time.monotonic()
            try:
                with partial.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 256)
                        if not chunk:
                            break
                        output.write(chunk)
                        received += len(chunk)
                        elapsed = max(time.monotonic() - started, 0.001)
                        speed = received / elapsed
                        if total:
                            percent = received * 100 / total
                            status = f"\r{percent:5.1f}%  {format_bytes(received)} / {format_bytes(total)}  {format_bytes(int(speed))}/s"
                        else:
                            status = f"\r{format_bytes(received)} downloaded  {format_bytes(int(speed))}/s"
                        print(status, end="", flush=True)
                if received == 0:
                    partial.unlink(missing_ok=True)
                    print("\nThe server returned an empty file.")
                    return
                partial.replace(destination)
            except BaseException:
                partial.unlink(missing_ok=True)
                raise
        print(f"\nSaved to: {destination}")
    except urllib.error.HTTPError as exc:
        print(f"Download failed: server returned HTTP {exc.code} ({exc.reason}).")
    except urllib.error.URLError as exc:
        print(f"Download failed: {exc.reason}")
    except (OSError, ValueError) as exc:
        print(f"Download failed: {exc}")
    except KeyboardInterrupt:
        print("\nDownload interrupted; the incomplete file was removed.")


def pick_episode(title: dict[str, Any]) -> tuple[dict[str, Any], int] | None:
    season = choose_season(title)
    if not season:
        return None
    episodes = sorted(season.get("episodes", []), key=lambda item: item["number"])
    if not episodes:
        print("No episodes saved in this season yet.")
        return None
    for index, episode in enumerate(episodes, 1):
        name = episode.get("name") or f"Episode {episode['number']}"
        print(f"{index}) E{episode['number']:02d} · {name} · {short_url(episode['url'])}")
    choice = ask("Episode number to download (list number)")
    try:
        return episodes[int(choice) - 1], season["number"]
    except (ValueError, IndexError):
        print("No episode selected.")
        return None


def title_menu(library: dict[str, Any], title: dict[str, Any]) -> None:
    while True:
        print(f"\n{title['name']} — {title_summary(title)}")
        if title["kind"] == "movie":
            print("1) Download movie\n2) Add or replace movie URL\n3) Remove title\n0) Back")
            action = ask("Choose an action", "0")
            if action == "1":
                if title.get("url"):
                    download(title["url"], library, safe_filename(title["name"]) + ".mp4")
                else:
                    print("Add a direct URL first.")
            elif action == "2":
                title["url"] = ask_url()
                save_library(library)
                print("Movie URL saved.")
            elif action == "3":
                library["titles"].remove(title)
                save_library(library)
                print("Title removed from your library.")
                return
            elif action == "0":
                return
        else:
            print("1) List/download an episode\n2) Add an episode\n3) Remove title\n0) Back")
            action = ask("Choose an action", "0")
            if action == "1":
                selection = pick_episode(title)
                if selection:
                    episode, season_number = selection
                    name = episode.get("name") or f"S{season_number}E{episode['number']:02d}"
                    fallback = safe_filename(f"{title['name']} - {name}") + ".mp4"
                    download(episode["url"], library, fallback)
            elif action == "2":
                add_episode(library, title)
            elif action == "3":
                library["titles"].remove(title)
                save_library(library)
                print("Title removed from your library.")
                return
            elif action == "0":
                return


def list_titles(library: dict[str, Any], query: str = "") -> None:
    titles = library["titles"]
    if query:
        titles = [title for title in titles if query.casefold() in title["name"].casefold()]
    if not titles:
        print("No matching titles. Add one from the main menu.")
        return
    for index, title in enumerate(titles, 1):
        print(f"{index}) {title['name']} — {title_summary(title)}")
    choice = ask("Open a title number (or Enter to go back)")
    if choice:
        try:
            title_menu(library, titles[int(choice) - 1])
        except (ValueError, IndexError):
            print("That title number is not in the list.")


def run() -> int:
    library = load_library()
    print("OmniSave · terminal video library")
    print(f"Library file: {LIBRARY_FILE}")
    while True:
        print("\n1) Browse library\n2) Search titles\n3) Add a title\n4) Set download folder\n0) Exit")
        try:
            action = ask("Choose an action", "1")
            if action == "1":
                list_titles(library)
            elif action == "2":
                list_titles(library, ask("Search title"))
            elif action == "3":
                title = add_title(library)
                if title:
                    title_menu(library, title)
            elif action == "4":
                current = library["download_dir"]
                folder = ask("Download folder", current)
                folder = str(Path(os.path.expandvars(os.path.expanduser(folder))).resolve())
                library["download_dir"] = folder
                save_library(library)
                print(f"Downloads will be saved in: {folder}")
            elif action == "0":
                print("Take care.")
                return 0
            else:
                print("Choose one of the listed numbers.")
        except (EOFError, KeyboardInterrupt):
            print("\nTake care.")
            return 0


if __name__ == "__main__":
    sys.exit(run())
