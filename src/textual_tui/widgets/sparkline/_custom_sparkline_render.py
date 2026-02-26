from __future__ import annotations

from fractions import Fraction
from typing import Callable, Generic, Iterable, Sequence, TypeVar

from rich.color import Color
from rich.console import Console, ConsoleOptions, RenderResult
from rich.measure import Measurement
from rich.segment import Segment
from rich.style import Style
from textual.renderables._blend_colors import blend_colors

T = TypeVar("T", int, float)

SummaryFunction = Callable[[Sequence[T]], float]


class CustomSparklineRenderable(Generic[T]):
    """A sparkline representing a series of data.
    This is an extended version of the original sparkline that allows for a custom range to be set,
    so that the color interpolation is consistent even when the data range changes.

    Args:
        data: The sequence of data to render.
        width: The width of the sparkline/the number of buckets to partition the data into.
        height: The height of the sparkline in lines.
        min_color: The color of values equal to the min value in data.
        max_color: The color of values equal to the max value in data.
        data_range: The range of values to use for color interpolation. If None, the orginal method is used to determine the range based on the data.
        summary_function: Function that will be applied to each bucket.
    """

    BARS = "▁▂▃▄▅▆▇█"

    def __init__(
        self,
        data: Sequence[T],
        *,
        width: int | None,
        height: int | None = None,
        min_color: Color = Color.from_rgb(0, 255, 0),
        max_color: Color = Color.from_rgb(255, 0, 0),
        data_range: tuple[T, T] | None = None,
        summary_function: SummaryFunction[T] = max,
    ) -> None:
        self.data: Sequence[T] = data
        self.width = width
        self.height = height
        self.min_color = Style.from_color(min_color)
        self.max_color = Style.from_color(max_color)
        self.range = data_range
        self.summary_function: SummaryFunction[T] = summary_function

    @classmethod
    def _buckets(cls, data: list[T], num_buckets: int) -> Iterable[Sequence[T]]:
        """Partition ``data`` into ``num_buckets`` buckets. For example, the data
        [1, 2, 3, 4] partitioned into 2 buckets is [[1, 2], [3, 4]].

        Args:
            data: The data to partition.
            num_buckets: The number of buckets to partition the data into.
        """
        bucket_step = Fraction(len(data), num_buckets)
        for bucket_no in range(num_buckets):
            start = int(bucket_step * bucket_no)
            end = int(bucket_step * (bucket_no + 1))
            partition = data[start:end]
            if partition:
                yield partition

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        width = self.width or options.max_width
        height = self.height or 1

        len_data = len(self.data)
        if len_data == 0:
            for _ in range(height - 1):
                yield Segment.line()

            yield Segment("▁" * width, self.min_color)
            return
        if len_data == 1:
            for i in range(height):
                yield Segment("█" * width, self.max_color)

                if i < height - 1:
                    yield Segment.line()
            return

        bar_line_segments = len(self.BARS)
        bar_segments = bar_line_segments * height - 1

        minimum, maximum = self.get_min_max()
        extent = maximum - minimum or 1

        summary_function = self.summary_function
        min_color, max_color = self.min_color.color, self.max_color.color
        assert min_color is not None
        assert max_color is not None

        buckets = tuple(self._buckets(list(self.data), num_buckets=width))

        for i in reversed(range(height)):
            current_bar_part_low = i * bar_line_segments
            current_bar_part_high = (i + 1) * bar_line_segments

            bucket_index = 0.0
            bars_rendered = 0
            step = len(buckets) / width
            while bars_rendered < width:
                partition = buckets[int(bucket_index)]
                partition_summary = summary_function(partition)
                height_ratio = (partition_summary - minimum) / extent
                bar_index = int(height_ratio * bar_segments)

                if bar_index < current_bar_part_low:
                    bar = " "
                    with_color = False
                elif bar_index >= current_bar_part_high:
                    bar = "█"
                    with_color = True
                else:
                    bar = self.BARS[bar_index % bar_line_segments]
                    with_color = True

                if with_color:
                    bar_color = blend_colors(min_color, max_color, height_ratio)
                    style = Style.from_color(bar_color)
                else:
                    style = None

                bars_rendered += 1
                bucket_index += step
                yield Segment(bar, style)

            if i > 0:
                yield Segment.line()

    def get_min_max(self) -> tuple[T, T]:
        if self.range is not None:
            return self.range
        return min(self.data), max(self.data)

    def __rich_measure__(
        self, console: "Console", options: "ConsoleOptions"
    ) -> Measurement:
        return Measurement(self.width or options.max_width, self.height or 1)
