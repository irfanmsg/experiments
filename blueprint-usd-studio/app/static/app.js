const $ = (id) => document.getElementById(id);
const state = { project: null, plan: null, image: null, styles: [], style: "contemporary", revision: 0, tool: null, points: [], dragStart: null, hover: null, saveTimer: null, suggestions: [], selectedAsset: null, generated: null, assets: [], reviewOpening: null };
const canvas = $("planCanvas");
const ctx = canvas.getContext("2d");

async function request(path, options = {}) {
  const response = await fetch(path, options);
  let data;
  try { data = await response.json(); } catch { data = {}; }
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === "string" ? detail : detail?.errors?.join("; ") || `Request failed (${response.status})`);
  }
  return data;
}
function toast(message) {
  const node = $("toast"); node.textContent = message; node.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => node.hidden = true, 5000);
}
function safeNumber(value, fallback) { const number = Number(value); return Number.isFinite(number) ? number : fallback; }
function calibration() {
  if (state.plan?.dimension_model && state.plan.rooms?.length) {
    const points = state.plan.rooms.flatMap(r => r.polygon);
    const xs = points.map(p=>p[0]), ys = points.map(p=>p[1]);
    const minx=Math.min(...xs), maxx=Math.max(...xs), miny=Math.min(...ys), maxy=Math.max(...ys);
    const scale=.90*Math.min(canvas.width/(maxx-minx),canvas.height/(maxy-miny));
    return {scale,origin:[(canvas.width-(maxx-minx)*scale)/2-minx*scale,(canvas.height-(maxy-miny)*scale)/2+maxy*scale]};
  }
  const value = state.plan?.calibration;
  if (!value) return null;
  const scale = value.pixels_per_meter || value.pixels_per_metre || value.px_per_m || value.scale_px_per_m;
  const origin = value.pixel_origin || value.origin_px || value.origin_in_crop_px || [0, state.image?.naturalHeight || 0];
  if (!scale || !Array.isArray(origin)) return null;
  return { scale: Number(scale), origin };
}
function pixelToMetres(point) {
  const cal = calibration(); if (!cal) throw new Error("Mark one known distance first");
  return [+( (point[0] - cal.origin[0]) / cal.scale ).toFixed(3), +( (cal.origin[1] - point[1]) / cal.scale ).toFixed(3)];
}
function metresToPixel(point) {
  const cal = calibration(); if (!cal) return null;
  return [cal.origin[0] + Number(point[0]) * cal.scale, cal.origin[1] - Number(point[1]) * cal.scale];
}
function getPixel(event) {
  const rect = canvas.getBoundingClientRect();
  return [(event.clientX - rect.left) * canvas.width / rect.width, (event.clientY - rect.top) * canvas.height / rect.height];
}
function distance(a, b) { return Math.hypot(a[0] - b[0], a[1] - b[1]); }
function polygonArea(points) {
  if (!points || points.length < 3) return 0;
  return Math.abs(points.reduce((sum, p, i) => sum + p[0] * points[(i + 1) % points.length][1] - points[(i + 1) % points.length][0] * p[1], 0) / 2);
}
function centroid(points) { return [points.reduce((s, p) => s + p[0], 0) / points.length, points.reduce((s, p) => s + p[1], 0) / points.length]; }
function hex(rgb) { return `#${rgb.map(n => Math.round(n * 255).toString(16).padStart(2, "0")).join("")}`; }
function dimensions(room) {
  const d = room.dimensions_m;
  if (Array.isArray(d) && d.length >= 2) return `${Number(d[0]).toFixed(2)} × ${Number(d[1]).toFixed(2)} m`;
  if (d && typeof d === "object" && d.width && d.length) return `${d.width} × ${d.length} m`;
  return `${polygonArea(room.polygon).toFixed(1)} m² traced`;
}

