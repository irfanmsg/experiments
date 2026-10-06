"""Conservative room suggestions from raster drawings, always user-reviewed."""

from __future__ import annotations

from pathlib import Path


def _enclosed_rooms(image_path: str | Path, max_results: int = 60) -> list[dict]:
    import cv2
    import numpy as np

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not read plan image")
    height, width = image.shape[:2]
    scale = min(1.0, 2200 / max(height, width))
    work = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else image
    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    # Floor colours, furniture outlines and text are not room boundaries.
    # Keep substantial dark wall strokes; opening removes thin furnishings
    # before flood-fill so a white mattress cannot become its own room.
    ink = np.uint8(gray < 150) * 255
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    # Only repair tiny scan gaps. Closing door-sized gaps invents divisions
    # and can merge balconies with rooms or round off actual wall corners.
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    free = 255 - ink
    count, labels, stats, _ = cv2.connectedComponentsWithStats(free, connectivity=8)
    work_area = work.shape[0] * work.shape[1]
    candidates = []
    for label in range(1, count):
        x, y, w, h, area = [int(v) for v in stats[label]]
        if x <= 2 or y <= 2 or x + w >= work.shape[1] - 2 or y + h >= work.shape[0] - 2:
            continue
        if area < max(300, work_area * 0.001) or area > work_area * 0.75:
            continue
        if min(w, h) < 14 or max(w / max(h, 1), h / max(w, 1)) > 10:
            continue
        mask = np.uint8(labels[y:y+h, x:x+w] == label) * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        contour = max(contours, key=cv2.contourArea)[:, 0, :].astype(float)
        if len(contour) < 3:
            continue
        contour[:, 0] += x
        contour[:, 1] += y
        perimeter = cv2.arcLength(contour.astype(np.float32), True)
        simple = cv2.approxPolyDP(contour.astype(np.float32), max(1, perimeter * 0.003), True)[:, 0, :]
        # Never substitute a bounding box: it can span other rooms and walls.
        if not (3 <= len(simple) <= 128):
            continue
        polygon = [[round(float(px / scale), 1), round(float(py / scale), 1)] for px, py in simple]
        candidates.append({"pixel_polygon": polygon, "pixel_area": int(cv2.contourArea(contour.astype(np.float32)) / scale**2),
                           "confidence": "suggestion",
                           "detection_basis": "Enclosed area bounded by substantial dark strokes after removing thin linework",
                           "review_note": "Not semantic room recognition. Open doors, glazing, thin walls and cropped boundaries can merge or hide spaces; review against the drawing."})
    candidates.sort(key=lambda item: item["pixel_area"], reverse=True)
    return [{**item, 'label': f'Space {i+1}'} for i, item in enumerate(candidates[:max_results])]


