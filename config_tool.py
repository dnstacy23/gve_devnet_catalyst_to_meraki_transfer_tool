#!/usr/bin/env python3
"""
Copyright (c) 2023 Cisco and/or its affiliates.
This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at
https://developer.cisco.com/docs/licenses
All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.
"""
from ciscoconfparse import CiscoConfParse
from netmiko import ConnectHandler
from dotenv import load_dotenv
import os
import ipaddress
import meraki
import sys
import re
import json
from pprint import pprint
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress

CONSOLE = Console()

def get_config():
    """
    Connect to Catalyst switch over ssh, retrieve show run output
    :return: string containing results of show run command
    """
    # credentials of Catalyst switch to connect to
    switch = {
        "device_type": "cisco_ios",
        "host": os.getenv("IP"),
        "username": os.getenv("USERNAME"),
        "password": os.getenv("PASSWORD"),
        "secret": os.getenv("SECRET")
    }

    CONSOLE.print(f'Connecting to Switch at [green]{switch["host"]}[/]...')

    show_command = f"show run"

    with ConnectHandler(**switch) as connection:
        # send show run command to switch
        output = connection.send_command(show_command)

        # check if shout output is valid
        if "Invalid" in output:
            CONSOLE.print(f' - [red]Failed to execute "{show_command}"[/], please ensure the command is correct!')
            return None
        else:
            CONSOLE.print(f' - Executed [blue]"{show_command}"[/] successfully!')
            return output

def parse_svi_data(file_path):
    """
    Parse SVI config from show run, extract SVI pieces and build dictionary of SVIs
    :param file_path: File path to temporary file containing show run output
    :return: Dictionary of parsed SVIs
    """
    # parse config file for VLANs
    parse = CiscoConfParse(file_path, syntax="ios")
    vlans = parse.find_objects(r"^interface Vlan")

    vlan_count = len(vlans)
    CONSOLE.print(f'Found [blue]{vlan_count} vlans[/] to convert!')

    # regex expressions used for finding SVI config details
    description_re = r"description\s(.+)"
    ip_address_re = r"ip\saddress\s([\d\.]+)\s([\d\.]+)"
    ip_helper_address_re = r"ip\shelper-address\s([\d\.]+)"

    # store extracted config info in this dictionary
    svi_data = {}

    # iterate over VLANs, extract out fields for Meraki API call
    with Progress() as progress:
        overall_progress = progress.add_task("Overall Progress", total=vlan_count, transient=True)
        counter = 1

        for vlan in vlans:
            # get VLAN ID
            vlan_id = re.search(r"\d+", vlan.text).group()

            description = ""
            ip_address = ""
            subnet_mask = ""

            # search VLAN configuration for description, ip, subnet, helper-address
            for child in vlan.children:
                if "description" in child.text:
                    description = child.re_match_typed(description_re, group=1)

                elif "ip address" in child.text:
                    ip_address = child.re_match_typed(ip_address_re, group=1)
                    subnet_mask = child.re_match_typed(ip_address_re, group=2)

            if vlan_id not in svi_data.keys() and ip_address != "" and subnet_mask != "":
                # convert ip/subnet to cidr notation for API call
                subnet = ipaddress.ip_network(f"{ip_address}/{subnet_mask}", strict=False)

                svi_data[vlan_id] = {
                    "name": description if description != "" else "Vlan" + vlan_id,
                    "vlanId": vlan_id,
                    "interfaceIp": ip_address,
                    "subnet": str(subnet),
                }

                progress.console.print(svi_data[vlan_id])
            else:
                # if key fields are missing, skip
                progress.console.print('[red]Error: one or more key fields are missing from vlan[/] ("ip address"). '
                                       'Skipping...')

            counter += 1
            progress.update(overall_progress, advance=1)

    return svi_data

