const BACKEND_ORIGIN = "https://zenpos-ef02.onrender.com";

export default async function handler(req, res) {
  const requestPath = (req.url || "/api").split("?", 1)[0];
  const suffix = requestPath.replace(/^\/api\/?/, "");
  const queryIndex = (req.url || "").indexOf("?");
  const query = queryIndex >= 0 ? req.url.slice(queryIndex) : "";
  const trailingSlash = requestPath.endsWith("/") && suffix.length > 0 ? "/" : "";
  const target = `${BACKEND_ORIGIN}/api/${suffix}${trailingSlash}${query}`;

  const headers = {};
  for (const name of ["accept", "authorization", "content-type", "user-agent"]) {
    const value = req.headers[name];
    if (value) headers[name] = value;
  }

  const options = { method: req.method, headers, redirect: "follow" };
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
    res.send(Buffer.from(await upstream.arrayBuffer()));
  } catch (error) {
    console.error("ZenPOS API proxy failed:", error);
    res.status(502).json({ detail: "API backend is temporarily unreachable." });
  }
}
