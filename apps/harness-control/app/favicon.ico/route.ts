const favicon = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="12" fill="#07111f"/>
  <path d="M32 7 53 19v26L32 57 11 45V19Z" fill="none" stroke="#00d4ff" stroke-width="4"/>
  <circle cx="32" cy="32" r="9" fill="#00d4ff"/>
  <circle cx="32" cy="32" r="4" fill="#07111f"/>
</svg>`

export function GET() {
  return new Response(favicon, {
    headers: {
      "Cache-Control": "public, max-age=86400",
      "Content-Type": "image/svg+xml",
    },
  })
}
