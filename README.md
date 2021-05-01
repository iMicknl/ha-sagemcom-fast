
![screenshot of a device detail page in Home Assistant](https://raw.githubusercontent.com/iMicknl/ha-sagemcom-fast/master/media/sagemcom_fast_device_page.png)
[![GitHub release](https://img.shields.io/github/release/iMicknl/ha-sagemcom-fast.svg)](https://github.com/iMicknl/ha-sagemcom-fast/releases/)

# Sagemcom F@st - Home Assistant (work in progress)

This integration adds support for Sagemcom F@st routers to Home Assistant. Currently this is a work in progress where only a basic device_tracker is supported, however in the future sensors will be added as well.

Sagemcom F@st routers are used by many providers worldwide, but many of them did rebrand the router. Examples are the b-box from Proximus, Home Hub from bell and the Smart Hub from BT.

## Installation
### Manual

Copy the `custom_components/sagemcom_fast` to your `custom_components` folder. Reboot Home Assistant and install the Sagemcom F@st integration via the integrations config flow.

### HACS
Add this repository to HACS, search for the `Sagemcom F@st` integration and choose install. Reboot Home Assistant and install the Sagemcom F@st integration via the integrations config flow.

```
https://github.com/imicknl/ha-sagemcom-fast
```

## Usage

This integration can only be confgured via the Config Flow. Go to `Configuration -> Integrations -> Add Integration` and choose Sagemcom F@st. The prompt will ask you for your credentials. Please note that some routers require authentication, where others can login with `guest` username and an empty password.

The encryption method differs per device. Please refer to the table below to understand which option to select. If your device is not listed, please try both methods one by one.

## Supported devices

Have a look at the table below for more information about supported devices.

| Router Model          | Provider(s)          | Authentication Method | Comments                      |
|-----------------------|----------------------|-----------------------|-------------------------------|
| Sagemcom F@st 3864    | Optus                | sha512                | username: guest, password: "" |
| Sagemcom F@st 3865b   | Proximus (b-box3)    | md5                   |                               |
| Sagemcom F@st 3890V3  | Delta / Zeelandnet   | md5                   |                               |
| Sagemcom F@st 4360Air | KPN                  | md5                   |                               |
| Sagemcom F@st 5250    | Bell (Home Hub 2000) | md5                   | username: guest, password: "" |
| Sagemcom F@st 5280    |                      | sha512                |                               |
| Sagemcom F@st 5364    | BT (Smart Hub)       | md5                   | username: guest, password: "" |
| SagemCom F@st 5366SD  | Eir F3000            | md5                   |                               |
| Sagemcom F@st 5370e   | Telia                | sha512                |                               |
| Sagemcom F@st 5566    | Bell (Home Hub 3000) | md5                   | username: guest, password: "" |
| Sagemcom F@st 5655V2  | MásMóvil             | md5                   |                               |
| Sagemcom F@st 5657    |                      | md5                   |                               |
| Speedport Pro         | Telekom              | md5                   |                               |

> Contributions welcome. If you router model is supported by this package, but not in the list above, please create [an issue](https://github.com/iMicknl/ha-sagemcom-fast/issues/new) or pull request.

## Advanced

### Enable debug logging

The [logger](https://www.home-assistant.io/integrations/logger/) integration lets you define the level of logging activities in Home Assistant. Turning on debug mode will show more information to help us understand your issues.

```yaml
logger:
  default: critical
  logs:
    custom_components.sagemcom_fast: debug
```


### Device not supported / working correctly

If you are not able to use this integration with your Sagemcom F@st device, please create [an issue](https://github.com/iMicknl/ha-sagemcom-fast/issues/new) with as much information as possible. Turn on debug logging and share the logs in your issue description.
