/**
 * Pingeon Cloudflare Worker
 *
 * GET  /         -> serves setup.ps1 for `irm "url" | iex`
 * POST /notify   -> relays an alert email to the user-supplied address
 *
 * Secrets (set via deploy.ps1 -- never stored in the repo):
 *   RESEND_API_KEY  -- from resend.com
 *   FROM_EMAIL      -- verified sender address
 *   NOTIFY_TOKEN    -- random secret; blocks unauthorized use of /notify
 *
 * Bindings (declared in wrangler.toml):
 *   IP_LIMITER      -- per-IP rate limiter for /notify
 *   TO_LIMITER      -- per-destination rate limiter for /notify
 */

const SETUP_URL =
  'https://raw.githubusercontent.com/talonbaker/Pingeon/main/setup.ps1';

const EMAIL_SUBJECT = 'Pingeon -- A slot just opened!';

// Hard caps on /notify input. The shared token is distributed to every
// installer, so anyone who installs Pingeon can call this endpoint --
// these limits constrain the blast radius of an abusive caller.
const MAX_BODY_BYTES   = 8 * 1024;
const MAX_EMAIL_LEN    = 254;   // RFC 5321
const MAX_SUMMARY_LEN  = 200;
const MAX_DATE_LEN     = 64;
const MAX_SLOTS        = 10;

// RFC-5322-ish: one @, no whitespace, a dot in the domain. Combined with
// the length cap this is strict enough to reject obvious junk.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function badRequest(msg) {
  return new Response(msg, { status: 400 });
}

function clipString(value, maxLen) {
  if (typeof value !== 'string') return '';
  return value.length > maxLen ? value.slice(0, maxLen) : value;
}

function buildEmailBody(slots, isTest) {
  if (isTest) {
    return 'This is a test alert from Pingeon.\n\nIf you received this, your alert email is configured correctly.';
  }
  const lines = slots.map(s => `  - ${s.summary} on ${s.date}`).join('\n');
  return (
    `A slot just opened on the calendar you are monitoring:\n\n${lines}\n\n` +
    `Go claim it before someone else does!\n\n---\nPingeon`
  );
}

async function handleInstall(env) {
  const upstream = await fetch(SETUP_URL, {
    headers: { 'User-Agent': 'Pingeon-Worker/1.0' },
  });
  if (!upstream.ok) {
    return new Response(
      `# Failed to fetch setup script (HTTP ${upstream.status})`,
      { status: 502, headers: { 'Content-Type': 'text/plain' } },
    );
  }

  // Inject the notify token here so it never appears in the GitHub repo.
  // The repo always holds an empty placeholder; the real value lives only
  // in Cloudflare secrets and on the user's local machine after install.
  //
  // The token is interpolated into a PowerShell single-quoted string on the
  // installer's machine. PowerShell escapes ' inside '...' by doubling it
  // (''), so we must do the same here -- otherwise a token containing '
  // could break out of the literal and execute arbitrary code on installers.
  let script = await upstream.text();
  const rawToken = env.NOTIFY_TOKEN || '';
  const token = rawToken.replace(/'/g, "''");
  script += `\n$PingeonNotifyToken = '${token}'\n`;

  return new Response(script, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'no-store',
    },
  });
}

async function handleNotify(request, env) {
  // Validate shared token -- stops random people from using this as a spam relay
  const auth = request.headers.get('Authorization') || '';
  const token = auth.startsWith('Bearer ') ? auth.slice(7) : '';
  if (!env.NOTIFY_TOKEN || token !== env.NOTIFY_TOKEN) {
    return new Response('Unauthorized', { status: 401 });
  }

  // Per-IP rate limit -- caps how fast any single source can hit /notify,
  // even with a valid token. Defends against an installer extracting the
  // token and using the relay for spam.
  const clientIP = request.headers.get('CF-Connecting-IP') || 'unknown';
  if (env.IP_LIMITER) {
    const { success } = await env.IP_LIMITER.limit({ key: clientIP });
    if (!success) {
      return new Response('Rate limit exceeded', { status: 429 });
    }
  }

  // Cap request body size before parsing -- a huge JSON blob shouldn't
  // even reach JSON.parse.
  const lenHeader = request.headers.get('Content-Length');
  if (lenHeader && Number(lenHeader) > MAX_BODY_BYTES) {
    return new Response('Payload too large', { status: 413 });
  }
  const raw = await request.text();
  if (raw.length > MAX_BODY_BYTES) {
    return new Response('Payload too large', { status: 413 });
  }

  let body;
  try {
    body = JSON.parse(raw);
  } catch {
    return badRequest('Bad JSON');
  }
  if (body === null || typeof body !== 'object' || Array.isArray(body)) {
    return badRequest('Bad JSON');
  }

  const to = typeof body.to === 'string' ? body.to.trim() : '';
  if (!to || to.length > MAX_EMAIL_LEN || !EMAIL_RE.test(to)) {
    return badRequest('Missing or invalid "to" address');
  }

  // Per-destination rate limit -- stops a malicious caller from flooding
  // a single victim's inbox even within their per-IP budget.
  if (env.TO_LIMITER) {
    const { success } = await env.TO_LIMITER.limit({ key: to.toLowerCase() });
    if (!success) {
      return new Response('Rate limit exceeded', { status: 429 });
    }
  }

  const isTest = Boolean(body.test);

  // Sanitize and cap slots. Anything malformed is dropped silently;
  // length caps keep one bad caller from generating gigantic emails.
  const rawSlots = Array.isArray(body.slots) ? body.slots.slice(0, MAX_SLOTS) : [];
  const slots = [];
  for (const s of rawSlots) {
    if (!s || typeof s !== 'object') continue;
    slots.push({
      summary: clipString(s.summary, MAX_SUMMARY_LEN),
      date:    clipString(s.date,    MAX_DATE_LEN),
    });
  }

  const emailPayload = {
    from: env.FROM_EMAIL || 'Pingeon <onboarding@resend.dev>',
    to:   [to],
    subject: isTest ? 'Pingeon -- Test Alert' : EMAIL_SUBJECT,
    text:    buildEmailBody(slots, isTest),
  };

  const resendRes = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.RESEND_API_KEY}`,
      'Content-Type':  'application/json',
    },
    body: JSON.stringify(emailPayload),
  });

  if (!resendRes.ok) {
    // Don't echo the upstream error body back to the caller -- it can
    // leak details about our Resend account / config.
    return new Response('Email service error', { status: 502 });
  }

  return new Response('OK', { status: 200 });
}

export default {
  async fetch(request, env) {
    const url    = new URL(request.url);
    const method = request.method.toUpperCase();

    if (method === 'POST' && url.pathname === '/notify') {
      return handleNotify(request, env);
    }

    return handleInstall(env);
  },
};
