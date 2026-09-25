// ============================================================
// SITE HARDENING for ff-like.noobs-api.top (paste into server.js)
// Fixes: (1) admin-login rate limiting  (2) ?token= JWT leak
// The admin password itself is set in your env vars on Render
// (whatever ADMIN_PASSWORD / ADMIN_PASS var your admin-login
// route reads) — change it in Render Dashboard -> Environment.
// ============================================================

// --- 1) ADMIN-LOGIN RATE LIMIT (5 tries per 15 min per IP) ---
// npm install express-rate-limit
const rateLimit = require("express-rate-limit");

const adminLoginLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 5,                    // 5 attempts
  message: { error: "Too many attempts. Try again in 15 minutes." },
  standardHeaders: true,
  legacyHeaders: false,
});

// put this RIGHT BEFORE your admin-login route:
// app.post("/api/user/admin-login", adminLoginLimiter, handler);
app.use("/api/user/admin-login", adminLoginLimiter);

// Optional: generic limiter on ALL /api routes (anti brute-force everywhere)
const apiLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 60, // 60 req/min per IP
  message: { error: "Too many requests" },
});
app.use("/api", apiLimiter);

// --- 2) REMOVE ?token= JWT AUTH (leaks to server logs & history) ---
// Find where you read the token, e.g.:
//   const token = req.query.token || req.headers.authorization...
// DELETE the req.query.token part, keep ONLY the header:
function auth(req, res, next) {
  const authHeader = req.headers.authorization || "";
  const token = authHeader.startsWith("Bearer ") ? authHeader.slice(7) : null;
  if (!token) return res.status(401).json({ error: "No token" });
  try {
    req.user = jwt.verify(token, process.env.JWT_SECRET);
    next();
  } catch {
    return res.status(401).json({ error: "Invalid token" });
  }
}
