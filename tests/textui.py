import sys
from time import sleep
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Header,
    Footer,
    Static,
    Input,
    Button,
    Label,
    ProgressBar,
)
from textual.binding import Binding
from textual.reactive import reactive
from textual import work
from textual.worker import Worker, WorkerState

# Import the laser control functions
from lambda_mini.lambda_mini import (
    laser_new,
    laser_init,
    laser_enable,
    laser_disable,
    laser_get_status,
    laser_get_temperature,
    laser_get_error,
    laser_get_device_info,
    laser_power_info,
    laser_set_power,
    LaserDeviceInfo,
    LaserStatus,
    LaserTemperature,
    LaserPower,
    LaserError,
)


class StatusDisplay(Static):
    """Display for status information."""

    status_text = reactive("Disconnected")
    error_text = reactive("None")
    temp_text = reactive("-- °C")

    def render(self) -> str:
        return f"[dim]Status:[/dim] {self.status_text} [dim]│[/dim] [dim]Error:[/dim] {self.error_text} [dim]│[/dim] [dim]Temp:[/dim] {self.temp_text}"


class DeviceInfoPanel(Static):
    """Side panel showing device information."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_info = None

    def update_info(self, info: LaserDeviceInfo) -> None:
        """Update the device information display."""
        self.device_info = info
        self.update(self.render_info())

    def render_info(self) -> str:
        """Render the device information."""
        if not self.device_info:
            return "[dim]No device connected[/dim]"

        info = self.device_info
        return f"""[bold cyan]Device Info[/bold cyan]
[dim]─────────────────[/dim]

[yellow]Manufacturer[/yellow]
{info.manufacturer}

[yellow]Device[/yellow]
{info.device_name}

[yellow]Serial[/yellow]
{info.serial_number}

[yellow]Software[/yellow]
{info.software_version}

[yellow]Wavelength[/yellow]
{info.emission_wavelength} nm

[yellow]Hours[/yellow]
{info.operating_hours:.2f}h

[yellow]Status[/yellow]
0x{info.status:02X}

