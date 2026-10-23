from fractions import Fraction
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
import av
import numpy as np
from urdftools.results.media import inspect_video, locate_metric_event
from urdftools.results.jobs import ImportFailure


class MediaAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "episode.mp4"
        with av.open(str(self.path), "w") as output:
            stream = output.add_stream("mpeg4", rate=10)
            stream.width, stream.height = 64, 64
            stream.pix_fmt = "yuv420p"
            stream.time_base = Fraction(1, 10)
            for i, pts in enumerate((0,1,2,4,5)):
                pixels = np.full((64,64,3), i*20, dtype=np.uint8)
                frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
                frame.pts = pts
                frame.time_base = Fraction(1,10)
                for packet in stream.encode(frame): output.mux(packet)
            for packet in stream.encode(): output.mux(packet)

    def test_decodable_video_gap_offset_and_event_lookup(self):
        report = inspect_video(self.path, episode_id="ep-1", camera="front", experiment_offset_s=4,
                               declared_fps=10)
        self.assertEqual(report["frame_count"], 5)
        self.assertEqual(report["suspected_gap_frame_indices"], [3])
        self.assertTrue(report["variable_frame_rate"])
        self.assertIsNone(report["torque_from_video"])
        self.assertIsNone(report["energy_from_video"])
        event = locate_metric_event(report, episode_id="ep-1", experiment_time_s=4.4,
                                    metric="fall", value=1)
        self.assertEqual(event["status"], "located")
        self.assertEqual(event["frame_index"], 3)
        outside = locate_metric_event(report, episode_id="ep-1", experiment_time_s=10,
                                      metric="fall", value=1)
        self.assertEqual(outside["status"], "outside_video")

    def test_bad_media_and_mismatched_episode(self):
        report = inspect_video(self.path, episode_id="ep-1", camera="front", experiment_offset_s=0)
        with self.assertRaises(ImportFailure):
            locate_metric_event(report, episode_id="wrong", experiment_time_s=0, metric="fall", value=1)
        invalid = Path(self.tmp.name) / "invalid.mp4"
        invalid.write_bytes(b"not a video")
        with self.assertRaises(ImportFailure):
            inspect_video(invalid, episode_id="ep-1", camera="front", experiment_offset_s=0)


if __name__ == "__main__":
    unittest.main()
