export function sparklineGeometry(data, width, height) {
  const values = (data || []).filter(Number.isFinite);
  if (!values.length) return { points: [], path: "", area: "" };

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = values.map((value, index) => {
    const progress = values.length === 1 ? 0.5 : index / (values.length - 1);
    return [
      progress * width,
      height - ((value - min) / range) * (height - 6) - 3,
    ];
  });
  const path = `M ${points.map((point) => point.join(" ")).join(" L ")}`;
  const firstX = points[0][0];
  const lastX = points.at(-1)[0];
  return {
    points,
    path,
    area: `${path} L ${lastX} ${height} L ${firstX} ${height} Z`,
  };
}