function setTool(tool) {
  if (tool === 'calibrate' && state.plan?.dimension_model) { toast('This plan uses printed meter dimensions. Image calibration is not needed.'); return; }
  state.tool = state.tool === tool ? null : tool;
  state.points = []; state.dragStart = null; state.hover = null;
  document.querySelectorAll(".tool").forEach(button => button.classList.toggle("active", button.dataset.tool === state.tool));
  $("clearTool").hidden = !state.tool;
  $("finishOutline").hidden = !["room-polygon", "perimeter", "balcony"].includes(state.tool);
  $("openingWidthRow").hidden = !["door", "window"].includes(state.tool);
  const hints = { calibrate: "Click the two endpoints of a printed measurement.", "room-rectangle": "Drag a rectangle around one room.", "room-polygon": "Click each corner of a room, then Finish this outline.", perimeter: "Click the outer corners, then Finish this outline.", balcony: "Click the balcony corners, then Finish this outline.", door: "Click where the doorway crosses a wall.", window: "Click where the window crosses a wall.", asset: "Click where the selected furnishing belongs." };
  $("toolHint").textContent = hints[state.tool] || "Review the traced plan, or choose a tool on the left.";
  draw();
}
function markChanged() {
  state.revision++;
  state.styles.forEach(style => { style.preview_url = null; });
  renderStyles();
  invalidateGenerated();
  $("saveState").textContent = "Saving…";
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(savePlan, 450);
  refreshAll();
}
function invalidateGenerated() {
  if (!state.generated) return;
  state.generated = null;
  $("resultPanel").hidden = true;
  $("generateStatus").textContent = "Plan changed. Create the 3D scene again to include your edits.";
  if (!$("streamPanel").hidden) $("streamPanel").querySelector("p").textContent = "This live view shows the previous scene. Create a new scene and restart the view to see your edits.";
}
async function savePlan() {
  if (!state.project || !state.plan) return;
  try {
    await request(`/api/projects/${state.project}/plan`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(state.plan) });
    $("saveState").textContent = "Saved";
  } catch (error) { $("saveState").textContent = "Save failed"; toast(error.message); }
}
async function setProject(data) {
  state.project = data.id; state.plan = data.plan; state.styles = data.styles || [];
  state.suggestions = []; state.suggesting = false;
  $('suggestions').replaceChildren(); $('suggestions').hidden = true; $('acceptSuggestions').hidden = true;
  $('suggestionStatus').textContent = state.plan.rooms?.length ? 'Review these rooms. You can rename them or adjust the outlines.' : 'Looking for room outlines…';
  state.editableObjects = data.editable_objects || {};
  $('sourceFilesInput').disabled = false;
  loadSupportingSources();
  if (state.plan.source?.primary_crop === 'agreement_unit_crop.jpg') state.style = availableStyles().find(style => style.is_design_scheme)?.id || availableStyles().find(style => style.id === 'home_specification')?.id || 'contemporary';
  state.reviewOpening = null;
  state.generated = null; state.selectedAsset = null; state.revision = 0;
  $("generateStatus").textContent = "";
  localStorage.setItem("blueprint-studio-project", data.id);
  const projectUrl = new URL(location.href);
  projectUrl.searchParams.set('project', data.id);
  projectUrl.searchParams.delete('example');
  history.replaceState(null, '', projectUrl);
  const isOlderExample = state.plan.example === 'B1-1502' && state.plan.source?.primary_crop !== 'agreement_unit_crop.jpg';
  $('legacyProjectNotice').hidden = !isOlderExample;
  $('liveProjectLink').hidden = true;
  if (isOlderExample) request('/api/stream/status').then(status => {
    if (state.project !== data.id || !status.running || !status.project_id || status.project_id === data.id) return;
    $('liveProjectLink').href = `/?project=${encodeURIComponent(status.project_id)}`;
    $('liveProjectLink').hidden = false;
  }).catch(() => {});
  $("projectTitle").textContent = state.plan.name || "Untitled project";
  $("projectSubtitle").textContent = state.plan.example ? `Flat B1-1502 · 15th floor · ${state.plan.source?.primary_crop === 'agreement_unit_crop.jpg' ? 'demarcated agreement plan' : 'approved architectural plan'}` : "Review your drawing, then build a measured 3D scene.";
  $("sourceNote").textContent = state.plan.source?.filename || (state.plan.example ? "Approved B1 building plan · unit 1502" : "Your drawing");
  if(state.plan.dimension_model) $("sourceNote").textContent=`Dimensioned plan · 1 m grid · ${state.plan.source?.primary_crop === 'agreement_unit_crop.jpg' ? 'agreement' : 'approved'} metric room dimensions`;
  $("sourceNote").hidden = false;
  renderAssets();
  $("pageControls").hidden = !(data.page_count > 1);
  if (data.page_count > 1) {
    $("pageSelect").replaceChildren(...Array.from({ length: data.page_count }, (_, i) => { const option = document.createElement("option"); option.value = i + 1; option.textContent = `Page ${i + 1}`; return option; }));
    $("pageSelect").value = state.plan.page || 1;
  }
  $("structureType").value = ["home", "factory", "office", "showroom", "other"].includes(state.plan.structure_type) ? state.plan.structure_type : "home";
  $("heightInput").value = state.plan.room_height_m || 2.9;
  $("heightStatus").textContent = state.plan.height_status || "Wall height is a visualization assumption. Confirm it if known.";
  $("showLabels").checked = !!state.plan.dimension_model || !state.plan.example;
  const image = new Image();
  image.onload = () => {
    if (state.project !== data.id || state.plan !== data.plan) return;
    state.image = image; canvas.width = image.naturalWidth; canvas.height = image.naturalHeight;
    $("canvasArea").hidden = false; $("emptyState").hidden = true;
    $("calibrateButton").disabled = !!state.plan.dimension_model; $("suggestButton").disabled = !!state.plan.dimension_model;
    document.querySelectorAll(".tool").forEach(button => button.disabled = false);
    if (!state.plan.image_size) state.plan.image_size = [image.naturalWidth, image.naturalHeight];
    renderStyles(); refreshAll();
    if (!state.plan.rooms?.length && !state.plan.dimension_model) findRoomSuggestions();
    if (state.plan.example && state.plan.footprint?.polygon?.length) requestAnimationFrame(() => {
      const pixels = state.plan.footprint.polygon.map(metresToPixel);
      const centerY = pixels.reduce((sum, point) => sum + point[1], 0) / pixels.length;
      const scroller = document.querySelector(".canvas-scroll");
      scroller.scrollTop = centerY * canvas.getBoundingClientRect().height / canvas.height - scroller.clientHeight / 2;
    });
  };
  image.onerror = () => toast("Could not show this plan image");
  image.src = `${data.image_url}?v=${Date.now()}`;
  $("resultPanel").hidden = true; $("streamPanel").hidden = true;
  loadSharedStream();
  setTool(null);
}
async function loadSharedStream() {
  const project = state.project;
  try {
    const status = await request('/api/stream/status');
    if (state.project !== project || !status.running || startStream.poller) return;
    $('streamPanel').hidden = false;
    $('streamPanel').querySelector('p').textContent = `Shared GPU view: ${status.style} (${status.project_id}). All viewers share the camera. Stop this view before starting another project.`;
    const link = $('streamLink'); link.hidden = !['ready', 'running', 'client_connected'].includes(status.phase);
    link.href = `http://${location.hostname}:8088/?signal_port=49100`; link.textContent = link.href;
  } catch { /* The editor remains available when no stream status can be read. */ }
}
function updateSteps() {
  const steps = [$("step-upload"), $("step-measure"), $("step-outline"), $("step-create")];
  const completed = state.project ? calibration() ? (state.plan?.rooms?.length || state.plan?.footprint?.polygon?.length ? 3 : 2) : 1 : 0;
  steps.forEach((node, i) => { node.classList.toggle("done", i < completed); node.classList.toggle("active", i === Math.min(completed, 3)); });
}
function refreshRooms() {
  const list = $("roomList"); list.replaceChildren();
  (state.plan?.rooms || []).forEach((room, index) => {
    const row = document.createElement("div"); row.className = "room-row";
    const label = document.createElement("div");
    const strong = document.createElement('input'); strong.type = 'text'; strong.value = room.name || `Room ${index + 1}`;
    strong.setAttribute('aria-label', `Name of room ${index + 1}`);
    strong.onchange = () => { room.name = strong.value.trim() || `Room ${index + 1}`; markChanged(); };
    const small = document.createElement("small"); small.textContent = ` · ${dimensions(room)}`;
    label.append(strong, small);
    const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "Remove"; remove.setAttribute("aria-label", `Remove ${room.name || "room"}`);
    remove.onclick = () => { state.plan.rooms.splice(index, 1); markChanged(); };
    row.append(label, remove); list.append(row);
  });
}
function allPlacements() {
  const overrides = state.plan?.object_overrides?.[state.style] || {};
  return [...(state.plan?.asset_placements || []), ...(state.editableObjects?.[state.style] || [])
    .map(item => ({...item, ...overrides[item.id], procedural: true}))
    .filter(item => !item.removed)];
}
function editPlacement(placement, change) {
  if (placement.procedural) {
    state.plan.object_overrides ||= {};
    state.plan.object_overrides[state.style] ||= {};
    const edits = state.plan.object_overrides[state.style];
    edits[placement.id] = {...edits[placement.id], ...change};
  } else Object.assign(placement, change);
}
function refreshPlacements() {
  const list = $("placementList"); list.replaceChildren();
  allPlacements().forEach(placement => {
    const row = document.createElement("div"); row.className = "room-row";
    const details = document.createElement("div"); details.className = "placement-details";
    const name = document.createElement("strong"); name.textContent = placement.name || placement.id || "Furnishing";
    const kind = document.createElement('small'); kind.textContent = placement.asset_kind || (placement.procedural ? 'Procedural USD' : 'NVIDIA SimReady USD');
    const move = document.createElement('button'); move.type = 'button'; move.textContent = 'Move'; move.setAttribute('aria-label', `Move ${name.textContent}`);
    move.onclick = () => { state.movingPlacement = placement; state.tool = 'move-placement'; $('canvasArea').scrollIntoView({block:'center'}); $('toolHint').textContent = `Click the new position for ${name.textContent}, or drag its marker.`; toast(`Click the plan to move ${name.textContent}`); };
    const controls = document.createElement("div"); controls.className = "placement-controls";
    for (const [label, axis, unit] of [["X", 0, "metres"], ["Y", 1, "metres"], ["Rotation", null, "degrees"]]) {
      const field = document.createElement("label"); field.textContent = `${label} ${unit === "metres" ? "(m)" : "(°)"} `;
      const input = document.createElement("input"); input.type = "number"; input.step = axis === null ? "1" : "0.01"; input.className = "placement-coordinate";
      const value = axis === null ? placement.rotation_deg || 0 : placement.position?.[axis] || 0;
      input.value = value; input.setAttribute("aria-label", `${label} of ${name.textContent} in ${unit}`);
      input.onchange = () => {
        const next = input.valueAsNumber;
        if (!Number.isFinite(next)) { input.value = value; toast(`${label} must be a finite number`); return; }
        if (axis === null) editPlacement(placement, {rotation_deg: next});
        else { const position = [...(placement.position || [0, 0, 0])]; position[axis] = next; editPlacement(placement, {position}); }
        markChanged();
      };
      field.append(input); controls.append(field);
    }
    if (!placement.procedural) {
    const movableLabel = document.createElement("label");
    const movable = document.createElement("input"); movable.type = "checkbox"; movable.checked = placement.physics_mode === "dynamic";
    movable.setAttribute("aria-label", `Dynamic physics for ${name.textContent}`);
    movable.onchange = () => { placement.physics_mode = movable.checked ? "dynamic" : "static"; if (!movable.checked) placement.position[2] = 0; markChanged(); };
    movableLabel.append(movable, " Dynamic physics"); controls.append(movableLabel);
    if (movable.checked) {
      const heightLabel = document.createElement("label"); heightLabel.textContent = "Start height ";
      const height = document.createElement("input"); height.type = "number"; height.min = "0"; height.max = "20"; height.step = "0.1"; height.value = Number(placement.position?.[2] || 0).toFixed(1); height.setAttribute("aria-label", `Starting height of ${name.textContent} in metres`);
      height.onchange = () => { const z = Number(height.value); if (!Number.isFinite(z) || z < 0 || z > 20) { toast("Starting height must be between 0 and 20 metres"); return; } placement.position[2] = z; markChanged(); };
      heightLabel.append(height, " m"); controls.append(heightLabel);
    }
    }
    const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "Remove"; remove.setAttribute("aria-label", `Remove furnishing ${name.textContent}`);
    remove.onclick = () => { if (placement.procedural) editPlacement(placement, {removed:true}); else state.plan.asset_placements = state.plan.asset_placements.filter(item => item !== placement); markChanged(); };
    details.append(name, kind, move, controls); row.append(details, remove); list.append(row);
  });
}
function refreshMeasurements() {
  const cal = calibration();
  $("scaleSummary").textContent = state.plan?.dimension_model ? "Printed meter dimensions enforced. Each grid square is 1 m × 1 m." : cal ? `Scale set: ${cal.scale.toFixed(1)} image pixels = 1 metre.` : state.project ? "Use a dimension printed on the plan. Click its two endpoints." : "Upload a drawing to begin.";
  $("canvasScale").textContent = cal ? `1 m ≈ ${cal.scale.toFixed(1)} px` : "Scale not set";
  const badges = $("measurementBadges"); badges.replaceChildren();
  if (!state.plan) { $("drawingInfo").hidden = true; return; }
  const area = state.plan.area_schedule_m2;
  const values = area ? [`${Number(area.carpet).toFixed(2)} m² carpet`, `${Number(area.balcony).toFixed(2)} m² balcony`, `${Number(area.dry_balcony).toFixed(2)} m² dry balcony`, `${Number(area.total).toFixed(2)} m² scheduled total`] : [`${state.plan.rooms?.length || 0} rooms outlined`, cal ? "Measured in metres" : "Scale needs review"];
  values.forEach(value => { const badge = document.createElement("span"); badge.textContent = value; badges.append(badge); });
  $("provenanceText").textContent = area ? `B1-1502 areas come from the printed RERA schedule. Room spans follow the ${state.plan.source?.primary_crop === 'agreement_unit_crop.jpg' ? 'demarcated agreement' : 'approved'} metric dimensions; wall thickness, heights and the detailed balcony curve remain assumptions.` : "Room outlines come from your review. Confirm any unprinted dimension before using the model for construction or purchasing.";
  if (state.plan.example === 'B1-1502' && state.plan.source?.primary_crop !== 'agreement_unit_crop.jpg') $("provenanceText").textContent += ' This is an older B1 reconstruction. Load the B1 example to review the agreement rebuild; this project is preserved.';
  $("drawingInfo").hidden = false;
}
function refreshReconstructionReview() {
  const plan = state.plan, review = $("reconstructionReview");
  review.hidden = !plan;
  if (!plan) return;
  const openings = plan.openings || [], decisions = [...(plan.reconstruction_decisions || []), ...(state.generated?.result.presentation_decisions || [])];
  const sourced = openings.filter(o => o.provenance?.topology === "source-derived").length;
  const inferred = openings.filter(o => o.provenance?.topology === "inferred").length;
  $("reconstructionCounts").textContent = `${sourced} openings with source-derived access · ${inferred} inferred · ${openings.length - sourced - inferred} without recorded access evidence · ${decisions.filter(d => d.status === "needs-review").length} decisions need review. Opening heights and assemblies remain assumptions.`;
  $("reconstructionTrace").href = `/api/projects/${state.project}/reconstruction-trace`;
  const text = (parent, tag, value) => { const node = document.createElement(tag); node.textContent = value; parent.append(node); return node; };
  const readable = value => String(value || "Unrecorded").replaceAll("_", " ");
  const manifest = plan.reference_manifest;
  $('referenceContext').hidden = !manifest;
  if (manifest) {
    const ledger = $('referenceLedger'); ledger.replaceChildren();
    text(ledger, 'p', `Geometry: ${manifest.primary_layout.file}, page ${manifest.primary_layout.pdf_page}, Annexure ${manifest.primary_layout.annexure}.`);
    const list = document.createElement('ul');
    for (const source of manifest.sources || []) text(list, 'li', `${source.file}: ${source.role}${source.pages?.length ? `; pages ${source.pages.map(page => page.number).join(', ')}` : ''}`);
    ledger.append(list);
    const photos = manifest.construction_photo_review;
    if (photos) text(ledger, 'p', `${photos.summary.file_count} construction-folder images reviewed: ${photos.summary.construction_exterior_count} exterior photos and ${photos.summary.sales_office_scale_model_count} builder scale-model views. Several show floor 15; tower/unit identity and metric calibration remain unconfirmed. These photos guide exterior detail, not room dimensions or interior finishes.`);
    for (const conflict of manifest.unresolved || []) text(ledger, 'p', typeof conflict === 'string' ? conflict : conflict.summary || conflict.description || JSON.stringify(conflict));
    const finishes = $('finishSpecification'); finishes.replaceChildren();
    const spec = manifest.finish_schedule;
    text(finishes, 'p', `${spec.file}, page ${spec.pdf_page}, Annexure ${spec.annexure}. Master bedroom: ${spec.flooring.master}. Other rooms: ${spec.flooring.other}. Wet areas: ${spec.flooring.wet}. Bathroom tile height: ${Number(spec.bathroom_dado_height_m).toFixed(2)} m.`);
    text(finishes, 'p', 'Exact colours, furniture sizes, cabinetry details and lighting are reviewable visualization assumptions. The specified-finish preset applies the documented surface types.');
  }
  const metric = value => value != null && value !== "" && Number.isFinite(Number(value)) ? Number(value).toFixed(2) : "unrecorded";
  const spans = value => Array.isArray(value) && value.length >= 2 ? `${value.map(metric).join(" × ")} m` : "unrecorded";
  const roomName = id => plan.rooms?.find(room => room.id === id)?.name || readable(id);
  const scale = $("reconstructionScale"); scale.replaceChildren();
  const audit = plan.scale_audit && { ...plan.scale_audit };
  if (audit) {
    const polygonSpans = points => {
      if (!points?.length) return [];
      const xs = points.map(point => Number(point[0])), ys = points.map(point => Number(point[1]));
      return [Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)];
    };
    audit.room_dimensions = (plan.rooms || []).map(room => {
      const modeled = polygonSpans(room.polygon);
      if (room.dimension_mode === "average_depth" && modeled.length) {
        const axis = Number(room.span_axis) === 1 ? 1 : 0;
        modeled[1 - axis] = modeled[axis] > 0 ? polygonArea(room.polygon) / modeled[axis] : null;
      }
      return { id: room.id, name: room.name, printed: room.dimensions_m, modeled, dimension_mode: room.dimension_mode };
    });
    audit.footprint_span_m = polygonSpans(plan.footprint?.polygon);
    audit.gross_area_m2 = polygonArea(plan.footprint?.polygon) - (plan.footprint?.holes || []).reduce((area, hole) => area + polygonArea(hole), 0);
    const scheduled = typeof audit.scheduled_area_m2 === "object" ? audit.scheduled_area_m2?.total : audit.scheduled_area_m2;
    text(scale, "p", `${metric(audit.meters_per_unit)} m per scene unit. Model footprint span: ${spans(audit.footprint_span_m)}; approximate source trace span: ${spans(audit.source_trace_span_m)}.`);
    if (audit.source_trace_basis) text(scale, 'p', `Source trace basis: ${audit.source_trace_basis}.`);
    if (audit.visible_agreement_span_m) text(scale, 'p', `Visible agreement bounds: ${spans(audit.visible_agreement_span_m)}; corresponding modeled bounds: ${spans(audit.modeled_visible_span_m)}. Image registration and unprinted offsets remain approximate.`);
    text(scale, "p", `Modeled gross footprint: ${metric(audit.gross_area_m2)} m². Source scheduled total: ${metric(scheduled)} m². Gross geometry and the scheduled net areas are different measurements.`);
    const wrap = document.createElement("div"); wrap.className = "review-table"; wrap.tabIndex = 0;
    const table = document.createElement("table"); const header = document.createElement("tr");
    ["Space", "Printed dimensions", "Modeled dimensions"].forEach(label => text(header, "th", label).scope = "col");
    const head = document.createElement("thead"); head.append(header); table.append(head);
    const body = document.createElement("tbody");
    (audit.room_dimensions || []).forEach(room => {
      const row = document.createElement("tr");
      const roles = room.dimension_mode === "average_depth" ? ` (${(plan.rooms?.find(item => item.id === room.id)?.dimension_roles || ["span", "average depth"]).map(readable).join(" × ")})` : "";
      text(row, "th", `${room.name || roomName(room.id)}${roles}`).scope = "row";
      text(row, "td", spans(room.printed)); text(row, "td", spans(room.modeled)); body.append(row);
    });
    table.append(body); wrap.append(table); scale.append(wrap);
    text(scale, "p", "Modeled dimensions and gross area are recalculated from the current outlines. Printed dimensions and the source trace remain separate references.");
    if (audit.notes) text(scale, "p", `Original reconstruction basis: ${Array.isArray(audit.notes) ? audit.notes.join(" ") : audit.notes}`);
  } else text(scale, "p", "A detailed scale comparison has not been recorded for this plan. Review the calibration and printed measurements.");
  const decisionList = $("reconstructionDecisions"); decisionList.replaceChildren();
  decisions.forEach(decision => {
    const item = document.createElement("li"); text(item, "strong", `${readable(decision.kind)} · ${readable(decision.status)}`);
    text(item, "code", decision.id); text(item, "p", decision.summary || ""); text(item, "p", `Basis: ${decision.basis || "unrecorded"}`);
    if (decision.parameters) text(item, "p", `Parameters: ${JSON.stringify(decision.parameters)}`);
    decisionList.append(item);
  });
  if (!decisions.length) text(decisionList, "li", "No reconstruction decisions have been recorded yet.");
  const openingList = $("reconstructionOpenings"); openingList.replaceChildren();
  openings.forEach(opening => {
    const item = document.createElement("li"), provenance = opening.provenance || {};
    text(item, "strong", opening.name || readable(opening.id)); text(item, "code", opening.id);
    text(item, "p", `${readable(opening.type)} · ${metric(opening.width_m)} m wide × ${metric(opening.height_m)} m high · ${(opening.connects || []).map(roomName).join(" ↔ ") || "connected spaces unrecorded"}`);
    text(item, "p", `Access: ${provenance.topology || "unrecorded"}; width: ${provenance.width || "unrecorded"}; height: ${provenance.height || "unrecorded"}; ${provenance.review_status || "needs review"}.`);
    text(item, "p", `Basis: ${provenance.basis || opening.confidence || "unrecorded"}. Placement: ${provenance.placement || "unrecorded"}.`);
    const reference = provenance.source_reference;
    if (reference) {
      if (typeof reference === "string") text(item, "p", `Source: ${reference}`);
      else {
        const source = [reference.file, reference.page ? `page ${reference.page}` : null, reference.sheet, reference.image].filter(Boolean).join(" · ");
        const jambs = reference.image_coordinates_px;
        const hasJambs = Array.isArray(jambs?.jamb_start) && Array.isArray(jambs?.jamb_end);
        const symbol = Array.isArray(reference.symbol_center_px) ? reference.symbol_center_px : null;
        text(item, "p", `Source: ${source || "unrecorded"}${symbol ? ` · symbol at (${symbol.join(", ")}) px` : ""}${hasJambs ? ` · jambs (${jambs.jamb_start.join(", ")}) → (${jambs.jamb_end.join(", ")}) px` : ""}${reference.image_coordinate_uncertainty_px ? ` · ±${reference.image_coordinate_uncertainty_px} px trace uncertainty` : ""}`);
      }
    }
    const button = text(item, "button", "Show on plan"); button.type = "button"; button.className = "subtle-button";
    button.setAttribute("aria-label", `Show ${readable(opening.id)} on plan`);
    button.onclick = () => {
      state.reviewOpening = opening.id; draw();
      const point = metresToPixel(opening.center || opening.start), scroller = document.querySelector(".canvas-scroll");
      if (point) scroller.scrollTop = point[1] * canvas.getBoundingClientRect().height / canvas.height - scroller.clientHeight / 2;
      $("canvasArea").scrollIntoView({ block: "center", behavior: "smooth" });
    };
    openingList.append(item);
  });
  if (!openings.length) text(openingList, "li", "No openings have been recorded yet.");
}
function updateCreateReady() {
  const measured = !!calibration();
  const outlined = state.plan?.footprint?.polygon?.length >= 3 || (state.plan?.rooms || []).some(room => room.polygon?.length >= 3);
  const ready = measured && outlined;
  $("generateButton").disabled = !ready; $("allStylesButton").disabled = !ready;
  if (!measured) $("generateStatus").textContent = "Mark one known distance to set the scale first.";
  else if (!outlined) $("generateStatus").textContent = "Accept a suggested room, or draw an outline, to create a 3D scene.";
  else if (!state.generated && ["Mark one known distance", "Accept a suggested room"].some(text => $("generateStatus").textContent.startsWith(text))) $("generateStatus").textContent = "";
}
function refreshAll() { updateSteps(); refreshRooms(); refreshPlacements(); refreshMeasurements(); refreshReconstructionReview(); updateCreateReady(); updateSuggestionReady(); draw(); }

