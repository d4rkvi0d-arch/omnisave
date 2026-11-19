# OmniSave

OmniSave is a free, open-source terminal video library for Windows, macOS, Linux, and Android through Termux. It lets you organize movies and series by season and episode, then download from direct media-file URLs you provide.

It uses only the Python standard library: no accounts, API keys, paid services, or third-party Python packages.

## Requirements

- Python 3.9 or newer
- A terminal
- An internet connection for downloads

## Get started

Clone the repository, enter its folder, and start OmniSave:

```sh
git clone <repository-url>
cd omnisave
python omnisave.py
```

On some systems, use `python3 omnisave.py` instead. On Windows, `py omnisave.py` also works.

## Termux setup

Install Python and Git in Termux, then clone and run the app:

```sh
pkg update
pkg install python git
termux-setup-storage
git clone <repository-url>
cd omnisave
python omnisave.py
```

After granting shared storage, OmniSave automatically saves downloads to `~/storage/downloads/OmniSave`. On other systems, downloads go to `~/Downloads/OmniSave` by default. You can change the folder inside the app.

## Use

1. Choose **Add a title** and pick **Series** or **Movie**.
2. For a series, add episodes and enter their season number, episode number, and direct media URL.
3. For a movie, save its direct media URL.
4. Browse or search the library and choose what to download.

Downloads stream to disk instead of loading the whole file into memory. Existing files are kept; duplicate names get a numbered suffix. The library and preferences are stored in your operating system's user data folder:

- Windows: `%APPDATA%\OmniSave`
- macOS: `~/Library/Application Support/OmniSave`
- Linux and Termux: `$XDG_DATA_HOME/omnisave`, or `~/.local/share/omnisave`

## What counts as a direct URL?

Use a URL that points to a media file, such as an MP4 or another video file, from a source you own or are authorized to download. OmniSave does not search for videos, extract links from websites, bypass sign-in or access controls, host files, or proxy streams. A URL to a webpage is not a direct download link. Some hosts require a browser session or block downloads; OmniSave cannot override those host rules.

## License

MIT. See [LICENSE](LICENSE).
