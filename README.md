# lambda_mini

A Python package and GUI tool for controlling and monitoring a [RGB-lasersystems lambda mini](https://rgb-lasersystems.com/products/) over a serial connection.  
It provides functions for querying device information, status, errors, power, and temperature, along with a PyQt-based interface for interactive use.

![gui](screenshot.png)

## Installation

Clone and install directly from GitHub:

```bash
pip install git+https://github.com/your-username/lambda_mini.git
````

## Usage

### As a library

You can import the package and use its functions directly:

```python
from lambda_mini import laser_new, laser_get_device_info

conn = laser_new("COM3")  # or "/dev/ttyUSB0" on Linux
info = laser_get_device_info(conn)
print(info)
```

### As a GUI

To launch the graphical interface:

```bash
python -m lambda_mini.lambda_mini
```

This will open a window where you can connect to the laser, enable/disable it, adjust power, and view device status.

## Requirements

* Python 3.9+
* [PyQt6](https://pypi.org/project/PyQt6/)
* [pyserial](https://pypi.org/project/pyserial/)

```

```
