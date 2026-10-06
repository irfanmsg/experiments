"""Persist edits to generated furnishings without changing the building shell."""
import json
import math

from pxr import Gf, Usd, UsdGeom


def validate_asset_edits(plan):
    """Reject malformed transforms before saving or building a scene."""
    errors = []
    placements = plan.get('asset_placements', [])
    overrides = plan.get('object_overrides', {})
    if not isinstance(placements, list) or not isinstance(overrides, dict):
        return ['Asset placements must be a list and object overrides a mapping']
    edits = list(placements)
    for values in overrides.values():
        if not isinstance(values, dict):
            errors.append('Object overrides must be a mapping')
        else:
            edits.extend(values.values())
    for edit in edits:
        if not isinstance(edit, dict):
            errors.append('Each asset edit must be an object')
            continue
        label = edit.get('id', 'Object')
        for key in ('position', 'scale_xyz'):
            if key not in edit:
                continue
            value = edit[key]
            if (not isinstance(value, list) or len(value) != 3
                    or any(type(v) not in (int, float) or not math.isfinite(v)
                           or (key == 'scale_xyz' and v <= 0) for v in value)):
                errors.append(f'{label}: {key} must contain three finite' + (' positive' if key == 'scale_xyz' else '') + ' numbers')
        if 'rotation_deg' in edit and (type(edit['rotation_deg']) not in (int, float) or not math.isfinite(edit['rotation_deg'])):
            errors.append(f'{label}: rotation must be finite')
    return errors


def apply_object_edits(stage, plan, style, decisions=None):
    errors = validate_asset_edits(plan)
    if errors:
        raise ValueError('; '.join(errors))
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
        scale_op = next((op for op in ops if op.GetOpType() == UsdGeom.XformOp.TypeScale), None)
        base_scale = list(prim.GetCustomDataByKey('editorBaseScale') or (scale_op.Get() if scale_op else [1., 1., 1.]))
        prim.SetCustomDataByKey('editorBaseScale', Gf.Vec3d(*base_scale))
        local_box = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render']).ComputeUntransformedBound(prim).ComputeAlignedBox()
        source_size = [abs(float(v) * base_scale[i]) for i, v in enumerate(local_box.GetSize())] if not local_box.IsEmpty() else None
        user_scale = edit.get('scale_xyz', [1., 1., 1.])
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
                if 'scale_xyz' in edit:
                    (scale_op or xf.AddScaleOp()).Set(Gf.Vec3d(*(a*b for a,b in zip(base_scale,user_scale))))
            decisions.append({'id': path, 'kind': 'user-edit', 'interior_scheme': style,
                              'summary': 'User edited generated furnishing; any resizing is an explicit scale override, separate from building dimensions.',
                              'parameters': edit, 'status': 'user-edited; clearance needs review'})
        if not prim.IsActive():
            continue
        bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render']).ComputeWorldBound(prim).ComputeAlignedBox()
        objects.append({'id': path, 'name': prim.GetName().replace('_', ' '),
                        'asset_kind': 'Procedural USD', 'room_id': prim.GetCustomDataByKey('roomId'),
                        'position': [float(v) for v in position], 'rotation_deg': rotation,
                        'scale_xyz': user_scale, 'source_size_xyz_m': source_size,
                        'local_size_xyz_m': [v * user_scale[i] for i,v in enumerate(source_size)] if source_size else None,
                        'size_xyz_m': list(bounds.GetSize()) if not bounds.IsEmpty() else None})
    if stage.GetDefaultPrim():
        stage.GetDefaultPrim().SetCustomDataByKey('presentationDecisions', json.dumps(decisions))
    return objects