function drawPolygon(points, stroke, fill, width = 3, label = "") {
  if (!points || points.length < 2) return;
  const pixels = points.map(metresToPixel); if (pixels.some(p => !p)) return;
  ctx.beginPath(); ctx.moveTo(...pixels[0]); pixels.slice(1).forEach(point => ctx.lineTo(...point)); ctx.closePath();
  ctx.lineWidth = width * canvas.width / Math.max(500, canvas.getBoundingClientRect().width);
  ctx.strokeStyle = stroke; ctx.fillStyle = fill; ctx.fill(); ctx.stroke();
  if (label) {
    const [x, y] = centroid(pixels); const size = Math.max(13, Math.min(25, canvas.width / 110));
    ctx.font = `700 ${size}px ui-sans-serif, sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.lineWidth = 4; ctx.strokeStyle = "#ffffffd9"; ctx.strokeText(label, x, y); ctx.fillStyle = "#174e7c"; ctx.fillText(label, x, y);
  }
}
function draw() {
  if (!state.image || !state.plan) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (state.plan.dimension_model) {
    ctx.fillStyle='#f9fbf8';ctx.fillRect(0,0,canvas.width,canvas.height);
    const cal=calibration();ctx.strokeStyle='#dbe5dc';ctx.lineWidth=1;
    for(let x=cal.origin[0]%cal.scale;x<canvas.width;x+=cal.scale){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,canvas.height);ctx.stroke();}
    for(let y=cal.origin[1]%cal.scale;y<canvas.height;y+=cal.scale){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(canvas.width,y);ctx.stroke();}
    ctx.fillStyle='#284b35';ctx.font='24px sans-serif';ctx.textAlign='left';ctx.fillText('1 grid square = 1 m × 1 m',35,40);
  } else ctx.drawImage(state.image, 0, 0);
  state.suggestions.forEach((suggestion, index) => {
    if (!suggestion.selected) return;
    const pixels = suggestion.pixel_polygon;
    ctx.beginPath(); ctx.moveTo(...pixels[0]); pixels.slice(1).forEach(p => ctx.lineTo(...p)); ctx.closePath();
    ctx.fillStyle = '#f4b64c25'; ctx.strokeStyle = '#ba6a0b'; ctx.lineWidth = Math.max(2, canvas.width / 500); ctx.setLineDash([8, 5]); ctx.fill(); ctx.stroke(); ctx.setLineDash([]);
    const [x, y] = centroid(pixels); ctx.font = `${Math.max(14, canvas.width / 65)}px sans-serif`; ctx.textAlign = 'center'; ctx.fillStyle = '#713f08'; ctx.fillText(`Proposed room ${index + 1}`, x, y);
  });
  const footprint = state.plan.footprint?.polygon || [];
  if (footprint.length >= 3) drawPolygon(footprint, "#1caa86", "#41b89917", 5);
  (state.plan.rooms || []).forEach(room => drawPolygon(room.polygon, "#407daf", "#75b7e224", 2, $("showLabels").checked ? room.name || "Room" : ""));
  (state.plan.balconies || []).forEach(balcony => drawPolygon(balcony.polygon, "#50a69a", "#9be1d127", 2, $("showLabels").checked ? balcony.name || "Balcony" : ""));
  (state.plan.wall_segments || []).forEach(wall => {
    const a = metresToPixel(wall.start), b = metresToPixel(wall.end); if (!a || !b) return;
    ctx.beginPath(); ctx.moveTo(...a); ctx.lineTo(...b); ctx.lineWidth = Math.max(2, canvas.width / 650); ctx.strokeStyle = wall.kind?.includes("guard") ? "#d19b52" : "#4c6578"; ctx.stroke();
  });
  (state.plan.openings || []).forEach(opening => {
    const point = metresToPixel(opening.center || opening.start); if (!point) return;
    ctx.beginPath(); ctx.arc(point[0], point[1], Math.max(5, canvas.width / 225), 0, Math.PI * 2); ctx.fillStyle = opening.type === "window" ? "#60adce" : "#f2a765"; ctx.fill(); ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.stroke();
    if (state.reviewOpening === opening.id) {
      ctx.beginPath(); ctx.arc(point[0], point[1], Math.max(12, canvas.width / 100), 0, Math.PI * 2);
      ctx.strokeStyle = "#206aaf"; ctx.lineWidth = Math.max(3, canvas.width / 450); ctx.stroke();
    }
  });
  allPlacements().forEach(placement => {
    const point = metresToPixel(placement.position); if (!point) return;
    ctx.beginPath(); ctx.arc(point[0], point[1], Math.max(8, canvas.width / 170), 0, Math.PI * 2);
    ctx.fillStyle = "#8869c4"; ctx.fill(); ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.stroke();
  });
  if (state.points.length) {
    ctx.beginPath(); ctx.moveTo(...state.points[0]); state.points.slice(1).forEach(point => ctx.lineTo(...point));
    if (state.hover) ctx.lineTo(...state.hover);
    ctx.strokeStyle = "#d37136"; ctx.lineWidth = Math.max(3, canvas.width / 550); ctx.setLineDash([10, 7]); ctx.stroke(); ctx.setLineDash([]);
    state.points.forEach(point => { ctx.beginPath(); ctx.arc(point[0], point[1], 5, 0, 2 * Math.PI); ctx.fillStyle = "#d37136"; ctx.fill(); });
  }
  if (state.dragStart && state.hover && state.tool === "room-rectangle") {
    ctx.strokeStyle = "#d37136"; ctx.lineWidth = Math.max(3, canvas.width / 550); ctx.strokeRect(state.dragStart[0], state.dragStart[1], state.hover[0] - state.dragStart[0], state.hover[1] - state.dragStart[1]);
  }
}
function createRoom(polygon, category = "room", suggestedName = null) {
  const name = (suggestedName === null ? $("roomName").value.trim() : suggestedName.trim()) || (category === "balcony" ? "Balcony" : `Room ${state.plan.rooms.length + 1}`);
  const room = { id: `space_${Date.now()}_${state.plan.rooms.length}`, name, category, polygon, confidence: "user-reviewed", geometry_provenance: suggestedName === null ? "traced in Blueprint Studio" : "image suggestion accepted by user; scaled using the confirmed distance" };
  state.plan.rooms.push(room);
  if (suggestedName !== null) {
    state.plan.reconstruction_decisions ||= [];
    state.plan.reconstruction_decisions.push({id:`outline_${room.id}`, kind:'image-suggestion',
      summary:'An image-detected outline was accepted by the user and scaled using one confirmed distance; room labels and printed dimensions were not automatically read.',
      source:state.plan.source, parameters:{room_id:room.id, polygon_m:polygon, calibration:state.plan.calibration}, status:'user-reviewed outline; dimensions need review'});
  }
  $("roomName").value = ""; markChanged(); toast(`${name} added`);
}
function finishOutline() {
  if (state.points.length < 3) { toast("Mark at least three corners"); return; }
  try {
    const polygon = state.points.map(pixelToMetres);
    if (polygonArea(polygon) < 0.1) throw new Error("The outline is too small");
    if (state.tool === "perimeter") { state.plan.footprint = { polygon, confidence: "user-reviewed", geometry_provenance: "traced in Blueprint Studio" }; markChanged(); toast("Outer edge saved"); }
    else createRoom(polygon, state.tool === "balcony" ? "balcony" : "room");
    state.points = []; state.hover = null; draw();
  } catch (error) { toast(error.message); }
}
function inferredWalls() {
  if (state.plan.wall_segments?.length) return state.plan.wall_segments;
  const seen = new Set(), walls = [];
  const shapes = [];
  if (state.plan.footprint?.polygon?.length) shapes.push(state.plan.footprint.polygon);
  (state.plan.rooms || []).forEach(room => shapes.push(room.polygon));
  shapes.forEach(polygon => polygon.forEach((start, i) => {
    const end = polygon[(i + 1) % polygon.length];
    const key = [start, end].map(p => p.map(v => Number(v).toFixed(3)).join(",")).sort().join("|");
    if (seen.has(key)) return; seen.add(key);
    walls.push({ id: `wall_${walls.length + 1}`, start, end });
  }));
  return walls;
}
function nearestWall(metres) {
  let best = null, bestDistance = Infinity;
  inferredWalls().forEach(wall => {
    const a = wall.start, b = wall.end, dx = b[0] - a[0], dy = b[1] - a[1], length2 = dx * dx + dy * dy;
    if (!length2) return;
    const t = Math.max(0, Math.min(1, ((metres[0] - a[0]) * dx + (metres[1] - a[1]) * dy) / length2));
    const distanceTo = Math.hypot(metres[0] - a[0] - t * dx, metres[1] - a[1] - t * dy);
    if (distanceTo < bestDistance) { bestDistance = distanceTo; best = { wall, center: [a[0] + t * dx, a[1] + t * dy] }; }
  });
  return bestDistance < 1.2 ? best : null;
}
function handleCanvasDown(event) {
  const point = getPixel(event);
  if (state.tool === 'move-placement' && state.movingPlacement) {
    const [x, y] = pixelToMetres(point), placement = state.movingPlacement;
    editPlacement(placement, {position: [x, y, placement.position?.[2] || 0]});
    state.movingPlacement = null; setTool(null); markChanged(); return;
  }
  if (!state.tool) {
    const radius = 15 * canvas.width / canvas.getBoundingClientRect().width;
    const placement = allPlacements().reverse().find(item => { const p = metresToPixel(item.position); return p && distance(point, p) < radius; });
    if (placement) { event.preventDefault(); state.draggingPlacement = placement; state.dragOriginal = [...placement.position]; canvas.setPointerCapture(event.pointerId); }
    return;
  }
  if (state.tool === "room-rectangle") { state.dragStart = point; canvas.setPointerCapture(event.pointerId); draw(); return; }
  if (state.tool === "calibrate") {
    state.points.push(point);
    if (state.points.length === 2) {
      const printed = Number($("distanceInput").value);
      if (!(printed > 0)) { toast("Enter the printed measurement first"); state.points = []; return; }
      const px = distance(...state.points);
      if (px < 10) { toast("Choose points farther apart"); state.points = []; return; }
      state.plan.calibration = { pixel_origin: [0, canvas.height], pixels_per_meter: +(px / printed).toFixed(5), reference_dimensions: [{ distance_m: printed, pixel_points: state.points }] };
      markChanged(); setTool(null); toast("Measurement saved. You can now use the suggested room outlines.");
    } else draw();
    return;
  }
  if (["room-polygon", "perimeter", "balcony"].includes(state.tool)) {
    if (state.points.length >= 3 && distance(point, state.points[0]) < Math.max(14, canvas.width / 150)) { finishOutline(); return; }
    state.points.push(point); draw(); return;
  }
  try {
    const metres = pixelToMetres(point);
    if (state.tool === "door" || state.tool === "window") {
      const near = nearestWall(metres);
      if (!near) throw new Error("Click closer to a wall line");
      const width = Number($("openingWidth").value);
      state.plan.openings.push({ id: `opening_${Date.now()}`, type: state.tool, wall_id: near.wall.id, center: near.center, width_m: width, confidence: "user-reviewed" });
      markChanged(); toast(`${state.tool === "door" ? "Door" : "Window"} added`);
    } else if (state.tool === "asset") {
      if (!state.selectedAsset) throw new Error("Choose a furnishing first");
      state.plan.asset_placements ||= [];
      state.plan.asset_placements.push({ id: `asset_${Date.now()}`, name: state.selectedAsset.name, asset_kind: state.selectedAsset.asset_kind || 'NVIDIA SimReady USD', asset_path: state.selectedAsset.usd_path, position: [...metres, 0], rotation_deg: 0 });
      markChanged(); toast(`${state.selectedAsset.name} placed`);
    }
  } catch (error) { toast(error.message); }
}
function handleCanvasMove(event) {
  if (state.draggingPlacement) {
    const [x, y] = pixelToMetres(getPixel(event)), placement = state.draggingPlacement;
    editPlacement(placement, {position:[x, y, state.dragOriginal[2] || 0]}); draw(); return;
  }
  if (!state.tool) return;
  state.hover = getPixel(event); draw();
}
function handleCanvasUp(event) {
  if (state.draggingPlacement) { state.draggingPlacement = null; markChanged(); return; }
  if (state.tool !== "room-rectangle" || !state.dragStart) return;
  const end = getPixel(event), start = state.dragStart; state.dragStart = null; state.hover = null;
  if (distance(start, end) < 12) { toast("Drag across the room to outline it"); return; }
  try {
    const a = pixelToMetres(start), b = pixelToMetres(end);
    createRoom([[Math.min(a[0], b[0]), Math.min(a[1], b[1])], [Math.max(a[0], b[0]), Math.min(a[1], b[1])], [Math.max(a[0], b[0]), Math.max(a[1], b[1])], [Math.min(a[0], b[0]), Math.max(a[1], b[1])]]);
  } catch (error) { toast(error.message); }
}
function availableStyles() {
  const category = state.plan?.structure_type || "home";
  const isReferencePlan = state.plan?.source?.primary_crop === 'agreement_unit_crop.jpg';
  return state.styles.filter(style => (category === "other" || style.category === category) && (!(style.requires_reference || style.id === 'home_specification') || isReferencePlan));
}
function renderStyles() {
  const styles = availableStyles();
  if (!styles.some(style => style.id === state.style)) state.style = styles[0]?.id || "contemporary";
  const schemes = styles.filter(style => style.is_design_scheme);
  $('styleChoices').setAttribute('aria-label', schemes.length ? 'Interior scheme or finish preset' : 'Finish preset');
  $('interiorSchemes').hidden = !schemes.length;
  $('finishPresets').hidden = !styles.some(style => !style.is_design_scheme);
  $('designOptionsTitle').textContent = schemes.length ? 'Choose an interior scheme for this layout.' : 'Choose finishes for this layout.';
  $('finishPresetNote').textContent = schemes.length
    ? (state.plan?.source?.primary_crop === 'agreement_unit_crop.jpg' ? 'Room dimensions follow the agreement. Furniture placement, colours and lighting are design proposals.' : 'Schemes use your reviewed room outlines and physical dimensions. Proposed decor is omitted where it cannot fit; every inferred placement is recorded.')
    : state.plan?.reference_manifest ? 'The B1-1502 specified finishes follow the agreement. Other presets are illustrative materials and lighting.' : 'Presets change surface materials and lighting. Your reviewed room dimensions stay in metres.';
  $('allStylesButton').textContent = schemes.length ? 'Export all options' : 'Export all finishes';
  $('schemeChoices').replaceChildren(); $('finishChoices').replaceChildren();
  styles.forEach(style => {
    const button = document.createElement("button"); button.type = "button"; button.className = `style-choice${state.style === style.id ? " selected" : ""}`;
    button.setAttribute("role", "radio"); button.setAttribute("aria-checked", String(state.style === style.id));
    button.setAttribute('aria-label', style.label); button.tabIndex = state.style === style.id ? 0 : -1; button.dataset.styleId = style.id;
    const name = document.createElement("strong"); name.textContent = style.label;
    const detail = document.createElement("small"); detail.textContent = style.description || "";
    if (style.is_design_scheme) {
      const card = document.createElement('article'); card.className = `scheme-card${state.style === style.id ? ' selected' : ''}`;
      button.classList.add('scheme-choice');
      const preview = document.createElement('span'); preview.className = 'scheme-preview';
      const pending = document.createElement('span'); pending.className = 'scheme-preview-pending'; pending.textContent = 'Preview appears when the 3D view is opened'; preview.append(pending);
      if (style.preview_url) {
        const image = document.createElement('img'); image.src = style.preview_url; image.alt = `${style.label} rendered from this layout`; image.loading = 'lazy';
        const caption = document.createElement('span'); caption.className = 'scheme-preview-caption'; caption.textContent = 'Rendered from this layout';
        image.onload = () => { pending.hidden = true; caption.hidden = false; };
        image.onerror = () => { image.remove(); caption.remove(); pending.hidden = false; };
        caption.hidden = true; preview.append(image, caption);
      }
      button.append(preview, name, detail); card.append(button);
      if (style.design_features?.length) {
        const features = document.createElement('ul'); features.className = 'scheme-features'; features.id = `scheme-features-${style.id}`;
        style.design_features.forEach(feature => { const item = document.createElement('li'); item.textContent = feature; features.append(item); });
        button.setAttribute('aria-describedby', features.id); card.append(features);
      }
      const references = document.createElement('div'); references.className = 'scheme-references';
      (style.reference_urls || []).forEach((value, index) => {
        let url; try { url = new URL(value); } catch { return; }
        if (!['https:', 'http:'].includes(url.protocol)) return;
        const link = document.createElement('a'); link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = `Design reference ${index + 1} ↗`; references.append(link);
      });
      if (references.childElementCount) card.append(references);
      $('schemeChoices').append(card);
    } else {
      const preview = document.createElement('span'); preview.className = 'style-preview'; preview.setAttribute('aria-hidden', 'true');
      const wall = document.createElement('span'); wall.style.background = hex(style.wall_color);
      const floor = document.createElement('span'); floor.style.background = hex(style.floor_color);
      preview.append(wall, floor); button.append(preview, name, detail); $('finishChoices').append(button);
    }
    button.onclick = () => {
      if (state.style === style.id) return;
      const restoreFocus = document.activeElement === button;
      state.style = style.id; state.revision++; invalidateGenerated(); renderStyles(); refreshPlacements(); draw();
      if (restoreFocus) [...$('styleChoices').querySelectorAll('[role="radio"]')].find(radio => radio.dataset.styleId === style.id)?.focus({ preventScroll: true });
    };
    button.onkeydown = event => {
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const radios = [...$('styleChoices').querySelectorAll('[role="radio"]')]; const index = radios.indexOf(button);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? radios.length - 1 : (index + (['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : -1) + radios.length) % radios.length;
      const id = radios[next].dataset.styleId; radios[next].click();
      [...$('styleChoices').querySelectorAll('[role="radio"]')].find(radio => radio.dataset.styleId === id)?.focus({ preventScroll: true });
    };
  });
}
async function generate(all = false) {
  if (!state.project) return;
  const projectId = state.project;
  const revision = state.revision;
  const selectedStyle = state.style;
  try {
    await savePlan();
    if (state.project !== projectId || state.revision !== revision) throw new Error("The plan changed. Create the scene again when edits are saved.");
    $("generateStatus").textContent = all ? "Creating all design and finish files…" : "Creating a measured USD scene…";
    $("generateButton").disabled = true; $("allStylesButton").disabled = true;
    const result = await request(`/api/projects/${projectId}/generate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ style: all ? "all" : selectedStyle }) });
    if (state.project !== projectId || state.revision !== revision) throw new Error("The plan changed while the scene was building. Create it again to include your edits.");
    state.generated = { result, style: selectedStyle };
    if (all) { state.editableObjects ||= {}; Object.entries(result.styles || {}).forEach(([id, report]) => { state.editableObjects[id] = report.editable_objects || []; }); refreshPlacements(); draw(); }
    if (!all) { state.editableObjects ||= {}; state.editableObjects[selectedStyle] = result.editable_objects || []; refreshPlacements(); draw(); }
    if (result.runtime_trace) renderLibraryTrace(result.runtime_trace);
    refreshReconstructionReview();
    $("resultPanel").hidden = false;
    $("streamPanel").hidden = true;
    $("streamPhysics").checked = (state.plan.asset_placements || []).some(item => item.physics_mode === "dynamic");
    $("resultDetails").textContent = all ? `${Object.keys(result.styles || {}).length} styles share this measured plan. Download the complete style pack.` : `${result.room_count} rooms · ${result.wall_count} wall runs · ${result.height_m.toFixed(2)} m wall height (${result.height_status}).`;
    $("downloadLink").href = result.download_url;
    $("downloadLink").textContent = all ? "Download style pack" : "Download USD";
    $("generateStatus").textContent = "Ready";
    toast("3D scene created");
  } catch (error) { $("generateStatus").textContent = error.message.includes("changed") ? error.message : ""; toast(error.message); }
  finally { updateCreateReady(); }
}
async function startStream() {
  if (!state.generated) return;
  const projectId = state.project, revision = state.revision;
  clearInterval(startStream.poller); startStream.poller = null;
  const link = $("streamLink");
  link.hidden = true; link.removeAttribute("href");
  $("streamPanel").hidden = false;
  const message = $("streamPanel").querySelector("p");
  message.textContent = "Starting RTX rendering. The first shader build can take a few minutes.";
  try {
    $("streamButton").disabled = true; $("streamButton").textContent = "Starting RTX view…";
    const status = await request(`/api/projects/${state.project}/stream`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ style: state.generated.style, quality: $("streamQuality").value, physics: $("streamPhysics").checked }) });
    const url = status.client_url || `http://${location.hostname}:8088/?signal_port=49100`;
    toast("RTX stream starting. You can keep working while it initializes.");
    const update = progress => {
      if (progress.phase === "ready" || progress.phase === "running" || progress.phase === "client_connected") {
        link.href = url; link.textContent = url; link.hidden = false;
        message.textContent = "Open the address on this laptop or another machine on the same network. The view connects automatically. Drag to rotate and scroll to zoom.";
        clearInterval(startStream.poller);
        request(`/api/projects/${projectId}`).then(data => {
          if (state.project !== projectId || state.revision !== revision) return;
          state.styles = data.styles || []; renderStyles();
        }).catch(() => {});
        return true;
      } else if (progress.phase === "error" || (!progress.running && progress.phase !== "loading")) {
        message.textContent = "The RTX stream stopped. Check the runtime setup or try again.";
        clearInterval(startStream.poller);
        return true;
      }
      return false;
    };
    if (!update(status)) {
      const poller = setInterval(async () => {
        try {
          const progress = await request("/api/stream/status");
          if (startStream.poller === poller) update(progress);
        } catch (error) {
          if (startStream.poller === poller) { message.textContent = error.message; clearInterval(poller); }
        }
      }, 3000);
      startStream.poller = poller;
    }
  } catch (error) { message.textContent = error.message; toast(error.message); }
  finally { $("streamButton").disabled = false; $("streamButton").innerHTML = 'Explore live on another screen <span>↗</span>'; }
}
function renderAssets() {
  const list = $("assetList"); list.replaceChildren();
  const category = state.plan?.structure_type || "home";
  const entries = state.assets.filter(asset => (asset.structure_types || ["home", "office", "showroom", "other"]).includes(category));
  $("starterFurniture").hidden = state.plan?.example !== "B1-1502" || !entries.length;
  if (!entries.length) { list.textContent = "No SimReady objects are installed for this space yet."; return; }
  entries.forEach(asset => {
    const button = document.createElement("button"); button.type = "button";
    const name = document.createElement("span"); name.textContent = asset.name;
    const size = document.createElement("small"); size.textContent = Array.isArray(asset.size_xyz_m) ? `Physical size: ${asset.size_xyz_m.map(n => Number(n).toFixed(2)).join(" × ")} m (X × Y × Z)` : asset.category || "SimReady";
    button.append(name, size);
    button.onclick = () => { state.selectedAsset = asset; if (state.tool !== "asset") setTool("asset"); document.querySelectorAll("#assetList button").forEach(item => item.classList.remove("active")); button.classList.add("active"); toast(`Click the plan to place ${asset.name}`); };
    list.append(button);
  });
}
async function loadAssets() {
  try {
    const data = await request("/api/assets");
    const entries = data.assets || data.entries || [];
    state.assets = entries;
    renderAssets();
  } catch { $("assetList").textContent = "SimReady library unavailable."; }
}

