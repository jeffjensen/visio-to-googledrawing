"""Convert Visio .vsdx files to EMF and upload every page to Google Drive as a native Google Drawing.

usage: .venv\\Scripts\\python.exe -I vsdx2drawing.py INPUT [INPUT ...] [--folder ID_OR_URL] [--full-drive]
           [--allow-duplicates] [--dry-run] [--emf-dir DIR] [--page NAME ...] [--prefix P] [--crop IN]
           [--text-mode importer|outline] [--upi N] [--client-secret FILE] [--no-browser]
       .venv\\Scripts\\python.exe -I vsdx2drawing.py --check | --auth [--full-drive]

INPUT is a .vsdx file (converted with convert.py first), an .emf or .wmf file (uploaded as it is), or a
folder of .emf and .wmf files.  A Drawing is named after its file: "<vsdx name> - <page>" for converted pages,
or just "<vsdx name>" for a one-page file converted whole.
A Drawing with that name already in the folder is skipped unless --allow-duplicates is given; the check only
sees files this sign-in can see, which under the default access means files uploaded by this script.

--check signs in and reports the account, the access granted and whether Drive converts metafile uploads.
--auth signs in again from scratch.  The Google setup is in README.adoc.

Exit status: 0 when every file was uploaded or already there; 1 when the converter skipped a page, an upload
failed or there was nothing to upload; 2 for a bad command line or missing sign-in setup.
"""
import argparse
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gdrive  # noqa: E402

METAFILES = (".emf", ".wmf")


class UsageError(Exception):
    pass


def title_of(path):
    return os.path.splitext(os.path.basename(path))[0]


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Convert Visio .vsdx files to EMF and upload every page to Google Drive as a native "
                    "Google Drawing.")
    ap.add_argument("inputs", nargs="*", metavar="INPUT",
                    help="a .vsdx file, an .emf or .wmf file, or a folder of .emf and .wmf files")
    ap.add_argument("--folder", metavar="ID_OR_URL", help="Drive folder for the Drawings (default: My Drive root)")
    ap.add_argument("--full-drive", action="store_true",
                    help="ask for access to all of your Drive; needed for a folder that already exists")
    ap.add_argument("--allow-duplicates", action="store_true",
                    help="upload even if a Drawing with that name is already in the folder")
    ap.add_argument("--dry-run", action="store_true",
                    help="convert and list what would be uploaded; no sign-in, no upload")
    ap.add_argument("--emf-dir", metavar="DIR",
                    help="keep the converted EMFs here, one subfolder per .vsdx (default: a temporary folder)")
    ap.add_argument("--check", action="store_true", help="sign in and report what Drive will do with a metafile")
    ap.add_argument("--auth", action="store_true", help="sign in to Google again from scratch and exit")
    ap.add_argument("--client-secret", metavar="FILE",
                    help="the Desktop-app client secret JSON (default: %s)" % gdrive.secret_path())
    ap.add_argument("--no-browser", action="store_true", help="print the sign-in link instead of opening a browser")
    conv = ap.add_argument_group("converter options, for .vsdx inputs (see convert.py)")
    conv.add_argument("--page", action="append", metavar="NAME", help="only this page; repeat for several")
    conv.add_argument("--prefix", metavar="P", help="name the pages 'P - page' instead of the file's name")
    conv.add_argument("--crop", type=float, metavar="MARGIN_IN", help="crop to content plus this margin (paper inches)")
    conv.add_argument("--text-mode", choices=["importer", "outline"])
    conv.add_argument("--upi", type=int, metavar="N", help="output units per paper inch (0 = automatic)")
    a = ap.parse_args(argv)
    if a.check and a.auth:
        ap.error("choose --check or --auth, not both")
    if (a.check or a.auth) and a.inputs:
        ap.error("--check and --auth take no INPUT")
    if not (a.check or a.auth or a.inputs):
        ap.error("give at least one INPUT, or --check or --auth")
    return a


def converter_args(a):
    args = []
    for page in a.page or []:
        args += ["--page", page]
    if a.prefix is not None:
        args += ["--prefix", a.prefix]
    if a.crop is not None:
        args += ["--crop", str(a.crop)]
    if a.text_mode:
        args += ["--text-mode", a.text_mode]
    if a.upi:
        args += ["--upi", str(a.upi)]
    return args


def collect(a, work):
    """([(path, title)], problems): the metafiles to upload, after converting any .vsdx inputs into `work`."""
    items, problems = [], 0
    for src in a.inputs:
        low = src.lower()
        if os.path.isdir(src):
            names = sorted(n for n in os.listdir(src) if n.lower().endswith(METAFILES))
            if not names:
                print(f"{src}: no .emf or .wmf files in this folder", file=sys.stderr)
                problems += 1
            items += [(os.path.join(src, n), title_of(n)) for n in names]
        elif os.path.isfile(src) and low.endswith(METAFILES):
            items.append((src, title_of(src)))
        elif os.path.isfile(src) and low.endswith(".vsdx"):
            out = os.path.join(work, title_of(src))
            if os.path.isdir(out) and os.listdir(out):
                raise UsageError(f"{out} is not empty; pick another --emf-dir or empty it")
            cmd = [sys.executable, "-I", os.path.join(HERE, "convert.py"), src, out] + converter_args(a)
            code = subprocess.run(cmd).returncode
            if code != 0:                                # a skipped page, or unusable input
                problems += 1
            made = sorted(n for n in os.listdir(out) if n.lower().endswith(".emf")) if os.path.isdir(out) else []
            # a one-page file is named after the file alone
            single = len(made) == 1 and code == 0 and not a.page and a.prefix is None
            items += [(os.path.join(out, n), title_of(src) if single else title_of(n)) for n in made]
        else:
            raise UsageError(f"{src}: expected a .vsdx, .emf or .wmf file or a folder of them")
    return items, problems


