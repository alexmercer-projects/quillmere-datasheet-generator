"""Print and inspect HTML in Chrome over its local DevTools pipe."""

import base64
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
from queue import Empty, Queue
import re
import shutil
import subprocess
from threading import Thread
import time

FIT_CHECK = """async () => {
  await document.fonts.ready;
  await Promise.all(Array.from(document.images, image => image.decode().catch(() => {})));
  const boxes = Array.from(document.querySelectorAll('[data-fit]'));
  return {
    checked: boxes.length,
    overflow: boxes.flatMap(el => {
      const width = el.scrollWidth - el.clientWidth;
      const height = el.scrollHeight - el.clientHeight;
      return width > 0 || height > 0
        ? [{field: el.dataset.fit || el.tagName, width: Math.max(0, width), height: Math.max(0, height)}]
        : [];
    }),
    broken: Array.from(document.images).filter(image => !image.naturalWidth)
      .map(image => image.alt || image.getAttribute('src')),
    fonts: Array.from(document.fonts).filter(font => font.status === 'error').map(font => font.family)
  };
}"""


class BrowserError(RuntimeError):
    pass


def executable(name):
    if path := shutil.which(name):
        return path
    raise BrowserError(f"{name} is required on PATH.")


def run_poppler(*args):
    try:
        return subprocess.run(
            [executable(args[0]), *map(str, args[1:])],
            capture_output=True, text=True, check=True, timeout=45,
            env={**os.environ, "LC_ALL": "C"},
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        detail = getattr(error, "stderr", None) or str(error)
        raise BrowserError(f"{args[0]} failed. {detail.strip()}") from error


def pdf_pages(path):
    match = re.search(r"^Pages:\s+(\d+)\s*$", run_poppler("pdfinfo", path), re.MULTILINE)
    if not match:
        raise BrowserError(f"Could not read the page count of {Path(path).name}.")
    return int(match[1])


class Chrome:
    """A Chrome process and one blank tab, with bounded requests and clean teardown."""

    def __init__(self, profile):
        self.profile = Path(profile)
        command = [
            executable(os.environ.get("QUILLMERE_CHROME", "google-chrome")),
            "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
            "--disable-background-networking", "--disable-extensions",
            "--no-first-run", "--no-default-browser-check", "--no-proxy-server",
            "--allow-file-access-from-files", "--remote-debugging-pipe",
            f"--user-data-dir={self.profile}", "about:blank",
        ]
        self.messages = Queue()
        self.call_id = 0
        self.session = None
        self.log = self.profile.with_suffix(".log").open("w+b")
        try:
            self.process = subprocess.Popen(
                ["/bin/sh", "-c", 'exec 3<&0 4>&1; exec "$@"', "chrome-pipe", *command],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, bufsize=0,
            )
        except OSError:
            self.log.close()
            raise
        self.reader = Thread(target=self.read_messages, daemon=True)
        self.reader.start()

    def read_messages(self):
        pending = b""
        try:
            while block := self.process.stdout.read(65536):
                chunks = (pending + block).split(b"\0")
                pending = chunks.pop()
                for message in chunks:
                    if message:
                        self.messages.put(json.loads(message))
        except (OSError, ValueError) as error:
            self.messages.put(error)
        finally:
            self.messages.put(None)

    def startup_error(self, message):
        with self.profile.with_suffix(".log").open(errors="replace") as log:
            lines = [line.strip() for line in log if line.strip()]
        return BrowserError(f"{message} {' '.join(lines[-3:])}".strip())

    def call(self, method, params=None, *, browser=False):
        self.call_id += 1
        request = {"id": self.call_id, "method": method, "params": params or {}}
        if self.session and not browser:
            request["sessionId"] = self.session
        try:
            self.process.stdin.write(json.dumps(request).encode() + b"\0")
        except OSError as error:
            raise self.startup_error("Chrome could not accept a DevTools request.") from error
        deadline = time.monotonic() + 25
        while True:
            try:
                message = self.messages.get(timeout=max(0, deadline - time.monotonic()))
            except Empty as error:
                raise self.startup_error(f"Chrome timed out during {method}.") from error
            if message is None or isinstance(message, Exception):
                raise self.startup_error(f"Chrome closed its pipe during {method}.")
            if message.get("id") == self.call_id:
                if "error" in message:
                    raise BrowserError(f"{method} failed. {message['error']['message']}")
                return message["result"]

    def open(self, url, width=816, height=1056, media="print"):
        if not self.session:
            target = self.call("Target.createTarget", {"url": "about:blank"})["targetId"]
            self.session = self.call("Target.attachToTarget", {
                "targetId": target, "flatten": True,
            })["sessionId"]
            self.call("Page.enable")
        self.call("Emulation.setDeviceMetricsOverride", {
            "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False,
        })
        if media == "print":
            self.call("Emulation.setEmulatedMedia", {"media": "print"})
        result = self.call("Page.navigate", {"url": url})
        if "errorText" in result:
            raise BrowserError(f"Could not load the document. {result['errorText']}")
        deadline = time.monotonic() + 12
        while True:
            status = self.evaluate("({url: location.href, ready: document.readyState})")
            if status == {"url": url, "ready": "complete"}:
                return
            if time.monotonic() >= deadline:
                raise BrowserError("The document did not finish loading in Chrome.")
            time.sleep(0.02)

    def evaluate(self, expression):
        result = self.call("Runtime.evaluate", {
            "expression": expression, "awaitPromise": True, "returnByValue": True,
        })
        if "exceptionDetails" in result:
            raise BrowserError(result["result"].get("description", "Document script failed."))
        return result["result"].get("value")

    def print_pdf(self, destination):
        result = self.call("Page.printToPDF", {
            "printBackground": True, "displayHeaderFooter": False,
            "preferCSSPageSize": True, "paperWidth": 8.5, "paperHeight": 11,
            "marginTop": 0, "marginBottom": 0, "marginLeft": 0, "marginRight": 0,
        })
        destination.write_bytes(base64.b64decode(result["data"]))

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.reader.join(timeout=1)
        self.process.stdout.close()
        self.log.close()


@contextmanager
def chrome(profile):
    browser = Chrome(profile)
    try:
        yield browser
    finally:
        browser.close()


@dataclass(frozen=True)
class PrintResult:
    pages: int
    checked: int
    overflow: list
    broken: list
    fonts: list


def print_document(html, destination, work):
    work.mkdir(parents=True, exist_ok=True)
    document = work / "print.html"
    document.write_text(html, encoding="utf-8")
    with chrome(work / "profile") as browser:
        browser.open(document.resolve().as_uri())
        fit = browser.evaluate(f"({FIT_CHECK})()")
        browser.print_pdf(destination)
    return PrintResult(pdf_pages(destination), **fit)
