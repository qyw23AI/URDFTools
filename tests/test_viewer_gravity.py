"""Regression checks for the viewer's pose-aware gravity trajectory."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from viewer_gravity_worker import settle  # noqa: E402


class GravityTrajectoryTest(unittest.TestCase):
    def test_current_pose_frames_and_optional_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            imported = Path(directory) / 'robot.urdf'
            shutil.copyfile(ROOT / 'examples/robot_demo/robot.urdf', imported)
            resting = settle(imported, {'hinge': 0.0}, {'hinge': True})
            angled = settle(imported, {'hinge': 0.8}, {'hinge': True})
            unlimited = settle(imported, {'hinge': 0.8}, {'hinge': False})

        self.assertAlmostEqual(resting['frames'][0]['joints']['hinge'], 0.0)
        self.assertAlmostEqual(angled['frames'][0]['joints']['hinge'], 0.8)
        self.assertGreater(len(angled['frames']), 10)
        self.assertEqual(angled['frames'][0]['time'], 0)
        self.assertAlmostEqual(angled['frames'][-1]['time'], angled['simulated_seconds'])
        self.assertTrue(all(a['time'] < b['time'] for a, b in zip(angled['frames'], angled['frames'][1:])))
        self.assertLessEqual(angled['joints']['hinge'], 1.2)
        self.assertGreater(unlimited['joints']['hinge'], 1.2)
        self.assertGreaterEqual(min(frame['ground_clearance'] for frame in angled['frames']), -0.0005)

    def test_a1_landing_does_not_sink_or_rebound(self):
        with tempfile.TemporaryDirectory() as directory:
            imported = Path(directory) / 'a1_description'
            shutil.copytree(ROOT / 'tests/fixtures/S06/a1_description', imported)
            result = settle(imported / 'a1.urdf', {}, {})

        frames = result['frames']
        self.assertGreater(len(frames), 20)
        self.assertLessEqual(abs(frames[0]['ground_clearance']), 0.0002)
        self.assertGreaterEqual(min(frame['ground_clearance'] for frame in frames), -0.0005)
        self.assertLessEqual(result['ground_clearance'], 0.002)
        heights = [frame['position'][2] for frame in frames]
        upward_motion = sum(max(0, right - left) for left, right in zip(heights, heights[1:]))
        self.assertLess(upward_motion, 0.02)


if __name__ == '__main__':
    unittest.main()
