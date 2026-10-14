"""Advance delayed pose coordinates using observed image motion, without another inference."""
from dataclasses import replace
import cv2
import numpy as np


def compensate(source_frame, latest_frame, detections):
    """Return translated detections, or None when image tracking is unreliable.

    Forward/backward optical flow follows features inside each person's box.
    This accounts for camera/robot motion as well as target translation during
    inference; it does not invent observations when texture or overlap is lost.
    """
    if not detections or source_frame.shape != latest_frame.shape:
        return None
    height, width = source_frame.shape[:2]
    scale = min(1.0, 320 / width)
    size = (round(width * scale), round(height * scale))
    old = cv2.cvtColor(cv2.resize(source_frame, size), cv2.COLOR_BGR2GRAY)
    new = cv2.cvtColor(cv2.resize(latest_frame, size), cv2.COLOR_BGR2GRAY)
    result = []
    for detection in detections:
        x1, y1, x2, y2 = detection.box
        mask = np.zeros_like(old)
        mask[max(0, round(y1*scale)):min(size[1], round(y2*scale)),
             max(0, round(x1*scale)):min(size[0], round(x2*scale))] = 255
        points = cv2.goodFeaturesToTrack(old, 40, .02, 4, mask=mask)
        if points is None or len(points) < 8:
            return None
        moved, valid, _ = cv2.calcOpticalFlowPyrLK(old, new, points, None,
                                                  winSize=(21, 21), maxLevel=3)
        if moved is None:
            return None
        returned, back_valid, _ = cv2.calcOpticalFlowPyrLK(new, old, moved, None,
                                                         winSize=(21, 21), maxLevel=3)
        if returned is None:
            return None
        good = valid.ravel().astype(bool) & back_valid.ravel().astype(bool)
        good &= np.linalg.norm((returned-points).reshape(-1, 2), axis=1) < 1.5
        shifts = (moved-points).reshape(-1, 2)[good]
        if len(shifts) < 8:
            return None
        median = np.median(shifts, axis=0)
        coherent = np.linalg.norm(shifts-median, axis=1) < 3
        if np.count_nonzero(coherent) < 8:
            return None
        dx, dy = np.median(shifts[coherent], axis=0) / scale
        aim_x, aim_y = detection.center
        aim = (round(aim_x+float(dx)), round(aim_y+float(dy)))
        if not (0 <= aim[0] < width and 0 <= aim[1] < height):
            continue
        box = (max(0, round(x1+float(dx))), max(0, round(y1+float(dy))),
               min(width, round(x2+float(dx))), min(height, round(y2+float(dy))))
        if box[0] >= box[2] or box[1] >= box[3]:
            continue
        keypoints = None if detection.keypoints is None else tuple(
            (float(x+dx), float(y+dy), score if 0 <= x+dx < width and 0 <= y+dy < height else 0.)
            for x, y, score in detection.keypoints)
        result.append(replace(detection, box=box, aim_point=aim, keypoints=keypoints))
    return result
