import * as THREE from "three";

function floatAttribute(attribute) {
  const values = new Float32Array(attribute.count * attribute.itemSize);
  for (let index = 0; index < attribute.count; index += 1) {
    const offset = index * attribute.itemSize;
    values[offset] = attribute.getX(index);
    if (attribute.itemSize > 1) values[offset + 1] = attribute.getY(index);
    if (attribute.itemSize > 2) values[offset + 2] = attribute.getZ(index);
    if (attribute.itemSize > 3) values[offset + 3] = attribute.getW(index);
  }
  return new THREE.Float32BufferAttribute(values, attribute.itemSize);
}

export function dequantizeGeometry(geometry) {
  const result = geometry.clone();
  Object.entries(result.attributes).forEach(([name, attribute]) => {
    if (attribute.normalized) {
      result.setAttribute(name, floatAttribute(attribute));
    }
  });
  return result;
}
