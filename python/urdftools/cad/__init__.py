"""Optional CAD functionality; imports OCP only when explicitly used."""


def inspect_step(path, **kwargs):
    from .step_reader import inspect_step as _inspect_step
    return _inspect_step(path, **kwargs)


def calculate_solid_mass_properties(shape, density_kg_m3, **kwargs):
    from .mass_properties import calculate_solid_mass_properties as _calculate
    return _calculate(shape, density_kg_m3, **kwargs)


def transform_mass_properties(local, transform_4x4_m):
    from .mass_properties import transform_mass_properties as _transform
    return _transform(local, transform_4x4_m)


def rotate_inertia_tensor(inertia_kg_m2, rotation):
    from .mass_properties import rotate_inertia_tensor as _rotate
    return _rotate(inertia_kg_m2, rotation)


def aggregate_mass_properties(parts):
    from .mass_properties import aggregate_mass_properties as _aggregate
    return _aggregate(parts)


def compute_step_mass_properties(path, densities_by_part=None, **kwargs):
    from .mass_properties import compute_step_mass_properties as _compute
    return _compute(path, densities_by_part, **kwargs)
