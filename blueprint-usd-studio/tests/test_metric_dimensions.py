"""Measure authored geometry rather than trusting dimension labels."""
import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
from pxr import Gf, Usd, UsdGeom
from shapely.geometry import Polygon, box

from app.dimensioned_b1 import build_dimensioned_plan, relocate_assets
from app.geometry import validate_plan
from app.usd_builder import build_usd

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope='module')
def measured(tmp_path_factory):
    plan = json.loads((ROOT/'data/b1_1502/plan.json').read_text())
    destination = tmp_path_factory.mktemp('meters')/'flat.usda'
    build_usd(plan, destination)
    return plan, Usd.Stage.Open(str(destination))


def test_exported_floor_vertices_match_every_printed_dimension(measured):
    plan, stage = measured
    assert UsdGeom.GetStageMetersPerUnit(stage) == 1.0
    for room in plan['rooms']:
        prim = stage.GetPrimAtPath('/World/Spaces/'+room['id']+'/Floor')
        mesh = UsdGeom.Mesh(prim)
        points = mesh.GetPointsAttr().Get()
        # Top contour is authored once, followed by bottom vertices.
        xy = [(float(p[0]),float(p[1])) for p in points[:len(points)//2]]
        shape = Polygon(xy)
        x0,y0,x1,y1 = shape.bounds
        if room['dimension_mode'] == 'clear_rectangle':
            actual = [x1-x0,y1-y0]
        elif room['span_axis'] == 1:
            actual = [shape.area/(y1-y0),y1-y0]
        else:
            actual = [x1-x0,shape.area/(x1-x0)]
        assert actual == pytest.approx(room['dimensions_m'],abs=2e-6), (room['id'],actual)


def _wall_boxes(stage):
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(),['default','render'])
    for prim in stage.Traverse():
        path = str(prim.GetPath())
        if not path.startswith('/World/Building/Walls/') or prim.GetTypeName() != 'Cube' or '_guard_' in path:
            continue
        bound = cache.ComputeWorldBound(prim).ComputeAlignedBox()
        yield prim, np.array(bound.GetMin()), np.array(bound.GetMax())


def test_finished_wall_faces_preserve_clear_room_dimensions(measured):
    plan, stage = measured
    solids = [(lo,hi) for _,lo,hi in _wall_boxes(stage) if lo[2] < 1 and hi[2] > 1]
    # Entrance and passage have intentionally open interfaces; balconies use
    # clear floor spans/average depths, not a rectangular wall enclosure.
    for room in plan['rooms']:
        if room['category'] == 'balcony' or room['id'] in {'entry','passage'}:
            continue
        x0,y0,x1,y1 = Polygon(room['polygon']).bounds
        center=np.array([(x0+x1)/2,(y0+y1)/2,1.0])
        for axis in [0,1]:
            matches=[]
            for fraction in [.13,.27,.43,.57,.73,.87]:
                point=center.copy();cross=1-axis
                point[cross]=[x0,y0][cross]+fraction*([x1,y1][cross]-[x0,y0][cross])
                lows=[];highs=[]
                for lo,hi in solids:
                    if lo[cross]+1e-6 < point[cross] < hi[cross]-1e-6:
                        if hi[axis] <= point[axis]+1e-6:lows.append(hi[axis])
                        if lo[axis] >= point[axis]-1e-6:highs.append(lo[axis])
                if lows and highs:
                    matches.append(min(highs)-max(lows))
            assert any(abs(v-room['dimensions_m'][axis]) < .00001 for v in matches), (room['id'],axis,matches)


def test_rooms_do_not_overlap_and_walls_stay_outside_clear_spaces(measured):
    plan, stage = measured
    shapes=[(r['id'],Polygon(r['polygon'])) for r in plan['rooms']]
    for i,(name,shape) in enumerate(shapes):
        for other,second in shapes[i+1:]:
            assert shape.intersection(second).area < 1e-7,(name,other)
    for prim,low,high in _wall_boxes(stage):
        wall=box(low[0],low[1],high[0],high[1])
        for name,shape in shapes:
            assert wall.intersection(shape).area < 5e-6,(str(prim.GetPath()),name)


def test_bad_dimensions_cannot_be_exported_with_good_labels(tmp_path):
    plan=json.loads((ROOT/'data/b1_1502/plan.json').read_text())
    kitchen=next(r for r in plan['rooms'] if r['id']=='kitchen')
    kitchen['polygon'][1][0] -= .08
    assert validate_plan(plan)
    with pytest.raises(ValueError):build_usd(plan,tmp_path/'bad.usda')


def test_dimensioned_rebuild_ignores_raster_pixel_calibration():
    source=json.loads((ROOT/'data/b1_1502/raster_trace.json').read_text())
    rebuilt=build_dimensioned_plan(source)
    source['calibration']['pixels_per_metre']=999
    changed=build_dimensioned_plan(source)
    assert [r['polygon'] for r in rebuilt['rooms']] == [r['polygon'] for r in changed['rooms']]
    altered=deepcopy(source)
    next(r for r in altered['rooms'] if r['id']=='kitchen')['dimensions_m'][0]=3.0
    widened=build_dimensioned_plan(altered)
    room=next(r for r in widened['rooms'] if r['id']=='kitchen')
    assert Polygon(room['polygon']).bounds[2]-Polygon(room['polygon']).bounds[0] == pytest.approx(3.0)


def test_brochure_feet_inches_crosscheck_keeps_approved_values():
    data=json.loads((ROOT/'data/b1_1502/source_comparison.json').read_text())
    plan=json.loads((ROOT/'data/b1_1502/plan.json').read_text())
    rooms={r['id']:r for r in plan['rooms']}
    for entry in data['measurements']:
        converted=[feet*.3048+inches*.0254 for feet,inches in entry['brochure_feet_inches']]
        assert converted == pytest.approx(entry['brochure_m'],abs=1e-9)
        assert rooms[entry['room_id']]['dimensions_m'] == entry['approved_m']


def test_existing_example_migrates_without_rescaling_furniture(tmp_path, monkeypatch):
    from app import main
    source=json.loads((ROOT/'data/b1_1502/raster_trace.json').read_text())
    source.update(id='existing',example='B1-1502',structure_type='home')
    source['asset_placements']=[{'id':'chair','asset_path':'unchanged.usd','position':[5.7,7.65,0.008],'rotation_deg':90}]
    project=tmp_path/'existing';project.mkdir()
    (project/'plan.json').write_text(json.dumps(source))
    monkeypatch.setattr(main,'UPLOADS',tmp_path)
    updated=main._read_plan('existing')
    assert updated['dimension_model']
    assert updated['asset_placements'][0]['asset_path']=='unchanged.usd'
    assert updated['asset_placements'][0]['rotation_deg']==90
    assert updated['asset_placements'][0]['position'][2]==.008
    assert 'scale' not in updated['asset_placements'][0]
    assert main._read_plan('existing') == updated  # No repeated position transform.


def test_edited_legacy_project_is_preserved(tmp_path, monkeypatch):
    from app import main
    source=json.loads((ROOT/'data/b1_1502/raster_trace.json').read_text())
    source.update(id='edited',example='B1-1502')
    source['rooms'][0]['polygon'][0][0] += .1
    project=tmp_path/'edited';project.mkdir()
    path=project/'plan.json'
    original=json.dumps(source)
    path.write_text(original)
    monkeypatch.setattr(main,'UPLOADS',tmp_path)
    with pytest.raises(main.HTTPException) as error:
        main._read_plan('edited')
    assert error.value.status_code == 409
    assert path.read_text() == original


def test_slab_preserves_voids_in_export_and_area_report(tmp_path):
    outer=[[0,0],[6,0],[6,5],[0,5]]
    hole=[[2,2],[3,2],[3,3],[2,3]]
    plan={'name':'Courtyard','units':'m','structure_type':'home',
          'footprint':{'polygon':outer,'holes':[hole]},'rooms':[],
          'wall_segments':[],'openings':[]}
    report=build_usd(plan,tmp_path/'courtyard.usda')
    assert report['footprint_area_m2'] == 29
    stage=Usd.Stage.Open(report['usd_path'])
    mesh=UsdGeom.Mesh(stage.GetPrimAtPath('/World/Building/FloorSlab'))
    points=mesh.GetPointsAttr().Get()
    counts=mesh.GetFaceVertexCountsAttr().Get()
    indices=mesh.GetFaceVertexIndicesAttr().Get()
    area=0;offset=0
    for count in counts:
        face=[points[i] for i in indices[offset:offset+count]]
        offset+=count
        if all(abs(p[2])<1e-8 for p in face):
            triangle=Polygon([(p[0],p[1]) for p in face])
            assert triangle.intersection(Polygon(hole)).area == pytest.approx(0)
            area+=triangle.area
    assert area == pytest.approx(29)