$("fileInput").addEventListener("change", async event => {
  const file = event.target.files?.[0]; if (!file) return;
  const form = new FormData(); form.append("file", file);
  try { $("connection").lastChild.textContent = " Uploading…"; await setProject(await request("/api/projects/upload", { method: "POST", body: form })); toast("Drawing uploaded"); }
  catch (error) { toast(error.message); }
  finally { $("connection").lastChild.textContent = " Studio connected"; event.target.value = ""; }
});
async function loadExample() { try { await setProject(await request("/api/examples/b1-1502", { method: "POST" })); toast("B1-1502 is ready to explore"); } catch (error) { toast(error.message); } }
$("exampleButton").onclick = loadExample; $("emptyExample").onclick = loadExample;
$("calibrateButton").onclick = () => setTool("calibrate");
$("clearTool").onclick = () => setTool(null);
$("finishOutline").onclick = finishOutline;
document.querySelectorAll(".tool").forEach(button => button.onclick = () => { if (!calibration()) { toast("Set the scale first"); return; } setTool(button.dataset.tool); });
canvas.addEventListener("pointerdown", handleCanvasDown);
canvas.addEventListener("pointermove", handleCanvasMove);
canvas.addEventListener("pointerup", handleCanvasUp);
canvas.addEventListener('pointercancel', () => { if (state.draggingPlacement) { editPlacement(state.draggingPlacement, {position:state.dragOriginal}); state.draggingPlacement = null; draw(); } });
canvas.addEventListener("dblclick", event => { event.preventDefault(); if (["room-polygon", "perimeter", "balcony"].includes(state.tool)) finishOutline(); });
$("structureType").onchange = event => { if (!state.plan) return; state.plan.structure_type = event.target.value; state.selectedAsset = null; renderStyles(); renderAssets(); markChanged(); };
$("heightInput").onchange = event => {
  if (!state.plan) return;
  const height = Number(event.target.value); if (!(height >= 1.5 && height <= 15)) { toast("Wall height must be between 1.5 and 15 metres"); return; }
  state.plan.room_height_m = height; state.plan.height_status = "confirmed by user in Blueprint Studio";
  (state.plan.wall_segments || []).forEach(wall => { if (!String(wall.kind).includes("guard") && !String(wall.kind).includes("rail")) wall.height_m = height; });
  $("heightStatus").textContent = "Wall height confirmed by you."; markChanged();
};
$("pageSelect").onchange = async event => {
  if (!state.project) return;
  const hasWork = state.plan.rooms?.length || state.plan.footprint?.polygon?.length || state.plan.openings?.length || state.plan.asset_placements?.length;
  if (hasWork && !confirm("Changing pages clears the outlines, openings, and objects on this page. Continue?")) { event.target.value = state.plan.page; return; }
  try { await setProject(await request(`/api/projects/${state.project}/page`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ page: Number(event.target.value) }) })); }
  catch (error) { toast(error.message); }
};
function updateSuggestionReady() {
  $('acceptSuggestions').hidden = !state.suggestions.length;
  $('acceptSuggestions').disabled = !calibration() || !state.suggestions.some(item => item.selected);
  if (state.suggestions.length) $('suggestionStatus').textContent = calibration()
    ? 'Review the dashed outlines. Uncheck mistakes, then use the selected rooms. Names can be changed later.'
    : 'Proposed rooms are shown with dashed outlines. Confirm one printed measurement to set their size before using them.';
}
async function findRoomSuggestions() {
  if (!state.project || state.suggesting) return;
  const project = state.project, plan = state.plan;
  state.suggesting = true;
  $('suggestButton').disabled = true; $('suggestButton').textContent = 'Looking for rooms…';
  try {
    const data = await request(`/api/projects/${project}/suggest`);
    if (state.project !== project || state.plan !== plan) return;
    state.suggestions = (data.suggestions || []).slice(0, 25).map(item => ({...item, selected: true, reviewName: ''}));
    const container = $('suggestions'); container.replaceChildren(); container.hidden = !state.suggestions.length;
    state.suggestions.forEach((suggestion, index) => {
      const row = document.createElement('div'); row.className = 'suggestion';
      const check = document.createElement('input'); check.type = 'checkbox'; check.checked = true;
      check.setAttribute('aria-label', `Use proposed room ${index + 1}`);
      check.onchange = () => { suggestion.selected = check.checked; updateSuggestionReady(); draw(); };
      const name = document.createElement('input'); name.type = 'text'; name.placeholder = `Room ${index + 1} (optional name)`;
      name.setAttribute('aria-label', `Name for proposed room ${index + 1}`);
      name.oninput = () => { suggestion.reviewName = name.value; };
      row.append(check, name); container.append(row);
    });
    if (!state.suggestions.length) $('suggestionStatus').textContent = 'No clear enclosed rooms were found in this image. Try a cleaner plan or use the manual outline tools below.';
    updateSuggestionReady(); draw();
  } catch (error) { if (state.project === project && state.plan === plan) $('suggestionStatus').textContent = `Room detection could not finish: ${error.message}. You can still use the manual outline tools.`; }
  finally { if (state.project === project && state.plan === plan) { state.suggesting = false; $('suggestButton').disabled = false; $('suggestButton').textContent = 'Find room outlines again'; } }
}
$('suggestButton').onclick = findRoomSuggestions;
$('acceptSuggestions').onclick = () => {
  if (!calibration()) return;
  const selected = state.suggestions.filter(item => item.selected);
  const before = state.plan.rooms.length;
  // Review converts pixel outlines to metric rooms; it does not read printed dimensions.
  for (const suggestion of selected) {
    const polygon = suggestion.pixel_polygon.map(pixelToMetres);
    if (polygonArea(polygon) < .1) continue;
    const center = centroid(polygon);
    if (state.plan.rooms.some(room => distance(centroid(room.polygon), center) < .01 && Math.abs(polygonArea(room.polygon) - polygonArea(polygon)) < .01)) continue;
    createRoom(polygon, 'room', suggestion.reviewName);
  }
  state.suggestions = []; $('suggestions').replaceChildren(); $('suggestions').hidden = true;
  $('suggestionStatus').textContent = state.plan.rooms.length > before ? 'Room outlines accepted. Names are optional; review doors and any missed boundaries before refining the model.' : 'No rooms added: these outlines are already included or too small. Review the selected outlines and measurement.';
  updateSuggestionReady(); draw();
};
$("generateButton").onclick = () => generate(false);
$("allStylesButton").onclick = () => generate(true);
$("starterFurniture").onclick = async () => {
  if (!state.project) return;
  try {
    const project = await request(`/api/projects/${state.project}/starter-furniture`, { method: "POST" });
    state.plan = project.plan; state.styles = project.styles || []; state.revision++; invalidateGenerated(); refreshAll(); toast(`${state.plan.asset_placements.length} SimReady furnishings in this layout`);
  } catch (error) { toast(error.message); }
};
$("showLabels").onchange = draw;
$("streamButton").onclick = startStream;
$("stopStreamButton").onclick = async () => { try { await request("/api/stream/stop", { method: "POST" }); clearInterval(startStream.poller); $("streamPanel").hidden = true; toast("Stream stopped"); } catch (error) { toast(error.message); } };
const uploadTarget = document.querySelector(".upload-target");
for (const name of ["dragenter", "dragover"]) uploadTarget.addEventListener(name, event => { event.preventDefault(); uploadTarget.classList.add("dragging"); });
for (const name of ["dragleave", "drop"]) uploadTarget.addEventListener(name, event => { event.preventDefault(); uploadTarget.classList.remove("dragging"); });
uploadTarget.addEventListener("drop", async event => { const file = event.dataTransfer?.files?.[0]; if (!file) return; const form = new FormData(); form.append("file", file); try { await setProject(await request("/api/projects/upload", { method: "POST", body: form })); toast("Drawing uploaded"); } catch (error) { toast(error.message); } });
loadAssets();
async function loadSupportingSources() {
  const project = state.project; if (!project) return;
  try {
    const result = await request(`/api/projects/${project}/sources`);
    if (state.project !== project) return;
    $('sourceFilesList').replaceChildren();
    for (const source of result.sources || []) {
      const row = document.createElement('p'), link = document.createElement('a');
      link.href = source.download_url; link.textContent = `${source.original_name} · ${source.role}`; link.target = '_blank'; link.rel = 'noopener';
      row.append(link); if (source.notes) row.append(document.createElement('br'), document.createTextNode(source.notes));
      $('sourceFilesList').append(row);
    }
    $('sourceUploadStatus').textContent = `${result.sources.length} supporting sources · retained for review`;
  } catch (error) { $('sourceUploadStatus').textContent = error.message; }
}
$('sourceFilesInput').onchange = async event => {
  const project = state.project; if (!project) return;
  try {
    for (const file of event.target.files || []) {
      const form = new FormData(); form.append('file', file); form.append('role', $('sourceRole').value); form.append('notes', $('sourceNotes').value);
      $('sourceUploadStatus').textContent = `Attaching ${file.name}…`;
      await request(`/api/projects/${project}/sources`, {method:'POST', body:form});
    }
    await loadSupportingSources();
    if (state.project === project) { state.styles.forEach(style => { style.preview_url = null; }); invalidateGenerated(); renderStyles(); }
  } catch (error) { $('sourceUploadStatus').textContent = error.message; toast(error.message); }
  finally { event.target.value = ''; }
};
function renderLibraryTrace(trace) {
  if (state.traceUrl) URL.revokeObjectURL(state.traceUrl);
  state.traceUrl = URL.createObjectURL(new Blob([JSON.stringify(trace, null, 2)], {type:'application/json'}));
  $('downloadLibraryTrace').href = state.traceUrl;
  const container = $('libraryTraceContent'); container.replaceChildren();
  const note = document.createElement('p'); note.textContent = trace.note; container.append(note);
  const versions = new Map((trace.libraries || []).map(lib => [lib.id, `${lib.name} ${lib.version || (lib.installed === false ? '(not installed)' : '(version unknown)')}`]));
  for (const action of trace.actions || []) {
    const row = document.createElement('p');
    const title = document.createElement('strong'); title.textContent = `${action.label} · ${action.status} (${action.observed_calls || 0} observed)`;
    const libraries = document.createElement('span'); libraries.textContent = action.libraries.map(id => versions.get(id) || id).join(' · ');
    const api = document.createElement('code'); api.textContent = action.apis.join(', ');
    row.append(title, document.createElement('br'), libraries, document.createElement('br'), api); container.append(row);
  }
}
async function loadLibraryTrace() { try { renderLibraryTrace(await request('/api/runtime-trace')); } catch (error) { $('libraryTraceContent').textContent = error.message; } }
$('refreshLibraryTrace').onclick = loadLibraryTrace;
loadLibraryTrace();
$('assetImportInput').onchange = async event => {
  const file = event.target.files?.[0]; if (!file) return;
  const form = new FormData(); form.append('file', file);
  $('assetImportStatus').textContent = 'Checking units, geometry and packaged dependencies…';
  try {
    const asset = await request('/api/assets/import', {method:'POST', body:form});
    if (asset.runtime_trace) renderLibraryTrace(asset.runtime_trace);
    await loadAssets(); state.selectedAsset = asset; setTool('asset');
    $('assetImportStatus').textContent = `${asset.name} imported as USD. Click the plan to place it; SimReady status is not verified.`;
    $('canvasArea').scrollIntoView({block:'center'});
  } catch (error) { $('assetImportStatus').textContent = error.message; toast(error.message); }
  finally { event.target.value = ''; }
};
const query = new URLSearchParams(location.search);
const previousProject = query.get('project') || localStorage.getItem("blueprint-studio-project");
if (query.get("example") === "b1-1502") loadExample();
else if (previousProject) request(`/api/projects/${previousProject}`).then(setProject).catch(() => localStorage.removeItem("blueprint-studio-project"));
