import requests
import urllib3
import getpass

# Disable SSL certificate verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Configuration ---
# The templates now include placeholders for {key} and, where needed, {version}.
# A 'requires_version' flag is added to trigger the version prompt.
URL_CHOICES = {
    "1": {
        "name": "Software Version Check",
        "template": "https://{host}/api/?type=op&cmd=<request><system><software><check></check></software></system></request>&key={key}",
        "requires_version": False
    },
    "2": {
        "name": "Download Version",
        "template": "https://{host}/api/?type=op&cmd=<request><system><software><download><version>{version}</version></download></software></system></request>&key={key}",
        "requires_version": True
    },
    "3": {
        "name": "Install Version",
        "template": "https://{host}/api/?type=op&cmd=<request><system><software><install><version>{version}</version></install></software></system></request>&key={key}",
        "requires_version": True
    },
    "4": {
        "name": "Reboot",
        "template": "https://{host}/api/?type=op&cmd=<request><restart><system></system></restart></request>&key={key}",
        "requires_version": False
    }
}

HEADERS = {
    'User-Agent': 'Palo-Upgrade-Script/1.0'
}

# --- Functions ---
def get_api_key():
    """Securely prompts the user for their API key."""
    return getpass.getpass("Please enter your API key: ")

def get_user_selections():
    """Displays a menu and gets the user's command choice and version, if needed."""
    print("Please select the command you would like to run:")
    for key, value in URL_CHOICES.items():
        print(f"  {key}. {value['name']}")
    
    version = None
    while True:
        choice = input("Enter your choice (e.g., 1): ")
        if choice in URL_CHOICES:
            selected_check = URL_CHOICES[choice]
            # If the chosen command requires a version, prompt for it
            if selected_check.get("requires_version"):
                version = input(f"Please enter the version for '{selected_check['name']}': ")
            return selected_check, version
        else:
            print("acInvalid choice. Please enter a valid number from the list.")

def get_host_list():
    """Prompts the user to enter a list of server hostnames."""
    hosts = []
    print("\nEnter the server hostnames or IP addresses one by one.")
    print("Press Enter on an empty line when you are finished.")
    
    while True:
        host = input(f"Host #{len(hosts) + 1}: ")
        if not host:
            break
        hosts.append(host)
    return hosts

def run_commands(host_list, selected_check, api_key, version=None):
    """Constructs URLs and makes HTTP GET requests."""
    if not host_list:
        print("\nNo hosts entered. Exiting.")
        return

    check_name = selected_check['name']
    url_template = selected_check['template']

    print(f"\n--- Starting '{check_name}' on {len(host_list)} server(s) ---")
    for host in host_list:
        # Prepare arguments for URL formatting
        format_args = {'host': host, 'key': api_key}
        if version:
            format_args['version'] = version
        
        # Build the final URL
        url = url_template.format(**format_args)
        
        print(f"--- Running '{check_name}' on {host} ---")
        try:
            response = requests.get(url, headers=HEADERS, timeout=30, verify=False)
            response.raise_for_status() 
            print(f"Success (Status Code: {response.status_code})")

        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error: {e.response.status_code} {e.response.reason}")
        except requests.exceptions.ConnectionError:
            print(f"Connection Error: Failed to resolve or connect to {host}.")
        except requests.exceptions.Timeout:
            print(f"Timeout: The request to {host} timed out.")
        except requests.exceptions.RequestException as e:
            print(f"An unexpected requests error occurred for {host}: {e}")
        print("-" * 25 + "\n")

# --- Main execution ---
if __name__ == "__main__":
    api_key = get_api_key()
    check_to_run, version_number = get_user_selections()
    hosts = get_host_list()
    run_commands(hosts, check_to_run, api_key, version=version_number)