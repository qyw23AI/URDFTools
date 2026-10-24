---
name: urdf-ui-workbench
description: Design or revise the URDFTools Electron interface for URDF viewing, STEP conversion, robot modeling, and evaluation when a large interactive 3D scene and clear engineering controls are needed.
---

# URDFTools UI workbench

Use this skill for this project's React, Three.js and Electron interface. Read `AGENTS.md`, the affected component, and the desktop bridge before changing a control.

- Keep the 3D scene visible and dominant during model inspection. Place file import, structure, joint controls, measurements, and diagnostics in compact panels that can be opened without losing the scene.
- Keep the same camera gestures throughout: left drag rotates, right drag pans, wheel zooms. Show these gestures near the canvas; keep reset view and fit controls discoverable.
- Preserve real state and source information: distinguish loading, empty, ready, missing resource, and failed import; mark approximate mesh bounds separately from CAD measurements; keep unknown mass/inertia unknown.
- Make each visible control operate a real bridge method or an explicit local UI state. Check keyboard focus, disabled states, narrow windows, and that panel content scrolls independently of the canvas.
- When changing import or CAD controls, preserve source SHA, resource location, unit, and human confirmation of joint and material parameters. Do not infer kinematics or density from shape alone.
- Before claiming a design follows an upstream tool, inspect its source or UI and record its URL and license. The locally saved `edsamsankey/step2urdf` source at commit `3845072` shows a settings column, central 3D preview, joint sliders, and export buttons; its copied MIT license has a copyright placeholder, so do not redistribute that source until Q01 license review resolves it. `urdf-loader` 0.13.1 (Apache-2.0) documents a drag-and-drop viewer and joint API. Other names in the architecture are reference candidates, not verified layout facts.
- Review the result in the actual desktop renderer with a model, then check the production build and affected interaction path. Report any checks blocked by the environment.
