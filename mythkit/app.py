from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request

from .builder import MAX_PER_CATEGORY, build_drumkit
from .flp_scan import find_project_flps

app = Flask(__name__)

# This app has no login and does real filesystem writes, so it must never
# be reachable by anything other than its own page in your own browser:
#   - bound to loopback only (see main() / run_server.py) — never 0.0.0.0,
#     which would expose it to the whole local network.
#   - request bodies capped, so a malformed/huge POST can't chew memory.
#   - every /api/ request must carry an Origin that matches this app's own
#     origin (or no Origin at all, which is what same-origin form/script
#     requests typically send) — this blocks the classic local-CSRF attack
#     where a malicious webpage, open in another tab, silently POSTs to
#     http://localhost:PORT/api/... using *your* browser to make this
#     server read/copy/open files on your disk without your knowledge.
#   - clickjacking is blocked (X-Frame-Options / frame-ancestors) so this
#     page can't be embedded invisibly in another site to trick you into
#     clicking "build" for real.
PORT = 5151
ALLOWED_ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}

app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2MB is generous for our JSON payloads


@app.before_request
def _reject_cross_origin_api_calls():
    if request.path.startswith("/api/"):
        origin = request.headers.get("Origin")
        if origin is not None and origin not in ALLOWED_ORIGINS:
            abort(403)


@app.after_request
def _security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    return response


# Hard safety cap: build-kit requests are handled synchronously, so bound
# how many .flp files a single request will parse. (1,264 real project
# files benchmarked at ~12s; this leaves generous headroom.)
MAX_FLPS_PER_REQUEST = 6000

_HOME = Path.home()
_PROJECTS_ROOT_CANDIDATES = [
    _HOME / "Desktop" / "Projects",
    _HOME / "Documents" / "Image-Line" / "FL Studio" / "Projects",
]
_LIBRARY_ROOT_CANDIDATES = [
    _HOME / "Desktop" / "LOSTINLIMERENCE" / "DRUMKITS",
    _HOME / "Desktop" / "DRUMKITS",
]


def _first_existing(candidates: list[Path]) -> str:
    for c in candidates:
        if c.is_dir():
            return str(c)
    return ""


@app.route("/")
def index():
    return render_template(
        "index.html",
        default_projects_root=_first_existing(_PROJECTS_ROOT_CANDIDATES),
        default_library_roots=_first_existing(_LIBRARY_ROOT_CANDIDATES),
        default_output_root=str(_HOME / "Desktop"),
    )


@app.route("/api/list-project-folders")
def list_project_folders():
    root_param = request.args.get("root", "").strip()
    if not root_param:
        return jsonify({"error": "No root path given."}), 400

    root = Path(root_param)
    if not root.is_dir():
        return jsonify({"error": f'"{root_param}" is not a folder that exists.'}), 400

    folders = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir():
            continue
        flp_count = len(find_project_flps([entry]))
        if flp_count > 0:
            folders.append({"name": entry.name, "flp_count": flp_count})

    # Also count .flp files sitting directly under root (not in a subfolder).
    root_level_flps = [
        p for p in root.glob("*.flp")
    ]

    return jsonify({
        "root": str(root),
        "folders": folders,
        "root_level_flp_count": len(root_level_flps),
    })


@app.route("/api/build-kit", methods=["POST"])
def api_build_kit():
    data = request.get_json(force=True, silent=True) or {}

    producer_name = (data.get("producer_name") or "").strip()
    world_text = (data.get("world_text") or "").strip()
    projects_root = (data.get("projects_root") or "").strip()
    selected_folders = data.get("selected_folders") or []
    library_roots_raw = (data.get("library_roots") or "").strip()
    output_root = (data.get("output_root") or "").strip()
    use_audio_analysis = bool(data.get("use_audio_analysis", True))
    use_audio_dedupe = bool(data.get("use_audio_dedupe", True))
    stash_mode = bool(data.get("stash_mode", False))

    if not producer_name:
        return jsonify({"error": "Missing producer name."}), 400
    if not projects_root or not Path(projects_root).is_dir():
        return jsonify({"error": f'Projects folder "{projects_root}" was not found.'}), 400
    if not output_root:
        return jsonify({"error": "Missing output folder."}), 400
    if not selected_folders:
        return jsonify({"error": "Select at least one folder to scan."}), 400

    proj_root = Path(projects_root)
    project_folders = [proj_root / name for name in selected_folders]

    flp_count = len(find_project_flps(project_folders))
    if flp_count == 0:
        return jsonify({"error": "No .flp files found in the selected folder(s)."}), 400
    if flp_count > MAX_FLPS_PER_REQUEST:
        return jsonify({
            "error": (
                f"{flp_count} .flp files selected — that's above the "
                f"{MAX_FLPS_PER_REQUEST} safety cap for one run. Select fewer folders."
            )
        }), 400

    library_roots = [
        Path(p.strip()) for p in library_roots_raw.split(";") if p.strip()
    ]
    library_roots = [p for p in library_roots if p.is_dir()]

    output_path = Path(output_root)
    output_path.mkdir(parents=True, exist_ok=True)

    try:
        result = build_drumkit(
            project_folders=project_folders,
            library_search_roots=library_roots,
            output_root=output_path,
            producer_name=producer_name,
            world_text=world_text,
            use_audio_analysis=use_audio_analysis,
            use_audio_dedupe=use_audio_dedupe,
            stash_mode=stash_mode,
        )
    except Exception as e:  # surface a clean error to the UI instead of a 500 stack trace
        return jsonify({"error": f"Build failed: {e}"}), 500

    categories_json = {}
    for category, cat_result in result.categories.items():
        categories_json[category] = {
            "folder": cat_result.folder,
            "tag": cat_result.tag,
            "count": len(cat_result.entries),
            "duplicates_skipped": cat_result.duplicates_skipped,
            "sounds": [
                {
                    "original_name": e.original_name,
                    "new_name": e.new_name,
                    "usage_count": e.usage_count,
                    "used_in": e.used_in,
                    "resolution_method": e.resolution_method,
                    "days_since_last_used": e.days_since_last_used,
                }
                for e in cat_result.entries
            ],
        }

    return jsonify({
        "kit_name": result.kit_name,
        "output_path": result.output_path,
        "stash_mode": stash_mode,
        "max_per_category": MAX_PER_CATEGORY,
        "total_unique": result.total_unique,
        "total_flps_scanned": result.total_flps_scanned,
        "total_flps_failed": result.total_flps_failed,
        "total_refs_found": result.total_refs_found,
        "total_unique_samples_resolved": result.total_unique_samples_resolved,
        "total_missing_refs": result.total_missing_refs,
        "unclassified_count": result.unclassified_count,
        "categories": categories_json,
    })


@app.route("/api/reveal-folder", methods=["POST"])
def api_reveal_folder():
    data = request.get_json(force=True, silent=True) or {}
    path = (data.get("path") or "").strip()
    if not path or not Path(path).exists():
        return jsonify({"error": "That folder doesn't exist."}), 400
    if sys.platform == "win32":
        subprocess.Popen(["explorer", path])
    return jsonify({"ok": True})


def main():
    # host must stay 127.0.0.1 (loopback-only) and debug must stay False —
    # debug mode's interactive traceback is a remote-code-execution
    # primitive if this port is ever reachable from anywhere else.
    app.run(host="127.0.0.1", port=PORT, debug=False)


if __name__ == "__main__":
    main()
