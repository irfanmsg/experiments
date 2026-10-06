"""Library metadata must not imply that a GPU operation has executed."""

from importlib import metadata
import json
import subprocess
import sys

from app import runtime_trace as trace_module


def test_versions_match_installed_metadata_without_importing_gpu_modules():
    subprocess.run([sys.executable, '-c',
                    "import sys; from app.runtime_trace import runtime_trace; runtime_trace(); "
                    "assert not ({'ovrtx', 'ovstage', 'ovstream', 'ovphysx', 'warp', 'pxr.Usd'} & set(sys.modules))"],
                   check=True)
    before = set(sys.modules)
    trace = trace_module.runtime_trace()
    assert not ({'ovrtx', 'ovstage', 'ovstream', 'ovphysx', 'warp'} & (set(sys.modules) - before))
    assert trace['kind'] == 'library_action_map'
    for library in trace['libraries']:
        if library.get('distribution'):
            try:
                version = metadata.version(library['distribution'])
            except metadata.PackageNotFoundError:
                assert library['installed'] is False and library['version'] is None
            else:
                assert library['installed'] is True and library['version'] == version
    assert not any(action['status'] == 'executed' for action in trace['actions'])
    assert '/localhome/' not in json.dumps(trace)


def test_missing_optional_packages_are_explicit(monkeypatch):
    def missing(name):
        raise metadata.PackageNotFoundError(name)
    monkeypatch.setattr(trace_module.metadata, 'version', missing)
    monkeypatch.setattr(trace_module, '_ocr_version', lambda: None)
    trace = trace_module.runtime_trace()
    optional = [library for library in trace['libraries'] if library.get('optional')]
    assert optional and all(not library['installed'] and library['version'] is None for library in optional)
    browser = next(library for library in trace['libraries'] if library['id'] == 'webrtc_browser')
    assert browser['version'] is None
    assert len(browser['sha256']) == 64


def test_execution_is_explicit_and_physics_is_conditional():
    trace = trace_module.runtime_trace(executed=['scene_preparation'], openusd_version='0.26.5')
    trace_module.record_execution(trace, 'rtx_render')
    trace_module.record_execution(trace, 'rtx_render')
    actions = {action['id']: action for action in trace['actions']}
    assert actions['rtx_render']['observed_calls'] == 2
    assert actions['rtx_render']['status'] == 'executed'
    assert actions['scene_preparation']['status'] == 'executed'
    assert actions['physics_step']['status'] == 'conditional'
    assert actions['usd_authoring']['status'] != 'executed'
    usd = next(library for library in trace['libraries'] if library['id'] == 'openusd')
    assert usd['version'] == '0.26.5'
    assert all(not action['source'].startswith('/') for action in trace['actions'])