def parse_shut_intf(file_path):
    """
    Parse through Catalyst show run output to find which interfaces are shutdown
    :param file_path: File path to temporary file containing show run output
    :return: List of names of shut interfaces
    """
    CONSOLE.print(f"Checking the number of shut interfaces")

    # parse config file for shutdown interfaces
    parse = CiscoConfParse(file_path, syntax="ios")
    shut_interfaces = []
    for intf_obj in parse.find_objects_w_child("^interface", "^\s+shutdown"):
        # add interface name of shutdown interface to list
        shut_interfaces.append(intf_obj.re_match_typed("^interface\s+(\S.+?)$"))

    shut_count = len(shut_interfaces)

    CONSOLE.print(f"Found [blue]{shut_count} shut interfaces[/]")

    return shut_interfaces

def parse_intf_config(file_path, num_switches):
    """
    Parse through Catalust show run output to find the interface configurations
    :param file_path: File path to temporary file containing show run output
    :param num_switches: Number of Meraki switches that will be configured
    :return: Dictionary of parsed interfaces
    """
    CONSOLE.print(f"Parsing the interface configurations")

    # parse config for interfaces
    parse = CiscoConfParse(file_path, syntax="ios")
    interfaces = parse.find_objects("^interface")

    # regex expressions for finding configurations of interfaces
    description_re = r"description\s(.+)"
    port_mode_re = r"\sswitchport\smode\s+(.+)"
    voice_vlan_re = r"\sswitchport\svoice\svlan\s+(\d+)"
    data_vlan_re = r"\sswitchport\saccess\svlan\s+(\S.*)"
    trunk_native_re = r"\sswitchport\strunk\snative\svlan\s+(.*)"
    vlan_allowed_re = r"\sswitchport\strunk\sallowed\svlan\s+(.*)"

    # module_counter is a variable that will keep track of the number of ports on the first switch
    module_counter = 0
    # dictionary will contain details of configuration
    intf_configs = {}
    # iterate through interfaces and retrieve necessary configurations
    for intf_obj in interfaces:
        # find the interface name, switch module, and port number
        intf_name = intf_obj.re_match_typed("^interface\s+(\S.*)$")
        only_intf_name = re.sub("\d+|\\/", "", intf_name)
        switch_module = intf_obj.re_match_typed("^interface\s\S+?thernet+(\d)")
        port_number = intf_obj.re_match_typed("^interface\s\S+?thernet\d.\d.(\d+)")

        # we only want configuration information of downlink interfaces
        if only_intf_name.startswith("Giga") and port_number != "":
            CONSOLE.print(f"Creating [blue] {intf_name}[/] object")

            intf_configs[intf_name] = {}
            port_number = int(port_number)
            # if we are only configuring one Meraki switch, we need to make sure the port numbers are correct
            if num_switches == 1:
                # the interface is in the first Catalyst switch module
                if int(switch_module) == 1:
                    # increase module_counter by 1
                    module_counter += 1
                # the interface is not in the first Catalyst switch module (it's part of a stack)
                elif int(switch_module) > 1:
                    # adjust port number the corresponding of the corresponding Meraki interface that will be configured
                    port_number += module_counter * (switch_module - 1)
            # configuring more than one Meraki switch
            elif num_switches > 1:
                # set which Meraki switch needs to be configured in the stack
                switch_module = int(switch_module)
                intf_configs[intf_name]["module"] = switch_module

            # search configuration for description, mode, data vlan, voice vlan, native vlan, and allowed vlans
            intf_configs[intf_name]["portId"] = str(port_number)
            for child in intf_obj.children:
                desc = child.re_match_typed(description_re)
                if desc != "":
                    intf_configs[intf_name]["name"] = desc

                port_mode = child.re_match_typed(port_mode_re)
                if port_mode != "":
                    intf_configs[intf_name]["type"] = port_mode

                voice_vlan = child.re_match_typed(voice_vlan_re)
                if voice_vlan != "":
                    intf_configs[intf_name]["voiceVlan"] = voice_vlan

                data_vlan = child.re_match_typed(data_vlan_re)
                if data_vlan != "":
                    intf_configs[intf_name]["vlan"] = data_vlan

                trunk_native = child.re_match_typed(trunk_native_re)
                if trunk_native != "":
                    intf_configs[intf_name]["vlan"] = trunk_native

                vlan_allowed = child.re_match_typed(vlan_allowed_re)
                if vlan_allowed != "":
                    intf_configs[intf_name]["allowedVlans"] = vlan_allowed


    intf_count = len(intf_configs)
    CONSOLE.print(f"Found [blue]{intf_count} downlink interface configurations[/] to convert")

    return intf_configs

