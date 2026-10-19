"""Offline tests for gdrive.py and vsdx2drawing.py.  A fake Drive stands in for the network and converts an
upload only the way the real service does: the metadata must ask for the Drawing type and the media part must
be declared application/x-msmetafile.

Run (the sign-in tests need requirements-upload.txt):
    .venv\\Scripts\\python.exe -I -B -m unittest discover -s tests -v
"""
import datetime
import io
import os
import re
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from json import dumps as json_dumps, loads as json_loads
from unittest import mock
from urllib.parse import parse_qsl, urlparse

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import emf as E             # noqa: E402
import gdrive               # noqa: E402
import vsdx2drawing         # noqa: E402

try:
    import google_auth_oauthlib   # noqa: F401
    import requests
    HAVE_GOOGLE = True
except ImportError:
    HAVE_GOOGLE = False

METAFILE = "application/x-msmetafile"      # spelled out here, not read from gdrive, so a change there is caught
DRAWING = "application/vnd.google-apps.drawing"
FOLDER_TYPE = "application/vnd.google-apps.folder"
FOLDER_ID = "FOLDERID12345"
SECRET = {"installed": {"client_id": "1-x.apps.googleusercontent.com", "project_id": "p",
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token", "client_secret": "s",
                        "redirect_uris": ["http://localhost"]}}


def tiny_emf(n=0):
    m = E.Emf(1000, 800, units_per_inch=100)
    m.pen("#000000", 3)
    m.brush(None)
    m.rectangle(100 + n, 100, 900, 700)
    return m.build()


def split_multipart(body, content_type):
    """[(headers, content)] by the RFC 2046 rules: every delimiter is CRLF + '--' + boundary."""
    boundary = re.fullmatch(r"multipart/related; boundary=(\S+)", content_type).group(1).encode()
    chunks = (b"\r\n" + body).split(b"\r\n--" + boundary)
    assert chunks[0] == b"", "text before the first delimiter"
    assert chunks[-1] == b"--\r\n", "closing delimiter"
    parts = []
    for chunk in chunks[1:-1]:
        assert chunk.startswith(b"\r\n")
        head, _, content = chunk[2:].partition(b"\r\n\r\n")
        parts.append((dict(line.split(": ", 1) for line in head.decode().split("\r\n")), content))
    return parts


class FakeResponse:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body
        self.content = json_dumps(body).encode() if body is not None else b""
        self.text = self.content.decode()

    def json(self):
        return self._body


class FakeDrive:
    """Answers the Drive calls gdrive makes."""

    def __init__(self, converts=True, folders=None, existing=None, upload_status=200, import_formats=None):
        self.calls, self.uploads, self.trashed = [], [], []
        self.converts = converts
        self.folders = folders if folders is not None else {FOLDER_ID: "Drawings"}
        self.existing = existing or []          # [{"id", "name", "parent"}] Drawings already in Drive
        self.upload_status = upload_status
        self.import_formats = ({METAFILE: [DRAWING]} if import_formats is None
                               else import_formats)
        self.n = 0

    def request(self, method, url, params=None, data=None, headers=None, json=None, timeout=None):
        self.calls.append((method, url, params))
        if method == "GET" and url.endswith("/about"):
            return FakeResponse(200, {"user": {"displayName": "Test User", "emailAddress": "t@example.com"},
                                      "importFormats": self.import_formats})
        m = re.search(r"/files/([^/?]+)$", url)
        if method == "GET" and m:
            if m.group(1) in self.folders:
                return FakeResponse(200, {"id": m.group(1), "name": self.folders[m.group(1)],
                                          "mimeType": FOLDER_TYPE})
            return FakeResponse(404, {"error": {"code": 404, "message": f"File not found: {m.group(1)}.",
                                                "errors": [{"reason": "notFound"}]}})
        if method == "GET" and url.endswith("/files"):
            q = params["q"]
            hits = [{"id": e["id"], "name": e["name"], "webViewLink": f"https://docs.google.com/{e['id']}"}
                    for e in self.existing
                    if f"name = '{gdrive.q_escape(e['name'])}'" in q and f"'{e.get('parent', 'root')}' in parents" in q
                    and DRAWING in q and "trashed = false" in q]
            return FakeResponse(200, {"files": hits})
        if method == "POST" and url == gdrive.UPLOAD:
            assert params["uploadType"] == "multipart"
            if self.upload_status != 200:
                return FakeResponse(self.upload_status, {"error": {"message": "refused", "errors": [{"reason": "x"}]}})
            (head1, meta_json), (head2, media) = split_multipart(data, headers["Content-Type"])
            assert head1 == {"Content-Type": "application/json; charset=UTF-8"}
            meta = json_loads(meta_json)
            self.uploads.append((meta, head2["Content-Type"], media))
            self.n += 1
            converted = (self.converts and meta.get("mimeType") == DRAWING
                         and head2["Content-Type"] == METAFILE)
            return FakeResponse(200, {"id": f"new{self.n}", "name": meta["name"],
                                      "mimeType": DRAWING if converted else head2["Content-Type"],
                                      "webViewLink": f"https://docs.google.com/drawings/d/new{self.n}/edit",
                                      "parents": meta.get("parents", [])})
        if method == "PATCH" and m:
            assert json == {"trashed": True}
            self.trashed.append(m.group(1))
            return FakeResponse(200, {"id": m.group(1), "trashed": True})
        raise AssertionError(f"unexpected call {method} {url}")