def analyze_drawing(image_path: str | Path, max_results: int = 60, *, text_data=None) -> dict:
    """Combine text anchors and wall evidence into explicitly inferred room outlines."""
    import cv2
    import numpy as np
    from itertools import product
    from .drawing_text import extract_drawing_text

    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError('Could not read plan image')
    text = text_data if text_data is not None else extract_drawing_text(image_path)
    report = {'suggestions': [], 'scale_proposal': None, 'warnings': list(text.get('warnings', [])), 'drawing_text': text}
    labels = text.get('room_labels', [])
    if not labels:
        report['suggestions'] = _enclosed_rooms(image_path, max_results)
        return report
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    thick = cv2.morphologyEx(np.uint8(gray < 150)*255, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    segments = cv2.HoughLinesP(thick, 1, np.pi/720, 60, minLineLength=max(40, min(w,h)*.05), maxLineGap=12)
    votes = np.zeros(121)
    for x0, y0, x1, y1 in segments[:, 0] if segments is not None else []:
        angle = (np.degrees(np.arctan2(y1-y0, x1-x0))+45)%90-45
        if abs(angle) <= 15:
            votes[round((angle+15)*4)] += np.hypot(x1-x0, y1-y0)
    angle = float(np.argmax(votes)/4-15) if votes.any() else 0.
    pad = int(max(w,h)*.15)
    transform = cv2.getRotationMatrix2D((w/2, h/2), angle, 1)
    transform[:, 2] += pad
    inverse = cv2.invertAffineTransform(transform)
    gray = cv2.warpAffine(gray, transform, (w+2*pad, h+2*pad), borderValue=255)
    ink = np.uint8(gray < 175)*255
    thick = cv2.morphologyEx(np.uint8(gray < 150)*255, cv2.MORPH_OPEN, np.ones((5,5), np.uint8))
    strong_near = cv2.dilate(thick, np.ones((9,9), np.uint8)) > 0
    weak_near = cv2.dilate(ink, np.ones((5,5), np.uint8)) > 0
    integral = cv2.integral(np.uint8(thick > 0))

    def point(x, y, matrix=transform):
        return matrix @ np.array([x, y, 1.])

    lines = [[], []]  # axis 0: vertical, axis 1: horizontal
    for strong, mask in ((True, thick), (False, ink)):
        for axis in (0, 1):
            length = max(35, int(min(w,h)*.035))
            kernel = np.ones((length, 3 if strong else 1) if axis == 0 else (3 if strong else 1, length), np.uint8)
            opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            _, _, stats, _ = cv2.connectedComponentsWithStats(opened, connectivity=8)
            for x, y, ww, hh, area in stats[1:]:
                if (hh if axis == 0 else ww) < length:
                    continue
                crop = opened[y:y+hh, x:x+ww] > 0
                profile = crop.sum(axis=0 if axis == 0 else 1)
                peak = np.flatnonzero(profile >= profile.max()*.8)
                lo = (x if axis == 0 else y)+int(peak[0])
                hi = (x if axis == 0 else y)+int(peak[-1])
                start, end = (y, y+hh) if axis == 0 else (x, x+ww)
                if hi-lo > (end-start)/3:
                    continue
                lines[axis].append({'lo': lo, 'hi': hi, 'start': start, 'end': end, 'strong': strong})

    anchors = []
    for label in labels:
        b = label['bbox']
        center = point((b[0]+b[2])/2, (b[1]+b[3])/2)
        matches = [d for d in text.get('dimensions', []) if d.get('room_label_bbox') == b]
        if not matches:
            matches = [d for d in text.get('dimensions', []) if not d.get('room_label_bbox')
                       and d.get('room_label') == label['name']
                       and sum(other['name'] == label['name'] for other in labels) == 1]
        dimension = max(matches, key=lambda d: d.get('confidence', 0), default={})
        dimensions = list(dimension.get('dimensions_m') or dimension.get('dimension_parts_m') or [None, None])
        # Text orientation is not a dimension-axis instruction: a rotated
        # width-by-depth caption still commonly describes plan X then Y.
        anchors.append({'label': label, 'center': center, 'dimension': dimension, 'dimensions': dimensions})

    def sides(anchor, axis, margin, strong_only=False):
        c, other = anchor['center'][axis], anchor['center'][1-axis]
        options = [line for line in lines[axis] if (not strong_only or line['strong'])
                   and line['start']-margin <= other <= line['end']+margin]
        before = sorted({line['hi']+1 for line in options if line['hi'] < c-10}, reverse=True)
        after = sorted({line['lo']-1 for line in options if line['lo'] > c+10})
        return before[:6], after[:6]

    observations = []
    for anchor in anchors:
        if not anchor['dimension'].get('dimensions_m'):
            continue
        for axis, dimension in enumerate(anchor['dimensions']):
            if not dimension or dimension <= 0:
                continue
            before, after = sides(anchor, axis, min(w,h)*.1, True)
            if not before or not after:
                continue
            span = after[0]-before[0]
            other = anchor['center'][1-axis]
            p0 = point(before[0], other, inverse) if axis == 0 else point(other, before[0], inverse)
            p1 = point(after[0], other, inverse) if axis == 0 else point(other, after[0], inverse)
            observations.append({'room_name': anchor['label']['name'], 'pixel_span': float(span),
                                 'dimension_m': dimension, 'pixels_per_meter': span/dimension, 'axis': 'x' if axis == 0 else 'y',
                                 'pixel_points': [p0.tolist(), p1.tolist()], 'text': anchor['dimension']['text']})
    scale = None
    if len(observations) >= 2:
        # Consensus rejects OCR decimals lost as tenfold measurements and wrong adjacent walls.
        consensus = max(([o for o in observations if abs(o['pixels_per_meter']/candidate['pixels_per_meter']-1) < .075]
                         for candidate in observations), key=len)
        midpoint = float(np.median([o['pixels_per_meter'] for o in consensus]))
        consensus = [o for o in consensus if abs(o['pixels_per_meter']/midpoint-1) <= .075]
        if len({o['room_name'] for o in consensus}) >= 2 and len({o['axis'] for o in consensus}) == 2:
            scale = float(np.median([o['pixels_per_meter'] for o in consensus]))
            for observation in consensus:
                observation['relative_error'] = observation['pixels_per_meter']/scale-1
            residual = max(abs(o['relative_error']) for o in consensus)
            report['scale_proposal'] = {'pixels_per_meter': scale, 'observations': consensus,
                                        'excluded_observations': [{**o, 'reason': 'Disagrees with independent room measurements; OCR digits, wall matching or raster distortion need review.'} for o in observations if o not in consensus],
                                        'max_relative_error': residual,
                                        'review_note': 'Estimated from OCR dimensions and opposing wall strokes. Confirm before applying; the raster can be distorted and OCR can misread digits.',
                                        'warnings': (['Some printed dimensions or wall matches disagree and were excluded; review those rooms separately.'] if len(consensus) < len(observations) else [])
                                                    + (['Wall-to-dimension readings vary; this is an approximate uniform image scale.'] if residual > .04 else [])}

    def support(mask, axis, fixed, start, end):
        fixed, start, end = int(round(fixed)), int(round(start)), int(round(end))
        values = mask[start:end+1, fixed] if axis == 0 else mask[fixed, start:end+1]
        return float(values.mean()) if values.size else 0.

    proposals, unmatched_anchors = [], []
    for anchor in anchors:
        dimensions = anchor['dimensions']
        margin = scale*1.3 if scale else min(w,h)*.08
        xs, xe = sides(anchor, 0, margin)
        ys, ye = sides(anchor, 1, margin)
        original_sides = [set(values) for values in (xs, xe, ys, ye)]
        if scale:
            for axis, values in enumerate(((xs, xe), (ys, ye))):
                if dimensions[axis]:
                    expected = dimensions[axis]*scale
                    before, after = values
                    c = anchor['center'][axis]
                    before += [round(v-expected) for v in after[:3] if v-expected < c-10]
                    after += [round(v+expected) for v in before[:3] if v+expected > c+10]
        xs, xe, ys, ye = [list(dict.fromkeys(values)) for values in (xs, xe, ys, ye)]
        best = None
        for left, right, top, bottom in product(xs, xe, ys, ye):
            width, height = right-left, bottom-top
            if min(width,height) < max(35, min(w,h)*.025) or min(left,top)<0 or right>=gray.shape[1] or bottom>=gray.shape[0]:
                continue
            errors = [abs(span/(dimension*scale)-1) for span,dimension in zip((width,height),dimensions) if dimension and scale]
            if errors and max(errors) > .16:
                continue
            bounds = [(0,left,top,bottom), (0,right,top,bottom), (1,top,left,right), (1,bottom,left,right)]
            strength = [support(strong_near, *edge) for edge in bounds]
            thin = [support(weak_near, *edge) for edge in bounds]
            evidenced = sum(value >= .25 for value in strength)
            if evidenced < 3:
                continue
            if any(strength[i]<.25 and thin[i]<.8 and (not scale or not dimensions[0 if i<2 else 1]) for i in range(4)):
                continue
            if any(strength[i]<.35 and not dimensions[0 if i<2 else 1] for i in range(4)):
                continue
            # A room rectangle may bridge openings but must not cross another wall.
            a,b,c,d = int(left+9),int(top+9),int(right-9),int(bottom-9)
            wall_fraction = float(integral[d,c]-integral[b,c]-integral[d,a]+integral[b,a])/max(1,(c-a)*(d-b))
            if wall_fraction > .028:
                continue
            enclosed_labels = [other for other in anchors if left<other['center'][0]<right and top<other['center'][1]<bottom]
            if len(enclosed_labels)>1 and not all(other['label']['name'].lower() in {'living','dining','lounge','family room'} for other in enclosed_labels):
                continue
            score = sum(strength)+.25*sum(thin)-3*sum(errors)-wall_fraction*30
            if best is None or score>best[0]:
                best = (score,(left,right,top,bottom),strength,thin,enclosed_labels)
        if best is None:
            unmatched_anchors.append(anchor)
            continue
        _, (left,right,top,bottom), strengths, thin, grouped = best
        polygon = [point(x,y,inverse).round(1).tolist() for x,y in ((left,top),(right,top),(right,bottom),(left,bottom))]
        evidence, inferred, openings = [], [], []
        for i, (name, value) in enumerate(zip(('left','right','top','bottom'), (left,right,top,bottom))):
            invented = value not in original_sides[i]
            item = {'side': name, 'structural_wall_support': round(strengths[i],3),
                    'all_line_support': round(thin[i],3), 'inferred': invented or strengths[i]<.85,
                    'basis': 'Readable dimension projected from the opposing wall' if invented else 'Aligned wall/window strokes; gaps between strokes treated as openings'}
            axis = 0 if i < 2 else 1
            start, end = (top, bottom) if axis == 0 else (left, right)

            def edge_point(offset):
                return point(value, offset, inverse) if axis == 0 else point(offset, value, inverse)

            item['pixel_start'] = edge_point(start).round(1).tolist()
            item['pixel_end'] = edge_point(end).round(1).tolist()
            # A geometrical room division is not proof of a solid wall. Keep
            # substantial missing wall segments visible and editable as openings.
            samples = (strong_near[round(start):round(end)+1, round(value)] if axis == 0
                       else strong_near[round(value), round(start):round(end)+1])
            missing = np.flatnonzero(np.diff(np.r_[False, ~samples, False]))
            runs = list(zip(missing[::2], missing[1::2]))
            if strengths[i] < .25:
                runs = [(0, round(end-start))]
                item['do_not_assume_solid_wall'] = True
            gaps = []
            for a, b in runs:
                if b-a < max(20, (scale or min(w,h)/12)*.45):
                    continue
                p0, p1 = edge_point(start+a), edge_point(min(end, start+b))
                gap = {'pixel_start': p0.round(1).tolist(), 'pixel_end': p1.round(1).tolist(),
                       'pixel_center': ((p0+p1)/2).round(1).tolist(), 'width_px': round(float(np.linalg.norm(p1-p0)),1),
                       'type': 'opening', 'no_header': True, 'confidence': 'needs-review', 'side': name,
                       'basis': 'Dimension-supported room division without an observed wall' if strengths[i] < .25
                                else 'Gap in aligned structural-wall strokes; door versus window is unclassified'}
                gaps.append(gap)
                openings.append(gap)
            item['gaps'] = gaps
            evidence.append(item)
            if item['inferred']:
                inferred.append(item)
        name = ' / '.join(dict.fromkeys(other['label']['name'] for other in grouped)) or anchor['label']['name']
        max_dimension_error = None
        dimension_evidence = dict(anchor['dimension'])
        if dimension_evidence:
            matches = []
            for axis, (span, dimension) in enumerate(zip((right-left, bottom-top), dimensions)):
                if not dimension:
                    continue
                a, b = ((left, (top+bottom)/2), (right, (top+bottom)/2)) if axis == 0 else (((left+right)/2, top), ((left+right)/2, bottom))
                matches.append({'axis': 'x' if axis == 0 else 'y', 'pixel_span': float(span), 'dimension_m': dimension,
                                'pixel_points': [point(*a, inverse).round(1).tolist(), point(*b, inverse).round(1).tolist()],
                                'relative_error': span/(dimension*scale)-1 if scale else None})
            dimension_evidence['wall_matches'] = matches
            max_dimension_error = max((abs(match['relative_error']) for match in matches if match['relative_error'] is not None), default=None)
            if max_dimension_error is not None and max_dimension_error > .075:
                report['warnings'].append(f'{name}: proposed walls differ from a printed dimension by more than 7.5%; verify the outline and image distortion.')
        proposals.append({'label': name, 'name': name, 'pixel_polygon': polygon, 'pixel_area': round((right-left)*(bottom-top)),
                          'confidence': 'needs-review', 'detection_basis': 'OCR room label anchored to aligned structural walls and readable dimensions',
                          'dimension_evidence': dimension_evidence, 'wall_evidence': evidence, 'inferred_boundaries': inferred,
                          'pixel_openings': openings, 'max_dimension_relative_error': max_dimension_error,
                          'review_note': 'Proposed wall-aligned outline. Door/window gaps and any open-plan boundary are inferred; verify against the drawing.',
                          'deskew_degrees': angle})
    # Shared living/dining anchors can produce the same open-plan outline.
    from shapely.geometry import Point, Polygon
    for proposal in sorted(proposals, key=lambda item: -item['pixel_area']):
        polygon = Polygon(proposal['pixel_polygon'])
        if any(polygon.intersection(Polygon(other['pixel_polygon'])).area/min(polygon.area,other['pixel_area']) > .03 for other in report['suggestions']):
            continue
        report['suggestions'].append(proposal)
    report['suggestions'] = report['suggestions'][:max_results]
    if not report['suggestions']:
        report['suggestions'] = _enclosed_rooms(image_path, max_results)
    accepted_shapes = [Polygon(item['pixel_polygon']) for item in report['suggestions']]
    for anchor in unmatched_anchors:
        location = Point(point(*anchor['center'], inverse))
        if not any(shape.covers(location) for shape in accepted_shapes):
            report['warnings'].append(f"{anchor['label']['name']}: no sufficiently supported room boundary; trace or correct this space manually.")
    return report


def suggest_rooms(image_path: str | Path, max_results: int = 60) -> list[dict]:
    return analyze_drawing(image_path, max_results)['suggestions']
