export type CadAxisHint = {axis: number[]; point_m: number[]; radius_m: number; evidence: string};
export type CadAxisPart = {name: string; center_m: number[]; bounds_min_m: number[]; bounds_max_m: number[]; axis_hints: CadAxisHint[]};
export type InferredJoint = {axis: number[]; origin_m: number[]; radius_m: number; evidence: string};
export type JointAxisCandidate = InferredJoint & {parentPart: string; childPart: string; score: number};

const distance = (a: number[], b: number[]) => Math.hypot(...a.map((value, index) => value - b[index]));
const dot = (a: number[], b: number[]) => a.reduce((sum, value, index) => sum + value * b[index], 0);
const normal = (axis: number[]) => {
  const length = Math.hypot(...axis);
  return length > 1e-9 ? axis.map(value => value / length) : [0, 0, 1];
};
const midpoint = (a: number[], b: number[]) => a.map((value, index) => (value + b[index]) / 2);
function closestInterface(parent: CadAxisPart[], child: CadAxisPart[]): number[] {
  let best: {score: number; point: number[]} | null = null;
  for (const p of parent) for (const c of child) {
    const parentPoint: number[] = [], childPoint: number[] = [];
    for (let i = 0; i < 3; i++) {
      if (p.bounds_max_m[i] < c.bounds_min_m[i]) {
        parentPoint.push(p.bounds_max_m[i]); childPoint.push(c.bounds_min_m[i]);
      } else if (c.bounds_max_m[i] < p.bounds_min_m[i]) {
        parentPoint.push(p.bounds_min_m[i]); childPoint.push(c.bounds_max_m[i]);
      } else {
        const overlap = (Math.max(p.bounds_min_m[i], c.bounds_min_m[i]) + Math.min(p.bounds_max_m[i], c.bounds_max_m[i])) / 2;
        parentPoint.push(overlap); childPoint.push(overlap);
      }
    }
    const score = distance(parentPoint, childPoint) + distance(p.center_m, c.center_m) * 0.0001;
    if (!best || score < best.score) best = {score, point: midpoint(parentPoint, childPoint)};
  }
  return best?.point || [0, 0, 0];
}

/** Estimate the common hinge line from matching cylindrical faces on both sides. */
export function findJointCandidates(parentParts: CadAxisPart[], childParts: CadAxisPart[]): JointAxisCandidate[] {
  const candidates: JointAxisCandidate[] = [];
  for (const parentPart of parentParts) for (const childPart of childParts) {
    const interfacePoint = closestInterface([parentPart], [childPart]);
    let best: JointAxisCandidate | null = null;
    for (const p of parentPart.axis_hints) for (const c of childPart.axis_hints) {
      const a = normal(p.axis), b = normal(c.axis);
      if (Math.abs(dot(a, b)) < 0.96) continue;
      const delta = p.point_m.map((value, i) => value - c.point_m[i]);
      const perpendicular = Math.sqrt(Math.max(0, dot(delta, delta) - dot(delta, a) ** 2));
      const scale = Math.max(p.radius_m, c.radius_m, 0.001);
      if (perpendicular > Math.max(0.006, scale * 0.35)) continue;
      if (Math.abs(p.radius_m - c.radius_m) > Math.max(0.008, scale * 0.8)) continue;
      const axis = normal(c.axis);
      const shift = dot(interfacePoint.map((value, i) => value - c.point_m[i]), axis);
      const origin_m = c.point_m.map((value, i) => value + shift * axis[i]);
      const score = perpendicular / scale + distance(origin_m, interfacePoint) / Math.max(scale, 0.01);
      const candidate: JointAxisCandidate = {axis, origin_m, radius_m: Math.max(p.radius_m, c.radius_m),
        evidence: 'matched_cylinders', parentPart: parentPart.name, childPart: childPart.name, score};
      if (!best || score < best.score) best = candidate;
    }
    if (best) candidates.push(best);
  }
  return candidates.sort((a, b) => a.score - b.score);
}

export function inferJoint(parentParts: CadAxisPart[], childParts: CadAxisPart[]): InferredJoint {
  const matched = findJointCandidates(parentParts, childParts)[0];
  if (matched) return matched;
  return {axis: [0, 0, 1], origin_m: closestInterface(parentParts, childParts), radius_m: 0,
    evidence: 'unresolved_no_matching_cylinders'};
}