def check_default_gateway(meraki_svis):
    """
    Determine if a default gateway is already configured for the Meraki switch
    :parameter meraki_svis: List of already existing SVIs on the Meraki switch
    :return: Boolean value representing if a default gateway already exists on the Meraki switch
    """
    for svi in meraki_svis:
        if "defaultGateway" in svi:
            return True

    return False

def create_default_svi(vlan_info, default_gateway, dash, serial):
    """
    Set the default gateway vlan of the Meraki switch
    :param vlan_info: Dictionary containing info of VLAN containing default gateway
    :param default_gateway: IP address of default gateway
    :return: String of VLAN ID of the VLAN with the default gateway
    """
    # get possible ip addresses of VLAN subnet
    network = ipaddress.ip_network(vlan_info["subnet"])

    # default gateway in vlan subnet
    if ipaddress.ip_address(default_gateway) in network:
        CONSOLE.print(f"Setting the ip default-gateway to {default_gateway}")
        vlan_info["defaultGateway"] = default_gateway

        svi_response = dash.switch.createDeviceSwitchRoutingInterface(serial, **vlan_info)
        target_svi_id = vlan_info["vlanId"]

        return target_svi_id

    return None

def configure_meraki(api_key, default_gateway, serials, svi_data, shut_interfaces, intf_configs):
    """
    Configure the SVIs and downlink interfaces of the Meraki switches
    :param api_key: API key for connecting to Meraki dashboard
    :param default_gateway: String of the IP of the default gateway
    :param serials: List of Meraki switch serial numbers
    :param shut_interfaces: List of interfaces that are shutdown
    :param intf_configs: Dictionary of interfaces and their configurations
    :return: Nothing
    """
    # connect to Meraki dashboard
    dash = meraki.DashboardAPI(api_key, suppress_logging=True)
    # iterate through Meraki switch serials and configure the default gateway VLAN
    default_svi = ""
    for serial in serials:
        # get the existing SVI on the Meraki switch
        meraki_svi_response = dash.switch.getDeviceSwitchRoutingInterfaces(serial)

        meraki_svis = [str(svi["vlanId"]) for svi in meraki_svi_response]

        # if no default gateway on switch, create one
        if not check_default_gateway(meraki_svis):
            for vlan_info in svi_data.values():
                network = ipaddress.ip_network(vlan_info["subnet"])

                if ipaddress.ip_address(default_gateway) in network:
                    default_svi = create_default_svi(vlan_info, default_gateway, dash, serial)

                    if default_svi is None:
                        CONSOLE.print(f"[red]Error: {default_gateway} does not exist on SVI. Please ensure Default Gateway exists on exactly one import SVI.[/]")
                        CONSOLE.print(f"Cannot proceed without Default Gateway. Exiting program...")

                        return

    # remove SVI with default gateway from dictionary
    if default_svi != "":
        del svi_data[default_svi]
    else:
        CONSOLE.print(f"[red]Error: {default_gateway} does not exist on SVI. Please ensure Default Gateway exists on exactly one import SVI.[/]")
        CONSOLE.print(f"Cannot proceed without Default Gateway. Exiting program...")


    # configure the remaining VLANs on the Meraki switches
    vlan_count = len(svi_data)
    sw_count = len(serials)
    with Progress() as progress:
        overall_progress = progress.add_task("Overall Progress", total=vlan_count*sw_count, transient=True)
        vlan_counter = 1
        for vlan in svi_data:
            sw_counter = 1
            for serial in serials:
                progress.console.print(f"Configuring [bold blue]{vlan}[/] ({vlan_counter} of {vlan_count}) on Meraki switch [blue]{serial}[/] ({sw_counter} of {sw_count})...")
                svi_response = dash.switch.createDeviceSwitchRoutingInterface(serial, **svi_data[vlan])

                sw_counter += 1
                progress.update(overall_progress, advance=1)

            vlan_counter += 1

    # configure the downlink interfaces on the Meraki switches
    intf_count = len(intf_configs)
    with Progress() as progress:
        overall_progress = progress.add_task("Overall Progress", total=intf_count, transient=True)
        intf_counter = 1
        for intf in intf_configs:
            progress.console.print(f"Configuring [bold blue]Port {intf_configs[intf]['portId']}[/] on Meraki switch ({intf_counter} of {intf_count})...")
            if intf in shut_interfaces:
                intf_configs[intf]["enabled"] = False
            else:
                intf_configs[intf]["enabled"] = True

            # if "module" in the keys, then there are multiple switches in the stack
            if "module" in intf_configs[intf].keys():
                # switch_num will determine the index of the switch in the list of switches
                switch_num = intf_configs[intf]["module"]
                del intf_configs[intf]["module"]
            else:
                switch_num = 1

            intf_response = dash.switch.updateDeviceSwitchPort(serials[switch_num-1], **intf_configs[intf])
            intf_counter += 1
            progress.update(overall_progress, advance=1)

