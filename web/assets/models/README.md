# Worker model

`worker.glb` is the "Xbot" rigged humanoid (Mixamo rig) from the three.js examples
(`examples/models/gltf/Xbot.glb`, three.js r128). The web UI recolours it as a worker
(hi-vis vest, hard hat, gloves, boots) at runtime in `web/js/human3d.js`.

`worker_glb.js` is the same file base64-encoded so the UI also works when opened via
`file://`. Regenerate it after replacing the model:

    python3 scripts/embed_model.py
