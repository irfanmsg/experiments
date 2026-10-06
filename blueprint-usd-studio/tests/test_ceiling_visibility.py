"""Keep cutaway visibility in the native runtime without editing source USD."""
import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path

import pytest

@pytest.mark.skipif(find_spec('ovstage') is None, reason='Optional native streaming runtime is not installed')
def test_native_ceiling_visibility_round_trip(tmp_path):
    source = tmp_path / 'ceiling.usda'
    source.write_text('''#usda 1.0
def Xform "World" {
    def Mesh "Ceiling" {
        point3f[] points = [(0,0,2.8),(1,0,2.8),(1,1,2.8)]
        int[] faceVertexCounts = [3]
        int[] faceVertexIndices = [0,1,2]
    }
}
''')
    original = source.read_bytes()
    script = '''
import sys
import ovstage
sys.path.insert(0, 'streaming')
from run import _set_ceiling_visibility
with ovstage.Stage('ceiling-test') as stage:
    ovstage.population.open_usd(stage, sys.argv[1], ordinal=1, domains=ovstage.PopulationDomain.RENDERING)
    stage.advance_write_floor(1, ovstage.Scope.ALL).wait()
    for ordinal, visible in [(2, False), (3, True), (4, False)]:
        _set_ceiling_visibility(stage, ['/World/Ceiling'], visible, ordinal)
        stage.advance_write_floor(ordinal, ovstage.Scope.ALL).wait()
        with ovstage.PathDictionary(stage) as paths:
            with paths.create_path_list_from_strings(['/World/Ceiling']) as prims:
                with stage.query_from_path_list(prims) as query:
                    with stage.read_attributes(query, [paths.intern_token('_worldVisibility')], ovstage.OrdinalRange.latest(ordinal)) as read:
                        read.wait()
                        with read.fetch_next() as group:
                            assert bool(group.array(0)[0]) == visible
'''
    subprocess.run([sys.executable, '-c', script, str(source)],
                   cwd=Path(__file__).resolve().parents[1], check=True, capture_output=True, timeout=30)
    assert source.read_bytes() == original
