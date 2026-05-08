/**
 * Pingeon Cloudflare Worker
 *
 * GET  /         -> serves setup.ps1 for `irm "url" | iex`
 * POST /notify   -> relays an alert email to the user-supplied address
 *
 * Secrets (set via deploy.ps1 -- never stored in the repo):
 *   RESEND_API_KEY  -- from resend.com
 *   FROM_EMAIL      -- verified sender address
 *
 * Bindings (declared in wrangler.toml):
 *   IP_LIMIT        -- per-IP rate limit on /notify
 *   TO_LIMIT        -- per-recipient daily cap on /notify
 */

const SETUP_URL =
  'https://raw.githubusercontent.com/talonbaker/Pingeon/main/setup.ps1';

const SUBJECT_TEST    = 'PINGEON!--Test Alert';
const SUBJECT_INITIAL = 'PINGEON!--Currently Open Dates';
const SUBJECT_UPDATE  = 'PINGEON!--Found an Opening';

// Hard caps. Defense-in-depth in case the auth token leaks: even with the
// token, an attacker can't post huge bodies, spam arbitrary content into the
// email body, or use this as a many-recipient relay.
const MAX_BODY_BYTES = 16 * 1024;
const MAX_SLOTS      = 100;
const TO_REGEX       = /^[^\s@<>"',;:\\]+@[^\s@<>"',;:\\]+\.[^\s@<>"',;:\\]+$/;
const TO_MAX_LEN     = 254;
const DATE_REGEX     = /^\d{4}-\d{2}-\d{2}$/;
const ALLOWED_KINDS  = new Set(['initial', 'update']);
const NOTE_MAX_LEN   = 500;

// Pigeon-themed signoffs. One is picked at random for every email Pingeon sends
// (test, initial snapshot, or update alert) so each message has a little
// personality. Add to this list freely.
const SIGNOFFS = [
  'Coo coo, signing off!',
  'Wings up, off to the next ledge.',
  'Stay breadcrumb-savvy.',
  'Yours in pigeonly devotion,',
  'Flap you later.',
  'Beak regards,',
  "Don't feed the seagulls.",
  'Pecking order maintained.',
  'Coo it however you want.',
  'Off to bother a statue.',
  'Catch you on the next perch.',
  'Stay puffed.',
  'Roost easy tonight.',
  'Always a-pigeon, never a-loaf.',
  'Talons crossed.',
  "Wing it 'til you make it.",
  'May your bread crusts be plentiful.',
  'Fly high, land low, eat fries.',
  'Coos and kisses,',
  "Don't let the feathers ruffle you.",
  'Stay flocking awesome.',
  'Bread now, regrets later.',
  'Pigeon out.',
  'Until our wings cross again,',
  'Keep on cooing.',
];

function pickSignoff() {
  return SIGNOFFS[Math.floor(Math.random() * SIGNOFFS.length)];
}

// Strip ASCII control characters from user-supplied note text (keep \n, \r, \t).
// The note is dropped into a plain-text email body, so this is more about
// keeping the rendering clean than preventing header injection.
function sanitizeNote(s) {
  return s.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '');
}

