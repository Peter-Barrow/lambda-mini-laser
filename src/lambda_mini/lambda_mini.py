import sys
import serial
from time import sleep
from dataclasses import dataclass
from typing import Optional
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QMessageBox,
    QStatusBar,
)
from PyQt6.QtCore import Qt, QTimer

__all__ = [
    "LaserDeviceInfo",
    "LaserStatus",
    "LaserTemperature",
    "LaserPower",
    "LaserError",
    "laser_query",
    "laser_get_temperature",
    "laser_get_error",
    "laser_get_device_info",
    "laser_new",
    "laser_init",
    "laser_enable",
    "laser_disable",
    "laser_get_max_power",
    "laser_power_info",
    "laser_set_power",
]


@dataclass
class LaserDeviceInfo:
    """Device information and status from the laser system"""

    status: int
    operating_hours: float
    manufacturer: str
    device_name: str
    serial_number: str
    software_version: str
    emission_wavelength: int
    available_features: str
    acc_status: str
    apc_status: str


@dataclass
class LaserStatus:
    """Laser system status flags"""

    laser_on: bool
    interlock_open: bool
    error: bool
    temperature_ok: bool


@dataclass
class LaserTemperature:
    """Temperature readings from the laser"""

    current_temp: float
    min_temp: float
    max_temp: float


@dataclass
class LaserPower:
    """Power readings from the laser"""

    current_power: float
    min_power: float
    max_power: float


@dataclass
class LaserError:
    """Error status of the laser system"""

    error_code: int
    error_description: str


def laser_query(
    serial_connection: serial.Serial, query: str, timeout: float = 0.1
) -> str:
    """Send a query to the laser and return the response."""
    command = f"{query}\r\n".encode()
    serial_connection.write(command)
    serial_connection.timeout = timeout
    sleep(timeout)
    response = serial_connection.read_all().decode().strip()
    return response


def laser_get_status(serial_connection: serial.Serial) -> LaserStatus:
    """Get the current status of the laser system."""
    response = laser_query(serial_connection, "S?")
    parts = response.split()
    if len(parts) >= 2:
        status_code = int(parts[1], 16)
        # if status_code == '55.0':
        # else:
        return LaserStatus(
            laser_on=(status_code & 0x01) != 0,
            interlock_open=(status_code & 0x04) != 0,
            error=(status_code & 0x08) != 0,
            temperature_ok=(status_code & 0x10) != 0,
        )
    return LaserStatus(False, False, False, False)


def laser_get_temperature(
    serial_connection: serial.Serial,
) -> LaserTemperature:
    """Get temperature information from the laser."""
    current_response = laser_query(serial_connection, "T?")
    min_response = laser_query(serial_connection, "LTN?")
    max_response = laser_query(serial_connection, "LTP?")

    return LaserTemperature(
        current_temp=float(current_response.split()[-1]),
        min_temp=float(min_response.split()[-1]),
        max_temp=float(max_response.split()[-1]),
    )


error_descriptions = {
    0x01: "Temperature of laser head is too high",
    0x02: "Temperature of laser head is too low",
    0x04: "Temperature sensor connection is broken",
    0x08: "Temperature sensor cable is shorted",
    0x40: "Current for laser head is too high",
    0x80: "Internal error - laser system cannot be activated",
}


def laser_get_error(serial_connection: serial.Serial) -> Optional[LaserError]:
    """Read the active error status of the laser system."""
    response = laser_query(serial_connection, "E?")
    parts = response.split()
    if len(parts) >= 2:
        error_code = int(parts[1], 16)

        if error_code == 0:
            return None

        description = error_descriptions.get(
            error_code, f"Unknown error: 0x{error_code:02X}"
        )
        return LaserError(error_code=error_code, error_description=description)

    return None