class Scripted:
    """A session that hands back the given responses, or raises the given exceptions, in order."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class TempDirCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name

    def write(self, name, data):
        path = os.path.join(self.dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    @staticmethod
    def read_json(path):
        with open(path, encoding="utf-8") as f:
            return json_loads(f.read())


class MultipartTests(TempDirCase):
    def test_binary_payload_survives_the_multipart_encoding_byte_for_byte(self):
        nasty = (b"\x00\r\n--\r\n--vsdx\r\n\xff\xfe" * 40) + bytes(range(256)) + b"\r\n"
        body, ctype = gdrive.multipart({"name": "x"}, nasty, METAFILE)
        (h1, meta), (h2, media) = split_multipart(body, ctype)
        self.assertEqual(json_loads(meta), {"name": "x"})
        self.assertEqual(h2, {"Content-Type": METAFILE})
        self.assertEqual(media, nasty)

    def test_boundary_is_never_found_in_the_payload(self):
        class Id:
            def __init__(self, hex):
                self.hex = hex
        media = b"xx vsdx" + b"a" * 32 + b" xx"
        with mock.patch("gdrive.uuid.uuid4", side_effect=[Id("a" * 32), Id("b" * 32)]):
            body, ctype = gdrive.multipart({}, media, METAFILE)
        self.assertIn("vsdx" + "b" * 32, ctype)
        self.assertEqual(split_multipart(body, ctype)[1][1], media)

    def test_parses_with_the_standard_library_mime_parser_too(self):
        import email
        body, ctype = gdrive.multipart({"name": "x", "mimeType": DRAWING}, tiny_emf(), METAFILE)
        msg = email.message_from_bytes(b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + body)
        meta, media = msg.get_payload()
        self.assertEqual(meta.get_content_type(), "application/json")
        self.assertEqual(media.get_content_type(), METAFILE)


class HelperTests(unittest.TestCase):
    def test_folder_ids_and_links(self):
        for text, want in [
            ("https://drive.google.com/drive/folders/0B-AbCdEfGhIjKlMnOpQrStUv?usp=sharing", "0B-AbCdEfGhIjKlMnOpQrStUv"),
            ("https://drive.google.com/drive/u/0/folders/1AbC_dEf-GhIjKlMnOp", "1AbC_dEf-GhIjKlMnOp"),
            ("https://drive.google.com/open?id=1AbCdEfGhIjK", "1AbCdEfGhIjK"),
            ("  0B-AbCdEfGhIjKlMnOpQrStUv ", "0B-AbCdEfGhIjKlMnOpQrStUv"),
        ]:
            self.assertEqual(gdrive.parse_folder_id(text), want)
        for bad in ("my folder", "","https://example.com/"):
            with self.assertRaises(ValueError):
                gdrive.parse_folder_id(bad)

    def test_scopes_and_endpoints_are_the_documented_ones(self):
        self.assertEqual(gdrive.SCOPE_FILE, "https://www.googleapis.com/auth/drive.file")
        self.assertEqual(gdrive.SCOPE_DRIVE, "https://www.googleapis.com/auth/drive")
        self.assertEqual(gdrive.API, "https://www.googleapis.com/drive/v3")
        self.assertEqual(gdrive.UPLOAD, "https://www.googleapis.com/upload/drive/v3/files")
        self.assertNotEqual(gdrive.token_path(gdrive.SCOPE_FILE), gdrive.token_path(gdrive.SCOPE_DRIVE))

    def test_query_escaping(self):
        self.assertEqual(gdrive.q_escape("O'Brien \\ page"), "O\\'Brien \\\\ page")

    def test_import_support_is_read_from_about(self):
        yes = {"importFormats": {METAFILE: [DRAWING, "other"]}}
        self.assertTrue(gdrive.Drive.imports_drawings(yes))
        self.assertFalse(gdrive.Drive.imports_drawings({"importFormats": {METAFILE: ["other"]}}))
        self.assertFalse(gdrive.Drive.imports_drawings({"importFormats": {}}))
        self.assertFalse(gdrive.Drive.imports_drawings({}))


class UploadTests(TempDirCase):
    def test_emf_and_wmf_are_both_declared_as_msmetafile_and_asked_to_become_drawings(self):
        # image/emf would be stored as a plain file, so the declared type is the
        # regression that matters most
        fake = FakeDrive()
        drive = gdrive.Drive(fake)
        emf_bytes = tiny_emf()
        wmf_bytes = b"\xd7\xcd\xc6\x9a" + bytes(range(100))
        for name, data in (("a - Overview.emf", emf_bytes), ("a - Details.wmf", wmf_bytes)):
            made = drive.upload_drawing(self.write(name, data), os.path.splitext(name)[0])
            self.assertEqual(made["mimeType"], DRAWING)
        self.assertEqual([u[1] for u in fake.uploads], [METAFILE, METAFILE])
        self.assertEqual([u[0]["mimeType"] for u in fake.uploads], [DRAWING, DRAWING])
        self.assertEqual([u[2] for u in fake.uploads], [emf_bytes, wmf_bytes])
        self.assertEqual([u[0]["name"] for u in fake.uploads], ["a - Overview", "a - Details"])
        self.assertTrue(all("parents" not in u[0] for u in fake.uploads))

    def test_folder_goes_in_the_metadata(self):
        fake = FakeDrive()
        gdrive.Drive(fake).upload_drawing(self.write("p.emf", tiny_emf()), "p", FOLDER_ID)
        self.assertEqual(fake.uploads[0][0]["parents"], [FOLDER_ID])

    def test_a_failed_conversion_trashes_only_the_file_just_made(self):
        fake = FakeDrive(converts=False)
        with self.assertRaises(gdrive.ConversionError) as cm:
            gdrive.Drive(fake).upload_drawing(self.write("p.emf", tiny_emf()), "p")
        self.assertEqual(fake.trashed, ["new1"])
        self.assertIn("instead of converting it to a Drawing", str(cm.exception))
        self.assertEqual([c[0] for c in fake.calls], ["POST", "PATCH"])

    def test_oversize_file_is_refused_before_any_request(self):
        fake = FakeDrive()
        path = self.write("big.emf", b"\0" * (gdrive.MAX_UPLOAD + 1))
        with self.assertRaises(gdrive.DriveError):
            gdrive.Drive(fake).upload_drawing(path, "big")
        self.assertEqual(fake.calls, [])

    def test_duplicate_search_is_scoped_escaped_and_ignores_the_trash(self):
        fake = FakeDrive()
        gdrive.Drive(fake).find_drawings("O'Brien \\ page", FOLDER_ID)
        q = fake.calls[0][2]["q"]
        self.assertIn("name = 'O\\'Brien \\\\ page'", q)
        self.assertIn(f"'{FOLDER_ID}' in parents", q)
        self.assertIn("trashed = false", q)
        self.assertIn(f"mimeType = '{DRAWING}'", q)
        gdrive.Drive(fake).find_drawings("x")
        self.assertIn("'root' in parents", fake.calls[1][2]["q"])

    def test_error_bodies_become_drive_errors(self):
        with self.assertRaises(gdrive.DriveError) as cm:
            gdrive.Drive(FakeDrive()).folder("nope-nope-nope")
        self.assertEqual(cm.exception.status, 404)
        self.assertEqual(cm.exception.reason, "notFound")
        self.assertIn("File not found", str(cm.exception))

    def test_reads_are_retried_but_an_upload_never_is(self):
        with mock.patch("gdrive.time.sleep"):
            s = Scripted(FakeResponse(503, {}), FakeResponse(503, {}), FakeResponse(200, {"files": []}))
            self.assertEqual(gdrive.Drive(s).find_drawings("x"), [])
            self.assertEqual(len(s.calls), 3)
            s = Scripted(FakeResponse(503, {"error": {"message": "busy"}}), FakeResponse(200, {"id": "dup"}))
            with self.assertRaises(gdrive.DriveError):
                gdrive.Drive(s).upload_drawing(self.write("p.emf", tiny_emf()), "p")
            self.assertEqual(len(s.calls), 1)

    def test_network_failure_is_reported_as_unreachable(self):
        with mock.patch("gdrive.time.sleep"):
            with self.assertRaises(gdrive.DriveError) as cm:
                gdrive.Drive(Scripted(*[OSError("boom")] * 4)).about()
        self.assertIn("could not reach Drive", str(cm.exception))


@unittest.skipUnless(HAVE_GOOGLE, "needs requirements-upload.txt")
class WireTests(TempDirCase):
    def test_requests_sends_the_upload_intact_to_a_real_http_server(self):
        seen = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                seen["path"], seen["ctype"] = self.path, self.headers["Content-Type"]
                seen["body"] = self.rfile.read(int(self.headers["Content-Length"]))
                out = json_dumps({"id": "w1", "name": "x", "mimeType": DRAWING, "webViewLink": "u"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        session = requests.Session()
        session.trust_env = False                        # stay on localhost whatever proxy the machine uses
        drive = gdrive.Drive(session, api=base + "/drive/v3", upload=base + "/upload/drive/v3/files")
        data = tiny_emf()
        drive.upload_drawing(self.write("p.emf", data), "p", FOLDER_ID)
        self.assertIn("uploadType=multipart", seen["path"])
        (h1, meta), (h2, media) = split_multipart(seen["body"], seen["ctype"])
        self.assertEqual(json_loads(meta), {"name": "p", "mimeType": DRAWING, "parents": [FOLDER_ID]})
        self.assertEqual(h2["Content-Type"], METAFILE)
        self.assertEqual(media, data)


@unittest.skipUnless(HAVE_GOOGLE, "needs requirements-upload.txt")
class SignInTests(TempDirCase):
    def credentials(self, expires_in_hours):
        from google.oauth2.credentials import Credentials
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        return Credentials(token="t", refresh_token="r", token_uri="https://oauth2.googleapis.com/token",
                           client_id="c", client_secret="s", scopes=[gdrive.SCOPE_FILE],
                           expiry=now + datetime.timedelta(hours=expires_in_hours))

    class FakeFlow:
        def __init__(self, creds):
            self.creds, self.kwargs = creds, None

        def run_local_server(self, **kw):
            self.kwargs = kw
            return self.creds

    def test_missing_client_secret_explains_the_setup(self):
        path = os.path.join(self.dir, "nope.json")
        with self.assertRaises(gdrive.SetupError) as cm:
            gdrive.read_client_secret(path)
        self.assertIn(path, str(cm.exception))
        self.assertIn("Desktop app", str(cm.exception))

    def test_client_secret_with_a_byte_order_mark_is_read(self):
        path = self.write("s.json", b"\xef\xbb\xbf" + json_dumps(SECRET).encode())
        self.assertEqual(gdrive.read_client_secret(path), SECRET)

    def test_a_web_client_or_bad_json_is_rejected_with_advice(self):
        with self.assertRaises(gdrive.SetupError) as cm:
            gdrive.read_client_secret(self.write("w.json", json_dumps({"web": {}})))
        self.assertIn("'web'", str(cm.exception))
        self.assertIn("Desktop app", str(cm.exception))
        with self.assertRaises(gdrive.SetupError):
            gdrive.read_client_secret(self.write("bad.json", "not json"))

    def test_the_authorisation_request_uses_pkce_the_right_scope_and_a_loopback_redirect(self):
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_config(SECRET, [gdrive.SCOPE_FILE])
        flow.redirect_uri = "http://127.0.0.1:5555/"
        url, _ = flow.authorization_url(access_type="offline", prompt="consent")
        q = dict(parse_qsl(urlparse(url).query))
        self.assertEqual(q["scope"], gdrive.SCOPE_FILE)
        self.assertEqual(q["code_challenge_method"], "S256")
        self.assertIn("code_challenge", q)
        self.assertTrue(q["redirect_uri"].startswith("http://127.0.0.1:"))

    def test_consent_runs_on_the_loopback_address_and_the_token_is_saved(self):
        secret = self.write("s.json", json_dumps(SECRET))
        token = os.path.join(self.dir, "cfg", "token.json")
        flow = self.FakeFlow(self.credentials(1))
        with mock.patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_config", return_value=flow):
            got = gdrive.load_credentials(gdrive.SCOPE_FILE, secret_file=secret, token_file=token, open_browser=False)
        self.assertEqual((flow.kwargs["host"], flow.kwargs["port"], flow.kwargs["prompt"], flow.kwargs["open_browser"]),
                         ("127.0.0.1", 0, "consent", False))
        self.assertEqual(self.read_json(token)["refresh_token"], "r")
        self.assertEqual(got.token, "t")

    def test_a_saved_sign_in_is_reused_without_asking_again(self):
        token = self.write("token.json", self.credentials(1).to_json())
        with mock.patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_config", side_effect=AssertionError):
            got = gdrive.load_credentials(gdrive.SCOPE_FILE, secret_file=os.path.join(self.dir, "none.json"),
                                          token_file=token)
        self.assertTrue(got.valid)

    def test_a_refused_refresh_falls_back_to_consent(self):
        from google.auth.exceptions import RefreshError
        secret = self.write("s.json", json_dumps(SECRET))
        token = self.write("token.json", self.credentials(-1).to_json())
        fresh = self.credentials(1)
        fresh.token = "new"
        flow = self.FakeFlow(fresh)
        err = io.StringIO()
        with mock.patch("google.oauth2.credentials.Credentials.refresh", side_effect=RefreshError("invalid_grant")), \
                mock.patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_config", return_value=flow), \
                redirect_stderr(err):
            got = gdrive.load_credentials(gdrive.SCOPE_FILE, secret_file=secret, token_file=token)
        self.assertEqual(got.token, "new")
        self.assertIsNotNone(flow.kwargs)
        self.assertIn("no longer accepts", err.getvalue())
        self.assertEqual(self.read_json(token)["token"], "new")


class CliTests(TempDirCase):
    def run_cli(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = vsdx2drawing.main(args)
        return code, out.getvalue(), err.getvalue()

    def run_upload(self, args, fake, full_drive=False):
        self.write("token-drive.json" if full_drive else "token-drive-file.json", "{}")
        with mock.patch.dict(os.environ, {"VSDX_GDRIVE_DIR": self.dir}), \
                mock.patch.object(vsdx2drawing.gdrive, "load_credentials", return_value=object()), \
                mock.patch.object(vsdx2drawing.gdrive, "authorised_session", return_value=fake):
            return self.run_cli(args)

    def pages(self, *names):
        return [self.write(f"in/{n}", tiny_emf(i)) for i, n in enumerate(names)]

    def test_dry_run_lists_a_folder_of_metafiles_and_ignores_other_files(self):
        self.pages("a - Overview.emf", "a - Details.wmf")
        self.write("in/notes.txt", "x")
        code, out, _ = self.run_cli(["--dry-run", os.path.join(self.dir, "in")])
        self.assertEqual(code, 0)
        self.assertIn("a - Overview", out)
        self.assertIn("a - Details", out)
        self.assertNotIn("notes", out)

    def test_nothing_to_upload_and_unsupported_input(self):
        os.makedirs(os.path.join(self.dir, "empty"))
        code, _, err = self.run_cli(["--dry-run", os.path.join(self.dir, "empty")])
        self.assertEqual(code, 1)
        self.assertIn("no .emf or .wmf", err)
        code, _, err = self.run_cli(["--dry-run", self.write("x.txt", "x")])
        self.assertEqual(code, 2)
        self.assertIn("expected a .vsdx", err)

    def test_conflicting_options_are_a_usage_error(self):
        for args in (["--check", "--auth"], ["--check", "x.emf"], []):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
                vsdx2drawing.parse_args(args)
            self.assertEqual(cm.exception.code, 2)

    def test_a_vsdx_is_converted_with_the_converter_options_and_its_pages_are_listed(self):
        src = self.write("diagram.vsdx", "zip")
        calls = []

        def fake_convert(cmd, **kw):
            calls.append(cmd)
            out = cmd[4]
            os.makedirs(out, exist_ok=True)
            for name in ("diagram - Overview.emf", "diagram - Details.emf"):
                with open(os.path.join(out, name), "wb") as f:
                    f.write(tiny_emf())
            return mock.Mock(returncode=1)               # the converter skipped a page

        with mock.patch.object(vsdx2drawing.subprocess, "run", side_effect=fake_convert):
            code, out, _ = self.run_cli(["--dry-run", src, "--page", "Overview", "--page", "Details", "--crop", "0.5",
                                         "--text-mode", "outline"])
        cmd = calls[0]
        self.assertEqual(cmd[1], "-I")
        self.assertTrue(cmd[2].endswith("convert.py"))
        self.assertEqual(cmd[3], src)
        self.assertEqual(cmd[5:], ["--page", "Overview", "--page", "Details", "--crop", "0.5", "--text-mode", "outline"])
        self.assertIn("diagram - Overview", out)
        self.assertIn("diagram - Details", out)
        self.assertEqual(code, 1)                        # a skipped page makes the run fail even though pages were found

    def test_a_one_page_file_converted_whole_is_named_after_the_file_alone(self):
        src = self.write("single-page.vsdx", "zip")

        def convert(returncode):
            def fake(cmd, **kw):
                os.makedirs(cmd[4], exist_ok=True)
                with open(os.path.join(cmd[4], "single-page - Page-1.emf"), "wb") as f:
                    f.write(tiny_emf())
                return mock.Mock(returncode=returncode)
            return fake

        def titles(args, returncode=0):
            work = tempfile.mkdtemp(dir=self.dir)
            with mock.patch.object(vsdx2drawing.subprocess, "run", side_effect=convert(returncode)):
                items, _ = vsdx2drawing.collect(vsdx2drawing.parse_args(args), work)
            return [t for _, t in items]

        self.assertEqual(titles(["--dry-run", src]), ["single-page"])
        self.assertEqual(titles(["--dry-run", src, "--page", "Page-1"]), ["single-page - Page-1"])
        self.assertEqual(titles(["--dry-run", src, "--prefix", "set"]), ["single-page - Page-1"])
        self.assertEqual(titles(["--dry-run", src], returncode=1), ["single-page - Page-1"])

    def test_upload_to_a_folder_then_a_second_run_skips_what_is_already_there(self):
        paths = self.pages("a - Overview.emf", "a - Details.emf")
        fake = FakeDrive()
        code, out, _ = self.run_upload(paths + ["--folder", f"https://drive.google.com/drive/folders/{FOLDER_ID}"], fake)
        self.assertEqual(code, 0)
        self.assertIn("2 uploaded, 0 already there, 0 failed", out)
        self.assertEqual([u[0]["parents"] for u in fake.uploads], [[FOLDER_ID], [FOLDER_ID]])
        self.assertIn("uploaded   a - Overview   https://docs.google.com/drawings/d/new1/edit", out)

        again = FakeDrive(existing=[{"id": "e1", "name": "a - Overview", "parent": FOLDER_ID},
                                    {"id": "e2", "name": "a - Details", "parent": FOLDER_ID}])
        code, out, _ = self.run_upload(paths + ["--folder", FOLDER_ID], again)
        self.assertEqual(code, 0)
        self.assertEqual(again.uploads, [])
        self.assertIn("exists     a - Overview", out)
        self.assertIn("0 uploaded, 2 already there", out)

        code, out, _ = self.run_upload(paths + ["--folder", FOLDER_ID, "--allow-duplicates"], again)
        self.assertEqual(len(again.uploads), 2)

    def test_no_folder_means_the_my_drive_root(self):
        fake = FakeDrive()
        self.run_upload(self.pages("a.emf"), fake)
        self.assertNotIn("parents", fake.uploads[0][0])
        self.assertIn("'root' in parents", [c for c in fake.calls if c[1].endswith("/files")][0][2]["q"])

    def test_an_unknown_folder_points_at_full_drive_only_when_that_would_help(self):
        fake = FakeDrive(folders={})
        code, _, err = self.run_upload(self.pages("a.emf") + ["--folder", FOLDER_ID], fake)
        self.assertEqual(code, 1)
        self.assertIn("--full-drive", err)
        self.assertEqual(fake.uploads, [])
        fake = FakeDrive(folders={})
        code, _, err = self.run_upload(self.pages("a.emf") + ["--folder", FOLDER_ID, "--full-drive"], fake, full_drive=True)
        self.assertEqual(code, 1)
        self.assertNotIn("re-run with --full-drive", err)

    def test_a_conversion_failure_stops_the_run_after_one_file(self):
        fake = FakeDrive(converts=False)
        code, out, _ = self.run_upload(self.pages("a.emf", "b.emf", "c.emf"), fake)
        self.assertEqual(code, 1)
        self.assertEqual(len(fake.uploads), 1)
        self.assertEqual(fake.trashed, ["new1"])
        self.assertIn("Stopping", out)
        self.assertIn("2 not attempted", out)

    def test_a_refused_request_stops_the_run(self):
        fake = FakeDrive(upload_status=403)
        code, out, _ = self.run_upload(self.pages("a.emf", "b.emf"), fake)
        self.assertEqual(code, 1)
        self.assertIn("Stopping", out)
        self.assertIn("1 not attempted", out)

    def test_check_reports_whether_drive_converts_metafiles(self):
        code, out, _ = self.run_upload(["--check"], FakeDrive())
        self.assertEqual(code, 0)
        self.assertIn("Test User <t@example.com>", out)
        self.assertIn("drive.file", out)
        self.assertIn("yes, Drive converts", out)
        code, out, _ = self.run_upload(["--check", "--full-drive"], FakeDrive(import_formats={}), full_drive=True)
        self.assertEqual(code, 1)
        self.assertIn("NO, Drive does not list", out)
        self.assertIn("all of your Drive", out)

    def test_without_any_sign_in_setup_it_fails_before_converting(self):
        with mock.patch.dict(os.environ, {"VSDX_GDRIVE_DIR": self.dir}):
            code, _, err = self.run_cli(self.pages("a.emf"))
        self.assertEqual(code, 2)
        self.assertIn("Desktop app", err)


if __name__ == "__main__":
    unittest.main()