function txt(status, body) {
  return new Response(body, {
    status,
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}

function pickSubject(kind, isTest) {
  if (isTest) return SUBJECT_TEST;
  if (kind === 'initial') return SUBJECT_INITIAL;
  return SUBJECT_UPDATE;
}

function buildEmailBody(slots, kind, isTest, note) {
  const signoff = pickSignoff();
  const sig = `---\n${signoff}\n— Pingeon`;

  if (isTest) {
    const intro =
      "Coo coo! It's your friendly neighborhood Pingeon, just flapping by " +
      "to make sure this nest is wired up right.\n\n" +
      "If you're reading this, your alert inbox is good to go — Pingeon will " +
      "swoop in the moment a slot opens up on the calendar you're watching.";
    const noteBlock = note
      ? `\n\n----- Your note -----\n${note}\n---------------------`
      : '';
    return `${intro}${noteBlock}\n\n${sig}`;
  }

  const lines = slots.map(s => `  - ${s.date}`).join('\n');
  if (kind === 'initial') {
    return (
      `Pingeon is now monitoring this calendar. These dates are currently open:\n\n${lines}\n\n` +
      `You will only get more emails when additional slots open up.\n\n${sig}`
    );
  }
  const plural = slots.length === 1 ? 'A slot has' : 'Slots have';
  return (
    `${plural} opened on the calendar you are monitoring:\n\n${lines}\n\n` +
    `Go claim it before someone else does!\n\n${sig}`
  );
}

async function handleInstall(env) {
  const upstream = await fetch(SETUP_URL, {
    headers: { 'User-Agent': 'Pingeon-Worker/1.0' },
  });
  if (!upstream.ok) {
    return txt(502, `# Failed to fetch setup script (HTTP ${upstream.status})`);
  }

  const script = await upstream.text();
  return new Response(script, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}

function validatePayload(body) {
  if (typeof body !== 'object' || body === null) {
    return { error: 'Body must be a JSON object.' };
  }

  const isTest = Boolean(body.test);
  const kindRaw = typeof body.kind === 'string' ? body.kind : 'update';
  const kind = ALLOWED_KINDS.has(kindRaw) ? kindRaw : 'update';

  const to = (typeof body.to === 'string' ? body.to : '').trim();
  if (!to || to.length > TO_MAX_LEN || !TO_REGEX.test(to)) {
    return { error: 'Invalid "to" address.' };
  }

  let slots = [];
  if (!isTest) {
    const raw = Array.isArray(body.slots) ? body.slots : [];
    if (raw.length > MAX_SLOTS) {
      return { error: `Too many slots (max ${MAX_SLOTS}).` };
    }
    for (const s of raw) {
      if (!s || typeof s !== 'object') {
        return { error: 'Each slot must be an object.' };
      }
      if (typeof s.date !== 'string' || !DATE_REGEX.test(s.date)) {
        return { error: 'Each slot.date must be YYYY-MM-DD.' };
      }
      slots.push({ date: s.date });
    }
  }

  // Optional free-form note attached to test emails (e.g. the calendar URL the
  // user is monitoring, so it lands in their inbox as a reminder). Only
  // accepted on test sends — alert emails are slot-only and shouldn't carry
  // arbitrary text.
  let note = '';
  if (isTest && body.note != null && body.note !== '') {
    if (typeof body.note !== 'string') {
      return { error: 'Note must be a string.' };
    }
    if (body.note.length > NOTE_MAX_LEN) {
      return { error: `Note too long (max ${NOTE_MAX_LEN} chars).` };
    }
    note = sanitizeNote(body.note);
  }

  return { to, kind, isTest, slots, note };
}

async function handleNotify(request, env) {
  // 1. Hard size cap before parsing -- prevents resource exhaustion.
  const lenHdr = request.headers.get('content-length');
  if (lenHdr && Number(lenHdr) > MAX_BODY_BYTES) {
    return txt(413, 'Payload too large');
  }

  // 2. Per-IP rate limit -- caps abuse even if token leaks.
  const ip = request.headers.get('cf-connecting-ip') || 'unknown';
  if (env.IP_LIMIT) {
    const r = await env.IP_LIMIT.limit({ key: ip });
    if (!r.success) return txt(429, 'Rate limit exceeded.');
  }

  // 3. Parse with explicit byte limit.
  const raw = await request.text();
  if (raw.length > MAX_BODY_BYTES) {
    return txt(413, 'Payload too large');
  }
  let body;
  try {
    body = JSON.parse(raw);
  } catch {
    return txt(400, 'Bad JSON');
  }

  // 5. Strict validation.
  const v = validatePayload(body);
  if (v.error) return txt(400, v.error);

  // 6. Per-recipient rate limit -- prevents one stolen token from
  //    flooding an unrelated address.
  if (env.TO_LIMIT) {
    const r = await env.TO_LIMIT.limit({ key: v.to });
    if (!r.success) return txt(429, 'Recipient rate limit exceeded.');
  }

  // 7. Send.
  const emailPayload = {
    from: env.FROM_EMAIL || 'Pingeon <onboarding@resend.dev>',
    to:   [v.to],
    subject: pickSubject(v.kind, v.isTest),
    text:    buildEmailBody(v.slots, v.kind, v.isTest, v.note),
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
    const detail = await resendRes.text();
    return txt(502, `Email service error (Resend ${resendRes.status}): ${detail}`);
  }
  return txt(200, 'OK');
}

export default {
  async fetch(request, env) {
    const url    = new URL(request.url);
    const method = request.method.toUpperCase();

    if (method === 'POST' && url.pathname === '/notify') {
      return handleNotify(request, env);
    }
    if (method === 'GET' && (url.pathname === '/' || url.pathname === '')) {
      return handleInstall(env);
    }
    return txt(404, 'Not Found');
  },
};