def show(items):
    width = max(len(title) for _, title in items)
    for path, title in items:
        print(f"{title:<{width}}  {os.path.getsize(path):>9,} bytes  {path}")


def connect(a, scope, secret):
    creds = gdrive.load_credentials(scope, secret, open_browser=not a.no_browser)
    return gdrive.Drive(gdrive.authorised_session(creds))


def require_setup(scope, secret):
    """Fail before converting anything if there is neither a saved sign-in nor a usable client secret."""
    if not os.path.isfile(gdrive.token_path(scope)):
        gdrive.read_client_secret(secret)


def resolve_folder(drive, text, full_drive):
    try:
        folder_id = gdrive.parse_folder_id(text)
    except ValueError as e:
        raise UsageError(str(e))
    try:
        return drive.folder(folder_id)
    except gdrive.DriveError as e:
        if e.status != 404:
            raise
        if full_drive:
            raise gdrive.DriveError(f"Drive cannot find folder {folder_id}: check the id, and that your "
                                    f"account can open it", 404) from e
        raise gdrive.DriveError(
            f"Drive cannot find folder {folder_id}. Either the id is wrong, or the default access (only files "
            f"this script created) does not cover it. For a folder that already exists, re-run with "
            f"--full-drive.", 404) from e


def check(drive, a, scope):
    about = drive.about()
    user = about.get("user", {})
    ok = drive.imports_drawings(about)
    print(f"signed in as      {user.get('displayName', '?')} <{user.get('emailAddress', '?')}>")
    print("access            " + ("all of your Drive (drive scope)" if scope == gdrive.SCOPE_DRIVE
                                  else "files this script creates (drive.file scope)"))
    print("metafile import   " + ("yes, Drive converts application/x-msmetafile uploads to Google Drawings" if ok
                                  else "NO, Drive does not list application/x-msmetafile as convertible to a "
                                       "Drawing, so uploads would stay plain files"))
    if a.folder:
        folder = resolve_folder(drive, a.folder, a.full_drive)
        print(f"folder            {folder['name']} ({folder['id']})")
    return 0 if ok else 1


def upload_items(drive, items, folder_id=None, allow_duplicates=False, out=print):
    """Upload each (path, title).  Returns (uploaded, already_there, failed, stopped).

    Stops early when the rest would fail the same way: Drive not converting, or refusing the request."""
    done = there = failed = 0
    for path, title in items:
        try:
            if not allow_duplicates:
                found = drive.find_drawings(title, folder_id)
                if found:
                    out(f"exists     {title}   {found[0].get('webViewLink', '')}")
                    there += 1
                    continue
            made = drive.upload_drawing(path, title, folder_id)
        except gdrive.ConversionError as e:
            out(f"FAILED     {title}: {e}")
            out("Stopping: Drive is not converting these uploads. Run --check.")
            return done, there, failed + 1, True
        except gdrive.DriveError as e:
            out(f"FAILED     {title}: {e}")
            failed += 1
            if e.status in (401, 403):
                out("Stopping: Drive refused the request, and the remaining files would be refused too.")
                return done, there, failed, True
            continue
        out(f"uploaded   {title}   {made.get('webViewLink', '')}")
        done += 1
    return done, there, failed, False


def run(a):
    scope = gdrive.SCOPE_DRIVE if a.full_drive else gdrive.SCOPE_FILE
    secret = a.client_secret or gdrive.secret_path()
    if a.auth:
        gdrive.load_credentials(scope, secret, reauth=True, open_browser=not a.no_browser)
        print(f"Signed in. The sign-in is saved in {gdrive.token_path(scope)}")
        return 0
    if a.check:
        return check(connect(a, scope, secret), a, scope)
    if not a.dry_run:
        require_setup(scope, secret)
    with tempfile.TemporaryDirectory(prefix="vsdx2drawing-") as tmp:
        items, problems = collect(a, a.emf_dir or tmp)
        if not items:
            print("nothing to upload", file=sys.stderr)
            return 1
        if a.dry_run:
            show(items)
            return 1 if problems else 0
        drive = connect(a, scope, secret)
        folder_id = resolve_folder(drive, a.folder, a.full_drive)["id"] if a.folder else None
        done, there, failed, stopped = upload_items(drive, items, folder_id, a.allow_duplicates)
    summary = f"{done} uploaded, {there} already there, {failed} failed"
    left = len(items) - done - there - failed
    if left:
        summary += f", {left} not attempted"
    print(summary)
    if a.emf_dir:
        print(f"EMF files kept in {a.emf_dir}")
    return 1 if (failed or stopped or problems) else 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    a = parse_args(argv)
    try:
        return run(a)
    except (UsageError, gdrive.SetupError) as e:
        print(e, file=sys.stderr)
        return 2
    except gdrive.DriveError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except ImportError as e:
        if "google" in str(e) or "requests" in str(e):
            print(f"{e}\nInstall the upload packages: .venv\\Scripts\\python.exe -m pip install "
                  f"-r requirements-upload.txt", file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    sys.exit(main())
