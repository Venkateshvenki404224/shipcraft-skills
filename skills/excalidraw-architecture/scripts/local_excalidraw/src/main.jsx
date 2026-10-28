// Mounts Excalidraw with a scene from ?scene=<path> and exposes window.exportPng(outPath, scale)
// which renders the whole canvas to PNG and POSTs it to the local server's /save endpoint.
import { createRoot } from "react-dom/client";
import { useEffect, useState } from "react";
import { Excalidraw, exportToBlob } from "@excalidraw/excalidraw";
import "@excalidraw/excalidraw/index.css";

const params = new URLSearchParams(window.location.search);
const scenePath = params.get("scene");

async function loadScene() {
	if (!scenePath) return { elements: [], appState: {}, files: {} };
	const response = await fetch(`/scene?path=${encodeURIComponent(scenePath)}`);
	if (!response.ok) throw new Error(`scene load failed: ${response.status}`);
	return response.json();
}

function App() {
	const [scene, setScene] = useState(null);
	const [api, setApi] = useState(null);

	useEffect(() => {
		loadScene().then(setScene).catch((error) => {
			document.title = "scene error";
			window.__sceneError = String(error);
		});
	}, []);

	useEffect(() => {
		if (!api || !scene) return;
		window.excalidrawAPI = api;
		window.__sceneReady = true;
		document.title = `rendered ${scene.elements.length} elements`;
		// region = [y0, y1] keeps only elements whose vertical centre falls in that band (one chapter)
		window.exportPng = async (outPath, scale = 2, region = null) => {
			let elements = api.getSceneElements();
			if (region) {
				const [y0, y1] = region;
				elements = elements.filter((e) => {
					const centre = e.y + (e.height || 0) / 2;
					return centre >= y0 && centre <= y1;
				});
			}
			const blob = await exportToBlob({
				elements,
				appState: { exportBackground: true, viewBackgroundColor: "#ffffff", exportWithDarkMode: false, exportScale: scale },
				files: api.getFiles(),
				mimeType: "image/png",
				exportPadding: 40,
			});
			const saved = await fetch(`/save?path=${encodeURIComponent(outPath)}`, { method: "POST", body: blob });
			return saved.ok ? `saved ${blob.size} bytes` : `save failed ${saved.status}`;
		};
	}, [api, scene]);

	if (!scene) return <div style={{ padding: 20, fontFamily: "sans-serif" }}>loading scene…</div>;
	return (
		<div style={{ height: "100vh" }}>
			<Excalidraw
				excalidrawAPI={setApi}
				initialData={{ elements: scene.elements, appState: { viewBackgroundColor: "#ffffff" }, files: scene.files || {}, scrollToContent: true }}
				UIOptions={{ canvasActions: { loadScene: false } }}
			/>
		</div>
	);
}

createRoot(document.getElementById("root")).render(<App />);