def laser_get_device_info(serial_connection: serial.Serial) -> LaserDeviceInfo:
    """Get comprehensive device information and status."""
    status_response = laser_query(serial_connection, "S?")
    hours_response = laser_query(serial_connection, "R?")
    manufacturer_response = laser_query(serial_connection, "DM?")
    device_name_response = laser_query(serial_connection, "DT?")
    serial_response = laser_query(serial_connection, "DS?")
    software_response = laser_query(serial_connection, "DO?")
    wavelength_response = laser_query(serial_connection, "DW?")
    features_response = laser_query(serial_connection, "DF?")
    control_response = laser_query(serial_connection, "DC?")

    status_parts = status_response.split()
    status = int(status_parts[1], 16) if len(status_parts) >= 2 else 0

    hours_parts = hours_response.split()
    hours_str = hours_parts[1] if len(hours_parts) >= 2 else "0:00"
    if ":" in hours_str:
        h, m = hours_str.split(":")
        operating_hours = float(h) + float(m) / 60.0
    else:
        operating_hours = 0.0

    wavelength_parts = wavelength_response.split()
    wavelength = 0
    if len(wavelength_parts) >= 2:
        wavelength = float(wavelength_parts[1])

    control_parts = control_response.split(maxsplit=1)
    control_status = control_parts[1] if len(control_parts) >= 2 else ""
    acc_status = "ACC active" if "ACC" in control_status else "ACC inactive"
    apc_status = "APC active" if "APC" in control_status else "APC inactive"

    return LaserDeviceInfo(
        status=status,
        operating_hours=operating_hours,
        manufacturer=manufacturer_response.split(maxsplit=1)[1],
        device_name=device_name_response.split(maxsplit=1)[1],
        serial_number=serial_response.split(maxsplit=1)[1],
        software_version=software_response.split(maxsplit=1)[1],
        emission_wavelength=wavelength,
        available_features=features_response.split(maxsplit=1),
        acc_status=acc_status,
        apc_status=apc_status,
    )


def laser_new(laser_port: str = "") -> serial.Serial:
    conn = serial.Serial(
        port=laser_port,
        baudrate=57600,
        timeout=10,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS,
    )
    return conn


def laser_init(
    serial_connection: serial.Serial,
) -> (LaserDeviceInfo, LaserStatus, LaserTemperature, LaserPower, LaserError):
    command = "init\r\n".encode()
    serial_connection.write(command)

    laser_info = laser_get_device_info(serial_connection)
    laser_status = laser_get_status(serial_connection)
    laser_temperature = laser_get_temperature(serial_connection)
    laser_power = laser_power_info(serial_connection)
    laser_error = laser_get_error(serial_connection)

    return (
        laser_info,
        laser_status,
        laser_temperature,
        laser_power,
        laser_error,
    )


def laser_enable(
    serial_connection: serial.Serial,
    timeout: float = 5.0,
) -> (LaserDeviceInfo, LaserStatus, LaserTemperature, LaserPower, LaserError):
    laser_info = laser_get_device_info(serial_connection)
    laser_status = laser_get_status(serial_connection)
    laser_temperature = laser_get_temperature(serial_connection)
    laser_power = laser_power_info(serial_connection)
    laser_error = laser_get_error(serial_connection)

    laser_set_power(serial_connection, power_info=laser_power, power=0.0)
    command = "O=1\r\n".encode()
    serial_connection.write(command)
    sleep(1.0)

    return (
        laser_info,
        laser_status,
        laser_temperature,
        laser_power,
        laser_error,
    )


def laser_disable(serial_connection: serial.Serial, power_info: LaserPower):
    laser_set_power(serial_connection, power_info=power_info, power=0.0)
    command = "O=0\r\n".encode()
    serial_connection.write(command)
    sleep(1.0)


def laser_get_power(serial_connection: serial.Serial) -> float:
    """
    Query the current output power setting.

    Returns:
        Output power in mW
    """
    response = laser_query(serial_connection, "P?")
    # Response format: "COMMAND_SUCCESS value"
    parts = response.split()
    if len(parts) >= 2:
        return float(parts[1])
    return 0.0


def laser_get_max_power(serial_connection: serial.Serial) -> float:
    """
    Query the maximum output power.

    Returns:
        Maximum output power in mW
    """
    response = laser_query(serial_connection, "LP?")
    # Response format: "COMMAND_SUCCESS value"
    parts = response.split()
    if len(parts) >= 2:
        return float(parts[1])
    return 0.0


def laser_power_info(serial_connection: serial.Serial) -> LaserPower:
    current = laser_get_power(serial_connection)
    min_power = 0.0
    max_power = laser_get_max_power(serial_connection)
    return LaserPower(
        current_power=current,
        min_power=min_power,
        max_power=max_power,
    )


