This script will request the following:

- API Key - The API Key of the user to run the commands
- Action to Perform:
  - Software Version Check - Downloads the latest list of OS Versions
  - Download Version - Commands the firewall to download the designated version
  - Install Version - Commands the firewall to install the designated version
  - Reboot - Commands the firewall to reboot
- Version (Option 2/3 Only) - Manually enter the desired version to download/install
- Host - Perform the selected action on the provided hostname/IP

Currently this tool does not provide the outputs returned by the firewall, only if the command was a success (e.g. 200) or a failure (e.g. 403)