def main(argv):
    load_dotenv()

    CONSOLE.print(Panel.fit(f"Cisco Catalyst to Meraki MS Mirgation"))

    # get variable to determine if the script needs to ssh to the switch
    connect_ssh = os.getenv("CONNECT_SSH")

    # connect to the Catalyst switch, returns the show run output
    if connect_ssh.lower() == "true":
        CONSOLE.print(Panel.fit(f"Get Catalyst Configuration (SSH)", title="Step 1"))
        config = get_config()

        # If config is None, the ssh attempt failed
        if config is None:
            print("There was an issue getting the switch configuration. Check the credentials.")

            return

        # write results to temp output file to be parsed
        config_file = "temp.txt"
        with open(config_file, 'w') as f:
            f.write(config)
    else:
        CONSOLE.print(Panel.fit(f"Get Catalyst Configuration from file", title="Step 1"))
        config_file = os.getenv("TEXT_FILE")
        CONSOLE.print(f"Config file found in [green]{config_file}[/]")

    # get API key from env file
    api_key = os.getenv("API_KEY")
    # get default gateway from env file
    default_gateway = os.getenv("DEFAULT_GATEWAY")
    # get serials from env file
    serials = json.loads(os.getenv("MS_SERIAL"))

    # parse out the svi data from the show run configuration
    CONSOLE.print(Panel.fit(f"Parse SVIs from Cataylst config", title="Step 2"))
    svi_data = parse_svi_data(config_file)
    # parse out the interfaces that are shut from the show run configuration
    CONSOLE.print(Panel.fit(f"Parse shut interfaces from Catalyst config", title="Step 3"))
    shut_interfaces = parse_shut_intf(config_file)
    # parse out the interface configurations from the show run configuration
    CONSOLE.print(Panel.fit(f"Parse all interface configurations from Catalyst config", title="Step 4"))
    interfaces = parse_intf_config(config_file, len(serials))

    CONSOLE.print(Panel.fit(f"Configure the Meraki switch with the parsed Catalyst interfaces", title="Step 5"))
    configure_meraki(api_key, default_gateway, serials, svi_data, shut_interfaces, interfaces)

    if connect_ssh.lower() == "true":
        # delete temp file
        os.remove("temp.txt")

    return

if __name__ == "__main__":
    sys.exit(main(sys.argv))