def laser_set_power(
    serial_connection: serial.Serial,
    power_info: LaserPower,
    power: float,
) -> LaserPower:
    if power < power_info.min_power:
        power = 0.0
    if power > power_info.max_power:
        power = power_info.max_power

    command = f"P={power}\r\n".encode()
    serial_connection.write(command)

    power_info.current_power = laser_get_power(serial_connection)
    return power_info


class LaserControlUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.serial_conn = None
        self.laser_enabled = False
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status_bar)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Laser Control")
        self.setFixedWidth(400)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()
        layout.setSpacing(20)
        central_widget.setLayout(layout)

        # Serial port connection
        port_layout = QHBoxLayout()
        port_label = QLabel("Serial Port:")
        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("e.g., COM3 or /dev/ttyUSB0")
        port_layout.addWidget(port_label)
        port_layout.addWidget(self.port_input)
        layout.addLayout(port_layout)

        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        layout.addWidget(self.connect_btn)

        # Enable/Disable button
        self.enable_btn = QPushButton("Enable Laser")
        self.enable_btn.setEnabled(False)
        self.enable_btn.clicked.connect(self.toggle_laser)
        layout.addWidget(self.enable_btn)

        # Power slider
        self.power_label = QLabel("Laser Power: 0.00")
        layout.addWidget(self.power_label)

        slider_layout = QHBoxLayout()
        self.power_slider = QSlider(Qt.Orientation.Horizontal)
        self.power_slider.setMinimum(0)
        self.power_slider.setMaximum(100)
        self.power_slider.setValue(0)
        self.power_slider.setEnabled(False)
        self.power_slider.valueChanged.connect(self.update_power_label)

        self.apply_btn = QPushButton("Apply Power")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.apply_power)

        slider_layout.addWidget(self.power_slider)
        slider_layout.addWidget(self.apply_btn)
        layout.addLayout(slider_layout)

        layout.addStretch()

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_label = QLabel("Status: Disconnected")
        self.error_label = QLabel("Error: None")
        self.temp_label = QLabel("Temp: -- °C")

        self.info_btn = QPushButton("Device Info")
        self.info_btn.setEnabled(False)
        self.info_btn.clicked.connect(self.show_device_info)

        self.status_bar.addWidget(self.status_label)
        self.status_bar.addWidget(QLabel("|"))
        self.status_bar.addWidget(self.error_label)
        self.status_bar.addWidget(QLabel("|"))
        self.status_bar.addWidget(self.temp_label)
        self.status_bar.addPermanentWidget(self.info_btn)

    def toggle_connection(self):
        if self.serial_conn is None:
            port = self.port_input.text().strip()
            if not port:
                QMessageBox.warning(
                    self,
                    "Error",
                    "Please enter a serial port.",
                )
                return

            try:
                self.serial_conn = laser_new(port)
                (
                    self.info,
                    self.status,
                    self.temp,
                    self.power,
                    self.error,
                ) = laser_init(self.serial_conn)
                self.connect_btn.setText("Disconnect")
                self.port_input.setEnabled(False)
                self.enable_btn.setEnabled(True)
                self.info_btn.setEnabled(True)
                self.status_timer.start(10000)  # Update status every second
                self.update_status_bar()
                self.power = laser_power_info(self.serial_conn)

                QMessageBox.information(self, "Success", "Connected to laser.")
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to connect: {str(e)}",
                )
        else:
            try:
                if self.laser_enabled:
                    laser_disable(self.serial_conn, self.power)
                    self.laser_enabled = False
                self.status_timer.stop()
                self.serial_conn.close()
                self.serial_conn = None
                self.connect_btn.setText("Connect")
                self.port_input.setEnabled(True)
                self.enable_btn.setEnabled(False)
                self.enable_btn.setText("Enable Laser")
                self.power_slider.setEnabled(False)
                self.apply_btn.setEnabled(False)
                self.info_btn.setEnabled(False)
                self.status_label.setText("Status: Disconnected")
                self.error_label.setText("Error: None")
                self.temp_label.setText("Temp: -- °C")
                QMessageBox.information(
                    self,
                    "Success",
                    "Disconnected from laser.",
                )
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Error during disconnect: {str(e)}"
                )

    def toggle_laser(self):
        if not self.laser_enabled:
            try:
                (
                    self.info,
                    self.status,
                    self.temp,
                    self.power,
                    self.error,
                ) = laser_enable(self.serial_conn)
                if self.power.max_power == 0.0:
                    self.power = laser_power_info(self.serial_conn)
                self.laser_enabled = True
                self.enable_btn.setText("Disable Laser")
                self.power = laser_power_info(self.serial_conn)
                self.power_slider.setEnabled(True)
                self.apply_btn.setEnabled(True)
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to enable laser: {str(e)}",
                )
        else:
            try:
                laser_disable(self.serial_conn, self.power)
                self.laser_enabled = False
                self.enable_btn.setText("Enable Laser")
                self.power_slider.setEnabled(False)
                self.apply_btn.setEnabled(False)
                self.power_slider.setValue(0)
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Failed to disable laser: {str(e)}"
                )

    def update_power_label(self, value):
        power = self.power_from_percent(value)
        self.power_label.setText(f"Laser Power: {power:.2f}")

    def update_status_bar(self):
        """
        Update the status bar with current laser status, error, and
            temperature.
        """
        if not self.serial_conn:
            return

        try:
            # Get status
            status = laser_get_status(self.serial_conn)
            status_text = []
            if status.laser_on:
                status_text.append("ON")
            else:
                status_text.append("OFF")
            if status.interlock_open:
                status_text.append("Interlock Open")
            if not status.temperature_ok:
                status_text.append("Temp Warning")

            self.status_label.setText(f"Status: {', '.join(status_text)}")

            # Get error
            self.error = laser_get_error(self.serial_conn)
            if self.error:
                self.error_label.setText(
                    f"Error: {self.error.error_description}",
                )
                self.error_label.setStyleSheet(
                    "color: red; font-weight: bold;",
                )
            else:
                self.error_label.setText("Error: None")
                self.error_label.setStyleSheet("")

            # Get temperature
            self.temperature = laser_get_temperature(self.serial_conn)
            self.temp_label.setText(f"Temp: {self.temp.current_temp:.1f} °C")

        except Exception:
            # If status update fails, don't crash the UI
            pass

    def show_device_info(self):
        """Display comprehensive device information in a dialog."""
        if not self.serial_conn:
            return

        try:
            self.info = laser_get_device_info(self.serial_conn)

            self.info_text = f"""
Device Information:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Manufacturer: {self.info.manufacturer}
Device Name: {self.info.device_name}
Serial Number: {self.info.serial_number}
Software Version: {self.info.software_version}

Emission Wavelength: {self.info.emission_wavelength} nm
Operating Hours: {self.info.operating_hours:.2f} hours

Status Code: 0x{self.info.status:02X}
Available Features: {self.info.available_features}

Control Status:
  {self.info.acc_status}
  {self.info.apc_status}
"""

            msg = QMessageBox(self)
            msg.setWindowTitle("Laser Device Information")
            msg.setText(self.info_text)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.exec()

        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to retrieve device info: {str(e)}"
            )

    def power_from_percent(self, percent: int) -> float:
        return self.power.max_power * (percent / 100)

    def percent_from_power(self, power: float) -> int:
        if self.power.max_power == 0.0:
            self.power = laser_get_power(self.serial_conn)
        return int(
            round(
                (power / self.power.max_power) * (100 / self.power.max_power),
            )
        )

    def apply_power(self):
        if self.serial_conn and self.laser_enabled:
            try:
                power_percentage = self.power_slider.value()
                power = self.power_from_percent(power_percentage)
                laser_set_power(self.serial_conn, self.power, power)
                self.power = laser_power_info(self.serial_conn)
                QMessageBox.information(
                    self,
                    "Success",
                    f"Power set to {power:.2f}",
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to set power: {str(e)}",
                )

    def closeEvent(self, event):
        if self.serial_conn:
            try:
                if self.laser_enabled:
                    laser_disable(self.serial_conn, self.power)
                self.serial_conn.close()
            except:
                pass
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = LaserControlUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
