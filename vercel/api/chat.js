export const config = { runtime: 'edge' };

const ALLOWED_HOSTS = ['api.deepseek.com', 'dashscope.aliyuncs.com'];

export default async function handler(req) {
  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: corsHeaders() });
  }
  if (req.method !== 'POST') {
    return json({ error: 'Method not allowed' }, 405);
  }

  try {
    const body = await req.json();
    const { apiKey, baseUrl, ...params } = body;

    if (!apiKey || !baseUrl) {
      return json({ error: 'Missing apiKey or baseUrl' }, 400);
    }

    // SSRF 防护：只允许已知的 API 域名
    let parsedUrl;
    try {
      parsedUrl = new URL(baseUrl);
    } catch {
      return json({ error: 'Invalid baseUrl' }, 400);
    }
    if (!ALLOWED_HOSTS.some(h => parsedUrl.hostname === h || parsedUrl.hostname.endsWith('.' + h))) {
      return json({ error: 'Unsupported API provider' }, 400);
    }

    const apiUrl = baseUrl.replace(/\/+$/, '') + '/chat/completions';

    const upstream = await fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify(params),
    });

    // 流式响应：直接转发
    if (params.stream) {
      return new Response(upstream.body, {
        status: upstream.status,
        headers: {
          ...corsHeaders(),
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
        },
      });
    }

    // 非流式：解析后转发
    const data = await upstream.json();
    return json(data, upstream.status);
  } catch (err) {
    return json({ error: err.message }, 500);
  }
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...corsHeaders(), 'Content-Type': 'application/json' },
  });
}

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };
}
