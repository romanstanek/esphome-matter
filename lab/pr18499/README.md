# ESPHome PR #18499 comparison

PR: https://github.com/esphome/esphome/pull/18499
Pinned head: `62db95c7bb5f35790da4169a3d9f0add17e130e1`
PR ESPHome version: `2026.10.0-dev`.
External-component baseline uses ESPHome `2026.8.2` and the working tree's
Ethernet and gesture implementation. This compares complete implementations,
not an isolated change against an identical ESPHome core.

## Test configuration

`a2.yaml` uses the same LAN8720, GPIO15/GPIO2 relay outputs, GPIO36/GPIO39
inputs, debounce, and off-at-start behavior as the existing A2 fixture.
The PR discovers entities automatically rather than accepting explicit endpoint
mappings. Inputs remain internal and forward `on_press` to template buttons.
A virtual monochromatic light exercises level-control state without driving a
physical load. It does not establish real dimming or electrical behavior.

No physical dimmable load or Home Assistant Matter server has been made
available for this comparison. P4 availability has not been confirmed.

## Findings so far

| Check | External component baseline | PR pinned head |
| --- | --- | --- |
| A2 LAN8720 Ethernet | Hardware verified | Native build and A2 100 Mbps Ethernet startup passed |
| P4 IP101 Ethernet | Hardware verified | Configuration rejects ESP32P4 |
| A2 relay lights in Apple Home | User verified both relays/indicators | User reports working; Relay 1 command observed, separate Relay 2 check pending |
| Single/double/long input gestures | User verified | Source supports single press/release only |
| Commissioning / Apple Home | Verified, two fabrics on A2 | Apple Home control verified; fresh commissioning pending |
| Home Assistant Matter | Not tested | Not tested |
| Dimming | Not tested | Apple Home virtual levels 25%, 50%, 100% verified; physical dimming untested |

### Packaging failure

Installing the PR as a wheel with `pip install /tmp/esphome-pr18499` succeeds,
but the wheel omits `components/matter/external_platform/external_platform.cmake`.
The initial A2 build fails during CMake configuration:
`CONFIG_CHIP_EXTERNAL_PLATFORM_DIR is not set correctly!`
The Python component points that setting into its installed package directory.
Retrying from the unchanged source tree avoids this packaging omission.

### PlatformIO failure

The unchanged source build with `toolchain: platformio` fails in
`esp_matter/CMakeLists.txt` with `Failed to resolve component main`.
The PR attempts to append its override to `board_build.cmake_extra_args`,
but the actual build does not receive the needed application-component name.
`a2-platformio.yaml` preserves the failing configuration. The primary `a2.yaml`
now uses the PR default native `esp-idf` toolchain, which built successfully.

### Button semantics

`matter_button_endpoint.cpp` enables only MomentarySwitch and
MomentarySwitchRelease. Each ESPHome button press immediately schedules
InitialPress and ShortRelease. No long-press or multi-press features/events
are implemented there. `binary_sensor` entities map to contact/occupancy
sensors, so physical momentary inputs need the YAML forwarding used here.
This is a source finding, not a claim that Apple Home runtime tests passed.

## Reproduction

The PR source and its separate virtual environment currently live under
`/tmp/esphome-pr18499` and `/tmp/esphome-pr18499-venv`.
From the external component repository root:

```sh
PYTHONPATH=/tmp/esphome-pr18499 /tmp/esphome-pr18499-venv/bin/python -m esphome compile lab/pr18499/a2.yaml
```

The existing firmware configuration and build remain separate at
`examples/kincony-kc868-a2-v25-ethernet.yaml`.

### Native build result

The unchanged PR builds successfully from source with `toolchain: esp-idf`.
Application size is 1,006,000 bytes (`0xf59b0`), leaving 45% of its app partition
free. The original external-component A2 binary is 964,304 bytes; this is not a
like-for-like size comparison because the PR fixture also includes a virtual
dimmer and a different ESPHome core/topology.

Baseline repository HEAD at test time: `d7ea0239128bfa6e62539e5d2934b69f0ef42323`,
with the button gesture support and A2 fixtures included alongside this report.
The native PR firmware has been flashed and boots on the A2.
LAN8720 obtains 192.168.1.134 and IPv6 link-local addressing. It registers
two generic-switch buttons (endpoints 2/3), two relay lights (4/5), and the
virtual dimmer (6), under Aggregator endpoint 1. The endpoint layout differs
from the external component. Apple Home results are recorded below.
Startup logs include `BridgedDeviceBasicInfo: ReachableChanged: ScheduleWork
failed: ac` during endpoint creation before server startup. No startup crash
has been observed.

### First controller/input result

The user reports the A2 works with the PR firmware. Serial logs show presses
from both physical input adapters (button endpoints 2 and 3) and an incoming
Matter OnOff write to Relay 1 (endpoint 4, state=1). This confirms button
callbacks execute and a Matter relay command reaches the device. Separate
confirmation of Relay 2, fresh commissioning, and
Home Assistant remains pending; the general user report does not establish
all of those checks.

### Apple Home virtual dimming verified

User-driven Apple Home brightness changes reached Matter endpoint 6:

| Requested brightness | Received Matter level (0–254) | Virtual output |
| --- | --- | --- |
| 25% | 64 | 0.021 |
| 50% | 128 | 0.147 |
| 100% | 254 | 1.000 |

The generated light uses ESPHome's default gamma correction of 2.8, explaining
nonlinear output values. These are controller-to-firmware protocol/output-state
checks, not physical dimmer measurements.
