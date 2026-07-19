![screenshot of a device detail page in Home Assistant](https://raw.githubusercontent.com/iMicknl/ha-sagemcom-fast/main/media/sagemcom_fast_device_page.png)
[![GitHub release](https://img.shields.io/github/release/iMicknl/ha-sagemcom-fast.svg)](https://github.com/iMicknl/ha-sagemcom-fast/releases/)
[![HA integration usage](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.sagemcom_fast.total)](https://analytics.home-assistant.io/custom_integrations.json)

# Sagemcom F@st integration for Home Assistant

This custom integration connects supported Sagemcom F@st routers to Home Assistant through the local `sagemcom_api` interface. It tracks connected devices and exposes gateway, WAN, DSL, and DOCSIS information when the router firmware provides the required API paths.

Sagemcom F@st routers are used and often rebranded by providers worldwide. Examples include the Proximus b-box, Bell Home Hub, Salt Fibre Box X6, and BT Smart Hub. Provider firmware differs considerably, so optional entities are discovered per router instead of being assumed from the model number.

## Features

- Device trackers for wired and wireless clients
- Reboot button with serialized router-session handling
- Gateway uptime and active client-count sensors
- WAN connectivity binary sensor
- DSL upstream and downstream rate sensors
- DOCSIS signal, power, and codeword diagnostic sensors
- Redacted integration diagnostics for troubleshooting
- English and Hungarian user-interface translations

### Entities

The integration always provides client tracking, active-client counts, and the reboot button. Other entities are created only after the corresponding API capability has been read successfully.

| Entity | Default | Requirement |
| ------ | ------- | ----------- |
| Client device trackers | Enabled | Host listing supported by the router |
| Reboot button | Enabled | Supported Sagemcom API |
| Active clients, wired clients, wireless clients | Enabled | Host listing supported by the router |
| Uptime | Enabled | `Device/DeviceInfo/UpTime` |
| WAN connectivity | Enabled | Supported WAN interface status path |
| DSL downstream and upstream rate | Enabled | Corresponding DSL current-rate path |
| DOCSIS codeword totals and error percentage | Enabled | Complete locked downstream collection with codeword counters |
| Per-channel DOCSIS downstream SNR and power | Disabled | Supported DOCSIS downstream collection |
| Per-channel DOCSIS upstream power | Disabled | Supported DOCSIS upstream collection |

The per-channel DOCSIS sensors are disabled by default because a cable gateway can create many entities. Enable the channels you need from the gateway device page in Home Assistant.

## Known limitations / issues

- API paths and response shapes can differ between provider firmware versions. An entity being absent usually means that its capability probe was not supported.
- The DOCSIS plural collection paths are confirmed on `FAST3896_MAGYAR_sw23.83.19.23e`. Older sw18 firmware is known to expose the same hierarchy through indexed channel paths, but plural collection reads still need confirmation.
- Aggregate DOCSIS codeword values are cumulative router counters. They are not marked as `total_increasing` until independent channel resets have been validated.
- Ziggo F3896LG-ZG firmware using the bearer-authenticated `/rest/v1` API is not currently supported by this integration.

## Installation

### Manual

Copy `custom_components/sagemcom_fast` into the `custom_components` directory in your Home Assistant configuration. Restart Home Assistant, then add the Sagemcom F@st integration from **Settings → Devices & services**.

### HACS

Add this repository as a custom repository to HACS as described in the [HACS documentation](https://hacs.xyz/docs/faq/custom_repositories). Search for `Sagemcom F@st`, install it, and restart Home Assistant. Then add the integration from **Settings → Devices & services**.

```
https://github.com/imicknl/ha-sagemcom-fast
```

## Usage

This integration is configured through the user interface. Go to **Settings → Devices & services → Add integration** and choose Sagemcom F@st. Enter the router address and web-interface credentials. Some routers require an administrator account, while others accept the `guest` username with an empty password.

The first login can take up to a minute while the integration detects the encryption method used by the router. The polling interval can be changed afterward from the integration's **Configure** dialog; the minimum is 10 seconds.

Home Assistant displays the integration in the language selected for each user. Hungarian is available automatically when the user's Home Assistant language is set to Magyar.

## Supported devices

Have a look at the table below for more information about supported devices. The Sagemcom F@st series is used by multiple cable companies, where some cable companies did rebrand the router. Examples are the b-box from Proximus, Home Hub from bell and the Smart Hub from BT.

| Router Model          | Provider(s)          | Authentication Method | Comments                      |
| --------------------- | -------------------- | --------------------- | ----------------------------- |
| Sagemcom F@st 3864    | Optus                | sha512                | username: guest, password: "" |
| Sagemcom F@st 3865b   | Proximus (b-box3)    | md5                   |                               |
| Sagemcom F@st 3890V3  | Delta / Zeelandnet   | sha512                |                               |
| Sagemcom F@st 3896    | Magyar Telekom      | sha512                | username: admin; sw23 DOCSIS sensors confirmed |
| Sagemcom F@st 4360Air | KPN                  | md5                   |                               |
| Sagemcom F@st 4353    | Belong Gateway       | md5                   | username: admin, password: "" |
| Sagemcom F@st 5250    | Bell (Home Hub 2000) | md5                   | username: guest, password: "" |
| Sagemcom F@st 5280    |                      | sha512                |                               |
| Sagemcom F@st 5359    | KPN (Box 12)         | sha512                | username: admin               |
| Sagemcom F@st 5364    | BT (Smart Hub)       | md5                   | username: guest, password: "" |
| SagemCom F@st 5366SD  | Eir F3000            | md5                   |                               |
| Sagemcom F@st 5370e   | Telia                | sha512                |                               |
| Sagemcom F@st 5380    | TDC                  | md5                   |                               |
| Sagemcom F@st 5566    | Bell (Home Hub 3000) | md5                   | username: guest, password: "" |
| Sagemcom F@st 5688T   | Salt (FibreBox_X6)   | sha512                | username: admin               |
| Sagemcom F@st 5689    | Bell (Home Hub 4000) | md5                   | username: admin, password: "" |
| Sagemcom F@st 5655V2  | MásMóvil             | md5                   |                               |
| Sagemcom F@st 5657IL  |                      | md5                   |                               |
| Speedport Pro         | Telekom              | md5                   | username: admin               |

> Contributions are welcome. If your router works but is missing from the table, please [open an issue](https://github.com/iMicknl/ha-sagemcom-fast/issues/new) or submit a pull request. A model in this table does not imply that every optional sensor is supported by every provider firmware.

## Advanced

### Enable debug logging

The [logger](https://www.home-assistant.io/integrations/logger/) integration lets you define the level of logging activities in Home Assistant. Turning on debug mode will show more information to help us understand your issues.

```yaml
logger:
  default: critical
  logs:
    custom_components.sagemcom_fast: debug
```

Do not publish logs without inspecting them for addresses, host names, or other private information.

### Download diagnostics

Open **Settings → Devices & services**, select Sagemcom F@st, open the integration menu, and choose **Download diagnostics**. The diagnostics include firmware metadata, supported aggregate channel counts, and active-client totals. Credentials, the router address, client identities, and raw router data are redacted or omitted.

### Device not supported / working correctly

If the integration cannot connect, or an expected optional entity is absent, please create [an issue](https://github.com/iMicknl/ha-sagemcom-fast/issues/new) containing:

- Router model, hardware version, software version, and provider
- Whether the integration itself loads successfully
- Which entities or capabilities are missing
- The downloaded, inspected integration diagnostics
- Relevant debug messages with private values removed

Do not attach complete router-tree dumps, credentials, public IP addresses, MAC addresses, or client details.

### Collect an unsupported-router profile

The repository includes a read-only contributor tool for gathering the API information needed to support another router or firmware without collecting client details or raw router dumps. Run it from a clone of this repository with the runtime dependency installed:

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts/router_profile.py --output sagemcom-profile.json
```

Linux or macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/router_profile.py --output sagemcom-profile.json
```

The tool prompts for the router address, username, and password. Password input is hidden and there is deliberately no `--password` command-line option. Use `--encryption MD5` or `--encryption SHA512` if the method is already known. Automatic detection can make several authentication attempts, so supplying a known method reduces the risk of a temporary router login lockout.

The collector:

- Uses only fixed, read-only capability and schema XPath probes
- Never requests the host/client list or the complete router tree
- Never invokes a write, reboot, Wi-Fi change, or other command
- Keeps credentials and the router address out of the profile
- Excludes gateway serial and MAC addresses, client data, channel UIDs, and raw metric or DOCSIS channel values
- Retains only firmware-identifying metadata, supported/missing status, field names and types, collection counts, safe protocol errors, and aggregate benchmark timings

Generated `sagemcom-profile*.json` files are ignored by Git so they cannot be committed accidentally. Inspect the JSON before attaching it to an issue. Its top-level `privacy.excluded` list documents the data classes the collector promises to omit. If anything unexpected appears, do not share it and open an issue describing only the field name.

Run `python scripts/router_profile.py --help` for SSL, certificate verification, benchmark, output, and overwrite options.

## Development and testing

Runtime dependencies are kept in both `requirements.txt` and the integration manifest. Development and CI dependencies are listed in `requirements_dev.txt`.

```bash
python -m pip install -r requirements_dev.txt
python -m pytest tests
pre-commit run --all-files
```

The unit tests exercise API lifecycle handling, capability discovery, snapshot updates, entity behavior, translations, contributor-profile privacy, and sanitized firmware fixtures without starting a Home Assistant instance or connecting to a router. Local virtual environments, credentials, and private development probes must remain outside version control.
