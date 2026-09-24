// Cloudflare Pages Function: POST /api/claim
// Receives "Claim your listing" submissions from claim.html.
//
// Degrades gracefully by design:
//   - With no secrets configured it validates + logs the submission and returns
//     success, so the form works on any Pages deployment out of the box.
//   - If RESEND_API_KEY (+ CLAIM_NOTIFY_TO / CLAIM_NOTIFY_FROM) is set, it emails
//     the submission via Resend.
//   - If CLAIM_WEBHOOK_URL is set, it also forwards the raw JSON to that webhook.
//   - If TURNSTILE_SECRET is set, it verifies the Cloudflare Turnstile token.
//
// Environment variables (all optional) are configured in the Pages dashboard.

const REQUIRED = ["contact_name", "email", "business_name", "trade"];
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

async function parseBody(request) {
  const ct = request.headers.get("content-type") || "";
  if (ct.includes("application/json")) return await request.json();
  const form = await request.formData();
  return Object.fromEntries(form.entries());
}

async function verifyTurnstile(secret, token, ip) {
  if (!secret) return true; // not configured -> skip
  if (!token) return false;
  const body = new FormData();
  body.append("secret", secret);
  body.append("response", token);
  if (ip) body.append("remoteip", ip);
  try {
    const r = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "POST",
      body,
    });
    const data = await r.json();
    return !!data.success;
  } catch (e) {
    return false;
  }
}

async function sendEmail(env, data) {
  if (!env.RESEND_API_KEY || !env.CLAIM_NOTIFY_TO || !env.CLAIM_NOTIFY_FROM) return;
  const lines = Object.entries(data)
    .filter(([k]) => k !== "cf-turnstile-response" && k !== "company_website")
    .map(([k, v]) => `${k}: ${v}`)
    .join("\n");
  await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      from: env.CLAIM_NOTIFY_FROM,
      to: env.CLAIM_NOTIFY_TO,
      reply_to: data.email,
      subject: `New listing claim: ${data.business_name}`,
      text: `New claim submission from grandtraversebuilders.com\n\n${lines}`,
    }),
  });
}

async function forwardWebhook(env, data) {
  if (!env.CLAIM_WEBHOOK_URL) return;
  await fetch(env.CLAIM_WEBHOOK_URL, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ source: "grandtraversebuilders.com", ...data }),
  });
}

export async function onRequestPost({ request, env }) {
  let data;
  try {
    data = await parseBody(request);
  } catch (e) {
    return json({ ok: false, error: "Invalid request body." }, 400);
  }

  // Honeypot: real users never fill this hidden field.
  if (data.company_website) return json({ ok: true });

  const missing = REQUIRED.filter((f) => !String(data[f] || "").trim());
  if (missing.length) {
    return json({ ok: false, error: `Missing required fields: ${missing.join(", ")}` }, 422);
  }
  if (!EMAIL_RE.test(String(data.email).trim())) {
    return json({ ok: false, error: "Please enter a valid email address." }, 422);
  }

  const ip = request.headers.get("cf-connecting-ip") || "";
  const ok = await verifyTurnstile(env.TURNSTILE_SECRET, data["cf-turnstile-response"], ip);
  if (!ok) return json({ ok: false, error: "Spam check failed. Please try again." }, 403);

  try {
    await Promise.all([sendEmail(env, data), forwardWebhook(env, data)]);
  } catch (e) {
    // Don't lose the lead on delivery failure — log and still succeed.
    console.error("claim delivery error:", e && e.message);
  }
  console.log("claim submission:", JSON.stringify({ business: data.business_name, email: data.email, trade: data.trade }));

  return json({ ok: true });
}

// Non-POST methods are not allowed on this endpoint.
export async function onRequestGet() {
  return json({ ok: false, error: "Method not allowed." }, 405);
}
