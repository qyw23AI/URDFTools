"""Independent analytical planar two-link dynamics for fixed-axis Y shoulder and elbow."""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PlanarArm:
    length1_m: float = 0.4
    com1_m: float = 0.2
    com2_m: float = 0.15
    mass1_kg: float = 2.0
    mass2_kg: float = 1.0
    inertia1_yy_kg_m2: float = 0.027733333333333336
    inertia2_yy_kg_m2: float = 0.008333333333333333
    gravity_m_s2: float = 9.81

    def mass_matrix(self, q1: float, q2: float) -> tuple[tuple[float, float], ...]:
        l, c = self.length1_m, self.com2_m
        m = self.mass2_kg
        j1, j2 = self.inertia1_yy_kg_m2, self.inertia2_yy_kg_m2
        coupling = m * l * c * math.cos(q2)
        m11 = j1 + j2 + self.mass1_kg * self.com1_m ** 2 + m * (l*l + c*c) + 2*coupling
        m12 = j2 + m*c*c + coupling
        m22 = j2 + m*c*c
        return ((m11, m12), (m12, m22))

    def gravity_generalized(self, q1: float, q2: float) -> tuple[float, float]:
        a = self.gravity_m_s2
        return (
            a * (self.mass1_kg * self.com1_m * math.sin(q1)
                 + self.mass2_kg * (self.length1_m * math.sin(q1)
                                    + self.com2_m * math.sin(q1 + q2))),
            a * self.mass2_kg * self.com2_m * math.sin(q1 + q2),
        )
