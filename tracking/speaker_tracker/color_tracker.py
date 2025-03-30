# speaker_tracker.py
import math
import numpy as np
from tracking.speaker_tracker.tracker_interface import TrackerInterface

class ColorTracker(TrackerInterface):
    def __init__(self, lost_threshold=20, color_threshold=10):
        self.speaker_bbox = None
        self.speaker_color = None
        self.lost_counter = 0
        self.lost_threshold = lost_threshold
        self.color_threshold = color_threshold

    def compute_center(self, bbox):
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def bbox_distance(self, bbox1, bbox2):
        cx1, cy1 = self.compute_center(bbox1)
        cx2, cy2 = self.compute_center(bbox2)
        return math.sqrt((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2)

    def set_speaker(self, bbox, speaker_color):
        self.speaker_bbox = bbox
        self.speaker_color = speaker_color
        self.lost_counter = 0

    def update(self, frame, bboxes):
        if self.speaker_bbox is None:
            return None

        if len(bboxes) == 0:
            self.lost_counter += 1
        else:
            best_bbox = None
            min_distance = float('inf')
            best_candidate_color = None

            for bbox in bboxes:
                dist = self.bbox_distance(bbox, self.speaker_bbox)
                x1, y1, x2, y2 = bbox
                candidate_crop = frame[y1:y2, x1:x2]
                if candidate_crop.size > 0:
                    candidate_color = np.mean(candidate_crop, axis=(0, 1))
                    color_diff = np.linalg.norm(np.array(candidate_color) - np.array(self.speaker_color))
                    if dist < min_distance:
                        if len(bboxes) > 1:
                            if color_diff < self.color_threshold:
                                min_distance = dist
                                best_bbox = bbox
                                best_candidate_color = candidate_color
                        else:
                            min_distance = dist
                            best_bbox = bbox
                            best_candidate_color = candidate_color

            if best_bbox is not None and min_distance < 150:
                self.speaker_bbox = best_bbox
                self.speaker_color = best_candidate_color
                self.lost_counter = 0
            else:
                self.lost_counter += 1

        if self.lost_counter >= self.lost_threshold:
            print("Speaker lost for too many frames. Resetting speaker.")
            self.speaker_bbox = None
            self.speaker_color = None
            self.lost_counter = 0

        return self.speaker_bbox
