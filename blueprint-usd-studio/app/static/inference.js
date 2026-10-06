// Keys live only in this page's password field and request headers.
(() => {
  const panel = $('inferencePanel');
  panel.innerHTML = `<details><summary>AI-assisted outlines · NVIDIA Inference Hub</summary>
    <p class="helper">Ask a vision model to propose rooms from the current blueprint image. Every proposal needs review; existing measurements and rooms remain unchanged until you accept an outline.</p>
    <p id="inferenceTransport" class="helper" role="status">Checking secure connection…</p>
    <fieldset id="inferenceFields" disabled>
      <label for="inferenceKey">Your Inference Hub key (this tab only)</label>
      <input id="inferenceKey" type="password" autocomplete="off" spellcheck="false">
      <button id="inferenceClear" type="button">Clear key</button>
      <button id="inferenceModels" type="button">List available models</button>
      <label for="inferenceModel">Vision-capable model ID</label>
      <input id="inferenceModel" type="text" list="inferenceModelList" placeholder="Choose a model that accepts images" autocomplete="off">
      <datalist id="inferenceModelList"></datalist>
      <p id="inferenceModelHelp" class="helper">Choose a model with documented image input support.</p>
      <label><input id="inferenceConsent" type="checkbox"> Send this project's current blueprint image to NVIDIA Inference Hub using my key. I have selected a model that accepts images.</label>
      <p class="helper">Supporting files are not sent in this version. Your key is never saved in the project and is cleared after an outline request.</p>
      <button id="inferenceRun" type="button">Propose AI room outlines</button>
    </fieldset>
    <p id="inferenceStatus" class="helper" role="status"></p>
    <button id="inferenceReview" type="button" hidden>Review AI proposals on the plan</button>
    <details id="inferenceTrace" hidden><summary>Inference evidence and assumptions</summary><pre id="inferenceEvidence"></pre></details>
  </details>`;
  let secure = false, busy = false, pending = null;
  const status = message => $('inferenceStatus').textContent = message;
  function setBusy(value) {
    busy = value;
    $('inferenceFields').disabled = !secure || busy;
    $('inferenceReview').disabled = busy;
  }
  function headers() {
    const key = $('inferenceKey').value.trim();
    if (!key) throw new Error('Enter your Inference Hub key in the key field.');
    return {'Content-Type': 'application/json', Authorization: `Bearer ${key}`};
  }
  $('inferenceClear').onclick = () => { $('inferenceKey').value = ''; status('Key cleared.'); };
  window.addEventListener('pagehide', () => { $('inferenceKey').value = ''; });
  $('inferenceModels').onclick = async () => {
    if (!secure || busy) return;
    try {
      const auth = headers(); setBusy(true); status('Loading available model IDs…');
      const data = await request('/api/inference/models', {method:'POST', headers:auth});
      const list = $('inferenceModelList'); list.replaceChildren();
      for (const id of data.models) { const option = document.createElement('option'); option.value = id; list.append(option); }
      const selected = $('inferenceModel').value.trim();
      status(data.models.includes(selected)
        ? `${data.models.length} model IDs loaded. Your selected model is available; selection retained.`
        : `${data.models.length} model IDs loaded. Your selected model was not listed for this key. Choose an available vision model; no automatic substitution is made.`);
    } catch (error) { status(error.message); }
    finally { setBusy(false); }
  };
  $('inferenceRun').onclick = async () => {
    if (!secure || busy) return;
    const project = state.project, plan = state.plan, revision = state.revision;
    let sent = false;
    try {
      if (!project) throw new Error('Upload a blueprint first.');
      if (plan.dimension_model) throw new Error('This worked example uses a fitted dimension model. Upload its drawing as a new project to review image-based AI outlines.');
      if (state.suggesting) throw new Error('Wait for local outline detection to finish.');
      if (!$('inferenceConsent').checked) throw new Error('Confirm image sharing and vision-model support first.');
      const model = $('inferenceModel').value.trim();
      if (!model) throw new Error('Choose a vision-capable model ID.');
      const auth = headers(); sent = true; setBusy(true); pending = null; $('inferenceReview').hidden = true;
      $('inferenceTrace').hidden = true; status(`Reading the blueprint with ${model}…`);
      const data = await request(`/api/projects/${project}/inference/outlines`, {
        method:'POST', headers:auth, body:JSON.stringify({model, consent:true})
      });
      if (state.project !== project || state.plan !== plan || state.revision !== revision) throw new Error('The project changed during inference. Run it again for the current drawing.');
      pending = {project, plan, revision, data};
      $('inferenceEvidence').textContent = JSON.stringify({trace:data.trace, rooms:data.suggestions.map(item => ({name:item.name, evidence:item.inference}))}, null, 2);
      $('inferenceTrace').hidden = false; $('inferenceReview').hidden = !data.suggestions.length;
      status(`${data.suggestions.length} AI proposals ready. Review their assumptions, then show them on the plan. No rooms or measurements have changed.`);
    } catch (error) { status(error.message); }
    finally { if (sent) { $('inferenceKey').value = ''; $('inferenceConsent').checked = false; } setBusy(false); }
  };
  $('inferenceReview').onclick = () => {
    if (!pending || busy) return;
    if (state.project !== pending.project || state.plan !== pending.plan || state.revision !== pending.revision || state.suggesting) {
      pending = null; $('inferenceReview').hidden = true; status('The plan changed. Run inference again before reviewing proposals.'); return;
    }
    renderRoomSuggestions(pending.data.suggestions);
    $('suggestionStatus').textContent = 'AI outlines are unchecked. Inspect each boundary and its recorded assumptions before selecting it. Existing rooms remain; avoid accepting overlapping duplicates.';
    $('inferenceReview').hidden = true;
    status('Select the AI outlines you want, then use “Use selected room outlines”. Confirm scale separately if needed.');
  };
  request('/api/inference/config').then(config => {
    secure = config.secure_transport === true;
    if (!$('inferenceModel').value.trim()) $('inferenceModel').value = config.default_model || '';
    if (config.default_model_label) $('inferenceModelHelp').textContent = `Preferred: ${config.default_model_label}. You can choose another vision model. Every outline still needs review.`;
    $('inferenceTransport').textContent = secure
      ? `Connected to ${config.base_url}. Your key is sent only when you request models or outlines.`
      : 'Personal-key entry requires HTTPS on the hosted portal. Open the same service at http://127.0.0.1:8001 on this machine for local key use, or configure HTTPS for remote users.';
    setBusy(false);
  }).catch(() => { status('Inference connection is unavailable. Local outlining remains available.'); });
})();
