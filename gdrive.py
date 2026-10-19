"""Upload metafiles (EMF or WMF) to Google Drive as native Google Drawings, through the Drive API.

Drive converts a file at upload only when the request asks for it: the metadata names the Google type
(`mimeType` = Drawing) and the media part is declared `application/x-msmetafile`.  Declared as `image/emf`
the same bytes are stored as a plain file, and a file dropped into a Drive for desktop folder is never
converted.

Sign-in needs an OAuth client of type "Desktop app" from your own Google Cloud project (README.adoc).  The
client secret and the saved sign-in live in config_dir(), outside the repository.  Only sign-in needs
third-party packages (requirements-upload.txt); the Drive class works with any requests-style session.
"""
import json
import os
import re
import sys
import time
import uuid

API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
DRAWING = "application/vnd.google-apps.drawing"
FOLDER = "application/vnd.google-apps.folder"
METAFILE = "application/x-msmetafile"          # the declared type Drive converts, for WMF and EMF alike
SCOPE_FILE = "https://www.googleapis.com/auth/drive.file"   # only files this app created or was given
SCOPE_DRIVE = "https://www.googleapis.com/auth/drive"       # all files
MAX_UPLOAD = 5 * 1024 * 1024                   # largest multipart upload
APP_DIR = "visio-to-googledrawing"

SETUP_HELP = """\
Uploading needs an OAuth client of type "Desktop app" from your own Google Cloud project:
  1. In the Google Cloud console, create a project and enable the Google Drive API.
  2. Google Auth platform > Branding, then Audience (External, with your Google account added as a test user),
     then Data Access (add the Drive scope).
  3. Google Auth platform > Clients > Create client > Desktop app, then download the JSON.
  4. Save it as {path}
README.adoc has the steps in full."""


class SetupError(Exception):
    """Credentials are missing or unusable; the message says what to do."""


class DriveError(Exception):
    """A Drive call failed.  `status` is the HTTP status, or None when Drive was not reached."""

    def __init__(self, message, status=None, reason=None):
        super().__init__(message)
        self.status = status
        self.reason = reason


class ConversionError(DriveError):
    """Drive stored the upload as a plain file instead of converting it to a Drawing."""


# ---- where things are kept ---------------------------------------------------------------------------

def config_dir():
    """Folder for the client secret and the saved sign-in; VSDX_GDRIVE_DIR overrides it."""
    path = os.environ.get("VSDX_GDRIVE_DIR")
    if path:
        return path
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_DIR)


def secret_path():
    return os.path.join(config_dir(), "client_secret.json")


def token_path(scope):
    """One saved sign-in per scope, so switching between the two scopes does not sign you out."""
    return os.path.join(config_dir(), "token-drive.json" if scope == SCOPE_DRIVE else "token-drive-file.json")


# ---- sign-in -----------------------------------------------------------------------------------------

def read_client_secret(path):
    """The parsed client secret file, or a SetupError saying what is wrong with it."""
    if not os.path.isfile(path):
        raise SetupError(f"No Google client secret at {path}\n\n" + SETUP_HELP.format(path=path))
    try:
        with open(path, encoding="utf-8-sig") as f:      # utf-8-sig: some editors add a byte order mark
            config = json.load(f)
    except ValueError as e:
        raise SetupError(f"{path} is not valid JSON ({e}). Download the client secret again.")
    if not isinstance(config, dict) or "installed" not in config:
        kind = next(iter(config), "unknown") if isinstance(config, dict) and config else "unknown"
        raise SetupError(f"{path} holds a '{kind}' client. This script needs an OAuth client of type "
                         f"\"Desktop app\"; create one and download its JSON.")
    return config


def save_token(path, creds):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(creds.to_json())


def load_credentials(scope, secret_file=None, token_file=None, reauth=False, open_browser=True):
    """Credentials for `scope`: the saved sign-in (refreshed if needed), else a browser consent.

    While the OAuth consent screen is in "Testing" Google expires the saved sign-in after 7 days; the
    refresh then fails and the browser consent runs again."""
    from google.auth.exceptions import RefreshError, TransportError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow, WSGITimeoutError

    secret_file = secret_file or secret_path()
    token_file = token_file or token_path(scope)
    creds = None
    if not reauth and os.path.isfile(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, [scope])
        except (ValueError, KeyError):
            creds = None                                  # unreadable token: sign in again
    if creds and not creds.valid and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_token(token_file, creds)
        except RefreshError:
            print("Google no longer accepts the saved sign-in (it expires after 7 days while the app "
                  "is in Testing). Signing in again.", file=sys.stderr)
            creds = None
        except TransportError as e:
            raise DriveError(f"could not reach Google to refresh the sign-in: {e}") from e
    if creds and creds.valid:
        return creds
    flow = InstalledAppFlow.from_client_config(read_client_secret(secret_file), [scope])
    try:
        creds = flow.run_local_server(
            host="127.0.0.1", port=0, open_browser=open_browser, prompt="consent", timeout_seconds=300,
            authorization_prompt_message="Signing in to Google. If your browser does not open, go to\n{url}\n"
                                         "Google may warn that the app is unverified; it is your own "
                                         "client, so continue.")
    except WSGITimeoutError as e:
        raise DriveError("no answer from the browser within 5 minutes; run again to retry") from e
    save_token(token_file, creds)
    return creds


