const $ = (id) => document.getElementById(id);
const state = { project: null, plan: null, image: null, styles: [], style: "contemporary", revision: 0, tool: null, points: [], dragStart: null, hover: null, saveTimer: null, suggestions: [], selectedAsset: null, generated: null, assets: [] };
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
  state.generated = null; state.selectedAsset = null; state.revision = 0;
  $("generateStatus").textContent = "";
  localStorage.setItem("blueprint-studio-project", data.id);
  $("projectTitle").textContent = state.plan.name || "Untitled project";
  $("projectSubtitle").textContent = state.plan.example ? "Flat B1-1502 · 15th floor · approved architectural plan" : "Review your drawing, then build a measured 3D scene.";
  $("sourceNote").textContent = state.plan.source?.filename || (state.plan.example ? "Approved B1 building plan · unit 1502" : "Your drawing");
  if(state.plan.dimension_model) $("sourceNote").textContent='Dimensioned plan · 1 m grid · approved metric room dimensions';
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
    state.image = image; canvas.width = image.naturalWidth; canvas.height = image.naturalHeight;
    $("canvasArea").hidden = false; $("emptyState").hidden = true;
    $("calibrateButton").disabled = !!state.plan.dimension_model; $("suggestButton").disabled = !!state.plan.dimension_model;
    document.querySelectorAll(".tool").forEach(button => button.disabled = false);
    if (!state.plan.image_size) state.plan.image_size = [image.naturalWidth, image.naturalHeight];
    renderStyles(); refreshAll();
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
  setTool(null);
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
    const strong = document.createElement("strong"); strong.textContent = room.name || `Space ${index + 1}`;
    const small = document.createElement("small"); small.textContent = ` · ${dimensions(room)}`;
    label.append(strong, small);
    const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "Remove"; remove.setAttribute("aria-label", `Remove ${room.name || "space"}`);
    remove.onclick = () => { state.plan.rooms.splice(index, 1); markChanged(); };
    row.append(label, remove); list.append(row);
  });
}
function refreshPlacements() {
  const list = $("placementList"); list.replaceChildren();
  (state.plan?.asset_placements || []).forEach((placement, index) => {
    const row = document.createElement("div"); row.className = "room-row";
    const details = document.createElement("div"); details.className = "placement-details";
    const name = document.createElement("strong"); name.textContent = placement.name || placement.id || "Furnishing";
    const controls = document.createElement("div"); controls.className = "placement-controls";
    const movableLabel = document.createElement("label");
    const movable = document.createElement("input"); movable.type = "checkbox"; movable.checked = placement.physics_mode === "dynamic";
    movable.setAttribute("aria-label", `Move ${name.textContent} in simulation`);
    movable.onchange = () => { placement.physics_mode = movable.checked ? "dynamic" : "static"; if (!movable.checked) placement.position[2] = 0; markChanged(); };
    movableLabel.append(movable, " Movable in simulation"); controls.append(movableLabel);
    if (movable.checked) {
      const heightLabel = document.createElement("label"); heightLabel.textContent = "Start height ";
      const height = document.createElement("input"); height.type = "number"; height.min = "0"; height.max = "20"; height.step = "0.1"; height.value = Number(placement.position?.[2] || 0).toFixed(1); height.setAttribute("aria-label", `Starting height of ${name.textContent} in metres`);
      height.onchange = () => { const z = Number(height.value); if (!Number.isFinite(z) || z < 0 || z > 20) { toast("Starting height must be between 0 and 20 metres"); return; } placement.position[2] = z; markChanged(); };
      heightLabel.append(height, " m"); controls.append(heightLabel);
    }
    const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "Remove";
    remove.onclick = () => { state.plan.asset_placements.splice(index, 1); markChanged(); };
    details.append(name, controls); row.append(details, remove); list.append(row);
  });
}
function refreshMeasurements() {
  const cal = calibration();
  $("scaleSummary").textContent = state.plan?.dimension_model ? "Printed meter dimensions enforced. Each grid square is 1 m × 1 m." : cal ? `Scale set: ${cal.scale.toFixed(1)} image pixels = 1 metre.` : state.project ? "Use a dimension printed on the plan. Click its two endpoints." : "Upload a drawing to begin.";
  $("canvasScale").textContent = cal ? `1 m ≈ ${cal.scale.toFixed(1)} px` : "Scale not set";
  const badges = $("measurementBadges"); badges.replaceChildren();
  if (!state.plan) { $("drawingInfo").hidden = true; return; }
  const area = state.plan.area_schedule_m2;
  const values = area ? [`${Number(area.carpet).toFixed(2)} m² carpet`, `${Number(area.balcony).toFixed(2)} m² balcony`, `${Number(area.dry_balcony).toFixed(2)} m² dry balcony`, `${Number(area.total).toFixed(2)} m² scheduled total`] : [`${state.plan.rooms?.length || 0} spaces outlined`, cal ? "Measured in metres" : "Scale needs review"];
  values.forEach(value => { const badge = document.createElement("span"); badge.textContent = value; badges.append(badge); });
  $("provenanceText").textContent = area ? "B1-1502 areas come from the printed RERA schedule. Room spans follow the approved meter dimensions; wall thickness, heights and the detailed balcony curve remain assumptions." : "Room outlines come from your review. Confirm any unprinted dimension before using the model for construction or purchasing.";
  $("drawingInfo").hidden = false;
}
function updateCreateReady() {
  const measured = !!calibration();
  const outlined = state.plan?.footprint?.polygon?.length >= 3 || (state.plan?.rooms || []).some(room => room.polygon?.length >= 3);
  const ready = measured && outlined;
  $("generateButton").disabled = !ready; $("allStylesButton").disabled = !ready;
  if (!measured) $("generateStatus").textContent = "Mark one known distance to set the scale first.";
  else if (!outlined) $("generateStatus").textContent = "Outline the outer edge or at least one space to make a 3D scene.";
  else if (!state.generated && ["Mark one known distance", "Outline the outer edge"].some(text => $("generateStatus").textContent.startsWith(text))) $("generateStatus").textContent = "";
}
function refreshAll() { updateSteps(); refreshRooms(); refreshPlacements(); refreshMeasurements(); updateCreateReady(); draw(); }

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
  const footprint = state.plan.footprint?.polygon || [];
  if (footprint.length >= 3) drawPolygon(footprint, "#1caa86", "#41b89917", 5);
  (state.plan.rooms || []).forEach(room => drawPolygon(room.polygon, "#407daf", "#75b7e224", 2, $("showLabels").checked ? room.name || "Space" : ""));
  (state.plan.balconies || []).forEach(balcony => drawPolygon(balcony.polygon, "#50a69a", "#9be1d127", 2, $("showLabels").checked ? balcony.name || "Balcony" : ""));
  (state.plan.wall_segments || []).forEach(wall => {
    const a = metresToPixel(wall.start), b = metresToPixel(wall.end); if (!a || !b) return;
    ctx.beginPath(); ctx.moveTo(...a); ctx.lineTo(...b); ctx.lineWidth = Math.max(2, canvas.width / 650); ctx.strokeStyle = wall.kind?.includes("guard") ? "#d19b52" : "#4c6578"; ctx.stroke();
  });
  (state.plan.openings || []).forEach(opening => {
    const point = metresToPixel(opening.center || opening.start); if (!point) return;
    ctx.beginPath(); ctx.arc(point[0], point[1], Math.max(5, canvas.width / 225), 0, Math.PI * 2); ctx.fillStyle = opening.type === "window" ? "#60adce" : "#f2a765"; ctx.fill(); ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.stroke();
  });
  (state.plan.asset_placements || []).forEach(placement => {
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
function createRoom(polygon, category = "room") {
  const name = $("roomName").value.trim() || (category === "balcony" ? "Balcony" : `Room ${state.plan.rooms.length + 1}`);
  const room = { id: `space_${Date.now()}`, name, category, polygon, confidence: "user-reviewed", geometry_provenance: "traced in Blueprint Studio" };
  state.plan.rooms.push(room);
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
  if (!state.tool) return;
  const point = getPixel(event);
  if (state.tool === "room-rectangle") { state.dragStart = point; canvas.setPointerCapture(event.pointerId); draw(); return; }
  if (state.tool === "calibrate") {
    state.points.push(point);
    if (state.points.length === 2) {
      const printed = Number($("distanceInput").value);
      if (!(printed > 0)) { toast("Enter the printed measurement first"); state.points = []; return; }
      const px = distance(...state.points);
      if (px < 10) { toast("Choose points farther apart"); state.points = []; return; }
      state.plan.calibration = { pixel_origin: [0, canvas.height], pixels_per_meter: +(px / printed).toFixed(5), reference_dimensions: [{ distance_m: printed, pixel_points: state.points }] };
      markChanged(); setTool(null); toast("Scale saved. You can now outline spaces.");
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
      state.plan.asset_placements.push({ id: `asset_${Date.now()}`, name: state.selectedAsset.name, asset_path: state.selectedAsset.usd_path, position: [...metres, 0], rotation_deg: 0 });
      markChanged(); toast(`${state.selectedAsset.name} placed`);
    }
  } catch (error) { toast(error.message); }
}
function handleCanvasMove(event) {
  if (!state.tool) return;
  state.hover = getPixel(event); draw();
}
function handleCanvasUp(event) {
  if (state.tool !== "room-rectangle" || !state.dragStart) return;
  const end = getPixel(event), start = state.dragStart; state.dragStart = null; state.hover = null;
  if (distance(start, end) < 12) { toast("Drag across the room to outline it"); return; }
  try {
    const a = pixelToMetres(start), b = pixelToMetres(end);
    createRoom([[Math.min(a[0], b[0]), Math.min(a[1], b[1])], [Math.max(a[0], b[0]), Math.min(a[1], b[1])], [Math.max(a[0], b[0]), Math.max(a[1], b[1])], [Math.min(a[0], b[0]), Math.max(a[1], b[1])]]);
  } catch (error) { toast(error.message); }
}
function renderStyles() {
  const category = state.plan?.structure_type || "home";
  const styles = state.styles.filter(style => category === "other" || style.category === category);
  if (!styles.some(style => style.id === state.style)) state.style = styles[0]?.id || "contemporary";
  const container = $("styleChoices"); container.replaceChildren();
  styles.forEach(style => {
    const button = document.createElement("button"); button.type = "button"; button.className = `style-choice${state.style === style.id ? " selected" : ""}`;
    button.setAttribute("role", "radio"); button.setAttribute("aria-checked", String(state.style === style.id));
    const preview = document.createElement("div"); preview.className = "style-preview";
    const wall = document.createElement("span"); wall.style.background = hex(style.wall_color);
    const floor = document.createElement("span"); floor.style.background = hex(style.floor_color);
    preview.append(wall, floor);
    const name = document.createElement("strong"); name.textContent = style.label;
    const detail = document.createElement("small"); detail.textContent = style.description || "";
    button.append(preview, name, detail);
    button.onclick = () => { if (state.style !== style.id) { state.style = style.id; state.revision++; invalidateGenerated(); renderStyles(); } };
    container.append(button);
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
    $("generateStatus").textContent = all ? "Creating all style files…" : "Creating a measured USD scene…";
    $("generateButton").disabled = true; $("allStylesButton").disabled = true;
    const result = await request(`/api/projects/${projectId}/generate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ style: all ? "all" : selectedStyle }) });
    if (state.project !== projectId || state.revision !== revision) throw new Error("The plan changed while the scene was building. Create it again to include your edits.");
    state.generated = { result, style: selectedStyle };
    $("resultPanel").hidden = false;
    $("streamPanel").hidden = true;
    $("streamPhysics").checked = (state.plan.asset_placements || []).some(item => item.physics_mode === "dynamic");
    $("resultDetails").textContent = all ? `${Object.keys(result.styles || {}).length} styles share this measured plan. Download the complete style pack.` : `${result.room_count} spaces · ${result.wall_count} wall runs · ${result.height_m.toFixed(2)} m wall height (${result.height_status}).`;
    $("downloadLink").href = result.download_url;
    $("downloadLink").textContent = all ? "Download style pack" : "Download USD";
    $("generateStatus").textContent = "Ready";
    toast("3D scene created");
  } catch (error) { $("generateStatus").textContent = error.message.includes("changed") ? error.message : ""; toast(error.message); }
  finally { updateCreateReady(); }
}
async function startStream() {
  if (!state.generated) return;
  try {
    $("streamButton").disabled = true; $("streamButton").textContent = "Starting RTX view…";
    const status = await request(`/api/projects/${state.project}/stream`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ style: state.generated.style, quality: $("streamQuality").value, physics: $("streamPhysics").checked }) });
    const url = status.client_url || `http://${location.hostname}:8088/?signal_port=49100`;
    $("streamLink").href = url; $("streamLink").textContent = url;
    $("streamPanel").hidden = false;
    const message = $("streamPanel").querySelector("p");
    message.textContent = "Starting RTX rendering. The first shader build can take a few minutes.";
    toast("RTX stream starting. You can keep working while it initializes.");
    clearInterval(startStream.poller);
    startStream.poller = setInterval(async () => {
      try {
        const progress = await request("/api/stream/status");
        if (progress.phase === "ready" || progress.phase === "running" || progress.phase === "client_connected") {
          message.textContent = "Open the address on this laptop or another machine on the same network. The view connects automatically. Drag to rotate and scroll to zoom.";
          clearInterval(startStream.poller);
        } else if (progress.phase === "error" || (!progress.running && progress.phase !== "loading")) {
          message.textContent = "The RTX stream stopped. Check the runtime setup or try again.";
          clearInterval(startStream.poller);
        }
      } catch { clearInterval(startStream.poller); }
    }, 3000);
  } catch (error) { toast(error.message); }
  finally { $("streamButton").disabled = false; $("streamButton").innerHTML = 'Explore live on another screen <span>↗</span>'; }
}
function renderAssets() {
  const list = $("assetList"); list.replaceChildren();
  const category = state.plan?.structure_type || "home";
  const entries = state.assets.filter(asset => (asset.structure_types || ["home", "office", "showroom", "other"]).includes(category));
  $("starterFurniture").hidden = state.plan?.example !== "B1-1502" || !entries.length;
  if (!entries.length) { list.textContent = "No SimReady objects are installed for this space yet."; return; }
  entries.slice(0, 60).forEach(asset => {
    const button = document.createElement("button"); button.type = "button";
    const name = document.createElement("span"); name.textContent = asset.name;
    const size = document.createElement("small"); size.textContent = Array.isArray(asset.size_xyz_m) ? `${asset.size_xyz_m.map(n => Number(n).toFixed(2)).join("×")} m` : asset.category || "SimReady";
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
  finally { $("connection").lastChild.textContent = " Ready on this laptop"; event.target.value = ""; }
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
$("suggestButton").onclick = async () => {
  if (!calibration()) { toast("Set the scale before adding room suggestions"); return; }
  try {
    $("suggestButton").disabled = true; $("suggestButton").textContent = "Looking for rooms…";
    const data = await request(`/api/projects/${state.project}/suggest`);
    state.suggestions = data.suggestions || [];
    const container = $("suggestions"); container.replaceChildren(); container.hidden = !state.suggestions.length;
    state.suggestions.slice(0, 25).forEach((suggestion, index) => {
      const row = document.createElement("div"); row.className = "suggestion";
      const text = document.createElement("span"); text.textContent = `Possible space ${index + 1}`;
      const button = document.createElement("button"); button.type = "button"; button.textContent = "Add";
      button.onclick = () => { $("roomName").value = `Space ${state.plan.rooms.length + 1}`; createRoom(suggestion.pixel_polygon.map(pixelToMetres)); row.remove(); };
      row.append(text, button); container.append(row);
    });
    if (!state.suggestions.length) toast("No enclosed spaces found. You can outline them by hand.");
  } catch (error) { toast(error.message); }
  finally { $("suggestButton").disabled = false; $("suggestButton").textContent = "Find likely rooms in the image"; }
};
$("generateButton").onclick = () => generate(false);
$("allStylesButton").onclick = () => generate(true);
$("starterFurniture").onclick = async () => {
  if (!state.project) return;
  try {
    const project = await request(`/api/projects/${state.project}/starter-furniture`, { method: "POST" });
    state.plan = project.plan; state.revision++; invalidateGenerated(); refreshAll(); toast("Five SimReady furnishings added to the example");
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
const previousProject = localStorage.getItem("blueprint-studio-project");
if (new URLSearchParams(location.search).get("example") === "b1-1502") loadExample();
else if (previousProject) request(`/api/projects/${previousProject}`).then(setProject).catch(() => localStorage.removeItem("blueprint-studio-project"));
