# MAKEMYDRUMKIT

by LOSTINLIMERENCE — [@lostinlimerence__](https://instagram.com/lostinlimerence__)

Builds a personal drumkit out of the samples you *actually use* across your
own FL Studio beats — not a random downloaded pack. It scans your `.flp`
projects, ranks samples by how often (and how recently) you've used each
one, sorts them by drum type, and renames every sound with a theme pulled
from what you type in at setup.

---

## Quick start (no coding needed)

1. **Unzip this whole folder** somewhere on your computer (Desktop is fine).
2. **Windows:** double-click **`RUN ME.bat`**
   **Mac:** open Terminal, drag the folder into it, type `bash "RUN ME.command"`, press Enter
3. First time only: it'll check if you have Python. If you don't, it tells
   you exactly what to do (2 minutes, one download).
4. A window opens and your browser pops up automatically with the app
   running. Follow the on-screen steps.
5. When you're done, just close that window — it shuts the app down. Your
   files are already saved wherever you told it to save them.

**That's it.** You never need to touch a command line yourself unless
Step 3 tells you Python is missing — and even then it just walks you
through a normal installer.

Keep that window open the whole time you're using the app. If you close
it by accident, just run `RUN ME.bat` again.

---

## What it actually does

1. **Name it / describe your world** — a few words about your sound or
   aesthetic. This is what every sound in the kit gets named after.
2. **Point it at your FL Studio projects folder.** It finds every `.flp`
   in there (and subfolders), skipping FL Studio's `Backup` autosave
   clutter so the count reflects real, distinct beats.
3. It reads each project file directly (no FL Studio installation
   needed) and figures out every audio sample it references, then finds
   the real file on your disk — even if the project was made on a
   different computer or drive, by searching a "sample library" folder
   you point it at.
4. Every sample gets sorted into 808 / kick / snare / clap / closed hat /
   open hat / percussion / fx / vox.
5. Within each category, sounds are ranked by how often *and how
   recently* you've used them — something used 5 times last week ranks
   above something used 10 times a year ago — duplicates are removed, and
   the top 20 per category get copied into a clean, organized,
   themed-and-renamed kit folder.

## Good to know

- Nothing leaves your computer. This runs entirely locally — no accounts,
  no uploads, no internet required except to load the page's fonts.
- If a referenced sample can't be found anywhere, it's listed under
  "refs missing" in the results instead of silently vanishing.
- The audio-analysis fallback (used only when a filename/folder doesn't
  already make the drum type obvious) is a simple heuristic, not a
  trained model — it won't be perfect on every ambiguous file.

## For developers

Requires Python 3.9+.

```bash
pip install -r requirements.txt
python run_server.py
```

Then open **http://localhost:5151**.

Run it from a normal terminal, not through an IDE's embedded "preview"
panel — some of those run the process in an isolated context where file
writes don't land on your real disk.
