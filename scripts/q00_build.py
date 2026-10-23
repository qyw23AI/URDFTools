#!/usr/bin/env python3
"""Use the project-pinned Node runtime for reproducible frontend build."""
import os
from accept_phase import ROOT, run_stage


def main():
    node = ROOT/'.tools/node/bin/node'
    npm = ROOT/'.tools/npm/bin/npm-cli.js'
    env = dict(os.environ, PATH=str(node.parent)+':'+os.environ.get('PATH',''))
    code, output = run_stage([str(node), str(npm), 'run', 'build'], env=env, timeout=130)
    print(output)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
