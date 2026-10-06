from app import main
from app.geometry import measured_scale_audit


def test_analysis_cache_changes_with_the_source_image(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(main, 'analyze_drawing', lambda path: calls.append(path) or {'suggestions': [], 'scale_proposal': None})
    monkeypatch.setattr(main, 'runtime_trace', lambda **kwargs: {'executed': kwargs['executed']})
    main._drawing_analysis.cache_clear()
    path = str(tmp_path / 'plan.png')
    first = main._drawing_analysis(path, 100, 40)
    assert main._drawing_analysis(path, 100, 40) == first
    assert len(calls) == 1
    main._drawing_analysis(path, 101, 40)
    assert len(calls) == 2
    assert first['runtime_trace']['executed'] == ('room_detection',)
    main._drawing_analysis.cache_clear()


def test_ocr_dimensions_remain_distinct_from_rotated_modeled_spans():
    plan = {'rooms': [{'id':'test', 'name':'Bedroom', 'polygon':[[0,0],[1.6,1.2],[-.2,3.6],[-1.8,2.4]],
                      'printed_dimensions_m':[None,3.1], 'source_evidence':{'dimension':{'rotation_deg':0}}}]}
    row = measured_scale_audit(plan)['room_dimensions'][0]
    assert row['printed'] == [None,3.1]
    assert all(abs(value-expected) < 1e-8 for value, expected in zip(row['modeled'], [2,3]))
