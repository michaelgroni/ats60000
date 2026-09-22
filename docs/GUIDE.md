# ATS-Mini Remote Control – Guide for Windows Users

This program controls your **ATS-Mini radio** over Wi-Fi – no cables, no
installation, and no computer skills required.

Note: under **View → Language** you can switch the program window to
German or English at any time. This guide describes the English
interface.

## Installation

1. Open the program page on GitHub:
   [github.com/michaelgroni/ats60000/releases](https://github.com/michaelgroni/ats60000/releases)
2. On that page, in the **Latest** section (newest release), download
   the EXE file offered there -- in the example it is called
   **ATS-Mini-Remote-0.3.exe**, with newer versions correspondingly
   **ATS-Mini-Remote-<version-number>.exe**
   (for example into your *Downloads* folder).
3. That's it. The file does not need to be unzipped and nothing needs to
   be installed. Keep it in a permanent place, for example on your
   desktop.

### The first Windows warning

The very first time you start it, Windows may show a blue notice:
*"Windows protected your PC."*

This is normal: Windows does not know the program yet. Click
**More info** and then **Run anyway**. The program will start normally.

## Preparing the radio

The radio must be connected to your Wi-Fi and have remote control
switched on:

1. On the radio: **Settings → Wi-Fi** → choose *AP Only*, *AP+Connect*
   or *Connect*.
2. On the radio: **Settings → TCP Port** → choose *Ad hoc*.

## Connecting

1. Start the downloaded file (e.g. **ATS-Mini-Remote-0.3.exe**) with a double
   click.
2. In the **Host** field, enter the radio's address. This is usually
   `atsmini.local`. Alternatively, the address (a number like
   `192.168.1.42`) is shown on the radio's display while it is
   connected to Wi-Fi.
3. The **Port** field already contains the correct number (60000) –
   please leave it as it is.
4. Click **Connect**.

The program also tries to reach the radio on its own when it starts
(automatic connection attempt). If that fails, nothing bad happens –
simply click **Connect** yourself.

The program now shows the radio's status at the bottom of the window,
for example the battery voltage. The frequency display at the top uses
fixed digit cells: the decimal point always stays in the same place
when you tune, and empty leading cells stay dark.

## Operating the program

### Setting the frequency

- **Type a number:** Enter the frequency in the field at the top,
  for example `7.2` with the unit *MHz*, and click **Set**.
- **Step by step:** Use the **◀** and **▶** buttons next to *Frequency*
  to move up and down in small steps – just like the dial on the
  radio.

### Other settings

Each row (**Step, Band, Mode, Bandwidth, AGC/Attn**) also has **◀** and
**▶** buttons: use them to move the values up and down, as you know
from the radio's menu.

### Volume

The **Volume** slider sets the radio's volume. The new value is sent
when you release the slider.

### Squelch

The **Squelch** (AM and FM only) mutes distracting noise when barely
any signal is arriving. Set the sensitivity on the slider and tick the
check box next to it. When the signal drops too far, the radio goes
briefly silent; when the signal returns, the volume is restored. In SSB
modes the squelch is greyed out – it does not work there.

### Reading signal strength (S-meter)

On the right you see a display like an old-fashioned meter with a
needle:

- **Level**: how strong the incoming signal is (in dBµV)
- **S-value**: the usual shortwave reading like *S9*, also *S9+20*
  and above
- **SNR**: how clean the signal is (in dB)

Click the small round buttons to switch between the three readings.
The red area on the right means: very strong signal.

### Spectrum (an overview of the whole band)

Click **Start sweep** to scan the entire band once. The program then shows a
picture where you can see at a glance where strong stations are:

- Green area = current signal strength
- Lighter green area = earlier signal peaks (a station may have been
  stronger during a previous sweep)

Click anywhere in the picture to tune the radio directly to that
frequency. This works even if no sweep has run yet – the program then
uses the range of the current band. Below the picture you can watch the
progress while the program measures.

### Memory slots

The **Memory slots** table next to the settings always shows what is
stored in the radio:

- **Show ($)**: lists the stations stored in the radio
- **Save current station (#)**: stores the current station in a free slot
- **Clear**: removes a slot (frequency 0)

Recalling a stored station is done on the radio itself – the remote
control protocol has no command for that.

### Other buttons

- **Screenshot**: takes a picture of the radio's display and can save
  it as a file
- **Disconnect**: ends the connection to the radio

### Log (expert view)

Under **View → Show log** you can show a table in which the program
records all communication with the radio (time, source, message). You
do not need it for normal operation – it helps with troubleshooting.

## If something does not work

| Problem | Solution |
|---|---|
| "Not connected" | Click **Connect** and check that the address is correct. |
| Connection fails | Radio and computer must be on the same Wi-Fi. Check on the radio: **Settings → Wi-Fi** and **Settings → TCP Port → Ad hoc**. |
| Radio does not respond | Switch the radio off and on again, then reconnect. |
| Windows warns at startup | Normal on the very first start only: **More info** → **Run anyway**. |

## Closing the program

Simply close the window. The settings on the radio remain unchanged.
