# GVE DevNet Catalyst to Meraki Switch Transfer Tool
This repository contains a Python script that assists in applying a Catalyst switch configuration to a Meraki switch. Specifically, this script will copy the SVI and interface configurations to the Meraki switch. The SVI configuration that gets copied over is the VLAN description/name, interface ip address, and subnet. The interface configuration that gets copied over is the port description/name, data vlan, voice vlan, shutdown status, access/trunk mode, native vlan, and vlans allowed on trunk port. This code is built from the [Catalyst to Meraki Migration Tool](https://github.com/gve-sw/gve_devnet_catalyst_to_meraki_migration) and [Catalyst to Meraki SVI Migration](https://github.com/gve-sw/gve_devnet_meraki_svi_migration). This code does assume if switches are stacked, then that they have the same number of interfaces.

## Contacts
* Danielle Stacy

## Solution Components
* Python 3.12
* Netmiko
* Catalyst
* Meraki

## Prerequisites
#### Meraki API Keys
In order to use the Meraki API, you need to enable the API for your organization first. After enabling API access, you can generate an API key. Follow these instructions to enable API access and generate an API key:
1. Login to the Meraki dashboard
2. In the left-hand menu, navigate to `Organization > Settings > Dashboard API access`
3. Click on `Enable access to the Cisco Meraki Dashboard API`
4. Go to `My Profile > API access`
5. Under API access, click on `Generate API key`
6. Save the API key in a safe place. The API key will only be shown once for security purposes, so it is very important to take note of the key then. In case you lose the key, then you have to revoke the key and a generate a new key. Moreover, there is a limit of only two API keys per profile.

> For more information on how to generate an API key, please click [here](https://developer.cisco.com/meraki/api-v1/#!authorization/authorization). 

> Note: You can add your account as Full Organization Admin to your organizations by following the instructions [here](https://documentation.meraki.com/General_Administration/Managing_Dashboard_Access/Managing_Dashboard_Administrators_and_Permissions).

## Installation/Configuration
1. Clone this repository with `git clone [repository name]`
2. To complete this step, you will need the API key retrieved in the Prerequisites section. In addition, the code can connect to the Catalyst switch via SSH, or you will need provide the name of the file that contains the switch configuration. To connect via SSH, set CONNECT_SSH to "true". Otherwise, set CONNECT_SSH to "false". If you choose to use the SSH capability, ensure that SSH is configured on the Catalyst switch and know the credentials for the switch. You will also need the serial number of the Meraki switches that you will be configuring from the Catalyst switch. If you are only configuring one switch, then you will only provide one serial number, but if you have a stack or multiple switches that you wish to replace the Catalyst switch with, then you will need to provide all the serial numbers separated by commas in the appropriate order. Lastly, you'll need the default gateway from the Catalyst configuration. The default gateway for the MS switch must exist on exactly one imported SVI or be configured on  the MS already.
```python
CONNECT_SSH = "true"

IP = "ip address of Catalyst switch"
USER = "username to ssh to Catalyst switch"
PASSWORD = "password to ssh to Catalyst switch"
SECRET = "secret to ssh to Catalyst switch"

TEXT_FILE = "name of file that contains config"

API_KEY = "API key for Meraki"
MS_SERIAL = ["serial num of Meraki switch"]

DEFAULT_GATEWAY = "ip address default gateway for Catalyst switch"
```
3. Set up a Python virtual environment. Make sure Python 3 is installed in your environment, and if not, you may download Python [here](https://www.python.org/downloads/). Once Python 3 is installed in your environment, you can activate the virtual environment with the instructions found [here](https://docs.python.org/3/tutorial/venv.html).
4. Install the requirements with `pip3 install -r requirements.txt`

## Usage
To run the program, use the command:
```
$ python3 config_tool.py
```
The script will connect to the Catalyst Switch
![/IMAGES/step1.png](/IMAGES/step1.png)

Then the script will parse through the SVI configuration of the Catalyst switch
![/IMAGES/step2.png](/IMAGES/step2.png)

The script will find the shut interfaces on the Catalyst switch
![/IMAGES/step3.png](/IMAGES/step3.png)

The script will also parse the downlink interface configurations on the Catalyst switch
![/IMAGES/step4.png](/IMAGES/step4.png)

Then, the script will parse the uplink interface configurations on the Catalyst switch
![/IMAGES/step5.png](/IMAGES/step5.png)

Last, the script will configure the Meraki switches with the configurations parsed from the Catalyst switch
![/IMAGES/step6.png](/IMAGES/step5.png)

![/IMAGES/0image.png](/IMAGES/0image.png)

### LICENSE

Provided under Cisco Sample Code License, for details see [LICENSE](LICENSE.md)

### CODE_OF_CONDUCT

Our code of conduct is available [here](CODE_OF_CONDUCT.md)

### CONTRIBUTING

See our contributing guidelines [here](CONTRIBUTING.md)

#### DISCLAIMER:
<b>Please note:</b> This script is meant for demo purposes only. All tools/ scripts in this repo are released for use "AS IS" without any warranties of any kind, including, but not limited to their installation, use, or performance. Any use of these scripts and tools is at your own risk. There is no guarantee that they have been through thorough testing in a comparable environment and we are not responsible for any damage or data loss incurred with their use.
You are responsible for reviewing and testing any scripts you run thoroughly before use in any non-testing environment.
