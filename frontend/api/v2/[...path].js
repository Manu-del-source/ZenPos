const BACKEND_ORIGIN = "https://zenpos-ef02.onrender.com";

export default async function handler(req, res) {
  const segments = req.query.path;
  const path = Array.isArray(segments) ? segments : segments ? [segments] : [];
  const suffix = path.map((part) => encodeURIComponent(String(part))).join("/");
  const queryIndex = req.url.indexOf("?");
  const query = queryIndex >= 0 ? req.url.slice(queryIndex) : "";
  const target = `${BACKEND_ORIGIN}/api/v2/${suffix}${query}`;

  const headers = {};
  for (const name of ["accept", "authorization", "content-type", "cookie", "user-agent"]) {
    const value = req.headers[name];
    if (value) headers[name] = value;
  }
  headers["x-forwarded-host"] = req.headers.host || "";

  const options = { method: req.method, headers, redirect: "manual" };
  if (!["GET", "HEAD"].includes(req.method)) {
    const chunks = [];
    for await (const chunk of req) chunks.push(Buffer.from(chunk));
    options.body = Buffer.concat(chunks);
  }

  try {
    const upstream = await fetch(target, options);
    res.status(upstream.status);
    upstream.headers.forEach((value, name) => {
      if (!["connection", "transfer-encoding", "content-encoding", "content-length"].includes(name.toLowerCase())) {
        res.setHeader(name, value);
      }
    });
    const body = Buffer.from(await upstream.arrayBuffer());
    res.send(body);
  } catch (error) {
    console.error("ZenPOS API proxy failed:", error);
    res.status(502).json({ detail: "API backend is temporarily unreachable." });
  }
}
