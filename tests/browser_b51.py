"""Optional Firefox/WebDriver E2E; existing binaries only, no pip dependencies.

Run from repository root. Own temporary profiles/data only; software rendering;
external browser traffic proxied to a closed loopback port. Never print keys.
"""

import argparse
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time


ELEMENT = "element-6066-11e4-a52e-4f735466cecf"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firefox-binary", required=True, type=Path)
    parser.add_argument("--geckodriver-binary", required=True, type=Path)
    args = parser.parse_args()
    children = []
    session = None
    with tempfile.TemporaryDirectory(prefix="pepeuch-b51-browser-data-") as temporary:
        root = Path(temporary)
        data = root / "application"
        profile, downloads = root / "profile", root / "downloads"
        profile.mkdir(mode=0o700)
        downloads.mkdir(mode=0o700)
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "MOZ_HEADLESS": "1",
               "XDG_CACHE_HOME": str(root / "cache"), "XDG_CONFIG_HOME": str(root / "configuration"),
               "XDG_DATA_HOME": str(root / "browser-data"), "XDG_RUNTIME_DIR": str(root / "runtime")}
        (root / "runtime").mkdir(mode=0o700)
        log = (root / "processes.log").open("wb")
        def start_backend():
            child = subprocess.Popen([sys.executable, "-m", "control_plane", "serve", "--data-dir", str(data), "--port", "0"],
                                     stdout=subprocess.PIPE, stderr=log, env=env, start_new_session=True)
            children.append(child)
            line = child.stdout.readline().decode()
            if "http://127.0.0.1:" not in line:
                raise RuntimeError("Backend startup failed")
            return child, int(line.rsplit(":", 1)[1])
        backend, api_port = start_backend()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            driver_port = probe.getsockname()[1]
        driver = subprocess.Popen([str(args.geckodriver_binary), "--host", "127.0.0.1", "--port", str(driver_port), "--log", "fatal"],
                                  stdout=log, stderr=log, env=env, start_new_session=True)
        children.append(driver)
        def call(method, path, body=None):
            connection = http.client.HTTPConnection("127.0.0.1", driver_port, timeout=20)
            try:
                raw = None if body is None else json.dumps(body)
                connection.request(method, path, body=raw, headers={"Content-Type": "application/json"})
                response = connection.getresponse()
                value = json.loads(response.read())
                if response.status >= 400:
                    raise RuntimeError("WebDriver operation failed: " + method + " " + path)
                return value.get("value")
            finally:
                connection.close()
        def command(method, path, body=None):
            return call(method, "/session/" + session + path, body)
        def script(code, arguments=None):
            return command("POST", "/execute/sync", {"script": code, "args": [] if arguments is None else arguments})
        def wait_for(expression):
            code = "const done=arguments[0]; const matches=()=>Boolean(" + expression + "); if(matches()){done(true);return;} const observer=new MutationObserver(()=>{if(matches()){observer.disconnect();done(true);}}); observer.observe(document,{subtree:true,attributes:true,childList:true,characterData:true});"
            command("POST", "/execute/async", {"script": code, "args": []})
        def element(selector):
            return command("POST", "/element", {"using": "css selector", "value": selector})[ELEMENT]
        def click(selector):
            command("POST", "/element/" + element(selector) + "/click", {})
        def enter(selector, value):
            command("POST", "/element/" + element(selector) + "/value", {"text": value})
        def login(port):
            command("POST", "/url", {"url": f"http://127.0.0.1:{port}"})
            enter("#credential", (data / "secrets/admin.token").read_text().strip())
            click("#login-form button")
            wait_for("!document.getElementById('application').hidden && document.getElementById('metrics').children.length===3")
        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    call("GET", "/status")
                    break
                except (ConnectionError, OSError):
                    if time.monotonic() > deadline:
                        raise RuntimeError("WebDriver startup timeout") from None
                    threading.Event().wait(0.05)
            prefs = {"gfx.webrender.software": True, "layers.acceleration.disabled": True,
                     "webgl.disabled": True, "media.hardware-video-decoding.enabled": False,
                     "network.proxy.type": 1, "network.proxy.http": "127.0.0.1", "network.proxy.http_port": 9,
                     "network.proxy.ssl": "127.0.0.1", "network.proxy.ssl_port": 9,
                     "network.proxy.no_proxies_on": "localhost,127.0.0.1", "network.dns.disablePrefetch": True,
                     "network.prefetch-next": False, "network.trr.mode": 5,
                     "toolkit.telemetry.enabled": False, "datareporting.healthreport.uploadEnabled": False,
                     "browser.shell.checkDefaultBrowser": False, "browser.startup.homepage": "about:blank",
                     "browser.download.folderList": 2, "browser.download.dir": str(downloads),
                     "browser.download.useDownloadDir": True,
                     "browser.helperApps.neverAsk.saveToDisk": "application/octet-stream", "pdfjs.disabled": True}
            response = call("POST", "/session", {"capabilities": {"alwaysMatch": {"browserName": "firefox", "moz:firefoxOptions": {
                "binary": str(args.firefox_binary), "args": ["-headless", "-profile", str(profile)], "prefs": prefs}}}})
            session = response["sessionId"]
            command("POST", "/timeouts", {"implicit": 5000, "script": 15000, "pageLoad": 15000})
            command("POST", "/window/rect", {"width": 1360, "height": 1000})
            screenshots = Path(tempfile.mkdtemp(prefix="pepeuch-b51-screenshots-"))
            login(api_port)
            assert script("return document.getElementById('credential').value === '' && localStorage.length === 0 && sessionStorage.length === 0;")
            click("#new-mission")
            enter("#mission-title", "Rapport navigateur")
            enter("#mission-objective", "Préparer un rapport. <img src=x onerror=window.b51xss=true>")
            click("#mission-form button[type=submit]")
            wait_for("document.querySelector('#mission-detail .status.draft')")
            mission_id = script("return document.querySelector('#mission-detail .identity').textContent;")
            assert script("return typeof window.b51xss === 'undefined';")
            click("#mission-detail .actions button")
            command("POST", "/alert/accept", {})
            wait_for("document.querySelector('#mission-detail .status.queued')")
            result = subprocess.run([sys.executable, "-m", "control_plane", "worker", "--data-dir", str(data),
                                     "--server-url", f"http://127.0.0.1:{api_port}", "--once"], env=env, capture_output=True, timeout=15)
            assert result.returncode == 0, "Worker process failed"
            wait_for("document.querySelector('#mission-detail .status.completed')")
            script("document.querySelector('#mission-detail').querySelectorAll('button').forEach(button=>{if(button.textContent==='Télécharger resultat.md')button.click();});")
            deadline = time.monotonic() + 10
            report = downloads / "resultat.md"
            while not report.exists() or not report.stat().st_size:
                if time.monotonic() > deadline:
                    raise RuntimeError("Browser download timeout")
                threading.Event().wait(0.05)
            first_sha = hashlib.sha256(report.read_bytes()).hexdigest()
            assert b"SIMULATION" in report.read_bytes()
            (screenshots / "mission.png").write_bytes(base64.b64decode(command("GET", "/screenshot")))
            click("[data-view=workspaces]")
            note = root / "notes.txt"
            note.write_text("Version une", encoding="utf-8")
            enter("#upload-file", str(note))
            click("#upload-form button[type=submit]")
            wait_for("Array.from(document.querySelectorAll('.file-card h2')).some(item=>item.textContent==='notes.txt')")
            note.write_text("Version deux", encoding="utf-8")
            enter("#upload-file", str(note))
            click("#upload-form button[type=submit]")
            wait_for("Array.from(document.querySelectorAll('.file-card')).some(card=>card.querySelector('h2').textContent==='notes.txt' && card.querySelector('select').options.length===2)")
            click("[data-view=missions]")
            enter("#mission-title", "Mission avec fichier")
            enter("#mission-objective", "Vérifier les références autorisées avant approbation.")
            script("for(const option of document.getElementById('mission-inputs').options){option.selected=option.textContent.startsWith('notes.txt');}")
            click("#mission-form button[type=submit]")
            wait_for("document.querySelector('#mission-detail .status.draft') && document.getElementById('mission-detail').textContent.includes('notes.txt · version 2')")
            click("[data-view=workspaces]")
            (screenshots / "desktop.png").write_bytes(base64.b64decode(command("GET", "/screenshot")))
            command("POST", "/window/rect", {"width": 390, "height": 844})
            assert script("return document.documentElement.scrollWidth <= window.innerWidth;")
            (screenshots / "mobile.png").write_bytes(base64.b64decode(command("GET", "/screenshot")))
            backend.send_signal(signal.SIGINT)
            backend.wait(timeout=10)
            backend, api_port = start_backend()
            login(api_port)
            restarted_worker = subprocess.run([sys.executable, "-m", "control_plane", "worker", "--data-dir", str(data),
                                                "--server-url", f"http://127.0.0.1:{api_port}", "--once"], env=env, capture_output=True, timeout=15)
            assert restarted_worker.returncode == 0 and b"idle" in restarted_worker.stdout, "Completed mission must not be reexecuted"
            click("[data-view=missions]")
            wait_for("document.querySelector('#mission-list .status.completed')")
            click("#mission-list .mission-row:has(.status.completed) button")
            wait_for("document.querySelector('#mission-detail .status.completed')")
            assert script("return document.querySelector('#mission-detail .identity').textContent;") == mission_id
            # Verify persisted result over authenticated HTTP after both services restarted.
            connection = http.client.HTTPConnection("127.0.0.1", api_port)
            auth = {"Authorization": "Bearer " + (data / "secrets/admin.token").read_text().strip()}
            connection.request("GET", "/api/v1/missions/" + mission_id, headers=auth)
            persisted = json.loads(connection.getresponse().read())["results"][0]
            # Workspace ID comes from API, never a host path.
            connection.request("GET", "/api/v1/workspaces", headers=auth)
            workspace = json.loads(connection.getresponse().read())["workspaces"][0]["id"]
            connection.request("GET", f"/api/v1/workspaces/{workspace}/files/{persisted['file_id']}/versions/{persisted['version_id']}/download", headers=auth)
            assert hashlib.sha256(connection.getresponse().read()).hexdigest() == first_sha
            connection.close()
            click("#logout")
            assert script("return document.getElementById('application').hidden && document.getElementById('mission-detail').textContent === '';")
            print(json.dumps({"browser": response["capabilities"]["browserVersion"], "result_sha256": first_sha,
                              "checks": "login, draft, explicit approval, authorized file versions, XSS text, worker process, download, two upload versions, restart, mobile width, logout",
                              "screenshots": str(screenshots)}, ensure_ascii=False))
        finally:
            if session is not None:
                try:
                    command("DELETE", "")
                except Exception:
                    pass
            for child in reversed(children):
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait(timeout=5)
                if child.stdout is not None:
                    child.stdout.close()
            log.close()


if __name__ == "__main__":
    main()
