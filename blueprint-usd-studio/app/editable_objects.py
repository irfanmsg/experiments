"""Persist edits to generated furnishings without changing the building shell."""
import json
import math

from pxr import Gf, Usd, UsdGeom


def apply_object_edits(stage, plan, style, decisions=None):
    decisions = decisions if decisions is not None else []
    overrides = plan.get('object_overrides', {}).get(style, {})
    objects = []
    for prim in list(stage.Traverse()):
        if not prim or not (prim.GetCustomDataByKey('interiorDecor') or prim.GetCustomDataByKey('assumedFixture')):
            continue
        path = str(prim.GetPath())
        edit = overrides.get(path, {})
        xf = UsdGeom.Xformable(prim)
        ops = xf.GetOrderedXformOps()
        translate = next((op for op in ops if op.GetOpType() == UsdGeom.XformOp.TypeTranslate), None)
        rotate = next((op for op in ops if op.GetOpType() == UsdGeom.XformOp.TypeRotateZ), None)
        position = list(translate.Get()) if translate else [0., 0., 0.]
        rotation = float(rotate.Get()) if rotate else 0.
        if edit:
            position = edit.get('position', position)
            rotation = edit.get('rotation_deg', rotation)
            if (not isinstance(position, list) or len(position) != 3
                    or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in [*position, rotation])):
                raise ValueError('Generated object position and rotation must be finite numbers')
            if edit.get('removed'):
                prim.SetActive(False)
            else:
                (translate or xf.AddTranslateOp()).Set(Gf.Vec3d(*position))
                (rotate or xf.AddRotateZOp()).Set(rotation)
            decisions.append({'id': path, 'kind': 'user-edit', 'interior_scheme': style,
                              'summary': 'User changed generated furnishing placement or removed it; dimensions retained.',
                              'parameters': edit, 'status': 'user-edited; clearance needs review'})
        if not prim.IsActive():
            continue
        bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render']).ComputeWorldBound(prim).ComputeAlignedBox()
        objects.append({'id': path, 'name': prim.GetName().replace('_', ' '),
                        'asset_kind': 'Procedural USD', 'room_id': prim.GetCustomDataByKey('roomId'),
                        'position': [float(v) for v in position], 'rotation_deg': rotation,
                        'size_xyz_m': list(bounds.GetSize()) if not bounds.IsEmpty() else None})
    if stage.GetDefaultPrim():
        stage.GetDefaultPrim().SetCustomDataByKey('presentationDecisions', json.dumps(decisions))
    return objects
