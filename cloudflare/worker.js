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
 */

const SETUP_URL =
  'https://raw.githubusercontent.com/talonbaker/Pingeon/main/setup.ps1';

const EMAIL_SUBJECT = 'Pingeon -- A slot just opened!';

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
  let script = await upstream.text();
  const token = env.NOTIFY_TOKEN || '';
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

  let body;
  try {
    body = await request.json();
  } catch {
    return new Response('Bad JSON', { status: 400 });
  }

  const to = (body.to || '').trim();
  if (!to || !to.includes('@')) {
    return new Response('Missing or invalid "to" address', { status: 400 });
  }

  const isTest = Boolean(body.test);
  const slots  = Array.isArray(body.slots) ? body.slots : [];

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
    const err = await resendRes.text();
    return new Response(`Email service error: ${err}`, { status: 502 });
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
