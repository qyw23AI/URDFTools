import assert from 'node:assert/strict';
import test from 'node:test';
import { findJointCandidates, inferJoint } from '../../apps/web/src/cadJointInference.ts';

const part = (name, min, max, hints = []) => ({name, bounds_min_m: min, bounds_max_m: max,
  center_m: min.map((value, i) => (value + max[i]) / 2), axis_hints: hints});

test('matches aligned cylindrical faces on both links at their interface', () => {
  const p = part('body', [0, 0, 0], [1, 1, 1], [
    {axis: [0, 0, 1], point_m: [1, 0.5, 0.1], radius_m: 0.05, evidence: 'cylinder'}]);
  const c = part('arm', [1, 0.2, 0.2], [2, 0.8, 0.8], [
    {axis: [0, 0, -1], point_m: [1.001, 0.5, 0.9], radius_m: 0.05, evidence: 'cylinder'}]);
  const result = inferJoint([p], [c]);
  assert.equal(result.evidence, 'matched_cylinders');
  assert.ok(Math.abs(result.origin_m[0] - 1.001) < 1e-6);
  assert.ok(Math.abs(result.origin_m[2] - 0.5) < 1e-6);
  assert.deepEqual(result.axis, [0, 0, -1]);
});

test('without cylindrical evidence estimates the closest interface, not the robot center', () => {
  const p = part('body', [0, 0, 0], [1, 1, 1]);
  const c = part('arm', [1.2, 0.2, 0.2], [2, 0.8, 0.8]);
  const result = inferJoint([p], [c]);
  assert.equal(result.evidence, 'unresolved_no_matching_cylinders');
  assert.deepEqual(result.origin_m, [1.1, 0.5, 0.5]);
  assert.equal(findJointCandidates([p], [c]).length, 0);
});

test('keeps only one best shared axis per parent-child part pair', () => {
  const p = part('body', [0, 0, 0], [1, 1, 1], [
    {axis: [0, 0, 1], point_m: [1, 0.5, 0.1], radius_m: 0.05, evidence: 'cylinder'},
    {axis: [1, 0, 0], point_m: [0, 0, 0], radius_m: 0.02, evidence: 'cylinder'}]);
  const c1 = part('arm1', [1, 0.2, 0.2], [2, 0.8, 0.8], [
    {axis: [0, 0, 1], point_m: [1.001, 0.5, 0.9], radius_m: 0.05, evidence: 'cylinder'},
    {axis: [0, 0, 1], point_m: [1.002, 0.5, 0.8], radius_m: 0.05, evidence: 'cylinder'}]);
  const c2 = part('arm2', [1, 1.2, 0.2], [2, 1.8, 0.8], [
    {axis: [0, 0, 1], point_m: [1.001, 1.5, 0.5], radius_m: 0.05, evidence: 'cylinder'}]);
  const candidates = findJointCandidates([p], [c1, c2]);
  assert.equal(candidates.length, 1);
  assert.equal(candidates[0].childPart, 'arm1');
});
