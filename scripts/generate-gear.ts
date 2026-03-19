import { mkdirSync, writeFileSync } from "node:fs";
import * as THREE from "three";
import { GLTFExporter } from "three/examples/jsm/exporters/GLTFExporter.js";

type LoadEndHandler = (() => void) | null;

class NodeFileReader {
  public result: string | null = null;
  public onloadend: LoadEndHandler = null;

  public addEventListener(type: string, handler: () => void): void {
    if (type === "loadend") {
      this.onloadend = handler;
    }
  }

  public readAsDataURL(blob: Blob): void {
    void blob.arrayBuffer().then((buffer) => {
      const base64 = Buffer.from(buffer).toString("base64");
      const mime = blob.type || "application/octet-stream";
      this.result = `data:${mime};base64,${base64}`;
      if (this.onloadend) {
        this.onloadend();
      }
    });
  }
}

const fileReaderGlobal = globalThis as unknown as { FileReader?: typeof NodeFileReader };
if (!fileReaderGlobal.FileReader) {
  fileReaderGlobal.FileReader = NodeFileReader;
}

const scene = new THREE.Scene();

const geometry = new THREE.TorusKnotGeometry(0.8, 0.25, 192, 40);
const material = new THREE.MeshStandardMaterial({
  color: new THREE.Color("#374151"),
  metalness: 0.9,
  roughness: 0.15,
});

const mesh = new THREE.Mesh(geometry, material);
mesh.rotation.x = Math.PI / 6;
mesh.rotation.y = Math.PI / 5;
scene.add(mesh);

const exporter = new GLTFExporter();

exporter.parse(
  scene,
  (result) => {
    if (ArrayBuffer.isView(result) || result instanceof ArrayBuffer) {
      throw new Error("Expected JSON glTF output, received binary output.");
    }

    mkdirSync("public/models", { recursive: true });
    writeFileSync("public/models/gear.gltf", JSON.stringify(result, null, 2));
    console.log("Generated public/models/gear.gltf");
  },
  (error) => {
    console.error("Failed to generate gear.gltf:", error);
    process.exitCode = 1;
  },
  { binary: false },
);
