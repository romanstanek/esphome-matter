# KinCony KC868-A2 revision 2.5

Use [the A2 configuration](../examples/kincony-kc868-a2-v25-ethernet.yaml) for the
classic ESP32 KC868-A2 revision 2.5, not the ESP32-S3 A2v3.

The [manufacturer pinout and revision clarification](https://www.kincony.com/forum/showthread.php?tid=2691&page=2)
retain relay GPIO15/GPIO2, input GPIO36/GPIO39, and LAN8720 Ethernet
(MDC23, MDIO18, clock output GPIO17, PHY address 0). The configuration assumes
4 MB flash; verify the detected flash size before uploading to a new board.

| Matter endpoint | Function |
| --- | --- |
| 1 | Relay 1 as an on/off light |
| 2 | Relay 2 as an on/off light |
| 3 | DI1 momentary button: single, double, long press |
| 4 | DI2 momentary button: single, double, long press |

Relays use `ALWAYS_OFF` on startup. This is a software startup setting, not a
hardware guarantee against transient relay activation during reset. Initial
bench tests should use empty relay terminals. Inputs are independent of outputs;
assign their actions in the Matter controller. Input GPIO36/39 use the board's
input circuitry and do not support internal pull-ups.

Build with `esphome compile examples/kincony-kc868-a2-v25-ethernet.yaml`.
Upload over the board's detected USB serial port. Obtain its generated Matter
pairing code from the boot log; this is a separate accessory from the P4 board.

Initial A2 hardware validation: detected ESP32-D0WD-V3 revision 3.1 and 4 MB
flash; firmware uploaded and verified successfully. LAN8720 connected at
100 Mbps with IPv4 and IPv6 link-local addressing, and Matter commissioning
opened successfully. Subsequent logs confirmed completed commissioning and
two committed Matter fabrics with operational CASE sessions. The user confirmed
both relays click and their indicators follow on/off commands from Apple Home.
The user subsequently reported the buttons working too. Individual gesture
results were not separately recorded on this board; single, double, and long
press were each confirmed on the P4.
