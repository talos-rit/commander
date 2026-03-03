from typing import Callable

from textual.color import Color
from textual.containers import HorizontalGroup
from textual.widgets import Label, Static

from .widgets.sparkline.custom_spark import Sparkline as CustomSparkline


class MetricDisplay(Static):
    """A widget to display single numerical metrics with a label."""

    CSS_PATH = "metric.tcss"

    # For some reason, float doesn't get converted to string when displayed
    metric = "0.00"
    cache = list()

    def __init__(
        self,
        poll_data: Callable[[], float],
        num_cached: int,
        rate: float,
        label: str,
        max_value: float = 60.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.metrics = {}
        self.poll_data = poll_data
        self.num_cached = num_cached
        self.label = label
        self.rate = rate or 0.5
        self.cache = list([0.0] * num_cached)
        self.max_value = max_value

    def compose(self):
        """Composes the widget layout."""
        spark = CustomSparkline(
            self.cache,
            classes="metric-sparkline",
            data_range=(0.0, self.max_value),
            min_color=Color(255, 0, 0),
            max_color=Color(0, 255, 0),
        )
        spark.styles.width = self.num_cached
        with HorizontalGroup():
            yield spark
            yield Label(self.metric, classes="metric-label-numeric")
            yield Label(self.label, classes="metric-label-text")

    def on_mount(self):
        """Starts polling for data when the widget is mounted."""
        self.update_metric()
        self.set_interval(self.rate, self.update_metric)

    def update_metric(self):
        """Polls for new data and updates the display."""
        new_value = self.poll_data()
        self.metric = f"{new_value:.2f}"
        self.cache.append(new_value)
        if len(self.cache) > self.num_cached:
            self.cache.pop(0)
        sparkline = self.query_one(".metric-sparkline", CustomSparkline)
        sparkline.data = self.cache
        sparkline.refresh()
        self.query_one(".metric-label-numeric", Label).update(self.metric)
