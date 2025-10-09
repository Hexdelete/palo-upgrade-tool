import asyncio
import requests
import urllib3
import xml.etree.ElementTree as ET
from typing import Union, List, Tuple

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Header,
    Footer,
    Static,
    Input,
    RichLog,
    Select,
    SelectionList,
)
from textual.widgets.selection_list import Selection
from textual import on

# Disable SSL certificate verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Configuration ---
# API Key is no longer in the templates
URL_CHOICES = {
    "Software Version Check": {
        "cmd": "<request><system><software><check></check></software></system></request>",
    },
    "Download Version": {
        "cmd": "<request><system><software><download><version>{version}</version></download></software></system></request>",
        "generates_job": True
    },
    "Install Version": {
        "cmd": "<request><system><software><install><version>{version}</version></install></software></system></request>",
        "generates_job": True
    },
    "Reboot": {
        "cmd": "<request><restart><system></system></restart></request>",
    },
}

class PanoramaTUI(App):
    TITLE = "Panorama Command Runner"
    BINDINGS = [("ctrl+q", "quit", "Quit")]
    
    CSS = """
    Screen {
        layout: vertical;
        padding: 0 1;
    }
    #main_content {
        layout: horizontal;
        height: 1fr;
        margin-top: 1;
        margin-bottom: 1;
    }
    #sidebar {
        width: 45%;
        height: 100%;
        border: round white;
        padding: 1;
        margin-right: 1;
    }
    #device_list_container {
        width: 1fr;
        height: 100%;
        border: round white;
        padding: 1;
    }
    #output_log {
        height: 12;
        border: round white;
        padding: 0 1;
    }
    #action-buttons > Button {
        width: 100%;
        margin-top: 1;
    }
    """

    def __init__(self):
        super().__init__()
        self.serial_to_hostname = {}

    def compose(self) -> ComposeResult:
        yield Header()
        
        with Horizontal(id="main_content"):
            with VerticalScroll(id="sidebar"):
                yield Static("[b]1. Panorama Details[/b]")
                yield Input(placeholder="Panorama IP/Hostname", id="pano_ip")
                # --- UI CHANGE IS HERE ---
                yield Input(placeholder="Username", id="username")
                yield Input(placeholder="Password", password=True, id="password")
                yield Button("Fetch Connected Devices", variant="primary", id="fetch")
                
                yield Static("\n[b]2. Check for Versions[/b]")
                yield Button("Check for Available Software", variant="primary", id="run_check_versions")
                
                yield Static("\n[b]3. Execute an Action[/b]")
                yield Select(
                    [],
                    prompt="Select a version...",
                    id="version_select",
                    disabled=True
                )
                with Vertical(id="action-buttons"):
                    yield Button("Download Version", variant="success", id="run_download")
                    yield Button("Install Version", variant="success", id="run_install")
                    yield Button("Reboot Devices", variant="error", id="run_reboot")

            with Container(id="device_list_container"):
                yield Static("[b]Target Devices[/b]")
                yield SelectionList(id="device_list")
        
        yield RichLog(id="output_log", wrap=True, highlight=True, auto_scroll=True, markup=True)
        yield Footer()

    async def on_mount(self) -> None:
        log = self.query_one(RichLog)
        log.write("Welcome! Enter your credentials and fetch devices to begin.")

    def run_api_request(self, url: str, params: dict, auth: tuple) -> requests.Response:
        """Runs a synchronous request with Basic Authentication."""
        return requests.get(url, params=params, auth=auth, verify=False, timeout=30)

    async def fetch_devices(self, auth: tuple) -> None:
        log = self.query_one(RichLog)
        selection_list = self.query_one(SelectionList)
        selection_list.clear_options()
        self.serial_to_hostname.clear()
        
        pano_ip = self.query_one("#pano_ip").value
        if not pano_ip:
            log.write("[red]Error: Panorama IP is required.[/red]")
            return

        log.write(f"Fetching devices from {pano_ip}...")
        base_url = f"https://{pano_ip}/api/"
        payload = { 'type': 'op', 'cmd': '<show><devices><connected></connected></devices></show>' }
        
        try:
            response = await asyncio.to_thread(self.run_api_request, base_url, payload, auth)
            response.raise_for_status()
            root = ET.fromstring(response.text)
            if root.attrib["status"] == "error":
                # Check for common auth failure message
                msg_node = root.find(".//msg")
                error_msg = msg_node.text if msg_node is not None else "Unknown API error"
                if "authentication failed" in error_msg.lower():
                    log.write("[red]API Error: Authentication failed. Please check your username and password.[/red]")
                else:
                    log.write(f"[red]API Error: {error_msg}[/red]")
                return

            options = []
            for entry in root.findall("./result/devices/entry"):
                hostname_node = entry.find("hostname")
                serial_node = entry.find("serial")
                if hostname_node is not None and serial_node is not None:
                    hostname, serial = hostname_node.text, serial_node.text
                    self.serial_to_hostname[serial] = hostname
                    options.append(Selection(f"{hostname} ({serial})", serial))
            
            options.sort(key=lambda sel: sel.prompt)

            selection_list.add_options(options)
            log.write(f"[green]Success! Found {len(options)} connected devices.[/green]")
        
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                log.write("[red]Connection Error: Received status 403 Forbidden. Please check your username and password.[/red]")
            else:
                log.write(f"[red]HTTP Error: {e}[/red]")
        except requests.exceptions.RequestException as e:
            log.write(f"[red]Connection Error: {e}[/red]")

    async def run_version_check(self, auth: tuple) -> None:
        log = self.query_one(RichLog)
        selection_list = self.query_one(SelectionList)
        version_select = self.query_one("#version_select")

        if not selection_list.selected:
            log.write("[red]Error: Please select one device to check for versions.[/red]")
            return

        target_serial = selection_list.selected[0]
        target_hostname = self.serial_to_hostname.get(target_serial, target_serial)
        log.write(f"Running Software Version Check on {target_hostname}...")

        pano_ip = self.query_one("#pano_ip").value
        
        base_url = f"https://{pano_ip}/api/"
        payload = { 'type': 'op', 'cmd': URL_CHOICES["Software Version Check"]['cmd'], 'target': target_serial }

        try:
            response = await asyncio.to_thread(self.run_api_request, base_url, payload, auth)
            response.raise_for_status()
            root = ET.fromstring(response.text)
            if root.attrib["status"] == "error":
                error_msg = root.find(".//msg").text
                log.write(f"[red]API Error: {error_msg}[/red]")
                return
            
            versions = [v.text for v in root.findall('./result/sw-updates/versions/entry/version')]
            
            if not versions:
                log.write("[yellow]Warning: No software versions found.[/yellow]")
                return

            version_select.set_options([(v, v) for v in versions])
            version_select.disabled = False
            log.write(f"[green]Success! Found {len(versions)} versions. Dropdown populated.[/green]")
        
        except requests.exceptions.RequestException as e:
            log.write(f"[red]Connection Error: {e}[/red]")

    async def track_job_progress(self, auth: tuple, serial: str, job_id: str) -> None:
        log = self.query_one(RichLog)
        hostname = self.serial_to_hostname.get(serial, serial)
        
        while True:
            await asyncio.sleep(5)
            
            pano_ip = self.query_one("#pano_ip").value
            base_url = f"https://{pano_ip}/api/"
            payload = { 'type': 'op', 'cmd': f'<show><jobs><id>{job_id}</id></jobs></show>', 'target': serial }
            
            try:
                response = await asyncio.to_thread(self.run_api_request, base_url, payload, auth)
                response.raise_for_status()
                root = ET.fromstring(response.text)
                
                status_node = root.find('./result/job/status')
                if status_node is None:
                    log.write(f"[yellow]Warning: Could not determine status for job {job_id} on {hostname}.[/yellow]")
                    break
                
                status = status_node.text
                if status == 'FIN':
                    result = root.find('./result/job/result').text
                    if result == 'OK':
                        log.write(f"[green]✅ Job {job_id} on {hostname} FINISHED successfully.[/green]")
                    else:
                        details = "\n".join([line.text for line in root.findall('./result/job/details/line')])
                        log.write(f"[red]❌ Job {job_id} on {hostname} FINISHED with failure.[/red]\n{details}")
                    break
                elif status == 'ACT':
                    progress_node = root.find('./result/job/progress')
                    if progress_node is not None and progress_node.text:
                        log.write(f"  -> Job {job_id} on {hostname} is downloading... {progress_node.text}% complete.")
                else:
                     log.write(f"  -> Job {job_id} on {hostname} is ongoing. Status: {status}")

            except requests.exceptions.RequestException as e:
                log.write(f"[red]❌ Error checking job {job_id} on {hostname}: {e}[/red]")
                break

    async def run_execute_command(self, auth: tuple, command_name: str, version: Union[str, None]) -> None:
        log = self.query_one(RichLog)
        selection_list = self.query_one(SelectionList)
        selected_serials = selection_list.selected
        if not selected_serials:
            log.write("[red]Error: No devices selected.[/red]")
            return

        pano_ip = self.query_one("#pano_ip").value
        command_info = URL_CHOICES[command_name]

        log.write(f"\n--- Starting '{command_name}' on {len(selected_serials)} device(s) ---")
        
        for serial in selected_serials:
            hostname = self.serial_to_hostname.get(serial, serial)
            base_url = f"https://{pano_ip}/api/"
            
            command_xml = command_info['cmd'].format(version=version) if version else command_info['cmd']
            payload = { 'type': 'op', 'cmd': command_xml, 'target': serial }
            
            log.write(f"--- Running '{command_name}' on {hostname} ---")
            
            try:
                response = await asyncio.to_thread(self.run_api_request, base_url, payload, auth)
                response.raise_for_status()
                
                if command_info.get("generates_job"):
                    root = ET.fromstring(response.text)
                    job_id_node = root.find('./result/job')
                    if job_id_node is not None and job_id_node.text:
                        job_id = job_id_node.text
                        log.write(f"Job enqueued (ID: {job_id}) on {hostname}. Monitoring...")
                        self.run_worker(self.track_job_progress(auth, serial, job_id))
                    else:
                        log.write(f"[red]❌ Error: Command '{command_name}' did not return a job ID for {hostname}.[/red]")
                else:
                    log.write(f"[green]✅ Success (Status Code: {response.status_code})[/green]")

            except requests.exceptions.RequestException as e:
                log.write(f"[red]❌ Error for {hostname}: {e}[/red]")

    @on(Button.Pressed)
    def handle_button_press(self, event: Button.Pressed) -> None:
        log = self.query_one(RichLog)
        username = self.query_one("#username").value
        password = self.query_one("#password").value

        if not username or not password:
            if event.button.id != "fetch" and not self.serial_to_hostname:
                # Allow fetching devices without creds, but not other actions
                pass
            else:
                log.write("[red]Error: Username and Password are required.[/red]")
                return
        
        auth = (username, password)

        if event.button.id == "fetch":
            self.run_worker(self.fetch_devices(auth))
        elif event.button.id == "run_check_versions":
            self.run_worker(self.run_version_check(auth))
        elif event.button.id in ("run_download", "run_install", "run_reboot"):
            command_name = ""
            if event.button.id == "run_download": command_name = "Download Version"
            elif event.button.id == "run_install": command_name = "Install Version"
            elif event.button.id == "run_reboot": command_name = "Reboot"

            version = None
            if URL_CHOICES[command_name].get("generates_job"):
                version = self.query_one("#version_select").value
                if version is Select.BLANK:
                    log.write("[red]Error: Please run a version check and select a version first.[/red]")
                    return
            
            self.run_worker(self.run_execute_command(auth, command_name, version))


if __name__ == "__main__":
    app = PanoramaTUI()
    app.run()