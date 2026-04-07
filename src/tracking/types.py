type BBox = tuple[int, int, int, int]  # (x1, y1, x2, y2) or (x, y, width, height)
type Frame = tuple[int, int]  # (height, width)
type BBoxMapping = dict[str, list[BBox]]