[yellow]Control[/yellow]
{info.acc_status}
{info.apc_status}
"""


class PowerSlider(Static):
    """Custom power slider widget."""

    value = reactive(0)
    max_value = reactive(100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_power = 0.0
        self.max_power = 100.0

    def compose(self) -> ComposeResult:
        yield Label(f"[dim]Power:[/dim] {self.current_power:.2f} mW", id="power-label")
        yield ProgressBar(total=100, show_eta=False, id="power-bar")

    def watch_value(self, value: int) -> None:
        """Update display when value changes."""
        power = self.max_power * (value / 100.0)
        self.current_power = power
        self.query_one("#power-label", Label).update(
            f"[dim]Power:[/dim] {power:.2f} mW"
        )
        self.query_one("#power-bar", ProgressBar).update(progress=value)

    def set_max_power(self, max_power: float) -> None:
        """Set the maximum power value."""
        self.max_power = max_power

    def get_power(self) -> float:
        """Get the current power in mW."""
        return self.max_power * (self.value / 100.0)


class LaserControlApp(App):
    """A Textual app for laser control."""

    CSS = """
    Screen {
        background: $surface;
    }

    Header {
        background: $boost;
        color: $text;
        border-bottom: heavy $primary;
    }

    Footer {
        background: $boost;
        color: $text;
        border-top: heavy $primary;
    }

    #main-layout {
        width: 100%;
        height: 100%;
    }

    #left-panel {
        width: 2fr;
        height: 100%;
        padding: 1 2;
    }

    #right-panel {
        width: 1fr;
        height: 100%;
        border-left: heavy $primary;
        padding: 1 2;
        display: none;
    }

    #right-panel.visible {
        display: block;
    }

    .section {
        border: heavy $primary;
        padding: 1;
        margin-bottom: 1;
        background: $panel;
    }

    .section-title {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }

    #port-input {
        width: 100%;
        border: tall $primary;
        background: $surface;
        margin-top: 1;
    }

    #port-input:focus {
        border: tall $accent;
    }

    Button {
        width: 100%;
        margin-top: 1;
        border: tall $primary;
    }

    Button:hover {
        background: $primary 20%;
    }

    Button:focus {
        border: tall $accent;
    }

    #status-display {
        width: 100%;
        height: 3;
        border: heavy $primary;
        padding: 1;
        background: $panel;
    }

    PowerSlider {
        width: 100%;
        margin-top: 1;
    }

    #power-label {
        text-align: left;
        width: 100%;
        margin-bottom: 1;
    }

    #power-bar {
        width: 100%;
        border: tall $primary;
    }

    #device-info-panel {
        height: 100%;
        background: $panel;
        border: heavy $primary;
        padding: 1;
        color: $text;
    }

    ProgressBar > .bar--complete {
        color: $accent;
    }

    ProgressBar > .bar--bar {
        color: $primary;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("c", "connect", "Connect/Disconnect"),
        Binding("e", "toggle_enable", "Enable/Disable"),
        Binding("up", "increase_power", "Power +", show=False),
        Binding("down", "decrease_power", "Power -", show=False),
        Binding("a", "apply_power", "Apply Power"),
    ]

    def __init__(self):
        super().__init__()
        self.serial_conn = None
        self.laser_enabled = False
        self.power_info = None
        self.update_worker = None

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        with Horizontal(id="main-layout"):
            with Vertical(id="left-panel"):
                with Vertical(classes="section"):
                    yield Label("[bold]Connection[/bold]", classes="section-title")
                    yield Label("[dim]Serial Port[/dim]")
                    yield Input(
                        placeholder="/dev/ttyUSB0 or COM3",
                        id="port-input",
                    )
                    yield Button("Connect", id="connect-btn", variant="primary")

                with Vertical(classes="section"):
                    yield Label("[bold]Laser Control[/bold]", classes="section-title")
                    yield Button(
                        "Enable Laser",
                        id="enable-btn",
                        variant="success",
                        disabled=True,
                    )
                    yield PowerSlider()
                    yield Button(
                        "Apply Power",
                        id="apply-btn",
                        variant="warning",
                        disabled=True,
                    )

                yield StatusDisplay(id="status-display")

            with VerticalScroll(id="right-panel"):
                yield DeviceInfoPanel(id="device-info-panel")

        yield Footer()

    def on_mount(self) -> None:
        """Called when app starts."""
        self.title = "Laser Control"
        self.sub_title = "Terminal Interface"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "connect-btn":
            self.action_connect()
        elif event.button.id == "enable-btn":
            self.action_toggle_enable()
        elif event.button.id == "apply-btn":
            self.action_apply_power()

    def action_connect(self) -> None:
        """Connect or disconnect from the laser."""
        if self.serial_conn is None:
            port = self.query_one("#port-input", Input).value.strip()
            if not port:
                self.notify("Please enter a serial port", severity="warning")
                return

            try:
                self.serial_conn = laser_new(port)
                info, status, temp, power, error = laser_init(self.serial_conn)
                self.power_info = power

                # Update device info panel
                self.query_one("#device-info-panel", DeviceInfoPanel).update_info(info)
                self.query_one("#right-panel").add_class("visible")

                # Update UI
                self.query_one("#connect-btn", Button).label = "Disconnect"
                self.query_one("#connect-btn", Button).variant = "error"
                self.query_one("#port-input", Input).disabled = True
                self.query_one("#enable-btn", Button).disabled = False

                # Set max power for slider
                self.query_one(PowerSlider).set_max_power(power.max_power)

                # Start status updates
                self.start_status_updates()

                self.notify("Connected to laser", severity="information")
            except Exception as e:
                self.notify(f"Failed to connect: {str(e)}", severity="error")
        else:
            try:
                # Stop updates
                if self.update_worker:
                    self.update_worker.cancel()

                if self.laser_enabled:
                    laser_disable(self.serial_conn, self.power_info)
                    self.laser_enabled = False

                self.serial_conn.close()
                self.serial_conn = None

                # Hide device info panel
                self.query_one("#right-panel").remove_class("visible")

                # Update UI
                self.query_one("#connect-btn", Button).label = "Connect"
                self.query_one("#connect-btn", Button).variant = "primary"
                self.query_one("#port-input", Input).disabled = False
                self.query_one("#enable-btn", Button).disabled = True
                self.query_one("#enable-btn", Button).label = "Enable Laser"
                self.query_one("#apply-btn", Button).disabled = True
                self.query_one(PowerSlider).value = 0

                # Reset status
                status_display = self.query_one("#status-display", StatusDisplay)
                status_display.status_text = "Disconnected"
                status_display.error_text = "None"
                status_display.temp_text = "-- °C"

                self.notify("Disconnected from laser", severity="information")
            except Exception as e:
                self.notify(f"Error during disconnect: {str(e)}", severity="error")

    def action_toggle_enable(self) -> None:
        """Enable or disable the laser."""
        if not self.serial_conn:
            return

        if not self.laser_enabled:
            try:
                info, status, temp, power, error = laser_enable(self.serial_conn)
                self.power_info = power
                self.laser_enabled = True

                # Update UI
                self.query_one("#enable-btn", Button).label = "Disable Laser"
                self.query_one("#enable-btn", Button).variant = "error"
                self.query_one("#apply-btn", Button).disabled = False
                self.query_one(PowerSlider).set_max_power(power.max_power)

                self.notify("Laser enabled", severity="warning")
            except Exception as e:
                self.notify(f"Failed to enable laser: {str(e)}", severity="error")
        else:
            try:
                laser_disable(self.serial_conn, self.power_info)
                self.laser_enabled = False

                # Update UI
                self.query_one("#enable-btn", Button).label = "Enable Laser"
                self.query_one("#enable-btn", Button).variant = "success"
                self.query_one("#apply-btn", Button).disabled = True
                self.query_one(PowerSlider).value = 0

                self.notify("Laser disabled", severity="information")
            except Exception as e:
                self.notify(f"Failed to disable laser: {str(e)}", severity="error")

    def action_apply_power(self) -> None:
        """Apply the current power setting."""
        if self.serial_conn and self.laser_enabled:
            try:
                slider = self.query_one(PowerSlider)
                power = slider.get_power()
                laser_set_power(self.serial_conn, self.power_info, power)
                self.power_info = laser_power_info(self.serial_conn)
                self.notify(f"Power set to {power:.2f} mW", severity="information")
            except Exception as e:
                self.notify(f"Failed to set power: {str(e)}", severity="error")

    def action_increase_power(self) -> None:
        """Increase power by 5%."""
        if self.query_one("#apply-btn", Button).disabled:
            return
        slider = self.query_one(PowerSlider)
        slider.value = min(100, slider.value + 5)

    def action_decrease_power(self) -> None:
        """Decrease power by 5%."""
        if self.query_one("#apply-btn", Button).disabled:
            return
        slider = self.query_one(PowerSlider)
        slider.value = max(0, slider.value - 5)

    @work(exclusive=True)
    async def start_status_updates(self) -> None:
        """Worker to update status periodically."""
        while self.serial_conn:
            try:
                # Get status
                status = laser_get_status(self.serial_conn)
                status_parts = []
                if status.laser_on:
                    status_parts.append("[green]ON[/green]")
                else:
                    status_parts.append("[dim]OFF[/dim]")
                if status.interlock_open:
                    status_parts.append("[red]Interlock Open[/red]")
                if not status.temperature_ok:
                    status_parts.append("[yellow]Temp Warning[/yellow]")

                # Get error
                error = laser_get_error(self.serial_conn)
                if error:
                    error_text = f"[red]{error.error_description}[/red]"
                else:
                    error_text = "[dim]None[/dim]"

                # Get temperature
                temp = laser_get_temperature(self.serial_conn)

                # Update status display
                status_display = self.query_one("#status-display", StatusDisplay)
                status_display.status_text = " ".join(status_parts)
                status_display.error_text = error_text
                status_display.temp_text = f"{temp.current_temp:.1f} °C"

                # Update device info
                info = laser_get_device_info(self.serial_conn)
                self.query_one("#device-info-panel", DeviceInfoPanel).update_info(info)

            except Exception:
                pass

            # Sleep for 10 seconds
            await self.sleep(10)


def main():
    app = LaserControlApp()
    app.run()


if __name__ == "__main__":
    main()