def authorised_session(creds):
    from google.auth.transport.requests import AuthorizedSession
    return AuthorizedSession(creds)


# ---- request pieces ----------------------------------------------------------------------------------

def q_escape(text):
    """Escape a string for a single-quoted Drive search query."""
    return text.replace("\\", "\\\\").replace("'", "\\'")


def parse_folder_id(text):
    """The folder id in a bare id or a drive.google.com folder link."""
    text = text.strip()
    for pattern in (r"/folders/([A-Za-z0-9_-]+)", r"[?&]id=([A-Za-z0-9_-]+)"):
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", text):
        return text
    raise ValueError(f"not a Drive folder id or link: {text!r}")


def multipart(metadata, media, media_type):
    """(body, Content-Type) of a multipart/related upload: JSON metadata first, then the media bytes."""
    boundary = "vsdx" + uuid.uuid4().hex
    while boundary.encode() in media:
        boundary = "vsdx" + uuid.uuid4().hex
    head = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(metadata)}\r\n"
            f"--{boundary}\r\nContent-Type: {media_type}\r\n\r\n").encode()
    return head + media + f"\r\n--{boundary}--\r\n".encode(), f"multipart/related; boundary={boundary}"


# ---- the Drive calls ---------------------------------------------------------------------------------

class Drive:
    """The few Drive v3 calls the upload needs.  `session` is anything shaped like requests.Session."""

    def __init__(self, session, api=API, upload=UPLOAD, timeout=60):
        self.session = session
        self.api = api
        self.upload = upload
        self.timeout = timeout

    def _call(self, method, url, **kw):
        """Decoded JSON of a Drive call.  Reads and PATCH retry on 429 and 5xx; a POST never does, because
        the first attempt may have created the file."""
        tries = 4 if method in ("GET", "PATCH") else 1
        for n in range(tries):
            try:
                r = self.session.request(method, url, timeout=self.timeout, **kw)
            except OSError as e:                          # requests' connection and timeout errors
                if n + 1 < tries:
                    time.sleep(2 ** n)
                    continue
                raise DriveError(f"could not reach Drive: {e}") from e
            if r.status_code in (429, 500, 502, 503, 504) and n + 1 < tries:
                time.sleep(2 ** n)
                continue
            break
        if r.status_code >= 400:
            try:
                err = r.json()["error"]
                message, reason = err.get("message", ""), (err.get("errors") or [{}])[0].get("reason")
            except (ValueError, KeyError, TypeError, AttributeError):
                message, reason = (r.text or "")[:200], None
            raise DriveError(f"Drive returned {r.status_code}: {message}", r.status_code, reason)
        return r.json() if r.content else {}

    def about(self):
        """The signed-in user and the conversions Drive supports on upload."""
        return self._call("GET", f"{self.api}/about",
                          params={"fields": "user(displayName,emailAddress),importFormats"})

    @staticmethod
    def imports_drawings(about):
        """True when `about` says an application/x-msmetafile upload can become a Drawing."""
        return DRAWING in (about.get("importFormats") or {}).get(METAFILE, [])

    def folder(self, folder_id):
        """{id, name, mimeType} of an existing folder; DriveError(404) if Drive cannot find it."""
        f = self._call("GET", f"{self.api}/files/{folder_id}",
                       params={"fields": "id,name,mimeType", "supportsAllDrives": "true"})
        if f.get("mimeType") != FOLDER:
            raise DriveError(f"{folder_id} is not a folder ({f.get('name')!r})")
        return f

    def find_drawings(self, title, folder_id=None):
        """Drawings called `title` in the folder (My Drive root when None) that this sign-in can see."""
        q = (f"name = '{q_escape(title)}' and mimeType = '{DRAWING}' and trashed = false "
             f"and '{folder_id or 'root'}' in parents")
        data = self._call("GET", f"{self.api}/files",
                          params={"q": q, "fields": "files(id,name,webViewLink)", "pageSize": 10,
                                  "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"})
        return data.get("files", [])

    def upload_drawing(self, path, title, folder_id=None):
        """Upload an EMF or WMF as a Google Drawing; {id, name, mimeType, webViewLink, parents}.

        If Drive keeps it as a plain file the new file is trashed (it is the only file ever trashed here)
        and ConversionError is raised."""
        size = os.path.getsize(path)
        if size > MAX_UPLOAD:
            raise DriveError(f"{os.path.basename(path)} is {size:,} bytes; a simple upload is limited to "
                             f"{MAX_UPLOAD:,}")
        with open(path, "rb") as f:
            media = f.read()
        metadata = {"name": title, "mimeType": DRAWING}
        if folder_id:
            metadata["parents"] = [folder_id]
        body, content_type = multipart(metadata, media, METAFILE)
        made = self._call("POST", self.upload, data=body, headers={"Content-Type": content_type},
                          params={"uploadType": "multipart", "supportsAllDrives": "true",
                                  "fields": "id,name,mimeType,webViewLink,parents"})
        if made.get("mimeType") != DRAWING:
            self.trash(made["id"])
            raise ConversionError(f"Drive stored {title!r} as {made.get('mimeType')!r} instead of converting "
                                  f"it to a Drawing; the stray file was moved to the trash")
        return made

    def trash(self, file_id):
        self._call("PATCH", f"{self.api}/files/{file_id}", params={"fields": "id,trashed"},
                   json={"trashed": True})
