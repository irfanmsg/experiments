from pathlib import Path
import zipfile

import pytest
from pxr import Usd, UsdGeom

from app.asset_library import catalog
from app.asset_uploads import import_asset


def asset_file(path):
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageMetersPerUnit(stage, 0.01)
    UsdGeom.SetStageUpAxis(stage, 'Y')
    cube = UsdGeom.Cube.Define(stage, '/Chair')
    cube.CreateSizeAttr(100)
    stage.SetDefaultPrim(cube.GetPrim())
    stage.GetRootLayer().Save()
    return path


def test_standalone_asset_import_is_durable_and_keeps_units(tmp_path, monkeypatch):
    library = tmp_path / 'library'
    monkeypatch.setenv('BLUEPRINT_STUDIO_ASSET_ROOT', str(library))
    result = import_asset(asset_file(tmp_path / 'chair.usda'), '../../my chair.usda')
    assert result['asset_kind'] == 'Imported USD (SimReady not verified)'
    assert result['source_units_m'] == 0.01 and result['source_up_axis'] == 'Y'
    assert result['size_xyz_m'] == pytest.approx([1, 1, 1])
    assert Path(result['usd_path']).is_relative_to(library / 'UserImports')
    assert next(item for item in catalog()['assets'] if item['id'] == result['id']) == result
    assert Usd.Stage.Open(result['usd_path']).GetDefaultPrim().GetName() == 'Chair'


@pytest.mark.parametrize('field', [
    'asset inputs:file = @/etc/passwd@',
    'asset inputs:file = @https://example.test/texture.png@',
    'asset inputs:file = @../outside.png@',
    'asset[] inputs:files = [@texture.png@]',
])
def test_external_asset_paths_are_rejected_without_import(tmp_path, monkeypatch, field):
    library = tmp_path / 'library'
    monkeypatch.setenv('BLUEPRINT_STUDIO_ASSET_ROOT', str(library))
    source = tmp_path / 'bad.usda'
    source.write_text('#usda 1.0\n(defaultPrim="Asset"\nmetersPerUnit=1\nupAxis="Z")\ndef Cube "Asset" {\n' + field + '\n}\n')
    with pytest.raises(ValueError, match='self-contained|outside|external'):
        import_asset(source, 'bad.usda')
    assert not catalog()['assets']


def test_external_reference_is_rejected_before_stage_composition(tmp_path, monkeypatch):
    monkeypatch.setenv('BLUEPRINT_STUDIO_ASSET_ROOT', str(tmp_path / 'library'))
    source = tmp_path / 'bad.usda'
    source.write_text('#usda 1.0\ndef Xform "Asset" (references = @/etc/passwd@) {}\n')
    monkeypatch.setattr(Usd.Stage, 'Open', lambda *args, **kwargs: pytest.fail('unsafe composition attempted'))
    with pytest.raises(ValueError, match='outside|external'):
        import_asset(source, 'bad.usda')


def test_usdz_dependencies_remain_within_import_directory(tmp_path, monkeypatch):
    monkeypatch.setenv('BLUEPRINT_STUDIO_ASSET_ROOT', str(tmp_path / 'library'))
    source = asset_file(tmp_path / 'asset.usda')
    stage = Usd.Stage.Open(str(source))
    from pxr import Sdf
    stage.GetDefaultPrim().CreateAttribute('inputs:file', Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath('textures/color.png'))
    stage.GetRootLayer().Save()
    archive = tmp_path / 'asset.usdz'
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.write(source, 'asset.usda')
        bundle.writestr('textures/color.png', b'image placeholder; not rendered in this test')
    imported = import_asset(archive, 'asset.usdz')
    assert Path(imported['usd_path']).with_name('textures').joinpath('color.png').is_file()
    assert imported['size_xyz_m'] == pytest.approx([1, 1, 1])


@pytest.mark.parametrize('entry', ['../escape.usda', '/absolute.usda', 'sub/../../escape.usda', 'sub\\escape.usda'])
def test_usdz_rejects_traversal_entries(tmp_path, monkeypatch, entry):
    monkeypatch.setenv('BLUEPRINT_STUDIO_ASSET_ROOT', str(tmp_path / 'library'))
    archive = tmp_path / 'bad.usdz'
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr(entry, '#usda 1.0\n')
    with pytest.raises(ValueError, match='archive|package'):
        import_asset(archive, 'bad.usdz')


def test_missing_authored_units_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv('BLUEPRINT_STUDIO_ASSET_ROOT', str(tmp_path / 'library'))
    source = asset_file(tmp_path / 'asset.usda')
    stage = Usd.Stage.Open(str(source))
    stage.ClearMetadata('metersPerUnit')
    stage.GetRootLayer().Save()
    with pytest.raises(ValueError, match='metersPerUnit'):
        import_asset(source, 'asset.usda')


@pytest.mark.parametrize('variant', [False, True])
def test_time_samples_and_unselected_variants_cannot_hide_external_paths(tmp_path, monkeypatch, variant):
    from pxr import Sdf
    monkeypatch.setenv('BLUEPRINT_STUDIO_ASSET_ROOT', str(tmp_path / 'library'))
    source = asset_file(tmp_path / 'asset.usda')
    stage = Usd.Stage.Open(str(source))
    prim = stage.GetDefaultPrim()
    if variant:
        variants = prim.GetVariantSets().AddVariantSet('shape')
        variants.AddVariant('unsafe')
        variants.SetVariantSelection('unsafe')
        with variants.GetVariantEditContext():
            prim.GetReferences().AddReference('/outside/model.usda')
        variants.AddVariant('safe')
        variants.SetVariantSelection('safe')
    else:
        prim.CreateAttribute('file', Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath('/outside/texture.png'), 12)
    stage.GetRootLayer().Save()
    with pytest.raises(ValueError, match='external|outside'):
        import_asset(source, 'asset.usda')


def test_usdz_rejects_symbolic_links(tmp_path, monkeypatch):
    import stat
    monkeypatch.setenv('BLUEPRINT_STUDIO_ASSET_ROOT', str(tmp_path / 'library'))
    archive = tmp_path / 'bad.usdz'
    with zipfile.ZipFile(archive, 'w') as bundle:
        info = zipfile.ZipInfo('link.usda')
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        bundle.writestr(info, '/outside/model.usda')
    with pytest.raises(ValueError, match='link'):
        import_asset(archive, 'bad.usdz')


@pytest.mark.parametrize('change,error', [('no_default', 'default prim'), ('no_axis', 'upAxis'), ('no_geometry', 'geometry')])
def test_import_requires_a_defined_physical_model(tmp_path, monkeypatch, change, error):
    monkeypatch.setenv('BLUEPRINT_STUDIO_ASSET_ROOT', str(tmp_path / 'library'))
    source = asset_file(tmp_path / 'asset.usda')
    stage = Usd.Stage.Open(str(source))
    if change == 'no_default':
        stage.ClearDefaultPrim()
    elif change == 'no_axis':
        stage.ClearMetadata('upAxis')
    else:
        stage.GetDefaultPrim().SetTypeName('Xform')
    stage.GetRootLayer().Save()
    with pytest.raises(ValueError, match=error):
        import_asset(source, 'asset.usda')


def test_binary_usdc_import(tmp_path, monkeypatch):
    monkeypatch.setenv('BLUEPRINT_STUDIO_ASSET_ROOT', str(tmp_path / 'library'))
    imported = import_asset(asset_file(tmp_path / 'chair.usdc'), 'chair.usdc')
    assert imported['size_xyz_m'] == pytest.approx([1, 1, 1])
